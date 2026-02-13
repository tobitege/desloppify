"""React anti-pattern detection: useState+useEffect state sync."""

import json
import re
from pathlib import Path

from ....utils import PROJECT_ROOT, c, find_tsx_files, print_table, rel

MAX_EFFECT_BODY = 1000  # max characters to scan for brace-matching a useEffect callback
MAX_FUNC_SCAN = 2000    # max lines to scan for function body extent


def detect_state_sync(path: Path) -> tuple[list[dict], int]:
    """Find useEffect blocks whose only statements are setState calls.

    This pattern causes an unnecessary extra render cycle — the derived value
    is stale for one frame. Common variants:
    - "Derived state": should be useMemo or inline computation
    - "Reset on change": should use key prop or restructure

    Returns one entry per occurrence with setter names and line number.
    """
    entries = []
    total_effects = 0

    for filepath in find_tsx_files(path):
        try:
            p = Path(filepath) if Path(filepath).is_absolute() else PROJECT_ROOT / filepath
            content = p.read_text()
            lines = content.splitlines()
        except (OSError, UnicodeDecodeError):
            continue

        # Collect all useState setters in this file
        setters = set()
        for m in re.finditer(r"const\s+\[\w+,\s*(set\w+)\]\s*=\s*useState", content):
            setters.add(m.group(1))

        if not setters:
            continue

        # Count all useEffect calls (potential) and find matching blocks
        total_effects += len(re.findall(r"useEffect\s*\(", content))
        effect_re = re.compile(r"useEffect\s*\(\s*\(\s*\)\s*=>\s*\{")
        for m in effect_re.finditer(content):
            # Extract the callback body using brace tracking
            brace_start = m.end() - 1  # the {
            depth = 0
            in_str = None
            prev_ch = ""
            body_end = None
            for ci in range(brace_start, min(brace_start + MAX_EFFECT_BODY, len(content))):
                ch = content[ci]
                if in_str:
                    if ch == in_str and prev_ch != "\\":
                        in_str = None
                    prev_ch = ch
                    continue
                if ch in "'\"`":
                    in_str = ch
                elif ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        body_end = ci
                        break
                prev_ch = ch

            if body_end is None:
                continue

            body = content[brace_start + 1:body_end]
            # Strip comments
            body_clean = re.sub(r"//[^\n]*", "", body)
            body_clean = re.sub(r"/\*.*?\*/", "", body_clean, flags=re.DOTALL)
            body_clean = body_clean.strip()

            if not body_clean:
                continue  # empty effect — caught by dead_useeffect

            # Split into statements
            statements = [s.strip().rstrip(";") for s in re.split(r"[;\n]", body_clean) if s.strip()]
            if not statements:
                continue

            # Check if ALL statements are setter calls from this component's useState
            matched_setters = set()
            all_setters = True
            for stmt in statements:
                found = False
                for setter in setters:
                    if stmt.startswith(setter + "("):
                        found = True
                        matched_setters.add(setter)
                        break
                if not found:
                    all_setters = False
                    break

            if all_setters and matched_setters:
                line_no = content[:m.start()].count("\n") + 1
                entries.append({
                    "file": filepath,
                    "line": line_no,
                    "setters": sorted(matched_setters),
                    "content": lines[line_no - 1].strip()[:100] if line_no <= len(lines) else "",
                })

    return entries, total_effects


def detect_context_nesting(path: Path) -> tuple[list[dict], int]:
    """Find deeply nested React Context provider trees (>5 levels in one file).

    Counts opening <*Provider> tags and tracks nesting depth via matching
    closing tags. Flags files where the max provider depth exceeds 5.
    """
    entries = []
    total_files = 0
    provider_open = re.compile(r"<(\w+Provider)\b(?!.*/>)")  # opening, not self-closing
    provider_close = re.compile(r"</(\w+Provider)\s*>")

    for filepath in find_tsx_files(path):
        total_files += 1
        try:
            p = Path(filepath) if Path(filepath).is_absolute() else PROJECT_ROOT / filepath
            content = p.read_text()
            lines = content.splitlines()
        except (OSError, UnicodeDecodeError):
            continue

        depth = 0
        max_depth = 0
        providers_at_max: list[str] = []
        provider_stack: list[str] = []

        for line in lines:
            # Count closing tags first (handles </Provider> on same line as next open)
            for m in provider_close.finditer(line):
                if provider_stack and provider_stack[-1] == m.group(1):
                    provider_stack.pop()
                    depth -= 1

            # Count opening tags (non-self-closing)
            for m in provider_open.finditer(line):
                depth += 1
                provider_stack.append(m.group(1))
                if depth > max_depth:
                    max_depth = depth
                    providers_at_max = list(provider_stack)

        if max_depth > 5:
            entries.append({
                "file": filepath,
                "depth": max_depth,
                "providers": providers_at_max,
            })

    return sorted(entries, key=lambda e: -e["depth"]), total_files


