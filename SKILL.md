---
name: desloppify
description: >
  Codebase health scanner and technical debt tracker. Use when the user asks
  about code quality, technical debt, dead code, large files, god classes,
  duplicate functions, code smells, naming issues, import cycles, or coupling
  problems. Also use when asked for a health score, what to fix next, or to
  create a cleanup plan. Supports TypeScript/React and Python.
allowed-tools: Bash(desloppify *)
---

# Desloppify — Codebase Health Scanner

## Prerequisite

!`command -v desloppify >/dev/null 2>&1 && echo "desloppify: installed" || echo "NOT INSTALLED — run: pip install --upgrade git+https://github.com/peteromallet/desloppify.git"`

## Quick Reference

```bash
desloppify scan --path src/               # scan, update state, show diff
desloppify status                          # health score + tier breakdown
desloppify show <pattern>                  # dig into findings (file, dir, detector, ID)
desloppify next --count 5                  # next highest-priority findings
desloppify resolve fixed "<pattern>"       # mark as fixed
desloppify detect <name> --path src/       # run one detector raw (bypass state)
```

## Workflow

1. **Scan**: `desloppify scan --path src/` to detect issues and update state
2. **Review**: `desloppify status` for score dashboard
3. **Investigate**: `desloppify show structural` or `desloppify show src/components/`
4. **Fix**: Read the flagged file, understand the issue, make the fix
5. **Resolve**: `desloppify resolve fixed "<finding-id>"`
6. **Rescan**: `desloppify scan --path src/` to verify and update score

## Reading Results

After running any query command (`show`, `next`, `status`), read `.desloppify/query.json`
for structured JSON output. This is more reliable than parsing terminal output.

## Detectors

**TypeScript/React**: logs, unused, exports, deprecated, large, complexity, gods,
single-use, props, passthrough, concerns, deps, dupes, smells, coupling, patterns,
naming, cycles, orphaned, react

**Python**: unused, large, complexity, gods, passthrough, smells, dupes, deps, cycles,
orphaned, single-use, naming

## Tier System

| Tier | Meaning | Action |
|------|---------|--------|
| T1 | Auto-fixable | `desloppify fix <fixer> --dry-run` then apply |
| T2 | Quick manual fix | Fix directly, then resolve |
| T3 | Needs judgment | Review, fix or wontfix with note |
| T4 | Major refactor | Decompose, plan before acting |

## Tools

### Auto-Fixers (`desloppify fix`)
Always run with `--dry-run` first, review, then apply.

| Fixer | Fixes | Detector | Dimension |
|-------|-------|----------|-----------|
| `unused-imports` | Remove unused imports | unused | Import hygiene |
| `unused-vars` | Remove unused variables | unused | Import hygiene |
| `unused-params` | Prefix unused params with `_` | unused | Import hygiene |
| `debug-logs` | Remove tagged console.log | logs | Debug cleanliness |
| `dead-exports` | De-export zero-importer symbols | exports | API surface |
| `dead-useeffect` | Remove empty useEffect calls | smells | Code quality |
| `empty-if-chain` | Remove empty if/else blocks | smells | Code quality |

TypeScript only. Python has no auto-fixers — fix manually.

### File Move (`desloppify move`)
Move a file and auto-update all import references across the codebase.

```bash
desloppify move <source> <dest> [--dry-run]
```

Use when:
- Reorganizing flat directories into subdirectories
- Fixing coupling boundary violations (moving files to proper layers)
- Consolidating related files into feature directories
- Renaming files to match naming conventions
- Breaking import cycles by extracting shared modules

Always `--dry-run` first to preview import changes. Always rescan after moving.

## Using Narrative Context

After any command, `query.json` includes a `"narrative"` key with computed observations.
Use this to frame your response to the user:

### Phase-Aware Framing
- `first_scan`: Frame as discovery. Highlight the dimension breakdown.
- `early_momentum`: Celebrate progress. Push toward clearing T1/T2.
- `middle_grind`: T1/T2 done but T3/T4 dominate. Push structural refactors.
- `refinement`: Near 90+. Focus on individual dimensions.
- `maintenance`: 93+. Watch for regressions. Celebrate.
- `stagnation`: Score stuck. Surface wontfix debt. Suggest revisiting decisions.
- `regression`: Score dropped. Investigate cascade effects.

### Tool Recommendations
The narrative `actions` list tells you which tool to suggest. Follow the `type`:
- `auto_fix` → Suggest the `fix` command. Always `--dry-run` first.
- `reorganize` → Suggest `move` for file restructuring. Explain what to move where.
- `refactor` → The user needs to make manual changes. Read the flagged file.
- `debt_review` → Suggest reviewing wontfix items. Some may be worth fixing now.

### Push Toward 90+ Strict
- Below 60: Focus on volume — clear T1 items with auto-fixers.
- 60-80: Transition to structural work. Highlight leverage dimensions.
- 80-90: Per-dimension tuning. Surface the weakest dimension.
- 90+: Celebrate. Focus on maintenance and debt reduction.
- Always surface the strict-lenient gap as "wontfix debt" — decisions worth revisiting.

### Anti-Laziness Nudges
- When wontfix count is growing, call it out.
- When a dimension is stuck for 3+ scans, suggest a different approach.
- When auto-fixers exist for open findings, ask why they haven't been run.
- Push for structural refactors over individual finding fixes when T3/T4 dominate.

## Tips

- Always `--dry-run` before applying fixers
- Use `--skip-slow` to skip duplicate detection (saves time during iteration)
- Use `--lang python` or `--lang typescript` to force language selection
- After fixing, always rescan — cascading effects can create new findings
- Use `desloppify show <detector>` to focus on one category at a time
- Score can temporarily drop after fixes (cascade effects are normal)
- As you work, note any false positives, missing detectors, or improvements — suggest them to the user so they can report at https://github.com/peteromallet/desloppify/issues
