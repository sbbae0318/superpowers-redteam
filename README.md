# superpowers-redteam

Adversarial Red Team critique loop for Claude Code spec documents. Wraps `superpowers:brainstorming` with a dismissive critic subagent that finds gaps the original author missed, then auto-revises the spec based on findings.

## Why

LLM-written specs suffer from authorial blind spots — the same model that drafted the doc rarely notices its own waved-past complexity, hidden assumptions, or YAGNI violations. Dispatching a *clean-context* subagent under an adversarial persona (treating the spec as "a competitor AI's hasty submission") surfaces weaknesses you'd otherwise carry into implementation.

This package gives you that loop as three reusable Claude Code artifacts.

## Components

| File | Role |
|---|---|
| `agents/red-team-critic.md` | Reusable adversarial-reviewer subagent. Tools restricted to `Read`, `Grep` — cannot mutate the spec. |
| `skills/red-team-spec/SKILL.md` | **Slim path (default).** L3 deterministic gates (when spec has structured blocks) + L4 per-spec critic + L6 banner drift on R2+. Round 1 fresh `Agent()`; rounds 2+ context-rich `Agent()` (no `SendMessage` in this CLI — see design doc). Graceful degrade: specs without structured blocks behave like v1 generic critique. |
| `skills/red-team-spec-full/SKILL.md` | **Full 6-layer path.** Adds L1 codebase audit (general-purpose subagent → `verified_facts/<topic>.yaml`) and, in series mode (≥2 spec paths), L5 cross-spec critic. Requires the three tools to be installed at `~/.claude/tools/redteam/`. Use for verified-facts workflows or spec series. |
| `skills/red-team-spec-auto/SKILL.md` | **Auto / unattended path (v2.1).** Single-spec only. Runs up to 10 rounds without per-round user gate; terminates on objective signals (CRITICAL+HIGH title-set stability, count-stable plateau, hard cap, context budget, gate failure, critic failure, mutation caps, severity oscillation). CRITICAL auto-accept, HIGH auto-rebut, MED/LOW skip. Concurrency lock + round-0 snapshot for safe revert. Use when you have abundant model-token budget and want unattended convergence. |
| `skills/red-team-conversation/SKILL.md` | Synthesizes the **current dialogue** (decisions, implementations, deferred items, untested assumptions) into a retrospective markdown document, then hands it to `red-team-spec` (slim) for critique. |
| `skills/redteam-brainstorm/SKILL.md` | Wrapper composing `superpowers:brainstorming → red-team-spec → superpowers:writing-plans` into one entry point. Always invokes the slim path. |
| `tools/verify_spec_facts.py` | **Gate C** — deterministic yaml-vs-spec fact check. Compares `## Claimed facts` block against `verified_against:` yaml. Sub-second, $0. |
| `tools/verify_signature_preservation.py` | **Gate D2** — AST diff on a `signature_changes:` block. Catches silent kwarg drops in refactors. |
| `tools/verify_banner_vs_body.py` | **Layer 6** — R2+ banner-vs-body drift. Greps backticked tokens from a R2+ banner block against the spec body. |

## Install

Requires Claude Code with the `superpowers` plugin installed.

```bash
git clone https://github.com/sbbae0318/superpowers-redteam.git
cd superpowers-redteam
./install.sh
```

The installer copies files to `~/.claude/agents/` and `~/.claude/skills/`. Idempotent — safe to re-run after pulling updates.

Manual install (if you want full control):
```bash
mkdir -p ~/.claude/agents ~/.claude/skills/red-team-spec ~/.claude/skills/redteam-brainstorm
cp agents/red-team-critic.md ~/.claude/agents/
cp skills/red-team-spec/SKILL.md ~/.claude/skills/red-team-spec/
cp skills/redteam-brainstorm/SKILL.md ~/.claude/skills/redteam-brainstorm/
```

## Usage

### Three paths (v2.1)

