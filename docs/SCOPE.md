# SCOPE.md: Benchmark Contamination Detector

**Status:** v1.0, written before any code. Items marked *provisional* will be settled by evidence in later phases and logged in `DECISIONS.md`. Changing a target after seeing results is allowed only if the change is logged with a reason.

**Verification note:** Facts marked ✓ were checked against the cited source on 2026-10-04. Facts marked ⚠ are from memory or secondary sources and must be re-checked on the primary page before you cite them in your README.

---

## 1. Plain-English summary

Language models are trained on huge web text. Benchmarks (public test sets like GSM8K) are also on the web. If a benchmark's test questions sit inside the training text, a model's score may reflect memorization instead of ability. This is called **test-set contamination**.

This project builds a small, well-tested tool that scans a slice of an open web corpus for benchmark items, and, most importantly, **measures how reliable that detection is**.

---

## 2. Research questions

**Primary question:**

> How much of benchmark B appears in corpus slice C, at what level of similarity, and how reliable is our detection?

**Sub-questions (each must be answerable with a table or figure):**

| ID | Question | How it's answered |
| --- | --- | --- |
| RQ1 | How does recall of an exact n-gram detector degrade as benchmark items are edited? | Planted-item experiment; recall vs. edit intensity |
| RQ2 | Does a MinHash-based near-duplicate detector recover items the exact detector misses, and at what cost in precision and compute? | Same planted data; side-by-side curves; timing |
| RQ3 | What fraction of GSM8K and ARC-Challenge test items appear in the corpus slice at each contamination level? | Real scan; headline table with confidence intervals |
| RQ4 | What do the false positives look like? | Hand-labeled sample of real hits; error taxonomy |
| RQ5 *(optional)* | Does an education-filtered corpus show different contamination rates than the general one? | Same scan on FineWeb vs. FineWeb-Edu slices |

---

## 3. Definitions

**Unit of analysis.** One benchmark *item* (a question plus, where applicable, answer choices). A *hit* is an (item, corpus document) pair that crosses a threshold. An item is "flagged" if it has at least one hit.

**Core quantity: containment.** After normalization (§6), turn each text into its set of n-grams (runs of n consecutive words). For item *i* and document *d*:

```
containment(i, d) = |ngrams(i) ∩ ngrams(d)| / |ngrams(i)|
```

*Plain English:* "what fraction of this test item's phrases also appear in this web page?" We use containment rather than Jaccard because a short item inside a long page has tiny Jaccard similarity even when it is copied word for word.

### Contamination levels

| Level | Name | Operational definition | Detector |
| --- | --- | --- | --- |
| **L3** | Exact | Normalized item text appears as one contiguous span in a document (containment = 1.0, contiguous) | M1 |
| **L2** | Near-duplicate | containment ≥ τ₂ (*provisional* default 0.8) in one document, verified | M1 + M2 |
| **L1** | Partial | τ₁ ≤ containment \< τ₂ (*provisional* default τ₁ = 0.5) in one document | M1 + M2 |
| **L0** | No detected overlap | None of the above | none |
| **Out of scope** | Paraphrase / translation | Same meaning, different words | not detected by design (§5) |

**Reference flag for comparability: "GPT-3-style dirty".** The GPT-3 paper flagged an item when it shared an N-gram with the training data, where N was the 5th-percentile example length in words (after ignoring case, punctuation and whitespace), capped at 13; items shorter than N were flagged on whole-example overlap ✓. We compute this flag too and report it separately, so your numbers can be compared with published practice. It is far more aggressive than L1-L3 (a single shared 13-gram flags an item), so expect it to flag more.

**Thresholds τ₁, τ₂ are not chosen by gut feeling.** They are tuned on the *dev* half of the planted data and then frozen before being evaluated on the *test* half and on real hits (§7, D-011).

**Granularity note.** We scan two text views: *question + choices* (primary) and *question only* (secondary). We report them separately because a leaked question without its answer is less concerning than a leaked question-with-answer.

---

## 4. In scope

### 4.1 Benchmarks

