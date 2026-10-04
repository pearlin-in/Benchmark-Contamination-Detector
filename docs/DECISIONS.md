# DECISIONS.md: Decision Log

This file records every non-trivial choice in the project: what was chosen, what else was considered, and **what evidence justified it**. It is the main place a reader sees that you understand *why*, not just *what*.

Entries D-001 to D-018 are pre-filled from `SCOPE.md` §6 with the **choice, alternatives and rationale** already known. Each also lists the **experiment that will confirm or change it**, and has an empty **Result** field. **Do not fill in a Result until you have actually run the experiment.** A result you wrote before running anything is the one thing this file must never contain.

---

## How to use this file

1. When you reach a phase, open the relevant entries and run the listed experiment.
2. Paste the result (a number, a table, or a link to a figure in `results/`) into **Result**.
3. Set **Status** to `Confirmed`, `Changed` (and update the Decision line), or `Locked` if it never needed an experiment.
4. If you change a decision later, don't delete the old one. Mark it `Superseded by D-0xx` and add the new entry.
5. When a target or threshold moves, add a line to the **Change log** at the bottom with the reason.

### Status legend

`Provisional` (default, awaiting evidence) · `Confirmed` (evidence supports it) · `Changed` (evidence overturned it) · `Locked` (a design principle, not an experiment) · `Superseded`

### Entry template (copy for new decisions)

```
### D-0xx: Title
- **Status:** Provisional | **Phase:** n | **Date:** YYYY-MM-DD
- **Context:** why this decision exists
- **Options:** A / B / C
- **Decision:** what you chose
- **Rationale:** why, in 2-4 sentences
- **Experiment:** what you will run to check it
- **Result:** (empty until run)
- **Tradeoff / what we gave up:**
- **Revisit if:**
```

---

## Index

| ID | Topic | Status |
| --- | --- | --- |
| D-001 | Unit of analysis | Locked |
| D-002 | Text views scanned | Locked |
| D-003 | Normalization | Provisional |
| D-004 | Tokenization | Locked |
| D-005 | n-gram size | Provisional |
| D-006 | Hashing | Locked |
| D-007 | Architecture (index the small side) | Locked |
| D-008 | Stop-n-gram filtering | Provisional |
| D-009 | Short-item policy | Provisional |
| D-010 | Near-duplicate method (MinHash + LSH) | Provisional |
| D-011 | Threshold selection (dev/test) | Locked |
| D-012 | Validation strategy | Locked |
| D-013 | Corruption types | Locked |
| D-014 | Statistics reporting | Locked |
| D-015 | Reproducibility | Locked |
| D-016 | Tooling | Locked |
| D-017 | Data handling and licenses | Locked |
| D-018 | Corpus sampling | Provisional |

---

## Decisions

### D-001: Unit of analysis

- **Status:** Locked | **Phase:** 0
- **Context:** Need one consistent thing to count and report.
- **Options:** benchmark item; corpus document; token span.
- **Decision:** The benchmark *item*. A *hit* is an (item, document) pair. An item is *flagged* if it has ≥ 1 hit.
- **Rationale:** Published contamination studies report "% of test items affected", so this makes results comparable.
- **Experiment:** none (design principle).
- **Result:** n/a
- **Tradeoff:** Hides how many documents contain each item (kept in the hit list instead).
- **Revisit if:** you want document-level analysis for RQ5.

### D-002: Text views scanned

- **Status:** Locked | **Phase:** 0
- **Context:** An item has a question, choices, and an answer. Which text do we search for?
- **Options:** question only; question + choices; full item with answer rationale.
- **Decision:** Primary = question + choices. Secondary = question only. Answers alone are never scanned.
- **Rationale:** Short answer strings ("B", "12") match everywhere and mean nothing. Question-only vs. question+choices lets us separate weaker from stronger leakage.
- **Experiment:** none, but report both views' rates.
- **Result:** n/a
- **Tradeoff:** Won't detect an answer-only leak (e.g., a page listing answers without questions).
- **Revisit if:** a benchmark has long free-text answers worth scanning.

### D-003: Normalization

