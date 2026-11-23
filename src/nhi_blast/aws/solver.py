"""Pure-Python bounded shared-witness solver for AWS IAM condition predicates.

Replaces pairwise heuristic checks with exact, bounded automata and interval solving:
- Minterm-compressed NFA->DFA intersection/complement for string/ARN globs
- Deletion-based Minimal Unsatisfiable Subset (MUS) on UNSAT
- Cross-key correlated OIDC projection across sub, ref, environment, and job_workflow_ref
- Exact IPv4/IPv6 CIDR conjunction and exclusion via stdlib ipaddress
- Exact Decimal interval conjunction and exclusion for Numeric* and Date* operators

All state-space budgets fail closed to SolverStatus.BUDGET (mapped to UNRESOLVED +
D-COND-BUDGET by callers). Zero external runtime dependencies.
"""

from __future__ import annotations

import ipaddress
import string
from collections import deque
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from urllib.parse import unquote

from nhi_blast.aws.glob import MAX_GLOB_LENGTH

MAX_DFA_STATES = 2048
MAX_PRODUCT_STATES = 16384
MAX_ALPHABET_SIZE = 512
MAX_CIDR_PREFIXES = 4096
MAX_WITNESS_STEPS = 10_000
_OTHER_SYMBOL = "\u0000"

_PREFERRED_ORDER = string.ascii_lowercase + string.digits + string.ascii_uppercase + "-_./:@+"
_PREFERRED_RANK = {ch: idx for idx, ch in enumerate(_PREFERRED_ORDER)}


class SolverStatus(StrEnum):
    SAT = "SAT"
    UNSAT = "UNSAT"
    BUDGET = "BUDGET"


@dataclass(frozen=True, slots=True)
class StringPredicate:
    """One conjunctive clause over a single string key.

    A positive clause requires the witness to match AT LEAST ONE pattern in ``patterns``.
    A negative clause requires the witness to match NONE of the patterns in ``patterns``.
    """

    label: str
    patterns: tuple[str, ...]
    negated: bool = False
    fold: bool = False
    is_glob: bool = True


@dataclass(frozen=True, slots=True)
class StringSolveResult:
    status: SolverStatus
    witness: str | None = None
    mus_indices: tuple[int, ...] = ()
    mus_labels: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class MultiKeySolveResult:
    status: SolverStatus
    witnesses: Mapping[str, str] = ()  # type: ignore[assignment]
    mus_labels: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CidrPredicate:
    label: str
    cidrs: tuple[str, ...]
    negated: bool = False


@dataclass(frozen=True, slots=True)
class CidrSolveResult:
    status: SolverStatus
    witness: str | None = None
    mus_labels: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class IntervalPredicate:
    """One Numeric* or Date* predicate normalized to Decimal (epoch seconds for dates)."""

    label: str
    relation: str  # "eq", "ne", "lt", "le", "gt", "ge"
    values: tuple[Decimal, ...]


@dataclass(frozen=True, slots=True)
class IntervalSolveResult:
    status: SolverStatus
    witness: Decimal | None = None
    mus_labels: tuple[str, ...] = ()


# ------------------------------------------------------------------ glob NFA -> DFA


def _symbol_sort_key(ch: str) -> tuple[int, int]:
    if ch == _OTHER_SYMBOL:
        return (2, 0)
    rank = _PREFERRED_RANK.get(ch)
    if rank is not None:
        return (0, rank)
    return (1, ord(ch))


def _choose_other_char(literals: set[str]) -> str:
    for ch in _PREFERRED_ORDER:
        if ch not in literals and ch.lower() not in literals and ch.upper() not in literals:
            return ch
    for code in range(0x21, 0x7F):
        ch = chr(code)
        if ch not in literals:
            return ch
    return "x"


def _normalize_ref_pattern(pattern: str) -> str:
    """Prevent degenerate empty ref segments like 'refs/heads/' when bounding wildcards."""
    for prefix in ("refs/heads/", "refs/tags/"):
        if pattern.endswith(f"{prefix}*"):
            return pattern[:-1] + "?*"
    return pattern


@dataclass(frozen=True, slots=True)
class _DFA:
    start: int
    accept: frozenset[int]
    transitions: tuple[dict[str, int], ...]
    symbols: tuple[str, ...]


