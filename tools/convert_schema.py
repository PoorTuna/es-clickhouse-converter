"""Offline CLI: ES _mapping JSON → ClickHouse DDL. No server, no network.

    python tools/convert_schema.py --mapping idx.mapping.json \
        --config idx.config.json [--sample data.ndjson] [--out idx.sql]

Wraps the same ``convert_index`` orchestrator the API uses, so CLI and service
emit identical DDL.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ch_converter.conversion import convert_index
from ch_converter.sampling import SampleProfile, profile_samples


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    mapping_raw = _load_json(args.mapping)
    config_raw = _load_json(args.config) if args.config else None
    profile = _load_profile(args.sample)
    index_name = args.index_name or args.mapping.stem.split(".")[0]

    artifacts = convert_index(index_name, mapping_raw, config_raw, profile)
    _write_output(artifacts.ddl, args.out)
    _report_advisories(artifacts.warnings, artifacts.suggestions)
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert an ES mapping to ClickHouse DDL.")
    parser.add_argument("--mapping", type=Path, required=True, help="ES _mapping JSON file.")
    parser.add_argument("--config", type=Path, help="Per-index conversion config JSON.")
    parser.add_argument("--sample", type=Path, help="NDJSON sample for type narrowing.")
    parser.add_argument("--out", type=Path, help="Write DDL here (default: stdout).")
    parser.add_argument("--index-name", help="Table name (default: mapping file stem).")
    return parser.parse_args(argv)


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_profile(sample_path: Path | None) -> SampleProfile | None:
    return profile_samples(sample_path) if sample_path else None


def _write_output(ddl: str, out_path: Path | None) -> None:
    if out_path is None:
        print(ddl)
        return
    out_path.write_text(ddl + "\n", encoding="utf-8")
    print(f"wrote {out_path}", file=sys.stderr)


def _report_advisories(warnings: tuple[str, ...], suggestions: tuple[str, ...]) -> None:
    for message in warnings:
        print(f"WARNING: {message}", file=sys.stderr)
    for message in suggestions:
        print(f"SUGGESTION: {message}", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
