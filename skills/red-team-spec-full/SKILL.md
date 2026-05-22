---
name: red-team-spec-full
description: Full 6-layer multi-agent red-team protocol — L1 audit + L3 deterministic gates + L4 per-spec critic + L5 cross-spec critic (series mode) + L6 banner drift (R2+). Use for verified-facts workflows (OpenMontage-style) or spec series where cross-spec contract issues matter. For lighter generic critique, use `red-team-spec` instead.
---

# Red Team Spec Critique — Full 6-Layer Path

You are running the full multi-agent red-team protocol. The slim path (`red-team-spec`) handles L3+L4+L6. This full path adds **L1 audit** (codebase fact-finding subagent) and, in series mode, **L5 cross-spec critic** (one critic reads all N specs together).

The full path assumes `~/.claude/tools/redteam/` exists and contains the three tool files. If any tool is missing, halt and tell the user to re-run `install.sh` — full path does NOT silently skip gates (use the slim path for tool-absent environments).

## Input

`/red-team-spec-full <path1> [path2 ...]`

- 1 path → single mode (Phase 5 cross-spec skipped)
- 2+ paths → series mode (Phase 5 fires once after all per-spec round-1 critics complete)
- Paths must be absolute or relative to cwd.

## Workflow

### Phase 1 — Audit per spec (L1, conditional)

For each spec, read its frontmatter:

- If the spec has `verified_against: <path>` AND the referenced yaml file exists → audit already done; skip Phase 1 for this spec.
- Otherwise: dispatch a fresh `general-purpose` subagent with the audit prompt template (see "Audit prompt" below). Wait for the yaml. Write it to `<spec-dir>/verified_facts/<spec-basename>.yaml`. Update the spec frontmatter to add or replace `verified_against:`. **Pause for user review of the generated yaml** before proceeding to Phase 2 — audit accuracy is load-bearing.

**Audit prompt template:**

```
Codebase fact-finding mission. DO NOT design or write spec.
Target: <repo root path>
Topic: <derived from spec title or filename>

Investigate and return a single YAML in your final assistant message:
1. Relevant module signatures (with file:line)
2. Data schema / column names / config keys
3. Existing related symbols (functions, classes, sentinels)
4. Confirmed absent symbols (claimed but not present)
5. key_surprises — things that invalidate common assumptions

Required fields for downstream Gate C:
- confirmed_absent_symbols: [list]
- cacheable_blocks: [list]
- per_chunk_blocks: [list]
- llm_entry_function, llm_entry_module, llm_entry_return_semantics (if applicable)

Category G avoidance: do NOT just report default constants. Also
report what values are actually passed at call sites. If a constant
says "v3_2" but production code passes "v3_3", record BOTH.

Return ONLY the YAML, no commentary. Do NOT call Write.
```

### Phase 2 — Gates per spec (L3)

For each spec, run the three gates in sequence:

1. **Gate B (import sandbox)** — fire iff `claimed_imports:` block present.
2. **Gate C** — `python3 ~/.claude/tools/redteam/verify_spec_facts.py <spec> <yaml>` — fire iff `## Claimed facts` block AND `verified_against:` present.
3. **Gate D2** — `python3 ~/.claude/tools/redteam/verify_signature_preservation.py <spec> <codebase_root>` — fire iff `signature_changes:` block present.

Tool missing = halt with error ("install incomplete; re-run install.sh"). FAIL = report + ask `[abort / proceed-with-warning]`. PASS = continue.

### Phase 3 — Per-spec critic (L4)

Identical to `red-team-spec` slim Phase B. For each spec, dispatch round-1 critic; persist findings to `<spec-dir>/<spec-basename>-redteam-round-<N>.md`.

### Phase 4 — Apply findings

Identical to `red-team-spec` slim Phase C. Anchored edits, disclosure schema, `## Design Decisions (Round N)` for rebuts.

### Phase 5 — Cross-spec critic (L5, series mode only)

Skipped in single mode. In series mode, after all per-spec round-1 critics complete and Phase 4 edits land:

