"""TypeScript/React code smell detection.

Defines TS-specific smell rules and multi-line smell helpers (brace-tracked).
"""

import re
from pathlib import Path

from ....utils import PROJECT_ROOT, find_ts_files
from ._smell_helpers import (
    _ts_match_is_in_string,
    _detect_async_no_await,
    _detect_error_no_throw,
    _detect_empty_if_chains,
    _detect_dead_useeffects,
    _detect_swallowed_errors,
    _detect_monster_functions,
    _detect_dead_functions,
    _detect_window_globals,
    _detect_catch_return_default,
)


TS_SMELL_CHECKS = [
    {
        "id": "empty_catch",
        "label": "Empty catch blocks",
        "pattern": r"catch\s*\([^)]*\)\s*\{\s*\}",
        "severity": "high",
    },
    {
        "id": "any_type",
        "label": "Explicit `any` types",
        "pattern": r":\s*any\b",
        "severity": "medium",
    },
    {
        "id": "ts_ignore",
        "label": "@ts-ignore / @ts-expect-error",
        "pattern": r"@ts-(?:ignore|expect-error)",
        "severity": "medium",
    },
    {
        "id": "ts_nocheck",
        "label": "@ts-nocheck disables all type checking",
        "pattern": r"^\s*//\s*@ts-nocheck",
        "severity": "high",
    },
    {
        "id": "non_null_assert",
        "label": "Non-null assertions (!.)",
        "pattern": r"\w+!\.",
        "severity": "low",
    },
    {
        "id": "hardcoded_color",
        "label": "Hardcoded color values",
        "pattern": r"""(?:color|background|border|fill|stroke)\s*[:=]\s*['"]#[0-9a-fA-F]{3,8}['"]""",
        "severity": "medium",
    },
    {
        "id": "hardcoded_rgb",
        "label": "Hardcoded rgb/rgba",
        "pattern": r"rgba?\(\s*\d+",
        "severity": "medium",
    },
    {
        "id": "async_no_await",
        "label": "Async functions without await",
        "pattern": None,  # multi-line analysis
        "severity": "medium",
    },
    {
        "id": "magic_number",
        "label": "Magic numbers (>1000 in logic)",
        "pattern": r"(?:===?|!==?|>=?|<=?|[+\-*/])\s*\d{4,}",
        "severity": "low",
    },
    {
        "id": "console_error_no_throw",
        "label": "console.error without throw/return",
        "pattern": None,  # multi-line analysis
        "severity": "medium",
    },
    {
        "id": "empty_if_chain",
        "label": "Empty if/else chains",
        "pattern": None,  # multi-line analysis
        "severity": "high",
    },
    {
        "id": "dead_useeffect",
        "label": "useEffect with empty body",
        "pattern": None,  # multi-line analysis
        "severity": "high",
    },
    {
        "id": "swallowed_error",
        "label": "Catch blocks that only log (swallowed errors)",
        "pattern": None,  # multi-line analysis
        "severity": "medium",
    },
    {
        "id": "hardcoded_url",
        "label": "Hardcoded URL in source code",
        "pattern": r"""(?:['\"])https?://[^\s'\"]+(?:['\"])""",
        "severity": "medium",
    },
    {
        "id": "todo_fixme",
        "label": "TODO/FIXME/HACK comments",
        "pattern": r"//\s*(?:TODO|FIXME|HACK|XXX)",
        "severity": "low",
    },
    {
        "id": "debug_tag",
        "label": "Vestigial debug tag in log/print",
        "pattern": r"""(?:['"`])\[([A-Z][A-Z0-9_]{2,})\]\s""",
        "severity": "low",
    },
    {
        "id": "monster_function",
        "label": "Monster function (>150 LOC)",
        # Detected via brace-tracking
        "pattern": None,
        "severity": "high",
    },
    {
        "id": "dead_function",
        "label": "Dead function (body is empty/return-only)",
        # Detected via brace-tracking
        "pattern": None,
        "severity": "medium",
    },
    {
        "id": "voided_symbol",
        "label": "Dead internal code (void-suppressed unused symbol)",
        "pattern": r"^\s*void\s+[a-zA-Z_]\w*\s*;?\s*$",
        "severity": "medium",
    },
    {
        "id": "window_global",
        "label": "Window global escape hatch (window.__*)",
        "pattern": None,  # multi-line analysis — regex needs alternation
        "severity": "medium",
    },
    {
        "id": "workaround_tag",
        "label": "Workaround tag in comment ([PascalCaseTag])",
        "pattern": r"//.*\[([A-Z][a-z]+(?:[A-Z][a-z]+)+)\]",
        "severity": "low",
    },
    {
        "id": "catch_return_default",
        "label": "Catch block returns default object (silent failure)",
        "pattern": None,  # multi-line brace-tracked
        "severity": "high",
    },
]


