"""Single-file offline HTML report with a restrictive CSP (spec 13.4)."""

from __future__ import annotations

import base64
import hashlib
import json
from functools import cache
from importlib import resources
from pathlib import Path
from typing import Any

from nhi_blast.core.models import Report
from nhi_blast.report.model_json import report_dict
from nhi_blast.report.ui import APP_JS, TEMPLATE

_ASSET_NAMES = ("cytoscape.min.js", "dagre.min.js", "cytoscape-dagre.js")
_FONT_ASSETS = ("geist-latin.woff2", "geist-mono-latin.woff2")
_FONT_FAMILIES = {"geist-latin.woff2": "Geist", "geist-mono-latin.woff2": "Geist Mono"}
_UNICODE_RANGE = (
    "U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, U+02DC, "
    "U+0304, U+0308, U+0329, U+2000-206F, U+20AC, U+2122, U+2191, U+2193, "
    "U+2212, U+2215, U+FEFF, U+FFFD"
)
_DATA_OPEN = '<script type="application/json" id="report-data">'


@cache
def _manifest() -> dict[str, Any]:
    manifest: dict[str, Any] = json.loads(
        resources.files("nhi_blast.report.assets")
        .joinpath("MANIFEST.json")
        .read_text(encoding="utf-8")
    )
    if manifest.get("format") != "nhi-blast-assets/1":
        msg = "unsupported report asset manifest format"
        raise RuntimeError(msg)
    return manifest


@cache
def _asset_texts() -> dict[str, str]:
    base = resources.files("nhi_blast.report.assets")
    entries = {str(entry["name"]): entry for entry in _manifest().get("assets", ())}
    if set(entries) != set(_ASSET_NAMES):
        msg = "report asset manifest does not pin the expected assets"
        raise RuntimeError(msg)
    texts: dict[str, str] = {}
    for name in _ASSET_NAMES:
        payload = base.joinpath("vendor", name).read_bytes()
        if hashlib.sha256(payload).hexdigest() != entries[name].get("sha256"):
            msg = f"report asset hash mismatch: {name}"
            raise RuntimeError(msg)
        texts[name] = payload.decode("utf-8")
    return texts


@cache
def _font_css() -> str:
    base = resources.files("nhi_blast.report.assets")
    entries = {str(entry["name"]): entry for entry in _manifest().get("fonts", ())}
    if set(entries) != set(_FONT_ASSETS):
        msg = "report asset manifest does not pin the expected fonts"
        raise RuntimeError(msg)
    for name in _FONT_ASSETS:
        entry = entries[name]
        if entry.get("license") != "OFL-1.1" or entry.get("license_file") != "OFL.txt":
            msg = f"report font is not pinned to its OFL licence: {name}"
            raise RuntimeError(msg)
        if entry.get("family") != _FONT_FAMILIES[name]:
            msg = f"report font family mismatch: {name}"
            raise RuntimeError(msg)
    licence = base.joinpath("fonts", "OFL.txt").read_text(encoding="utf-8")
    if "SIL OPEN FONT LICENSE" not in licence:
        msg = "report font licence file is not the SIL Open Font License"
        raise RuntimeError(msg)
    faces: list[str] = []
    for name in _FONT_ASSETS:
        payload = base.joinpath("fonts", name).read_bytes()
        if hashlib.sha256(payload).hexdigest() != entries[name].get("sha256"):
            msg = f"report font hash mismatch: {name}"
            raise RuntimeError(msg)
        data = base64.b64encode(payload).decode("ascii")
        faces.append(
            "@font-face {\n"
            f'  font-family: "{_FONT_FAMILIES[name]}";\n'
            "  font-style: normal;\n"
            "  font-weight: 400 700;\n"
            "  font-display: optional;\n"
            f'  src: url("data:font/woff2;base64,{data}") format("woff2");\n'
            f"  unicode-range: {_UNICODE_RANGE};\n"
            "}"
        )
    return "\n".join(faces)


def _script_hash(body: str) -> str:
    digest = hashlib.sha256(body.encode("utf-8")).digest()
    return base64.b64encode(digest).decode("ascii")


def _embedded_json(report: Report) -> str:
    text = json.dumps(
        report_dict(report),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return (
        text.replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def _inline_scripts(data: str, assets: dict[str, str]) -> str:
    for name in _ASSET_NAMES:
        if "</script" in assets[name]:
            msg = f"vendored script contains a closing script tag: {name}"
            raise RuntimeError(msg)
    blocks = [
        f"{_DATA_OPEN}{data}</script>",
        *(f"<script>{assets[name]}</script>" for name in _ASSET_NAMES),
        f"<script>{APP_JS}</script>",
    ]
    return "\n".join(blocks)


def html_report(report: Report) -> str:
    """Render one deterministic, self-contained HTML document."""
    data = _embedded_json(report)
    assets = _asset_texts()
    scripts = _inline_scripts(data, assets)
    bodies = [data, *(assets[name] for name in _ASSET_NAMES), APP_JS]
    hashes = " ".join(f"'sha256-{_script_hash(body)}'" for body in bodies)
    csp = (
        "default-src 'none'; style-src 'unsafe-inline'; font-src data:; "
        f"script-src {hashes}; base-uri 'none'; form-action 'none'"
    )
    document = TEMPLATE.replace("__CSP__", csp)
    document = document.replace("__FONT_CSS__", _font_css())
    document = document.replace("__SCRIPTS__", scripts)
    return document.rstrip() + "\n"


def write_html(report: Report, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html_report(report), encoding="utf-8", newline="\n")


__all__ = ["html_report", "write_html"]
