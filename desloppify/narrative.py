"""Computed narrative context for LLM coaching and terminal headlines.

Pure functions that derive structured observations from state data.
No print statements — returns dicts that flow into _write_query().
"""

from __future__ import annotations


# ── Detector → tool mapping ────────────────────────────────

DETECTOR_TOOLS = {
    # Detectors with auto-fixers (TypeScript only)
    "unused":  {"fixers": ["unused-imports", "unused-vars", "unused-params"],
                "action_type": "auto_fix"},
    "logs":    {"fixers": ["debug-logs"], "action_type": "auto_fix"},
    "exports": {"fixers": ["dead-exports"], "action_type": "auto_fix"},
    "smells":  {"fixers": ["dead-useeffect", "empty-if-chain"],
                "action_type": "auto_fix"},  # partial — only some smells
    # Detectors where `move` is the primary tool
    "orphaned":   {"fixers": [], "action_type": "reorganize",
                   "tool": "move", "guidance": "delete dead files or relocate with `desloppify move`"},
    "flat_dirs":  {"fixers": [], "action_type": "reorganize",
                   "tool": "move", "guidance": "create subdirectories and use `desloppify move`"},
    "naming":     {"fixers": [], "action_type": "reorganize",
                   "tool": "move", "guidance": "rename files with `desloppify move` to fix conventions"},
    "single_use": {"fixers": [], "action_type": "reorganize",
                   "tool": "move", "guidance": "inline or relocate with `desloppify move`"},
    "coupling":   {"fixers": [], "action_type": "reorganize",
                   "tool": "move", "guidance": "fix boundary violations with `desloppify move`"},
    "cycles":     {"fixers": [], "action_type": "reorganize",
                   "tool": "move", "guidance": "break cycles by extracting shared code or using `desloppify move`"},
    # Detectors requiring manual intervention
    "structural": {"fixers": [], "action_type": "refactor",
                   "guidance": "decompose large files — extract logic into focused modules"},
    "props":      {"fixers": [], "action_type": "refactor",
                   "guidance": "split bloated components, extract sub-components"},
    "deprecated": {"fixers": [], "action_type": "manual_fix",
                   "guidance": "remove deprecated symbols or migrate callers"},
    "react":      {"fixers": [], "action_type": "refactor",
                   "guidance": "refactor React antipatterns (state sync, useEffect misuse)"},
    "dupes":      {"fixers": [], "action_type": "refactor",
                   "guidance": "extract shared utility or consolidate duplicates"},
    "patterns":   {"fixers": [], "action_type": "refactor",
                   "guidance": "align to single pattern across the codebase"},
}

# Structural sub-detectors that merge under "structural"
_STRUCTURAL_MERGE = {"large", "complexity", "gods", "concerns"}


def compute_narrative(state: dict, *, diff: dict | None = None,
                      lang: str | None = None) -> dict:
    """Compute structured narrative context from state data.

    Returns a dict with: phase, headline, dimensions, actions, tools, debt, milestone.
    """
    history = state.get("scan_history", [])
    dim_scores = state.get("dimension_scores", {})
    stats = state.get("stats", {})
    obj_strict = state.get("objective_strict")
    obj_score = state.get("objective_score")
    findings = state.get("findings", {})

    phase = _detect_phase(history, obj_strict)
    dimensions = _analyze_dimensions(dim_scores, history, state)
    debt = _analyze_debt(dim_scores, findings, history)
    milestone = _detect_milestone(state, diff, history)
    actions = _compute_actions(findings, dim_scores, state, debt, lang)
    tools = _compute_tools(findings, dim_scores, lang)
    headline = _compute_headline(phase, dimensions, debt, milestone, diff,
                                 obj_strict, obj_score, stats, history)

    return {
        "phase": phase,
        "headline": headline,
        "dimensions": dimensions,
        "actions": actions,
        "tools": tools,
        "debt": debt,
        "milestone": milestone,
    }


# ── Phase detection ────────────────────────────────────────

