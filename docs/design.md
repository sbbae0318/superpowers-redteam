# Red Team Spec Critique Workflow — Design

**Date:** 2026-05-14
**Status:** Implemented (revised)

## Goal

Automate adversarial review of spec/plan documents produced by the superpowers `brainstorming` skill. A clean-context subagent critiques the spec as if it were a competitor AI's hastily-written submission. The main agent auto-revises the spec based on findings it accepts, surfaces the critic's per-round readiness verdict to the user, and gates further rounds on user approval. Multi-round critique runs with explicit prior-round context passed through the dispatch prompt — see "Context Continuity Across Rounds" below.

## Components

Three artifacts, all user-level under `~/.claude/`:

```
~/.claude/
├── agents/red-team-critic.md            # Adversarial reviewer persona (reusable)
├── skills/red-team-spec/SKILL.md        # Standalone red-team loop on a given spec
└── skills/redteam-brainstorm/SKILL.md   # Wrapper: brainstorm → red-team → plans
```

No modifications to `~/.claude/CLAUDE.md` and no fork of the superpowers plugin.

---

### 1. `~/.claude/agents/red-team-critic.md`

Reusable subagent definition. Frontmatter restricts tools to `Read` and `Grep` so the critic cannot modify the spec.

**Persona (system prompt):**

- Adopt a dismissive, bad-mood tone. Treat the supplied document as a hastily-written submission from a competing AI model that you must shred.
- Cite specific spec text in every finding. Vague critiques are rejected by the harness — be concrete.
- Always produce a one-line readiness verdict per round (score 1–10 + recommendation) — see verdict rubric below.
- Coverage dimensions (use as checklist, not template):
  - Missing requirements (functional, non-functional, operational)
  - Ambiguous or weasel-worded language
  - Hidden assumptions never made explicit
  - Oversimplifications that hide real complexity
  - Untested assumptions about user behavior, scale, dependencies
  - Missing edge cases, security holes, scalability ceilings
  - Internal contradictions between sections
  - YAGNI violations (speculative features without justification)

**Verdict rubric (1–10 readiness score):**

| Score | Meaning | Recommendation (verbatim) |
|---|---|---|
| 9–10 | Only LOW items remain, if any | `Ready for implementation — no further rounds needed` |
| 7–8 | A few HIGH/MEDIUM items, nothing blocks implementation | `Another round advised — significant gaps remain` |
| 5–6 | At least one CRITICAL, or many HIGH | `Another round advised — significant gaps remain` |
| 3–4 | Multiple CRITICAL gaps, significant rework needed | `Another round strongly advised — spec not safe to implement as-is` |
| 1–2 | Spec fundamentally underspecified / contradictory | `Another round strongly advised — spec not safe to implement as-is` |

For round 2+, the rationale should reference the prior round's score (e.g., "Round 1: 4/10 → Round 2: 7/10").

**Output format (fixed):**

```markdown
---
reviewed-spec: <spec A filename>
round: <N>
---

## Verdict
**Readiness: <N>/10** — <one-sentence rationale>
**Recommendation:** <one of the three sentences from rubric>

## CRITICAL  (spec is not safe to adopt without addressing these)
- **<gap title>** — spec A의 "<인용>" 부분. 왜 문제인가: <한 줄>. 제안: <한 줄>

## HIGH  (strongly recommended)
...

## MEDIUM  (improvements worth considering)
...

## LOW  (nitpicks)
...
```

**Round 2+ behavior:**

> The dispatching prompt for round 2+ contains: (a) your prior round's findings pasted in full, (b) summaries of what the main agent accepted/rebutted, (c) the revised spec path. Treat the pasted prior findings as your own prior position. Then:
> (a) If a rebuttal is sound or the spec change addressed the gap, drop that item.
> (b) If a rebuttal is weak/evasive, re-escalate with sharper reasoning. Quote the rebuttal text.
> (c) Spend most attention on **new** issues exposed by the revision.
> (d) Never repeat a claim already accepted as resolved.
> (e) Your Verdict rationale should reference the prior round's score to show whether the spec is converging.

---

