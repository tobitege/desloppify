# Desloppify

Multi-language codebase health scanner and technical debt tracker. Scans for cruft (dead code, duplication, complexity, code smells), tracks findings across scans, auto-fixes mechanical issues, and reports a weighted health score.

Supports TypeScript/React and Python. Adding a language = adding one directory.

## Install

```bash
pip install git+https://github.com/peteromallet/desloppify.git
```

## Claude Code Integration

### Option A: Skill (recommended)

One command — Claude auto-discovers it and knows when to use it:

```bash
mkdir -p .claude/skills/desloppify && curl -sL \
  https://raw.githubusercontent.com/peteromallet/desloppify/main/SKILL.md \
  -o .claude/skills/desloppify/SKILL.md
```

Or copy from a local clone:

```bash
mkdir -p .claude/skills/desloppify
cp path/to/desloppify/SKILL.md .claude/skills/desloppify/SKILL.md
```

Now ask Claude: "scan my codebase for code quality issues" — it knows what to do.

### Option B: MCP Server

Structured tool interface — Claude calls desloppify tools directly with typed parameters:

```bash
pip install "mcp[cli]"  # additional dependency
```

Add to your `.mcp.json`:

```json
{
  "mcpServers": {
    "desloppify": {
      "command": "python",
      "args": ["-m", "desloppify.mcp_server"]
    }
  }
}
```

Exposes tools: `scan`, `status`, `show`, `detect`, `next_finding`, `resolve`.

### Option C: Both

The skill provides workflow guidance (when to scan, what to look at, how to fix).
The MCP server provides structured data access. They complement each other.

## Quick Start

```bash
desloppify scan --path src/              # detect findings, update state
desloppify status                         # health score + tier breakdown
desloppify show structural                # dig into structural findings
desloppify next --count 5                 # next 5 highest-priority items
desloppify fix unused-imports --dry-run   # preview auto-fix
desloppify scan --path src/              # rescan to update state
```

## Workflow

```
scan → status → fix T1 → fix T2 → review T3/T4 → rescan
```

1. **Scan**: `desloppify scan --path src/` — run detectors, merge into state
2. **Review**: `desloppify status` — score, tier breakdown, suggested next action
3. **Fix T1** (auto-fixable): `desloppify fix <fixer> --dry-run` then apply
4. **Fix T2** (quick): `desloppify next --tier 2` → fix → `desloppify resolve fixed "id"`
5. **Review T3/T4**: `desloppify show gods` or `desloppify show src/components/` → fix or wontfix
6. **Rescan** after every batch of fixes

## Commands

| Command | Description |
|---------|-------------|
| `scan` | Run all detectors, update state, show diff |
| `status` | Score dashboard with per-tier progress |
| `show <pattern>` | Dig into findings by file, directory, detector, or ID |
| `next [--tier N]` | Next highest-priority open finding |
| `resolve <status> <patterns>` | Mark as fixed / wontfix / false_positive |
| `ignore <pattern>` | Suppress findings matching a pattern |
| `fix <fixer> [--dry-run]` | Auto-fix mechanical issues |
| `plan` | Generate prioritized markdown plan |
| `detect <name>` | Run a single detector raw (bypass state) |
| `tree` | Annotated codebase tree |
| `viz` | Interactive HTML treemap |

## Detectors

**TypeScript/React**: logs, unused, exports, deprecated, large, complexity, gods, single-use, props, passthrough, concerns, deps, dupes, smells, coupling, patterns, naming, cycles, orphaned, react

**Python**: unused, large, complexity, gods, passthrough, smells, dupes, deps, cycles, orphaned, single-use, naming

## Tier System

| Tier | Description | Examples |
|------|-------------|----------|
| T1 | Auto-fixable | Unused imports, tagged debug logs |
| T2 | Quick manual fix | Unused vars, dead exports, high-severity smells |
| T3 | Needs judgment | Code smells, near-dupes, single-use abstractions |
| T4 | Major refactor | God components, mixed concerns |

## Scoring

- **Weighted**: T4 findings count 4x more than T1
- **Score**: all non-open findings count as resolved
- **Strict score**: excludes wontfix from both numerator and denominator
- Score can temporarily drop after fixing (cascade effects)

## Configuration

Environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `DESLOPPIFY_ROOT` | Current directory | Project root for path resolution |
| `DESLOPPIFY_SRC` | `src` | Source directory (for TS import resolution) |

## Multi-Language

`--lang <name>` selects language (auto-detected if omitted). Each language has its own state file, detectors, and fixers. Scans are scoped — languages never cross-contaminate state.

## Adding a Language

Create `desloppify/lang/<name>/`:

```
lang/<name>/
├── __init__.py      # LangConfig subclass + phase runners + config data
├── commands.py      # detect-subcommand wrappers + command registry
├── extractors.py    # extract_functions/classes → FunctionInfo/ClassInfo
├── deps.py          # Import graph builder
├── unused.py        # Wrap language tool (ruff, gopls, etc.)
└── smells.py        # Language-specific smell rules (optional)
```

Zero changes to shared code required. See `desloppify/lang/python/` for a complete example.

## Architecture

```
detectors/              ← Layer 1: Generic algorithms (zero language knowledge)
lang/base.py            ← Layer 2: Shared helpers (make_*_findings, structural signals)
lang/<name>/__init__.py ← Layer 3: Language orchestration (config + phase runners)
```

Import direction: `lang/` → `detectors/`. Never the reverse.
