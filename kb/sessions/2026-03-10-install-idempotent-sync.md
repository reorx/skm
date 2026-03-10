---
created: 2026-03-10
tags:
  - skm-install
  - idempotency
  - sync
  - cleanup
---

# Enhance `skm install` idempotent sync behavior

## Summary

Made `skm install` fully declarative — `skills.yaml` is now a state file, and each install syncs agent directories to match it. Previously, install only added new skills but didn't clean up stale links when config changed.

## Changes

### `src/skm/commands/install.py`
- Replaced the old removal logic (which only detected fully removed skill/source pairs) with a link-level diff approach
- After installing all packages, collect all new `linked_to` paths into a set
- Compare every old lock entry's `linked_to` paths against the new set
- Remove any path present in old lock but not in new state
- Contextual messages distinguish "agent config changed" vs "no longer in config"
- Added a "Removing stale links" header (red, bold) printed once before removal entries
- Individual removal lines printed in red

### Three sync scenarios now handled
1. **Skill removed from `skills:` list** — all its links across all agents get cleaned up
2. **Agent added to `excludes:` (or removed from `includes:`)** — only links to that agent get removed, skill stays in other agents
3. **Entire package removed from config** — all skills from that source get cleaned up

### Safety boundary
Only links tracked in `skills-lock.yaml` are removed. Manually created files or skills installed by other tools in agent directories are never touched.

### Tests added (`tests/test_install.py`)
- `test_install_removes_skill_dropped_from_config` — installs skill-a and skill-b, then removes skill-b from config and verifies links are cleaned up
- `test_install_removes_links_for_excluded_agent` — installs to all agents, then adds `excludes: [codex]` and verifies codex link is removed while claude link remains

### Documentation updated
- **README.md**: New "Install Sync Behavior" section explaining declarative sync and the safety boundary
- **AGENTS.md**: Expanded `skm install` command description with sync details
