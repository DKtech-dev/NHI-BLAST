"""Properties and edge cases for the IAM glob matcher and intersection (spec 9.2)."""

from __future__ import annotations

import itertools

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from nhi_blast.aws.glob import (
    MAX_GLOB_LENGTH,
    glob_intersects,
    glob_match,
    has_wildcard,
    is_exact,
    wildcard_count,
)

ALPHABET = "ab"
PATTERN = st.text(alphabet=ALPHABET + "*?", max_size=4)
CONCRETE = st.text(alphabet=ALPHABET, max_size=5)


def _brute_intersects(a: str, b: str) -> bool:
    """Enumerate every candidate common string up to a safe bound."""
    max_length = len(a) + len(b) + 1
    for length in range(max_length + 1):
        for chars in itertools.product(ALPHABET, repeat=length):
            text = "".join(chars)
            if glob_match(a, text) and glob_match(b, text):
                return True
    return False


@pytest.mark.parametrize(
    ("pattern", "text", "expected"),
    [
        ("", "", True),
        ("", "a", False),
        ("*", "", True),
        ("*", "anything", True),
        ("a*", "a", True),
        ("a*", "abc", True),
        ("a*c", "abc", True),
        ("a*c", "ac", True),
        ("a*c", "abd", False),
        ("a?c", "abc", True),
        ("a?c", "ac", False),
        ("?*", "z", True),
        ("a**b", "ab", True),
        ("a**b", "axxb", True),
        ("ABC", "abc", False),
    ],
)
def test_glob_match_examples(pattern: str, text: str, expected: bool) -> None:
    assert glob_match(pattern, text) is expected


def test_glob_match_fold() -> None:
    assert glob_match("Repo:ACME/*", "repo:acme/shop", fold=True)
    assert not glob_match("Repo:ACME/*", "repo:acme/shop")


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        ("abc", "abc", True),
        ("abc", "abd", False),
        ("abc", "ab", False),
        ("*", "abc", True),
        ("a*", "abc", True),
        ("a*c", "ab*", True),
        ("a?c", "a*c", True),
        ("a*c", "a?d", False),
        ("repo:acme/*", "repo:acme/shop", True),
        ("repo:acme/*", "repo:other/shop", False),
        ("repo:acme@*/shop@*", "repo:acme/*", False),
        ("repo:acme@*/shop@*", "repo:acme@*/shop@*:ref:*", True),
    ],
)
def test_glob_intersects_examples(a: str, b: str, expected: bool) -> None:
    assert glob_intersects(a, b) is expected


def test_glob_intersects_fold() -> None:
    assert glob_intersects("Repo:ACME/*", "repo:acme/shop", fold=True)
    assert not glob_intersects("Repo:ACME/*", "repo:acme/shop")


@given(PATTERN, CONCRETE)
def test_intersection_with_concrete_equals_match(pattern: str, concrete: str) -> None:
    assert glob_intersects(pattern, concrete) is glob_match(pattern, concrete)


@given(PATTERN, PATTERN)
def test_intersection_is_symmetric(a: str, b: str) -> None:
    assert glob_intersects(a, b) is glob_intersects(b, a)


@given(PATTERN)
def test_every_pattern_intersects_itself(pattern: str) -> None:
    assert glob_intersects(pattern, pattern)


@given(PATTERN, PATTERN)
@settings(max_examples=150, deadline=None)
def test_intersection_matches_brute_force(a: str, b: str) -> None:
    assert glob_intersects(a, b) is _brute_intersects(a, b)


@given(PATTERN, PATTERN, CONCRETE)
def test_witness_implies_intersection(a: str, b: str, witness: str) -> None:
    if glob_match(a, witness) and glob_match(b, witness):
        assert glob_intersects(a, b)


def test_oversize_patterns_fail_closed() -> None:
    oversized = "a" * (MAX_GLOB_LENGTH + 1)
    assert glob_intersects(oversized, oversized)
    assert not glob_intersects(oversized, oversized[:-1] + "b")
    assert glob_intersects(oversized, "*")
    assert glob_intersects(oversized, "a*")


def test_wildcard_helpers() -> None:
    assert has_wildcard("a*b")
    assert has_wildcard("a?b")
    assert not has_wildcard("literal")
    assert wildcard_count("a*b?c**") == 4
    assert is_exact("literal")
    assert not is_exact("*")
