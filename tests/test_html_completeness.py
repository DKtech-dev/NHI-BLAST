"""The analysis-completeness panel and the scope-aware empty findings state (plan A3, HTML)."""

from __future__ import annotations

import json
import re
from functools import cache
from html.parser import HTMLParser
from pathlib import Path

from nhi_blast.core.completeness import FAMILY_LABELS
from nhi_blast.core.models import (
    Completeness,
    CompletenessItem,
    CompletenessSource,
    CompletenessStatus,
    InputFamily,
)
from nhi_blast.pipeline import ScanOptions, run_scan
from nhi_blast.report.html import html_report
from nhi_blast.report.ui import APP_JS
from tests.report_support import HOSTILE, make_report

FX07 = Path(__file__).parent / "fixtures" / "fx07-incident"
ACTION = "action:tj-actions/changed-files@v45"
STATUS_ORDER = (
    "partially_analysed",
    "not_provided",
    "not_supported",
    "analysed",
    "not_applicable",
)


class _Tags(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tags: list[tuple[str, dict[str, str | None]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append((tag, dict(attrs)))


@cache
def _fx07() -> tuple[str, dict[str, object]]:
    report = run_scan(ScanOptions(root=FX07, selectors=(ACTION,))).report
    document = html_report(report)
    island = re.search(
        r'<script type="application/json" id="report-data">(.*?)</script>', document, re.DOTALL
    )
    assert island is not None
    return document, json.loads(island.group(1))


def _panel_js() -> str:
    start = APP_JS.index("const COMPLETENESS_GROUPS")
    return APP_JS[start : APP_JS.index("function revealDisclosure(")]


def test_panel_section_sits_between_summary_and_survival_with_a_nav_link() -> None:
    document, _ = _fx07()
    summary = document.index('<section id="summary"')
    panel = document.index('<section id="completeness"')
    survival = document.index('<section id="survival"')
    assert summary < panel < survival
    assert '<h2 id="completeness-title">Analysis completeness</h2>' in document
    assert (
        # G6: the floating nav uses the short label; the section heading keeps the full title.
        '<a id="completeness-link" href="#completeness" hidden>Completeness</a>' in document
    )
    assert '<div id="completeness-content"></div>' in document


def test_island_carries_the_completeness_items_the_panel_renders() -> None:
    _, data = _fx07()
    block = data["completeness"]
    assert isinstance(block, dict)
    items = block["items"]
    assert isinstance(items, list)
    assert len(items) == len(InputFamily)
    statuses = {item["status"] for item in items}
    assert statuses <= set(STATUS_ORDER)
    # The three statuses that must never read as a clean result are present on fx07.
    assert {"not_provided", "not_supported"} <= statuses


def test_groups_follow_the_documented_order_and_the_last_two_start_collapsed() -> None:
    js = _panel_js()
    positions = [js.index(f'key: "{key}"') for key in STATUS_ORDER]
    assert positions == sorted(positions)
    assert js.count("collapsed: true") == 2
    assert js.index('key: "analysed", label: "Analysed", collapsed: true') > positions[2]
    assert (
        js.index('key: "not_applicable", label: "Not applicable", collapsed: true') > positions[3]
    )
    assert 'host = append(group, "details");' in js
    assert 'append(host, "summary", "", "Show " + plural(groupInfo.items.length, "item"));' in js


def test_family_labels_are_embedded_from_the_core_table_and_inert() -> None:
    match = re.search(r"const FAMILY_LABELS = (\{.*?\});", APP_JS)
    assert match is not None
    assert json.loads(match.group(1)) == {
        family.value: label for family, label in FAMILY_LABELS.items()
    }
    assert "__FAMILY_LABELS__" not in APP_JS
    assert "</script" not in APP_JS.lower()


def test_item_rendering_uses_text_status_badges_sources_hashes_and_links() -> None:
    js = _panel_js()
    assert "statusBadge(head, item.status, group ? group.label :" in js
    assert 'textOf(item.status).replace(/_/g, " "));' in js
    assert "textOf(source.sha256).slice(0, 12)" in js
    assert 'completenessLinks(facts, "Diagnostics", item.diagnostics, "diagnostic-");' in js
    assert 'completenessLinks(facts, "Assumptions", item.assumptions, "assumption-");' in js
    assert 'link.setAttribute("href", "#" + targetId);' in js
    assert 'row.setAttribute("id", "assumption-" + safeId(assumption.id));' in APP_JS
    assert 'row.setAttribute("id", "diagnostic-" + safeId(item.code));' in APP_JS
    for forbidden in ("innerHTML", "insertAdjacentHTML", "outerHTML"):
        assert forbidden not in js


def test_panel_wording_makes_no_percentage_or_completeness_claim() -> None:
    document, _ = _fx07()
    js = _panel_js()
    section = document[
        document.index('<section id="completeness"') : document.index('<section id="survival"')
    ]
    strings = " ".join(re.findall(r'"([^"\n]*)"', js)) + " " + section
    assert "%" not in strings
    assert not re.search(r"\bcomplete\b|fully analysed|fully covered", strings, re.IGNORECASE)
    joined = re.sub(r'"\s*\+\s*"', "", js)
    assert "the report says nothing about that family, not that nothing is there" in joined


def test_empty_findings_state_points_at_the_panel_when_there_are_gaps() -> None:
    assert 'document.createTextNode("No findings in the analysed scope - see ")' in APP_JS
    assert 'link.setAttribute("href", "#completeness");' in APP_JS
    gap = APP_JS.index("!matches.length && !findings.length && completenessGaps().length")
    plain = APP_JS.index('"No findings were generated."')
    assert gap < plain
    assert 'const GAP_STATUSES = ["partially_analysed", "not_provided", "not_supported"];' in APP_JS


def test_hostile_completeness_strings_stay_data() -> None:
    report = make_report()
    completeness = Completeness(
        items=(
            CompletenessItem(
                id="gha_workflows",
                family=InputFamily.GHA_WORKFLOWS,
                status=CompletenessStatus.PARTIALLY_ANALYSED,
                sources=(CompletenessSource(path=HOSTILE, sha256="f" * 64),),
                diagnostics=(HOSTILE,),
                assumptions=(HOSTILE,),
                explanation=HOSTILE,
            ),
        ),
        digest="d" * 64,
    )
    document = html_report(report.model_copy(update={"completeness": completeness}))
    tags = _Tags()
    tags.feed(document)
    names = [tag for tag, _ in tags.tags]

    assert names.count("script") == 5
    assert not {"img", "iframe", "object", "embed"} & set(names)
    assert not any(name.lower().startswith("on") for _, attrs in tags.tags for name in attrs)
    island = re.search(
        r'<script type="application/json" id="report-data">(.*?)</script>', document, re.DOTALL
    )
    assert island is not None
    assert "<" not in island.group(1)
    data = json.loads(island.group(1))
    item = data["completeness"]["items"][0]
    assert item["sources"][0]["path"] == HOSTILE
    assert item["explanation"] == HOSTILE
