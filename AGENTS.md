# AGENTS.md

## Project Overview

`aiognmi` is a small Python library that provides an asynchronous gNMI client built on `grpc.aio`.

- Package code lives in `aiognmi/`.
- The public client is `aiognmi.AsyncgNMIClient`, implemented in `aiognmi/client.py`.
- Request/response helpers and gNMI path/value conversion logic live in `aiognmi/utils.py`, `aiognmi/response.py`, and `aiognmi/models.py`.
- `aiognmi/proto/` contains vendored OpenConfig gNMI `.proto` files and generated Python protobuf/gRPC modules.
- Tests live in `tests/`; the current suite focuses on utility/path conversion behavior.

## Environment Setup

Supported Python versions are 3.12, and 3.13. The package uses setuptools via `pyproject.toml`; there is no lockfile.

Set up a local editable environment with pip:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e ".[dev,test]"
```

Or use `uv`, which is also used in the README examples:

```bash
uv venv --python 3.12
source .venv/bin/activate
uv pip install -e ".[dev,test]"
```

Install publish tooling only when building release artifacts:

```bash
python -m pip install -e ".[publish]"
```

There is no database, background worker, or development server for this project.

## Development Workflow

- Use an editable install before running tests or importing the package locally.
- `aiognmi.__version__` in `aiognmi/__init__.py` is the dynamic package version used by setuptools.
- Keep the public import surface in `aiognmi/__init__.py` deliberate; currently only `AsyncgNMIClient` is exported.
- Do not hand-edit generated `*_pb2.py` or `*_pb2_grpc.py` files unless you are intentionally regenerating protobuf outputs from the vendored `.proto` sources.
- Prefer unit tests with mocked gRPC stubs for client behavior; do not make normal tests depend on a real network device.

## Testing Instructions

Run the full test suite:

```bash
uv run --extra test pytest
```

Run a specific test module:

```bash
uv run --extra test pytest tests/test_utils.py
```

Focus on one test or parameterized group:

```bash
uv run --extra test pytest tests/test_utils.py -k create_gnmi_path
```

Pytest options are configured in `pyproject.toml` as `-p no:warnings -v`. Add or update tests for changed behavior, especially around gNMI path parsing, typed value parsing, response shaping, and request construction.

## Linting and Formatting

Ruff is configured in `pyproject.toml`.

Format code:

```bash
uv run --extra dev ruff format .
```

Run lint checks:

```bash
uv run --extra dev ruff check .
```

Check formatting without modifying files:

```bash
uv run --extra dev ruff format --check .
```

Ruff settings to preserve:

- Target Python version: `py310`.
- Line length: 120.
- Selected lint families: `C`, `E`, `F`, and `I`.
- Ignored lint: `C901`.
- Excluded path: `proto`, so generated protobuf modules are not linted.

## Code Style

- Use modern Python type hints compatible with Python 3.12+.
- Keep data containers in `aiognmi/models.py` as dataclasses unless there is a clear reason to change the pattern.
- Use `logging` for diagnostics instead of `print`.
- Keep utility functions deterministic and free of network side effects.
- Preserve the default gNMI origin behavior in path helpers unless tests and docs are updated with the intentional change.
- Keep runtime credentials and certificate paths as caller-provided values; never hard-code secrets in source, tests, or docs.

## Build and Release

Build distribution artifacts:

```bash
python -m build
```

Validate built artifacts:

```bash
python -m twine check dist/*
```

Publishing is handled by `.github/workflows/publish.yaml` when a GitHub release is created. The workflow builds with Python 3.12 and uploads to PyPI using the `PYPI_TOKEN` secret. Do not run `twine upload` locally unless the maintainer explicitly asks for it.

## CI Expectations

GitHub Actions run on pushes and pull requests:

- Lint job on Python 3.12 installs `.[dev]`, then runs `ruff format .` and `ruff check .`.
- Test job runs on Python 3.12, and 3.13, installs `.[test]`, then runs `pytest`.

Before submitting changes, run:

```bash
uv run --extra dev ruff format .
uv run --extra dev ruff check .
uv run --extra test pytest
```

## gNMI Runtime Notes

- README examples require a reachable gNMI target and runtime credentials.
- `insecure=True` uses an insecure gRPC channel.
- TLS/certificate support is documented as alpha in the README; keep changes in that area conservative and covered by focused tests where possible.
- Avoid logging usernames, passwords, certificate contents, or private keys.

## Repository Hygiene

- Do not commit local environments, caches, build outputs, or distribution files. `.gitignore` already excludes `.venv/`, `dist/`, `build/`, `*.egg-info/`, `.pytest_cache/`, and `.ruff_cache/`.
- Keep generated files and vendored protobuf sources together under `aiognmi/proto/`.
- Keep documentation changes in `README.md` for human-facing usage and `AGENTS.md` for coding-agent workflow guidance.
