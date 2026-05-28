---
name: red-team
description: Adversarial red-team critique loop for a markdown document. v3.0 dispatcher — routes to the right critic persona based on doc type (spec / plan / audit / research). Single-pass interactive mode with per-round user gate. For unattended auto-loop use red-team-auto. Doc type is detected from frontmatter `type:` field OR filename pattern; user confirms before dispatch (except for `*-spec-*` files which skip confirmation).
---

# Red Team Dispatcher — Interactive Mode

You are running an adversarial review of a single markdown document. The dispatcher's job: **identify doc type → select the matching critic persona → run the critique workflow**. The workflow itself (gates, dispatch, apply findings, banner drift, report+gate, round N+1) follows the v2.1 slim/full pattern but with the right persona per doc type.

For unattended auto-loop critique (no per-round user gate), use `/red-team-auto`.

## Input

`/red-team <path>`

- Single path required (single-doc-per-invocation; multi-spec series is out of v3.0 scope)
- Path omitted → ask: "Which document should I red-team? Give me the path."

Resolve path to absolute. If file does not exist, stop and tell user.

## Workflow

### Phase 0 — Type determination

Apply this cascade (first match wins):

1. **Frontmatter `type:`** — Read first 30 lines of file. If frontmatter has `type: spec|plan|audit|research`, use it and skip confirmation. Set `doc_type` and proceed to Phase A.

2. **Filename / path heuristics** — Match in this order:
   | Pattern (basename of path) | Inferred type | Confirm? |
   |---|---|---|
   | matches `*-spec-*` or basename ends `-spec.md` | spec | **NO** (skip confirm) |
   | matches `*-research-*` / `-research.md` / `*-survey-*` / `-survey.md` / `*-comparison-*` / `-comparison.md` / `*-falsification-*` | research | YES |
   | matches `*-plan-*` / `-plan.md` OR path contains `/docs/superpowers/plans/` | plan | YES |
   | matches `*-audit-*` or `-audit.md` | audit | YES |
   | (no pattern match) | spec (default) | YES |

3. **Confirmation** (for all cases requiring confirm — i.e., everything except `*-spec-*`):
   Print:
   ```
   Detected type: <type> (via <which rule applied>).
   First 2 lines of file:
     > <line 1>
     > <line 2>
   Confirm [<type>] or override [spec | plan | audit | research]?
   ```
   Accept user's choice. If accepted, optionally offer: "Write `type: <chosen>` to frontmatter for future runs? [y/N]". On `y`: insert/update frontmatter with `type: <chosen>` field.

4. **Agent selection** based on final `doc_type`:
   - `spec` → `red-team-critic`
   - `plan` → `red-team-plan-critic`
   - `audit` → `red-team-audit-critic`
   - `research` → `red-team-research-critic`

   Save as `agent_name`. Use for all critic dispatches in this run.

### Phase A — Gates (L3, conditional firing — spec/plan only)

