# DECISIONS.md: Decision Log

This file records every non-trivial choice in the project: what was chosen, what else was considered, and **what evidence justified it**. It is the main place a reader sees that you understand *why*, not just *what*.

Entries D-001 to D-018 come from `SCOPE.md` section 6. Entries D-028 to D-033 were added during roadmap phases 2-3, D-034 to D-040 during phase 4, and D-041 to D-045 are the planned design for phase 5. Each entry lists the **experiment that will confirm or change it**, and has a **Result** field that stays empty until you have actually run that experiment. **Never write a Result before running the experiment.** A result written in advance is the one thing this file must never contain.

IDs D-019 to D-027 are reserved for decisions that depend on evidence (see the table near the end), which is why the numbering jumps from D-018 to D-028.

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
- **Implemented in:** file or function (once code exists)
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
| D-006 | Hashing (hash space and stability) | Locked |
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
| D-028 | Rolling polynomial hash over BLAKE2b token hashes | Provisional |
| D-029 | Identical items are grouped | Locked |
| D-030 | Containment denominator and exact verification | Provisional |
| D-031 | Minimum item length defaults | Provisional |
| D-032 | Symbols are separate tokens | Locked |
| D-033 | Question+choices view and labelled options | Provisional |
| D-034 | Dev/test split key is the normalized question text | Locked |
| D-035 | Per-record deterministic randomness | Locked |
| D-036 | One planted item per document; manifest stores no text | Locked |
| D-037 | Control flags are an upper bound on the false-positive rate | Locked |
| D-038 | Recall definition and unindexed items | Locked |
| D-039 | Operating-point selection rule | Provisional |
| D-040 | Scan once at a floor threshold, then re-threshold | Locked |
| D-041 | Phase 5 purpose and hypothesis | Provisional |
| D-042 | MinHash implementation and validation | Provisional |
| D-043 | LSH banding and S-curve check | Provisional |
| D-044 | Windowed fuzzy matching with exact verification | Provisional |
| D-045 | Within-benchmark near-duplicate detection | Provisional |

---

## Decisions

### D-001: Unit of analysis

- **Status:** Locked | **Phase:** 0
- **Context:** Need one consistent thing to count and report.
- **Options:** benchmark item; corpus document; token span.
- **Decision:** The benchmark *item*. A *hit* is an (item, document) pair. An item is *flagged* if it has at least one hit.
- **Rationale:** Published contamination studies report "% of test items affected", so this makes results comparable.
- **Implemented in:** `Hit` and `ExactIndex.scan_document` in `src/contam/exact.py`.
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
- **Implemented in:** `View` and `BenchmarkItem.text` in `src/contam/items.py`.
- **Experiment:** none, but report both views' rates. See also D-033 for a known limitation of the question+choices view.
- **Result:** n/a
- **Tradeoff:** Won't detect an answer-only leak (e.g., a page listing answers without questions).
- **Revisit if:** a benchmark has long free-text answers worth scanning.

### D-003: Normalization

- **Status:** Provisional | **Phase:** 2-4
- **Context:** Web text and benchmark text differ in case, punctuation, whitespace, and Unicode.
- **Options:** (A) keep punctuation; (B) NFKC + lowercase + strip punctuation + collapse whitespace, **keep digits**; (C) as B but drop digits; (D) add stemming/lemmatization.
- **Decision:** B, as implemented: delete invisible format characters (Unicode category Cf); NFKC; lowercase; NFKC again (lowercasing can undo NFKC stability); replace every punctuation character (category P*) with a space; keep symbols (category S*, such as `+`, `=`, `$`) and digits; collapse whitespace. Accents are kept.
- **Rationale:** GPT-3's methodology ignored case, punctuation and whitespace. Digits carry the identity of math word problems, so dropping them would create false positives. Keeping math symbols preserves the difference between problems that differ only in an operator.
- **Implemented in:** `normalize` in `src/contam/normalize.py`; contract tests in `tests/unit/test_normalize.py` (cases tagged `[D-003]`) and `tests/property/test_normalize_properties.py`.
- **Experiment:** Run the exact detector on the planted *dev* set under A, B, C. Compare recall on case/whitespace/punctuation corruptions and false-positive rate on control documents. Check how many GSM8K items collide with each other after normalization.
- **Result:** *(partial)* On the planted test set (GSM8K + ARC-Challenge, 100 plants per condition, n=5, thresholds 0.3/0.9), deleting punctuation instead of spacing it out (`punct_delete`) gave recall 0.99 [0.95, 1.00], and case/whitespace/punctuation noise (`format_noise`) gave 1.00. Variants A and C were not compared and GSM8K self-collisions were not counted, so this experiment is unfinished.
- **Tradeoff:** Punctuation becomes a space, so `1,000` and `3.5` become `1 000` and `3 5`, and `don't` becomes `don t`. This is consistent on both sides of the comparison but loses information, and it makes `3.5` and `3 5` indistinguishable.
- **Revisit if:** LaTeX/MMLU math items behave badly, or number formats cause missed matches.

