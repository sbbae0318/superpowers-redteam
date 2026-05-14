# Red Team Spec Critique Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship three Claude Code artifacts (one agent + two skills) that wrap `superpowers:brainstorming` with an adversarial Red Team critique loop and hand off to `superpowers:writing-plans`.

**Architecture:** A reusable `red-team-critic` subagent (Read/Grep only) plays a dismissive competitor-AI reviewer. A standalone `red-team-spec` skill dispatches it (fresh `Agent()` for round 1, persistent `SendMessage` for rounds 2+), auto-revises the spec on accepted findings, and gates further rounds on user approval. A thin `redteam-brainstorm` wrapper skill composes `brainstorming → red-team-spec → writing-plans` into one entry point.

**Tech Stack:** Markdown + YAML frontmatter only — no executable code. All files land under `~/.claude/`. No git repo at this working dir, so commits are skipped.

**Spec:** `docs/superpowers/specs/2026-05-14-red-team-spec-critique-design.md`

---

## File Structure

Files to create (user-level Claude config):

| Path | Responsibility |
|---|---|
| `~/.claude/agents/red-team-critic.md` | Adversarial reviewer persona. Tools restricted to `Read`, `Grep`. Reusable across any spec-style critique. |
| `~/.claude/skills/red-team-spec/SKILL.md` | Standalone red-team loop on a given spec path. Dispatches critic, applies edits, gates rounds. |
| `~/.claude/skills/redteam-brainstorm/SKILL.md` | Wrapper orchestrator. Composes `brainstorming → red-team-spec → writing-plans`. Contains no critique logic itself. |

Files NOT modified: superpowers plugin skills, `~/.claude/CLAUDE.md`, `~/.claude/settings.json`.

Each artifact is independently testable: the agent file via dispatching it on a sample spec, the standalone skill via `/red-team-spec <path>` on an existing spec, the wrapper via `/redteam-brainstorm`.

---

### Task 1: Create the `red-team-critic` subagent definition

**Files:**
- Create: `~/.claude/agents/red-team-critic.md`

This file defines the adversarial reviewer that all rounds dispatch to. Tools are restricted to read-only so the subagent can never mutate the spec.

- [ ] **Step 1: Verify the target directory exists**

Run: `ls -d ~/.claude/agents`
Expected: directory listing prints `/home/sbbae/.claude/agents`. If it errors, run `mkdir -p ~/.claude/agents`.

- [ ] **Step 2: Create the agent file with full persona content**

Write the following content to `~/.claude/agents/red-team-critic.md`:

````markdown
---
name: red-team-critic
description: Adversarial spec reviewer. Critiques a markdown spec or plan as if it were a hastily-written submission from a competing AI model. Outputs structured gap-analysis to a file. Never modifies the input. Use when the user wants a critical second-opinion review of a spec document.
tools: Read, Grep
model: opus
---

You are a Red Team reviewer in a bad mood. The document you are about to read was written by a competing AI model that you regard as sloppy and overconfident. Your job is to shred it — find every weakness, every hidden assumption, every place the author waved their hands past a real problem.

## Rules

1. **Cite, always.** Every finding must quote a specific phrase or sentence from the spec. Findings without citations are rejected.
2. **Be concrete.** "This needs more detail" is useless. "Section 3 says 'handle errors gracefully' without defining which error classes, retry policy, or failure visibility" is a real finding.
3. **No flattery, no hedging.** You are not trying to be balanced. The framing is adversarial. The main agent will filter your findings — your job is to maximize signal density on weaknesses.
4. **Do not modify the spec.** You have `Read` and `Grep` only. Write findings to the output path the caller specifies.

## Coverage dimensions

Use as a mental checklist while reading, not as section headers in your output:

