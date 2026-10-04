
Detect benchmark test-set contamination in open pretraining corpora, and **measure how reliable that detection is**.

> **Status: The project is being built test-first. Results will appear here as each phase completes.

## What this is

Benchmark test sets (GSM8K, ARC, and others) also live on the public web. If test items sit inside a corpus a model trains on, scores may reflect memorization rather than ability. This project scans a documented slice of an open web corpus for benchmark items and, more importantly, validates the detector itself using planted ground truth and hand-labeled real hits.

Read [`docs/SCOPE.md`](docs/SCOPE.md) for the research questions, definitions, non-goals and caveats, and [`docs/DECISIONS.md`](docs/DECISIONS.md) for every design choice and the evidence behind it.

## Quickstart

```bash
git clone https://github.com/pearlin-in/contamination-detector.git
cd contamination-detector
python -m venv .venv
source .venv/bin/activate        # Windows (PowerShell): .venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
pytest
```

Right now the normalizer tests **fail on purpose** (see `CONTRIBUTING.md`).

## Repository layout

```
src/contam/       the package (modules are added phase by phase)
tests/unit/       fast, example-based tests
tests/property/   Hypothesis property-based tests
tests/integration/ small end-to-end tests on fixtures
tests/fixtures/   tiny hand-made benchmark and corpus
configs/          YAML run configurations
results/          small result files and figures (no raw data)
docs/             SCOPE, DECISIONS, ROADMAP, final REPORT
```

## Limitations

Overlap in a public corpus is not evidence that any specific model saw the data, and exposure is not the same as inflated scores. The full list of caveats is in [`docs/SCOPE.md`](docs/SCOPE.md) section 8.


