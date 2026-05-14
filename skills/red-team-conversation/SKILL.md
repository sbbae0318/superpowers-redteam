---
name: red-team-conversation
description: Synthesize the current conversation into a structured markdown document and then run the red-team-spec critique loop on it. Use when the user wants to stress-test the decisions made in the recent dialogue — design choices, implementations, deferred items, assumptions — via adversarial review. Captures past decisions; does not generate plans.
---

# Red Team Conversation Critique

You are converting the current conversation into a structured retrospective document, then handing it to the existing `red-team-spec` critique loop. Unlike `red-team-spec` (which reviews a forward-looking spec), this skill reviews **what already happened in dialogue** — decisions taken, things built, assumptions made — to surface gaps before they cost the user later.

## When to use

- The user invokes `/red-team-conversation [optional topic]`
- The user asks to "red-team this conversation" / "비평해줘 이 대화" / similar
- A wrapper skill (e.g. future `redteam-discussion`) invokes it via `Skill` tool

## Workflow

### Phase 1 — Determine topic and output path

1. If the user passed a topic argument, slugify it (kebab-case, ASCII, max ~40 chars).
2. If no argument was given, derive a slug from the conversation's dominant theme. Examples: "red-team-workflow-design", "auth-middleware-refactor". Ask the user to confirm if ambiguous.
3. Compute today's date in `YYYY-MM-DD` format (use the harness-provided current date — do not guess).
4. Compute the output path: `docs/superpowers/conversations/<date>-<slug>-conversation.md`. Resolve to an absolute path relative to the current working directory.
5. Create the parent directory if it does not exist (`mkdir -p` via Bash).

### Phase 2 — Synthesize the conversation

Draft a markdown document with the **fixed section structure** below. **Source only from this conversation** — do not invent items to fill sections. If a section has nothing real to record, write `- (none captured in this conversation)` under it. Honest empty sections are far better than fabricated content, because the critic will critique whatever you write.

Required structure:

````markdown
# <Topic Title> — Conversation Retrospective

**Date:** <YYYY-MM-DD>
**Participants:** user + assistant (Claude Code)
**Status:** Draft for red-team review

## Goal & Context

<2-5 sentences. What was the user trying to accomplish? Why did this conversation happen? What constraints or background drove it?>

## Decisions

For each meaningful decision made during the conversation, one subsection:

### <Decision title>

- **Choice point:** <the question that was on the table>
- **Options considered:** <list, including any rejected ones>
- **Chosen:** <the option taken>
- **Rationale:** <why — 1-3 sentences>
- **Trade-offs accepted:** <what was given up, if anything>

## Implementations

What was actually built or modified during the conversation. For each:

- **<artifact name>** — `<file path>` — <status: working / smoke-tested only / deferred> — <one-line summary>

## Discovered Issues / Pivots

Constraints, surprises, or harness limitations discovered mid-conversation that forced design changes. For each:

- **<issue>** — Impact: <what it broke or threatened>. Handling: <how it was resolved or worked around>.

## Open Questions

Items the user and assistant agreed were unresolved or deferred. For each:

- **<question>** — Why deferred: <one line>. Suggested next step: <one line>.

## Untested Assumptions

Things that were assumed to work but were not actually verified (e.g., "the install script is idempotent — never re-ran it", "the wrapper override actually beats the plugin skill's terminal state — only documented, not tested"). For each:

- **<assumption>** — How to verify: <one concrete test or check>.
````

### Phase 3 — User review gate (critical)

Before handing the document to the critic, show the user the synthesis and ask:

> "이 회고가 정확한가요? 사실관계가 틀렸거나, 누락된 결정/이슈가 있으면 알려주세요. 다음 단계에서 critic이 이 문서를 비평합니다 — 부정확하면 critic이 가짜 갭을 찾게 됩니다."

Wait for the user's response.

- If they request corrections: edit the file, then re-ask. Loop until they confirm.
- If they confirm: write the final version to disk, proceed to Phase 4.

Do not skip this gate. The critic's value comes from accurate input. If you fabricate a section the user never agreed to, the critic will critique your fabrication, not the real conversation.

### Phase 4 — Hand off to `red-team-spec`

Invoke the standalone critique loop on the saved file:

```
Skill({ skill: "red-team-spec", args: "<absolute path to conversation file>" })
```

`red-team-spec` will:
- Dispatch the `red-team-critic` subagent (clean context, round 1)
- Apply accepted findings to the conversation document (treating it like any other spec)
- Surface a per-round Verdict
- Gate further rounds on user approval (round 2+ uses context-rich Agent dispatch)
- Terminate when the user declines another round

When `red-team-spec` returns, this skill is done. Do NOT invoke `writing-plans` — a conversation retrospective is not a plan, and there is nothing to implement from it.

## Files this skill writes

- The conversation retrospective: `docs/superpowers/conversations/<date>-<slug>-conversation.md`
- (Indirectly, via `red-team-spec`) per-round findings: `<same-dir>/<basename>-redteam-round-<N>.md`
- (Indirectly, via `red-team-spec`) `## Design Decisions (Round N)` sections appended to the retrospective itself

## Files this skill never writes

- Anything in `docs/superpowers/specs/` (this is a retrospective, not a spec)
- Plans, code, tests, implementation files
- The original artifacts of the conversation (e.g. existing repo files, settings) — those stay untouched

## Termination

The skill ends when `red-team-spec` returns control. The output to the user is:
- The (possibly multi-round-revised) retrospective file path
- A note that the file accumulates audit trail (rebutted findings + design decisions) and can be committed to a notes repo / docs folder if the user wants to keep it

Do not auto-judge convergence. The Verdict is informational.
