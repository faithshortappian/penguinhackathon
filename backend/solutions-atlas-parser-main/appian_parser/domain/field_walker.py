"""Shared utility for walking dotted field paths with list notation.

Supports paths like:
  - 'sail_code'                          → simple key
  - 'nodes[].form_expression'            → iterate list, access key
  - 'nodes[].gateway_conditions[].condition' → nested list iteration
  - 'nodes[].subprocess_config.input_mappings[].expression' → mixed
"""

from typing import Any, Callable


def walk_field_paths(data: dict[str, Any], path: str) -> list[str]:
    """Walk a dotted field path and collect all leaf string values.

    Args:
        data: Root dict to walk.
        path: Dotted path with [] for list iteration.

    Returns:
        List of string values found at the leaf positions.
    """
    results: list[str] = []
    _collect(data, path.split('.'), 0, results)
    return results


def apply_to_field_paths(
    data: dict[str, Any],
    path: str,
    resolver: Callable[[str], str],
) -> None:
    """Walk a dotted field path and apply resolver to leaf string values in place.

    Args:
        data: Root dict to walk (mutated in place).
        path: Dotted path with [] for list iteration.
        resolver: Function that transforms a string value.
    """
    _apply(data, path.split('.'), 0, resolver)


def _collect(node: Any, parts: list[str], idx: int, results: list[str]) -> None:
    if node is None or idx >= len(parts):
        return
    key = parts[idx]

    if key.endswith('[]'):
        key = key[:-2]
        items = node.get(key) if isinstance(node, dict) else None
        if isinstance(items, list):
            if idx == len(parts) - 1:
                results.extend(item for item in items if isinstance(item, str))
            else:
                for item in items:
                    _collect(item, parts, idx + 1, results)
    elif idx == len(parts) - 1:
        if isinstance(node, dict) and key in node and isinstance(node[key], str):
            results.append(node[key])
    else:
        if isinstance(node, dict):
            _collect(node.get(key), parts, idx + 1, results)


def _apply(node: Any, parts: list[str], idx: int, resolver: Callable[[str], str]) -> None:
    if node is None or idx >= len(parts):
        return
    key = parts[idx]

    if key.endswith('[]'):
        key = key[:-2]
        items = node.get(key) if isinstance(node, dict) else None
        if isinstance(items, list):
            if idx == len(parts) - 1:
                for i, item in enumerate(items):
                    if isinstance(item, str):
                        items[i] = resolver(item)
            else:
                for item in items:
                    _apply(item, parts, idx + 1, resolver)
    elif idx == len(parts) - 1:
        if isinstance(node, dict) and key in node and isinstance(node[key], str):
            node[key] = resolver(node[key])
    else:
        if isinstance(node, dict):
            _apply(node.get(key), parts, idx + 1, resolver)
