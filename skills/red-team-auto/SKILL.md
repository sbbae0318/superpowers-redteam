---
name: red-team-auto
description: Run the red-team critique loop in unattended auto mode (no per-round user gate). v3.0 adds doc-type routing (spec/plan/audit/research) — Phase 0 detects type and selects matching critic agent. Termination via objective count/title-set signals only — no LLM score is used. Single-doc per invocation. CRITICAL findings auto-accept, HIGH auto-rebut, MEDIUM/LOW skip. Up to hard_cap rounds (default 10) with concurrency lock, failure recovery, per-round CRITICAL cap, identity-review gate (cumulative-edits threshold; user decides continue/abort with before/after summary), and severity-oscillation detection. Merge archives intermediate artifacts so the loop can naturally re-run. Use when you have abundant model-token budget and want unattended convergence.
---

# Red Team Auto Mode — Dispatcher

You are running the red-team critique loop without per-round user gates. v3.0 adds doc-type routing: Phase 0 detects the document type (spec/plan/audit/research) and selects the matching critic agent for all rounds in this invocation. For each round you dispatch the selected critic, auto-accept CRITICAL findings, auto-rebut HIGH findings, and check objective termination conditions. The loop runs up to `hard_cap` rounds (default 10) or until a termination condition fires.

For interactive critique with per-round gates, use `/red-team` (the v3.0 interactive dispatcher).

The auto path assumes `~/.claude/tools/redteam/` exists with the three tool files. Halts on missing tools.

## Input

`/red-team-auto <path>`

- 1 path → proceed
- 2+ paths → refuse; tell user "auto mode is single-doc per invocation; for series support see v3.1 (deferred)".
- Path omitted → ask: "Which document should I auto-red-team?"

Resolve to absolute. If not exists: stop.

## Category definitions (inherited from red-team-critic)

- **A** — yaml fact contradiction (claim contradicts verified_facts yaml)
- **B** — signature drop (refactor silently drops a kwarg)
- **C** — caller drift (claim about caller behavior contradicts grep)
- **D** — design / runtime issue not statically catchable
- **E** — cross-spec contract mismatch (series mode only — N/A in auto)
- **F** — banner-vs-body drift (R2+; not gated separately in auto skill — banner check is a separate tool the user can run)
- **G** — semantically wrong but technically correct

## Workflow

### Phase 0 — Pre-loop setup

1. Resolve spec path to absolute. If not exists: stop, tell user.

1.5. **Type determination** (same cascade as `/red-team` dispatcher Phase 0):
   a. If frontmatter `type:` field present → use it; skip confirmation.
   b. Else apply filename heuristics:
      - `*-spec-*` or `-spec.md` → `spec` (skip confirmation, high-confidence)
      - `*-research-*` / `-research.md` / `*-survey-*` / `-survey.md` / `*-comparison-*` / `-comparison.md` / `*-falsification-*` → `research` (confirm)
      - `*-plan-*` / `-plan.md` / under `/docs/superpowers/plans/` → `plan` (confirm)
      - `*-audit-*` / `-audit.md` → `audit` (confirm)
      - default → `spec` (confirm)
   c. For non-`*-spec-*` matches: prompt user as in `/red-team` Phase 0 step 3 (with offer to pin via frontmatter).
   d. Select `agent_name`:
      - spec → `red-team-critic`
      - plan → `red-team-plan-critic`
      - audit → `red-team-audit-critic`
      - research → `red-team-research-critic`
   e. Type does NOT change mid-loop (one type per invocation).

2. **Concurrency lock.** Check `<spec-dir>/<spec-basename>-redteam.lock`. If present:
   - Read PID + `started_at` from lock
   - If `kill -0 <PID>` succeeds AND `started_at` is within 1 hour: refuse — another invocation in progress. Tell user lock path + PID; exit.
   - Otherwise: stale; warn, overwrite the lock.
   Write fresh lock as YAML: `{pid: <pid>, started_at: <ISO>, spec: <abs path>}`. **Release lock on every termination path (Phases 6/7).**

3. Validate `hard_cap` (default 10) is in `[1, 100]`. Out-of-range → error and exit (do not start the loop).

4. Read spec into memory. Check existing state YAML at `<spec-dir>/<basename>-redteam-state.yaml`:
   - If exists AND `round_0_snapshot` ≠ current spec text → prompt "previous state YAML found but spec text has changed — [overwrite (start fresh) / abort]?". Block until answered. On `abort`: release lock, exit. On `overwrite`: continue.
   - Otherwise (or after overwrite): write initial state YAML (see schema below).