def _detect_phase(history: list[dict], obj_strict: float | None) -> str:
    """Detect project phase from scan history trajectory."""
    if not history:
        return "first_scan"

    if len(history) == 1:
        return "first_scan"

    strict = obj_strict
    if strict is None and history:
        strict = history[-1].get("objective_strict")

    # Check regression: strict dropped from previous scan
    if len(history) >= 2:
        prev = history[-2].get("objective_strict")
        curr = history[-1].get("objective_strict")
        if prev is not None and curr is not None and curr < prev - 0.5:
            return "regression"

    # Check stagnation: strict unchanged ±0.5 for 3+ scans
    if len(history) >= 3:
        recent = [h.get("objective_strict") for h in history[-3:]]
        if all(r is not None for r in recent):
            spread = max(recent) - min(recent)
            if spread <= 0.5:
                return "stagnation"

    if strict is not None:
        if strict > 93:
            return "maintenance"
        if strict > 80:
            return "refinement"

    # Early momentum: scans 2-5 with score rising
    if len(history) <= 5:
        if len(history) >= 2:
            first = history[0].get("objective_strict")
            last = history[-1].get("objective_strict")
            if first is not None and last is not None and last > first:
                return "early_momentum"
        return "early_momentum"

    return "middle_grind"


# ── Dimension analysis ─────────────────────────────────────

def _analyze_dimensions(dim_scores: dict, history: list[dict],
                        state: dict) -> dict:
    """Compute per-dimension structured analysis."""
    if not dim_scores:
        return {}

    from .scoring import merge_potentials, compute_score_impact

    potentials = merge_potentials(state.get("potentials", {}))

    # Lowest dimensions (by strict score)
    sorted_dims = sorted(
        ((name, ds) for name, ds in dim_scores.items() if ds.get("strict", ds["score"]) < 100),
        key=lambda x: x[1].get("strict", x[1]["score"]),
    )
    lowest = []
    for name, ds in sorted_dims[:3]:
        strict = ds.get("strict", ds["score"])
        issues = ds["issues"]
        # Estimate impact from the dominant detector
        impact = 0.0
        for det, det_data in ds.get("detectors", {}).items():
            if det_data.get("issues", 0) > 0:
                imp = compute_score_impact(
                    {k: {"score": v["score"], "tier": v.get("tier", 3),
                          "detectors": v.get("detectors", {})}
                     for k, v in dim_scores.items()},
                    potentials, det, det_data["issues"])
                impact = max(impact, imp)
        lowest.append({"name": name, "strict": round(strict, 1),
                        "issues": issues, "impact": round(impact, 1)})

    # Biggest gap dimensions (lenient - strict)
    biggest_gap = []
    for name, ds in dim_scores.items():
        lenient = ds["score"]
        strict = ds.get("strict", lenient)
        gap = lenient - strict
        if gap > 1.0:
            wontfix_count = sum(
                1 for f in state.get("findings", {}).values()
                if f["status"] == "wontfix" and _finding_in_dimension(f, name, dim_scores)
            )
            biggest_gap.append({"name": name, "lenient": round(lenient, 1),
                                "strict": round(strict, 1), "gap": round(gap, 1),
                                "wontfix_count": wontfix_count})
    biggest_gap.sort(key=lambda x: -x["gap"])

    # Stagnant dimensions (strict unchanged for 3+ scans)
    stagnant = []
    if len(history) >= 3:
        for name in dim_scores:
            scores = []
            for h in history[-5:]:
                hdim = (h.get("dimension_scores") or {}).get(name)
                if hdim:
                    scores.append(hdim.get("strict", hdim.get("score")))
            if len(scores) >= 3 and all(s is not None for s in scores):
                if max(scores) - min(scores) <= 0.5:
                    stagnant.append({"name": name,
                                     "strict": round(dim_scores[name].get("strict", dim_scores[name]["score"]), 1),
                                     "stuck_scans": len(scores)})

    return {
        "lowest_dimensions": lowest,
        "biggest_gap_dimensions": biggest_gap[:3],
        "stagnant_dimensions": stagnant,
    }


def _finding_in_dimension(finding: dict, dim_name: str, dim_scores: dict) -> bool:
    """Check if a finding's detector belongs to a dimension."""
    from .scoring import DIMENSIONS
    det = finding.get("detector", "")
    if det in _STRUCTURAL_MERGE:
        det = "structural"
    for dim in DIMENSIONS:
        if dim.name == dim_name and det in dim.detectors:
            return True
    return False