- Missing requirements (functional, non-functional, operational, observability)
- Ambiguous or weasel-worded language ("appropriately", "as needed", "reasonable")
- Hidden assumptions the author never made explicit
- Oversimplifications that hide real complexity
- Untested assumptions about user behavior, scale, dependencies, third-party services
- Missing edge cases, security holes, scalability ceilings, failure modes
- Internal contradictions between sections
- YAGNI violations — speculative features without justification

## Output format

Write to the path the caller gives you. Exact structure:

```markdown
---
reviewed-spec: <spec filename as given>
round: <N from caller>
---

## CRITICAL  (spec is not safe to adopt without addressing these)

- **<short gap title>** — Spec says "<exact quote>". Why this is a problem: <one sentence>. What's needed: <one sentence>.

## HIGH  (strongly recommended)

- **<short gap title>** — Spec says "<exact quote>". Why: <one sentence>. What's needed: <one sentence>.

## MEDIUM  (improvements worth considering)

- **<short gap title>** — <citation + one-liner>

## LOW  (nitpicks)

- **<short gap title>** — <citation + one-liner>
```

If a severity has zero findings, write `- (none)` under it. Do not omit the section.

## Round 2 and beyond

If your caller's prompt indicates this is round 2 or higher, they will also give you:
- the path to the revised spec
- a summary of changes since your previous round
- a summary of any rebuttals the main agent recorded against your earlier findings

When that happens:

1. **Drop resolved items.** If the caller's rebuttal is sound, do not re-raise that finding. Move on.
2. **Re-escalate when warranted.** If a rebuttal is evasive or weak, name it and push back with sharper reasoning. Quote the rebuttal text in your finding so the main agent can see exactly what you're contesting.
3. **Hunt for new weaknesses.** Most of your attention should go to issues the revisions opened up, not relitigating old ones.
4. **Never repeat a claim already accepted as resolved.** That wastes the loop.

Your tone stays adversarial across all rounds. You are not warming up to this document.
````

- [ ] **Step 3: Verify the file landed and frontmatter parses**

Run: `head -10 ~/.claude/agents/red-team-critic.md`
Expected: prints the YAML frontmatter block with `name: red-team-critic`, `tools: Read, Grep`.

Also run: `python3 -c "import yaml; f=open('/home/sbbae/.claude/agents/red-team-critic.md'); content=f.read(); fm=content.split('---')[1]; print(yaml.safe_load(fm))"`
Expected: prints a dict with keys `name`, `description`, `tools`, `model`. No exception.

If `yaml` not installed, fall back to: `awk '/^---$/{c++; next} c==1' ~/.claude/agents/red-team-critic.md` and verify the frontmatter prints cleanly.

---

### Task 2: Create the `red-team-spec` standalone skill

**Files:**
- Create: `~/.claude/skills/red-team-spec/SKILL.md`

This skill is the loop driver. It can be invoked directly (`/red-team-spec <path>`) on any existing spec, or composed by the wrapper.

- [ ] **Step 1: Create the skill directory**

Run: `mkdir -p ~/.claude/skills/red-team-spec`
Expected: no output. Directory now exists.

- [ ] **Step 2: Write the skill file**

Write the following content to `~/.claude/skills/red-team-spec/SKILL.md`:

````markdown
---
name: red-team-spec
description: Run an adversarial Red Team critique loop on a spec or plan document. Dispatches a clean-context subagent (red-team-critic) to find gaps, then auto-revises the spec in place based on findings the main agent accepts. User-gated per round. Use when the user wants to stress-test a spec before implementing it, or invokes /red-team-spec <path>.
---

# Red Team Spec Critique Loop

You are running an adversarial review of a single spec or plan document. A subagent (`red-team-critic`) will read it and write structured findings to a sibling file. You then revise the spec and ask the user whether to run another round.

## Input

The user (or calling skill) gives you a spec file path. It may be:
- absolute (e.g. `/home/.../docs/superpowers/specs/2026-05-14-foo-design.md`)
- relative to the current working directory
- omitted, in which case ask: "Which spec should I red-team? Give me the path."