### D-004: Tokenization

- **Status:** Locked | **Phase:** 2
- **Context:** n-grams of what?
- **Options:** simple regex word tokens; whitespace split; model BPE tokens.
- **Decision:** Regex word-level tokens (see D-032 for how symbols are handled).
- **Rationale:** Deterministic, fast, independent of any model's vocabulary. GPT-3 worked on words; Llama-style analyses used tokens, so state that numbers are not directly comparable.
- **Implemented in:** `tokenize` in `src/contam/tokenizer.py`.
- **Experiment:** Build an edge-case table (hyphens, apostrophes, numbers with commas/decimals, LaTeX, emoji, non-ASCII) with the exact tokens produced; cover each row with a unit test.
- **Result:** *(empty)*
- **Tradeoff:** Not comparable one-to-one with token-based studies. Scripts that rely on combining marks are split into more tokens than a linguist would; acceptable under the English-only scope.
- **Revisit if:** you add a code benchmark where word tokens are a poor fit.

### D-005: n-gram size

- **Status:** Provisional | **Phase:** 4
- **Context:** Small n catches more edited copies but flags boilerplate; large n is precise but brittle.
- **Options:** fixed n = 5, 8, or 13; sweep; GPT-3-style adaptive N (5th-percentile item length, capped at 13).
- **Decision:** Sweep n in {5, 8, 13}; default 8 *provisionally*; also compute the GPT-3-style flag for comparison.
- **Rationale:** 8-grams appear in GPT-2-era analysis and 13-grams in GPT-3's; sweeping shows the tradeoff on your own data rather than assuming it.
- **Implemented in:** `ExactIndex.build(n=...)`, `gpt3_style_ngram_size` and `ExactIndex.gpt3_style` in `src/contam/exact.py`.
- **Experiment:** Grid over n x overlap threshold on the planted dev set: recall by corruption type, false-positive rate on controls. Then count real hits per n on tier-S corpus data.
- **Result:** *(partial)* With the grid n in {5, 8, 13}, partial in {0.3, 0.5, 0.7}, near in {0.8, 0.9}, both the real-data run and the synthetic demo selected n=5 with thresholds 0.3/0.9 on dev data: the smallest n and the loosest partial threshold in the grid. The optimum may lie outside the grid, so the grid is being widened (n=3 and 4). Real-hit counts per n are not yet measured.
- **Tradeoff:** Reporting three n values complicates the headline; pick one and show the others in an appendix.
- **Revisit if:** short benchmark items (ARC) make the chosen n unusable.

### D-006: Hashing (hash space and stability)

