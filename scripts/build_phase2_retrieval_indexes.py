from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Dict

if __package__ in (None, ""):
    PROJECT_ROOT = Path(__file__).resolve().parents[1]
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))

import config
from utils.ahu_knowledge_builder import (
    build_ahu_knowledge_assets,
    write_pattern_library,
    write_assets_to_chroma,
)


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build Phase 2 AHU retrieval indexes.")
    parser.add_argument(
        "--flows-dir",
        default="AHU程序",
        help="Directory containing AHU flows_*.json files.",
    )
    parser.add_argument(
        "--output-dir",
        default=config.AHU_PATTERN_LIBRARY_DIR,
        help="Directory to write normalized pattern_library outputs.",
    )
    parser.add_argument(
        "--system-type",
        default="AHU",
        help="System type label used for pattern generation.",
    )
    parser.add_argument(
        "--write-chroma",
        action="store_true",
        help="Write generated assets into Chroma collections.",
    )
    parser.add_argument(
        "--persist-dir",
        default=config.CHROMA_PERSIST_DIR,
        help="Chroma persistence directory when --write-chroma is enabled.",
    )
    return parser


def main(argv: list[str] | None = None) -> Dict[str, Any]:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    build_command = "python scripts/build_phase2_retrieval_indexes.py"
    build_command += f" --flows-dir \"{args.flows_dir}\""
    build_command += f" --output-dir \"{args.output_dir}\""
    build_command += f" --system-type \"{args.system_type}\""
    if args.write_chroma:
        build_command += f" --write-chroma --persist-dir \"{args.persist_dir}\""

    assets = build_ahu_knowledge_assets(
        flows_dir=args.flows_dir,
        output_dir=args.output_dir,
        system_type=args.system_type,
    )
    assets.setdefault("manifest", {})["build_command"] = build_command

    print(json.dumps(assets.get("manifest", {}), ensure_ascii=False, indent=2))
    print(f"subflow_templates: {len(assets.get('subflow_templates', []))}")
    print(f"system_patterns: {len(assets.get('system_patterns', []))}")
    print(f"pattern_library: {args.output_dir}")

    if args.write_chroma:
        written = write_assets_to_chroma(assets, persist_dir=args.persist_dir)
        write_pattern_library(args.output_dir, assets)
        print(json.dumps(written, ensure_ascii=False, indent=2))
        print(f"persist_dir: {args.persist_dir}")

    return assets


if __name__ == "__main__":
    main()
