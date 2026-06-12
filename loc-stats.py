#!/usr/bin/env python3
"""Summarize lines of code authored via Claude Code from session-meta JSON files."""

import json
import os
from collections import defaultdict
from pathlib import Path

SESSION_META_DIR = Path.home() / ".claude/usage-data/session-meta"


def load_sessions():
    sessions = []
    for f in SESSION_META_DIR.glob("*.json"):
        try:
            with open(f) as fh:
                sessions.append(json.load(fh))
        except (json.JSONDecodeError, OSError):
            pass
    return sessions


def main():
    sessions = load_sessions()
    if not sessions:
        print(f"No session files found in {SESSION_META_DIR}")
        return

    total_added = 0
    total_removed = 0
    by_project = defaultdict(lambda: {"added": 0, "removed": 0, "sessions": 0})

    for s in sessions:
        added = s.get("lines_added", 0) or 0
        removed = s.get("lines_removed", 0) or 0
        project = s.get("project_path", "unknown")

        total_added += added
        total_removed += removed
        by_project[project]["added"] += added
        by_project[project]["removed"] += removed
        by_project[project]["sessions"] += 1

    print(f"Sessions analyzed : {len(sessions)}")
    print(f"Lines added       : {total_added:,}")
    print(f"Lines removed     : {total_removed:,}")
    print(f"Net lines         : {total_added - total_removed:,}")
    print()
    print("── Top projects by lines added ──────────────────────────────")
    ranked = sorted(by_project.items(), key=lambda x: x[1]["added"], reverse=True)
    for path, stats in ranked[:15]:
        name = path.split("/")[-1] if path != "unknown" else "unknown"
        print(f"  {stats['added']:>8,} added  {stats['removed']:>8,} removed"
              f"  ({stats['sessions']:>3} sessions)  {name}")


if __name__ == "__main__":
    main()