- **Status:** Locked | **Phase:** 2
- **Context:** n-grams are stored and compared as integer hashes for speed and memory.
- **Options:** Python `hash()`; stable 64-bit hash (blake2b truncated, or xxhash); 32-bit hash; a 61-bit hash space (Mersenne prime 2^61 - 1).
- **Decision:** Stable hashing in a 61-bit space. The scheme is described in D-028.
- **Rationale:** `hash()` is salted per process and breaks reproducibility across runs and multiprocessing workers. In a 2^61 space, with about 10^6 benchmark hashes, the chance that a random corpus n-gram collides with one is about 4x10^-13, so about 4x10^-4 expected false collisions over 10^9 corpus n-grams. A single spurious collision would add at most one n-gram to one item's overlap count, so the effect on any score is negligible.
- **Implemented in:** `token_hash` and `MODULUS` in `src/contam/ngrams.py`.
- **Experiment:** (a) a test that two separate processes with different `PYTHONHASHSEED` values hash identical input identically (exists in `tests/unit/test_ngrams.py`); (b) count collisions among the *distinct* benchmark n-grams (expect 0).
- **Result:** *(empty)*
- **Tradeoff:** 61 bits instead of 64 slightly raises collision odds; the modular arithmetic it buys is what makes rolling hashes cheap (D-028).
- **Revisit if:** the collision check finds any collision, or hashing dominates runtime in profiling.

### D-007: Architecture (index the small side)

- **Status:** Locked | **Phase:** 3
- **Context:** How to find benchmark text inside a corpus too big to hold.
- **Options:** index the corpus (suffix array, search engine, Spark); hold the benchmark's n-grams in memory and stream the corpus once.
- **Decision:** Stream the corpus; hold only the benchmark n-gram table.
- **Rationale:** The benchmark side is tiny (order 10^5-10^6 hashes). Indexing the corpus is unnecessary here and impossible on a free tier.
- **Implemented in:** `ExactIndex` in `src/contam/exact.py`; streaming in `src/contam/data/corpus.py`.
- **Experiment:** Record memory of the benchmark table (`ExactIndex.table_size`) and throughput (docs/s, tokens/s) on tier-S data.
- **Result:** *(empty)*
- **Tradeoff:** Adding a new benchmark means rescanning the corpus.
- **Revisit if:** you want to query many benchmarks repeatedly (then an index pays off).

### D-008: Stop-n-gram filtering

- **Status:** Provisional | **Phase:** 3-4
- **Context:** Templated phrases ("which of the following is...") match everywhere and cause false positives.
- **Options:** no filtering; drop n-grams shared by at least k benchmark items; drop n-grams frequent in the corpus.
- **Decision:** Benchmark-side filter with cutoff k (value TBD), counted over *distinct* item texts (see D-029).
- **Rationale:** Cheap, needs no corpus statistics.
- **Implemented in:** `ExactIndex.build(stop_ngram_k=...)` in `src/contam/exact.py`.
- **Experiment:** k in {none, 3, 5, 10}. For each: number of n-grams removed, false-positive rate on controls, and precision on a small hand-checked preview of real hits.
- **Result:** *(empty)*
- **Tradeoff:** May remove n-grams from genuinely contaminated items that share a template. Items made only of template n-grams are skipped and reported as `all_stop_ngrams`.
- **Revisit if:** recall on planted data drops noticeably after filtering.

### D-009: Short-item policy

- **Status:** Provisional | **Phase:** 3
- **Context:** Items shorter than n tokens produce no n-grams.
- **Options:** drop them; shrink n to the item length; shrink n and tag as low-confidence.
- **Decision:** Use N_item = item length, tag `short`, and report separately from headline numbers. Defaults are in D-031.
- **Rationale:** GPT-3 handled items shorter than N by whole-example overlap; tagging stops weak matches from polluting the headline.
- **Implemented in:** `ExactIndex.build(min_tokens=...)`, `Hit.short` in `src/contam/exact.py`.
- **Experiment:** Plot item-length distributions per benchmark; report what % fall below each n; compare flagged rates with and without `short` items.
- **Result:** *(empty)*
- **Tradeoff:** Two sets of numbers to explain.
- **Revisit if:** a benchmark is mostly short items.

### D-010: Near-duplicate method (MinHash + LSH)