def _literal_alphabet(predicates: Sequence[StringPredicate]) -> tuple[tuple[str, ...], str]:
    literals: set[str] = set()
    for pred in predicates:
        for pat in pred.patterns:
            for ch in pat:
                if pred.is_glob and ch in "*?":
                    continue
                literals.add(ch)
                if pred.fold and ch.isascii() and ch.isalpha():
                    literals.add(ch.lower())
                    literals.add(ch.upper())
                if len(literals) >= MAX_ALPHABET_SIZE:
                    ordered = (*sorted(literals, key=_symbol_sort_key), _OTHER_SYMBOL)
                    return ordered, _choose_other_char(literals)
    other = _choose_other_char(literals)
    ordered = (*sorted(literals, key=_symbol_sort_key), _OTHER_SYMBOL)
    return ordered, other


def _pattern_nfa_step(
    pattern: str,
    states: frozenset[int],
    sym: str,
    *,
    is_glob: bool,
    fold: bool,
) -> frozenset[int]:
    n = len(pattern)

    def _eps(seed: Iterable[int]) -> frozenset[int]:
        out = set(seed)
        stack = list(out)
        while stack:
            pos = stack.pop()
            if is_glob and pos < n and pattern[pos] == "*" and (pos + 1) not in out:
                out.add(pos + 1)
                stack.append(pos + 1)
        return frozenset(out)

    cur = _eps(states)
    nxt: set[int] = set()
    sym_cmp = sym.lower() if fold and sym != _OTHER_SYMBOL else sym
    for pos in cur:
        if pos >= n:
            continue
        ch = pattern[pos]
        if is_glob and ch == "*":
            nxt.add(pos)
        elif is_glob and ch == "?":
            nxt.add(pos + 1)
        else:
            pat_cmp = ch.lower() if fold else ch
            if sym != _OTHER_SYMBOL and sym_cmp == pat_cmp:
                nxt.add(pos + 1)
    return _eps(nxt)


def _compile_predicate_dfa(
    pred: StringPredicate,
    symbols: tuple[str, ...],
) -> _DFA | None:
    """Compile a single StringPredicate (disjunction of patterns, optionally negated) to a DFA."""
    if len(symbols) > MAX_ALPHABET_SIZE:
        return None
    if any(len(p) > MAX_GLOB_LENGTH for p in pred.patterns):
        return None
    fold = pred.fold
    pats = tuple(
        _normalize_ref_pattern(p.lower() if fold else p)
        if pred.is_glob
        else (p.lower() if fold else p)
        for p in pred.patterns
    )
    if any(len(p) > MAX_GLOB_LENGTH for p in pats):
        return None
    if not pats:
        # Empty positive disjunction is unsatisfiable; empty negative disjunction is tautological.
        accept = frozenset({0}) if pred.negated else frozenset()
        return _DFA(
            start=0, accept=accept, transitions=(dict.fromkeys(symbols, 0),), symbols=symbols
        )

    def _init_state(pat: str) -> frozenset[int]:
        if not pred.is_glob:
            return frozenset({0})
        out = {0}
        pos = 0
        while pos < len(pat) and pat[pos] == "*":
            pos += 1
            out.add(pos)
        return frozenset(out)

    start_tuple = tuple(_init_state(p) for p in pats)
    state_ids: dict[tuple[frozenset[int], ...], int] = {start_tuple: 0}
    queue: deque[tuple[frozenset[int], ...]] = deque([start_tuple])
    transitions: list[dict[str, int]] = []
    accepting: set[int] = set()

    while queue:
        cur = queue.popleft()
        cur_id = state_ids[cur]
        matched = any(len(pats[i]) in cur[i] for i in range(len(pats)))
        if matched != pred.negated:
            accepting.add(cur_id)
        trans: dict[str, int] = {}
        for sym in symbols:
            nxt = tuple(
                _pattern_nfa_step(pats[i], cur[i], sym, is_glob=pred.is_glob, fold=fold)
                for i in range(len(pats))
            )
            nxt_id = state_ids.get(nxt)
            if nxt_id is None:
                if len(state_ids) >= MAX_DFA_STATES:
                    return None
                nxt_id = len(state_ids)
                state_ids[nxt] = nxt_id
                queue.append(nxt)
            trans[sym] = nxt_id
        transitions.append(trans)

    return _DFA(
        start=0,
        accept=frozenset(accepting),
        transitions=tuple(transitions),
        symbols=symbols,
    )