5. Announce templated: `"Auto mode — running up to <hard_cap> rounds. Termination conditions: stable / plateau / soft_plateau / hard_cap / context_budget / gate_fail / critic_failure / edit_cap_per_round / aborted_at_identity_review / severity_oscillation. No per-round user gate; one merge/continue/discard gate at termination. An identity-review gate may pause the loop if cumulative_critical_accepts > 25."`

### Phase 1a — Gates per round (L3, conditional firing)

**Skip Phase 1a entirely if `doc_type ∈ {audit, research}`** — gate-relevant blocks don't exist in those doc types. Proceed directly to Phase 1b.

For spec/plan only:

For round N, run gates that apply to the (possibly-mutated) spec at this round:

1. **Gate B (import sandbox)** — fire iff spec contains a `claimed_imports:` fenced yaml under a `## Claimed imports` heading.
2. **Gate C** — `python3 ~/.claude/tools/redteam/verify_spec_facts.py <spec> <yaml>` — fire iff spec has both `## Claimed facts` block AND `verified_against:` frontmatter field.
3. **Gate D2** — `python3 ~/.claude/tools/redteam/verify_signature_preservation.py <spec> <codebase_root>` — fire iff spec contains `signature_changes:` block.

**On any Gate FAIL: halt the loop with `termination.reason: gate_fail`.** Record gate name + tool output in state YAML `termination.details`. Surface to user. Do NOT proceed to critic dispatch.

If no gates applicable: print `"no structured blocks → gates skipped"` and continue to Phase 1b.

### Phase 1b — Round N critic dispatch

Round 1: fresh `Agent({subagent_type: "<agent_name>", description: "Round 1 red-team review (auto mode, type=<doc_type>)", prompt: <slim Phase B template adapted to doc_type>})`. Critic returns findings as text.

Round 2+: fresh `Agent()` with prior doc B + accept/rebut summary inlined per slim Phase F template, plus add `"Auto mode: HIGH items are being auto-rebutted; re-escalate to CRITICAL if you believe one is genuinely unsafe."` to the prompt.

**Failure semantics:**
- `Agent()` returns error, times out, or returns empty → retry once with same prompt.
- Output missing any of (Verdict block, `## CRITICAL`, `## HIGH`, `## CRITICAL category count`) OR Verdict missing `Readiness:` / `Recommendation:` lines → malformed → retry once.
- Second failure → halt with `termination.reason: critic_failure`. Record round with `status: failed` (no count fields). Do NOT mutate the spec.

On success: write critic's message verbatim to `<spec-dir>/<basename>-redteam-round-<N>.md`. Continue to Phase 2.

### Phase 2 — Auto apply findings

**Edit scope (hard limit):** auto mode edits ONLY the target spec file. Cross-file recommendations from the critic are logged to round-N doc B + accumulated in `cross_file_recommendations` count. Never mutate sibling files (`verified_facts/*`, `README`, `design.md`, etc.).

**Per-round CRITICAL edit cap:** if a round has > 5 CRITICAL findings → halt with `termination.reason: edit_cap_per_round` (record finding count in `termination.details`). Rationale: noisy critic emitting >5 CRITICAL/round is more likely malfunctioning than detecting genuine crisis; surface to user.

**Per-loop cumulative-edits gate (identity review):** track `cumulative_critical_accepts` (count of CRITICAL findings auto-accepted across all rounds — includes both anchored `Edit` operations AND anchored-edit fallback appended sections). When `cumulative_critical_accepts > 25` (default; configurable per state YAML), **do NOT halt** — instead trigger an **identity review gate** (see Phase 2.5). Rationale for count-based metric (not byte-based): bytes are a weak proxy for "spec changed identity" — a 1-character API rename can be high impact; a verbose docstring addition can be low. Count of CRITICAL auto-accepts maps better to "spec mutations driven by critic". Threshold 25 = per-round CRITICAL cap (5) × hard_cap (10) ÷ 2, i.e., when cumulative impact reaches half the theoretical loop maximum.

`bytes_changed_cumulative` is still tracked in state YAML but is informational only (no gating).

**Severity oscillation detection:** for each finding title T (normalized — see Phase 3) in round N, compare against `CRITICAL_HIGH_titles` from rounds 1..N-1:
- If T appeared as CRITICAL in round M and HIGH in round N (or vice versa), increment a per-title oscillation counter.
- If any title oscillates ≥ 2 times across the loop → halt with `termination.reason: severity_oscillation` (record T in `termination.details`).

