import contextlib
import csv
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import build_combined as build


def fixture_archive(entries=None, index_overrides=None):
    index = {
        "title": "KANJIDIC",
        "format": 3,
        "revision": "source-1",
        "attribution": "Original attribution",
        "isUpdatable": True,
        "indexUrl": "https://example.com/index.json",
        "downloadUrl": "https://example.com/source.zip",
    }
    index.update(index_overrides or {})
    if entries is None:
        entries = [
            ["一", "イチ", "ひと.つ", "jouyou", ["one"], {"heisig": "1"}],
            ["二", "ニ", "ふた.つ", "", ["two"], {}],
        ]
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.comment = b"source comment"
        archive.writestr("index.json", json.dumps(index))
        archive.writestr("kanji_bank_1.json", json.dumps(entries))
        archive.writestr("kanji_bank_2.json", "[]")
        archive.writestr("tag_bank_1.json", b'[["jouyou", "", 0, "Common", 0]]')
        archive.writestr("assets/source.txt", b"unchanged")
    return stream.getvalue()


class CsvTests(unittest.TestCase):
    def test_quoted_unicode_multiline_and_bom(self):
        records = build.read_rtk('\ufeff1,一,"one, only","line 1\n日本語"\r\n'.encode())
        self.assertEqual(records["一"], [("1", "one, only", "line 1\n日本語")])

    def test_duplicates_merge_without_blank_overwrite(self):
        records = build.read_rtk(
            "1,一,one,\n,一,,story\n,一,,\n1,一,one,story\n".encode()
        )
        self.assertEqual(records["一"], [("1", "one", "story")])

    def test_conflicting_records_preserved(self):
        records = build.read_rtk("1,一,one,story\n2,一,single,story\n".encode())
        self.assertEqual(
            build.rtk_meanings(records["一"]),
            [
                "RTK #1: one",
                "RTK story: story",
                "RTK #2: single",
            ],
        )

    def test_optional_fields(self):
        records = build.read_rtk("1,一,,\n,二,two,\n,三,,story\n,四,,\n".encode())
        self.assertEqual(build.rtk_meanings(records["一"]), ["RTK #1"])
        self.assertEqual(build.rtk_meanings(records["二"]), ["RTK: two"])
        self.assertEqual(build.rtk_meanings(records["三"]), ["RTK story: story"])
        self.assertEqual(build.rtk_meanings(records["四"]), [])

    def test_malformed_csv(self):
        for data in (
            b"",
            b"1,x,keyword\n",
            b"1,,keyword,story\n",
            b"abc,x,keyword,story\n",
            b'1,x,keyword,"unterminated',
        ):
            with self.subTest(data=data), self.assertRaises((ValueError, csv.Error)):
                build.read_rtk(data)