# ── Debt analysis ──────────────────────────────────────────

def _analyze_debt(dim_scores: dict, findings: dict,
                  history: list[dict]) -> dict:
    """Compute wontfix debt analysis."""
    # Count wontfix
    wontfix_count = sum(1 for f in findings.values() if f["status"] == "wontfix")

    # Compute gap per dimension
    worst_dim = None
    worst_gap = 0.0
    overall_lenient = 0.0
    overall_strict = 0.0
    if dim_scores:
        from .scoring import TIER_WEIGHTS
        w_sum_l = 0.0
        w_sum_s = 0.0
        w_total = 0.0
        for name, ds in dim_scores.items():
            tier = ds.get("tier", 3)
            w = TIER_WEIGHTS.get(tier, 2)
            w_sum_l += ds["score"] * w
            w_sum_s += ds.get("strict", ds["score"]) * w
            w_total += w
            gap = ds["score"] - ds.get("strict", ds["score"])
            if gap > worst_gap:
                worst_gap = gap
                worst_dim = name
        if w_total > 0:
            overall_lenient = round(w_sum_l / w_total, 1)
            overall_strict = round(w_sum_s / w_total, 1)

    overall_gap = round(overall_lenient - overall_strict, 1)

    # Trend from history
    trend = "stable"
    if len(history) >= 3:
        gaps = []
        for h in history[-5:]:
            hs = h.get("objective_strict")
            hl = h.get("objective_score")
            if hs is not None and hl is not None:
                gaps.append(hl - hs)
        if len(gaps) >= 2:
            if gaps[-1] > gaps[0] + 0.5:
                trend = "growing"
            elif gaps[-1] < gaps[0] - 0.5:
                trend = "shrinking"

    return {
        "overall_gap": overall_gap,
        "wontfix_count": wontfix_count,
        "worst_dimension": worst_dim,
        "worst_gap": round(worst_gap, 1),
        "trend": trend,
    }


# ── Milestone detection ────────────────────────────────────

def _detect_milestone(state: dict, diff: dict | None,
                      history: list[dict]) -> str | None:
    """Detect notable milestones worth celebrating."""
    obj_strict = state.get("objective_strict")
    stats = state.get("stats", {})

    # Check T1 clear
    by_tier = stats.get("by_tier", {})
    t1_open = by_tier.get("1", {}).get("open", 0)
    t2_open = by_tier.get("2", {}).get("open", 0)

    if len(history) >= 2:
        prev_strict = history[-2].get("objective_strict")
        if prev_strict is not None and obj_strict is not None:
            # Crossed 90
            if prev_strict < 90 and obj_strict >= 90:
                return "Crossed 90% strict!"
            # Crossed 80
            if prev_strict < 80 and obj_strict >= 80:
                return "Crossed 80% strict!"

    if t1_open == 0 and t2_open == 0:
        # Check if there were T1/T2 items before
        total_t1 = sum(by_tier.get("1", {}).values())
        total_t2 = sum(by_tier.get("2", {}).values())
        if total_t1 + total_t2 > 0:
            return "All T1 and T2 items cleared!"

    if t1_open == 0:
        total_t1 = sum(by_tier.get("1", {}).values())
        if total_t1 > 0:
            return "All T1 items cleared!"

    if stats.get("open", 0) == 0 and stats.get("total", 0) > 0:
        return "Zero open findings!"

    return None


# ── Recommended actions ────────────────────────────────────

