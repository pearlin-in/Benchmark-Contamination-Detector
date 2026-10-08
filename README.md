# Benchmark Contamination Detector

**Detect benchmark test-set contamination in open pretraining corpora — and measure how reliable that detection is.**

Most contamination studies report a number. This project reports a number *and* the evidence that the detector producing it works: planted ground truth with controlled corruption, a dev/test split frozen before the real scan, control documents as a false-positive bound, and a decision log that records every choice and the experiment that justified it.

> **Status:** Phases 0–6 complete. 277 tests, 92% coverage. Strict scan over ~76M FineWeb tokens found **0 exact / 0 near-duplicate / 0 partial** matches for 2,491 GSM8K + ARC-Challenge items. Phases 7–9 (analysis, hardening, write-up) in progress.

## Why this matters

Benchmark test sets live on the public web. If a test item sits inside a pretraining corpus, a model's score on that item may reflect memorization rather than ability. Detecting that is easy to *claim* and hard to *validate* — a detector that flags nothing looks perfect on clean data and a detector that flags everything looks perfect on contaminated data. This project treats the detector as the thing under test.

**What this does not show:** overlap in a public corpus is not proof that any model saw it, and exposure is not proof of inflated scores. Full caveats in [`docs/SCOPE.md`](docs/SCOPE.md) §8.

## Quickstart

```bash
git clone https://github.com/pearlin-in/contamination-detector.git
cd contamination-detector
python -m venv .venv
source .venv/bin/activate        # Windows (PowerShell): .venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
pytest
```

Run a scan:

```bash
contam scan \
  --benchmark gsm8k --benchmark arc_challenge \
  --operating-point results/phase6_eval/operating_point.json \
  --n 3 --partial 0.5 --stop-k 5 \
  --max-tokens 100000000 \
  --out C:\contam_scans\tier_s_strict
```

Generate a report from a completed scan:

```bash
contam report --scan results/scan_tier_s_strict --top 50 > docs/REPORT.md
```

## Headline result

Strict settings (`n=3`, `partial=0.5`, stop-n-gram filter `k=5`, question+choices view), ~100M FineWeb tokens:

| Benchmark | Items indexed | Partial | Near-dup | Exact |
|---|---:|---:|---:|---:|
| ARC-Challenge | 1,172 | 0 | 0 | 0 |
| GSM8K | 1,319 | 0 | 0 | 0 |

95% Wilson intervals: ARC [0.00%, 0.33%], GSM8K [0.00%, 0.29%]. 143,176 documents, 76,425,015 tokens, 136 s (561k tokens/s). 0 items skipped as too short or template-only.

An earlier, looser run (`n=2`, `partial=0.3`) produced 34 partial hits. Inspection showed they were template phrases and topic lists, not contamination — which is the main reason the headline scan uses strict settings.

These are **lower bounds for a corpus slice** and say nothing about any model.

## How the detector is validated

This is the part most contamination projects skip.

- **Planted ground truth.** Real corpus documents with benchmark items inserted at known offsets under controlled corruption (verbatim, case/punctuation, reordered choices, changed numbers, word deletion/substitution at 5–30%, truncation, HTML embedding). Manifest stores offsets and digests only, never text. Planted test macro recall: **0.997**.
- **Control documents.** Random web pages with nothing planted. Reported as an *upper bound* on the false-positive rate, with Wilson intervals — not as "precision."
- **Dev/test split by normalized question text**, so duplicate questions can't leak across the split. Operating point frozen before the real scan.
- **Hand-labeling** (Phase 7) as the only real precision measure. Planted-data precision over-estimates real-world precision because the controls are random web pages, not topically related pages.
- **Self-corrections.** Two earlier conclusions were overturned by later runs and are recorded in [`docs/DECISIONS.md`](docs/DECISIONS.md): D-053 corrects the explanation of what kept false positives down, and the partial-hit interpretation is corrected under D-052.

## Method

Two detectors, two stages:

1. **Exact n-gram containment** (streaming). The benchmark side is small (10⁵–10⁶ n-gram hashes), so the corpus is streamed once and only the benchmark table is held in memory. n ∈ {2, 3, 4, 5, 8}; operating point `n=3`. Stable 61-bit hashing via BLAKE2b + rolling polynomial, so results are identical across processes and OSes.
2. **MinHash + LSH** for near-duplicates and within-benchmark duplicate detection. Implemented from scratch and cross-checked against `datasketch`. Two-stage: cheap LSH candidate generation, then exact Jaccard/containment verification.

