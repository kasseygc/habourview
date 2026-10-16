"""Generate a fictional house. Deterministic for a given seed.

    uv run python scripts/generate_data.py                      # writes the generated test house
    uv run python scripts/generate_data.py --prefix XY --n 300 --capacity 30 --seed 1 --out data/raw/xy.csv
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from axon.config import RAW_DIR
from axon.synth import generate, to_csv_frame


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--prefix", default="GT")
    p.add_argument("--n", type=int, default=150)
    p.add_argument("--capacity", type=int, default=16)
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--out", type=Path, default=RAW_DIR / "testhouse_residents.csv")
    args = p.parse_args()

    g = generate(prefix=args.prefix, n=args.n, capacity=args.capacity, seed=args.seed)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    to_csv_frame(g.frame).to_csv(args.out, index=False)
    manifest_path = args.out.with_name(args.out.stem.replace("_residents", "") + "_manifest.json")
    manifest_path.write_text(json.dumps(g.manifest, indent=2) + "\n")
    print(f"wrote {args.out} ({len(g.frame)} rows) and {manifest_path}")


if __name__ == "__main__":
    main()
