#!/usr/bin/env python3
"""verify_signature_preservation.py — Gate D2.

For a spec that refactors functions, the spec declares which kwargs are
*preserved* across the refactor. This tool AST-parses the *current* source
to find which kwargs the function actually uses today, and fails if any of
those are missing from the spec's preserve_kwargs list.

Catches silent param-drop regressions like the v3 tool_choice case:
existing call_tool_use passes tool_choice={"type":"tool","name":tool_name} to
client.messages.create(), but the v3 refactor extracted _anthropic_messages_create
without listing tool_choice in its kwargs — silently breaking forced tool use.

Spec frontmatter block (under `## Claimed facts` next to claimed_facts):

```yaml
signature_changes:
  call_tool_use:
    source_file: core/sentence_strict_llm.py
    preserve_kwargs: [tool_choice, model, max_tokens, timeout, system, temperature, tools, messages]
    add_kwargs: [cache_blocks]
    remove_kwargs: []
```

Usage:
    python tools/verify_signature_preservation.py <spec.md> <codebase_root>
"""
from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("ERROR: PyYAML not installed. pip install pyyaml")


def _extract_signature_changes(spec_path: Path) -> dict:
    """Pull a yaml fenced block whose key is `signature_changes`."""
    text = spec_path.read_text(encoding="utf-8")
    # Find any yaml fence containing signature_changes:
    pat = re.compile(r"^```yaml\s*$\n(?P<body>.*?)^```\s*$", re.MULTILINE | re.DOTALL)
    for m in pat.finditer(text):
        try:
            data = yaml.safe_load(m.group("body")) or {}
        except yaml.YAMLError:
            continue
        if isinstance(data, dict) and "signature_changes" in data:
            return data["signature_changes"]
    sys.exit(
        f"ERROR: spec at {spec_path} has no `signature_changes:` yaml block. "
        "The signature-preservation gate requires it."
    )


def _kwargs_used_in_function(file_path: Path, func_name: str) -> set[str]:
    """Walk the AST of `func_name` in `file_path`; collect every keyword arg
    name used in any function call inside the body. Includes nested function
    calls (e.g., client.messages.create(tool_choice=...)).
    """
    if not file_path.exists():
        sys.exit(f"ERROR: source file not found: {file_path}")
    try:
        tree = ast.parse(file_path.read_text(encoding="utf-8"))
    except SyntaxError as exc:
        sys.exit(f"ERROR: syntax error parsing {file_path}: {exc}")

    target_fn = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func_name:
            target_fn = node
            break
    if target_fn is None:
        sys.exit(f"ERROR: function '{func_name}' not found in {file_path}")

    kwargs: set[str] = set()
    for sub in ast.walk(target_fn):
        if isinstance(sub, ast.Call):
            for kw in sub.keywords:
                if kw.arg:  # **kwargs unpacking has arg=None; skip those
                    kwargs.add(kw.arg)
    return kwargs


def _params_of_function(file_path: Path, func_name: str) -> set[str]:
    """Top-level parameter names of `func_name` (positional + keyword + kwonly).
    Excludes *args / **kwargs sentinels.
    """
    tree = ast.parse(file_path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func_name:
            args = node.args
            names = set()
            for a in args.args + args.kwonlyargs + args.posonlyargs:
                names.add(a.arg)
            return names
    return set()


def main() -> int:
    p = argparse.ArgumentParser(description="Verify spec signature_changes preserves load-bearing kwargs")
    p.add_argument("spec", type=Path, help="path to spec markdown")
    p.add_argument("codebase_root", type=Path, help="path to target codebase root")
    args = p.parse_args()

    if not args.spec.exists():
        sys.exit(f"ERROR: spec not found: {args.spec}")
    if not args.codebase_root.exists():
        sys.exit(f"ERROR: codebase root not found: {args.codebase_root}")

    sig_changes = _extract_signature_changes(args.spec)
    if not isinstance(sig_changes, dict):
        sys.exit("ERROR: signature_changes must be a dict mapping function names to declarations")

    contradictions: list[str] = []
    checks: list[str] = []

    for fn_name, decl in sig_changes.items():
        if not isinstance(decl, dict):
            contradictions.append(f"{fn_name}: declaration must be a dict")
            continue
        source_file_rel = decl.get("source_file")
        if not source_file_rel:
            contradictions.append(f"{fn_name}: missing source_file")
            continue
        source_path = args.codebase_root / source_file_rel
        preserve = set(decl.get("preserve_kwargs", []) or [])
        remove = set(decl.get("remove_kwargs", []) or [])
        add = set(decl.get("add_kwargs", []) or [])

        # 1. Kwargs currently used in function body (passed to nested calls)
        used = _kwargs_used_in_function(source_path, fn_name)
        # 2. Function's own params (passed straight through don't need to be in `used`
        #    again — they're already declared in the signature)
        params = _params_of_function(source_path, fn_name)
        # Effective "load-bearing kwargs" the refactor must preserve:
        #   (kwargs used inside the body) UNION (current function params)
        #   minus those explicitly listed for removal.
        load_bearing = (used | params) - remove

        # Each load_bearing kwarg must be EITHER in preserve_kwargs OR is being
        # renamed (i.e., add and remove together) — but we treat rename as
        # remove+add explicit declarations.
        missed = load_bearing - preserve - add
        if missed:
            for m in sorted(missed):
                contradictions.append(
                    f"{fn_name}: kwarg '{m}' is load-bearing (used in current "
                    f"body at {source_file_rel}) but spec does not list it in "
                    f"preserve_kwargs or add_kwargs. Silently dropping it "
                    f"will break the refactor."
                )
        else:
            checks.append(
                f"{fn_name}: {len(preserve)} preserved, {len(add)} added, "
                f"{len(remove)} removed — all current usage covered"
            )

        # Reverse check: any preserve kwarg not actually used in current body?
        # (Could indicate stale spec.)
        stale = preserve - load_bearing - add
        for s in sorted(stale):
            contradictions.append(
                f"{fn_name}: kwarg '{s}' listed in preserve_kwargs but NOT "
                f"found in current body — spec may be stale (function may "
                f"have already dropped it)."
            )

    if contradictions:
        print(f"FAIL: {len(contradictions)} signature-preservation issue(s) in {args.spec.name}", file=sys.stderr)
        for c in contradictions:
            print(f"  - {c}", file=sys.stderr)
        return 1

    for c in checks:
        print(f"OK: {c}")
    print(f"PASS: all signature changes preserve load-bearing kwargs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