class ArchiveTests(unittest.TestCase):
    def test_merge_preserves_source_and_updates_index(self):
        source = fixture_archive()
        result, stats = build.enrich_archive(source, "1,一,one,story\n,三,,\n".encode())
        self.assertEqual(
            stats, {"csv_kanji": 2, "entries": 2, "enriched": 1, "unmatched": ["三"]}
        )
        with (
            zipfile.ZipFile(io.BytesIO(source)) as original,
            zipfile.ZipFile(io.BytesIO(result)) as output,
        ):
            self.assertIsNone(output.testzip())
            self.assertEqual(
                output.namelist(),
                original.namelist() + ["tag_bank_2.json", "styles.css"],
            )
            self.assertEqual(
                output.read("styles.css").strip(),
                (build.ROOT / "yomitan-rtk.css").read_bytes().strip(),
            )
            self.assertEqual(output.comment, original.comment)
            for name in ("tag_bank_1.json", "assets/source.txt", "kanji_bank_2.json"):
                self.assertEqual(output.read(name), original.read(name))
            before = json.loads(original.read("kanji_bank_1.json"))
            after = json.loads(output.read("kanji_bank_1.json"))
            self.assertEqual(after[0][4], ["RTK #1: one\nRTK story: story", "one"])
            self.assertEqual(after[0][:3], before[0][:3])
            self.assertEqual(after[0][3].split()[0], "jouyou")
            tags = json.loads(output.read("tag_bank_2.json"))
            self.assertEqual(after[0][3].split()[1:], [tag[0] for tag in tags])
            self.assertEqual(
                [tag[1:4] for tag in tags],
                [
                    ["rtk-keyword", 1000, "one"],
                    ["rtk-number", 1001, "#1"],
                    ["rtk-story", 1002, "story"],
                ],
            )
            self.assertEqual(after[0][5], before[0][5])
            self.assertEqual(after[1], before[1])
            index = json.loads(output.read("index.json"))
            self.assertEqual(index["title"], "KANJIDIC + RTK")
            self.assertEqual(index["attribution"], "Original attribution")
            self.assertNotIn("isUpdatable", index)
            self.assertNotIn("indexUrl", index)
            self.assertNotIn("downloadUrl", index)
            self.assertTrue(index["revision"].startswith("source-1-rtk3-"))

    def test_bundled_styles_preserve_upstream_css(self):
        stream = io.BytesIO(fixture_archive())
        with zipfile.ZipFile(stream, "a") as source:
            source.writestr("styles.css", "a { color: red; }")
        result, _ = build.enrich_archive(stream.getvalue(), "1,一,one,story\n".encode())
        with zipfile.ZipFile(io.BytesIO(result)) as output:
            self.assertEqual(output.namelist().count("styles.css"), 1)
            self.assertTrue(
                output.read("styles.css").startswith(b"a { color: red; }\n")
            )
            self.assertIn(b'&[data-type="kanji"]', output.read("styles.css"))

    def test_revision_tracks_stylesheet_changes(self):
        data = "1,一,one,story\n".encode()
        source = fixture_archive()
        first, _ = build.enrich_archive(source, data)
        with patch.object(
            Path, "read_bytes", return_value=b'&[data-type="kanji"] { color: red; }'
        ):
            changed, _ = build.enrich_archive(source, data)
        with (
            zipfile.ZipFile(io.BytesIO(first)) as a,
            zipfile.ZipFile(io.BytesIO(changed)) as b,
        ):
            self.assertNotEqual(
                json.loads(a.read("index.json"))["revision"],
                json.loads(b.read("index.json"))["revision"],
            )

    def test_no_metadata_means_no_layout_tags_or_extra_bank(self):
        source = fixture_archive()
        result, stats = build.enrich_archive(source, ",一,,\n".encode())
        self.assertEqual(stats["enriched"], 0)
        with (
            zipfile.ZipFile(io.BytesIO(source)) as original,
            zipfile.ZipFile(io.BytesIO(result)) as output,
        ):
            self.assertEqual(original.namelist(), output.namelist())
            self.assertEqual(
                json.loads(original.read("kanji_bank_1.json")),
                json.loads(output.read("kanji_bank_1.json")),
            )

    def test_conflicting_records_have_separate_ordered_tags(self):
        tags = build.rtk_tags(
            "一", [("1", "one", "first story"), ("2", "single", "second story")]
        )
        self.assertEqual(len({tag[0] for tag in tags}), 6)
        self.assertEqual([tag[2] for tag in tags], list(range(1000, 1006)))
        self.assertEqual(
            [tag[3] for tag in tags],
            ["one", "#1", "first story", "single", "#2", "second story"],
        )

    def test_missing_fields_do_not_create_empty_tags(self):
        tags = build.rtk_tags(
            "一", [("", "", "story only"), ("1", "", ""), ("", "keyword only", "")]
        )
        self.assertEqual(
            [tag[1] for tag in tags], ["rtk-story", "rtk-number", "rtk-keyword"]
        )
        self.assertTrue(all(tag[3] for tag in tags))

    def test_revision_tracks_csv_changes_and_build_is_repeatable(self):
        source = fixture_archive()
        data = "1,一,one,story\n".encode()
        first, _ = build.enrich_archive(source, data)
        self.assertEqual(first, build.enrich_archive(source, data)[0])
        changed, _ = build.enrich_archive(source, data.replace(b"story", b"new story"))
        with (
            zipfile.ZipFile(io.BytesIO(first)) as a,
            zipfile.ZipFile(io.BytesIO(changed)) as b,
        ):
            self.assertNotEqual(
                json.loads(a.read("index.json"))["revision"],
                json.loads(b.read("index.json"))["revision"],
            )

    def test_invalid_archive_or_schema(self):
        sources = [
            b"not a zip",
            fixture_archive(index_overrides={"format": 2}),
            fixture_archive(entries=[]),
            fixture_archive(entries=[["一"]]),
            fixture_archive(entries=[["一", "", "", "", [{}], {}]]),
        ]
        empty = io.BytesIO()
        with zipfile.ZipFile(empty, "w"):
            pass
        sources.append(empty.getvalue())
        for source in sources:
            with (
                self.subTest(source=source[:20]),
                self.assertRaises((ValueError, zipfile.BadZipFile)),
            ):
                build.enrich_archive(source, "1,一,one,story\n".encode())