- **Status:** Provisional | **Phase:** 5
- **Context:** Exact n-gram overlap collapses when a few words change.
- **Options:** one-stage MinHash on whole documents; two-stage (LSH candidates on sliding windows, then exact containment verification); embeddings.
- **Decision:** Two-stage, windows sized to the item length. Refined in D-041 to D-045 after the phase 4 results.
- **Rationale:** Whole-document signatures are too coarse for short items; verification protects precision. Implement MinHash yourself and cross-check against `datasketch`.
- **Experiment:** Vary `num_perm`, bands x rows, and window size. Plot the LSH S-curve (theory vs. empirical). Compare recall by corruption against M1 and measure time/memory cost.
- **Result:** *(empty)*
- **Tradeoff:** Much slower than M1; more parameters to defend.
- **Revisit if:** M2 adds little recall over M1 for light edits.

### D-011: Threshold selection (dev/test)

- **Status:** Locked | **Phase:** 4
- **Context:** Choosing the thresholds (tau1, tau2) and n by looking at the same data you report on overfits your own evaluation.
- **Options:** tune on everything; dev/test split.
- **Decision:** Split planted items into dev and test **by benchmark item id** (not by document, otherwise the same item leaks into both). Tune on dev, freeze, report on test and on hand-labeled real hits.
- **Rationale:** Standard discipline applied to detector thresholds.
- **Implemented in:** `Thresholds` in `src/contam/exact.py` (the split itself arrives with the Phase 4 harness).
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
- **Experiment:** Write the labeling rubric *before* labeling: categories `true contamination`, `coincidental template overlap`, `benign (discussion/quote)`. Label about 150 hits stratified by score band and benchmark; relabel 30 later and record agreement.
- **Result:** *(empty)*
- **Tradeoff:** Hand-labeling is slow and subjective.
- **Revisit if:** agreement with your own earlier labels is poor (tighten the rubric).

### D-013: Corruption types

- **Status:** Locked | **Phase:** 4
- **Decision:** Verbatim; case/whitespace/punctuation changes; reordered choices; changed numbers; random word deletion/substitution at 5/10/20/30%; truncation; embedded in boilerplate/HTML.
- **Rationale:** Covers realistic mechanical degradation. It explicitly does *not* model natural paraphrase (SCOPE section 5).
- **Experiment:** Store the full corruption parameters and seed in the injection manifest; test determinism.
- **Result:** *(empty)*
- **Tradeoff:** Synthetic edits are easier than real rewrites, so recall here is optimistic.
- **Revisit if:** you add a small hand-written paraphrase set as an honest "hard" test.

### D-014: Statistics reporting

- **Status:** Locked | **Phase:** 7
- **Decision:** Every proportion is reported with a Wilson 95% confidence interval and its sample size.
- **Rationale:** Small samples (about 150 labels) give wide intervals; stating them is honest.
- **Experiment:** Implement the interval and test it against hand-computed known values.
- **Result:** *(empty)*
- **Tradeoff:** Tables get busier.
- **Revisit if:** you need comparisons between two rates (add a proper test or overlapping-interval caution).

### D-015: Reproducibility

- **Status:** Locked | **Phase:** 1, 6
- **Decision:** Pinned dependencies; pinned dataset revisions (commit hashes); fixed seeds; every run writes a manifest (config hash, git commit, dataset revisions, timings, library versions).
- **Implemented in:** loaders accept a `revision` argument (`src/contam/data/benchmarks.py`, `src/contam/data/corpus.py`); the run manifest arrives in Phase 6.
- **Experiment:** From a clean clone, regenerate the headline table and diff against your saved result.
- **Result:** *(empty)*
- **Tradeoff:** Pinning means occasional manual upgrades.
- **Revisit if:** a pinned dataset revision disappears.

### D-016: Tooling

- **Status:** Locked | **Phase:** 1
- **Decision:** Python 3.11+, `pyproject.toml`, pytest, Hypothesis, ruff, mypy, Hugging Face `datasets`, numpy, pandas/pyarrow, matplotlib; `datasketch` for cross-checking only; GitHub Actions for CI (confirm current free terms for public repos).
- **Rationale:** Free, standard, few dependencies.
- **Implemented in:** `pyproject.toml`, `.github/workflows/ci.yml`.
- **Experiment:** CI runs lint, type check and tests on a clean environment.
- **Result:** *(empty)*
- **Revisit if:** CI becomes slow or flaky.

