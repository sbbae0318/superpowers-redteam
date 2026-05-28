#!/usr/bin/env bash
# Install superpowers-redteam artifacts into ~/.claude/.
# Idempotent — safe to re-run after pulling updates.
# v3.0: cleans up deprecated v2.1 skills (red-team-spec, red-team-spec-full,
#       red-team-conversation, redteam-brainstorm) on first run.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_DIR="${CLAUDE_DIR:-$HOME/.claude}"

# v3.0 source files
AGENT_SPEC_SRC="$REPO_DIR/agents/red-team-critic.md"
AGENT_PLAN_SRC="$REPO_DIR/agents/red-team-plan-critic.md"
AGENT_AUDIT_SRC="$REPO_DIR/agents/red-team-audit-critic.md"
AGENT_RESEARCH_SRC="$REPO_DIR/agents/red-team-research-critic.md"

SKILL_RT_SRC="$REPO_DIR/skills/red-team/SKILL.md"
SKILL_RT_AUTO_SRC="$REPO_DIR/skills/red-team-auto/SKILL.md"

TOOL_SPECF_SRC="$REPO_DIR/tools/verify_spec_facts.py"
TOOL_SIGP_SRC="$REPO_DIR/tools/verify_signature_preservation.py"
TOOL_BANR_SRC="$REPO_DIR/tools/verify_banner_vs_body.py"

# Pre-flight: validate all v3.0 source files exist
for src in "$AGENT_SPEC_SRC" "$AGENT_PLAN_SRC" "$AGENT_AUDIT_SRC" "$AGENT_RESEARCH_SRC" \
           "$SKILL_RT_SRC" "$SKILL_RT_AUTO_SRC" \
           "$TOOL_SPECF_SRC" "$TOOL_SIGP_SRC" "$TOOL_BANR_SRC"; do
  if [[ ! -f "$src" ]]; then
    echo "error: missing source file: $src" >&2
    exit 1
  fi
done

# v3.0 cleanup: remove deprecated v2.1 skill directories from CLAUDE_DIR
DEPRECATED_DIRS=(
  "$CLAUDE_DIR/skills/red-team-spec"
  "$CLAUDE_DIR/skills/red-team-spec-full"
  "$CLAUDE_DIR/skills/red-team-conversation"
  "$CLAUDE_DIR/skills/redteam-brainstorm"
)

EXISTING_DEPRECATED=()
for d in "${DEPRECATED_DIRS[@]}"; do
  if [[ -d "$d" ]]; then
    EXISTING_DEPRECATED+=("$d")
  fi
done

if [[ ${#EXISTING_DEPRECATED[@]} -gt 0 ]]; then
  echo "v3.0 upgrade: the following deprecated v2.1 skill directories will be DELETED:"
  for d in "${EXISTING_DEPRECATED[@]}"; do
    echo "  - $d"
  done

  # Allow non-interactive override via --yes flag or REDTEAM_YES env
  if [[ "${1:-}" == "--yes" ]] || [[ "${REDTEAM_YES:-}" == "1" ]]; then
    echo "(--yes / REDTEAM_YES=1 set; proceeding without prompt)"
  else
    read -p "Continue? [y/N] " ans
    case "$ans" in
      [yY]|[yY][eE][sS]) ;;
      *) echo "Aborted."; exit 1 ;;
    esac
  fi

  for d in "${EXISTING_DEPRECATED[@]}"; do
    rm -rf "$d"
    echo "  deleted $d"
  done
  echo
fi

# Install
mkdir -p \
  "$CLAUDE_DIR/agents" \
  "$CLAUDE_DIR/skills/red-team" \
  "$CLAUDE_DIR/skills/red-team-auto" \
  "$CLAUDE_DIR/tools/redteam"

install -m 0644 "$AGENT_SPEC_SRC"      "$CLAUDE_DIR/agents/red-team-critic.md"
install -m 0644 "$AGENT_PLAN_SRC"      "$CLAUDE_DIR/agents/red-team-plan-critic.md"
install -m 0644 "$AGENT_AUDIT_SRC"     "$CLAUDE_DIR/agents/red-team-audit-critic.md"
install -m 0644 "$AGENT_RESEARCH_SRC"  "$CLAUDE_DIR/agents/red-team-research-critic.md"
install -m 0644 "$SKILL_RT_SRC"        "$CLAUDE_DIR/skills/red-team/SKILL.md"
install -m 0644 "$SKILL_RT_AUTO_SRC"   "$CLAUDE_DIR/skills/red-team-auto/SKILL.md"

install -m 0755 "$TOOL_SPECF_SRC" "$CLAUDE_DIR/tools/redteam/verify_spec_facts.py"
install -m 0755 "$TOOL_SIGP_SRC"  "$CLAUDE_DIR/tools/redteam/verify_signature_preservation.py"
install -m 0755 "$TOOL_BANR_SRC"  "$CLAUDE_DIR/tools/redteam/verify_banner_vs_body.py"

echo "installed:"
echo "  $CLAUDE_DIR/agents/red-team-critic.md         (spec)"
echo "  $CLAUDE_DIR/agents/red-team-plan-critic.md    (plan)"
echo "  $CLAUDE_DIR/agents/red-team-audit-critic.md   (audit)"
echo "  $CLAUDE_DIR/agents/red-team-research-critic.md (research)"
echo "  $CLAUDE_DIR/skills/red-team/SKILL.md          (dispatcher, interactive)"
echo "  $CLAUDE_DIR/skills/red-team-auto/SKILL.md     (dispatcher, auto-loop)"
echo "  $CLAUDE_DIR/tools/redteam/verify_spec_facts.py"
echo "  $CLAUDE_DIR/tools/redteam/verify_signature_preservation.py"
echo "  $CLAUDE_DIR/tools/redteam/verify_banner_vs_body.py"
echo
echo "Start a fresh Claude Code session to register the new artifacts."
echo "Then try:"
echo "  /red-team <doc-path>             (interactive, dispatches by doc type)"
echo "  /red-team-auto <doc-path>        (auto-loop, dispatches by doc type)"
echo
echo "v3.0 removed: /red-team-spec, /red-team-spec-full, /red-team-conversation, /redteam-brainstorm"
echo "Replacement patterns documented in README.md 'Manual workflow patterns' section."
