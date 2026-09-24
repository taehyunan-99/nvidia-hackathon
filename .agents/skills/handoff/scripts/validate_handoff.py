"""Validate a handoff receipt without producing HTML."""

from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
RENDERER_PATH = SCRIPT_DIR / "render_handoff.py"
SPEC = importlib.util.spec_from_file_location("handoff_contract", RENDERER_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"could not load handoff validator: {RENDERER_PATH}")
CONTRACT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CONTRACT)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate docs/HANDOFF.md without producing HTML."
    )
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--handoff", default="docs/HANDOFF.md")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(args.project_root).resolve()
    source = (root / args.handoff).resolve()
    try:
        source.relative_to(root)
    except ValueError:
        print("handoff validation error: handoff path escapes project root")
        return 2
    try:
        raw = source.read_text(encoding="utf-8")
        CONTRACT.parse_handoff(raw)
    except (OSError, CONTRACT.HandoffError) as exc:
        print(f"handoff validation error: {exc}")
        return 2
    print(f"Handoff is valid: {source}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())