**Severity policy:**
- **CRITICAL** → auto-accept → `Edit` spec in place. Anchored edits required: `old_string` includes unique surrounding context, or use whole-section replacement (find `##` heading, replace section body). Never match on a short string that could appear in multiple places.
- **HIGH** → auto-rebut → append entry to `## Design Decisions (Round N)` section at bottom of spec. Create the section if it doesn't exist:
  ```markdown
  ### <gap title>
  - **Critic:** <one-sentence summary>
  - **Decision:** auto-rebut in auto mode — HIGH items are not main-agent-approved automatically; promote to CRITICAL or re-run in slim mode for manual review.
  ```
- **MEDIUM / LOW** → skip silently (do not record).

**Anchored edit fallback** (CRITICAL has no in-spec anchor — e.g., the finding is "missing Goals section"):
- Append a new top-level section at end of spec body. If a `## Design Decisions (Round N)` section already exists, insert above it.
- Section heading: derived from finding title (e.g., `## Goals (added round N)`).
- Record in round report: `"[CRITICAL] <title> → appended new section: <heading>"`.

**Alternative considered (rejected):** "CRITICAL+HIGH auto-accept with single pre-loop user confirmation." Rejected because (a) reintroduces gates contrary to auto-mode value proposition, (b) HIGH auto-accept compounds critic noise across rounds with no offsetting brake.

### Phase 2.5 — Identity review gate (triggered by cumulative-edits threshold)

Triggers iff `cumulative_critical_accepts > 25` (default; configurable per state YAML) AND the gate has not already fired in this invocation (one-time per run). Fires AFTER Phase 2 applies the current round's findings, BEFORE Phase 3 records state.

**Render to user:**

```
═══════════════════════════════════════════
 Identity Review Gate
═══════════════════════════════════════════

The auto loop has applied <cumulative_critical_accepts> CRITICAL findings across <N> rounds.
At this point, the spec's identity may have drifted from what you submitted.

──────────────── Identity: BEFORE (round 0) ────────────────
<First 3 top-level `##` headings from round_0_snapshot, plus first 200 chars of body>

──────────────── Identity: AFTER (current) ────────────────
<First 3 top-level `##` headings from current spec, plus first 200 chars of body>

