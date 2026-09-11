from __future__ import annotations

import json
from typing import Any


def text_report(data: dict[str, Any]) -> str:
    target = data.get("target", {})
    lines = [f"X-RAY · {target.get('display_name', 'Unknown')}", f"TYPE  {str(target.get('type', '')).upper()}", ""]

    def emit(value: Any, depth: int = 0, limit: int = 80) -> None:
        indent = "  " * depth
        if isinstance(value, dict):
            for index, (key, child) in enumerate(value.items()):
                if index >= limit:
                    lines.append(f"{indent}… truncated")
                    break
                if isinstance(child, (dict, list)):
                    lines.append(f"{indent}{key.replace('_', ' ').upper()}")
                    emit(child, depth + 1, limit)
                else:
                    lines.append(f"{indent}{key.replace('_', ' ')}: {child}")
        elif isinstance(value, list):
            for index, child in enumerate(value[:limit]):
                if isinstance(child, (dict, list)):
                    lines.append(f"{indent}[{index + 1}]")
                    emit(child, depth + 1, limit)
                else:
                    lines.append(f"{indent}{child}")
            if len(value) > limit:
                lines.append(f"{indent}… {len(value) - limit} more")
        else:
            lines.append(f"{indent}{value}")

    emit(data.get("sections", {}))
    if data.get("warnings"):
        lines.extend(["", "WARNINGS", *[f"! {warning}" for warning in data["warnings"]]])
    return "\n".join(lines)


def json_report(data: dict[str, Any]) -> str:
    return json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False)
