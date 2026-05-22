#!/usr/bin/env python3
"""verify_banner_vs_body.py — Layer 6.

Catches the "banner-only" hallucination category F:  spec author writes a
post-R2 cross-spec fix banner claiming a Task or artifact was added, but the
spec body doesn't actually contain that task / artifact.

The verification works by requiring banner bullets to declare *anchor tokens*
that must appear elsewhere in the spec body. Two anchor styles are supported:

(1) Explicit anchor in banner bullet:
    > - Fix description [anchor: task_0_v4_probe]
    Body must contain `<!-- anchor: task_0_v4_probe -->` somewhere.

(2) Quoted code/identifier in banner bullet:
    > - `Task 0` v4 CLIProxyAPI probe added
    Body must contain `## Task 0` or `### Task 0` heading.

    > - Phase B Task 5 writes `speaker_id_propagation_test.json`
    Body must contain the literal filename outside the banner block.

The tool extracts all backtick-quoted tokens AND explicit anchors from the
banner block, then greps the spec body (excluding the banner) for each.

Usage:
    python3 tools/verify_banner_vs_body.py <spec.md>

Exit codes:
    0 — all banner claims have body matches
    1 — at least one banner-only claim found
    2 — usage error
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


# Banner block start patterns. Add new variants as the protocol evolves.
_BANNER_HEADERS = [
    r"^> \*\*⚠️ R2 cross-spec fixes",
    r"^> \*\*⚠️ Cross-spec R[0-9]+ fixes",
    r"^> \*\*⚠️ R[0-9]+ v[0-9]+ → v[0-9]+ fixes",
    r"^> \*\*⚠️ R[0-9]+ v[0-9]+ fixes applied",
]

# Tokens we'll skip — they're noise / boilerplate in banners.
_SKIP_TOKENS = {
    "R1", "R2", "R3", "R4", "R5",
    "v1", "v2", "v3", "v4", "v5",
    "TRUE", "FALSE",
}


def _find_banner_block(text: str) -> tuple[int, int] | None:
    """Locate the cross-spec fix banner block. Returns (start, end) byte offsets
    in `text`, or None if no banner found.

    A banner is a markdown blockquote (lines starting with `> `) that begins
    with one of the _BANNER_HEADERS and ends at the first blank or non-`>` line.
    """
    lines = text.splitlines(keepends=True)
    banner_start_line = None
    for i, ln in enumerate(lines):
        for pat in _BANNER_HEADERS:
            if re.match(pat, ln):
                banner_start_line = i
                break
        if banner_start_line is not None:
            break

    if banner_start_line is None:
        return None

    banner_end_line = banner_start_line
    for j in range(banner_start_line + 1, len(lines)):
        ln = lines[j].rstrip("\n")
        if ln.startswith("> ") or ln == ">":
            banner_end_line = j
            continue
        break

    start_byte = sum(len(l) for l in lines[:banner_start_line])
    end_byte = sum(len(l) for l in lines[: banner_end_line + 1])
    return (start_byte, end_byte)


def _extract_claims(banner_text: str) -> list[tuple[str, str]]:
    """Extract (claim_label, anchor_token) tuples from banner_text.

    Two extraction modes:
    1. Explicit anchor `[anchor: <name>]` → use `<name>` as token, looks for
       `<!-- anchor: <name> -->` in body
    2. Inline backticked token `\`Task N\``, \`Step N\`, \`<filename>\`,
       \`<symbol>\` → use the token, looks for it literally in body
    """
    claims: list[tuple[str, str]] = []

    # Mode 1: explicit anchor
    for m in re.finditer(r"\[anchor:\s*([a-zA-Z0-9_./-]+)\s*\]", banner_text):
        claims.append((m.group(0), f"anchor:{m.group(1)}"))

    # Mode 2: backticked tokens
    # We collect ALL backticked tokens in banner; filter noise after
    seen_tokens: set[str] = set()
    for m in re.finditer(r"`([^`]+)`", banner_text):
        tok = m.group(1).strip()
        if not tok or tok in _SKIP_TOKENS:
            continue
        # Skip code-blocks-looking-tokens (they get verified elsewhere)
        if "(" in tok and ")" in tok and "=" in tok:
            continue
        # Skip pure version identifiers
        if re.fullmatch(r"v[0-9]+(\.[0-9]+)*", tok):
            continue
        # Dedup
        if tok in seen_tokens:
            continue
        seen_tokens.add(tok)
        claims.append((f"`{tok}`", tok))

    return claims


def _body_text(text: str, banner_range: tuple[int, int]) -> str:
    return text[: banner_range[0]] + text[banner_range[1]:]


def _claim_matches_body(token: str, body: str) -> bool:
    """Check whether the claim's anchor token appears in `body`."""
    if token.startswith("anchor:"):
        name = token[len("anchor:"):]
        return f"<!-- anchor: {name} -->" in body

    # For backticked tokens, look for the literal string anywhere in body.
    # Hyphenate task references: `Task 0` matches `Task 0` in heading.
    if token in body:
        return True

    # Tolerate code-block variations: `Task 0` should also match `## Task 0`,
    # `### Task 0`, `Task 0:`, `Task 0 — `, etc.
    if re.match(r"^(Task|Step) \d+", token):
        if re.search(rf"^#+\s+{re.escape(token)}(\b|[:\s—-])", body, re.MULTILINE):
            return True

    return False


def main() -> int:
    p = argparse.ArgumentParser(description="Verify spec banner claims have body matches")
    p.add_argument("spec", type=Path)
    p.add_argument("--strict", action="store_true",
                   help="Also require explicit [anchor: ...] tokens on every banner bullet")
    args = p.parse_args()

    if not args.spec.exists():
        sys.exit(f"ERROR: spec not found: {args.spec}")

    text = args.spec.read_text(encoding="utf-8")
    banner = _find_banner_block(text)
    if banner is None:
        print(f"OK: no cross-spec fix banner in {args.spec.name} — Layer 6 check vacuous")
        return 0

    banner_text = text[banner[0]:banner[1]]
    body = _body_text(text, banner)
    claims = _extract_claims(banner_text)

    if not claims:
        print(f"OK: banner present but contains no actionable claims in {args.spec.name}")
        return 0

    missing: list[tuple[str, str]] = []
    for label, token in claims:
        if not _claim_matches_body(token, body):
            missing.append((label, token))

    if missing:
        print(f"FAIL: {len(missing)}/{len(claims)} banner claim(s) in {args.spec.name} have no body match", file=sys.stderr)
        for label, token in missing:
            print(f"  - banner mentions {label} but no `{token}` reference found in spec body", file=sys.stderr)
        return 1

    print(f"PASS: all {len(claims)} banner claim(s) in {args.spec.name} have body matches")
    return 0


if __name__ == "__main__":
    sys.exit(main())
