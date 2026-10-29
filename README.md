# RTK

A standalone kanji dictionary with RTK keywords, numbers, and mnemonic stories
from `rtk.csv`, for Yomitan and Manatan. No custom CSS or KANJIDIC download is needed.

## Use

1. Download `RTK.zip` from this repository's Releases page, or build it below.
2. Import it alongside regular KANJIDIC.
3. Move **RTK above KANJIDIC** in the dictionary order.

The dictionary is named `RTK`. Each entry contains a keyword and number followed
by its story. For example, 明 contains:

```text
bright (#20)
The sun makes the moon bright.
```

RTK and KANJIDIC appear as separate results using each app's normal formatting.
If switching from `KANJIDIC + RTK`, disable or remove that combined dictionary
and enable regular KANJIDIC to avoid duplicate RTK results. Remove any RTK-specific
snippet previously pasted into Yomitan's Popup CSS.

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

## Legacy combined dictionary

The original KANJIDIC + RTK builder remains available for Yomitan:

```sh
python3 build_combined.py
```

It downloads the latest [KANJIDIC English dictionary](https://github.com/yomidevs/jmdict-yomitan)
and writes `dist/KANJIDIC_RTK_english.zip`. Use `--source-zip` to build from a local
KANJIDIC archive offline. This combined dictionary is no longer included in new
releases.

<details>
<summary>Combined dictionary screenshot and styling</summary>

![RTK section in Yomitan showing 大, its keyword, number, and story](docs/rtk-preview.png)

The combined ZIP bundles [yomitan-rtk.css](yomitan-rtk.css) as `styles.css` to show
RTK above the original meanings, readings, and statistics in Yomitan. It preserves
upstream entries and attribution and disables upstream automatic updates.

Manatan's kanji renderer shows the metadata tags and text fallback instead;
use the standalone `RTK.zip` there. The screenshot above shows the combined
Yomitan version, not the standalone dictionary.

</details>

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

The legacy combined dictionary also uses KANJIDIC material from
[yomidevs/jmdict-yomitan](https://github.com/yomidevs/jmdict-yomitan) and retains its
attribution. Consult [KANJIDIC](https://www.edrdg.org/wiki/index.php/KANJIDIC_Project)
for the dictionary data's license terms.
