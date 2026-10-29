import contextlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import build


def unpack(data):
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return json.loads(archive.read("index.json")), json.loads(
            archive.read("kanji_bank_1.json")
        )


class StandaloneTests(unittest.TestCase):
    def test_native_kanji_dictionary_without_layout_dependencies(self):
        data, stats = build.create_archive(
            "20,明,bright,The sun makes the moon bright.\n,暗,,\n".encode()
        )
        index, entries = unpack(data)
        self.assertEqual(stats, {"entries": 1, "skipped": 1})
        self.assertEqual(index["title"], "RTK")
        self.assertEqual(index["format"], 3)
        for field in ("isUpdatable", "indexUrl", "downloadUrl"):
            self.assertNotIn(field, index)
        self.assertEqual(
            entries,
            [["明", "", "", "", ["bright (#20)\nThe sun makes the moon bright."], {}]],
        )
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            self.assertIsNone(archive.testzip())
            self.assertEqual(archive.namelist(), ["index.json", "kanji_bank_1.json"])

    def test_missing_fields_and_multiline_stories(self):
        _, entries = unpack(
            build.create_archive('1,一,,\n,二,two,\n,三,,"first\nsecond"\n'.encode())[0]
        )
        self.assertEqual(
            [entry[4] for entry in entries], [["#1"], ["two"], ["first\nsecond"]]
        )

    def test_duplicate_and_conflicting_records(self):
        _, entries = unpack(
            build.create_archive(
                "1,一,one,\n,一,,first story\n,一,,\n2,一,single,second story\n".encode()
            )[0]
        )
        self.assertEqual(len(entries), 1)
        self.assertEqual(
            entries[0][4], ["one (#1)\nfirst story", "single (#2)\nsecond story"]
        )

    def test_no_information_fails(self):
        with self.assertRaisesRegex(ValueError, "no RTK information"):
            build.create_archive(",一,,\n".encode())

    def test_repeatable_build_and_revision_tracks_csv(self):
        csv_data = "1,一,one,story\n".encode()
        first = build.create_archive(csv_data)[0]
        self.assertEqual(first, build.create_archive(csv_data)[0])
        changed = build.create_archive(csv_data.replace(b"story", b"changed"))[0]
        self.assertNotEqual(
            unpack(first)[0]["revision"], unpack(changed)[0]["revision"]
        )

    def test_cli_works_offline_and_without_stylesheet(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            csv_path = root / "rtk.csv"
            csv_path.write_text("1,一,one,story\n", encoding="utf-8")
            output = root / "dist/RTK.zip"
            with (
                patch("urllib.request.urlopen") as download,
                patch.object(build, "ROOT", root),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                code = build.main([])
            self.assertEqual(code, 0)
            download.assert_not_called()
            self.assertEqual(unpack(output.read_bytes())[0]["title"], "RTK")

    def test_invalid_csv_preserves_existing_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            csv_path = root / "rtk.csv"
            csv_path.write_text("invalid csv", encoding="utf-8")
            output = root / "result.zip"
            output.write_bytes(b"previous output")
            with contextlib.redirect_stderr(io.StringIO()) as errors:
                code = build.main(["--csv", str(csv_path), "--output", str(output)])
            self.assertEqual(code, 1)
            self.assertIn("expected four columns", errors.getvalue())
            self.assertEqual(output.read_bytes(), b"previous output")


if __name__ == "__main__":
    unittest.main()
