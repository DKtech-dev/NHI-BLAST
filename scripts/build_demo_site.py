"""Build a deterministic static demo bundle of 3 synthetic incident reports."""

from __future__ import annotations

import argparse
from html import escape
from pathlib import Path

from nhi_blast import __version__
from nhi_blast.pipeline import ScanOptions, run_scan
from nhi_blast.report.html import write_html
from nhi_blast.report.json_report import write_json
from nhi_blast.report.whatif_html import render_whatif_html
from nhi_blast.whatif.engine import run_whatif
from nhi_blast.whatif.plan import synthesize_auto_plan

_DEMOS: tuple[tuple[str, str, str, Path, str], ...] = (
    (
        "incident-oidc-wildcard",
        "OIDC Wildcard Trust & Persistent Secret Survival",
        (
            "Demonstrates an organisation-wide OIDC subject wildcard reaching production "
            "AWS secrets that survive workflow revocation."
        ),
        Path("tests/fixtures/fx07-incident"),
        "acme/shop",
    ),
    (
        "untrusted-pr-checkout",
        "Privileged pull_request_target Checkout",
        (
            "Models fork pull-request code execution inside a privileged trigger with "
            "repository secret access."
        ),
        Path("tests/fixtures/fx12-untrusted-checkout"),
        "acme/shop",
    ),
    (
        "rotation-cycle",
        "Self-Defeating Credential Rotation Cycle",
        (
            "Highlights a reachable IAM role with secretsmanager:PutSecretValue that can "
            "defeat naive rotation order."
        ),
        Path("tests/fixtures/fx11-rotation-cycle"),
        "acme/shop",
    ),
)

_INDEX_CSS = """
:root {
  color-scheme: light;
  --bg: #fcfcfd;
  --surface: #ffffff;
  --surface-2: #f4f6f9;
  --ink: #0f172a;
  --muted: #475569;
  --border: #e2e8f0;
  --border-strong: #cbd5e1;
  --accent: #074ce0;
  --shadow-card: 0 1px 2px rgba(15, 23, 42, 0.04), 0 10px 24px -16px rgba(15, 23, 42, 0.16);
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0e1116;
    --surface: #151a22;
    --surface-2: #1c222d;
    --ink: #f8fafc;
    --muted: #94a3b8;
    --border: #2a3342;
    --border-strong: #3c475c;
    --accent: #6f9bff;
    --shadow-card: 0 1px 2px rgba(0, 0, 0, 0.35), 0 12px 24px -16px rgba(0, 0, 0, 0.7);
  }
}
* { box-sizing: border-box; }
html, body {
  overflow-x: clip;
  margin: 0;
  font-family: system-ui, -apple-system, sans-serif;
  font-variant-numeric: tabular-nums;
  background: var(--bg);
  color: var(--ink);
  line-height: 1.58;
  -webkit-font-smoothing: antialiased;
}
main { max-width: 960px; margin: 0 auto; padding: 56px 24px 80px; }
h1 { font-size: clamp(1.9rem, 3.6vw, 2.6rem); letter-spacing: -0.03em; margin: 0 0 12px; }
.lead { color: var(--muted); max-width: 66ch; margin: 0 0 36px; font-size: 1.04rem; }
.grid { display: grid; gap: 20px; }
article {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  box-shadow: var(--shadow-card);
  padding: 24px 26px;
}
article h2 { margin: 0 0 8px; font-size: 1.22rem; letter-spacing: -0.015em; }
article p { margin: 0 0 14px; color: var(--muted); font-size: 0.96rem; }
.meta {
  display: inline-block;
  padding: 4px 10px;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: var(--surface-2);
  font-family: ui-monospace, monospace;
  font-variant-numeric: tabular-nums;
  font-size: 0.82rem;
  color: var(--ink);
  margin-bottom: 16px;
}
.links { display: flex; flex-wrap: wrap; gap: 18px; font-weight: 600; font-size: 0.94rem; }
a { color: var(--accent); text-decoration: underline; text-underline-offset: 3px; }
a:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
footer {
  margin-top: 48px;
  padding-top: 20px;
  border-top: 1px solid var(--border);
  font-size: 0.86rem;
  color: var(--muted);
}
@media print {
  html, body { background: #ffffff; color: #000000; }
  article { break-inside: avoid; box-shadow: none; border-color: #cbd5e1; }
}
"""


def build_demo_site(out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    cards: list[str] = []
    for slug, title, summary, fixture_dir, repo_slug in _DEMOS:
        target = out_dir / slug
        target.mkdir(parents=True, exist_ok=True)
        outcome = run_scan(
            ScanOptions(root=fixture_dir, repo_slug=repo_slug, selectors=("repo-write",))
        )
        rep_json = target / "report.json"
        rep_html = target / "report.html"
        write_json(outcome.report, rep_json)
        write_html(outcome.report, rep_html)
        auto = synthesize_auto_plan(outcome.report)
        wf_payload = run_whatif(outcome.report, auto)
        wf_html = target / "whatif.html"
        wf_html.write_text(render_whatif_html(outcome.report, wf_payload), encoding="utf-8")
        written.extend((rep_json, rep_html, wf_html))
        scen = outcome.report.scenarios[0] if outcome.report.scenarios else None
        rez = (
            f"R={len(scen.partition.R)} / E={len(scen.partition.E)} / Z={len(scen.partition.Z)}"
            if scen
            else "n/a"
        )
        findings_count = len(outcome.report.findings)
        cards.append(
            "<article>"
            f"<h2>{escape(title)}</h2>"
            f"<p>{escape(summary)}</p>"
            f'<div class="meta">Findings: {findings_count} &mdash; Survival ({escape(rez)})</div>'
            '<div class="links">'
            f'<a href="{escape(slug)}/report.html">Open interactive blast-radius report</a>'
            f'<a href="{escape(slug)}/whatif.html">Open containment what-if report</a>'
            "</div>"
            "</article>"
        )
    index_path = out_dir / "index.html"
    index_html = (
        "<!DOCTYPE html>\n"
        '<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        "<title>NHI-Blast Interactive Incident Demos</title>"
        f"<style>{_INDEX_CSS}</style></head>"
        "<body><main>"
        "<h1>NHI-Blast Interactive Incident Demos</h1>"
        "<p class='lead'>Self-contained, zero-network reports generated deterministically from "
        "synthetic GitHub Actions and Terraform fixtures. Open any scenario below to inspect "
        "the authority graph, R/E/Z survival partition, and containment playbook.</p>"
        f'<div class="grid">{"".join(cards)}</div>'
        f"<footer>Generated offline by NHI-Blast {escape(__version__)} &mdash; "
        '<a href="https://github.com/DKtech-dev/nhi-blast">DKtech-dev/nhi-blast</a></footer>'
        "</main></body></html>\n"
    )
    index_path.write_text(index_html, encoding="utf-8")
    written.append(index_path)
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("nhi-blast-out/demo-site"),
        help="Destination directory for generated demo reports.",
    )
    args = parser.parse_args()
    written = build_demo_site(args.out)
    print(f"Built demo site ({len(written)} files) under {args.out.as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