**Windowing** (window-localized containment, `window_slack=1.5`) is available and helps slightly at low n, but the compare run showed the fuzzy method's precision came from **LSH gating**, not from windowing — see D-053. The headline scan uses the exact detector at strict settings.

**Crash and resume:** exactly-once checkpointing with atomic writes; validated by an accidental OneDrive file lock during a real scan, which `--resume` recovered from cleanly at 100,000 documents.

## Repository layout

```
src/contam/         the package
  exact.py          streaming n-gram containment detector
  minhash.py        MinHash + LSH
  fuzzy.py          windowed fuzzy matching
  corrupt.py        corruption specs
  inject.py         synthetic contamination generator
  evaluate.py       precision/recall, sweeps
  scan.py           real-data scan with checkpointing
  report.py         headline tables and figures
tests/unit/         fast, example-based tests
tests/property/     Hypothesis property-based tests
tests/integration/  end-to-end tests on fixtures
tests/fixtures/     tiny hand-made benchmark and corpus
configs/            YAML run configurations
results/            small result files and figures (no raw data)
docs/               SCOPE, DECISIONS, ROADMAP, REPORT
```

## Engineering

- **Tests:** 277 passing, 92% coverage (99% on `exact.py` and `evaluate.py`). Property-based tests for normalization idempotence, n-gram counts, and cross-process hash stability.
- **Reproducibility:** pinned dependencies, pinned dataset revisions, fixed seeds, run manifests (config hash, git commit, dataset revision, timings).
- **Scale:** 561k tokens/s on 11 workers; ~1B-token slice in about an hour; memory flat on corpus size via bounded batching in a spawn process pool.
- **Data handling:** commits only IDs, hashes, offsets, scores, and ≤200-character snippets. No corpus or benchmark text is redistributed. FineWeb is ODC-By; ARC is CC BY-SA 4.0.

## Limitations

- One corpus slice (~76M tokens of FineWeb `sample-10BT`), English-only. Rates are lower bounds for the full corpus.
- Synthetic corruption is easier than natural paraphrase; planted-data recall is optimistic.
- Word-level tokens, so numbers are not directly comparable to BPE-based studies.
- No paraphrase detection (stretch goal).
- Controls are random web pages, so the false-positive bound says nothing about precision on topically related pages. Real precision requires hand-labeling.

Full list in [`docs/SCOPE.md`](docs/SCOPE.md) §8.

## Docs

- [`docs/SCOPE.md`](docs/SCOPE.md) — research questions, contamination levels, non-goals, caveats
- [`docs/DECISIONS.md`](docs/DECISIONS.md) — 50+ design choices with evidence
- [`docs/ROADMAP.md`](docs/ROADMAP.md) — phase plan
- [`docs/REPORT.md`](docs/REPORT.md) — full write-up

---

## What changed and why

1. **Status line updated.** The old one said "results will appear here as each phase completes." You have results now — lead with them. A README that says "coming soon" when it isn't reads as abandoned.
2. **Added the headline table.** This is the first thing a reviewer looks for. Put it above the fold.
3. **Reframed around validation, not detection.** "Detect contamination" is a crowded, boring pitch. "Measure how reliable the detection is" is your actual contribution and it's what makes the project interesting. The tagline already said this; the body now does too.
4. **Removed the failing-tests joke.** "Right now the normalizer tests fail on purpose" was a placeholder from Phase 1. If CI is green now, that line actively hurts you — a reviewer will run `pytest`, see green, and wonder why the README lies. If you *do* have an intentional failing test, name it explicitly and explain why.
5. **Added the method summary.** A reviewer shouldn't have to open `exact.py` to know what the detector does.
6. **Added the engineering section.** 277 tests at 92% coverage, 561k tokens/s, crash/resume — these are the things that make a hiring manager stop scrolling.
7. **Kept the limitations section** and linked it to SCOPE §8. This is your credibility. Don't bury it.
8. **Moved `docs/` links to the bottom** so they don't compete with the results. Keep the two inline links (SCOPE, DECISIONS) in the intro because they signal rigor early.
