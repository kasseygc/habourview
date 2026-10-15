"""Command line: `uv run axon build | report | eval`."""

from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="axon")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("build", help="Build one read-only DuckDB file per house from data/raw/*.csv")
    report = sub.add_parser("report", help="Write the funder report (small counts hidden) to out/")
    report.add_argument("--tenant", default="harbourview")
    report.add_argument("--fy", type=int, default=2025)
    ev = sub.add_parser("eval", help="Run the NL-to-spec evaluation set")
    ev.add_argument("--mode", choices=["replay", "record", "live"], default="replay")
    ev.add_argument("--model", default=None)
    nev = sub.add_parser("notes-eval", help="Score staff-note extraction against eval/notes_gold.yaml")
    nev.add_argument("--mode", choices=["replay", "record", "live"], default="replay")
    nev.add_argument("--model", default=None)
    args = parser.parse_args(argv)

    if args.command == "build":
        from axon.warehouse import build_all

        for meta in build_all():
            print(f"built {meta['tenant_id']}: capacity {meta['capacity']}, as of {meta['as_of']:%Y-%m-%d}")
        return 0
    if args.command == "report":
        from axon.report.funder import write_report

        path = write_report(args.tenant, args.fy)
        print(f"wrote {path}")
        return 0
    if args.command == "notes-eval":
        from axon.notes.evaluate import run_cli as notes_cli

        return notes_cli(mode=args.mode, model=args.model)
    if args.command == "eval":
        from axon.evaluation import run_cli

        return run_cli(mode=args.mode, model=args.model)
    return 1


if __name__ == "__main__":
    sys.exit(main())
