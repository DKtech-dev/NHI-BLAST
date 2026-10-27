"""uses: reference parsing and pin classification (spec 7.6)."""

from __future__ import annotations

import re

from nhi_blast.core.models import PinKind
from nhi_blast.parsers.gha.facts import UsesRef

_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$|^[0-9a-fA-F]{64}$")
_TAG_RE = re.compile(r"^v?\d+(?:\.\d+)*$")
_BRANCHES = frozenset({"main", "master", "develop", "dev", "trunk"})
_FIRST_PARTY = frozenset({"actions", "github"})
_REUSABLE_SUFFIXES = (".yml", ".yaml")


def classify_pin(ref: str | None, *, is_docker: bool = False) -> PinKind:
    if is_docker:
        return PinKind.SHA if ref else PinKind.DOCKER
    if ref is None:
        return PinKind.AMBIGUOUS
    if _SHA_RE.match(ref):
        return PinKind.SHA
    if _TAG_RE.match(ref):
        return PinKind.TAG
    if ref in _BRANCHES:
        return PinKind.BRANCH
    return PinKind.AMBIGUOUS


def parse_uses(raw: str, line: int) -> UsesRef:
    value = raw.strip()
    if value.startswith("docker://"):
        reference = value[len("docker://") :]
        digest = reference.split("@", 1)[1] if "@" in reference else None
        pinned = digest is not None and digest.startswith("sha256:")
        return UsesRef(
            raw=value,
            kind="DOCKER",
            pin_kind=PinKind.SHA if pinned else PinKind.DOCKER,
            mutable=not pinned,
            line=line,
        )
    if value.startswith("./") or value == ".":
        return UsesRef(
            raw=value,
            kind="LOCAL",
            pin_kind=PinKind.LOCAL,
            mutable=False,
            first_party=True,
            line=line,
        )
    ref: str | None = None
    path = value
    if "@" in value:
        path, ref = value.rsplit("@", 1)
        ref = ref.strip() or None
    parts = path.split("/")
    owner = parts[0] if parts and parts[0] else None
    repo = parts[1] if len(parts) > 1 else None
    subpath = "/".join(parts[2:]) if len(parts) > 2 else None
    pin_kind = classify_pin(ref)
    return UsesRef(
        raw=value,
        kind="REMOTE",
        owner=owner,
        repo=repo,
        subpath=subpath,
        ref=ref,
        pin_kind=pin_kind,
        mutable=pin_kind is not PinKind.SHA,
        first_party=owner is not None and owner.lower() in _FIRST_PARTY,
        line=line,
    )


def is_reusable_workflow_ref(uses: UsesRef) -> bool:
    """True when a uses: value names a workflow file (job-level reusable call)."""
    if uses.kind == "LOCAL":
        return uses.raw.endswith(_REUSABLE_SUFFIXES)
    if uses.kind != "REMOTE" or uses.subpath is None:
        return False
    return uses.subpath.startswith(".github/workflows/") and uses.subpath.endswith(
        _REUSABLE_SUFFIXES
    )


def local_action_dir(uses: UsesRef) -> str | None:
    """Return the relative directory of a local action reference, if any."""
    if uses.kind != "LOCAL":
        return None
    value = uses.raw.strip()
    if value == ".":
        return "."
    if not value.startswith("./"):
        return None
    return value[2:].rstrip("/") or "."


def is_action(uses: UsesRef, owner: str, repo: str) -> bool:
    return (
        uses.kind == "REMOTE"
        and uses.owner is not None
        and uses.repo is not None
        and uses.owner.lower() == owner.lower()
        and uses.repo.lower() == repo.lower()
    )
