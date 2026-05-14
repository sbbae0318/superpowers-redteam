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
