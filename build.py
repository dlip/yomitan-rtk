#!/usr/bin/env python3
"""Build a standalone RTK kanji dictionary from CSV."""

import argparse
import csv
import hashlib
import io
import json
import sys
import zipfile
from pathlib import Path

from rtk import ROOT, read_rtk, write_atomic


def create_archive(csv_data):
    records = read_rtk(csv_data)
    entries = []
    for kanji, values in records.items():
        meanings = []
        for number, keyword, story in values:
            heading = keyword
            if number:
                heading = f"{keyword} (#{number})" if keyword else f"#{number}"
            text = "\n".join(value for value in (heading, story) if value)
            if text and text not in meanings:
                meanings.append(text)
        if meanings:
            entries.append([kanji, "", "", "", meanings, {}])
    if not entries:
        raise ValueError("CSV contains no RTK information")
    index = {
        "title": "RTK",
        "format": 3,
        "revision": f"rtk-standalone1-{hashlib.sha256(csv_data).hexdigest()[:12]}",
        "sequenced": False,
        "description": "RTK keywords, numbers, and mnemonic stories.",
    }
    result = io.BytesIO()
    with zipfile.ZipFile(result, "w") as archive:
        for name, data in (("index.json", index), ("kanji_bank_1.json", entries)):
            archive.writestr(
                zipfile.ZipInfo(name),
                json.dumps(data, ensure_ascii=False).encode("utf-8"),
                compress_type=zipfile.ZIP_DEFLATED,
                compresslevel=9,
            )
    return result.getvalue(), {
        "entries": len(entries),
        "skipped": len(records) - len(entries),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--csv", type=Path, default=ROOT / "rtk.csv", help="RTK CSV path"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "dist/RTK.zip",
        help="Generated dictionary ZIP path",
    )
    args = parser.parse_args(argv)
    try:
        archive, stats = create_archive(args.csv.read_bytes())
        write_atomic(args.output, archive)
    except (OSError, ValueError, csv.Error) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    print(f"Wrote {args.output}")
    print(
        f"{stats['entries']:,} RTK entries; {stats['skipped']:,} kanji skipped without RTK information."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