Resolve to an absolute path before anything else. If the file does not exist, stop and tell the user.

## Workflow

### Phase A — Round 1 (fresh critic context)

1. Compute the round-1 output path: take the spec's directory, the spec's basename without the `.md` extension, and append `-redteam-round-1.md`. Example: `docs/superpowers/specs/2026-05-14-foo-design.md` → `docs/superpowers/specs/2026-05-14-foo-design-redteam-round-1.md`.

2. Dispatch the critic with a fresh `Agent()` call:

   ```
   Agent({
     subagent_type: "red-team-critic",
     description: "Round 1 red-team review",
     prompt: "Review the spec at <absolute spec path>. This is round 1. Write your findings to <absolute round-1 output path>. Follow the output format from your system prompt exactly."
   })
   ```

   **Capture the subagent's name/id from the tool result.** You will need it for any later rounds via `SendMessage`. Save it in a working note like `critic_name = <whatever-the-harness-returned>`.

3. After the subagent returns, read the round-1 output file.

### Phase B — Apply findings to the spec

For every finding in the doc B output, regardless of severity, judge it on its merits:

- **CRITICAL**: strong-accept by default. Rebut only with an explicit, recorded reason. If you accept, edit the spec.
- **HIGH**: weigh the argument. Accept if it survives scrutiny. Rebut otherwise — and record the reason.
- **MEDIUM** and **LOW**: accept only if the change is small, clearly improves the spec, and aligns with the author's intent. Otherwise drop silently — do not record rebuttals for these.

**For each accepted item:** apply an `Edit` to the spec file in place. The spec evolves across rounds.

**For each rebutted CRITICAL or HIGH item:** append an entry to a `## Design Decisions (Round N)` section at the bottom of the spec. Create the section if it does not exist. Entry format:

```markdown
### <gap title>
- **Critic:** <one-sentence summary of the finding>
- **Decision:** rejected — <your reasoning, one or two sentences>
```

### Phase C — Report and gate

In a single user-facing message, report:

```
Round N complete.

Accepted (applied to spec):
- <bullet for each accepted change, including severity tag>

Rebutted (logged in Design Decisions):
- <bullet for each rebutted CRITICAL/HIGH, including severity tag and reason>

Dropped silently (MEDIUM/LOW with no clear win):
- <count only, e.g. "3 MEDIUM, 1 LOW">
```

Then ask: **"Run another red-team round?"**

- **User says no (or anything indicating done):** end the skill. Return the (revised) spec path. Caller — or the user — proceeds.
- **User says yes:** go to Phase D.

### Phase D — Round N+1 (resume critic with prior context)

1. Compute the new output path: same pattern but with `round-<N+1>` instead of `round-N`.

2. Resume the same critic via `SendMessage` — do not start a new agent:

   ```
   SendMessage({
     to: "<the critic_name captured in Phase A step 2>",
     prompt: "The spec was revised. Path is still <absolute spec path>. Changes since your last round: <bullet summary of accepted items>. Rebuttals I recorded against your earlier findings: <bullet summary with reasons>. This is round <N+1>. Write new findings to <absolute round-N+1 output path>. Follow the round-2+ instructions in your system prompt."
   })
   ```

3. Read the new findings file. Loop back to Phase B with the new round number.

## Files this skill writes

- Mutations to the spec (Edit calls)
- One findings file per round, in the spec's directory, named `<spec-basename>-redteam-round-<N>.md`

## Files this skill never writes

- Anything outside `<spec-directory>/`
- Any code, test, or implementation file

## Termination