def _solve_compiled_dfas(
    dfas: Sequence[_DFA],
    symbols: tuple[str, ...],
    other_char: str,
) -> tuple[SolverStatus, str | None]:
    if not dfas:
        return SolverStatus.SAT, ""
    start = tuple(d.start for d in dfas)
    if all(start[i] in dfas[i].accept for i in range(len(dfas))):
        return SolverStatus.SAT, ""

    visited: set[tuple[int, ...]] = {start}
    parent: dict[tuple[int, ...], tuple[tuple[int, ...] | None, str]] = {start: (None, "")}
    queue: deque[tuple[int, ...]] = deque([start])

    while queue:
        cur = queue.popleft()
        for sym in symbols:
            nxt = tuple(dfas[i].transitions[cur[i]][sym] for i in range(len(dfas)))
            if nxt in visited:
                continue
            if len(visited) >= MAX_PRODUCT_STATES:
                return SolverStatus.BUDGET, None
            visited.add(nxt)
            ch = other_char if sym == _OTHER_SYMBOL else sym
            parent[nxt] = (cur, ch)
            if all(nxt[i] in dfas[i].accept for i in range(len(dfas))):
                chars: list[str] = []
                node: tuple[int, ...] | None = nxt
                while node is not None:
                    prev, edge_ch = parent[node]
                    if prev is not None:
                        chars.append(edge_ch)
                    node = prev
                chars.reverse()
                return SolverStatus.SAT, "".join(chars)
            queue.append(nxt)

    return SolverStatus.UNSAT, None


def _compute_mus(
    predicates: Sequence[StringPredicate],
    dfas: Sequence[_DFA],
    symbols: tuple[str, ...],
    other_char: str,
) -> tuple[tuple[int, ...], tuple[str, ...]]:
    """Deletion-based Minimal Unsatisfiable Subset over compiled DFAs."""
    active = list(range(len(dfas)))
    for idx in list(active):
        trial = [i for i in active if i != idx]
        status, _ = _solve_compiled_dfas([dfas[i] for i in trial], symbols, other_char)
        if status is SolverStatus.UNSAT:
            active = trial
    return tuple(active), tuple(predicates[i].label for i in active)


def solve_string_predicates(predicates: Sequence[StringPredicate]) -> StringSolveResult:
    """Solve a conjunction of positive/negative string/glob predicates over one key."""
    if not predicates:
        return StringSolveResult(status=SolverStatus.SAT, witness="")
    if any(len(p) > MAX_GLOB_LENGTH for pred in predicates for p in pred.patterns):
        return StringSolveResult(status=SolverStatus.BUDGET)
    symbols, other_char = _literal_alphabet(predicates)
    if len(symbols) > MAX_ALPHABET_SIZE:
        return StringSolveResult(status=SolverStatus.BUDGET)
    dfas: list[_DFA] = []
    for pred in predicates:
        dfa = _compile_predicate_dfa(pred, symbols)
        if dfa is None:
            return StringSolveResult(status=SolverStatus.BUDGET)
        dfas.append(dfa)

    status, witness = _solve_compiled_dfas(dfas, symbols, other_char)
    if status is SolverStatus.SAT:
        return StringSolveResult(status=SolverStatus.SAT, witness=witness)
    if status is SolverStatus.BUDGET:
        return StringSolveResult(status=SolverStatus.BUDGET)

    mus_idx, mus_labels = _compute_mus(predicates, dfas, symbols, other_char)
    return StringSolveResult(
        status=SolverStatus.UNSAT,
        mus_indices=mus_idx,
        mus_labels=mus_labels,
    )


# ------------------------------------------------------- cross-key OIDC projection


def _project_ref_from_sub(pattern: str) -> str | None:
    marker = ":ref:"
    idx = pattern.find(marker)
    if idx == -1:
        return None
    return pattern[idx + len(marker) :]


def _project_env_from_sub(pattern: str) -> str | None:
    marker = ":environment:"
    idx = pattern.find(marker)
    if idx == -1:
        return None
    return unquote(pattern[idx + len(marker) :])


def _project_repo_from_sub(pattern: str, *, is_glob: bool = True) -> str | None:
    if not pattern.startswith("repo:"):
        return None
    body = pattern[len("repo:") :]
    if ":" not in body and not is_glob:
        return None
    repo_part = body.split(":", 1)[0]
    if "/" not in repo_part:
        return None
    owner_part, repo_name = repo_part.split("/", 1)
    owner = owner_part.split("@", 1)[0]
    name = repo_name.split("@", 1)[0]
    if not owner or not name:
        return None
    return f"{owner}/{name}"


