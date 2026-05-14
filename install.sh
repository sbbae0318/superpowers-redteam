#!/usr/bin/env bash
# Install superpowers-redteam artifacts into ~/.claude/.
# Idempotent — safe to re-run after pulling updates.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_DIR="${CLAUDE_DIR:-$HOME/.claude}"

AGENT_SRC="$REPO_DIR/agents/red-team-critic.md"
SKILL_SPEC_SRC="$REPO_DIR/skills/red-team-spec/SKILL.md"
SKILL_CONV_SRC="$REPO_DIR/skills/red-team-conversation/SKILL.md"
SKILL_BRAIN_SRC="$REPO_DIR/skills/redteam-brainstorm/SKILL.md"

for src in "$AGENT_SRC" "$SKILL_SPEC_SRC" "$SKILL_CONV_SRC" "$SKILL_BRAIN_SRC"; do
  if [[ ! -f "$src" ]]; then
    echo "error: missing source file: $src" >&2
    exit 1
  fi
done

mkdir -p \
  "$CLAUDE_DIR/agents" \
  "$CLAUDE_DIR/skills/red-team-spec" \
  "$CLAUDE_DIR/skills/red-team-conversation" \
  "$CLAUDE_DIR/skills/redteam-brainstorm"

install -m 0644 "$AGENT_SRC"       "$CLAUDE_DIR/agents/red-team-critic.md"
install -m 0644 "$SKILL_SPEC_SRC"  "$CLAUDE_DIR/skills/red-team-spec/SKILL.md"
install -m 0644 "$SKILL_CONV_SRC"  "$CLAUDE_DIR/skills/red-team-conversation/SKILL.md"
install -m 0644 "$SKILL_BRAIN_SRC" "$CLAUDE_DIR/skills/redteam-brainstorm/SKILL.md"

echo "installed:"
echo "  $CLAUDE_DIR/agents/red-team-critic.md"
echo "  $CLAUDE_DIR/skills/red-team-spec/SKILL.md"
echo "  $CLAUDE_DIR/skills/red-team-conversation/SKILL.md"
echo "  $CLAUDE_DIR/skills/redteam-brainstorm/SKILL.md"
echo
echo "Start a fresh Claude Code session to register the new artifacts."
echo "Then try:  /red-team-spec <path-to-some-spec.md>"
echo "Or:        /red-team-conversation [topic]"
echo "Or:        /redteam-brainstorm"