### 2. `~/.claude/skills/red-team-spec/SKILL.md`

Standalone skill. Composable — invokable on any existing spec, not only those produced by `redteam-brainstorm`.

**Trigger:** user invokes `/red-team-spec <path>` or another skill invokes it via `Skill` tool with a spec path argument.

**Inputs:** spec file path (absolute, or relative to cwd).

**Workflow:**

1. Verify spec path exists and is readable.
2. Compute round-1 doc B path: `<dir>/<spec-basename>-redteam-round-1.md`.
3. **Round 1 dispatch (fresh context):**
   ```
   Agent({
     subagent_type: "red-team-critic",
     prompt: "Review the spec at <abs-path>. Write findings to <out-abs-path>. Round=1. Include the Verdict block at the top."
   })
   ```
4. Read doc B. Extract the Verdict block. Iterate every item across **all severities** (CRITICAL, HIGH, MEDIUM, LOW). Severity is a prioritization hint, not a filter:
   - **CRITICAL**: strong-accept default. Rebut only with explicit, recorded reason.
   - **HIGH**: careful accept/rebut balance based on merit.
   - **MEDIUM / LOW**: accept only if cheap and clearly-improving; otherwise drop silently.
5. For each **accepted** item: apply `Edit` to spec A in place.
6. For each **rebutted** CRITICAL or HIGH item: append entry to a `## Design Decisions (Round N)` section at the bottom of spec A, with format:
   ```
   ### <gap title>
   - **Critic:** <one-line summary>
   - **Decision:** rejected — <reason>
   ```
   (MEDIUM/LOW rebuttals not recorded — too low signal.)
7. Report to user in **one message**, with the Verdict surfaced prominently before anything else:
   ```
   ═══════════════════════════════════════════
    Red Team Round N Verdict
   ═══════════════════════════════════════════
    Readiness: X/10 — <critic's rationale verbatim>
    Recommendation: <critic's recommendation verbatim>

   ──────────────── Round N changes ────────────────
   Accepted (applied to spec):  - ...
   Rebutted (logged):           - ...
   Dropped silently:            <count>
   ```
8. Ask user: "Run another red-team round?"
   - **yes** → dispatch round N+1 with full prior context inlined (see Context Continuity below). Loop back to step 4 with `N+1`. doc B path increments: `...-redteam-round-2.md`, etc.
   - **no** → exit, return control to caller.

**Output to caller:** the (possibly multi-round-revised) spec A path. Caller proceeds.

---

### 3. `~/.claude/skills/redteam-brainstorm/SKILL.md`

Wrapper orchestrator. Composes `superpowers:brainstorming` → `red-team-spec` → `superpowers:writing-plans` so the user can run the full flow with one entry point.

**Trigger:** user invokes `/redteam-brainstorm`.

**Workflow:**

1. **Phase 1 — Brainstorm:** invoke `superpowers:brainstorming` via `Skill` tool. Follow it through to completion (clarifying questions, design, spec write).
   - **Override its terminal-state directive.** The brainstorming skill ends by saying "invoke `writing-plans`." This wrapper's instructions take precedence per the superpowers priority rule (user instructions > skills). Do NOT invoke `writing-plans` yet.
2. Extract spec A's absolute path from brainstorming's output (it writes to `docs/superpowers/specs/<date>-<topic>-design.md`).
3. **Phase 2 — Red Team:** invoke `red-team-spec` skill with spec A's path. Let it run its loop (rounds gated by user, each round surfacing a verdict).
4. **Phase 3 — Plans:** once `red-team-spec` returns, invoke `superpowers:writing-plans`.

The wrapper itself contains no critique logic — it delegates entirely to the standalone skill.

---

## Context Continuity Across Rounds

Round 1 uses `Agent()` — fresh, clean context. The critic has no knowledge of the spec's authoring history; the "competitor AI submission" framing is intact.

Rounds 2+ dispatch a **new** `Agent()` call but inline the full prior context in the prompt:

- the previous round's doc B contents (pasted verbatim)
- the main agent's accepted-items summary (severity + one-liner each)
- the main agent's rebutted-items summary (severity + one-liner + rebuttal reason each)
- a count of MEDIUM/LOW items dropped silently
- the (revised) spec path