| Benchmark | HF id | License | Test size | Version tier |
| --- | --- | --- | --- | --- |
| GSM8K | `openai/gsm8k` | MIT ✓ | \~1.3k ⚠ (confirm exact count on the card) | **v1** |
| ARC-Challenge | `allenai/ai2_arc` | CC BY-SA 4.0 ✓ | \~1.2k ⚠ | **v1** |
| MMLU | `cais/mmlu` ⚠ (check which mirror is canonical) | MIT ✓ | \~14k ⚠ | v1.1 |
| HellaSwag | check mirror | MIT in the original repo ✓; some mirrors differ ✓ | ⚠ | stretch |

*Why these two for v1:* both are small, free, and behave differently (templated math word problems vs. short science questions), which exposes different failure modes. Always pin the dataset **revision** (commit hash) in your run manifest, because mirrors differ in license and formatting.

### 4.2 Corpus

**Primary: FineWeb** (`HuggingFaceFW/fineweb`) ✓

- English web text, **ODC-By 1.0** license ✓.
- Has sampled configs `sample-10BT` (\~10B GPT-2 tokens, \~27.6 GB on disk), `sample-100BT`, and `sample-350BT`; the card says each is a random sample of the full dataset, with the smaller ones nested ✓.
- Supports streaming (`load_dataset(..., streaming=True)`), so nothing needs to fit on disk ✓.

**Optional second corpus: FineWeb-Edu** (`HuggingFaceFW/fineweb-edu`) ✓, same license and `sample-10BT` config, filtered for educational content. Homework-style pages are more likely to contain textbook problems, so this supports RQ5.

