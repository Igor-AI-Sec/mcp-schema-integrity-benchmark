# Evaluation report — mcp-schema-integrity-benchmark

This summarizes a single run of `src/detector/evaluate.py` against
`fixtures/mutation_corpus.json`. Every number below comes directly from
`results/results.json` — nothing here is hand-written or estimated.

## Corpus

17 synthetic MCP Tool cases across 3 mock tools (`read_file`,
`send_notification`, `query_database`), each shaped like a real MCP Tool
object (`name`, `description`, `inputSchema`, `annotations`):

- 13 cases with a single injected mutation, one per test category
  (2 cases each for `parameter_type_change`, `required_field_change`,
  `description_change`, `enum_expansion`, `annotation_change`,
  `unexpected_additional_fields`; 1 case for
  `schema_hash_mismatch_unclassified`).
- 4 unmutated-control cases: 3 exact duplicates, and 1 deliberately
  adversarial control — a benign reorder of an `enum` list's values (same
  set, different order) — included specifically to check whether the
  detector over-fires on a change that shouldn't matter.

## Results

| Metric | Value |
|---|---|
| Mutation detection rate | 1.0 (13/13 genuine mutations detected) |
| False positive rate | 0.25 — 1 false positive out of 4 controls |
| Undetected mutations | 0 |
| Correctly classified mutations | 13/13 |

Detection by category also came back at 1.0 for all seven mutation
categories, but with 1–2 cases per category that reflects the classifier
handling the specific cases it was built to handle, not a generalizable
per-category accuracy figure.

Each case in `results.json` records `detection_correct` (whether the
mutated yes/no call was right — applies to every case) and
`category_classification_correct` (whether the predicted category was
right — `null` for unmutated controls, since there's no category to get
right when nothing was mutated).

## Interpretation

The 100% detection rate isn't a claim about a clever detector — it's an
expected property of comparing SHA-256 fingerprints. Any content change
flips the hash, so it would catch any mutation, including ones outside
the 7 named categories here. What this design can't tell you is *why*
something changed or whether it matters; it only answers "did the content
change."

The more interesting result is the classification, and specifically where
it went wrong. The rule-based classifier correctly labeled all 13 genuine
mutations with their true category, which took covering seven different
diff shapes with separate heuristics rather than one blanket rule. But
the adversarial control case broke it: reordering an enum's values
without changing its contents still changes the fingerprint, because
canonicalization sorts dictionary keys but not list contents. The
detector flags it as mutated, and specifically mislabels it as
`parameter_type_change`, since the enum-expansion rule only recognizes
strict growth, not reordering. One false positive out of four controls —
traceable to that one design choice.

## Limitations of this evaluation

- **Small, hand-authored corpus.** 17 cases across 3 mock tools is enough
  to exercise every named category at least once and catch the ordering
  issue, but far too small to say anything about a false-positive rate in
  general — the 0.25 figure is "1 adversarial case out of 4 controls I
  happened to include," not a population-level estimate.
- **No compound mutations.** Every mutated case changes exactly one
  thing. Real tampering could combine several changes at once; the
  classifier would report the union of matched categories, but this
  hasn't been tested.
- **No other benign-equivalence cases** beyond the one enum reorder (e.g.
  numeric `1` vs `1.0`, unicode normalization forms, whitespace-only
  string differences). These would likely produce further false
  positives for the same underlying reason.
- **The classifier is a fixed set of path-based rules**, not a learned or
  formally verified system — it will misclassify any diff shape it
  wasn't designed to recognize as `schema_hash_mismatch_unclassified`
  (correctly flagging tampering, incorrectly attributing a cause).
- **Synthetic tools only.** These are hand-written MCP Tool objects
  modeled on the real MCP Tool shape (`inputSchema`, `annotations`), not
  schemas pulled from or validated against a real MCP server or SDK. See
  README for the full scope and safety statement.
