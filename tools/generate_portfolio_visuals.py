"""Regenerate recruiter-facing SVG assets from the verified scheduler study summary."""

from __future__ import annotations

import argparse
from pathlib import Path

from nr_ran_sim.reporting.portfolio import generate_portfolio_visuals


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--summary",
        type=Path,
        default=Path("evidence/scheduler-study-v1/metrics/summary.json"),
    )
    parser.add_argument("--output", type=Path, default=Path("docs/assets"))
    arguments = parser.parse_args()
    manifest = generate_portfolio_visuals(arguments.summary, arguments.output)
    print(f"generated {len(manifest['assets'])} visuals in {arguments.output}")


if __name__ == "__main__":
    main()