- **Status:** Provisional | **Phase:** 2-4
- **Context:** Web text and benchmark text differ in case, punctuation, whitespace, and Unicode.
- **Options:** (A) keep punctuation; (B) NFKC + lowercase + strip punctuation + collapse whitespace, **keep digits**; (C) as B but drop digits; (D) add stemming/lemmatization.
- **Decision:** B.
- **Rationale:** GPT-3's methodology ignored case, punctuation and whitespace. Digits carry the identity of math word problems, so dropping them would create false positives.
- **Experiment:** Run the exact detector on the planted *dev* set under A, B, C. Compare recall on case/whitespace/punctuation corruptions and false-positive rate on control documents. Check how many GSM8K items collide with each other after normalization.
- **Result:** *(empty)*
- **Tradeoff:** Stripping punctuation loses information (e.g., "1,000" vs "1 000"); handle number formats explicitly if it matters.
- **Revisit if:** LaTeX/MMLU math items behave badly.

### D-004: Tokenization

- **Status:** Locked | **Phase:** 2
- **Context:** n-grams of what?
- **Options:** simple regex word tokens; whitespace split; model BPE tokens.
- **Decision:** Regex word-level tokens.
- **Rationale:** Deterministic, fast, independent of any model's vocabulary. GPT-3 worked on words; Llama-style analyses used tokens, so state that numbers are not directly comparable.
- **Experiment:** Build an edge-case table (hyphens, apostrophes, numbers with commas/decimals, LaTeX, emoji, non-ASCII) with the exact tokens produced; cover each row with a unit test.
- **Result:** *(empty)*
- **Tradeoff:** Not comparable one-to-one with token-based studies.
- **Revisit if:** you add a code benchmark where word tokens are a poor fit.

### D-005: n-gram size

- **Status:** Provisional | **Phase:** 4
- **Context:** Small n catches more edited copies but flags boilerplate; large n is precise but brittle.
- **Options:** fixed n = 5, 8, or 13; sweep; GPT-3-style adaptive N (5th-percentile item length, capped at 13).
- **Decision:** Sweep n ∈ {5, 8, 13}; default 8 *provisionally*; also compute the GPT-3-style flag for comparison.
- **Rationale:** 8-grams appear in GPT-2-era analysis and 13-grams in GPT-3's; sweeping shows the tradeoff on your own data rather than assuming it.
- **Experiment:** Grid over n × overlap threshold on the planted dev set: recall by corruption type, false-positive rate on controls. Then count real hits per n on tier-S corpus data.
- **Result:** *(empty)*
- **Tradeoff:** Reporting three n values complicates the headline; pick one and show the others in an appendix.
- **Revisit if:** short benchmark items (ARC) make the chosen n unusable.

### D-006: Hashing

- **Status:** Locked | **Phase:** 2
- **Context:** n-grams are stored and compared as integer hashes for speed and memory.
- **Options:** Python `hash()`; stable 64-bit hash (blake2b truncated, or xxhash); 32-bit hash.
- **Decision:** Stable 64-bit hash.
- **Rationale:** `hash()` is salted per process and breaks reproducibility across runs and multiprocessing workers. At 64 bits, with \~10⁶ benchmark hashes the chance a random corpus n-gram collides is ≈ 5×10⁻¹⁴, so ≈ 5×10⁻⁵ expected false collisions over 10⁹ corpus n-grams.
- **Experiment:** (a) test that two separate processes hash identical input identically; (b) confirm zero collisions among *distinct* benchmark n-grams; (c) microbenchmark blake2b vs xxhash.
- **Result:** *(empty)*
- **Tradeoff:** blake2b is slower than xxhash; xxhash adds a dependency.
- **Revisit if:** hashing dominates runtime in profiling.

### D-007: Architecture (index the small side)

- **Status:** Locked | **Phase:** 3
- **Context:** How to find benchmark text inside a corpus too big to hold.
- **Options:** index the corpus (suffix array, search engine, Spark); hold the benchmark's n-grams in memory and stream the corpus once.
- **Decision:** Stream the corpus; hold only the benchmark n-gram table.
- **Rationale:** The benchmark side is tiny (order 10⁵-10⁶ hashes). Indexing the corpus is unnecessary here and impossible on a free tier.
- **Experiment:** Record memory of the benchmark table and throughput (docs/s, tokens/s) on tier-S data.
- **Result:** *(empty)*
- **Tradeoff:** Adding a new benchmark means rescanning the corpus.
- **Revisit if:** you want to query many benchmarks repeatedly (then an index pays off).