The critic's system prompt instructs it to treat pasted prior findings as its own prior position, not a fresh document. Behavior matches what a truly-resumed session would produce: drop resolved items, escalate weak rebuttals, hunt for new weaknesses, score the delta.

**Why not `SendMessage` for true session persistence?** The Claude Code harness for this distribution does not expose a `SendMessage` tool that resumes a previously-spawned subagent. Verified at design time via `ToolSearch` against the deferred-tools registry — no match for any spelling. The Anthropic Agent SDK has the capability, but the CLI's installed tool set does not.

Explicit context-passing achieves functionally equivalent behavior and adds two benefits over implicit session memory: (1) the round-2 prompt is inspectable for audit, and (2) there's no cross-round persona drift since each round starts from the same system prompt.

---

## Per-Round Verdict (user gate quality)

The critic must include a Verdict block at the top of every doc B:
- Readiness score 1–10 per the rubric in §1
- One-sentence rationale citing dominant blockers or strengths
- Explicit recommendation: ready / another round advised / another round strongly advised
- For round 2+: rationale references the prior round's score

The main agent surfaces this verdict prominently in its Phase C report — above the "Run another round?" gate — so the user makes an informed decision rather than blindly continuing or stopping.

Rationale: without an explicit verdict, users either over-run rounds (paying token cost for diminishing returns) or under-run (stopping at a 4/10 spec because the diff alone doesn't convey severity). The score gives a calibrated stopping signal.

---

## Files Per Session

- `docs/superpowers/specs/<date>-<topic>-design.md` — spec A (created by brainstorming, revised in place each round, accumulates `## Design Decisions (Round N)` sections)
- `docs/superpowers/specs/<date>-<topic>-design-redteam-round-1.md` — doc B round 1 (with Verdict at top)
- `docs/superpowers/specs/<date>-<topic>-design-redteam-round-2.md` — doc B round 2 (if user runs round 2)
- ... and so on per round

History is preserved by keeping round-N doc B files; spec A is mutated in place but rebuttals create an audit trail at the bottom.

---

## Non-Goals

- **Auto-judging convergence.** The Verdict is informational, not binding. The user decides whether to run another round.
- **Modifying the superpowers plugin.** The wrapper composes via `Skill` tool only; brainstorming and writing-plans remain untouched.
- **Red-teaming non-spec content.** This workflow is scoped to spec/plan documents. PR review, code critique, architecture review would be separate skills (the `red-team-critic` agent persona could be reused there with different driver skills).

---

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Critic suggests scope creep or premature optimization | Main agent gates each item; rebuttals logged with reason for traceability |
| Pasted prior context anchors critic on stale round-1 framing | Round 2+ prompt and system prompt both instruct: drop resolved items, focus on novel issues, score the delta |
| Subagent attempts spec modification | Agent file restricts tools to `Read`, `Grep` only |
| Brainstorming's "invoke writing-plans" directive fires anyway | Wrapper skill content cites the user-instruction-over-plugin-skill priority rule from `using-superpowers` |
| Spec A becomes bloated by accumulating Design Decisions sections | Acceptable — provides audit trail; user can manually prune before merging to writing-plans |
| User runs rounds blindly without reading verdict | Skill's Phase C report puts Verdict block first, before any change summary; cannot be skimmed past |
| Round 2+ prompt grows large with prior context | Acceptable — prior doc B is ~1–3 KB per round; even 5 rounds stays well under context limits. Token cost is sunk anyway since critic already produced that content |

---

## Open Questions (deferred)

- Should round-N doc B files be auto-deleted after the loop ends? Current plan: keep them as audit trail.
- Should the wrapper skill expose options to skip Phase 2 (back to plain brainstorm)? Current plan: no — that's what `/superpowers:brainstorming` is for.
- If `SendMessage` becomes available in this harness later, should the skill switch back to true session persistence? Current plan: keep explicit context-passing for auditability even if the alternative appears. Revisit only if context size becomes a concrete problem.
