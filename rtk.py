import csv
import io
import os
import tempfile
from pathlib import Path

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
