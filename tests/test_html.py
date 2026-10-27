"""Self-contained offline HTML report and its CSP (M5, spec 13.4)."""

from __future__ import annotations

import base64
import hashlib
import html as html_module
import json
import re
from collections.abc import Iterator
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import pytest

from nhi_blast.report import html as report_html_module
from nhi_blast.report.html import html_report, write_html
from tests.report_support import HOSTILE, make_report

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "src" / "nhi_blast" / "report" / "assets"
VENDOR = ASSETS / "vendor"
FONTS = ASSETS / "fonts"
MANIFEST = ASSETS / "MANIFEST.json"


class _TagCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tags: list[tuple[str, dict[str, str | None]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append((tag, dict(attrs)))


def _scripts(document: str) -> list[tuple[str, str]]:
    return re.findall(r"<script([^>]*)>(.*?)</script\s*>", document, re.DOTALL | re.IGNORECASE)


def test_script_extractor_matches_any_letter_case_and_end_tag_spacing() -> None:
    assert _scripts('<SCRIPT src="x"></SCRIPT ><script>y</script>') == [
        (' src="x"', ""),
        ("", "y"),
    ]


def test_html_has_required_sections_and_stays_under_size_target() -> None:
    document = html_report(make_report())

    for heading in (
        "Scope and Limits",
        "Summary",
        "Scenario",
        "Graph",
        "Survival panel",
        "Cross-scenario exposure",
        "Rotation plan",
        "Findings",
        "Assumptions and Unknowns",
        "Diagnostics",
    ):
        assert heading in document
    assert document.endswith("\n")
    assert len(document.encode("utf-8")) < 3 * 1024 * 1024


def test_csp_hashes_every_inline_script_and_forbids_inline_execution() -> None:
    document = html_report(make_report())
    match = re.search(
        r'<meta http-equiv="Content-Security-Policy" content="([^"]+)">',
        document,
    )
    assert match is not None
    policy = html_module.unescape(match.group(1))
    scripts = _scripts(document)

    assert len(scripts) == 5
    for attrs, body in scripts:
        assert "src=" not in attrs
        digest = base64.b64encode(hashlib.sha256(body.encode("utf-8")).digest()).decode("ascii")
        assert f"'sha256-{digest}'" in policy
    script_src = next(part for part in policy.split(";") if part.strip().startswith("script-src"))
    assert "'unsafe-inline'" not in script_src
    assert "'unsafe-eval'" not in script_src
    assert "default-src 'none'" in policy


def test_html_has_no_external_resources_or_unsafe_dom_sinks() -> None:
    document = html_report(make_report())
    collector = _TagCollector()
    collector.feed(document)

    assert not {"img", "iframe", "object", "embed", "link"} & {tag for tag, _ in collector.tags}
    for tag, attrs in collector.tags:
        if tag == "script":
            assert "src" not in attrs
        assert not any(name.lower().startswith("on") for name in attrs)
        for name in ("src", "href"):
            value = attrs.get(name)
            if value:
                assert not value.lower().startswith(("http:", "https:", "//", "javascript:"))
    assert ".innerHTML" not in document
    assert "insertAdjacentHTML" not in document
    assert "document.write" not in document
    assert "eval(" not in document
    assert "new Function" not in document


def test_report_hides_until_hydrated_and_remains_usable_without_script() -> None:
    document = html_report(make_report())

    assert '<html lang="en" class="booting">' in document
    hidden = "html.booting body { visibility: hidden; }"
    visible = "<noscript><style>html.booting body { visibility: visible; }</style></noscript>"
    assert hidden in document
    assert visible in document
    # The no-script override must come after the hiding rule so it wins.
    assert document.index(hidden) < document.index(visible)
    app = _scripts(document)[-1][1]
    assert 'classList.remove("booting")' in app


def test_embedded_json_escapes_html_metacharacters_and_preserves_exact_strings() -> None:
    report = make_report(hostile=True)
    document = html_report(report)
    match = re.search(
        r'<script type="application/json" id="report-data">(.*?)</script>',
        document,
        re.DOTALL,
    )
    assert match is not None
    embedded = match.group(1)

    assert "<" not in embedded
    assert ">" not in embedded
    assert "&" not in embedded
    assert "\\u003c" in embedded
    assert "\\u003e" in embedded
    data = json.loads(embedded)
    labels = [node["label"] for node in data["graph"]["nodes"]]
    assert HOSTILE in labels


def test_hostile_content_is_data_not_markup() -> None:
    document = html_report(make_report(hostile=True))
    collector = _TagCollector()
    collector.feed(document)

    assert "<img" not in document.lower()
    assert "</script><img" not in document.lower()
    assert not any(name.lower().startswith("on") for _, attrs in collector.tags for name in attrs)


def test_report_has_accessible_structure_and_table_semantics() -> None:
    document = html_report(make_report())

    assert '<html lang="en" class="booting">' in document
    assert '<meta name="viewport"' in document
    assert "<title>NHI-Blast report</title>" in document
    assert 'class="skip-link"' in document
    assert 'aria-label="Report sections"' in document
    assert 'aria-live="polite"' in document
    assert 'id="graph-note"' in document
    assert "not keyboard operable" in document

    app_script = _scripts(document)[-1][1]
    assert 'append(table, "caption"' in app_script
    assert 'cell.scope = "col"' in app_script
    assert 'append(container, "div", "table-wrap")' in app_script
    assert "scroll.tabIndex = 0" in app_script
    assert ":focus-visible" in document
    assert "grid-template-columns: minmax(0, 1fr)" in document
    assert "min-width: 0" in document


def test_scenario_picker_renders_without_a_scenario() -> None:
    app_script = _scripts(html_report(make_report()))[-1][1]
    start = app_script.index("function renderScenarioPicker()")
    end = app_script.index("function renderScenario(", start)
    picker = app_script[start:end]

    assert "picker.disabled = true;\n      return;" not in picker
    assert 'picker.addEventListener("change"' in picker
    assert picker.index("selectScenario(0);") > picker.index("} else {")


def test_html_exposes_cross_scenario_matrix_path_trace_and_finding_filters() -> None:
    document = html_report(make_report())
    app_script = _scripts(document)[-1][1]

    for element_id in (
        "matrix",
        "matrix-summary",
        "matrix-shared",
        "trace-content",
        "finding-search",
        "finding-severity",
        "finding-scenario",
        "findings-count",
    ):
        assert f'id="{element_id}"' in document
    for function in (
        "function shortestPath(",
        "function traceTo(",
        "function renderTrace(",
        "function renderMatrix(",
        "function renderFindings(",
    ):
        assert function in app_script
    assert "scenarios.length < 2" in app_script
    assert "scenario.potential_nodes" in app_script
    assert "innerHTML" not in app_script
    assert "insertAdjacentHTML" not in app_script


def test_graph_focus_maps_expiring_credentials_to_their_node_ids() -> None:
    app_script = _scripts(html_report(make_report()))[-1][1]

    assert "scenario.partition.R.forEach((id) => focus.add(id));" in app_script
    assert "scenario.partition.E.forEach((entry) => focus.add(entry.credential));" in app_script
    assert "scenario.partition.Z.forEach((entry) => focus.add(entry.credential));" in app_script
    assert "scenario.partition.E.forEach((item) => focus.add(id));" not in app_script


def test_vendored_assets_match_the_pinned_manifest() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    assert manifest["format"] == "nhi-blast-assets/1"
    entries = {entry["name"]: entry for entry in manifest["assets"]}
    assert set(entries) == {
        "cytoscape.min.js",
        "dagre.min.js",
        "cytoscape-dagre.js",
    }
    for name, entry in entries.items():
        payload = (VENDOR / name).read_bytes()
        assert hashlib.sha256(payload).hexdigest() == entry["sha256"]
        assert entry["version"]
        assert entry["source_url"].startswith("https://")
        assert entry["license"] == "MIT"


def test_embedded_fonts_match_the_pinned_manifest_and_carry_their_licence() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    entries = {entry["name"]: entry for entry in manifest["fonts"]}

    assert set(entries) == {"geist-latin.woff2", "geist-mono-latin.woff2"}
    for name, entry in entries.items():
        payload = (FONTS / name).read_bytes()
        assert payload[:4] == b"wOF2"
        assert hashlib.sha256(payload).hexdigest() == entry["sha256"]
        assert entry["family"] in {"Geist", "Geist Mono"}
        assert entry["license"] == "OFL-1.1"
        assert entry["license_file"] == "OFL.txt"
        assert entry["source_url"].startswith("https://")
    licence = (FONTS / "OFL.txt").read_text(encoding="utf-8")
    assert "SIL OPEN FONT LICENSE" in licence
    assert "Version 1.1" in licence


def test_fonts_are_embedded_as_data_uris_and_csp_allows_only_data_fonts() -> None:
    document = html_report(make_report())
    style = document.split("<style>", 1)[1].split("</style>", 1)[0]

    assert len(re.findall(r"@font-face \{", style)) == 2
    assert style.count('url("data:font/woff2;base64,') == 2
    assert "font-display: optional" in style
    assert "http://" not in style
    assert "https://" not in style

    policy = re.search(
        r'<meta http-equiv="Content-Security-Policy" content="([^"]+)">',
        document,
    )
    assert policy is not None
    unescaped = html_module.unescape(policy.group(1))
    assert "default-src 'none'" in unescaped
    assert "font-src data:" in unescaped
    font_src = next(part for part in unescaped.split(";") if part.strip().startswith("font-src"))
    assert font_src.strip() == "font-src data:"


def test_embedded_font_payloads_are_byte_identical_to_the_licensed_files() -> None:
    document = html_report(make_report())
    payloads = re.findall(r'url\("data:font/woff2;base64,([A-Za-z0-9+/=]+)"\)', document)

    assert len(payloads) == 2
    embedded = sorted(hashlib.sha256(base64.b64decode(item)).hexdigest() for item in payloads)
    source = sorted(
        hashlib.sha256((FONTS / name).read_bytes()).hexdigest()
        for name in ("geist-latin.woff2", "geist-mono-latin.woff2")
    )
    assert embedded == source


def test_html_is_deterministic_and_app_script_uses_text_content() -> None:
    report = make_report()
    first = html_report(report)
    second = html_report(report)
    app_script = _scripts(first)[-1][1]

    assert first == second
    assert "textContent" in app_script
    assert "replaceChildren" in app_script
    assert "innerHTML" not in app_script


@pytest.fixture
def report_html() -> Iterator[Any]:
    report_html_module._manifest.cache_clear()
    report_html_module._asset_texts.cache_clear()
    report_html_module._font_css.cache_clear()
    yield report_html_module
    report_html_module._manifest.cache_clear()
    report_html_module._asset_texts.cache_clear()
    report_html_module._font_css.cache_clear()


def _manifest() -> dict[str, Any]:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_asset_manifest_rejects_an_unknown_format(
    report_html: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FakeFile:
        def read_text(self, *_args: Any, **_kwargs: Any) -> str:
            return '{"format": "nhi-blast-assets/2"}'

    class FakeRoot:
        def joinpath(self, *_args: Any, **_kwargs: Any) -> FakeFile:
            return FakeFile()

    def fake_files(*_args: Any, **_kwargs: Any) -> FakeRoot:
        return FakeRoot()

    monkeypatch.setattr(report_html.resources, "files", fake_files)
    report_html._manifest.cache_clear()

    with pytest.raises(RuntimeError, match="unsupported report asset manifest format"):
        report_html._manifest()


def test_asset_manifest_must_pin_every_vendor_script(
    report_html: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(report_html, "_manifest", lambda: {"assets": [], "fonts": []})

    with pytest.raises(RuntimeError, match="does not pin the expected assets"):
        report_html._asset_texts()


def test_asset_texts_reject_a_changed_vendor_file(
    report_html: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = _manifest()
    manifest["assets"][0]["sha256"] = "0" * 64
    monkeypatch.setattr(report_html, "_manifest", lambda: manifest)

    with pytest.raises(RuntimeError, match="report asset hash mismatch"):
        report_html._asset_texts()


def test_font_css_requires_every_dealt_font(
    report_html: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = _manifest()
    manifest["fonts"] = []
    monkeypatch.setattr(report_html, "_manifest", lambda: manifest)

    with pytest.raises(RuntimeError, match="does not pin the expected fonts"):
        report_html._font_css()


def test_font_css_requires_the_pinned_licence_and_family(
    report_html: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = _manifest()
    manifest["fonts"][0]["license"] = "MIT"
    monkeypatch.setattr(report_html, "_manifest", lambda: manifest)
    with pytest.raises(RuntimeError, match="not pinned to its OFL licence"):
        report_html._font_css()

    manifest = _manifest()
    manifest["fonts"][0]["family"] = "Another Sans"
    monkeypatch.setattr(report_html, "_manifest", lambda: manifest)
    with pytest.raises(RuntimeError, match="report font family mismatch"):
        report_html._font_css()


def test_font_css_rejects_a_changed_binary(
    report_html: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = _manifest()
    manifest["fonts"][0]["sha256"] = "0" * 64
    monkeypatch.setattr(report_html, "_manifest", lambda: manifest)

    with pytest.raises(RuntimeError, match="report font hash mismatch"):
        report_html._font_css()


def test_font_css_rejects_a_non_ofl_licence_file(
    report_html: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FakeFile:
        def read_text(self, *_args: Any, **_kwargs: Any) -> str:
            return "All rights reserved."

    class FakeRoot:
        def joinpath(self, *_args: Any, **_kwargs: Any) -> FakeFile:
            return FakeFile()

    monkeypatch.setattr(report_html, "_manifest", _manifest)

    def fake_files(*_args: Any, **_kwargs: Any) -> FakeRoot:
        return FakeRoot()

    monkeypatch.setattr(report_html.resources, "files", fake_files)

    with pytest.raises(RuntimeError, match="not the SIL Open Font License"):
        report_html._font_css()


def test_inline_scripts_reject_a_vendor_closing_tag(report_html: Any) -> None:
    assets = dict.fromkeys(
        ("cytoscape.min.js", "dagre.min.js", "cytoscape-dagre.js"), "window.x = 1;"
    )
    assets["dagre.min.js"] = "</script><script>alert(1)</script>"

    with pytest.raises(RuntimeError, match="closing script tag"):
        report_html._inline_scripts("{}", assets)


def test_write_html_creates_parent_directories_and_ends_with_one_newline(
    tmp_path: Path,
) -> None:
    target = tmp_path / "nested" / "report.html"
    write_html(make_report(), target)

    text = target.read_text(encoding="utf-8")
    assert text.startswith("<!DOCTYPE html>")
    assert text.endswith("\n")
    assert not text.endswith("\n\n")
