#!/usr/bin/env python3
"""verify_spec_facts.py — deterministic verification gate for spec markdown.

Cross-references the `## Claimed facts` block in a spec against a
verified_facts/*.yaml file. Catches block-level mis-readings where the spec
claims a fact (e.g., "free_slice is chunk_shared") that contradicts the
audited reality (yaml says "per_chunk").

Usage:
    python tools/verify_spec_facts.py <spec.md> <verified_facts.yaml>

Exit codes:
    0 — all claims consistent with yaml
    1 — at least one contradiction found
    2 — usage error (missing args, file not found, malformed claimed_facts)

The spec must contain a fenced yaml block under a `## Claimed facts` heading.
Recognized claim keys:
    cacheable_blocks: list[str]
        Each name must have scope==chunk_shared in
        yaml.translate_dispatch.prompt_template_components.<name>.scope

    per_chunk_blocks: list[str]
        Each name must have scope==per_chunk.

    min_cache_tokens_<model_slug>: int
        Must equal yaml.caching.min_cache_tokens.<model_slug>.
        model_slug uses dashes replaced by underscores (claude_sonnet_4_6).

    llm_entry_function: str
        Substring of yaml.translate_dispatch.llm_entry_point_active.

    llm_entry_module: str
        Substring of yaml.translate_dispatch.llm_entry_point_active.

    llm_entry_return_semantics: str
        Equal to yaml.translate_dispatch.llm_entry_return_semantics.

    confirmed_absent: list[str]
        Each name must be in yaml.confirmed_absent_symbols.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("ERROR: PyYAML not installed. pip install pyyaml")


def _extract_claimed_facts_block(spec_path: Path) -> dict:
    """Pull the ```yaml ... ``` block under `## Claimed facts` heading."""
    text = spec_path.read_text(encoding="utf-8")
    # Match `## Claimed facts` then a fenced yaml block (allow blank lines / prose between).
    pat = re.compile(
        r"^##\s+Claimed facts\s*$.*?^```yaml\s*$\n(?P<body>.*?)^```\s*$",
        re.MULTILINE | re.DOTALL,
    )
    m = pat.search(text)
    if not m:
        sys.exit(
            f"ERROR: spec at {spec_path} has no `## Claimed facts` section "
            "with a fenced yaml block. The verification gate requires it."
        )
    try:
        return yaml.safe_load(m.group("body")) or {}
    except yaml.YAMLError as exc:
        sys.exit(f"ERROR: claimed_facts yaml in {spec_path} is malformed: {exc}")


def _check_block_scopes(
    spec_value: list[str],
    expected_scope: str,
    yaml_facts: dict,
    contradictions: list[str],
    claim_name: str,
) -> None:
    components = (
        yaml_facts.get("translate_dispatch", {})
        .get("prompt_template_components", {})
    )
    if not components:
        contradictions.append(
            f"{claim_name}: yaml lacks translate_dispatch.prompt_template_components"
        )
        return
    for name in spec_value:
        info = components.get(name)
        if info is None:
            contradictions.append(
                f"{claim_name}: '{name}' not found in yaml prompt_template_components"
            )
            continue
        actual = info.get("scope")
        if actual != expected_scope:
            contradictions.append(
                f"{claim_name}: '{name}' has yaml scope='{actual}' "
                f"but spec claims '{expected_scope}'"
            )


def _check_min_cache_tokens(
    spec_claims: dict, yaml_facts: dict, contradictions: list[str]
) -> None:
    yaml_table = yaml_facts.get("caching", {}).get("min_cache_tokens", {})
    if not yaml_table:
        return
    for key, spec_val in spec_claims.items():
        if not key.startswith("min_cache_tokens_"):
            continue
        # claude_sonnet_4_6 → claude-sonnet-4-6
        slug = key[len("min_cache_tokens_"):]
        model = slug.replace("_", "-")
        yaml_val = yaml_table.get(model)
        if yaml_val is None:
            contradictions.append(
                f"min_cache_tokens: spec claims {model}={spec_val} "
                f"but yaml has no entry for {model}"
            )
            continue
        if yaml_val != spec_val:
            contradictions.append(
                f"min_cache_tokens: {model}: spec={spec_val}, yaml={yaml_val} "
                f"(source: {yaml_facts['caching'].get('min_cache_tokens_source', 'unknown')})"
            )


def _check_llm_entry(
    spec_claims: dict, yaml_facts: dict, contradictions: list[str]
) -> None:
    dispatch = yaml_facts.get("translate_dispatch", {})
    active = dispatch.get("llm_entry_point_active", "")
    if "llm_entry_function" in spec_claims:
        spec_fn = spec_claims["llm_entry_function"]
        if spec_fn not in active:
            contradictions.append(
                f"llm_entry_function: spec='{spec_fn}' not found in yaml "
                f"llm_entry_point_active='{active}'"
            )
    if "llm_entry_module" in spec_claims:
        spec_mod = spec_claims["llm_entry_module"]
        if spec_mod not in active:
            contradictions.append(
                f"llm_entry_module: spec='{spec_mod}' not found in yaml "
                f"llm_entry_point_active='{active}'"
            )
    if "llm_entry_return_semantics" in spec_claims:
        spec_ret = spec_claims["llm_entry_return_semantics"]
        yaml_ret = dispatch.get("llm_entry_return_semantics")
        if yaml_ret != spec_ret:
            contradictions.append(
                f"llm_entry_return_semantics: spec='{spec_ret}', yaml='{yaml_ret}'"
            )


def _check_confirmed_absent(
    spec_claims: dict, yaml_facts: dict, contradictions: list[str]
) -> None:
    if "confirmed_absent" not in spec_claims:
        return
    yaml_absent = set(yaml_facts.get("confirmed_absent_symbols", []))
    for sym in spec_claims["confirmed_absent"]:
        if sym not in yaml_absent:
            contradictions.append(
                f"confirmed_absent: spec claims '{sym}' is absent but yaml "
                "confirmed_absent_symbols does not include it (may exist!)"
            )


def main() -> int:
    p = argparse.ArgumentParser(description="Verify spec claimed_facts vs verified_facts yaml")
    p.add_argument("spec", type=Path, help="path to spec markdown")
    p.add_argument("yaml_path", type=Path, help="path to verified_facts/*.yaml")
    args = p.parse_args()

    if not args.spec.exists():
        sys.exit(f"ERROR: spec not found: {args.spec}")
    if not args.yaml_path.exists():
        sys.exit(f"ERROR: yaml not found: {args.yaml_path}")

    spec_claims = _extract_claimed_facts_block(args.spec)
    yaml_facts = yaml.safe_load(args.yaml_path.read_text(encoding="utf-8")) or {}

    contradictions: list[str] = []

    if "cacheable_blocks" in spec_claims:
        _check_block_scopes(
            spec_claims["cacheable_blocks"], "chunk_shared",
            yaml_facts, contradictions, "cacheable_blocks",
        )
    if "per_chunk_blocks" in spec_claims:
        _check_block_scopes(
            spec_claims["per_chunk_blocks"], "per_chunk",
            yaml_facts, contradictions, "per_chunk_blocks",
        )
    _check_min_cache_tokens(spec_claims, yaml_facts, contradictions)
    _check_llm_entry(spec_claims, yaml_facts, contradictions)
    _check_confirmed_absent(spec_claims, yaml_facts, contradictions)

    if contradictions:
        print(f"FAIL: {len(contradictions)} contradiction(s) in {args.spec.name}", file=sys.stderr)
        for c in contradictions:
            print(f"  - {c}", file=sys.stderr)
        return 1

    print(f"PASS: all {len(spec_claims)} claim(s) in {args.spec.name} consistent with {args.yaml_path.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