### D-008: Stop-n-gram filtering

- **Status:** Provisional | **Phase:** 3-4
- **Context:** Templated phrases ("which of the following is…") match everywhere and cause false positives.
- **Options:** no filtering; drop n-grams shared by ≥ k benchmark items; drop n-grams frequent in the corpus.
- **Decision:** Benchmark-side filter with cutoff k (value TBD).
- **Rationale:** Cheap, needs no corpus statistics.
- **Experiment:** k ∈ {none, 3, 5, 10}. For each: number of n-grams removed, false-positive rate on controls, and precision on a small hand-checked preview of real hits.
- **Result:** *(empty)*
- **Tradeoff:** May remove n-grams from genuinely contaminated items that share a template.
- **Revisit if:** recall on planted data drops noticeably after filtering.

### D-009: Short-item policy

- **Status:** Provisional | **Phase:** 3
- **Context:** Items shorter than n tokens produce no n-grams.
- **Options:** drop them; shrink n to the item length; shrink n and tag as low-confidence.
- **Decision:** Use N_item = item length, tag `short`, and report separately from headline numbers.
- **Rationale:** GPT-3 handled items shorter than N by whole-example overlap; tagging stops weak matches from polluting the headline.
- **Experiment:** Plot item-length distributions per benchmark; report what % fall below each n; compare flagged rates with and without `short` items.
- **Result:** *(empty)*
- **Tradeoff:** Two sets of numbers to explain.
- **Revisit if:** a benchmark is mostly short items.

### D-010: Near-duplicate method (MinHash + LSH)

- **Status:** Provisional | **Phase:** 5
- **Context:** Exact n-gram overlap collapses when a few words change.
- **Options:** one-stage MinHash on whole documents; two-stage (LSH candidates on sliding windows, then exact containment verification); embeddings.
- **Decision:** Two-stage, windows sized to the item length.
- **Rationale:** Whole-document signatures are too coarse for short items; verification protects precision. Implement MinHash yourself and cross-check against `datasketch`.
- **Experiment:** Vary `num_perm`, bands × rows, and window size. Plot the LSH S-curve (theory vs. empirical). Compare recall by corruption against M1 and measure time/memory cost.
- **Result:** *(empty)*
- **Tradeoff:** Much slower than M1; more parameters to defend.
- **Revisit if:** M2 adds little recall over M1 for light edits.

### D-011: Threshold selection (dev/test)

- **Status:** Locked | **Phase:** 4
- **Context:** Choosing τ₁, τ₂ and n by looking at the same data you report on overfits your own evaluation.
- **Options:** tune on everything; dev/test split.
- **Decision:** Split planted items into dev and test **by benchmark item id** (not by document, otherwise the same item leaks into both). Tune on dev, freeze, report on test and on hand-labeled real hits.
- **Rationale:** Standard discipline applied to detector thresholds.
- **Experiment:** Record the split seed and the frozen thresholds with a timestamp/commit before running the test split.
- **Result:** *(empty)*
- **Tradeoff:** Fewer items per split (small benchmarks).
- **Revisit if:** the splits are too small to give stable estimates (then use repeated random splits and report the spread).

### D-012: Validation strategy

- **Status:** Locked | **Phase:** 4, 7
- **Context:** Real data has no ground truth for recall.
- **Options:** eyeballing; planted ground truth only; planted + hand-labeled real hits.
- **Decision:** Both planted ground truth (recall) and hand-labeled real hits (precision).
- **Rationale:** Each covers the other's blind spot: planted data can be unrealistic; hand-labels only cover what was found.
- **Experiment:** Write the labeling rubric *before* labeling: categories `true contamination`, `coincidental template overlap`, `benign (discussion/quote)`. Label \~150 hits stratified by score band and benchmark; relabel 30 later and record agreement.
- **Result:** *(empty)*
- **Tradeoff:** Hand-labeling is slow and subjective.
- **Revisit if:** agreement with your own earlier labels is poor (tighten the rubric).

### D-013: Corruption types