def _project_owner_from_sub(pattern: str, *, is_glob: bool = True) -> str | None:
    repo = _project_repo_from_sub(pattern, is_glob=is_glob)
    if repo is None:
        return None
    return repo.split("/", 1)[0]


def solve_correlated_oidc_predicates(
    predicates_by_key: Mapping[str, Sequence[StringPredicate]],
) -> MultiKeySolveResult:
    """Jointly solve correlated GitHub OIDC keys (sub, ref, environment, job_workflow_ref).

    Projects ref, environment, repository, and repository_owner constraints implied by
    ``sub`` onto the shared variable domain so cross-key contradictions (e.g.
    ``sub=repo:org-a/app:ref:refs/heads/main`` AND ``repository_owner=org-b``) are
    detected as UNSAT and coherent multi-claim witnesses are produced on SAT.
    ``job_workflow_ref`` is solved against its own predicates without projecting into
    the caller's ``repository``/``repository_owner``/``ref`` buckets because reusable
    workflows legitimately live in a different repository, owner, or ref than ``sub``.
    """
    working: dict[str, list[StringPredicate]] = {
        key: list(preds) for key, preds in predicates_by_key.items() if preds
    }

    # Project positive ref/environment/repository/repository_owner bindings from sub
    sub_preds = working.get("sub", [])
    for pred in sub_preds:
        if pred.negated:
            continue
        ref_pats = tuple(
            p for p in (_project_ref_from_sub(x) for x in pred.patterns) if p is not None
        )
        if ref_pats and len(ref_pats) == len(pred.patterns):
            working.setdefault("ref", []).append(
                StringPredicate(
                    label=f"projected(ref<-{pred.label})",
                    patterns=ref_pats,
                    negated=False,
                    fold=pred.fold,
                    is_glob=pred.is_glob,
                )
            )
        env_pats = tuple(
            p for p in (_project_env_from_sub(x) for x in pred.patterns) if p is not None
        )
        if env_pats and len(env_pats) == len(pred.patterns):
            working.setdefault("environment", []).append(
                StringPredicate(
                    label=f"projected(environment<-{pred.label})",
                    patterns=env_pats,
                    negated=False,
                    fold=pred.fold,
                    is_glob=pred.is_glob,
                )
            )
        repo_pats = tuple(
            p
            for p in (_project_repo_from_sub(x, is_glob=pred.is_glob) for x in pred.patterns)
            if p is not None
        )
        if repo_pats and len(repo_pats) == len(pred.patterns):
            working.setdefault("repository", []).append(
                StringPredicate(
                    label=f"projected(repository<-{pred.label})",
                    patterns=repo_pats,
                    negated=False,
                    fold=pred.fold,
                    is_glob=pred.is_glob,
                )
            )
        owner_pats = tuple(
            p
            for p in (_project_owner_from_sub(x, is_glob=pred.is_glob) for x in pred.patterns)
            if p is not None
        )
        if owner_pats and len(owner_pats) == len(pred.patterns):
            working.setdefault("repository_owner", []).append(
                StringPredicate(
                    label=f"projected(repository_owner<-{pred.label})",
                    patterns=owner_pats,
                    negated=False,
                    fold=pred.fold,
                    is_glob=pred.is_glob,
                )
            )

    witnesses: dict[str, str] = {}
    for key in sorted(working):
        res = solve_string_predicates(working[key])
        if res.status is SolverStatus.BUDGET:
            return MultiKeySolveResult(status=SolverStatus.BUDGET)
        if res.status is SolverStatus.UNSAT:
            return MultiKeySolveResult(status=SolverStatus.UNSAT, mus_labels=res.mus_labels)
        if res.witness is not None:
            witnesses[key] = res.witness

    return MultiKeySolveResult(status=SolverStatus.SAT, witnesses=witnesses)


# ----------------------------------------------------------- exact CIDR solver


IPNet = ipaddress.IPv4Network | ipaddress.IPv6Network


def _parse_cidr(raw: str) -> IPNet:
    return ipaddress.ip_network(raw.strip(), strict=False)


