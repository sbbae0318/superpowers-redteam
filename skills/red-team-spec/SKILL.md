---
name: red-team-spec
description: Run an adversarial Red Team critique loop on a spec or plan document. Slim path — L3 deterministic gates + L4 per-spec critic + L6 banner drift (R2+). For the full 6-layer protocol (audit + cross-spec), use `red-team-spec-full`. Single spec or per-spec loop on multiple paths. User-gated per round with verdict surfaced before the gate.
---

# Red Team Spec Critique Loop — Slim Path

You are running an adversarial review of one or more spec/plan documents using the slim path (no audit, no cross-spec). For each spec: optionally run deterministic gates, dispatch a `red-team-critic` subagent for findings, apply accepted findings, surface a verdict, gate further rounds on user approval.

For the **full 6-layer protocol** (L1 audit + L5 cross-spec critic), use `/red-team-spec-full` instead.

## Input

`/red-team-spec <path1> [path2 ...]`

- 1 path → single mode
- 2+ paths → per-spec loop (this skill does NOT cross-correlate; use full path for cross-spec critique)
- Path is omitted → ask: "Which spec(s) should I red-team? Give me the path(s)."

Resolve each path to absolute. If any does not exist, stop and tell the user.

## Workflow (per spec — for multi-path, run sequentially)

### Phase A — Gates (L3, conditional firing)

For each gate, fire only if the spec contains the corresponding structured block. Gate tools are expected at `~/.claude/tools/redteam/`; if a tool file is missing, skip with a one-line warning (graceful degrade).

1. **Gate B — Import sandbox.** Fire iff the spec contains a `claimed_imports:` block (a fenced yaml under a `## Claimed imports` heading). For each `<module>: [<symbol>, ...]` entry, run `.venv/bin/python -c "from <module> import <symbol>; import inspect; print(inspect.signature(<symbol>))"` (or `python3` if no venv). On any ImportError: report and ask user `[abort / proceed-with-warning]`.
2. **Gate C — `verify_spec_facts.py`.** Fire iff the spec contains a `## Claimed facts` block AND a `verified_against:` field in frontmatter. Run `python3 ~/.claude/tools/redteam/verify_spec_facts.py <spec> <yaml>`. Exit 0 = PASS; exit 1 = FAIL with diagnostic. On FAIL: report and ask user `[abort / proceed-with-warning]`.
3. **Gate D2 — `verify_signature_preservation.py`.** Fire iff the spec contains a `signature_changes:` block. Run `python3 ~/.claude/tools/redteam/verify_signature_preservation.py <spec> <codebase_root>`. Same FAIL handling.

If none of the gates have applicable blocks (typical for non-OpenMontage specs): print one line "no structured blocks → gates skipped" and proceed to Phase B. This makes the slim path behave identically to v1 generic critique on a plain markdown spec.

### Phase B — Per-spec critic (L4)

Round 1: fresh `Agent({subagent_type: "red-team-critic", description: "Round 1 red-team review", prompt: "Review the spec at <abs path>. This is round 1. Return your findings as your final assistant message in the exact output format from your system prompt (Verdict block, then CRITICAL/HIGH/MEDIUM/LOW sections, then CRITICAL category count block). Do NOT call Write — the harness blocks subagents from writing report .md files. The main agent will persist your message to <abs round-1 output path>."})`

Round 2+: fresh `Agent()` with prior round's findings + accept/rebut summary inlined in the prompt (see Phase F template below). No `SendMessage` — verified absent in this harness; explicit context-passing achieves equivalent behavior.

Persist the critic's final assistant message verbatim to `<spec-dir>/<spec-basename>-redteam-round-<N>.md`.

### Phase C — Apply findings

For each finding in doc B, regardless of severity, judge on its merits:

- **CRITICAL**: strong-accept by default. Rebut only with an explicit, recorded reason.
- **HIGH**: weigh the argument; accept if it survives scrutiny; rebut otherwise.
- **MEDIUM / LOW**: accept only if the change is small, clearly improves the spec, and aligns with author intent. Otherwise drop silently — do not record rebuttals for these.

