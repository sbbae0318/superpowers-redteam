---
name: red-team-spec
description: Run an adversarial Red Team critique loop on a spec or plan document. Dispatches a clean-context subagent (red-team-critic) to find gaps, then auto-revises the spec in place based on findings the main agent accepts. User-gated per round with the critic's own readiness verdict surfaced before the gate. Use when the user wants to stress-test a spec before implementing it, or invokes /red-team-spec <path>.
---

# Red Team Spec Critique Loop

You are running an adversarial review of a single spec or plan document. A subagent (`red-team-critic`) reads it and writes structured findings — including a 1–10 readiness verdict — to a sibling file. You then revise the spec, surface the verdict to the user, and ask whether to run another round.

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
     prompt: "Review the spec at <absolute spec path>. This is round 1. Write your findings to <absolute round-1 output path>. Follow the output format from your system prompt exactly — include the Verdict block at the top."
   })
   ```

3. After the subagent returns, read the round-1 output file. Extract the Verdict block (Readiness score, rationale, Recommendation) — you will surface it to the user verbatim in Phase C.

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

Surface the critic's **Verdict** prominently before anything else. The user must see it before deciding whether to run another round — that is the whole point of the verdict. Single user-facing message in this exact shape:

```
═══════════════════════════════════════════
 Red Team Round N Verdict
═══════════════════════════════════════════
 Readiness: X/10 — <critic's one-line rationale, verbatim>
 Recommendation: <critic's recommendation, verbatim>

──────────────── Round N changes ────────────────

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

Never skip the Verdict surfacing. If a user repeatedly runs rounds without reading the verdict, the loop is degrading into token-burn. The verdict is the user's signal for when to stop.

### Phase D — Round N+1 (context-rich fresh dispatch)

The Claude Code harness for this distribution does not expose a `SendMessage` tool that resumes a previously-spawned subagent — checked at design time. Round 2+ therefore dispatches a **fresh** `Agent()` but inlines all prior context through the prompt. The critic's system prompt is designed to treat pasted prior findings as its own prior position, so behavior matches a true resumed session.

1. Compute the new output path: same pattern but with `round-<N+1>` instead of `round-N`.

2. Read the prior round's findings file (doc B-N) into memory — you will paste it into the prompt.

3. Dispatch a new `Agent()` call with the full prior context inlined:

   ```
   Agent({
     subagent_type: "red-team-critic",
     description: "Round <N+1> red-team review",
     prompt: """
   This is round <N+1> of an ongoing adversarial review. Your prior findings and the main agent's response are below — treat the prior findings as YOUR OWN prior position, not as a new document.

   ── Spec under review ──
   Path: <absolute spec path>
   (Re-read this file; it has been revised since round <N>.)

   ── Your prior findings (round <N>), pasted verbatim ──
   <full contents of doc B-N>

   ── Main agent's response to your prior findings ──
   Accepted and applied to the spec:
   - <bullet per accepted item: severity + one-line summary>

   Rebutted with documented reasoning (logged in spec's Design Decisions):
   - <bullet per rebutted CRITICAL/HIGH: severity + one-line summary + rebuttal reason>

   Dropped without recorded action (MEDIUM/LOW with no clear win):
   - <count summary, e.g. "3 MEDIUM, 1 LOW">

   ── Your task ──
   Follow the round-2+ instructions in your system prompt:
   - Drop items already resolved by accepted changes
   - Re-escalate any rebuttals you find weak (quote the rebuttal text)
   - Spend most attention on new weaknesses exposed by the revisions
   - Update your Verdict score to reflect current state and reference the prior round's score in the rationale

   Write your new findings to <absolute round-(N+1) output path>. Follow the output format exactly, including the Verdict block at the top.
     """
   })
   ```

4. Read the new findings file. Loop back to Phase B with the new round number.

## Files this skill writes

- Mutations to the spec (Edit calls)
- One findings file per round, in the spec's directory, named `<spec-basename>-redteam-round-<N>.md`

## Files this skill never writes

- Anything outside `<spec-directory>/`
- Any code, test, or implementation file

## Termination

The skill ends when the user declines another round. Do not auto-decide convergence on the user's behalf — the Verdict + Recommendation is informational, not binding. Do not invoke `writing-plans`; that is the caller's job (or the wrapper skill's job).