**Slice tiers (token counts approximate; \~2.8 GB of download per 1B tokens, derived from the card's 10B ≈ 27.6 GB):**

| Tier | Size | Use |
| --- | --- | --- |
| S | \~100M tokens (\~0.3 GB) | development, tests, planted experiments |
| **M** | **\~1B tokens (\~2.8 GB)** | **primary headline scan** |
| L | up to 10B tokens (27.6 GB) | stretch only; must stream, cannot be stored on a free tier |

Tier M is the target. It is *provisional*: after Phase 3 you measure throughput and set the real number.

**Representativeness check (required):** the streamed prefix of a sampled config may not be uniformly spread across crawl dumps. FineWeb records a `dump` field per document ✓; plot the dump distribution of your slice and state it in the report.

### 4.3 Detectors

- **M1: Exact n-gram containment** (baseline, always built).
- **M2: MinHash + LSH containment** (near-duplicates; two-stage: cheap candidate generation, then exact verification).
- **M3: Embedding similarity**, *stretch only*.

### 4.4 Deliverables

Python package with CLI; test suite; planted-ground-truth evaluation harness; real-scan results (hit lists, not corpus text); REPORT.md; README; DECISIONS.md.

### 4.5 Compute envelope (free tier)

- **Core design is CPU-only. No GPU is needed** (a GPU only matters for the M3 stretch goal).
- Target machine: a laptop with ≥ 8 GB RAM and \~10 GB free disk.
- Free notebook platforms (Kaggle, Colab) are useful as burst compute. Reported limits: Kaggle ≈ 9-12 h sessions, \~20 GB persistent storage, 30 GPU-hours/week; Colab ≈ 12 h sessions with variable quota ⚠ (these change often and sources disagree; check current terms).
- Because sessions die, **checkpoint/resume is a requirement, not a nicety.**
- **Memory estimate:** the benchmark n-gram table has on the order of 10⁵ entries for v1 (10⁶ with MMLU), which fits in a Python dict comfortably. The corpus is never held in memory.
- **CI:** GitHub Actions is free for public repositories ⚠ (verify current terms).

---

## 5. Non-goals

Each non-goal is deliberate and is stated in the README.

| Non-goal | Why it is excluded |
| --- | --- |
| Proving that any specific model was trained on a benchmark | We scan public corpora, not model training sets. Different question, and needs access we don't have. |
| Naming models as "contaminated" | Same reason; also reputationally irresponsible without evidence. |
| Measuring how much contamination inflates scores | Needs model runs and careful controls; the confounds are serious. Allowed only as a clearly labeled stretch. |
| Detecting paraphrased or translated test items | Published work shows rephrased test data can evade n-gram overlap detection (and embedding similarity) ✓. Reliable paraphrase detection needs LLM-based judges, which cost money. We document this limit instead of pretending to solve it. |
| Model-based detection (perplexity, membership inference, Min-K% style) | Requires model access/GPU and answers a different question. |
| Non-English text | Single-language scope keeps normalization and evaluation tractable. |
| Scanning the full corpus | Infeasible on a free tier; we scan a documented slice and call results lower bounds. |
| Cleaning or removing contaminated data | We detect and measure; we don't produce a decontaminated corpus. |
| Production-grade scale (Spark, distributed) | Over-engineering for a portfolio project; the design choice in D-007 makes it unnecessary at this scale. |

---

## 6. Design decisions

*Each row becomes an entry in `DECISIONS.md` with the evidence you gather. "Provisional" means you will confirm or change it with data.*

| ID | Decision | Choice | Alternatives considered | Rationale | Status |
| --- | --- | --- | --- | --- | --- |
| D-001 | Unit of analysis | Benchmark item; hit = (item, doc) | Document-level; token-level | Matches how published studies report "% of test set contaminated" | Locked |
| D-002 | Text views scanned | Question+choices (primary), question-only (secondary); answers are not scanned alone | Full text with answer rationale | Answer strings are too short and ambiguous to match meaningfully | Locked |
| D-003 | Normalization | Unicode NFKC, lowercase, strip punctuation, collapse whitespace; **keep digits** | Keep punctuation; stem/lemmatize | GPT-3's method ignores case, punctuation and whitespace ✓; digits carry the identity of math problems | Provisional (test impact on GSM8K) |
| D-004 | Tokenization | Simple word-level regex tokens | Model tokenizers (BPE) | Deterministic, fast, model-agnostic. Note: GPT-3 used words ✓, while Llama-2/3 measured on tokens ✓. Document the difference | Locked |
| D-005 | n-gram size | **Sweep n ∈ {5, 8, 13}**; default 8; also report the GPT-3-style adaptive N (cap 13) | Single fixed n | Eight-grams were used by GPT-2's analysis and token 8-grams by Llama-3 ✓; 13 by GPT-3 ✓. Smaller n finds more but flags more boilerplate | Provisional |
| D-006 | Hashing | Stable 64-bit hash (blake2b truncated, or xxhash) | Python `hash()`; 32-bit | `hash()` is salted per process and breaks multiprocessing/reproducibility. Collision math: with \~10⁶ benchmark hashes in a 2⁶⁴ space, the chance a random corpus n-gram collides is ≈ 5×10⁻¹⁴; over 10⁹ corpus n-grams that is ≈ 5×10⁻⁵ expected false collisions, negligible | Locked |
| D-007 | Architecture | **Hold the small side (benchmark n-grams) in memory; stream the large side (corpus) once** | Build a corpus index (suffix array, Spark, search engine) | Indexing the corpus is unnecessary and infeasible on a free tier. GPT-3's team used Spark for exact collisions ✓; at our scale a stream-and-lookup is enough | Locked |
| D-008 | Stop-n-grams | Drop benchmark n-grams shared by ≥ k benchmark items (templates like "which of the following is") | No filtering; corpus-frequency filtering | Reduces false positives from boilerplate. Measure precision with and without | Provisional |
| D-009 | Short-item policy | Items with fewer than n tokens use N_item = item length, are tagged `short`, and are reported separately from headline numbers | Drop them; treat like the rest | Mirrors GPT-3's whole-example rule for short items ✓ but avoids letting low-information matches pollute the headline | Provisional |
| D-010 | Near-duplicate method | Two-stage: (1) LSH candidate generation on MinHash signatures of sliding windows; (2) exact containment verification | One-stage MinHash; embeddings | Windows match the item's length (whole-document signatures are too coarse); verification keeps precision high. Implement MinHash yourself, cross-check against `datasketch` | Provisional |
| D-011 | Threshold selection | Tune on **dev** half of planted data; freeze; evaluate on **test** half + hand-labeled real hits | Tune on everything | Standard train/dev/test discipline applied to detector thresholds; prevents quietly overfitting your own evaluation | Locked |
| D-012 | Validation | (a) Planted ground truth with known corruptions; (b) hand-labeled sample of \~150 real hits | Eyeballing a few examples | You can't measure recall on real data without labels. Planting creates them; hand-labeling measures precision on real data | Locked |
| D-013 | Corruption types | Verbatim; case/whitespace/punctuation; reordered choices; changed numbers; random word deletion/substitution at 5/10/20/30%; truncation; embedded in boilerplate/HTML | More exotic edits | Covers realistic copy-paste degradation. Explicitly *not* natural paraphrase (§5) | Locked |
| D-014 | Statistics | Report proportions with **Wilson 95% confidence intervals**; no bare percentages | Point estimates only | With \~150 labels and precision near 0.9, the interval is roughly ±5 percentage points. Say so honestly | Locked |
| D-015 | Reproducibility | Pinned dependencies; pinned dataset revisions; fixed seeds; run manifest (config hash, git commit, dataset revision, timings) | Ad hoc notebooks | A stranger must be able to regenerate your headline table | Locked |
| D-016 | Tooling | Python 3.11+, `pyproject.toml`, pytest, Hypothesis, ruff, mypy, Hugging Face `datasets`, numpy, pandas/pyarrow, matplotlib; `datasketch` for cross-checking only | Heavier frameworks | All free and standard. Keep dependencies few | Locked |
| D-017 | Data handling | Publish only IDs, hashes, offsets, scores and snippets ≤ \~200 characters; **never redistribute corpus or benchmark text** | Ship the hit texts | FineWeb is ODC-By (attribution) ✓; ARC is CC BY-SA 4.0 (share-alike) ✓. Shipping only identifiers avoids license entanglement. (I'm not a lawyer; read each license yourself.) | Locked |
| D-018 | Sampling | Stream a prefix of `sample-10BT`; verify spread across the `dump` field; seed any subsampling | Random access to shards | Cheap and reproducible; the check guards against a biased prefix | Provisional |

---

## 7. Evaluation plan and success criteria

### Metrics

- **Recall** by corruption type and intensity (planted data): the main result for RQ1/RQ2.
- **Precision**: on matched control documents (planted nothing) and on the hand-labeled real hits.
- **Precision-recall curves** over n and thresholds.
- **Cost**: documents per second, peak memory, wall-clock time for the full scan.
- **Hand-labeling protocol:** \~150 hits stratified by score band and benchmark; labels = true contamination / coincidental template overlap / benign (e.g., a page that legitimately discusses or quotes the problem). Relabel 30 of them a few days later and report your own agreement rate.

### Acceptance criteria (all *provisional targets*)

| # | Criterion |
| --- | --- |
| A1 | Verbatim planted items are recalled at **100%** (anything less is a bug) |
| A2 | M2 recalls ≥ 90% of items with ≤ 10% word-level edits at the chosen operating point, *or* the report explains why not |
| A3 | Precision ≥ 0.90 on hand-labeled real hits at the headline operating point (with Wilson CI), *or* the report explains why not |
| A4 | Full tier-M scan completes with checkpoint/resume; a deliberate crash-and-resume test passes |
| A5 | Clean-clone reproduction of the headline table in a few commands |
| A6 | CI green; test coverage ≥ \~85% with meaningful (not padded) tests |
| A7 | REPORT.md includes the limitations in §8 in the authors' own words |

"Or the report explains why not" is intentional: an honest miss with analysis is better than a quietly adjusted target.

---

## 8. Caveats (must appear in README and REPORT, in your own words)

1. **Overlap in a public corpus is not evidence that any particular model saw the data.** We scan a corpus, not a training set.
2. **Exposure is not the same as inflated performance.** In the GPT-3 analysis, scores on "clean" versions of benchmarks mostly differed little from the originals ✓, and a later open report found that contamination does not necessarily lead to inflated performance ✓. Don't claim otherwise.
3. **Our results are lower bounds.** We scan a slice, not the whole corpus, and exact/near-exact methods miss rewrites.
4. **N-gram and embedding methods can miss rephrased items** ✓. A "clean" result means "no copy-like overlap found", not "uncontaminated".
5. **Processed corpora differ from raw crawls.** FineWeb has been filtered and deduplicated by its authors ⚠, so rates are specific to this corpus in its published form.
6. **Not every hit is a leak.** Pages that discuss, solve, or quote benchmark problems are not necessarily training-set leakage into a *benchmark release*; they are still reported but categorized (D-012).
7. **Results depend on choices.** Normalization, n, thresholds and item views change the numbers; the sensitivity analysis is part of the findings, not an appendix.
8. **Synthetic edits are not natural paraphrase.** Planted-data recall says how robust the detector is to *mechanical* edits only.
9. **English only.** Benchmark versions and mirrors also differ (formatting, splits), so the pinned revision is part of every result.

**Language rules for the write-up:** say "overlap found in corpus slice X", never "model Y is contaminated"; always attach a confidence interval or sample size to a percentage; separate "flagged" from "confirmed after hand-labeling".

---

## 9. Open questions to settle with evidence

| Question | Settled in phase | Decision |
| --- | --- | --- |
| Best default n (5 vs 8 vs 13)? | Eval harness | D-005 |
| Does keeping digits/operators help or hurt GSM8K precision? | Eval harness | D-003 |
| Right window size and LSH banding for M2? | Near-duplicate phase | D-010 |
| What is the real throughput, and therefore the real slice size? | Exact-detector phase | §4.2 |
| Which stop-n-gram cutoff k? | Exact-detector phase | D-008 |
| Does the streamed prefix look representative (by dump)? | Real-scan phase | D-018 |

---

## 10. References

Checked against source on 2026-10-04 ✓:

- Brown et al., 2020, *Language Models are Few-Shot Learners* (Appendix C: contamination methodology; 13-gram overlap; variable N capped at 13; ignoring case, punctuation, whitespace). arXiv:2005.14165.
- *An Open Source Data Contamination Report for Large Language Models* (search-engine / Common Crawl pipeline; contamination growing over time; not necessarily inflating scores). arXiv:2310.17589.
- *Rethinking Benchmark and Contamination for Language Models with Rephrased Samples* (n-gram overlap and embedding similarity fail on rephrased test data; overlap found in HumanEval-related pretraining data). arXiv:2311.04850.
- *A Comprehensive Survey of Contamination Detection Methods in Large Language Models* (summarizes GPT-2 8-grams, GPT-3 13-grams, GPT-4 50-character collisions, Llama-2/3 token-level methods). arXiv:2404.00699.
- Hugging Face dataset cards: `HuggingFaceFW/fineweb` and `HuggingFaceFW/fineweb-edu` (configs, sizes, ODC-By license, streaming usage).
- Benchmark licenses (GSM8K MIT, ARC CC BY-SA 4.0, MMLU MIT, HellaSwag MIT in original repo) as listed in several papers' license tables; **re-check on each dataset card.**

From memory, ⚠ verify before citing:

- Lee et al., 2022, *Deduplicating Training Data Makes Language Models Better* (near-duplicate removal at scale).
- Broder, 1997, *On the resemblance and containment of documents* (MinHash, containment).
- Leskovec, Rajaraman, Ullman, *Mining of Massive Datasets*, ch. 3 (shingling, MinHash, LSH).
- Touvron et al., 2023, Llama 2 paper (token-based contamination method with skip-gram budget; summarized in the survey above ✓).

---

## 11. Glossary (for your future self)

- **n-gram:** a run of n consecutive words. "the cat sat" has two 2-grams: "the cat", "cat sat".
- **Containment:** the fraction of one text's n-grams found in another text.
- **Jaccard similarity:** overlap divided by union of two sets; penalizes length differences.
- **MinHash:** a compact "fingerprint" of a set whose similarity approximates Jaccard.
- **LSH (locality-sensitive hashing):** a trick that groups similar fingerprints into the same bucket so you don't compare every pair.
- **Planted ground truth:** items you insert yourself, so you know exactly what a perfect detector should find.
- **Precision / recall:** of the things flagged, how many were right / of the real ones, how many were found.
- **Wilson interval:** a confidence interval for a proportion that behaves well with small samples.