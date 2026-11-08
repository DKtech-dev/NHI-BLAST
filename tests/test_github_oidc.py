"""GitHub OIDC subject formats and the [github] config table (plan C7)."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest

from nhi_blast.core.config import Config, ConfigError
from nhi_blast.core.models import OidcSettings, Report, SubFormat
from nhi_blast.oidc.github_subject import format_is_declared, repo_prefixes
from nhi_blast.pipeline import ScanOptions, run_scan

FX07 = Path(__file__).parent / "fixtures" / "fx07-incident"
CLASSIC = (SubFormat.CLASSIC, "repo:acme/app")
WILDCARD = (SubFormat.IMMUTABLE, "repo:acme@*/app@*")
EXACT = (SubFormat.IMMUTABLE, "repo:acme@123/app@456")


def _settings(**kwargs: Any) -> OidcSettings:
    return OidcSettings(**kwargs)


def test_default_emits_both_formats_with_wildcard_ids() -> None:
    assert repo_prefixes("acme/app") == (CLASSIC, WILDCARD)
    assert repo_prefixes("acme/app", _settings()) == (CLASSIC, WILDCARD)
    assert not format_is_declared(None)
    assert not format_is_declared(_settings())


def test_unknown_slug_stays_symbolic() -> None:
    assert repo_prefixes(None, _settings(subject_format="immutable")) == (
        (SubFormat.UNKNOWN, "*/*"),
    )


def test_declared_ids_make_the_immutable_subject_exact() -> None:
    both = _settings(owner_id=123, repo_id=456)
    assert repo_prefixes("acme/app", both) == (CLASSIC, EXACT)
    only = _settings(subject_format="immutable", owner_id=123, repo_id=456)
    assert repo_prefixes("acme/app", only) == (EXACT,)
    assert format_is_declared(only)


def test_declared_immutable_without_ids_keeps_the_wildcard_only() -> None:
    assert repo_prefixes("acme/app", _settings(subject_format="immutable")) == (WILDCARD,)


def test_classic_and_ghes_never_emit_the_immutable_form() -> None:
    assert repo_prefixes("acme/app", _settings(subject_format="classic")) == (CLASSIC,)
    ghes = _settings(host="ghes")
    assert repo_prefixes("acme/app", ghes) == (CLASSIC,)
    assert format_is_declared(ghes)


@pytest.mark.parametrize(
    ("github", "message"),
    [
        ({"host": "gitlab"}, "host"),
        ({"subject_format": "both"}, "subject_format"),
        ({"owner_id": 0, "repo_id": 1}, "owner_id"),
        ({"owner_id": True, "repo_id": 1}, "owner_id"),
        ({"owner_id": "7", "repo_id": 1}, "owner_id"),
        ({"owner_id": 7}, "together"),
        ({"repo_id": 7}, "together"),
        ({"host": "ghes", "subject_format": "immutable"}, "Enterprise Server"),
        ({"host": "ghes", "owner_id": 1, "repo_id": 2}, "Enterprise Server"),
        ({"subject_format": "classic", "owner_id": 1, "repo_id": 2}, "contradict"),
        ({"surprise": 1}, "unknown"),
    ],
)
def test_invalid_github_tables_are_rejected(github: dict[str, Any], message: str) -> None:
    with pytest.raises(ConfigError, match=message):
        Config.from_mapping({"github": github})


def test_github_table_must_be_a_table() -> None:
    with pytest.raises(ConfigError, match="table"):
        Config.from_mapping({"github": "immutable"})


def test_github_settings_change_the_config_digest() -> None:
    base = Config.from_mapping({}).digest()
    immutable = Config.from_mapping({"github": {"subject_format": "immutable"}}).digest()
    ids = Config.from_mapping(
        {"github": {"subject_format": "immutable", "owner_id": 1, "repo_id": 2}}
    ).digest()
    assert len({base, immutable, ids}) == 3
    assert Config.from_mapping({"github": {}}).oidc_settings() == OidcSettings()


def _assumption_ids(report: Report) -> set[str]:
    return {item.id for item in report.assumptions}


def _scan(tmp_path: Path, config_text: str | None) -> Report:
    root = tmp_path / "repo"
    shutil.copytree(FX07, root)
    config = None
    if config_text is not None:
        config = root / "nhi-blast.toml"
        config.write_text(config_text, encoding="utf-8")
    options = ScanOptions(
        root=root, repo_slug="acme/app", config_path=config, selectors=("repo-write",)
    )
    return run_scan(options).report


def _formats_matched(report: Report) -> set[str]:
    found: set[str] = set()
    for edge in report.graph.edges:
        found.update(str(item) for item in edge.attrs.get("matched_formats", ()))
    return found


def test_undeclared_format_reports_the_age_assumption(tmp_path: Path) -> None:
    report = _scan(tmp_path, None)
    assert report.context is not None
    assert report.context.oidc == OidcSettings()
    assert "A-REPO-AGE" in _assumption_ids(report)
    assert _formats_matched(report) == {"CLASSIC"}


def test_declared_format_removes_the_age_assumption_and_is_recorded(tmp_path: Path) -> None:
    report = _scan(
        tmp_path,
        '[github]\nsubject_format = "immutable"\nowner_id = 123\nrepo_id = 456\n',
    )
    assert report.context is not None
    assert report.context.oidc == _settings(subject_format="immutable", owner_id=123, repo_id=456)
    assert "A-REPO-AGE" not in _assumption_ids(report)
    # fx07's trust policy is written for the classic form, so it no longer matches.
    assert _formats_matched(report) == set()


def test_ghes_scan_matches_only_classic_subjects(tmp_path: Path) -> None:
    report = _scan(tmp_path, '[github]\nhost = "ghes"\n')
    assert "A-REPO-AGE" not in _assumption_ids(report)
    assert _formats_matched(report) == {"CLASSIC"}