def _subtract_network(nets: list[IPNet], excluded: IPNet) -> list[IPNet] | None:
    out: list[IPNet] = []
    for net in nets:
        if net.version != excluded.version or not net.overlaps(excluded):
            out.append(net)
            if len(out) > MAX_CIDR_PREFIXES:
                return None
            continue
        if excluded.supernet_of(net):  # type: ignore[arg-type]
            continue
        for piece in net.address_exclude(excluded):  # type: ignore[arg-type]
            out.append(piece)
            if len(out) > MAX_CIDR_PREFIXES:
                return None
    return out


def _intersect_network_sets(left: list[IPNet], right: list[IPNet]) -> list[IPNet] | None:
    out: list[IPNet] = []
    for a in left:
        for b in right:
            if a.version != b.version or not a.overlaps(b):
                continue
            out.append(a if a.prefixlen >= b.prefixlen else b)
            if len(out) > MAX_CIDR_PREFIXES:
                return None
    v4 = list(
        ipaddress.collapse_addresses([n for n in out if isinstance(n, ipaddress.IPv4Network)])
    )
    v6 = list(
        ipaddress.collapse_addresses([n for n in out if isinstance(n, ipaddress.IPv6Network)])
    )
    combined: list[IPNet] = [*v4, *v6]
    if len(combined) > MAX_CIDR_PREFIXES:
        return None
    return combined


def solve_cidr_predicates(predicates: Sequence[CidrPredicate]) -> CidrSolveResult:
    """Solve conjunction and exclusion of IPv4/IPv6 CIDR predicates."""
    if not predicates:
        return CidrSolveResult(status=SolverStatus.SAT, witness="192.0.2.1")
    allowed: list[IPNet] = [
        ipaddress.IPv4Network("0.0.0.0/0"),
        ipaddress.IPv6Network("::/0"),
    ]
    used_labels: list[str] = []
    for pred in predicates:
        used_labels.append(pred.label)
        if len(pred.cidrs) > MAX_CIDR_PREFIXES:
            return CidrSolveResult(status=SolverStatus.BUDGET)
        parsed = [_parse_cidr(c) for c in pred.cidrs]
        if pred.negated:
            for excl in parsed:
                reduced = _subtract_network(allowed, excl)
                if reduced is None:
                    return CidrSolveResult(status=SolverStatus.BUDGET)
                allowed = reduced
        else:
            intersected = _intersect_network_sets(allowed, parsed)
            if intersected is None:
                return CidrSolveResult(status=SolverStatus.BUDGET)
            allowed = intersected
        if not allowed:
            return CidrSolveResult(status=SolverStatus.UNSAT, mus_labels=tuple(used_labels))
    first = allowed[0]
    return CidrSolveResult(status=SolverStatus.SAT, witness=str(first.network_address))


# ------------------------------------------------- exact Numeric / Date interval solver


def parse_iso8601_decimal(raw: str) -> Decimal:
    """Parse an ISO-8601 timestamp or epoch seconds string into an exact Decimal."""
    text = raw.strip()
    try:
        return Decimal(text)
    except InvalidOperation:
        pass
    iso = text[:-1] + "+00:00" if text.endswith(("Z", "z")) else text
    dt = datetime.fromisoformat(iso)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return Decimal(str(dt.timestamp()))


def _step_up(val: Decimal) -> Decimal:
    nxt = val + Decimal(1)
    return nxt if nxt > val else val.next_plus()


def _step_down(val: Decimal) -> Decimal:
    nxt = val - Decimal(1)
    return nxt if nxt < val else val.next_minus()