| Situation | Use |
|---|---|
| Single markdown spec, no audit, no gates needed (most cases) | `/red-team-spec <path>` |
| Wrapper-generated spec (from `/redteam-brainstorm` or `/red-team-conversation`) | invoked automatically as `red-team-spec` (slim) |
| OpenMontage-style spec with `verified_against:` frontmatter | `/red-team-spec-full <path>` |
| Multi-spec series (Phase A/B/C/D) — cross-spec contract checks needed | `/red-team-spec-full <path1> <path2> ...` |
| New spec without verified facts yet — want to bootstrap audit | `/red-team-spec-full <path>` (Phase 1 generates the yaml) |
| Abundant token budget + want unattended loop convergence | `/red-team-spec-auto <path>` |
| Spec that needs many rounds + you'll be away from the terminal | `/red-team-spec-auto <path>` |

**Slim path (`red-team-spec`)** is the default for most users. It gracefully skips gates when the spec doesn't have structured blocks (`claimed_imports:`, `## Claimed facts`, `signature_changes:`), so it works on any markdown spec.

**Full path (`red-team-spec-full`)** requires the deterministic tools at `~/.claude/tools/redteam/` (installed by `install.sh`). Use it when you want the full 6-layer protocol, audit included.

**Auto path (`red-team-spec-auto`)** runs the loop without per-round user gates. Terminates on objective count/title-set signals plus safety halts (mutation caps, severity oscillation, gate failure, critic failure). CRITICAL findings auto-applied, HIGH auto-rebutted to `## Design Decisions (Round N)`. Round-0 snapshot kept in state YAML so you can discard the whole loop and revert. Use when (a) you have token budget for ~10 rounds × ~30k tokens each, (b) you want unattended convergence, (c) per-round manual review isn't critical to your workflow. Not recommended for: production-critical specs (the lack of per-round human review trades safety for autonomy).

### Full workflow (brainstorm + red-team + plans in one go):
```
/redteam-brainstorm
```
Walks you through `superpowers:brainstorming` as usual, then runs the critique loop on the resulting spec, then hands off to `superpowers:writing-plans`.

**Critique an existing spec** standalone:
```
/red-team-spec docs/superpowers/specs/2026-05-14-foo-design.md
```
Runs the loop on any markdown file you point at. Useful for retro-fitting critique on specs that were brainstormed without the wrapper.

**Critique the current conversation** (decisions made in dialogue):
```
/red-team-conversation [optional-topic]
```
The skill synthesizes what just happened into `docs/superpowers/conversations/<date>-<slug>-conversation.md` — Goal, Decisions, Implementations, Discovered Issues, Open Questions, Untested Assumptions — asks you to confirm accuracy, then hands the file to the same `red-team-spec` critique loop. Use this when you want adversarial review of a working session before its conclusions calcify.

## How it works

```
┌─────────────────────────────────────────────────────────┐
│ Phase 1: superpowers:brainstorming                      │
│   → writes spec A at docs/superpowers/specs/...md       │
└────────────────────────┬────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────┐
│ Phase 2: red-team loop (per round)                      │
│                                                         │
│   round 1: Agent(red-team-critic) ──────► doc B-1       │
│            (clean context, hostile framing)             │
│            doc B-1 leads with a 1-10 Verdict block      │
│                                                         │
│   main agent reads B-N → judges each finding            │
│           accepted → Edit spec A in place               │
│           rebutted → log in ## Design Decisions         │
│                                                         │
│   user gate: Verdict (X/10 + recommendation)            │
│              shown first; user picks "another round?"   │
│      yes → Agent(critic) with prior doc B + rebuttal   │
│            summary inlined ────────────► doc B-(N+1)    │
│            (fresh dispatch, full context in prompt)     │
│      no  → exit loop                                    │
└────────────────────────┬────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────┐
│ Phase 3: superpowers:writing-plans                      │
│   → writes plan from the now-stress-tested spec         │
└─────────────────────────────────────────────────────────┘
```

### Context continuity across rounds

