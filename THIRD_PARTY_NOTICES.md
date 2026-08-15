# Third-Party Notices

This repository does not vendor dependency source trees. Installed dependencies remain governed by
their own licenses; `uv.lock` defines the exact resolved Python environment.

## Direct runtime dependencies

| Package | Frozen release | Metadata-reported license |
| --- | ---: | --- |
| NumPy | 2.4.6 | BSD-3-Clause, 0BSD, MIT, Zlib and CC0-1.0 components |
| Pint | 0.25.3 | BSD |
| Pydantic | 2.13.4 | MIT |
| PyYAML | 6.0.3 | MIT |

Development and build tools include Bandit (Apache-2.0), Hypothesis (MPL-2.0), mypy (MIT), pytest
and pytest-cov (MIT), Ruff (MIT), types-PyYAML (Apache-2.0), pip-audit, uv and Hatchling. Their
resolved versions are recorded in `uv.lock`; they are not incorporated into the distributed wheel.

## Standards and generated assets

- 3GPP specifications are cited as engineering sources but are not redistributed.
- The SVG diagrams and charts under `docs/assets` are project-owned code-generated assets. Chart
  values come from the checksum-verified saved summary identified by
  `docs/assets/portfolio-visuals.json`.
- `docs/assets/social-preview.png` is rendered from the project-owned `social-preview.svg` and
  contains no third-party artwork.

Dependency metadata should be rechecked when the lockfile changes. This inventory is not legal
advice.