### D-017: Data handling and licenses

- **Status:** Locked | **Phase:** 1, 9
- **Decision:** Commit only IDs, hashes, offsets, scores and snippets of about 200 characters or less. Never commit corpus or benchmark text. `.gitignore` all downloaded data.
- **Rationale:** FineWeb is ODC-By (attribution) and ARC is CC BY-SA 4.0 (share-alike); shipping only identifiers sidesteps redistribution questions. Read each license yourself; this is not legal advice. Note: the test fixtures in `tests/fixtures/` use invented text, not real benchmark items, for this reason.
- **Experiment:** Before every release, grep the repo for large text blobs; keep a license table in the README with links.
- **Result:** *(empty)*
- **Revisit if:** you want to publish a labeled dataset (then check licensing properly first).

### D-018: Corpus sampling

- **Status:** Provisional | **Phase:** 6
- **Decision:** Stream a prefix of `sample-10BT`; verify its spread across the `dump` field; seed any subsampling.
- **Rationale:** Cheap and reproducible; the check guards against a biased prefix.
- **Implemented in:** `stream_documents` and `limit_documents` in `src/contam/data/corpus.py`.
- **Experiment:** Plot dump distribution of the slice and note any skew in the report.
- **Result:** *(empty)*
- **Tradeoff:** A prefix is not guaranteed to be a uniform random sample.
- **Revisit if:** the dump distribution is clearly skewed (then sample across shards).

### D-028: Rolling polynomial hash over BLAKE2b token hashes

- **Status:** Provisional | **Phase:** 2
- **Context:** Hashing every n-gram with a cryptographic hash costs one call plus a string join per window; a 1B-token scan does about 1B windows per n.
- **Options:** BLAKE2b of each joined n-gram; xxhash of each joined n-gram; hash each token once and combine with a rolling polynomial hash.
- **Decision:** Token hash = BLAKE2b (8 bytes) mod 2^61 - 1; n-gram hash = polynomial of token hashes with a fixed base, updated in O(1) per window.
- **Rationale:** Constant work per window, no string building, and fully deterministic across runs, OSes and processes (unlike built-in `hash()`).
- **Implemented in:** `token_hash`, `ngram_hash`, `ngram_hashes` in `src/contam/ngrams.py`.
- **Experiment:** (a) microbenchmark rolling vs per-n-gram BLAKE2b on 1M tokens; (b) count collisions among the distinct benchmark n-grams (expect 0); (c) keep the existing tests: rolling equals direct definition, golden values, identical across `PYTHONHASHSEED`.
- **Result:** *(empty)*
- **Tradeoff:** A fixed base is not adversarially robust. Acceptable for natural text in a measurement tool; state it in the README limitations.
- **Revisit if:** the collision check finds any collision, or you scan far beyond 10^10 n-grams.

### D-029: Identical items are grouped

- **Status:** Locked | **Phase:** 3
- **Context:** Benchmarks contain duplicate or near-identical questions.
- **Decision:** Items with the same normalized text share one index entry; every item id is still reported. Stop-n-gram counts use distinct texts, so duplicates cannot turn their own n-grams into "templates".
- **Implemented in:** grouping in `ExactIndex.build` in `src/contam/exact.py`; test `test_identical_items_share_one_entry_and_both_ids_are_reported`.
- **Experiment:** Count duplicate groups in GSM8K, ARC and MMLU test sets and report them (a finding on its own).
- **Result:** *(empty)*

### D-030: Containment denominator and exact verification