class CliTests(unittest.TestCase):
    def test_invalid_inputs_preserve_existing_output(self):
        for csv_data, source in (
            (b"invalid csv", fixture_archive()),
            ("1,一,one,story\n".encode(), b"invalid zip"),
        ):
            with (
                self.subTest(csv_data=csv_data),
                tempfile.TemporaryDirectory() as directory,
            ):
                root = Path(directory)
                csv_path = root / "rtk.csv"
                csv_path.write_bytes(csv_data)
                source_path = root / "source.zip"
                source_path.write_bytes(source)
                output = root / "result.zip"
                output.write_bytes(b"previous output")
                with contextlib.redirect_stderr(io.StringIO()) as errors:
                    code = build.main(
                        [
                            "--csv",
                            str(csv_path),
                            "--source-zip",
                            str(source_path),
                            "--output",
                            str(output),
                        ]
                    )
                self.assertEqual(code, 1)
                self.assertIn("Error:", errors.getvalue())
                self.assertEqual(output.read_bytes(), b"previous output")

    def test_offline_build(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "rtk.csv").write_text("1,一,one,story\n", encoding="utf-8")
            (root / "source.zip").write_bytes(fixture_archive())
            output = root / "dist/result.zip"
            with (
                patch("build_combined.urlopen") as download,
                contextlib.redirect_stdout(io.StringIO()) as messages,
            ):
                code = build.main(
                    [
                        "--csv",
                        str(root / "rtk.csv"),
                        "--source-zip",
                        str(root / "source.zip"),
                        "--output",
                        str(output),
                    ]
                )
            self.assertEqual(code, 0)
            download.assert_not_called()
            self.assertIn("1 entries enriched", messages.getvalue())
            with zipfile.ZipFile(output) as archive:
                self.assertIsNone(archive.testzip())

    def test_failed_download_preserves_existing_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            csv_path = root / "rtk.csv"
            csv_path.write_text("1,一,one,story\n", encoding="utf-8")
            output = root / "result.zip"
            output.write_bytes(b"previous output")
            with (
                patch("build_combined.urlopen", side_effect=OSError("network failed")),
                contextlib.redirect_stdout(io.StringIO()),
                contextlib.redirect_stderr(io.StringIO()) as errors,
            ):
                code = build.main(["--csv", str(csv_path), "--output", str(output)])
            self.assertEqual(code, 1)
            self.assertIn("network failed", errors.getvalue())
            self.assertEqual(output.read_bytes(), b"previous output")

    def test_failed_replace_cleans_temporary_file(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "result.zip"
            output.write_bytes(b"previous output")
            with (
                patch("rtk.os.replace", side_effect=OSError("replace failed")),
                self.assertRaises(OSError),
            ):
                build.write_atomic(output, b"new output")
            self.assertEqual(output.read_bytes(), b"previous output")
            self.assertEqual(list(Path(directory).iterdir()), [output])


if __name__ == "__main__":
    unittest.main()
