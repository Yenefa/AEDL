"""A small, strict JSON Schema subset evaluator (standard library only).

The sandbox policy kernel must not depend on third-party packages, but the
normalized policy document still needs one authoritative description. This
module evaluates the subset of JSON Schema 2020-12 used by
``sandbox_runtime/contracts/domain_policy_schema_v1.json``.

Design rule: an unsupported keyword is a hard ``PolicySchemaError`` rather than
a silently ignored annotation. A validator that ignores what it does not
understand cannot be trusted to fail closed.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any

from .errors import PolicySchemaError

SCHEMA_PATH = (
    Path(__file__).resolve().parents[3] / "contracts" / "domain_policy_schema_v1.json"
)

_ANNOTATIONS = frozenset(
    {
        "$schema",
        "$id",
        "$comment",
        "$defs",
        "defs",
        "title",
        "description",
        "default",
        "examples",
        "deprecated",
    }
)

_APPLICATORS = frozenset(
    {
        "$ref",
        "allOf",
        "anyOf",
        "oneOf",
        "not",
        "items",
        "additionalProperties",
        "properties",
    }
)

_ASSERTIONS = frozenset(
    {
        "type",
        "const",
        "enum",
        "required",
        "minItems",
        "maxItems",
        "uniqueItems",
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "minLength",
        "maxLength",
        "pattern",
    }
)

_SUPPORTED = _ANNOTATIONS | _APPLICATORS | _ASSERTIONS

_JSON_TYPES: dict[str, tuple[type, ...]] = {
    "object": (dict,),
    "array": (list,),
    "string": (str,),
    "boolean": (bool,),
    "null": (type(None),),
    "number": (int, float),
    "integer": (int,),
}


def load_schema(path: Path | None = None) -> dict[str, Any]:
    """Load the authoritative normalized policy document schema."""
    target = SCHEMA_PATH if path is None else path
    try:
        raw = target.read_text(encoding="utf-8")
    except OSError as exc:  # pragma: no cover - environment failure
        raise PolicySchemaError(f"cannot read policy schema at {target}: {exc}") from exc
    try:
        document = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise PolicySchemaError(f"policy schema at {target} is not valid JSON: {exc}") from exc
    if not isinstance(document, dict):
        raise PolicySchemaError("policy schema root must be an object")
    return document


def _resolve_pointer(ref: str, root: Mapping[str, Any], path: str) -> Any:
    if not ref.startswith("#/"):
        raise PolicySchemaError(f"only local $ref is supported: {ref!r}", path=path, keyword="$ref")
    node: Any = root
    for raw_token in ref[2:].split("/"):
        token = raw_token.replace("~1", "/").replace("~0", "~")
        if not isinstance(node, Mapping) or token not in node:
            raise PolicySchemaError(f"unresolvable $ref: {ref!r}", path=path, keyword="$ref")
        node = node[token]
    return node


def _type_matches(instance: Any, expected: str) -> bool:
    types = _JSON_TYPES.get(expected)
    if types is None:
        raise PolicySchemaError(f"unsupported type keyword value: {expected!r}")
    if expected in ("number", "integer") and isinstance(instance, bool):
        return False
    return isinstance(instance, types)


def _unique(values: Sequence[Any]) -> bool:
    seen: list[Any] = []
    for value in values:
        for candidate in seen:
            if type(candidate) is type(value) and candidate == value:
                return False
        seen.append(value)
    return True


def _iter_violations(
    instance: Any,
    schema: Mapping[str, Any],
    root: Mapping[str, Any],
    path: str,
) -> Iterator[str]:
    if not isinstance(schema, Mapping):
        raise PolicySchemaError("schema node must be an object", path=path)

    for keyword in schema:
        if keyword not in _SUPPORTED:
            raise PolicySchemaError(f"unsupported schema keyword {keyword!r}", path=path, keyword=keyword)

    if "$ref" in schema:
        yield from _iter_violations(
            instance, _resolve_pointer(schema["$ref"], root, path), root, path
        )
        return

    if "type" in schema:
        expected = schema["type"]
        options = (expected,) if isinstance(expected, str) else tuple(expected)
        if not any(_type_matches(instance, option) for option in options):
            rendered = "|".join(options)
            yield f"{path}: expected type {rendered}"
            return

    if "const" in schema and instance != schema["const"]:
        yield f"{path}: expected constant {schema['const']!r}"

    if "enum" in schema and instance not in schema["enum"]:
        yield f"{path}: value is not one of {schema['enum']!r}"

    if isinstance(instance, str):
        if "minLength" in schema and len(instance) < schema["minLength"]:
            yield f"{path}: shorter than minLength {schema['minLength']}"
        if "maxLength" in schema and len(instance) > schema["maxLength"]:
            yield f"{path}: longer than maxLength {schema['maxLength']}"
        if "pattern" in schema and re.search(schema["pattern"], instance) is None:
            yield f"{path}: does not match pattern {schema['pattern']!r}"

    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if "minimum" in schema and instance < schema["minimum"]:
            yield f"{path}: below minimum {schema['minimum']}"
        if "maximum" in schema and instance > schema["maximum"]:
            yield f"{path}: above maximum {schema['maximum']}"
        if "exclusiveMinimum" in schema and instance <= schema["exclusiveMinimum"]:
            yield f"{path}: not greater than exclusiveMinimum {schema['exclusiveMinimum']}"
        if "exclusiveMaximum" in schema and instance >= schema["exclusiveMaximum"]:
            yield f"{path}: not less than exclusiveMaximum {schema['exclusiveMaximum']}"

    if isinstance(instance, list):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            yield f"{path}: fewer than minItems {schema['minItems']}"
        if "maxItems" in schema and len(instance) > schema["maxItems"]:
            yield f"{path}: more than maxItems {schema['maxItems']}"
        if "uniqueItems" in schema and schema["uniqueItems"] and not _unique(instance):
            yield f"{path}: items are not unique"
        if "items" in schema:
            for index, item in enumerate(instance):
                yield from _iter_violations(item, schema["items"], root, f"{path}[{index}]")

    if isinstance(instance, Mapping):
        for name in schema.get("required", ()):
            if name not in instance:
                yield f"{path}: missing required property {name!r}"
        properties = schema.get("properties", {})
        for name, value in instance.items():
            child_path = f"{path}.{name}"
            if name in properties:
                yield from _iter_violations(value, properties[name], root, child_path)
                continue
            additional = schema.get("additionalProperties")
            if additional is False:
                yield f"{child_path}: additional property is not allowed"
            elif isinstance(additional, Mapping):
                yield from _iter_violations(value, additional, root, child_path)

    for keyword in ("allOf", "anyOf", "oneOf"):
        if keyword not in schema:
            continue
        branches = schema[keyword]
        results = [
            list(_iter_violations(instance, branch, root, f"{path}/{keyword}[{index}]"))
            for index, branch in enumerate(branches)
        ]
        if keyword == "allOf":
            for violations in results:
                yield from violations
        elif keyword == "anyOf":
            if all(violations for violations in results):
                yield f"{path}: does not match any allowed alternative"
        elif sum(1 for violations in results if not violations) != 1:
            yield f"{path}: must match exactly one allowed alternative"

    if "not" in schema:
        if not list(_iter_violations(instance, schema["not"], root, f"{path}/not")):
            yield f"{path}: matches a forbidden shape"


def iter_violations(instance: Any, schema: Mapping[str, Any]) -> tuple[str, ...]:
    """Return a deterministic, de-duplicated tuple of schema violations."""
    found = _iter_violations(instance, schema, schema, "$")
    return tuple(sorted(set(found)))


__all__ = ["SCHEMA_PATH", "iter_violations", "load_schema"]