def detect_hook_return_bloat(path: Path) -> tuple[list[dict], int]:
    """Find custom hooks returning objects with too many fields (>12).

    Scans for exported functions named use* and counts the top-level
    properties in their return object literal.
    """
    entries = []
    total_hooks = 0
    hook_re = re.compile(
        r"(?:export\s+)?(?:function|const)\s+(use[A-Z]\w*)"
    )

    for filepath in find_tsx_files(path):
        try:
            p = Path(filepath) if Path(filepath).is_absolute() else PROJECT_ROOT / filepath
            content = p.read_text()
            lines = content.splitlines()
        except (OSError, UnicodeDecodeError):
            continue

        # Also check .ts files with use* names
        for m in hook_re.finditer(content):
            hook_name = m.group(1)
            total_hooks += 1
            hook_start = content[:m.start()].count("\n")

            # Find the function body by tracking braces from the opening {
            brace_line = None
            for k in range(hook_start, min(hook_start + 5, len(lines))):
                if "{" in lines[k]:
                    brace_line = k
                    break
            if brace_line is None:
                continue

            # Find end of function
            depth = 0
            found_open = False
            func_end = None
            for j in range(brace_line, min(brace_line + MAX_FUNC_SCAN, len(lines))):
                in_str = None
                prev_ch = ""
                for ch in lines[j]:
                    if in_str:
                        if ch == in_str and prev_ch != "\\":
                            in_str = None
                        prev_ch = ch
                        continue
                    if ch in "'\"`":
                        in_str = ch
                    elif ch == "{":
                        depth += 1
                        found_open = True
                    elif ch == "}":
                        depth -= 1
                        if found_open and depth == 0:
                            func_end = j
                            break
                    prev_ch = ch
                if func_end is not None:
                    break

            if func_end is None:
                continue

            # Find the last top-level return statement with an object literal
            # Scan backwards from function end for "return {"
            func_body = "\n".join(lines[brace_line:func_end + 1])
            field_count = _count_return_fields(func_body)
            if field_count is not None and field_count > 12:
                entries.append({
                    "file": filepath,
                    "line": hook_start + 1,
                    "hook": hook_name,
                    "field_count": field_count,
                })

    return sorted(entries, key=lambda e: -e["field_count"]), total_hooks


def _count_return_fields(func_body: str) -> int | None:
    """Count fields in the last return { ... } object in a function body.

    Finds the last `return {` at depth 1 (top-level of function) and counts
    comma-separated fields at depth 1 within that object.
    """
    # Find all "return" positions at depth 1
    lines = func_body.splitlines()
    depth = 0
    return_positions: list[int] = []

    for i, line in enumerate(lines):
        in_str = None
        prev_ch = ""
        for ci, ch in enumerate(line):
            if in_str:
                if ch == in_str and prev_ch != "\\":
                    in_str = None
                prev_ch = ch
                continue
            if ch in "'\"`":
                in_str = ch
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
            prev_ch = ch

        # depth == 1 means we're at the function body level
        stripped = line.strip()
        if depth == 1 and stripped.startswith("return") and "{" in stripped:
            return_positions.append(i)

    if not return_positions:
        return None

    # Take the last return statement
    return_line = return_positions[-1]

    # Count fields in the returned object — track braces from the return {
    ret_text = "\n".join(lines[return_line:])
    brace_start = ret_text.find("{")
    if brace_start == -1:
        return None

    obj_depth = 0
    field_count = 0
    in_str = None
    prev_ch = ""
    started = False

    for ch in ret_text[brace_start:]:
        if in_str:
            if ch == in_str and prev_ch != "\\":
                in_str = None
            prev_ch = ch
            continue
        if ch in "'\"`":
            in_str = ch
        elif ch == "{":
            obj_depth += 1
            started = True
        elif ch == "}":
            obj_depth -= 1
            if started and obj_depth == 0:
                break
        elif ch == "," and obj_depth == 1:
            field_count += 1
        elif ch not in " \t\n" and obj_depth == 1 and not started:
            pass
        prev_ch = ch

    # field_count counts commas; fields = commas + 1 (if any content)
    if field_count > 0:
        field_count += 1
    else:
        # Check if there's any content at all (single field, no comma)
        obj_content = ""
        d = 0
        for ch in ret_text[brace_start:]:
            if ch == "{":
                d += 1
            elif ch == "}":
                d -= 1
                if d == 0:
                    break
            elif d == 1:
                obj_content += ch
        if obj_content.strip():
            field_count = 1

    return field_count


def cmd_react(args):
    """Show React anti-patterns (state sync via useEffect)."""
    entries, _ = detect_state_sync(Path(args.path))

    if args.json:
        print(json.dumps({"count": len(entries), "entries": [
            {"file": rel(e["file"]), "line": e["line"],
             "setters": e["setters"]}
            for e in entries
        ]}, indent=2))
        return

    if not entries:
        print(c("\nNo state sync anti-patterns found.", "green"))
        return

    print(c(f"\nState sync anti-patterns (useEffect only calls setters): "
            f"{len(entries)}\n", "bold"))

    rows = []
    for e in entries[:args.top]:
        rows.append([
            rel(e["file"]),
            str(e["line"]),
            ", ".join(e["setters"]),
        ])
    print_table(["File", "Line", "Setters"], rows, [60, 6, 40])
    print()