def _compute_actions(findings: dict, dim_scores: dict, state: dict,
                     debt: dict, lang: str | None) -> list[dict]:
    """Compute prioritized action list with tool mapping."""
    from .scoring import merge_potentials, compute_score_impact

    potentials = merge_potentials(state.get("potentials", {}))
    actions = []
    priority = 0

    # Count open findings by detector
    by_det: dict[str, int] = {}
    for f in findings.values():
        if f["status"] != "open":
            continue
        det = f.get("detector", "unknown")
        if det in _STRUCTURAL_MERGE:
            det = "structural"
        by_det[det] = by_det.get(det, 0) + 1

    # Auto-fixable actions (or manual-fix for Python)
    for det, tool_info in DETECTOR_TOOLS.items():
        if tool_info["action_type"] != "auto_fix":
            continue
        count = by_det.get(det, 0)
        if count == 0:
            continue

        impact = 0.0
        if potentials and dim_scores:
            impact = compute_score_impact(
                {k: {"score": v["score"], "tier": v.get("tier", 3),
                      "detectors": v.get("detectors", {})}
                 for k, v in dim_scores.items()},
                potentials, det, count)

        from .scoring import get_dimension_for_detector
        dim = get_dimension_for_detector(det)
        dim_name = dim.name if dim else "Unknown"

        # Python has no auto-fixers — suggest manual fix instead
        if lang == "python":
            priority += 1
            actions.append({
                "priority": priority,
                "type": "manual_fix",
                "description": f"{count} {det} findings — fix manually",
                "command": f"desloppify show {det} --status open",
                "impact": round(impact, 1),
                "dimension": dim_name,
            })
            continue

        for fixer in tool_info["fixers"]:
            priority += 1
            actions.append({
                "priority": priority,
                "type": "auto_fix",
                "description": f"{count} {det} findings — auto-fixable",
                "command": f"desloppify fix {fixer} --dry-run",
                "impact": round(impact, 1),
                "dimension": dim_name,
            })
            break  # One action per detector, listing first fixer

    # Reorganize actions
    for det, tool_info in DETECTOR_TOOLS.items():
        if tool_info["action_type"] != "reorganize":
            continue
        count = by_det.get(det, 0)
        if count == 0:
            continue

        impact = 0.0
        if potentials and dim_scores:
            impact = compute_score_impact(
                {k: {"score": v["score"], "tier": v.get("tier", 3),
                      "detectors": v.get("detectors", {})}
                 for k, v in dim_scores.items()},
                potentials, det, count)

        from .scoring import get_dimension_for_detector
        dim = get_dimension_for_detector(det)
        dim_name = dim.name if dim else "Unknown"

        priority += 1
        actions.append({
            "priority": priority,
            "type": "reorganize",
            "description": f"{count} {det} findings — restructure with move",
            "command": f"desloppify show {det} --status open",
            "tool_hint": tool_info.get("guidance", ""),
            "impact": round(impact, 1),
            "dimension": dim_name,
        })

    # Refactor actions
    for det, tool_info in DETECTOR_TOOLS.items():
        if tool_info["action_type"] not in ("refactor", "manual_fix"):
            continue
        count = by_det.get(det, 0)
        if count == 0:
            continue

        impact = 0.0
        if potentials and dim_scores:
            impact = compute_score_impact(
                {k: {"score": v["score"], "tier": v.get("tier", 3),
                      "detectors": v.get("detectors", {})}
                 for k, v in dim_scores.items()},
                potentials, det, count)

        from .scoring import get_dimension_for_detector
        dim = get_dimension_for_detector(det)
        dim_name = dim.name if dim else "Unknown"

        priority += 1
        actions.append({
            "priority": priority,
            "type": tool_info["action_type"],
            "description": f"{count} {det} findings — {tool_info.get('guidance', 'manual fix')}",
            "command": f"desloppify show {det} --status open",
            "impact": round(impact, 1),
            "dimension": dim_name,
        })

    # Debt review action
    if debt.get("overall_gap", 0) > 2.0:
        priority += 1
        actions.append({
            "priority": priority,
            "type": "debt_review",
            "description": f"{debt['overall_gap']} pts of wontfix debt — review stale decisions",
            "command": "desloppify show --status wontfix",
            "gap": debt["overall_gap"],
        })

    # Sort by impact descending, auto_fix first
    type_order = {"auto_fix": 0, "reorganize": 1, "refactor": 2, "manual_fix": 3, "debt_review": 4}
    actions.sort(key=lambda a: (type_order.get(a["type"], 9), -a.get("impact", 0)))
    for i, a in enumerate(actions):
        a["priority"] = i + 1

    return actions


# ── Tool inventory ─────────────────────────────────────────

