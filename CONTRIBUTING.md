# Development guide

Works on Windows, macOS and Linux. Python 3.11 or newer.

## Setup

```bash
python -m venv .venv
# macOS / Linux:
source .venv/bin/activate
# Windows (PowerShell):
.venv\Scripts\Activate.ps1

python -m pip install -e ".[dev]"
pre-commit install
```

The core package has no runtime dependencies, so setup is fast and light. Heavier extras are opt-in:

```bash
python -m pip install -e ".[data]"       # Hugging Face datasets, pyarrow (streaming corpora)
python -m pip install -e ".[analysis]"   # numpy, pandas, matplotlib (tables and figures)
```

## Everyday commands

| Task | Command |
|---|---|
| Run all tests | `pytest` |
| Skip property tests | `pytest -m "not property"` |
| Only property tests | `pytest -m property` |
| Run tests with coverage | `pytest --cov` |
| Lint | `ruff check .` |
| Auto-fix lint issues | `ruff check . --fix` |
| Format | `ruff format .` |
| Type check | `mypy src` |
| Heavier property testing | `HYPOTHESIS_PROFILE=ci pytest -m property` (PowerShell: `$env:HYPOTHESIS_PROFILE="ci"; pytest -m property`) |

Run `ruff format .` once before your first commit so formatting matches exactly.

## Working test-first

1. Write or extend a test that describes the behaviour you want. Run it and watch it fail for the right reason.
2. Write the smallest code that makes it pass.
3. Refactor with the tests green.
4. If you make a judgement call, record it in `docs/DECISIONS.md` (with the evidence).

## Windows and cross-platform rules

- Always open files with `encoding="utf-8"`.
- Line endings are forced to LF by `.gitattributes`; do not fight it.
- Use `pathlib.Path`, never string concatenation for paths.
- Never use Python's built-in `hash()` for anything stored or compared across runs (it is salted per process). See `docs/DECISIONS.md`, D-006.

## Commit messages

Short imperative subject line (`Add normalizer contract tests`), optional body explaining *why*. Reference decision IDs (`D-003`) where relevant.
