"""Local, string-aware bracket-balance check for SAIL expressions.

Mirrors the frontend's Tokenizer-based paren/bracket/brace matcher
(frontend/parser/tokenizer.js + panel.js's computeBracketRepairPlan), but
runs server-side on AI-generated code before it's ever handed back to the
user — catching structural mistakes (an unclosed `{` from a truncated
a!richTextItem list, a stray `)`) without needing a live Appian
connection at all. This is a syntax check only; it says nothing about
whether a referenced function/component actually exists — that's what
the Docs MCP check (see ai_routes.py's _validate_with_docs_mcp) is for.
"""

import re

OPENERS = {"(": ")", "{": "}", "[": "]"}
CLOSERS = {")": "(", "}": "{", "]": "["}


def check_balanced_brackets(code: str) -> list[str]:
    """Return human-readable diagnostics for unbalanced (), {}, [] in code.

    Skips brackets inside string literals ("...", with "" as the SAIL
    escape for a literal quote) and /* */ comments, so it won't false-
    positive on a paren typed inside a text value.
    """
    diagnostics: list[str] = []
    stack: list[tuple[str, int]] = []
    in_string = False
    i = 0
    n = len(code)

    def line_of(index: int) -> int:
        return code.count("\n", 0, index) + 1

    while i < n:
        ch = code[i]

        if in_string:
            if ch == '"':
                if i + 1 < n and code[i + 1] == '"':
                    i += 2
                    continue
                in_string = False
            i += 1
            continue

        if ch == '"':
            in_string = True
            i += 1
            continue

        if ch == "/" and i + 1 < n and code[i + 1] == "*":
            end = code.find("*/", i + 2)
            i = end + 2 if end != -1 else n
            continue

        if ch in OPENERS:
            stack.append((ch, i))
        elif ch in CLOSERS:
            if stack and stack[-1][0] == CLOSERS[ch]:
                stack.pop()
            else:
                diagnostics.append(
                    f'Unmatched closing "{ch}" at line {line_of(i)} — no matching "{CLOSERS[ch]}" open.'
                )

        i += 1

    for opener, idx in stack:
        diagnostics.append(
            f'Unclosed "{opener}" opened at line {line_of(idx)} — missing "{OPENERS[opener]}".'
        )

    return diagnostics


# ─── Known deprecated/renamed SAIL parameter values ──────────────
#
# Appian has renamed a handful of component enum values across releases,
# and separately the model tends to substitute generic web-design
# vocabulary for Appian's actual enum spelling even when it's never been
# valid at all (e.g. padding: "MEDIUM" instead of "STANDARD" — Appian's
# spacing scale was never named after t-shirt sizes). Both are the same
# failure mode from this codebase's point of view: a value the model was
# confident about that Appian's engine will reject. The AI can still emit
# these from stale/generic training data even with docs grounding in
# place (see ai_routes.py's per-component doc lookups), so this is a
# deterministic, no-network backstop for the ones we know about. Keyed by
# (parameter name, value) -> current/correct value.
DEPRECATED_VALUE_RENAMES = {
    ("style", "PRIMARY"): "SOLID",      # a!buttonWidget / a!buttonArrayLayout style
    ("style", "SECONDARY"): "OUTLINE",  # a!buttonWidget / a!buttonArrayLayout style
}

# Appian's standard spacing scale (NONE/EVEN_LESS/LESS/STANDARD/MORE/
# EVEN_MORE) is shared by padding, marginAbove, and marginBelow across
# layout components (a!cardLayout, a!columnsLayout, a!sideBySideLayout,
# etc.). The model frequently reaches for generic small/medium/large
# sizing words here instead, so map that whole vocabulary onto the real
# scale for every parameter that uses it.
_SPACING_SIZE_WORDS = {
    "EXTRA_SMALL": "EVEN_LESS",
    "SMALL": "LESS",
    "MEDIUM": "STANDARD",
    "LARGE": "MORE",
    "EXTRA_LARGE": "EVEN_MORE",
}
for _param in ("padding", "marginAbove", "marginBelow"):
    for _generic, _correct in _SPACING_SIZE_WORDS.items():
        DEPRECATED_VALUE_RENAMES[(_param, _generic)] = _correct
del _param, _generic, _correct

_PARAM_VALUE_RE = re.compile(r'(\w+)\s*:\s*"([A-Z_]+)"')


def fix_deprecated_values(code: str) -> tuple[str, list[str]]:
    """Auto-correct known-renamed SAIL parameter values (e.g. style: "PRIMARY"
    -> style: "SOLID") and report what was changed.

    Returns (fixed_code, notes). Fixing rather than just flagging means the
    user never has to notice-and-manually-edit these — the corrected value
    is what actually lands in the editor. This is a narrow, hardcoded list —
    it only catches renames we've confirmed, not every possible stale enum
    value. It complements, not replaces, the docs-grounded generation and
    Docs MCP validation.
    """
    notes: list[str] = []

    def _replace(match: re.Match) -> str:
        param, value = match.group(1), match.group(2)
        current = DEPRECATED_VALUE_RENAMES.get((param, value))
        if not current:
            return match.group(0)
        line = code.count("\n", 0, match.start()) + 1
        notes.append(
            f'Auto-fixed deprecated value at line {line}: {param}: "{value}" -> {param}: "{current}".'
        )
        return f'{param}: "{current}"'

    fixed_code = _PARAM_VALUE_RE.sub(_replace, code)
    return fixed_code, notes
