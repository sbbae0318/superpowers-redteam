# Red Team Spec Critique Workflow — Design

**Date:** 2026-05-14
**Status:** Draft for review

## Goal

Automate adversarial review of spec/plan documents produced by the superpowers `brainstorming` skill. A clean-context subagent critiques the spec as if it were a competitor AI's hastily-written submission, then the main agent auto-revises the spec based on the findings and discloses changes to the user. Supports multi-round debate via persistent subagent context.

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
- Coverage dimensions (use as checklist, not template):
  - Missing requirements (functional, non-functional, operational)
  - Ambiguous or weasel-worded language
  - Hidden assumptions never made explicit
  - Oversimplifications that hide real complexity
  - Untested assumptions about user behavior, scale, dependencies
  - Missing edge cases, security holes, scalability ceilings
  - Internal contradictions between sections
  - YAGNI violations (speculative features without justification)

**Output format (fixed):**

```markdown
---
reviewed-spec: <spec A filename>
round: <N>
---
## CRITICAL  (spec is not safe to adopt without addressing these)
- **<gap title>** — spec A의 "<인용>" 부분. 왜 문제인가: <한 줄>. 제안: <한 줄>

## HIGH  (strongly recommended)
...

## MEDIUM  (improvements worth considering)
...

## LOW  (nitpicks)
...
```

**Round 2+ behavior (when invoked via SendMessage with prior context):**

> If you are being resumed for a follow-up round, you will be told the spec was revised and given a summary of the main agent's rebuttals. Then:
> (a) If a rebuttal is sound, drop that item — do not re-raise it.
> (b) If a rebuttal is weak or evasive, re-escalate with sharper reasoning.
> (c) Spend most attention on **new** issues exposed by the revision.
> (d) Never repeat a claim already accepted as resolved.

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
     prompt: "Review the spec at <abs-path>. Write findings to <out-abs-path>. Round=1."
   })
   ```
   Capture and remember the subagent's name/id from the response — needed for later rounds.
4. Read doc B. Iterate every item across **all severities** (CRITICAL, HIGH, MEDIUM, LOW). Severity is a prioritization hint, not a filter:
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
7. Report to user in **one message**:
   ```
   Round N complete:
   - Accepted: X items
   - Rebutted (logged): Y items
   - Changes:
     - <bullet summary of edits>
   - Rebuttals:
     - <bullet summary with reasons>
   ```
8. Ask user: "Run another red-team round?"
   - **yes** →
     ```
     SendMessage({
       to: "<critic name from round 1>",
       prompt: "Spec was revised. Path=<abs>, changes since your last review=<bullets>, rebuttals to your previous claims=<bullets with reasons>. Review again. Round=N+1. Write findings to <new round path>."
     })
     ```
     Then loop back to step 4 with `N+1`. doc B path increments: `...-redteam-round-2.md`, etc.
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
3. **Phase 2 — Red Team:** invoke `red-team-spec` skill with spec A's path. Let it run its loop (rounds gated by user).
4. **Phase 3 — Plans:** once `red-team-spec` returns, invoke `superpowers:writing-plans`.

The wrapper itself contains no critique logic — it delegates entirely to the standalone skill.

---

## Persistent Context Across Rounds

Round 1 uses `Agent()` — fresh, clean context. The critic has no knowledge of the spec's authoring history; the "competitor AI submission" framing is intact.

Rounds 2+ use `SendMessage` to the **same** critic subagent. Rationale:

- Critic remembers prior round's claims and the main's rebuttals → no redundant re-discovery
- Enables genuine debate: critic can concede points or escalate rebuttals it finds weak
- Persona stays consistent (system prompt persists across SendMessage)
- Subsequent rounds focus on **new** weaknesses exposed by the revisions

The main agent must capture the critic's name/id from the round-1 `Agent()` return value and pass it to all later `SendMessage` calls in the same loop.

---

## Files Per Session

- `docs/superpowers/specs/<date>-<topic>-design.md` — spec A (created by brainstorming, revised in place each round, accumulates `## Design Decisions (Round N)` sections)
- `docs/superpowers/specs/<date>-<topic>-design-redteam-round-1.md` — doc B round 1
- `docs/superpowers/specs/<date>-<topic>-design-redteam-round-2.md` — doc B round 2 (if user runs round 2)
- ... and so on per round

History is preserved by keeping round-N doc B files; spec A is mutated in place but rebuttals create an audit trail at the bottom.

---

## Non-Goals

- **Auto-judging convergence.** No heuristic decides when the critic is "done" — user gates every round.
- **Modifying the superpowers plugin.** The wrapper composes via `Skill` tool only; brainstorming and writing-plans remain untouched.
- **Red-teaming non-spec content.** This workflow is scoped to spec/plan documents. PR review, code critique, architecture review would be separate skills (the `red-team-critic` agent persona could be reused there with different driver skills).

---

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Critic suggests scope creep or premature optimization | Main agent gates each item; rebuttals logged with reason for traceability |
| Persistent context anchors critic on stale round-1 framing | Round 2+ prompt explicitly tells critic to drop resolved items and focus on novel issues |
| Subagent attempts spec modification | Agent file restricts tools to `Read`, `Grep` only |
| Brainstorming's "invoke writing-plans" directive fires anyway | Wrapper skill content cites the user-instruction-over-plugin-skill priority rule from `using-superpowers` |
| Spec A becomes bloated by accumulating Design Decisions sections | Acceptable — provides audit trail; user can manually prune before merging to writing-plans |
| Main agent loses track of critic's id between rounds | Agent SDK returns name/id on `Agent()` invocation; main records it in working memory for the loop duration |

---

## Open Questions (deferred)

- Should round-N doc B files be auto-deleted after the loop ends? Current plan: keep them as audit trail.
- Should the wrapper skill expose options to skip Phase 2 (back to plain brainstorm)? Current plan: no — that's what `/superpowers:brainstorming` is for.
