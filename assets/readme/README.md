# Repository artwork

Source and rendered copies of the repository artwork, the README product screenshot and the GitHub
social preview. All of them use the Vermilion Noir identity of the offline report: near-black
surfaces, warm ivory type and a vermilion accent. The product screenshots contain only the synthetic
`fx07-incident` fixture.

| File | Size | Source | Used for |
| --- | --- | --- | --- |
| `banner-dark.png` | 1600×600 | `banner.html` | Rendered brand artwork (dark); not referenced by the current README |
| `banner-light.png` | 1600×600 | `banner.html` | Rendered brand artwork (light); not referenced by the current README |
| `report-dark.png` | 1600×1500 | Live report, top viewport | README product screenshot |
| `social-dark.png` | 1280×640 | `social.html` plus a live report crop | GitHub social preview (uploaded manually) |

The banner assets are retained as repository brand artwork and remain regenerable from
`banner.html`; no current README or documentation page embeds them. The social preview uses
`social-dark.png`, rendered from `social.html` and a live report crop, not from either banner.

## Regenerate the product screenshots

Build the report from the fixture without a timestamp, then open it offline in Chrome or Edge:

```sh
.venv/bin/nhi-blast scan tests/fixtures/fx07-incident \
  --simulate-compromise action:tj-actions/changed-files@v45 \
  --format html --out nhi-blast-out/readme-shots
```

Capture with Playwright at 1600 px wide, `deviceScaleFactor: 1`, `prefers-reduced-motion: reduce`
and a settled `document.fonts.ready`. The reduced-motion setting shows the resting state: all panels
revealed and no entrance animation. The capture is 1600×1500 from the top of the page. Keep the
generated report and capture scripts in the gitignored `nhi-blast-out/` tree; do not commit report
exports.

## Regenerate the cards

`render.mjs` needs Node.js, a local Chrome or Edge, and the fonts in
`src/nhi_blast/report/assets/fonts/`. It replaces the font placeholders and, for `social.html`, the
`__REPORT_CROP__` placeholder with a base64-cropped view of the live report.

```sh
cd assets/readme
node render.mjs --html banner.html --out banner-dark.png \
  --width 1600 --height 600 --scheme dark
node render.mjs --html banner.html --out banner-light.png \
  --width 1600 --height 600 --scheme light
node render.mjs --html social.html --out social-dark.png \
  --width 1280 --height 640 --scheme dark --crop <report-crop.png>
```

The social crop is the summary and survival-panel region of `report-dark.png`, captured at 2× and
passed with `--crop`. If the report layout changes, recapture the crop and check that the card still
reads at 1280×640.

## GitHub social preview

Upload `social-dark.png` in the GitHub repository under **Settings → Social preview → Edit →
Upload an image**. GitHub recommends 1280×640 and a file below 1 MB; this file is 1280×640 and about
123 KB. The repository cannot set this field itself, and the setting is not changed by committing
the image.

See GitHub's guidance:
[Customizing your repository's social media preview](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/customizing-your-repositorys-social-media-preview).

## Licence

The artwork is original to this repository. The embedded fonts (Instrument Serif, Geist and Geist
Mono) are distributed under the SIL Open Font License; see [NOTICE](../../NOTICE). No stock
photography or third-party imagery is used.
