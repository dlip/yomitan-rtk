# Yomitan RTK

A standalone kanji dictionary with RTK keywords, numbers, and mnemonic stories
from `rtk.csv`, for Yomitan. No custom CSS or downloads are needed to build.

## Use

1. Download `RTK.zip` from this repository's Releases page, or build it below.
2. Import it into Yomitan.
3. Move **RTK above your other kanji dictionaries** if you want its results first.

The dictionary is named `RTK`. Each entry contains a keyword and number followed
by its story. For example, 明 contains:

```text
bright (#20)
The sun makes the moon bright.
```

Entries use Yomitan's normal formatting. No extra RTK tags or custom CSS are needed.

## Build

Requires Python 3.10 or newer. No dependencies to install.

```sh
python3 build.py
```

This writes `dist/RTK.zip` using only the CSV. Kanji without any RTK number,
keyword, or story are omitted. The supplied CSV produces 3,038 entries.

Custom paths are supported:

```sh
python3 build.py --csv rtk.csv --output dist/custom-rtk.zip
```

Default paths are relative to this project; explicit paths are relative to your
working directory. Malformed inputs fail without replacing an existing output ZIP.

## Releases

Push a new tag to run the release workflow:

```sh
git tag v1.2.0
git push origin v1.2.0
```

The workflow runs the tests, builds from the tagged CSV, and publishes `RTK.zip`
with automatically generated release notes. All tag names are supported. It uses
the built-in `GITHUB_TOKEN`; no additional secrets are required. The tagged
commit must contain the workflow.

## CSV format

The input is UTF-8 CSV without a header: `number,kanji,keyword,story`. Quoted
commas and multiline stories are supported. Numbers are optional; when present,
they must be decimal digits. Each kanji field must contain one character.

Blank fields produce no empty labels. Duplicate rows combine complementary
fields; conflicting records are preserved as separate definitions for the same
kanji. Original mnemonic text and internal line breaks are preserved.

## Tests

```sh
python3 -m unittest discover -s tests -v
```

Tests use small local fixtures and require no network access.

## Sources and attribution

The standalone dictionary uses only `rtk.csv`. Its provenance and redistribution
terms, including those of the mnemonic stories, are unspecified. This project
does not assign new license terms to that data. The code license is in
[LICENSE](LICENSE).