- **Status:** Provisional | **Phase:** 3
- **Context:** Stop-n-gram filtering removes n-grams, so containment must be defined over what remains. "Exact" must not depend on n-gram counting alone.
- **Decision:** Denominator = the item's distinct non-stop n-grams. Level EXACT is granted only when the item's token sequence appears contiguously in the document (token-boundary-safe substring check), and that check runs only for candidates already at or above the near-duplicate threshold.
- **Rationale:** Containment 1.0 can arise without a contiguous copy (the same n-grams in a different order); the substring check removes that false positive at almost no cost.
- **Implemented in:** `ExactIndex._scan_tokens` in `src/contam/exact.py`.
- **Experiment:** Plant items with shuffled sentence order and confirm they reach containment 1.0 but not EXACT.
- **Result:** *(empty)*
- **Tradeoff:** An item whose n-grams are reordered but all present reports as NEAR_DUPLICATE, not EXACT.
- **Revisit if:** the planted-data experiments show the near-duplicate level hiding real exact copies.

### D-031: Minimum item length defaults

- **Status:** Provisional | **Phase:** 3
- **Decision:** `min_tokens` defaults to `min(4, n)`. Shorter items are skipped and listed with the reason `too_short`; items with `min_tokens <= length < n` are matched whole and tagged `short`.
- **Implemented in:** `ExactIndex.build` in `src/contam/exact.py`.
- **Experiment:** Report, per benchmark and view, how many items are skipped and how many are short.
- **Result:** *(empty)*

### D-032: Symbols are separate tokens

- **Status:** Locked | **Phase:** 2
- **Decision:** Tokenizer is `\w+|[^\w\s]`, so "12+30" and "12 + 30" produce the same tokens.
- **Implemented in:** `src/contam/tokenizer.py`; tests in `tests/unit/test_tokenizer.py`.
- **Experiment:** Test on GSM8K-style items with and without spaces around operators.
- **Result:** *(empty)*

### D-033: Question+choices view and labelled options

- **Status:** Provisional | **Phase:** 4
- **Context:** Web pages write multiple-choice options with labels ("A. ... B. ..."). Labels break contiguity, so an item copied this way cannot reach EXACT in the question+choices view even though containment stays high (a test in `tests/unit/test_exact.py` documents this).
- **Options:** keep as is and report the limitation; also match with labels removed; rely on the question-only view for exact matching.
- **Decision:** Keep as is for now; report both views. Revisit after the planted-data experiments.
- **Experiment:** Plant MCQ items with and without option labels; compare recall in both views.
- **Result:** *(partial)* Question+choices view, n=5, thresholds 0.3/0.9, 100 plants per condition on the test set: `choice_shuffle` 0.98 [0.93, 0.99], `labelled_dot` 0.96 [0.90, 0.98], `labelled_paren` 0.94 [0.88, 0.97]. Option labels cost about 2-4 points of recall at this operating point. The question-only view and the exact-match counts for these conditions have not been compared yet.

### D-034: Dev/test split key is the normalized question text
- **Status:** Locked | **Phase:** 4
- **Decision:** Items with the same normalized question always land on the same side of the split (refines D-011). Background documents are split by id so dev and test never share host text.
- **Rationale:** Splitting by item id would let duplicate questions leak from dev into test and inflate test results.
- **Implemented in:** `src/contam/split.py`
- **Experiment:** Report how many duplicate-question groups each benchmark has.
- **Result:** *(empty)*

### D-035: Per-record deterministic randomness
- **Status:** Locked | **Phase:** 4
- **Decision:** Every random choice uses a `random.Random` seeded from a hash of (seed, spec, item id), and only `random()` and `randrange()` (own Fisher-Yates shuffle).
- **Rationale:** Adding a spec or reordering items never changes other records, and output is stable across Python versions.
- **Implemented in:** `make_rng` in `src/contam/synthetic.py`; `src/contam/corrupt.py`
- **Result:** n/a

### D-036: One planted item per document; manifest stores no text
- **Status:** Locked | **Phase:** 4
- **Decision:** Each plant sits in its own document at a paragraph (or word) boundary, surrounded by blank lines. The manifest stores offsets, lengths and digests only.
- **Implemented in:** `src/contam/inject.py` (`verify_plants` checks every offset)
- **Result:** n/a