```
Agent({
  subagent_type: "red-team-critic",
  description: "Cross-spec red-team review (round <N>)",
  prompt: """
Cross-spec red-team review. Read all <N> specs as a single integrated plan series.

Specs (in dependency order):
- <abs path 1>
- <abs path 2>
- ...

Per-spec round-<N> findings (do NOT repeat — already in per-spec docs B):
<one-line summary per spec, including CRITICAL category counts>

Your task: per the Cross-spec mode section in your system prompt, focus
on category E (cross-spec contract mismatches), plus any D / G issues
visible only when specs are read together.

Return findings as your final assistant message in the standard format
including the CRITICAL category count block. The main agent will
persist to <abs cross-output path>. Do NOT call Write.
"""
})
```

Persist cross-spec findings to `<common-parent-dir>/<series-tag>-redteam-cross-round-<N>.md`. The series tag is derived from the common prefix of the input paths (e.g., specs named `2026-05-19-vl-wc-phase-A.md`, `2026-05-19-vl-wc-phase-B.md`, ... → series tag `2026-05-19-vl-wc`).

### Phase 6 — Banner drift (L6, R2+ only)

For each spec, if N ≥ 2: `python3 ~/.claude/tools/redteam/verify_banner_vs_body.py <spec>`. Append findings to per-spec round-N doc B under `## Layer 6 — Banner drift check`.

### Phase 7 — State YAML + aggregate report + gate

For each spec, maintain `<spec-dir>/<spec-basename>-redteam-state.yaml`:

```yaml
spec: <spec-basename>
rounds:
  - round: 1
    CRITICAL_count: <n>
    CRITICAL_breakdown_by_category:
      A: 0
      B: 0
      C: <n>
      D: <n>
      E: <n>
      F: 0
      G: 0
  - round: 2
    CRITICAL_count: <n>
    CRITICAL_breakdown_by_category: {...}
    delta_R1_to_R2:
      total: <n>
      genuinely_resolved: <n>
      banner_only_unresolved: <n>
```

If a per-spec state YAML exists from a prior session, append the new round; do not overwrite.

**Aggregate report** (one user-facing message):

```
═══════════════════════════════════════════
 Cross-Spec Red Team Round N Verdict     (~tokens: <estimate>)
═══════════════════════════════════════════
 Cross-spec readiness: X/10 — <rationale citing top unresolved cross-spec finding>
 Recommendation: <verbatim>
 Cross-spec CRITICAL category count: A=0 B=0 C=0 D=<n> E=<n> F=0 G=0

──────────────── Per-spec results ────────────────
- <spec-1>: <readiness>/10 — <top unresolved> [A B C D E F G counts]
- <spec-2>: <readiness>/10 — <top unresolved> [counts]
- ...

──────────────── Round N changes (per spec) ────────────────
spec-1:
  Accepted: ...
  Rebutted: ...
  Dropped: ...
spec-2:
  ...

──────────────── Cross-spec round N changes ────────────────
Accepted: ...
Rebutted: ...

──────────────── Open issues entering next round ────────────────
- [CRITICAL] <title> (spec X, rebutted round N)
- [CROSS-CRITICAL E] <title> (cross-spec)
- [HIGH] <title> (carryover)
- ...
```

Then ask: **"Run another red-team round?"** — same gate semantics as slim path, soft max-round-5.

### Phase 8 — Round N+1 dispatch (when user says yes)

Per-spec: identical to slim Phase F.

Cross-spec (series mode only): fresh `Agent()` with prior cross-spec round-1 findings + summary of changes applied across specs + per-spec round-<N+1> findings summary, then prompt as in Phase 5.

## Files this skill writes

- Per-spec findings: `<spec-dir>/<spec-basename>-redteam-round-<N>.md`
- Per-spec state YAML: `<spec-dir>/<spec-basename>-redteam-state.yaml`
- Audit yaml (Phase 1): `<spec-dir>/verified_facts/<spec-basename>.yaml`
- Cross-spec findings (series mode): `<common-parent>/<series-tag>-redteam-cross-round-<N>.md`
- In-place spec edits: accepted-item edits + `## Design Decisions (Round N)` appendices + Phase 1 frontmatter updates

## Files this skill never writes

- Code, tests, implementation files
- Anything outside `<spec-directories>/` and `<common-parent>/`

## Termination

The skill ends when the user declines another round. Do not auto-decide convergence. Do not invoke `writing-plans`.
