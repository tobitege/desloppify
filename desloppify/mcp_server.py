"""MCP server for desloppify — thin wrappers around CLI commands.

Each tool delegates to the existing CLI with --json output.
No code duplication — the CLI is the source of truth.

Setup: add to .mcp.json in your project:
{
  "mcpServers": {
    "desloppify": {
      "command": "python",
      "args": ["-m", "desloppify.mcp_server"]
    }
  }
}
"""

import json
import subprocess
import sys

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    print("MCP server requires: pip install mcp[cli]", file=sys.stderr)
    sys.exit(1)

mcp = FastMCP("desloppify")


def _run_cli(*args: str) -> dict:
    """Run a desloppify CLI command and return parsed output."""
    result = subprocess.run(
        [sys.executable, "-m", "desloppify", *args],
        capture_output=True, text=True, cwd="."
    )
    # Try to parse JSON from stdout
    for line in result.stdout.strip().splitlines():
        try:
            return json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
    # Fallback: return raw output
    return {"stdout": result.stdout.strip(), "stderr": result.stderr.strip()}


@mcp.tool()
def scan(path: str = "src/", skip_slow: bool = False, lang: str | None = None) -> dict:
    """Run all detectors on the codebase, update state, and return score summary.

    Args:
        path: Directory to scan (relative to project root)
        skip_slow: Skip slow detectors like duplicate detection
        lang: Language to scan (auto-detected if omitted)
    """
    args = []
    if lang:
        args += ["--lang", lang]
    args += ["scan", "--path", path]
    if skip_slow:
        args.append("--skip-slow")
    # Scan writes to state file; get status after
    subprocess.run(
        [sys.executable, "-m", "desloppify", *args],
        capture_output=True, text=True, cwd="."
    )
    return _run_cli("status", "--json")


@mcp.tool()
def status(lang: str | None = None) -> dict:
    """Get health score dashboard with per-detector progress.

    Args:
        lang: Language (auto-detected if omitted)
    """
    args = []
    if lang:
        args += ["--lang", lang]
    args += ["status", "--json"]
    return _run_cli(*args)


@mcp.tool()
def show(pattern: str, status_filter: str = "open", top: int = 20) -> dict:
    """Show findings matching a pattern.

    Args:
        pattern: File path, directory, detector name, finding ID, or glob
        status_filter: Filter by status (open, fixed, wontfix, all)
        top: Maximum number of results
    """
    return _run_cli("show", pattern, "--status", status_filter,
                     "--top", str(top), "--json")


@mcp.tool()
def detect(detector: str, path: str = "src/", top: int = 20) -> dict:
    """Run a single detector directly, bypassing state tracking.

    Args:
        detector: Detector name (large, complexity, gods, dupes, smells, etc.)
        path: Directory to scan
        top: Maximum results
    """
    return _run_cli("detect", detector, "--path", path,
                     "--top", str(top), "--json")


@mcp.tool()
def next_finding(count: int = 1, tier: int | None = None) -> dict:
    """Get the next highest-priority open findings to work on.

    Args:
        count: Number of findings to return
        tier: Filter to a specific tier (1-4)
    """
    args = ["next", "--count", str(count), "--json"]
    if tier:
        args += ["--tier", str(tier)]
    return _run_cli(*args)


@mcp.tool()
def resolve(patterns: list[str], resolution: str, note: str | None = None) -> dict:
    """Mark findings as fixed, wontfix, or false_positive.

    Args:
        patterns: Finding IDs, detector names, file paths, or globs
        resolution: One of: fixed, wontfix, false_positive
        note: Optional note explaining the resolution
    """
    args = ["resolve", resolution, *patterns]
    if note:
        args += ["--note", note]
    return _run_cli(*args)


if __name__ == "__main__":
    mcp.run()