### D-037: Control flags are an upper bound on the false-positive rate
- **Status:** Locked | **Phase:** 4
- **Context:** On real background text, a "false positive" in a control document may be genuine contamination.
- **Decision:** Report control flag rate with a Wilson interval and call it an upper bound. Do NOT screen controls with the detector under test (that would make precision look perfect by construction). Real precision comes from hand-labelling (D-012).
- **Result:** Real-data run: 0 of 500 control documents flagged (Wilson upper bound 0.008). No setting ever flagged a control, so the bound never constrained the selection in D-039.

### D-038: Recall definition and unindexed items
- **Status:** Locked | **Phase:** 4
- **Decision:** A plant is detected if its (document, item) pair is reported at or above the thresholds. Plants of items the index skipped (too short, all template n-grams) are excluded from recall and counted as `unindexed`.
- **Implemented in:** `summarize` in `src/contam/evaluate.py`
- **Result:** Real-data run: 0 unindexed plants (every planted item was indexable at n=5).

### D-039: Operating-point selection rule
- **Status:** Provisional | **Phase:** 4
- **Decision:** On dev data only, maximize macro recall (every corruption condition weighted equally) among settings whose Wilson UPPER bound on the control flag rate is at most 0.05. Ties prefer stricter thresholds, then larger n, then no stop-n-gram filter. The point is written to `operating_point.json` before the test corpus is built.
- **Experiment:** Compare the chosen point against the best-recall point without the false-positive bound.
- **Result:** *(partial)* On dev data the rule selected n=5, view question_choices, partial 0.3, near_duplicate 0.9 in both the real-data run and the synthetic demo. Because the false-positive bound never bound (D-037), the rule reduced to maximizing macro recall, which favours the loosest settings, and the choice sits on the grid boundary. Treat it as provisional until precision is measured on hand-labelled real hits (D-012). The comparison without the bound has not been run.
- **Revisit if:** macro recall hides a condition you care about (try a minimum-recall rule per condition).

### D-040: Scan once at a floor threshold, then re-threshold
- **Status:** Locked | **Phase:** 4
- **Decision:** Scan each corpus once with thresholds near zero, store containment and the exact flag per (document, item), and apply any thresholds afterwards.
- **Rationale:** Every threshold setting sees identical data and sweeps cost almost nothing.
- **Implemented in:** `score_corpus`, `summarize` in `src/contam/evaluate.py`
- **Result:** n/a


### D-041: Phase 5 purpose and hypothesis
- **Status:** Provisional | **Phase:** 5
- **Context:** Phase 4 showed recall collapsing at 20-30% word edits. Deleting a fraction p of words destroys every n-gram window that touches a deleted word, so containment is expected to be about (1 - p)^n. For n=5 that is 0.33 at p=0.2 and 0.17 at p=0.3, against observed recall of 0.51 and 0.10 at a 0.3 threshold. MinHash over the *same* n-grams cannot change this arithmetic.
- **Hypothesis:** Heavy-edit recall comes from smaller shingles (n=2 or 3), which predict containment of 0.64/0.49 (n=2) and 0.51/0.34 (n=3) at p=0.2/0.3, not from MinHash itself. MinHash+LSH adds value for scale and for item-to-item near-duplicate search.
- **Decision:** Treat Phase 5 as a comparison, not an assumed improvement: evaluate exact containment at n=2 and n=3, and the fuzzy MinHash method, on the same planted harness, by condition, with precision on controls and runtime.
- **Experiment:** Compare predicted (1 - p)^n against observed containment per n; compare recall by condition for exact n=2, 3, 5 and for the fuzzy method.
- **Result:** *(empty)*
- **Tradeoff:** If exact n=3 matches the fuzzy method at lower cost, that is the finding, and the fuzzy method is reported as a scaling option.
- **Revisit if:** precision on controls collapses at n=2 or 3.

