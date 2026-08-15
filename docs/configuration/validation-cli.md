# Configuration Validation CLI

The CLI provides the strict validation boundary, static radio/capacity inspection, and integrated
static or opt-in dynamic simulation. Validation turns human-authored YAML or JSON into a
unit-normalized, content-addressed manifest. No command claims calibrated performance.

## Supported environment

- CPython 3.11 through 3.13;
- Windows and Linux as continuously tested platforms;
- `uv` 0.12.3 for the frozen development environment;
- exact dependency resolution in `uv.lock`.

## Clean setup

```console
python -m pip install uv==0.12.3
uv sync --frozen --all-extras
```

`uv.lock` is the cross-platform environment authority. Normal work must not refresh it implicitly; dependency changes use `uv lock` intentionally and include the resulting diff.

## Validate and normalize

```console
uv run nr-ran-sim validate examples/scenarios/uma-fr1-foundation.yaml
```

The command writes the canonical manifest to standard output. To preserve it as an artifact:

```console
uv run nr-ran-sim validate examples/scenarios/uma-fr1-foundation.yaml \
  --output artifacts/uma-fr1-foundation.normalized.json \
  --quiet
```

Existing files are not replaced unless `--force` is present. Expected configuration failures return exit code 2; artifact collisions/failures return exit code 3. `--error-format json` provides a stable machine-readable error object.

## Generated schema

The typed Pydantic models are the schema source of truth. The committed JSON Schema is regenerated with:

```console
uv run nr-ran-sim schema --output schemas/scenario.schema.json --force
uv run nr-ran-sim dynamic-schema --output schemas/dynamic-radio.schema.json --force
```

The base schema deliberately keeps namespaced `extensions` open for later modules. The second
schema is the complete typed contract for the `nr-ran-sim.dynamic-radio` value. Automated tests fail
if either committed schema differs from its typed source.

## Canonical identity

Normalization:

1. rejects unknown fields and unsupported enum values;
2. validates explicit physical units through Pint;
3. converts time, frequency, distance, power, data, and rate once at the boundary;
4. checks cross-field Tier A radio domains;
5. inserts derived numerology, slot, PRB, and transmission-bandwidth fields;
6. expands documented defaults;
7. sorts identity-bearing mappings and serializes Decimal values as canonical strings;
8. hashes the normalized scientific content with SHA-256.

The digest deliberately excludes platform, timestamp, and dependency diagnostics so equivalent YAML/JSON and declaration orders produce the same scenario identity. Environment metadata is available separately:

```console
uv run nr-ran-sim environment
```

## Static radio snapshot

```console
uv run nr-ran-sim radio-snapshot \
  examples/scenarios/uma-multicell-radio.yaml \
  --master-seed 0x11111111111111111111111111111111 \
  --replication-id 0 \
  --output artifacts/radio-snapshot.json \
  --quiet
```

Both seed and replication ID are required scientific inputs. The versioned JSON scene includes
all cell/UE positions, all candidate links, LOS/shadow realizations, association, complete
link-budget terms, noise/interference, SINR, semantic RNG records, and a content digest. Existing
files remain collision-safe unless `--force` is supplied. See the
[radio propagation and link-budget guide](../radio/radio-propagation-and-link-budget.md) for equations, domains, and the saved
visualization boundary.

## Capacity snapshot

```console
uv run nr-ran-sim capacity-snapshot \
  examples/scenarios/uma-multicell-radio.yaml \
  --master-seed 0x11111111111111111111111111111111 \
  --replication-id 0 \
  --output artifacts/capacity-snapshot.json \
  --quiet
```

This command evaluates the resource grid, analytical CQI/MCS decision, exact supported TBS
procedure, and capacity for every serving-link SINR. Every UE receives a separate full-cell PRB
allocation for diagnosis; the values are not simultaneous or summable. The artifact carries its
configuration identity and parent radio-snapshot digest, uses canonical JSON, refuses collisions
without `--force`, and exposes explicit outage/zero-resource states. See the
[NR resource-grid and link-adaptation guide](../radio/nr-resource-grid-and-link-adaptation.md).

## Integrated simulation

`simulate` dispatches from the explicit fidelity profile. The unchanged Tier A profile uses the
static scheduler/KPI pipeline; dynamic-radio profiles use the dynamic kernel path.

```console
uv run nr-ran-sim simulate examples/scenarios/dynamic-fr1-mobility.yaml \
  --master-seed 0x11111111111111111111111111111111 \
  --replication-id 0 \
  --code-revision 1111111111111111111111111111111111111111 \
  --working-tree-state clean \
  --output artifacts/dynamic-simulation.json \
  --quiet
```

The canonical result contains configuration/run identity, event trace, radio frames, actual
allocation SINR diagnostics, queue/service records, transitions, KPIs, RNG provenance, and a
semantic digest. See the [mobility, handover, and FR2 guide](../radio/mobility-handover-and-fr2.md).

## Quality commands

```console
uv lock --check
uv run ruff format --check src tests
uv run ruff check src tests
uv run mypy src
uv run pytest
uv run bandit -c pyproject.toml -r src
uv export --frozen --all-extras --no-emit-project --no-hashes \
  --output-file artifacts/audit-requirements.txt
uv run pip-audit --strict --requirement artifacts/audit-requirements.txt
uv build
```

GitHub Actions runs the same gates on Windows and Linux with Python 3.11 and 3.13. The dependency and source-security checks are engineering hygiene; they are not evidence that future radio models are verified.
