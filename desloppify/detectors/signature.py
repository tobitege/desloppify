"""Signature variance detection — same function name, different signatures across modules."""

from __future__ import annotations

from collections import defaultdict

from .base import FunctionInfo


# Names that are legitimately polymorphic — skip them
_ALLOWLIST = {
    "__init__", "__repr__", "__str__", "__eq__", "__hash__", "__lt__",
    "__le__", "__gt__", "__ge__", "__len__", "__iter__", "__next__",
    "__enter__", "__exit__", "__call__", "__getattr__", "__setattr__",
    "__getitem__", "__setitem__", "__delitem__", "__contains__",
    "main", "setup", "teardown", "configure", "run", "handle",
    "setUp", "tearDown", "setUpClass", "tearDownClass",
    "get", "post", "put", "delete", "patch",  # HTTP methods
}


def detect_signature_variance(
    functions: list[FunctionInfo],
    min_occurrences: int = 3,
) -> tuple[list[dict], int]:
    """Find function names appearing 3+ times across files with different signatures.

    Returns (entries, total_functions_checked).

    Each entry represents a function name group where signatures differ:
    {
        "name": str,           # function name
        "occurrences": int,    # how many definitions
        "files": list[str],    # distinct files
        "variants": list[dict] # [{file, line, params, param_count}]
    }
    """
    # Group by function name
    by_name: dict[str, list[FunctionInfo]] = defaultdict(list)
    for fn in functions:
        if fn.name.startswith("_") and not fn.name.startswith("__"):
            continue  # Skip private functions — expected to be independent
        if fn.name in _ALLOWLIST:
            continue
        if fn.name.startswith("test_"):
            continue  # Skip test functions
        by_name[fn.name].append(fn)

    entries = []
    for name, fns in by_name.items():
        # Need at least min_occurrences across different files
        distinct_files = set(getattr(f, "file", "") for f in fns)
        if len(distinct_files) < min_occurrences:
            continue

        # Compare parameter lists (ignore self/cls)
        variants = []
        for fn in fns:
            params = [p for p in fn.params if p not in ("self", "cls")]
            variants.append({
                "file": getattr(fn, "file", ""),
                "line": fn.line,
                "params": params,
                "param_count": len(params),
            })

        # Check if signatures actually differ
        param_signatures = set()
        for v in variants:
            # Normalize: just param names as a tuple
            param_signatures.add(tuple(v["params"]))

        if len(param_signatures) < 2:
            continue  # All identical — no variance

        entries.append({
            "name": name,
            "occurrences": len(fns),
            "files": sorted(distinct_files),
            "file_count": len(distinct_files),
            "variants": variants,
            "signature_count": len(param_signatures),
        })

    entries.sort(key=lambda e: (-e["signature_count"], -e["occurrences"]))
    return entries, len(functions)
