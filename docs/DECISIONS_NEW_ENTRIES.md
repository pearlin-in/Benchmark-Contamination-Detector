# New decision entries from roadmap phases 2-3

Paste these into `docs/DECISIONS.md` (add rows to the Index table, then paste the entries below
D-018). Fill in each **Result** only after you run the experiment. Also edit D-006: the
implementation uses a 61-bit hash space, not 64-bit (see D-028), so the collision estimate there
should read about 4×10⁻⁴ expected false collisions (10⁶ benchmark hashes × 10⁹ corpus n-grams / 2⁶¹).

### D-028: Rolling polynomial hash over BLAKE2b token hashes
- **Status:** Provisional | **Phase:** 2
- **Context:** Hashing every n-gram with a cryptographic hash costs one call plus a string join per window; a 1B-token scan does about 1B windows per n.
- **Options:** BLAKE2b of each joined n-gram; xxhash of each joined n-gram; hash each token once and combine with a rolling polynomial hash.
- **Decision:** Token hash = BLAKE2b (8 bytes) mod 2^61 - 1; n-gram hash = polynomial of token hashes with a fixed base, updated in O(1) per window.
- **Rationale:** Constant work per window, no string building, and fully deterministic across runs, OSes and processes (unlike built-in `hash()`).
- **Experiment:** (a) microbenchmark rolling vs per-n-gram BLAKE2b on 1M tokens; (b) count collisions among the distinct benchmark n-grams (expect 0); (c) keep the existing tests: rolling equals direct definition, golden values, identical across `PYTHONHASHSEED`.
- **Result:** *(empty)*
- **Tradeoff:** A fixed base is not adversarially robust. Acceptable for natural text in a measurement tool; stated in the README limitations.
- **Revisit if:** the collision check finds any collision, or you scan far beyond 10^10 n-grams.

### D-029: Identical items are grouped
- **Status:** Locked | **Phase:** 3
- **Context:** Benchmarks contain duplicate or near-identical questions.
- **Decision:** Items with the same normalized text share one index entry; every item id is still reported. Stop-n-gram counts use distinct texts, so duplicates cannot turn their own n-grams into "templates".
- **Experiment:** Count duplicate groups in GSM8K, ARC and MMLU test sets and report them (a finding on its own).
- **Result:** *(empty)*

### D-030: Containment denominator and exact verification
- **Status:** Provisional | **Phase:** 3
- **Context:** Stop-n-gram filtering removes n-grams, so containment must be defined over what remains. "Exact" must not depend on n-gram counting alone.
- **Decision:** Denominator = the item's distinct non-stop n-grams. Level EXACT is granted only when the item's token sequence appears contiguously in the document (token-boundary-safe substring check), and that check runs only for candidates already at or above the near-duplicate threshold.
- **Rationale:** Containment 1.0 can arise without a contiguous copy (the same n-grams in a different order); the substring check removes that false positive at almost no cost.
- **Experiment:** Plant items with shuffled sentence order and confirm they reach containment 1.0 but not EXACT.
- **Result:** *(empty)*

### D-031: Minimum item length
- **Status:** Provisional | **Phase:** 3
- **Decision:** `min_tokens` defaults to `min(4, n)`. Shorter items are skipped and listed with the reason `too_short`; items with `min_tokens <= length < n` are matched whole and tagged `short`.
- **Experiment:** Report, per benchmark and view, how many items are skipped and how many are short.
- **Result:** *(empty)*

### D-032: Symbols are separate tokens
- **Status:** Locked | **Phase:** 2
- **Decision:** Tokenizer is `\w+|[^\w\s]`, so "12+30" and "12 + 30" produce the same tokens.
- **Experiment:** Test on GSM8K-style items with and without spaces around operators.
- **Result:** *(empty)*

### D-033: Question+choices view and labelled options
- **Status:** Provisional | **Phase:** 4
- **Context:** Web pages write multiple-choice options with labels ("A. ... B. ..."). Labels break contiguity, so an item copied this way cannot reach EXACT in the question+choices view even though containment stays high (a test in `tests/unit/test_exact.py` documents this).
- **Options:** keep as is and report the limitation; also match with labels removed; rely on the question-only view for exact matching.
- **Decision:** Keep as is for now; report both views. Revisit after the planted-data experiments.
- **Experiment:** Plant MCQ items with and without option labels; compare recall in both views.
- **Result:** *(empty)*