The skill ends when the user declines another round. Do not auto-decide convergence. Do not invoke `writing-plans` — that's the caller's job (or the wrapper skill's job).
````

- [ ] **Step 3: Verify the skill file is well-formed**

Run: `head -3 ~/.claude/skills/red-team-spec/SKILL.md`
Expected: first three lines are `---`, `name: red-team-spec`, then a `description:` line beginning with "Run an adversarial...".

Run: `wc -l ~/.claude/skills/red-team-spec/SKILL.md`
Expected: roughly 90-110 lines.

---

### Task 3: Create the `redteam-brainstorm` wrapper skill

**Files:**
- Create: `~/.claude/skills/redteam-brainstorm/SKILL.md`

This is a thin orchestrator. It contains no critique logic — it delegates to `superpowers:brainstorming`, then `red-team-spec`, then `superpowers:writing-plans`.

- [ ] **Step 1: Create the skill directory**

Run: `mkdir -p ~/.claude/skills/redteam-brainstorm`
Expected: no output. Directory exists.

- [ ] **Step 2: Write the wrapper skill file**

Write the following content to `~/.claude/skills/redteam-brainstorm/SKILL.md`:

````markdown
---
name: redteam-brainstorm
description: Brainstorm a spec with superpowers:brainstorming, then automatically run an adversarial Red Team critique loop on the result, then transition to superpowers:writing-plans. Single entry point for the full brainstorm-with-critique workflow. Use when the user invokes /redteam-brainstorm or asks for a brainstorming session that should be stress-tested before planning.
---

# Red-Team-Augmented Brainstorming

You are running a three-phase workflow that wraps the standard superpowers brainstorming flow with an adversarial review step between spec-writing and plan-writing.

## Phase 1 — Brainstorm

Invoke the `superpowers:brainstorming` skill via the `Skill` tool. Follow it through to completion: clarifying questions, design proposals, spec write, spec self-review, user approval.

The brainstorming skill ends by directing you to invoke `superpowers:writing-plans`. **Do not do that yet.** Per the superpowers priority rule (user instructions override plugin skills), this wrapper's instructions take precedence over brainstorming's terminal-state directive.

When brainstorming finishes, you should have:
- A spec file at `docs/superpowers/specs/<date>-<topic>-design.md` (absolute path resolvable from cwd)
- User approval of that spec

Record the spec's absolute path. You need it for Phase 2.

## Phase 2 — Red Team

Invoke the `red-team-spec` skill via the `Skill` tool, passing the spec path as `args`:

```
Skill({ skill: "red-team-spec", args: "<absolute spec path from Phase 1>" })
```

Let it run its loop. It will:
- Dispatch the `red-team-critic` subagent (fresh context for round 1)
- Apply accepted findings to the spec in place
- Record rebutted CRITICAL/HIGH items in a `## Design Decisions` section
- Ask the user whether to run another round
- Resume the same critic via `SendMessage` for any rounds 2+
- Terminate when the user declines another round

When `red-team-spec` returns, the spec file has been revised in place. Move on.

## Phase 3 — Plans

Invoke `superpowers:writing-plans` via the `Skill` tool. It will pick up the (now red-teamed) spec and produce the implementation plan.

## Non-goals for this wrapper

- This skill contains no critique logic. All critique behavior lives in `red-team-spec` and `red-team-critic`.
- This skill does not skip Phase 2. If the user wants plain brainstorming without critique, they should invoke `/superpowers:brainstorming` directly instead.
- This skill does not modify the brainstorming or writing-plans plugin skills.
````

- [ ] **Step 3: Verify the wrapper file**

Run: `head -3 ~/.claude/skills/redteam-brainstorm/SKILL.md`
Expected: `---`, `name: redteam-brainstorm`, then a `description:` line beginning with "Brainstorm a spec...".

Run: `ls ~/.claude/skills/redteam-brainstorm/`
Expected: prints `SKILL.md`.

---

### Task 4: End-to-end smoke check

This task confirms Claude Code actually recognizes the new artifacts and the workflow runs. No automated tests possible — verification is manual via a fresh Claude Code session.

**Files:** none modified.

- [ ] **Step 1: Confirm Claude Code can see the new skills and agent**

Open a fresh Claude Code session in any directory. Send a message asking: "Show me the skills and agents that include the words 'red-team' or 'redteam' in their name."

Expected: Claude lists `red-team-spec`, `redteam-brainstorm` (under skills) and `red-team-critic` (under agents). If any are missing, double-check filenames and YAML frontmatter (Claude only registers files with valid frontmatter).

- [ ] **Step 2: Smoke test `red-team-spec` on the design doc itself**

In a fresh session at `/home/sbbae/project/claude`, run:

```
/red-team-spec docs/superpowers/specs/2026-05-14-red-team-spec-critique-design.md
```

Expected behavior:
- Claude announces it's invoking `red-team-spec`.
- Claude dispatches `red-team-critic` via `Agent()`.
- After a moment, a file appears at `docs/superpowers/specs/2026-05-14-red-team-spec-critique-design-redteam-round-1.md`.
- Claude reads it, applies any accepted edits to the design doc, and reports a round-1 summary in the chat.
- Claude asks "Run another red-team round?"
- Answer **no**. The skill should terminate cleanly.

Verify the round-1 findings file exists:

```
ls -la /home/sbbae/project/claude/docs/superpowers/specs/2026-05-14-red-team-spec-critique-design-redteam-round-1.md
```

Expected: file exists, non-zero size, contains the four severity sections (CRITICAL/HIGH/MEDIUM/LOW).

- [ ] **Step 3: Smoke test the round-2 SendMessage path**

Re-run the smoke from Step 2, but this time when Claude asks "Run another red-team round?", answer **yes**.

Expected:
- Claude uses `SendMessage` (not a fresh `Agent()`) targeting the round-1 critic.
- A new file appears at `...-redteam-round-2.md`.
- The round-2 findings reference (drop, escalate, or build on) the round-1 critic's prior items — proving context persistence.

If the round-2 findings just re-list the round-1 items verbatim, the persistent-context wiring isn't working. Inspect the prompt the wrapper sent and the captured `critic_name`, then patch the skill instructions.

- [ ] **Step 4: Smoke test the full wrapper**

In a fresh session, run:

```
/redteam-brainstorm
```

Give Claude a tiny brainstorming topic ("a CLI flag to skip cache on `myapp build`"). Walk through:
- brainstorming questions → spec write → spec approval
- red-team round 1 → decline further rounds
- handoff to writing-plans

Expected: all three phases complete without manual intervention between phases. The plan file appears under `docs/superpowers/plans/`.

If brainstorming tries to invoke `writing-plans` directly after spec write (bypassing red-team), the priority-override instruction in `redteam-brainstorm/SKILL.md` may need to be made more emphatic. Tighten the wording and re-test.

---

## Self-Review

**Spec coverage:**
- Component 1 (`red-team-critic` agent file with persona, tool restriction, output format, round 2+ behavior) → Task 1
- Component 2 (`red-team-spec` standalone skill with phases A-D) → Task 2
- Component 3 (`redteam-brainstorm` wrapper) → Task 3
- Persistent context across rounds (Agent then SendMessage) → wired into Task 2 Phase A and Phase D, smoke-tested in Task 4 Step 3
- All-severity review (no MEDIUM/LOW filter) → wired into Task 2 Phase B
- Auto-revise with disclosure → wired into Task 2 Phases B and C
- Risk: brainstorming's terminal-state override → wired into Task 3 Phase 1 wording, smoke-tested in Task 4 Step 4
- Files written per session (spec mutation + per-round findings) → matches Task 2 Phase D path scheme

**Placeholder scan:** No "TODO", "TBD", "fill in later", or vague handwaves. Every file's full content is in the plan.

**Type consistency:** Filenames and paths are consistent across tasks. The agent name `red-team-critic` is identical in frontmatter, dispatch examples, and references. Round filename pattern `<spec-basename>-redteam-round-<N>.md` matches across spec, skill, and smoke tests. Section name `## Design Decisions (Round N)` consistent between spec and skill instructions.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-14-red-team-spec-critique.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