- **Status:** Locked | **Phase:** 4
- **Decision:** Verbatim; case/whitespace/punctuation changes; reordered choices; changed numbers; random word deletion/substitution at 5/10/20/30%; truncation; embedded in boilerplate/HTML.
- **Rationale:** Covers realistic mechanical degradation. It explicitly does *not* model natural paraphrase (SCOPE §5).
- **Experiment:** Store the full corruption parameters and seed in the injection manifest; test determinism.
- **Result:** *(empty)*
- **Tradeoff:** Synthetic edits are easier than real rewrites, so recall here is optimistic.
- **Revisit if:** you add a small hand-written paraphrase set as an honest "hard" test.

### D-014: Statistics reporting

- **Status:** Locked | **Phase:** 7
- **Decision:** Every proportion is reported with a Wilson 95% confidence interval and its sample size.
- **Rationale:** Small samples (≈150 labels) give wide intervals; stating them is honest.
- **Experiment:** Implement the interval and test it against hand-computed known values.
- **Result:** *(empty)*
- **Tradeoff:** Tables get busier.
- **Revisit if:** you need comparisons between two rates (add a proper test or overlapping-interval caution).

### D-015: Reproducibility

- **Status:** Locked | **Phase:** 1, 6
- **Decision:** Pinned dependencies; pinned dataset revisions (commit hashes); fixed seeds; every run writes a manifest (config hash, git commit, dataset revisions, timings, library versions).
- **Experiment:** From a clean clone, regenerate the headline table and diff against your saved result.
- **Result:** *(empty)*
- **Tradeoff:** Pinning means occasional manual upgrades.
- **Revisit if:** a pinned dataset revision disappears.

### D-016: Tooling

- **Status:** Locked | **Phase:** 1
- **Decision:** Python 3.11+, `pyproject.toml`, pytest, Hypothesis, ruff, mypy, Hugging Face `datasets`, numpy, pandas/pyarrow, matplotlib; `datasketch` for cross-checking only; GitHub Actions for CI (confirm current free terms for public repos).
- **Rationale:** Free, standard, few dependencies.
- **Experiment:** CI runs lint, type check and tests on a clean environment.
- **Result:** *(empty)*
- **Revisit if:** CI becomes slow or flaky.

### D-017: Data handling and licenses

- **Status:** Locked | **Phase:** 1, 9
- **Decision:** Commit only IDs, hashes, offsets, scores and snippets ≤ \~200 characters. Never commit corpus or benchmark text. `.gitignore` all downloaded data.
- **Rationale:** FineWeb is ODC-By (attribution) and ARC is CC BY-SA 4.0 (share-alike); shipping only identifiers sidesteps redistribution questions. Read each license yourself; this is not legal advice.
- **Experiment:** Before every release, grep the repo for large text blobs; keep a license table in the README with links.
- **Result:** *(empty)*
- **Revisit if:** you want to publish a labeled dataset (then check licensing properly first).

### D-018: Corpus sampling

- **Status:** Provisional | **Phase:** 6
- **Decision:** Stream a prefix of `sample-10BT`; verify its spread across the `dump` field; seed any subsampling.
- **Rationale:** Cheap and reproducible; the check guards against a biased prefix.
- **Experiment:** Plot dump distribution of the slice and note any skew in the report.
- **Result:** *(empty)*
- **Tradeoff:** A prefix is not guaranteed to be a uniform random sample.
- **Revisit if:** the dump distribution is clearly skewed (then sample across shards).

---

## Decisions you will need to add (reserved IDs)

These don't exist yet because they depend on evidence. Create each entry when you reach it.

| ID | Topic | When |
| --- | --- | --- |
| D-019 | Final τ₁ and τ₂ values | after dev-set tuning |
| D-020 | Final n and headline operating point | after the sweep |
| D-021 | Stop-n-gram cutoff k | after D-008 experiment |
| D-022 | Window size and LSH banding for M2 | after D-010 experiment |
| D-023 | Final corpus slice size | after throughput is measured |
| D-024 | Checkpoint format and resume strategy | before the full scan |
| D-025 | Multiprocessing design and deterministic merge | before the full scan |
| D-026 | Hit-list output schema | before the full scan |
| D-027 | Whether to run the FineWeb-Edu comparison (RQ5) | after the main scan |

---

## Change log (targets, thresholds, scope)

| Date | What changed | Why | Entry |
| --- | --- | --- | --- |
|  |  |  |  |

*(Every edit to a success criterion in `SCOPE.md` §7 must appear here.)*