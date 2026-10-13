# contam: detecting benchmark test-set contamination, and measuring how reliable the detector is

[![CI](https://github.com/YOUR_USERNAME/contamination-detector/actions/workflows/ci.yml/badge.svg)](https://github.com/YOUR_USERNAME/contamination-detector/actions/workflows/ci.yml)

Benchmark test sets such as GSM8K and ARC also live on the public web. If test items sit inside the text a model trains on, its score may reflect memorization rather than ability. This project scans open web corpora for benchmark items **and validates the detector itself** with planted ground truth and hand-labelled hits, so that a "found nothing" result can be trusted for what it covers.

## Headline result

| Scan | Corpus slice | Setting | GSM8K (1,319 items) | ARC-Challenge (1,172 items) |
| --- | --- | --- | --- | --- |
| Strict | FineWeb, ~100M GPT-2 tokens (143,176 docs) | n=3, partial 0.5, stop-k 5 | 0 items flagged | 0 items flagged |
| Strict | FineWeb-Edu, ~1B tokens (965,087 docs) | n=3, partial 0.5, stop-k 5 | 0 flagged | 2 weak partial hits, 0 near-duplicate, 0 exact |
| Loose | FineWeb, ~100M tokens | n=2, partial 0.3 | 3 weak hits | 31 weak hits, 0 near-duplicate, 0 exact |

- **No exact or near-duplicate copy of any test item was found in any scan.**
- **Weak partial-level hits are not contamination here.** I hand-labelled 122 of the 244 hits from the main scans using the stored excerpt: 0 were true contamination, 122 were coincidental or benign overlap (95% upper bound on the true share: about 3.1%).
- **Short items cause most weak hits.** Only 1.7% of items (42 of 2,491, all in ARC) have fewer than 15 tokens, yet they produced 84% of hits.
- These are **lower bounds for a corpus slice**. They say nothing about any specific model.

## How reliable is "found nothing"? Validation on planted ground truth

Real corpora have no labels, so recall cannot be measured on them. I planted corrupted benchmark items into real FineWeb pages at known positions and measured how many the detector recovered, on a held-out test split (100 plants per condition, tuned on a separate dev half). Recall at the scan setting:

| Corruption | Recall | Corruption | Recall |
| --- | --- | --- | --- |
| verbatim | 1.00 | 20% of words deleted | 0.57 |
| case/whitespace/punctuation noise | 1.00 | 20% of words substituted | 0.65 |
| punctuation deleted | 0.99 | 30% of words deleted | 0.12 |
| up to 10% words edited | 0.99 to 1.00 | 30% of words substituted | 0.18 |
| truncated to 80% / 60% | 1.00 / 0.97 | numbers changed | 0.93 |
| wrapped or split by HTML | 1.00 | choices shuffled / labelled | 0.93 to 0.96 |

**What this means:** the scans would very likely have caught verbatim, reformatted, truncated and lightly edited copies. They would mostly miss copies with 20% or more of the words changed, and paraphrases are not detected by design.

## What I learned (and got wrong along the way)

- **Recall decays predictably with n-gram size.** Deleting a fraction p of words leaves about (1 - p)^n of the n-grams, and measured recall followed that curve.
- **Lowering n buys recall and destroys precision.** At n=2, 138 of 300 ordinary web pages were flagged by a whole-document detector; at n=3 only 3.
- **A MinHash/LSH fuzzy matcher I built from scratch was not worth it.** It matched exact n=2 on recall and flagged fewer controls, but cost about 40 times more than exact n=3. I first credited window-localization for its precision, then measured that a window-localized exact detector still flagged 117 of 300; the decision log records the correction.
- **Random web pages made a poor precision test.** Controls drawn from random pages never flagged, while topically related pages produced 244 weak hits at the loose setting. Hand-labelling real hits was the measurement that mattered.
- **A real crash taught me about checkpointing.** A 100M-token scan died with a Windows file-lock error (the repo lived in OneDrive); `--resume` continued from the checkpoint without losing or duplicating a hit.

## How it works

1. **Normalize** (Unicode NFKC, lowercase, punctuation to spaces) and **tokenize** words.
2. **Index the small side.** Every benchmark n-gram is hashed (a stable rolling hash over BLAKE2b token hashes) into memory; the corpus is streamed once and never indexed.
3. **Score** each benchmark item per document by containment: the fraction of the item's n-grams found, inside an item-sized window, with a contiguity check for exact matches.
4. **Scan at scale.** A spawn-based process pool with bounded batches, ordered commits and atomic checkpoints (exactly-once output, safe to interrupt and resume).
5. **Validate.** Planted corruptions (verbatim, edited, truncated, reformatted, HTML-wrapped and more) with a dev/test split, Wilson confidence intervals, and a frozen operating point chosen on dev data only.

Every design choice, the experiment behind it and its result is in [`docs/DECISIONS.md`](docs/DECISIONS.md). Scope, definitions and caveats are in [`docs/SCOPE.md`](docs/SCOPE.md).

## Limitations

- The slices are small compared with FineWeb (roughly 15T tokens; check the dataset card), and FineWeb is already filtered and deduplicated.
- Paraphrased or translated test items are not detected, and heavily edited copies are mostly missed (see the recall table).
- Planted corruptions are mechanical, not natural rewrites. Hand labels come from one labeller judging short excerpts.
- English only. Findings concern corpora, not models: overlap does not prove a model saw the data, and exposure does not prove inflated scores.

## Reproduce

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\Activate.ps1
python -m pip install -e ".[dev,data,analysis]"
pytest

# validate the detector on planted ground truth (held-out test split)
contam evaluate --benchmark gsm8k --benchmark arc_challenge --background fineweb \
  --background-docs 5000 --n 3 --stop-k 5 --window-slack 1.5 --controls 1000 --out results/validation

# scan a corpus slice (safe to interrupt; add --resume to continue)
contam scan --benchmark gsm8k --benchmark arc_challenge --n 3 --partial 0.5 --stop-k 5 \
  --max-tokens 100000000 --out results/scan

contam report --scan results/scan
```

## Repository layout

`src/contam/` the package (normalize, ngrams, exact, corrupt, inject, evaluate, scan, report, minhash, fuzzy) · `tests/` unit, property-based and integration tests · `docs/` scope, decision log, roadmap · `scripts/` small analysis helpers.

## License

<!-- decide: MIT (add a LICENSE file with your name) or leave unlicensed -->