### D-042: MinHash implementation and validation
- **Status:** Provisional | **Phase:** 5
- **Decision:** Implement MinHash directly: universal hash functions h_i(x) = (a_i * x + b_i) mod (2^61 - 1) applied to the stable shingle hashes from `ngrams.py`, with 128 permutations by default. Cross-check against `datasketch` (dev dependency only) and against exact Jaccard.
- **Rationale:** The fraction of agreeing minimum values is an unbiased Jaccard estimate with standard deviation sqrt(J(1-J)/k), at most 0.044 for k=128. Implementing it yourself and validating it is stronger evidence of understanding than importing it.
- **Experiment:** On random set pairs, check the estimate lies within 4 standard deviations of exact Jaccard; check agreement with `datasketch`; test determinism across processes.
- **Result:** *(empty)*
- **Revisit if:** estimates are visibly biased (a bug, not a result).

### D-043: LSH banding and S-curve check
- **Status:** Provisional | **Phase:** 5
- **Decision:** Split signatures into b bands of r rows (b * r = number of permutations). A pair becomes a candidate with probability 1 - (1 - s^r)^b at similarity s; the curve rises steepest near (1/b)^(1/r). For example, 128 permutations as 32 bands of 4 rows rises near similarity 0.42. Choose b and r from the target similarity, then verify.
- **Experiment:** Plot the theoretical S-curve against the empirical candidate rate on pairs of known similarity.
- **Result:** *(empty)*
- **Revisit if:** the empirical curve disagrees with theory (a bug).

### D-044: Windowed fuzzy matching with exact verification
- **Status:** Provisional | **Phase:** 5
- **Decision:** Slide windows sized to the item's token length across each document. A window signature is the elementwise minimum of the per-shingle signatures it contains (computed with a rolling minimum, so each shingle is hashed once). LSH proposes candidate (window, item) pairs; each candidate is verified by exact containment of the item's word k-shingles (k = 2 or 3, decided in D-046) and kept only above a verification threshold tuned on dev data (D-011).
- **Rationale:** Whole-document signatures are too coarse for short items; verification keeps precision high.
- **Experiment:** Run on the planted harness and compare recall by condition against exact n=2, 3 and 5; measure documents per second and memory.
- **Result:** *(empty)*
- **Tradeoff:** Much slower than the exact detector; report the cost honestly.
- **Revisit if:** exact n=3 gives the same recall at lower cost (see D-041).

### D-045: Within-benchmark near-duplicate detection
- **Status:** Provisional | **Phase:** 5
- **Decision:** Use MinHash+LSH on benchmark items to find near-duplicate items within a benchmark and between its splits (for example GSM8K train versus test), using word 3-shingles at Jaccard thresholds 0.5, 0.7 and 0.9. Hand-check a sample of 30 pairs.
- **Rationale:** This is the natural use of LSH (item-to-item similarity at scale) and gives real findings without any corpus. It also answers the D-029 experiment.
- **Experiment:** Report the number of near-duplicate pairs per threshold for each benchmark and split pair.
- **Result:** *(empty)*

---

## Decisions you will need to add (reserved IDs)

These don't exist yet because they depend on evidence. Create each entry when you reach it.

| ID | Topic | When |
| --- | --- | --- |
| D-019 | Final tau1 and tau2 values | after dev-set tuning |
| D-020 | Final n and headline operating point | after the sweep |
| D-021 | Stop-n-gram cutoff k | after D-008 experiment |
| D-022 | Window size and LSH banding for M2 | after D-010 experiment |
| D-023 | Final corpus slice size | after throughput is measured |
| D-024 | Checkpoint format and resume strategy | before the full scan |
| D-025 | Multiprocessing design and deterministic merge | before the full scan |
| D-026 | Hit-list output schema | before the full scan |
| D-027 | Whether to run the FineWeb-Edu comparison (RQ5) | after the main scan |
| D-046 | Final M2 parameters (shingle size, permutations, bands x rows, stride, verification threshold) | after the M2 experiments |

---

## Change log (targets, thresholds, scope)

| Date | What changed | Why | Entry |
| --- | --- | --- | --- |
| 2026-10-05 | Phase 5 scope refined: the fuzzy method is compared against exact n=2 and n=3, and within-benchmark duplicate detection is added | Phase 4 showed recall tracks (1 - p)^n, so MinHash over the same n-grams cannot help by itself | D-041 |

