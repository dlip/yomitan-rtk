#!/usr/bin/env python3
"""Build an RTK-enriched KANJIDIC dictionary for Yomitan."""

import argparse
import csv
import hashlib
import io
import json
import os
import re
import sys
import tempfile
import zipfile
from pathlib import Path
from urllib.request import Request, urlopen

SOURCE_URL = (
    "https://github.com/yomidevs/jmdict-yomitan/releases/latest/download/"
    "KANJIDIC_english.zip"
)
ROOT = Path(__file__).resolve().parent


def read_rtk(data):
    records = {}
    reader = csv.reader(io.StringIO(data.decode("utf-8-sig"), newline=""), strict=True)
    for row in reader:
        if len(row) != 4:
            raise ValueError(f"CSV line {reader.line_num}: expected four columns")
        number, kanji, keyword, story = (value.strip() for value in row)
        if len(kanji) != 1:
            raise ValueError(
                f"CSV line {reader.line_num}: expected one kanji character"
            )
        if number and not number.isdecimal():
            raise ValueError(
                f"CSV line {reader.line_num}: invalid RTK number {number!r}"
            )
        values = (number, keyword, story)
        existing = records.setdefault(kanji, [])
        if not any(values):
            continue
        for index, previous in enumerate(existing):
            if all(not a or not b or a == b for a, b in zip(previous, values)):
                existing[index] = tuple(a or b for a, b in zip(previous, values))
                break
        else:
            existing.append(values)
    if not records:
        raise ValueError("CSV contains no kanji")
    return records


def rtk_meanings(records):
    meanings = []
    for number, keyword, story in records:
        label = f"RTK #{number}" if number else "RTK"
        if number or keyword:
            meanings.append(f"{label}: {keyword}" if keyword else label)
        if story:
            meanings.append(f"RTK story: {story}")
    return list(dict.fromkeys(meanings))


def validate_entry(entry, bank):
    if (
        not isinstance(entry, list)
        or len(entry) != 6
        or not all(isinstance(value, str) for value in entry[:4])
        or not entry[0]
        or not isinstance(entry[4], list)
        or not all(isinstance(value, str) for value in entry[4])
        or not isinstance(entry[5], dict)
        or not all(isinstance(value, str) for value in entry[5].values())
    ):
        raise ValueError(f"{bank}: invalid Yomitan kanji entry")


def enrich_archive(source, csv_data):
    records = read_rtk(csv_data)
    result = io.BytesIO()
    seen = set()
    entry_count = enriched_count = 0
    with zipfile.ZipFile(io.BytesIO(source)) as original:
        names = original.namelist()
        if len(names) != len(set(names)):
            raise ValueError("Source ZIP contains duplicate filenames")
        if "index.json" not in names:
            raise ValueError("Source ZIP is missing index.json")
        index = json.loads(original.read("index.json"))
        if not isinstance(index, dict) or index.get("format") != 3:
            raise ValueError("Expected a Yomitan format 3 dictionary")
        revision = index.get("revision")
        if not isinstance(revision, str) or not revision:
            raise ValueError("Dictionary index is missing a revision")
        index["title"] = "KANJIDIC + RTK"
        index["revision"] = (
            f"{revision}-rtk-{hashlib.sha256(csv_data).hexdigest()[:12]}"
        )
        index.pop("isUpdatable", None)
        index.pop("indexUrl", None)
        index.pop("downloadUrl", None)
        bank_count = 0
        with zipfile.ZipFile(result, "w") as output:
            output.comment = original.comment
            for info in original.infolist():
                data = original.read(info)
                if info.filename == "index.json":
                    data = json.dumps(index, ensure_ascii=False).encode("utf-8")
                elif re.fullmatch(r"kanji_bank_[0-9]+\.json", info.filename):
                    bank_count += 1
                    entries = json.loads(data)
                    if not isinstance(entries, list):
                        raise ValueError(f"{info.filename}: expected an array")
                    for entry in entries:
                        validate_entry(entry, info.filename)
                        kanji = entry[0]
                        seen.add(kanji)
                        entry_count += 1
                        additions = rtk_meanings(records.get(kanji, []))
                        if additions:
                            entry[4] = additions + entry[4]
                            enriched_count += 1
                    data = json.dumps(entries, ensure_ascii=False).encode("utf-8")
                output.writestr(info, data)
        if not bank_count or not entry_count:
            raise ValueError("Source ZIP contains no kanji entries")
    return result.getvalue(), {
        "csv_kanji": len(records),
        "entries": entry_count,
        "enriched": enriched_count,
        "unmatched": sorted(records.keys() - seen),
    }


def write_atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(data)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--csv", type=Path, default=ROOT / "rtk.csv", help="RTK CSV path"
    )
    parser.add_argument(
        "--source-zip", type=Path, help="Use a local KANJIDIC ZIP offline"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "dist/KANJIDIC_RTK_english.zip",
        help="Generated dictionary ZIP path",
    )
    args = parser.parse_args(argv)
    try:
        csv_data = args.csv.read_bytes()
        read_rtk(csv_data)
        if args.source_zip:
            source = args.source_zip.read_bytes()
        else:
            print("Downloading KANJIDIC English...", flush=True)
            request = Request(SOURCE_URL, headers={"User-Agent": "kanjidic-rtk/1"})
            with urlopen(request, timeout=60) as response:
                source = response.read()
        archive, stats = enrich_archive(source, csv_data)
        write_atomic(args.output, archive)
    except (OSError, ValueError, csv.Error, zipfile.BadZipFile) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    print(f"Wrote {args.output}")
    print(
        f"{stats['entries']:,} dictionary entries; {stats['csv_kanji']:,} unique CSV kanji; "
        f"{stats['enriched']:,} entries enriched; {len(stats['unmatched']):,} unmatched kanji."
    )
    if stats["unmatched"]:
        print("Unmatched kanji: " + " ".join(stats["unmatched"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
