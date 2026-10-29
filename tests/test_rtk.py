import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import rtk


class CsvTests(unittest.TestCase):
    def test_quoted_unicode_multiline_and_bom(self):
        records = rtk.read_rtk('\ufeff1,一,"one, only","line 1\n日本語"\r\n'.encode())
        self.assertEqual(records["一"], [("1", "one, only", "line 1\n日本語")])

    def test_duplicates_merge_without_blank_overwrite(self):
        records = rtk.read_rtk(
            "1,一,one,\n,一,,story\n,一,,\n1,一,one,story\n".encode()
        )
        self.assertEqual(records["一"], [("1", "one", "story")])

    def test_conflicting_records_preserved(self):
        records = rtk.read_rtk("1,一,one,story\n2,一,single,story\n".encode())
        self.assertEqual(
            records["一"], [("1", "one", "story"), ("2", "single", "story")]
        )

    def test_optional_fields(self):
        records = rtk.read_rtk("1,一,,\n,二,two,\n,三,,story\n,四,,\n".encode())
        self.assertEqual(
            records,
            {
                "一": [("1", "", "")],
                "二": [("", "two", "")],
                "三": [("", "", "story")],
                "四": [],
            },
        )

    def test_malformed_csv(self):
        for data in (
            b"",
            b"1,x,keyword\n",
            b"1,,keyword,story\n",
            b"abc,x,keyword,story\n",
            b'1,x,keyword,"unterminated',
        ):
            with self.subTest(data=data), self.assertRaises((ValueError, csv.Error)):
                rtk.read_rtk(data)


class AtomicWriteTests(unittest.TestCase):
    def test_failed_replace_cleans_temporary_file(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "result.zip"
            output.write_bytes(b"previous output")
            with (
                patch("rtk.os.replace", side_effect=OSError("replace failed")),
                self.assertRaises(OSError),
            ):
                rtk.write_atomic(output, b"new output")
            self.assertEqual(output.read_bytes(), b"previous output")
            self.assertEqual(list(Path(directory).iterdir()), [output])


if __name__ == "__main__":
    unittest.main()