def solve_interval_predicates(  # noqa: PLR0912, PLR0911
    predicates: Sequence[IntervalPredicate],
) -> IntervalSolveResult:
    """Solve conjunction of Numeric* or Date* predicates over exact Decimal intervals."""
    if not predicates:
        return IntervalSolveResult(status=SolverStatus.SAT, witness=Decimal(0))

    low: Decimal | None = None
    low_inc = True
    high: Decimal | None = None
    high_inc = True
    excluded: set[Decimal] = set()
    allowed_sets: list[set[Decimal]] = []
    labels: list[str] = []

    for pred in predicates:
        labels.append(pred.label)
        if any(v.is_nan() for v in pred.values):
            return IntervalSolveResult(status=SolverStatus.BUDGET)
        if not pred.values:
            if pred.relation == "ne":
                continue
            return IntervalSolveResult(status=SolverStatus.UNSAT, mus_labels=tuple(labels))
        if pred.relation == "eq":
            allowed_sets.append(set(pred.values))
        elif pred.relation == "ne":
            excluded.update(pred.values)
        elif pred.relation == "lt":
            bound = max(pred.values)
            if high is None or bound < high or (bound == high and high_inc):
                high, high_inc = bound, False
        elif pred.relation == "le":
            bound = max(pred.values)
            if high is None or bound < high:
                high, high_inc = bound, True
        elif pred.relation == "gt":
            bound = min(pred.values)
            if low is None or bound > low or (bound == low and low_inc):
                low, low_inc = bound, False
        elif pred.relation == "ge":
            bound = min(pred.values)
            if low is None or bound > low:
                low, low_inc = bound, True

    def _in_bounds(val: Decimal) -> bool:
        if val in excluded:
            return False
        if low is not None and (val < low or (val == low and not low_inc)):
            return False
        return not (high is not None and (val > high or (val == high and not high_inc)))

    if allowed_sets:
        candidates = set.intersection(*allowed_sets)
        valid = sorted(v for v in candidates if _in_bounds(v))
        if valid:
            return IntervalSolveResult(status=SolverStatus.SAT, witness=valid[0])
        return IntervalSolveResult(status=SolverStatus.UNSAT, mus_labels=tuple(labels))

    if low is not None and high is not None:
        if low > high or (low == high and (not low_inc or not high_inc)):
            return IntervalSolveResult(status=SolverStatus.UNSAT, mus_labels=tuple(labels))
        if low == high:
            if low not in excluded:
                return IntervalSolveResult(status=SolverStatus.SAT, witness=low)
            return IntervalSolveResult(status=SolverStatus.UNSAT, mus_labels=tuple(labels))
        # Continuous interval (low, high): pick midpoint avoiding excluded values.
        step = Decimal(2)
        a, b = low, high
        for _ in range(128):
            mid = (a + b) / step
            if _in_bounds(mid):
                return IntervalSolveResult(status=SolverStatus.SAT, witness=mid)
            a = mid
        return IntervalSolveResult(status=SolverStatus.UNSAT, mus_labels=tuple(labels))

    if low is not None:
        if not low.is_finite():
            return IntervalSolveResult(status=SolverStatus.BUDGET)
        cand = low if low_inc else _step_up(low)
        for _ in range(MAX_WITNESS_STEPS):
            if not cand.is_finite():
                return IntervalSolveResult(status=SolverStatus.BUDGET)
            if _in_bounds(cand):
                return IntervalSolveResult(status=SolverStatus.SAT, witness=cand)
            nxt = _step_up(cand)
            if nxt <= cand:
                return IntervalSolveResult(status=SolverStatus.BUDGET)
            cand = nxt
        return IntervalSolveResult(status=SolverStatus.BUDGET)

    if high is not None:
        if not high.is_finite():
            return IntervalSolveResult(status=SolverStatus.BUDGET)
        cand = high if high_inc else _step_down(high)
        for _ in range(MAX_WITNESS_STEPS):
            if not cand.is_finite():
                return IntervalSolveResult(status=SolverStatus.BUDGET)
            if _in_bounds(cand):
                return IntervalSolveResult(status=SolverStatus.SAT, witness=cand)
            nxt = _step_down(cand)
            if nxt >= cand:
                return IntervalSolveResult(status=SolverStatus.BUDGET)
            cand = nxt
        return IntervalSolveResult(status=SolverStatus.BUDGET)

    cand = Decimal(0)
    for _ in range(MAX_WITNESS_STEPS):
        if cand not in excluded:
            return IntervalSolveResult(status=SolverStatus.SAT, witness=cand)
        cand = _step_up(cand)
    return IntervalSolveResult(status=SolverStatus.BUDGET)


__all__ = [
    "MAX_ALPHABET_SIZE",
    "MAX_CIDR_PREFIXES",
    "MAX_DFA_STATES",
    "MAX_PRODUCT_STATES",
    "MAX_WITNESS_STEPS",
    "CidrPredicate",
    "CidrSolveResult",
    "IntervalPredicate",
    "IntervalSolveResult",
    "MultiKeySolveResult",
    "SolverStatus",
    "StringPredicate",
    "StringSolveResult",
    "parse_iso8601_decimal",
    "solve_cidr_predicates",
    "solve_correlated_oidc_predicates",
    "solve_interval_predicates",
    "solve_string_predicates",
]
