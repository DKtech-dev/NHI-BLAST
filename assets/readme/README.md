# Repository artwork

Source and rendered copies of the repository artwork, the README product screenshots and the
GitHub social preview. The product screenshots show the current offline-report identity — Host
Grotesk and Instrument Sans type with an electric-blue accent — in the light theme, and contain
only the synthetic `fx07-incident` fixture.

| File | Size | Source | Used for |
| --- | --- | --- | --- |
| `banner-dark.png` | 1600×600 | `banner.html` | README header in dark mode |
| `banner-light.png` | 1600×600 | `banner.html` | README header in light mode |
| `report-light.png` | 1440×900 | Live report, top viewport | README product screenshot (light theme) |
| `completeness-light.png` | 1440×900 | Live report, completeness section | README completeness detail (light theme) |
| `social-dark.png` | 1280×640 | `social.html` plus a live report crop | GitHub social preview (uploaded manually) |

The README banner uses `<picture>` to select the dark or light artwork. The product screenshots
use the light theme and contain only the synthetic `fx07-incident` fixture. The social preview uses
`social-dark.png`, rendered from `social.html` and a live report crop, not from either banner.

## Regenerate the product screenshots

Build the report from the fixture without a timestamp, then capture it offline in Chromium with
Playwright at 1440 px wide, `colorScheme: light`, `reducedMotion: reduce` and a settled boot gate
(`html:not(.booting)`). The top capture is the 1440×900 viewport from the top of the page; the
completeness capture scrolls `#completeness` to just below the sticky navigation and takes the same
viewport. The full light/dark responsive set lives in `docs/usability/screens/` and is regenerated
by `tests/ui/screenshots.js`. Keep the generated report and capture scripts in the gitignored
`nhi-blast-out/` tree; do not commit report exports.

```sh
.venv/bin/nhi-blast scan tests/fixtures/fx07-incident \
  --simulate-compromise action:tj-actions/changed-files@v45 \
  --format html --out nhi-blast-out/readme-shots
```

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

The social crop is the summary and survival-panel region of the live report in the dark theme,
captured at 2× and passed with `--crop`. If the report layout changes, recapture the crop and check
that the card still reads at 1280×640.

## GitHub social preview

Upload `social-dark.png` in the GitHub repository under **Settings → Social preview → Edit →
Upload an image**. GitHub recommends 1280×640 and a file below 1 MB; this file is 1280×640 and about
123 KB. The repository cannot set this field itself, and the setting is not changed by committing
the image.

See GitHub's guidance:
[Customizing your repository's social media preview](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/customizing-your-repositorys-social-media-preview).

## Licence

The artwork is original to this repository. The embedded fonts (Host Grotesk, Instrument Sans and
Geist Mono) are distributed under the SIL Open Font License; see [NOTICE](../../NOTICE). No stock
photography or third-party imagery is used.
