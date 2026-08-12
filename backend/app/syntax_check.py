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