- **Round 1**: `Agent()` spawns a fresh subagent — no prior conversation, no anchor on the original author's framing. The "competitor AI submitted this" stance is intact.
- **Round 2+**: a **new** `Agent()` is dispatched, but the prompt inlines (a) the previous round's findings verbatim, (b) the main agent's accept/rebut decisions with reasons, (c) the revised spec path. The critic's system prompt instructs it to treat the pasted prior findings as its own prior position — so it drops resolved items, escalates weak rebuttals, and hunts for new weaknesses, exactly as a resumed session would.

**Why not `SendMessage`?** The Claude Code CLI for this distribution does not expose a `SendMessage` tool that resumes a previously-spawned subagent (verified via `ToolSearch`). The Anthropic Agent SDK has the capability, but the installed tool set does not. Explicit context-passing achieves functionally equivalent behavior — and adds auditability (the round-2 prompt is inspectable) and isolation from cross-round persona drift.

### Per-round verdict

Every round, the critic produces a 1–10 readiness score with a one-sentence rationale and an explicit recommendation:
- `9–10` → `Ready for implementation — no further rounds needed`
- `5–8` → `Another round advised — significant gaps remain`
- `1–4` → `Another round strongly advised — spec not safe to implement as-is`

The skill surfaces this verdict prominently in the user-facing report *before* the "Run another round?" gate — so you decide based on the critic's calibrated assessment, not just by skimming the diff. For round 2+, the rationale references the prior round's score so you can see whether the spec is converging or stalling.

### What the critic looks at

(used as a mental checklist by the persona, not as output headers)

- Missing requirements (functional, non-functional, operational, observability)
- Ambiguous or weasel-worded language
- Hidden assumptions never made explicit
- Oversimplifications hiding real complexity
- Untested assumptions about scale, dependencies, third parties
- Missing edge cases, security holes, scalability ceilings, failure modes
- Internal contradictions between sections
- YAGNI violations

### Output format (doc B)

```markdown
---
reviewed-spec: <spec filename>
round: <N>
---
## Verdict
**Readiness: <N>/10** — <one-sentence rationale>
**Recommendation:** <one of the three sentences from the rubric>

## CRITICAL  (spec not safe to adopt without addressing these)
- **<gap title>** — Spec says "<quote>". Why: <one line>. What's needed: <one line>.
## HIGH  (strongly recommended)
- ...
## MEDIUM  (improvements worth considering)
- ...
## LOW  (nitpicks)
- ...
```

## Design philosophy

- **User-gated, not auto-converged.** No heuristic decides when the critic is "satisfied" — the user runs another round only if they want one. LLM self-evaluation of done-ness is unreliable.
- **Severity is a prioritization hint, not a filter.** The main agent reviews all severities. CRITICAL gets strong-accept by default, MEDIUM/LOW gets accepted only when cheap and clearly-improving.
- **Audit trail.** Rebutted CRITICAL/HIGH findings get logged in a `## Design Decisions (Round N)` section at the bottom of the spec. Future readers can see what the critic argued and why it was rejected.
- **Composable.** `red-team-spec` works on any spec, not just those produced by the wrapper. The `red-team-critic` agent is reusable — you can build other workflows on top of it.

## Customization

Want a different tone (less dismissive, more constructive)? Edit `~/.claude/agents/red-team-critic.md` — the persona is in the system prompt below the frontmatter.

Want a different acceptance policy (e.g., always log MEDIUM rebuttals too)? Edit Phase B of `~/.claude/skills/red-team-spec/SKILL.md`.

Want to skip the wrapper and use a different brainstorming flow? Use `red-team-spec` standalone — it doesn't care how the spec was produced.

## Repository contents

- `agents/`, `skills/` — the installable artifacts (mirror of `~/.claude/` layout)
- `docs/design.md` — full design doc (what was brainstormed to produce this package)
- `docs/implementation-plan.md` — the implementation plan that was executed to build it
- `install.sh` — idempotent installer (run after every `git pull`)

## License

MIT — see `LICENSE`.