def _compute_tools(findings: dict, dim_scores: dict,
                   lang: str | None) -> dict:
    """Compute available tools inventory for the current context."""
    # Count open findings by detector
    by_det: dict[str, int] = {}
    for f in findings.values():
        if f["status"] != "open":
            continue
        det = f.get("detector", "unknown")
        if det in _STRUCTURAL_MERGE:
            det = "structural"
        by_det[det] = by_det.get(det, 0) + 1

    # Available fixers (only those with >0 open findings)
    fixers = []
    if lang != "python":
        for det, tool_info in DETECTOR_TOOLS.items():
            if tool_info["action_type"] != "auto_fix":
                continue
            count = by_det.get(det, 0)
            if count == 0:
                continue
            for fixer in tool_info["fixers"]:
                fixers.append({
                    "name": fixer,
                    "detector": det,
                    "open_count": count,
                    "command": f"desloppify fix {fixer} --dry-run",
                })

    # Move tool relevance
    org_issues = sum(by_det.get(d, 0) for d in
                     ["orphaned", "flat_dirs", "naming", "single_use", "coupling", "cycles"])
    move_reasons = []
    if by_det.get("orphaned", 0):
        move_reasons.append(f"{by_det['orphaned']} orphaned files")
    if by_det.get("coupling", 0):
        move_reasons.append(f"{by_det['coupling']} coupling violations")
    if by_det.get("single_use", 0):
        move_reasons.append(f"{by_det['single_use']} single-use files")
    if by_det.get("flat_dirs", 0):
        move_reasons.append(f"{by_det['flat_dirs']} flat directories")
    if by_det.get("naming", 0):
        move_reasons.append(f"{by_det['naming']} naming issues")

    return {
        "fixers": fixers,
        "move": {
            "available": True,
            "relevant": org_issues > 0,
            "reason": " + ".join(move_reasons) if move_reasons else None,
            "usage": "desloppify move <source> <dest> [--dry-run]",
        },
        "plan": {
            "command": "desloppify plan",
            "description": "Generate prioritized markdown cleanup plan",
        },
    }


# ── Headline computation ──────────────────────────────────

def _compute_headline(phase: str, dimensions: dict, debt: dict,
                      milestone: str | None, diff: dict | None,
                      obj_strict: float | None, obj_score: float | None,
                      stats: dict, history: list[dict]) -> str | None:
    """Compute one computed sentence for terminal display."""
    # Milestone takes priority
    if milestone:
        return milestone

    # First scan framing
    if phase == "first_scan":
        dims = len(dimensions.get("lowest_dimensions", [])) if dimensions else 0
        open_count = stats.get("open", 0)
        if dims:
            return f"First scan complete. {open_count} open findings across {dims} dimensions."
        return f"First scan complete. {open_count} findings detected."

    # Regression
    if phase == "regression" and len(history) >= 2:
        prev = history[-2].get("objective_strict")
        curr = history[-1].get("objective_strict")
        if prev is not None and curr is not None:
            drop = round(prev - curr, 1)
            return f"Score dropped {drop} pts — check for cascading effects from recent fixes."

    # Stagnation
    if phase == "stagnation":
        if obj_strict is not None:
            stuck_scans = min(len(history), 5)
            wontfix = debt.get("wontfix_count", 0)
            if wontfix > 0:
                return (f"Score stuck at {obj_strict:.1f} for {stuck_scans} scans. "
                        f"{wontfix} wontfix items — revisit?")
            return f"Score stuck at {obj_strict:.1f} for {stuck_scans} scans. Try a different approach."

    # Leverage point (lowest dimension with biggest impact)
    lowest = dimensions.get("lowest_dimensions", [])
    if lowest and lowest[0].get("impact", 0) > 0:
        top = lowest[0]
        return (f"{top['name']} is your biggest lever: "
                f"{top['issues']} items → +{top['impact']} pts")

    # Gap callout
    if debt.get("overall_gap", 0) > 5.0:
        gap = debt["overall_gap"]
        worst = debt.get("worst_dimension", "")
        if obj_strict is not None and obj_score is not None:
            return (f"Strict {obj_strict:.1f} vs lenient {obj_score:.1f} — "
                    f"{gap} pts of wontfix debt, mostly in {worst}")

    # Maintenance phase
    if phase == "maintenance":
        return f"Health {obj_strict:.1f}/100 — maintenance mode. Watch for regressions."

    return None
