#!/usr/bin/env python3
"""Build an RTK-enriched KANJIDIC dictionary for Yomitan."""

import argparse
import csv
import hashlib
import io
import json
import re
import sys
import zipfile
from pathlib import Path
from urllib.request import Request, urlopen

from rtk import ROOT, read_rtk, write_atomic

SOURCE_URL = (
    "https://github.com/yomidevs/jmdict-yomitan/releases/latest/download/"
    "KANJIDIC_english.zip"
)


def rtk_meanings(records):
    meanings = []
    for number, keyword, story in records:
        label = f"RTK #{number}" if number else "RTK"
        if number or keyword:
            meanings.append(f"{label}: {keyword}" if keyword else label)
        if story:
            meanings.append(f"RTK story: {story}")
    return list(dict.fromkeys(meanings))


def rtk_tags(kanji, records):
    tags = []
    for index, (number, keyword, story) in enumerate(records):
        for offset, (field, value) in enumerate(
            (
                ("keyword", keyword),
                ("number", f"#{number}" if number else ""),
                ("story", story),
            )
        ):
            if value:
                tags.append(
                    [
                        f"RTK-{kanji}-{index + 1}-{field}",
                        f"rtk-{field}",
                        1000 + index * 3 + offset,
                        value,
                        0,
                    ]
                )
    return tags


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
    styles = (ROOT / "yomitan-rtk.css").read_bytes()
    content_hash = hashlib.sha256(csv_data + b"\0" + styles).hexdigest()[:12]
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
        index["revision"] = f"{revision}-rtk3-{content_hash}"
        index.pop("isUpdatable", None)
        index.pop("indexUrl", None)
        index.pop("downloadUrl", None)
        bank_count = 0
        tags = []
        with zipfile.ZipFile(result, "w") as output:
            output.comment = original.comment
            for info in original.infolist():
                if info.filename == "styles.css":
                    continue
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
                            entry_tags = rtk_tags(kanji, records[kanji])
                            tags.extend(entry_tags)
                            entry[3] = " ".join(
                                filter(
                                    None, [entry[3], *(tag[0] for tag in entry_tags)]
                                )
                            )
                            entry[4] = ["\n".join(additions)] + entry[4]
                            enriched_count += 1
                    data = json.dumps(entries, ensure_ascii=False).encode("utf-8")
                output.writestr(info, data)
            if tags:
                tag_numbers = [
                    int(match[1])
                    for name in names
                    if (match := re.fullmatch(r"tag_bank_([0-9]+)\.json", name))
                ]
                output.writestr(
                    f"tag_bank_{max(tag_numbers, default=0) + 1}.json",
                    json.dumps(
                        list({tag[0]: tag for tag in tags}.values()), ensure_ascii=False
                    ),
                    compress_type=zipfile.ZIP_DEFLATED,
                )
            upstream_styles = (
                original.read("styles.css") if "styles.css" in names else b""
            )
            if tags or upstream_styles:
                output.writestr(
                    "styles.css",
                    upstream_styles + b"\n" + styles if tags else upstream_styles,
                    compress_type=zipfile.ZIP_DEFLATED,
                )
        if not bank_count or not entry_count:
            raise ValueError("Source ZIP contains no kanji entries")
    return result.getvalue(), {
        "csv_kanji": len(records),
        "entries": entry_count,
        "enriched": enriched_count,
        "unmatched": sorted(records.keys() - seen),
    }


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