**Anchored edits required.** When applying `Edit`, include at least one line of unique surrounding context in `old_string`. If the target text is ambiguous, prefer whole-section replacement (find section by `##` heading, replace its body). Never match on a short string that could appear in more than one place.

**Rebutted CRITICAL/HIGH** → append entry to `## Design Decisions (Round N)` at the bottom of the spec:

```markdown
### <gap title>
- **Critic:** <one-sentence summary>
- **Decision:** rejected — <reasoning>
```

### Phase D — Banner drift check (L6, R2+ only)

For round 2 and later, after Phase C edits land but before the report:

```bash
python3 ~/.claude/tools/redteam/verify_banner_vs_body.py <spec abs path>
```

Exit 0 = PASS; exit 1 = FAIL with diagnostic of missing-from-body banner tokens. Append the output to the round-N doc B file under a `## Layer 6 — Banner drift check` section.

### Phase E — Report and gate

Surface a single user-facing message in this shape:

```
═══════════════════════════════════════════
 Red Team Round N Verdict     (~tokens: <rough estimate>)
═══════════════════════════════════════════
 Readiness: X/10 — <critic's rationale verbatim, citing top unresolved>
 Recommendation: <critic's recommendation verbatim>
 CRITICAL category count: A=<n> B=<n> C=<n> D=<n> E=<n> F=<n> G=<n>

──────────────── Round N changes ────────────────

Accepted (applied to spec):
- [severity] <finding title> → edited <section-name or line-range>: <one-line summary>

Rebutted (logged in Design Decisions):
- [severity] <finding title> → <one-line rebuttal reason>

Dropped silently (MEDIUM/LOW with no clear win):
- <count, e.g. "3 MEDIUM, 1 LOW">

──────────────── Open issues entering next round ────────────────
- [CRITICAL] <title> (rebutted round N — see Design Decisions)
- [HIGH] <title> (carryover from round 1; still unaddressed)
- ...
```

The **Open Issues panel** is auto-derived from: (a) this round's rebutted CRITICAL/HIGH, (b) spec's `## Outstanding Risks` entries without `→ RESOLVED` markers, (c) spec's `## Open Questions` entries without `→ DONE` markers. Lists everything still on the table for the next round.

**Token estimate** = rough sum of doc B size + spec size + dispatch overhead (informational).

Then ask: **"Run another red-team round?"**

- yes → Phase F context-rich dispatch (Round N+1)
- no → end the skill; return the (possibly revised) spec path(s) to the caller

**Soft max-round warning.** If N ≥ 5 and user requests another round, warn: "You have completed N rounds; default soft max is 5; further rounds typically find diminishing returns. Confirm to proceed."

### Phase F — Round N+1 dispatch (when user says yes)

For each spec being re-reviewed:

```
Agent({
  subagent_type: "red-team-critic",
  description: "Round <N+1> red-team review",
  prompt: """
This is round <N+1> of an ongoing adversarial review. Your prior findings and the main agent's response are below — treat the prior findings as YOUR OWN prior position.

── Spec under review ──
Path: <absolute spec path>
(Re-read this file; it has been revised since round <N>.)

── Your prior findings (round <N>), pasted verbatim ──
<full contents of doc B-N>

── Main agent's response ──
Accepted and applied:
- <bullets per accepted item>
Rebutted (logged in Design Decisions):
- <bullets per rebutted CRITICAL/HIGH with reasons>
Dropped without recorded action: <count>

── Your task ──
Follow the round-2+ instructions in your system prompt:
- Drop items already resolved
- Re-escalate weak rebuttals (quote the rebuttal)
- Hunt for new weaknesses exposed by revisions
- Update Verdict score and reference the prior round's score
- Cite the top unresolved item

Return findings as your final assistant message. The main agent will persist to <abs round-(N+1) path>.
"""
})
```

Then loop back to Phase C with the new round number.

## Files this skill writes

- Per-round findings: `<spec-dir>/<spec-basename>-redteam-round-<N>.md`
- In-place edits to spec: accepted-item edits + `## Design Decisions (Round N)` appendices

## Files this skill never writes

- Anything outside `<spec-directory>/`
- Code, tests, implementation files

## Termination

The skill ends when the user declines another round. Do not auto-decide convergence. Do not invoke `writing-plans` — that is the caller's responsibility.
