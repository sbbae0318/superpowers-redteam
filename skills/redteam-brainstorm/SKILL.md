---
name: redteam-brainstorm
description: Brainstorm a spec with superpowers:brainstorming, then automatically run an adversarial Red Team critique loop on the result, then transition to superpowers:writing-plans. Single entry point for the full brainstorm-with-critique workflow. Use when the user invokes /redteam-brainstorm or asks for a brainstorming session that should be stress-tested before planning.
---

# Red-Team-Augmented Brainstorming

You are running a three-phase workflow that wraps the standard superpowers brainstorming flow with an adversarial review step between spec-writing and plan-writing.

## Phase 1 — Brainstorm

Invoke the `superpowers:brainstorming` skill via the `Skill` tool. Follow it through to completion: clarifying questions, design proposals, spec write, spec self-review, user approval.

The brainstorming skill ends by directing you to invoke `superpowers:writing-plans`. **Do not do that yet.** This wrapper's instructions take precedence over brainstorming's terminal-state directive, per the explicit precedence rule documented in `superpowers:using-superpowers`:

> "Superpowers skills override default system prompt behavior, but **user instructions always take precedence**: (1) User's explicit instructions (CLAUDE.md, GEMINI.md, AGENTS.md, direct requests) — highest priority; (2) Superpowers skills — override default system behavior where they conflict; (3) Default system prompt — lowest priority."

A user-invoked wrapper skill (this one) counts as a user-directed instruction in that hierarchy, so it outranks brainstorming's terminal-state directive.

**Observable failure mode if this precedence rule shifts in a future superpowers release:** the wrapper still runs Phase 1 normally, but brainstorming's terminal call to `superpowers:writing-plans` fires *immediately after the spec is written* — skipping Phase 2 (red-team) entirely. You will notice because:

- no `<spec-basename>-redteam-round-1.md` file appears
- no Verdict box is surfaced in the chat
- a plan appears under `docs/superpowers/plans/` before red-team had a chance to mutate the spec

If you observe any of these, **stop and surface the problem to the user** — do not silently proceed without red-team. Likely diagnosis: the precedence rule in `using-superpowers` has been weakened or removed.

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
