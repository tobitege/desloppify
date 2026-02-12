"""zone command: show/set/clear zone classifications."""

from pathlib import Path

from ..utils import c, rel
from ..cli import _state_path
from ..zones import Zone


def cmd_zone(args):
    """Handle zone subcommands: show, set, clear."""
    action = getattr(args, "zone_action", None)
    if action == "show":
        _zone_show(args)
    elif action == "set":
        _zone_set(args)
    elif action == "clear":
        _zone_clear(args)
    else:
        print(c("Usage: desloppify zone {show|set|clear}", "red"))


def _zone_show(args):
    """Show zone classifications for all scanned files."""
    from ..state import load_state
    from ..cli import _resolve_lang

    sp = _state_path(args)
    state = load_state(sp)
    lang = _resolve_lang(args)
    if not lang or not lang.file_finder:
        print(c("No language detected — run a scan first.", "red"))
        return

    path = Path(args.path)
    overrides = state.get("config", {}).get("zone_overrides", {})

    from ..zones import FileZoneMap
    files = lang.file_finder(path)
    zone_map = FileZoneMap(files, lang.zone_rules, rel_fn=rel, overrides=overrides or None)

    # Group files by zone
    by_zone: dict[str, list[str]] = {}
    for f in sorted(files, key=lambda f: rel(f)):
        zone = zone_map.get(f)
        by_zone.setdefault(zone.value, []).append(f)

    total = len(files)
    print(c(f"\nZone classifications ({total} files)\n", "bold"))

    for zone_val in ["production", "test", "config", "generated", "script", "vendor"]:
        zone_files = by_zone.get(zone_val, [])
        if not zone_files:
            continue
        print(c(f"  {zone_val} ({len(zone_files)} files)", "bold"))
        for f in zone_files:
            rp = rel(f)
            is_override = rp in overrides
            suffix = c(" (override)", "cyan") if is_override else ""
            print(f"    {rp}{suffix}")
        print()

    if overrides:
        print(c(f"  {len(overrides)} override(s) active", "dim"))
    print(c("  Override: desloppify zone set <file> <zone>", "dim"))
    print(c("  Clear:    desloppify zone clear <file>", "dim"))


def _zone_set(args):
    """Set a zone override for a file."""
    from ..state import load_state, save_state

    sp = _state_path(args)
    state = load_state(sp)
    filepath = args.zone_path
    zone_value = args.zone_value

    # Validate zone value
    valid_zones = {z.value for z in Zone}
    if zone_value not in valid_zones:
        print(c(f"Invalid zone: {zone_value}. Valid: {', '.join(sorted(valid_zones))}", "red"))
        return

    state.setdefault("config", {}).setdefault("zone_overrides", {})[filepath] = zone_value
    save_state(state, sp)
    print(f"  Set {filepath} → {zone_value}")
    print(c("  Run `desloppify scan` to apply.", "dim"))


def _zone_clear(args):
    """Clear a zone override for a file."""
    from ..state import load_state, save_state

    sp = _state_path(args)
    state = load_state(sp)
    filepath = args.zone_path

    overrides = state.get("config", {}).get("zone_overrides", {})
    if filepath in overrides:
        del overrides[filepath]
        save_state(state, sp)
        print(f"  Cleared override for {filepath}")
        print(c("  Run `desloppify scan` to apply.", "dim"))
    else:
        print(c(f"  No override found for {filepath}", "yellow"))
