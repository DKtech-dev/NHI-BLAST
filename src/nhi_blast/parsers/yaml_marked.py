"""Safe YAML loading with line marks (spec 7.1).

yaml.compose_all builds the node graph without constructing Python objects, so no
arbitrary object construction is possible and anchors stay shared rather than being
expanded eagerly. Only the first document is composed and the remaining stream is not
read. The walker converts nodes into Marked trees while enforcing the
node-count, depth and alias-expansion limits, detecting duplicate mapping keys and
normalising the YAML 1.1 on key (which PyYAML resolves to boolean True) back to the
string "on". Only the first document is read.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import yaml
from yaml.nodes import MappingNode, Node, ScalarNode, SequenceNode

from nhi_blast.core.diagnostics import Diagnostic, error, warning
from nhi_blast.core.limits import Limits


class _AbortWalkError(Exception):
    """Raised internally for structural limits or invalid Unicode scalars."""


@dataclass(frozen=True, slots=True)
class Marked:
    """A YAML value with the 1-based source line of its node."""

    value: Any
    line: int
    end_line: int

    def is_mapping(self) -> bool:
        return isinstance(self.value, dict)

    def is_sequence(self) -> bool:
        return isinstance(self.value, tuple)

    def is_scalar(self) -> bool:
        return not isinstance(self.value, (dict, tuple))

    def get(self, key: str) -> Marked | None:
        if not isinstance(self.value, dict):
            return None
        return self.value.get(key)

    def get_str(self, key: str) -> str | None:
        item = self.get(key)
        if item is None:
            return None
        if isinstance(item.value, str):
            return item.value
        if item.value is None:
            return None
        return str(item.value)

    def as_mapping(self) -> dict[str, Marked]:
        if not isinstance(self.value, dict):
            msg = f"expected a mapping at line {self.line}"
            raise TypeError(msg)
        return self.value

    def as_sequence(self) -> tuple[Marked, ...]:
        if not isinstance(self.value, tuple):
            msg = f"expected a sequence at line {self.line}"
            raise TypeError(msg)
        return self.value

    def as_text(self) -> str | None:
        return self.value if isinstance(self.value, str) else None


def _construct_scalar(node: ScalarNode) -> Any:
    tag = node.tag
    value = node.value
    if tag.endswith(":null"):
        return None
    if tag.endswith(":bool"):
        return value.strip().lower() in {"true", "yes", "on", "y", "1"}
    if tag.endswith(":int"):
        cleaned = value.replace("_", "")
        try:
            if len(cleaned) > 1 and cleaned.startswith("0") and cleaned[1:].isdigit():
                return int(cleaned, 8)
            return int(cleaned, 0)
        except ValueError:
            return value
    if tag.endswith(":float"):
        cleaned = value.replace("_", "")
        lowered = cleaned.lower()
        if lowered.endswith((".inf", "-.inf", ".nan")):
            return cleaned
        try:
            return float(cleaned)
        except ValueError:
            return value
    if tag.endswith(":binary"):
        return f"<binary {len(value)} bytes>"
    return value


_KEY_ALIASES = {True: "on", False: "off"}


class _Walker:
    def __init__(self, limits: Limits, rel_path: str) -> None:
        self._limits = limits
        self._rel_path = rel_path
        self.diagnostics: list[Diagnostic] = []
        self._nodes = 0
        self._occurrences: dict[int, int] = {}
        self._unknown_tag_reported = False

    def walk(self, node: Node, depth: int) -> Marked:
        self._nodes += 1
        if self._nodes > self._limits.max_yaml_nodes:
            self._fail("D-YAML-NODES", f"more than {self._limits.max_yaml_nodes} YAML nodes")
        if depth > self._limits.max_yaml_depth:
            self._fail("D-YAML-DEPTH", f"nesting deeper than {self._limits.max_yaml_depth} levels")
        occurrences = self._occurrences.get(id(node), 0) + 1
        self._occurrences[id(node)] = occurrences
        if occurrences > self._limits.alias_expansion_factor:
            self._fail(
                "D-YAML-ALIAS",
                f"alias expansion above the factor limit ({self._limits.alias_expansion_factor})",
            )
        line = node.start_mark.line + 1
        end_line = node.end_mark.line + 1
        if isinstance(node, ScalarNode):
            # PyYAML accepts escaped surrogates; reject them rather than collapse IDs
            # by replacing invalid characters during later UTF-8 serialization.
            try:
                node.value.encode("utf-8")
            except UnicodeEncodeError:
                self._fail("D-YAML-UNICODE", "invalid Unicode in YAML scalar", line=line)
            if not node.tag.startswith("tag:yaml.org,2002:") and not self._unknown_tag_reported:
                self._unknown_tag_reported = True
                self.diagnostics.append(
                    warning(
                        "D-YAML-TAG",
                        "unknown YAML tag treated as text",
                        file=self._rel_path,
                        line=line,
                    )
                )
            return Marked(_construct_scalar(node), line, end_line)
        if isinstance(node, SequenceNode):
            items = tuple(self.walk(item, depth + 1) for item in node.value)
            return Marked(items, line, end_line)
        if isinstance(node, MappingNode):
            result: dict[str, Marked] = {}
            key_lines: dict[str, int] = {}
            for key_node, value_node in node.value:
                key_marked = self.walk(key_node, depth + 1)
                raw_key = key_marked.value
                if isinstance(raw_key, bool):
                    key = _KEY_ALIASES.get(raw_key, str(raw_key))
                elif raw_key is None:
                    key = "null"
                else:
                    key = str(raw_key)
                if key in result:
                    self.diagnostics.append(
                        warning(
                            "D-YAML-DUPKEY",
                            "duplicate mapping key; the last value wins",
                            file=self._rel_path,
                            line=key_lines[key],
                        )
                    )
                else:
                    key_lines[key] = key_marked.line
                result[key] = self.walk(value_node, depth + 1)
            return Marked(result, line, end_line)
        self._fail("D-YAML-NODE", f"unsupported YAML node type {type(node).__name__}")
        msg = "unreachable after _fail"
        raise AssertionError(msg)

    def _fail(self, code: str, message: str, *, line: int | None = None) -> None:
        self.diagnostics.append(error(code, message, file=self._rel_path, line=line))
        raise _AbortWalkError


def load_marked_document(
    text: str, *, rel_path: str, limits: Limits
) -> tuple[Marked | None, tuple[Diagnostic, ...]]:
    """Compose the first YAML document into a Marked tree.

    Returns (None, diagnostics) when the document cannot be read safely. The parser
    never raises on hostile input.
    """
    try:
        documents = yaml.compose_all(text, Loader=yaml.SafeLoader)
        try:
            node = next(documents, None)
        finally:
            documents.close()
    except RecursionError:
        return None, (
            error("D-YAML-DEPTH", "YAML nesting exceeds the parser recursion limit", file=rel_path),
        )
    except (yaml.YAMLError, ValueError, OverflowError) as exc:
        mark = getattr(exc, "problem_mark", None)
        line = mark.line + 1 if mark is not None else None
        # Exception messages can echo arbitrary source text, including credentials.
        return None, (
            error("D-YAML-PARSE", "invalid YAML or Unicode escape", file=rel_path, line=line),
        )
    if node is None:
        return None, (error("D-YAML-EMPTY", "document is empty", file=rel_path),)
    walker = _Walker(limits, rel_path)
    try:
        marked = walker.walk(node, 0)
    except _AbortWalkError:
        return None, tuple(walker.diagnostics)
    except RecursionError:
        walker.diagnostics.append(
            error("D-YAML-DEPTH", "YAML nesting exceeds the walker recursion limit", file=rel_path)
        )
        return None, tuple(walker.diagnostics)
    return marked, tuple(walker.diagnostics)


def to_plain(value: Marked | None) -> Any:
    """Convert a Marked tree to plain Python values (dict/list/scalars)."""
    if value is None:
        return None
    raw = value.value
    if isinstance(raw, dict):
        return {key: to_plain(item) for key, item in raw.items()}
    if isinstance(raw, tuple):
        return [to_plain(item) for item in raw]
    return raw
