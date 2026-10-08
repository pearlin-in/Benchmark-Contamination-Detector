# Report: Benchmark contamination scan

## Summary

Two scans of a ~76M-token FineWeb slice against GSM8K and ARC-Challenge test items.

- **Strict scan** (`n=3`, `partial=0.5`, stop-n-gram filter `k=5`, question+choices view):
  **0 exact / 0 near-duplicate / 0 partial matches** across 2,491 items.
- **Loose scan** (`n=2`, `partial=0.3`, question+choices view): 231 hits, 31 ARC and
  3 GSM8K items flagged at `partial` or above, 0 at `near-duplicate` or `exact`.

Inspection of the loose-scan hits shows they are template phrases and topic lists,
not contamination. The strict scan confirms this: the hits vanish when the
stop-n-gram filter and a stricter partial threshold are applied. See
`docs/DECISIONS.md` D-052 and D-053 for the full record.

**These are lower bounds for a corpus slice and say nothing about any model.**

## Scan parameters

| | Strict | Loose |
|---|---|---|
| n | 3 | 2 |
| partial threshold | 0.5 | 0.3 |
| near-duplicate threshold | 0.9 | 0.9 |
| stop-n-gram k | 5 | (none) |
| view | question_choices | question_choices |
| documents | 143,176 | 143,176 |
| tokens | 76,425,015 | 76,425,015 |
| runtime | 136 s | — |
| throughput | 561,314 tokens/s | — |

## Headline result (strict scan)

| Benchmark | Items indexed | ≥ partial | ≥ near-dup | exact |
|---|---:|---:|---:|---:|
| ARC-Challenge | 1,172 | 0 [0.00%, 0.33%] | 0 [0.00%, 0.33%] | 0 |
| GSM8K | 1,319 | 0 [0.00%, 0.29%] | 0 [0.00%, 0.29%] | 0 |

0 items skipped as too short or template-only. Intervals are 95% Wilson.

## Loose scan (error analysis)

An earlier, looser run (`n=2`, `partial=0.3`) produced 231 hits, flagging 31 ARC
and 3 GSM8K items at `partial` or above.

| Benchmark | Items indexed | ≥ partial | ≥ near-dup | exact |
|---|---:|---:|---:|---:|
| ARC-Challenge | 1,172 | 31 [1.87%, 3.73%] | 0 [0.00%, 0.33%] | 0 |
| GSM8K | 1,319 | 3 [0.08%, 0.67%] | 0 [0.00%, 0.29%] | 0 |

Inspection of the 34 partial hits shows they fall into three categories, all
consistent with incidental overlap rather than leakage:

1. **Template phrases.** "which of the following is not an example of" accounts
   for many hits across unrelated documents (a modeling-scam page, an aortic
   valve page, a communicative-tools page). The phrase is generic, not
   benchmark-specific.
2. **Topic lists.** "the skeletal system the nervous system the circulatory
   system..." matches ARC answer choices verbatim, but the same list appears on
   unrelated anatomy pages.
3. **Short common phrases.** "the sun and the moon", "is a renewable resource",
   "is made up of more than" — high-frequency n-grams that accumulate over a
   long document at low n.

One item (`TIMSS_2003_8_pg94`) appears in 12 unrelated documents, each sharing
only the phrase "is an example of". That pattern — one item matching many
documents that have nothing to do with the item — is the signature of incidental
n-gram overlap, not of a copied test item.

The loose-scan hit rate (~1.6 per 1,000 documents) grows steadily with corpus
size, which is also consistent with incidental overlap.

**Conclusion:** the partial hits are weak overlap candidates, not contamination.
Real precision on topically related pages is unknown and would require
hand-labeling at scale. This is the main limitation of the loose configuration.

## Sensitivity

Moving from `n=2, partial=0.3` to `n=3, partial=0.5, stop-k=5` eliminates all
34 partial hits, with no loss of exact or near-duplicate recall (both are 0 in
both runs). This is the expected effect of the stop-n-gram filter and a stricter
partial threshold: template n-grams are removed and the remaining matches are
too weak to cross 0.5.

## Limitations

- One corpus slice (~76M tokens of FineWeb `sample-10BT`), English-only.
  Absolute rates are lower bounds for the full corpus.
- Synthetic corruption is easier than natural paraphrase; planted-data recall
  is optimistic.
- Word-level tokens, so numbers are not directly comparable to BPE-based
  studies.
- No paraphrase detection.
- Controls are random web pages, so the false-positive bound says nothing
  about precision on topically related pages.
- This scan does not show that any model saw any benchmark item, and exposure
  is not proof of inflated scores.

## Reproduce

```bash
# Strict scan
contam scan \
  --benchmark gsm8k --benchmark arc_challenge \
  --operating-point results/phase6_eval/operating_point.json \
  --n 3 --partial 0.5 --stop-k 5 \
  --max-tokens 100000000 \
  --out C:\contam_scans\tier_s_strict

# Report
contam report --scan C:\contam_scans\tier_s_strict --top 50

Strict scan (n=3, partial=0.5, stop-k=5, question+choices view) over ~76M FineWeb tokens.

scan finished: 143,176 documents, 76,425,015 tokens, 0 hits
items flagged (at least one hit); 95% Wilson interval over indexed items
benchmark         items  indexed              >= partial         >= near-dup  exact
arc_challenge      1172     1172        0 [0.00%, 0.33%]    0 [0.00%, 0.33%]      0
gsm8k              1319     1319        0 [0.00%, 0.29%]    0 [0.00%, 0.29%]      0
items skipped (too short or template-only): 0
These are lower bounds for a corpus SLICE and say nothing about any model.