def _build_ts_line_state(lines: list[str]) -> dict[int, str]:
    """Build a map of line numbers that are inside block comments or template literals.

    Returns {0-indexed line: reason} where reason is "block_comment" or "template_literal".
    Lines not in the map are normal code lines suitable for regex checks.

    Tracks:
    - Block comment state (opened by /*, closed by */)
    - Template literal state (opened by backtick, closed by backtick,
      with ${} nesting awareness)
    """
    state: dict[int, str] = {}
    in_block_comment = False
    in_template = False
    template_brace_depth = 0  # tracks ${} nesting inside template literals

    for i, line in enumerate(lines):
        if in_block_comment:
            state[i] = "block_comment"
            if "*/" in line:
                in_block_comment = False
            continue

        if in_template:
            state[i] = "template_literal"
            # Scan for closing backtick or ${} nesting
            j = 0
            while j < len(line):
                ch = line[j]
                if ch == "\\" and j + 1 < len(line):
                    j += 2
                    continue
                if ch == "$" and j + 1 < len(line) and line[j + 1] == "{":
                    template_brace_depth += 1
                    j += 2
                    continue
                if ch == "}" and template_brace_depth > 0:
                    template_brace_depth -= 1
                    j += 1
                    continue
                if ch == "`" and template_brace_depth == 0:
                    in_template = False
                    # Rest of line is normal code — don't mark it
                    # but we already marked the line; that's fine for
                    # line-level filtering
                    break
                j += 1
            continue

        # Normal code line — check for block comment or template literal start
        j = 0
        in_str = None
        while j < len(line):
            ch = line[j]

            # Skip escape sequences
            if in_str and ch == "\\" and j + 1 < len(line):
                j += 2
                continue

            # String tracking
            if in_str:
                if ch == in_str:
                    in_str = None
                j += 1
                continue

            # Line comment — rest is not code
            if ch == "/" and j + 1 < len(line) and line[j + 1] == "/":
                break

            # Block comment start
            if ch == "/" and j + 1 < len(line) and line[j + 1] == "*":
                # Check if it closes on same line
                close = line.find("*/", j + 2)
                if close != -1:
                    j = close + 2
                    continue
                else:
                    in_block_comment = True
                    break

            # Template literal start
            if ch == "`":
                # Scan for closing backtick on same line
                k = j + 1
                found_close = False
                depth = 0
                while k < len(line):
                    c = line[k]
                    if c == "\\" and k + 1 < len(line):
                        k += 2
                        continue
                    if c == "$" and k + 1 < len(line) and line[k + 1] == "{":
                        depth += 1
                        k += 2
                        continue
                    if c == "}" and depth > 0:
                        depth -= 1
                        k += 1
                        continue
                    if c == "`" and depth == 0:
                        found_close = True
                        j = k + 1
                        break
                    k += 1
                if found_close:
                    continue
                else:
                    in_template = True
                    template_brace_depth = depth
                    break

            if ch in ("'", '"'):
                in_str = ch
                j += 1
                continue

            j += 1

    return state


def detect_smells(path: Path) -> tuple[list[dict], int]:
    """Detect TypeScript/React code smell patterns across the codebase.

    Returns (entries, total_files_checked).
    """
    checks = TS_SMELL_CHECKS
    smell_counts: dict[str, list[dict]] = {s["id"]: [] for s in checks}
    files = find_ts_files(path)

    for filepath in files:
        if "node_modules" in filepath or ".d.ts" in filepath:
            continue
        try:
            p = Path(filepath) if Path(filepath).is_absolute() else PROJECT_ROOT / filepath
            content = p.read_text()
            lines = content.splitlines()
        except (OSError, UnicodeDecodeError):
            continue

        # Build line state for string/comment filtering
        line_state = _build_ts_line_state(lines)

        # Regex-based smells
        for check in checks:
            if check["pattern"] is None:
                continue
            for i, line in enumerate(lines):
                # Skip lines inside block comments or template literals
                if i in line_state:
                    continue
                m = re.search(check["pattern"], line)
                if not m:
                    continue
                # Check if match is inside a single-line string or comment
                if _ts_match_is_in_string(line, m.start()):
                    continue
                # Skip URLs assigned to module-level constants
                if check["id"] == "hardcoded_url" and re.match(
                    r"^(?:export\s+)?(?:const|let|var)\s+[A-Z_][A-Z0-9_]*\s*=", line.strip()
                ):
                    continue
                smell_counts[check["id"]].append({
                    "file": filepath,
                    "line": i + 1,
                    "content": line.strip()[:100],
                })

        # Multi-line smell helpers (brace-tracked)
        _detect_async_no_await(filepath, content, lines, smell_counts)
        _detect_error_no_throw(filepath, lines, smell_counts)
        _detect_empty_if_chains(filepath, lines, smell_counts)
        _detect_dead_useeffects(filepath, lines, smell_counts)
        _detect_swallowed_errors(filepath, content, lines, smell_counts)
        _detect_monster_functions(filepath, lines, smell_counts)
        _detect_dead_functions(filepath, lines, smell_counts)
        _detect_window_globals(filepath, lines, line_state, smell_counts)
        _detect_catch_return_default(filepath, content, smell_counts)

    # Build summary entries sorted by severity then count
    severity_order = {"high": 0, "medium": 1, "low": 2}
    entries = []
    for check in checks:
        matches = smell_counts[check["id"]]
        if matches:
            entries.append({
                "id": check["id"],
                "label": check["label"],
                "severity": check["severity"],
                "count": len(matches),
                "files": len(set(m["file"] for m in matches)),
                "matches": matches[:50],
            })
    entries.sort(key=lambda e: (severity_order.get(e["severity"], 9), -e["count"]))
    return entries, len(files)
