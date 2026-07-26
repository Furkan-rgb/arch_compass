"""Generate dependency-free TypeScript declarations from the FastAPI contract."""

from __future__ import annotations

import argparse
import json
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from archcompass.bootstrap import initialize_workspace
from archcompass.presentation.web import create_app

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "frontend" / "src" / "openapi.generated.ts"
HTTP_METHODS = ("get", "post", "put", "patch", "delete", "options", "head", "trace")


def _object(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): item for key, item in cast(Mapping[object, Any], value).items()}


def _schema_type(schema_value: object) -> str:
    schema = _object(schema_value)
    reference = schema.get("$ref")
    if isinstance(reference, str):
        return f'components["schemas"][{json.dumps(reference.rsplit("/", 1)[-1])}]'

    if "const" in schema:
        return json.dumps(schema["const"], ensure_ascii=False)
    enum = schema.get("enum")
    if isinstance(enum, list):
        return " | ".join(json.dumps(item, ensure_ascii=False) for item in enum)

    for keyword, separator in (("allOf", " & "), ("oneOf", " | "), ("anyOf", " | ")):
        branches = schema.get(keyword)
        if isinstance(branches, list):
            rendered = [_schema_type(branch) for branch in branches]
            return separator.join(dict.fromkeys(rendered))

    schema_type = schema.get("type")
    if isinstance(schema_type, list):
        return " | ".join(
            _schema_type({**schema, "type": item}) for item in schema_type
        )
    if schema_type == "array":
        item_type = _schema_type(schema.get("items", {}))
        return f"Array<{item_type}>"
    if schema_type == "object" or "properties" in schema or "additionalProperties" in schema:
        properties = _object(schema.get("properties", {}))
        required = {
            str(item)
            for item in schema.get("required", [])
            if isinstance(item, str)
        }
        fields = [
            f"    {json.dumps(name)}{'?' if name not in required else ''}: "
            f"{_schema_type(value)};"
            for name, value in properties.items()
        ]
        additional = schema.get("additionalProperties")
        if additional is True:
            fields.append("    [key: string]: unknown;")
        elif isinstance(additional, Mapping):
            fields.append(f"    [key: string]: {_schema_type(additional)};")
        if not fields:
            return "Record<string, unknown>"
        return "{\n" + "\n".join(fields) + "\n  }"
    if schema_type == "string":
        return "string"
    if schema_type in {"integer", "number"}:
        return "number"
    if schema_type == "boolean":
        return "boolean"
    if schema_type == "null":
        return "null"
    return "unknown"


def _parameter_groups(operation: dict[str, Any]) -> str:
    grouped: dict[str, list[str]] = {
        "query": [],
        "path": [],
        "header": [],
        "cookie": [],
    }
    for parameter_value in operation.get("parameters", []):
        parameter = _object(parameter_value)
        location = str(parameter.get("in", "query"))
        if location not in grouped:
            continue
        name = str(parameter.get("name", "value"))
        optional = "" if parameter.get("required") is True else "?"
        grouped[location].append(
            f"      {json.dumps(name)}{optional}: "
            f"{_schema_type(parameter.get('schema', {}))};"
        )
    lines = ["    parameters: {"]
    for location, fields in grouped.items():
        if fields:
            lines.append(f"      {location}: {{")
            lines.extend(fields)
            lines.append("      };")
        else:
            lines.append(f"      {location}: never;")
    lines.append("    };")
    return "\n".join(lines)


def _content_type(content_value: object) -> str:
    content = _object(content_value)
    preferred = (
        "application/json",
        "text/event-stream",
        "text/plain",
        "text/markdown",
    )
    for media_type in preferred:
        media = _object(content.get(media_type, {}))
        if media:
            return _schema_type(media.get("schema", {}))
    if content:
        media = _object(next(iter(content.values())))
        return _schema_type(media.get("schema", {}))
    return "unknown"


def _request_body(operation: dict[str, Any]) -> str:
    request_body = _object(operation.get("requestBody", {}))
    if not request_body:
        return "    requestBody?: never;"
    optional = "" if request_body.get("required") is True else "?"
    return (
        f"    requestBody{optional}: "
        f"{_content_type(request_body.get('content', {}))};"
    )


def _responses(operation: dict[str, Any]) -> str:
    lines = ["    responses: {"]
    for status, response_value in _object(operation.get("responses", {})).items():
        response = _object(response_value)
        lines.append(
            f"      {json.dumps(status)}: {_content_type(response.get('content', {}))};"
        )
    lines.append("    };")
    return "\n".join(lines)


def render(schema_value: object) -> str:
    schema = _object(schema_value)
    components = _object(schema.get("components", {}))
    schemas = _object(components.get("schemas", {}))
    paths = _object(schema.get("paths", {}))
    operations: dict[str, dict[str, Any]] = {}

    output = [
        "/* eslint-disable */",
        "/**",
        " * Generated by scripts/generate_openapi_types.py from FastAPI's OpenAPI schema.",
        " * Do not edit this file directly.",
        " */",
        "",
        "export interface components {",
        "  schemas: {",
    ]
    for name in sorted(schemas):
        output.append(f"    {json.dumps(name)}: {_schema_type(schemas[name])};")
    output.extend(["  };", "}", "", "export interface operations {"])

    for path in sorted(paths):
        path_item = _object(paths[path])
        for method in HTTP_METHODS:
            operation = _object(path_item.get(method, {}))
            if not operation:
                continue
            operation_id = str(operation.get("operationId", f"{method}_{path}"))
            operations[operation_id] = operation
    for operation_id in sorted(operations):
        operation = operations[operation_id]
        output.extend(
            [
                f"  {json.dumps(operation_id)}: {{",
                _parameter_groups(operation),
                _request_body(operation),
                _responses(operation),
                "  };",
            ]
        )
    output.extend(["}", "", "export interface paths {"])
    for path in sorted(paths):
        path_item = _object(paths[path])
        output.append(f"  {json.dumps(path)}: {{")
        for method in HTTP_METHODS:
            operation = _object(path_item.get(method, {}))
            if not operation:
                continue
            operation_id = str(operation.get("operationId", f"{method}_{path}"))
            output.append(
                f"    {method}: operations[{json.dumps(operation_id)}];"
            )
        output.append("  };")
    output.extend(["}", ""])
    return "\n".join(output)


def generate() -> str:
    with tempfile.TemporaryDirectory(prefix="archcompass-openapi-") as temporary:
        initialized = initialize_workspace(Path(temporary))
        return render(create_app(initialized.runtime).openapi())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail when the committed declarations differ from the API contract.",
    )
    arguments = parser.parse_args()
    generated = generate()
    if arguments.check:
        if not OUTPUT.is_file() or OUTPUT.read_text(encoding="utf-8") != generated:
            print(
                "Generated API types are stale. "
                "Run `make api-types` and commit the result."
            )
            return 1
        return 0
    OUTPUT.write_text(generated, encoding="utf-8")
    print(f"Generated {OUTPUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