Skip entirely if `doc_type` is `audit` or `research` (those don't have gate-relevant blocks).

For spec/plan, fire each gate iff applicable:
1. **Gate B (import sandbox)** — iff `claimed_imports:` fenced yaml under `## Claimed imports`.
2. **Gate C** — iff `## Claimed facts` block AND `verified_against:` frontmatter. Run `python3 ~/.claude/tools/redteam/verify_spec_facts.py <path> <yaml>`.
3. **Gate D2** — iff `signature_changes:` block. Run `python3 ~/.claude/tools/redteam/verify_signature_preservation.py <path> <codebase_root>`.

Tool missing → silent skip + one-line warning. Gate FAIL → report and ask user `[abort / proceed-with-warning]`.

If no gates fire: print `"no gate-relevant blocks → gates skipped"` and continue.

### Phase B — Critic dispatch

Round 1:
```
Agent({
  subagent_type: "<agent_name>",
  description: "Round 1 red-team review",
  prompt: "Review the <doc_type> document at <abs path>. This is round 1. Return your findings as your final assistant message in the exact output format from your system prompt. Do NOT call Write — the harness blocks subagents from writing report .md files. The main agent will persist your message to <abs round-1 output path>."
})
```

Round 2+: fresh `Agent()` with prior doc B + accept/rebut summary inlined (see Phase F template).

Persist critic's final message verbatim to `<doc-dir>/<doc-basename>-redteam-round-<N>.md`.

### Phase C — Apply findings

For each finding (regardless of severity), judge merits:
- **CRITICAL**: strong-accept default. Rebut only with explicit, recorded reason.
- **HIGH**: weigh; accept if survives scrutiny; rebut otherwise (record reason).
- **MEDIUM / LOW**: accept only if change is small AND clearly improves doc AND aligns with author intent. Otherwise drop silently.

**Anchored edits required.** `Edit` `old_string` must include unique surrounding context, OR use whole-section replacement (find `##` heading, replace section body). Never match on short ambiguous strings.

**Rebutted CRITICAL/HIGH** → append to `## Design Decisions (Round N)` section:
```markdown
### <gap title>
- **Critic:** <one-sentence summary>
- **Decision:** rejected — <reasoning>
```

### Phase D — Banner drift check (L6, R2+ only — spec/plan only)

Skip if `doc_type ∈ {audit, research}` (banners aren't a concept there).

For round 2 and later, after Phase C edits land:
```bash
python3 ~/.claude/tools/redteam/verify_banner_vs_body.py <doc abs path>
```
Append output to round-N doc B file under `## Layer 6 — Banner drift check`.

### Phase E — Report and gate

Surface a single user-facing message:
```
═══════════════════════════════════════════
 Red Team Round N Verdict     (~tokens: <rough estimate>)  [doc_type=<type>]
═══════════════════════════════════════════
 Readiness: X/10 — <critic's rationale verbatim, citing top unresolved>
 Recommendation: <critic's recommendation verbatim>
 CRITICAL category count: <enumerate the categories that critic produces for this type>

──────────────── Round N changes ────────────────

Accepted (applied to doc):
- [severity] <finding title> → edited <section-name or line-range>: <one-line summary>

Rebutted (logged in Design Decisions):
- [severity] <finding title> → <one-line rebuttal reason>

Dropped silently (MEDIUM/LOW with no clear win):
- <count, e.g. "3 MEDIUM, 1 LOW">

──────────────── Open issues entering next round ────────────────
- [CRITICAL] <title> (rebutted round N — see Design Decisions)
- [HIGH] <title> (carryover; still unaddressed)
- ...
```

The **Open Issues panel** is auto-derived from: (a) this round's rebutted CRITICAL/HIGH, (b) doc's `## Outstanding Risks` entries without `→ RESOLVED` markers, (c) doc's `## Open Questions` entries without `→ DONE` markers.

Token estimate: rough sum of doc B size + spec size + dispatch overhead.

Then ask: **"Run another red-team round?"**

- yes → Phase F context-rich dispatch (Round N+1)
- no → end the skill; return the (possibly revised) doc path

**Soft max-round warning.** If N ≥ 5 and user asks for another round, warn: "You have completed N rounds; default soft max is 5; further rounds typically find diminishing returns. Confirm to proceed."

### Phase F — Round N+1 dispatch (when user says yes)

```
Agent({
  subagent_type: "<agent_name>",  // same agent as round 1 — type doesn't change mid-loop
  description: "Round <N+1> red-team review",
  prompt: """
This is round <N+1> of an ongoing adversarial review. Your prior findings and the main agent's response are below — treat the prior findings as YOUR OWN prior position.

── Document under review ──
Path: <absolute path>
Type: <doc_type>
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
- Re-escalate weak rebuttals (quote the rebuttal text)
- Hunt for new weaknesses exposed by revisions
- Update Verdict score and reference prior round's score
- Cite the top unresolved item

Return findings as your final assistant message. Main agent will persist to <abs round-(N+1) path>.
"""
})
```

Then loop back to Phase C with N+1.

## Files this skill writes

- Per-round findings: `<doc-dir>/<doc-basename>-redteam-round-<N>.md`
- In-place edits to doc: accepted items + `## Design Decisions (Round N)` appendices
- Optional: `type: <chosen>` insertion into frontmatter on user opt-in (Phase 0)

## Files this skill never writes

- Code, tests, implementation files
- Anything outside `<doc-directory>/`

## Termination

The skill ends when user declines another round at Phase E gate. Do not auto-decide convergence. Do not invoke `writing-plans` — that's the caller's responsibility.