──────────────── What changed (and the critic's reasoning) ────────────────
CRITICAL findings auto-accepted (titles, grouped by round):
  Round 1: <title1>, <title2>, ...
  Round 2: <title3>, ...
  ...

Category breakdown: A=<n> B=<n> C=<n> D=<n> E=<n> F=<n> G=<n>
Cumulative bytes changed: <bytes> (<pct>% of round_0) — informational

──────────────── Why this gate fired ────────────────
The critic has driven <cumulative_critical_accepts> changes — above the threshold (25).
This is the auto loop asking: do you still want this trajectory?

──────────────── Options ────────────────
  [continue]  — accept the mutation trajectory; proceed to round <N+1>
  [abort]     — halt loop now; proceed to Phase 6 with reason aborted_at_identity_review
                (you can still merge, discard, or continue from Phase 6)
```

**Input recognition** (case-insensitive, whitespace stripped):
- continue: `continue`, `c`, `proceed`, `keep going`, `go`, `ok`
- abort: `abort`, `a`, `stop`, `halt`, `no`, `cancel`

Ambiguous input: re-prompt once; after 2 unrecognized → default `abort` (conservative for this gate — abnormal mutation context).

**Idle timeout: 1 hour → default `abort`** (NOT merge — this gate signals abnormal trajectory; the conservative default differs from the final gate's idle-default).

**Outcomes:**
- `continue` → set per-invocation flag `identity_gate_passed = true`; do NOT re-fire this gate again in the same invocation. Proceed to Phase 3.
- `abort` → record `termination.reason: aborted_at_identity_review`, `termination.details: identity gate triggered at cumulative_critical_accepts=<N>, user aborted`. Skip Phase 3 for the current round (it's complete already); proceed to Phase 6 with the abort reason. In Phase 6, the user still gets merge/continue/discard options on the partially-revised spec.

### Phase 3 — Update state YAML

Append a round entry. Title normalization: for each `- **<title>** — ...` bullet under `## CRITICAL` and `## HIGH`, extract the text between `**` markers; lowercase; collapse internal whitespace to single space; strip leading/trailing whitespace. Backticks preserved.

(See full schema at bottom of skill.)

### Phase 4 — Termination check (after each round)

Mid-phase halts (`gate_fail` / `critic_failure` / `edit_cap_per_round` / `aborted_at_identity_review` / `severity_oscillation`) take precedence — if any fired during current round's processing, terminate immediately with that reason. Note: the identity-review gate (Phase 2.5) does NOT itself terminate the loop; only the user's `abort` decision at that gate produces `aborted_at_identity_review`.

Otherwise, evaluate in order; first match wins:

1. **plateau** — `set(rounds[-1].CRITICAL_HIGH_titles) == set(rounds[-2].CRITICAL_HIGH_titles)`. Set equality on normalized titles. Round 2+ only.
2. **soft_plateau** — `CRITICAL_count + HIGH_count` unchanged for last 3 rounds AND at least one CRITICAL or HIGH still open. Round 3+ only. Secondary signal for cosmetic title drift escaping primary plateau.
3. **stable** — either:
   - `rounds[-1].CRITICAL_count == 0 AND rounds[-1].HIGH_count == 0` AND same for `rounds[-2]` (strict), OR
   - `rounds[-1].CRITICAL_count == 0 AND rounds[-1].HIGH_count == 1` AND `rounds[-2].CRITICAL_count == 0 AND rounds[-2].HIGH_count == 1` AND `set(rounds[-1].CRITICAL_HIGH_titles) != set(rounds[-2].CRITICAL_HIGH_titles)` (the single residual HIGH changed across rounds — actively being addressed).
4. **hard_cap** — `len(rounds) >= state.hard_cap`.
5. **context_budget** — estimated next-round prompt > `0.8 * state.model_context_limit_tokens`. Estimate: prefer `tiktoken` if importable, else `(len(round-N doc B chars) + len(spec chars) + 5000) / 4`. If `model_context_limit_tokens` is 0 or missing: print warning, skip this check (hard_cap remains backstop).

Note: plateau is evaluated before stable to ensure "stable with 1 persistent HIGH (same title both rounds)" is correctly reported as plateau (critic stuck, not converged).

If no condition fires → Phase 5. Otherwise → Phase 6.

### Phase 5 — Continue

Log per-round summary (NOT a user gate, stdout-style informational):

```
═══════════════════════════════════════════
 Auto Red Team Round N
═══════════════════════════════════════════
 CRITICAL: <n>  (Δ <±n> from round N-1)
 HIGH:     <n>  (Δ <±n> from round N-1)
 Categories: A=<n> B=<n> C=<n> D=<n> E=<n> F=<n> G=<n>

 Title set change from round N-1:
   added:     [<titles>]
   removed:   [<titles>]
   unchanged: [<titles>]

 Cumulative spec change: <bytes_changed> bytes (<pct>% of round_0)

 Termination check: not yet — <one-line reason: e.g., "plateau not yet (titles differ); stable not met (HIGH=2); hard_cap not yet (3/10)">
 Continuing to round <N+1>...
```

Dispatch round N+1 (Phase 1a with `len(rounds)+1`).

### Phase 6 — Final report + user gate

```
═══════════════════════════════════════════
 Auto Red Team — Loop Complete
═══════════════════════════════════════════
 Termination: <reason>
 Rounds: <N> (of <hard_cap> max)
 Final counts: CRITICAL=<n>, HIGH=<n>
 Final categories: A=<n> B=<n> C=<n> D=<n> E=<n> F=<n> G=<n>

 Round-by-round CRITICAL: <n1> → <n2> → ... → <nN>
 Round-by-round HIGH:     <h1> → <h2> → ... → <hN>

 Cumulative spec change: <bytes_changed> bytes (<pct>%)
 Cross-file recommendations (logged, not applied): <n>

 Files:
   doc B per round:  <spec>-redteam-round-1.md ... -round-<N>.md
   state YAML:       <spec>-redteam-state.yaml
   lockfile:         <spec>-redteam.lock (will be released on your choice)

Options:
  [merge]    — keep spec as-is, exit
  [continue] — run one more round (only valid for plateau / soft_plateau / hard_cap)
  [discard]  — revert spec to round_0_snapshot
```

**Input recognition** (case-insensitive, leading/trailing whitespace stripped):
- merge: `merge`, `m`, `yes`, `y`, `done`, `ok`, `accept`
- continue: `continue`, `c`, `more`, `another round`
- discard: `discard`, `revert`, `undo`, `rollback`

Ambiguous input (anything not in the lists, e.g. `"yeah"`, `"k"`): re-print options + re-prompt once. After 2 unrecognized inputs in a row → default action `merge`, record `confirmed_action: merge_after_ambiguous_input`.

**Idle timeout**: if no input within 1 hour of prompt display → default `merge`, record `confirmed_action: merge_after_idle_timeout`. Auto mode is for unattended runs; an indefinite block defeats that.

**Behavior per choice:**
- `merge` → write `termination.confirmed_action: merge` + `confirmed_at` to state YAML. **Archive intermediate artifacts** so a subsequent auto run on this spec starts clean (no stale state-YAML mismatch prompt in Phase 0):
  1. `mkdir -p <spec-dir>/.redteam-archive/<ISO timestamp>/`
  2. `mv <spec-dir>/<basename>-redteam-round-*.md → <archive-dir>/`
  3. `mv <spec-dir>/<basename>-redteam-state.yaml → <archive-dir>/`
  4. Release lock (`rm <spec-dir>/<basename>-redteam.lock`)
  5. Print: `"Archived <N> round files + state YAML to <archive-dir>. Spec ready for re-runs without state conflict."`

  Exit; return spec path (mutated). The archive preserves audit trail for later inspection.

- `continue` → valid only for `termination.reason` ∈ `{plateau, soft_plateau, hard_cap, aborted_at_identity_review}`. Other reasons (e.g., `gate_fail`, `critic_failure`, `edit_cap_per_round`, `severity_oscillation`) require addressing the root cause; refuse + re-prompt. On valid continue: run one more round (Phase 1a with `len(rounds)+1`); then return to Phase 6. (Note: `aborted_at_identity_review` is continuable — the user can choose to push past the identity gate after seeing the report. Identity-gate one-time-flag remains set, so the gate does NOT re-fire even after threshold remains crossed.)

- `discard` → restore spec from `round_0_snapshot` via `Write` (full overwrite); print `cross_file_recommendations` one more time (user may want to action those manually); write `termination.confirmed_action: discarded` + `confirmed_at`. **Archive same way as merge** (the audit trail of what was tried is valuable even if reverted — directory marker `.redteam-archive/<ISO>/discarded/` so the reverted-vs-merged distinction is visible). Release lock; exit; return spec path (now reverted).

### Phase 7 — Termination metadata + cleanup

Append `termination` block to state YAML if not already done by Phase 6:

```yaml
termination:
  reason: <enum>
  round: <N>
  triggered_at: <ISO>
  details: <optional one-line context — e.g., for gate_fail, which gate; for severity_oscillation, the title>
  confirmed_action: <enum>
  confirmed_at: <ISO>
```

Release `<spec>-redteam.lock` (`rm` if it exists). Skill ends. Do NOT invoke `writing-plans` — that is the caller's job.

## State YAML schema (full)

```yaml
spec: <basename>                       # spec filename without .md
mode: auto                             # marker for tooling
started_at: <ISO>
hard_cap: <int, default 10>
model_context_limit_tokens: <int, default 200000>
round_0_snapshot: |                    # full pre-loop spec text, verbatim
  <multi-line content>
rounds:
  - round: 1
    status: ok                         # or "failed" — failed rounds omit count fields
    started_at: <ISO>
    completed_at: <ISO>
    CRITICAL_count: <n>
    HIGH_count: <n>
    CRITICAL_breakdown_by_category:
      A: <n>
      B: <n>
      C: <n>
      D: <n>
      E: <n>
      F: <n>
      G: <n>
    CRITICAL_HIGH_titles: [<str>, <str>, ...]
    dropped_count: <n>                 # MEDIUM + LOW dropped silently
    cumulative_critical_accepts: <int>     # count-based; gate trigger metric
    bytes_changed_cumulative: <int>        # informational only; not a gate trigger
    cross_file_recommendations_logged: <n>
  - round: 2
    ...
termination:
  reason: <stable | plateau | soft_plateau | hard_cap | context_budget |
           gate_fail | critic_failure | edit_cap_per_round | aborted_at_identity_review |
           severity_oscillation>
  round: <N>
  triggered_at: <ISO>
  details: <optional str>
  confirmed_action: <merge | discarded | merge_after_idle_timeout | merge_after_ambiguous_input>
  confirmed_at: <ISO>
```

`accepted_count` and `rebutted_count` are intentionally omitted — in auto mode they tautologically equal `CRITICAL_count` and `HIGH_count`. Re-add them if a future mode introduces a partial-accept policy.

## Files this skill writes

- Round findings (per round): `<spec-dir>/<basename>-redteam-round-<N>.md`
- State YAML: `<spec-dir>/<basename>-redteam-state.yaml`
- Lockfile (during loop, removed at termination): `<spec-dir>/<basename>-redteam.lock`
- In-place spec edits: CRITICAL accepts (anchored or fallback-appended sections); `## Design Decisions (Round N)` rebuts

## Files this skill never writes

- Anything outside `<spec-directory>/`
- Sibling files of the spec (`verified_facts/*`, `README`, `design.md`, etc.) — cross-file recos logged only
- Code, tests, implementation files

## Termination

The loop ends when a termination condition fires AND the user confirms (or idle-timeout defaults). Do NOT auto-invoke `writing-plans` or any downstream skill. Caller decides next step.
