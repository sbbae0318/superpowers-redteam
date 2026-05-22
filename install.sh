#!/usr/bin/env bash
# Install superpowers-redteam artifacts into ~/.claude/.
# Idempotent — safe to re-run after pulling updates.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_DIR="${CLAUDE_DIR:-$HOME/.claude}"

AGENT_SRC="$REPO_DIR/agents/red-team-critic.md"
SKILL_SPEC_SRC="$REPO_DIR/skills/red-team-spec/SKILL.md"
SKILL_FULL_SRC="$REPO_DIR/skills/red-team-spec-full/SKILL.md"
SKILL_AUTO_SRC="$REPO_DIR/skills/red-team-spec-auto/SKILL.md"
SKILL_CONV_SRC="$REPO_DIR/skills/red-team-conversation/SKILL.md"
SKILL_BRAIN_SRC="$REPO_DIR/skills/redteam-brainstorm/SKILL.md"

TOOL_SPECF_SRC="$REPO_DIR/tools/verify_spec_facts.py"
TOOL_SIGP_SRC="$REPO_DIR/tools/verify_signature_preservation.py"
TOOL_BANR_SRC="$REPO_DIR/tools/verify_banner_vs_body.py"

for src in "$AGENT_SRC" "$SKILL_SPEC_SRC" "$SKILL_FULL_SRC" "$SKILL_AUTO_SRC" "$SKILL_CONV_SRC" "$SKILL_BRAIN_SRC" \
           "$TOOL_SPECF_SRC" "$TOOL_SIGP_SRC" "$TOOL_BANR_SRC"; do
  if [[ ! -f "$src" ]]; then
    echo "error: missing source file: $src" >&2
    exit 1
  fi
done

mkdir -p \
  "$CLAUDE_DIR/agents" \
  "$CLAUDE_DIR/skills/red-team-spec" \
  "$CLAUDE_DIR/skills/red-team-spec-full" \
  "$CLAUDE_DIR/skills/red-team-spec-auto" \
  "$CLAUDE_DIR/skills/red-team-conversation" \
  "$CLAUDE_DIR/skills/redteam-brainstorm" \
  "$CLAUDE_DIR/tools/redteam"

install -m 0644 "$AGENT_SRC"       "$CLAUDE_DIR/agents/red-team-critic.md"
install -m 0644 "$SKILL_SPEC_SRC"  "$CLAUDE_DIR/skills/red-team-spec/SKILL.md"
install -m 0644 "$SKILL_FULL_SRC"  "$CLAUDE_DIR/skills/red-team-spec-full/SKILL.md"
install -m 0644 "$SKILL_AUTO_SRC"  "$CLAUDE_DIR/skills/red-team-spec-auto/SKILL.md"
install -m 0644 "$SKILL_CONV_SRC"  "$CLAUDE_DIR/skills/red-team-conversation/SKILL.md"
install -m 0644 "$SKILL_BRAIN_SRC" "$CLAUDE_DIR/skills/redteam-brainstorm/SKILL.md"

install -m 0755 "$TOOL_SPECF_SRC" "$CLAUDE_DIR/tools/redteam/verify_spec_facts.py"
install -m 0755 "$TOOL_SIGP_SRC"  "$CLAUDE_DIR/tools/redteam/verify_signature_preservation.py"
install -m 0755 "$TOOL_BANR_SRC"  "$CLAUDE_DIR/tools/redteam/verify_banner_vs_body.py"

echo "installed:"
echo "  $CLAUDE_DIR/agents/red-team-critic.md"
echo "  $CLAUDE_DIR/skills/red-team-spec/SKILL.md"
echo "  $CLAUDE_DIR/skills/red-team-spec-full/SKILL.md"
echo "  $CLAUDE_DIR/skills/red-team-spec-auto/SKILL.md"
echo "  $CLAUDE_DIR/skills/red-team-conversation/SKILL.md"
echo "  $CLAUDE_DIR/skills/redteam-brainstorm/SKILL.md"
echo "  $CLAUDE_DIR/tools/redteam/verify_spec_facts.py"
echo "  $CLAUDE_DIR/tools/redteam/verify_signature_preservation.py"
echo "  $CLAUDE_DIR/tools/redteam/verify_banner_vs_body.py"
echo
echo "Start a fresh Claude Code session to register the new artifacts."
echo "Then try:"
echo "  /red-team-spec <path-to-some-spec.md>             (slim, default)"
echo "  /red-team-spec-full <path1> [path2 ...]          (full 6-layer, audit + cross-spec)"
echo "  /red-team-spec-auto <path>                       (unattended-loop auto mode, v2.1)"
echo "  /red-team-conversation [topic]                   (unchanged)"
echo "  /redteam-brainstorm                              (unchanged)"
