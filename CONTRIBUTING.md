# Contributing

Contributions are welcome when they preserve the simulator's fidelity, determinism and evidence
boundaries.

## Development setup

```console
python -m pip install uv==0.12.3
uv sync --frozen --all-extras
```

## Engineering requirements

Every behavioral change should include:

- explicit assumptions, units and supported domains;
- automated tests covering expected, boundary and failure behavior;
- deterministic replay or conservation checks where applicable;
- documentation updates for changed interfaces, models or claims; and
- an independent analytical, tabulated or reference check for model changes.

Schedulers must remain behind the immutable policy interface. Reporting must consume saved
artifacts and must not call the live simulation kernel. Published comparisons should keep
non-target factors fixed and use paired random streams when appropriate.

## Quality gate

Run before submitting a change:

```console
uv lock --check
uv run ruff format --check src tests tools
uv run ruff check src tests tools
uv run mypy src
uv run pytest
uv run python tools/generate_portfolio_visuals.py
uv run bandit -c pyproject.toml -r src
uv export --frozen --all-extras --no-emit-project --no-hashes \
  --output-file artifacts/audit-requirements.txt
uv run pip-audit --strict --requirement artifacts/audit-requirements.txt
uv build
```

Keep changes focused and do not commit generated run bundles, local environments, caches or
unreviewed evidence. Changes to accepted equations, KPI definitions or regression baselines require
an explicit impact review.

## License

By contributing, you agree that your contribution is licensed under the repository's
[MIT License](LICENSE).
