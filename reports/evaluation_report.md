# Evaluation report: mcp-schema-integrity-benchmark

This summarizes a single run of `src/detector/evaluate.py` against
`fixtures/mutation_corpus.json`. Every number below comes directly from
`results/results.json`; nothing here is fabricated or estimated.

## Corpus

19 synthetic MCP-like Tool cases across 4 mock tools (`read_file`,
`send_notification`, `query_database`, `list_directory`), each shaped like
a real MCP Tool object (`name`, `description`, `inputSchema`,
`annotations`):

- 13 cases with a single injected mutation, one per test category
  (2 cases each for `parameter_type_change`, `required_field_change`,
  `description_change`, `enum_expansion`, `annotation_change`,
  `unexpected_additional_fields`; 1 case for
  `schema_hash_mismatch_unclassified`).
- 6 unmutated-control cases: 3 exact duplicates, and 3 deliberately
  adversarial controls, benign changes that shouldn't matter semantically,
  included specifically to check whether the detector over-fires on a
  change it shouldn't:
  - a reorder of an `enum` list's values (same set, different order)
  - a reorder of a `required` list's entries (same required fields,
    different order)
  - an annotation (`readOnlyHint`) written out explicitly with its own
    MCP-defined default value, instead of left omitted

## Results

| Metric | Value |
|---|---|
| Mutation detection rate | 1.0 (13/13 genuine mutations detected) |
| False positive rate | 0.5, 3 false positives out of 6 controls |
| Undetected mutations | 0 |
| Correctly classified mutations | 13/13 |

Detection by category also came back at 1.0 for all seven mutation
categories, but with 1-2 cases per category that reflects the classifier
handling the specific cases it was built to handle, not a generalizable
per-category accuracy figure.

Each case in `results.json` records `detection_correct` (whether the
mutated yes/no call was right, applies to every case) and
`category_classification_correct` (whether the predicted category set
matched the expected category exactly, `null` for unmutated controls,
since there's no category to get right when nothing was mutated). An
extra, unrelated category alongside the correct one no longer counts as a
correct classification either, since each mutated fixture injects exactly
one change.

## Interpretation

The 100% detection rate isn't a claim about a clever detector, it's an
expected property of comparing SHA-256 fingerprints. Any content change
flips the hash, so it would catch any mutation, including ones outside
the 7 named categories here. What this design can't tell you is *why*
something changed or whether it matters; it only answers "did the content
change."

The more interesting result is the classification, and specifically where
it goes wrong. The rule-based classifier correctly labeled all 13 genuine
mutations with their true category, which took covering seven different
diff shapes with separate heuristics rather than one blanket rule. But all
three adversarial controls broke it, for two related reasons:

- Reordering an enum's values, or a required list's entries, without
  changing their contents still changes the fingerprint, because
  canonicalization sorts dictionary keys but not list contents. The enum
  reorder gets mislabeled as `parameter_type_change` (the enum-expansion
  rule only recognizes strict growth, not reordering); the required-list
  reorder gets labeled `required_field_change`, which is the right
  category name for the wrong reason, since nothing was actually
  mutated.
- Writing an annotation out explicitly with the exact value the MCP spec
  already treats as its default produces a genuinely new key in the diff,
  which the classifier has no way to distinguish from an actual behavior
  change, so it comes back as `annotation_change`.

Three false positives out of six controls, traceable to two design
choices: list-order-sensitive hashing, and no concept of protocol-level
default values.

## Fixes applied since the previous version of this report

Two bugs were found and fixed in the detector itself:

- A fingerprint mismatch caused by a value that differs in canonical JSON
  form but compares equal under plain Python equality (`1 == 1.0`,
  `True == 1`) used to produce an empty diff and an empty category set,
  silently reporting `mutated=True` with nothing to explain it. It now
  falls back to `schema_hash_mismatch_unclassified`, consistent with every
  other diff shape the classifier doesn't have a specific rule for.
- Enum-expansion classification used to build a plain `set()` of enum
  values, which raises `TypeError` the moment an enum value is a list or
  object (unhashable). It now canonicalizes each value to a JSON string
  before comparing, so object- and array-valued enums are classified the
  same way string-valued ones already were.

## Limitations of this evaluation

- **Small, purpose-built corpus.** 19 cases across 4 mock tools is enough
  to exercise every named category at least once and surface three
  distinct benign-equivalence false positives, but far too small to say
  anything about a false-positive rate in general. The 0.5 figure is
  "3 adversarial cases out of 6 controls in this fixture set," not a
  population-level estimate.
- **No compound mutations.** Every mutated case changes exactly one
  thing. Real tampering could combine several changes at once; the
  classifier would report the union of matched categories, but this
  hasn't been tested.
- **Other benign-equivalence cases remain untested**: Unicode
  normalization forms and whitespace-only string differences aren't in
  the corpus. Numeric representation (`1` vs `1.0`) and boolean/numeric
  equality (`true` vs `1`) are covered by unit tests directly against the
  classifier rather than as corpus fixtures.
- **The classifier is a fixed set of path-based rules**, not a learned or
  formally verified system. It will correctly flag any content change as
  a mismatch (the hash guarantees that), but it can misclassify a diff
  shape it wasn't designed to recognize, or one that's semantically inert
  but structurally different, as this evaluation's three false positives
  show.
- **Synthetic tools only.** These are purpose-built MCP-like Tool objects
  modeled on the real MCP Tool shape (`inputSchema`, `annotations`), not
  schemas pulled from or validated against a real MCP server or SDK, and
  they exercise only a narrow subset of JSON Schema. See README for the
  full scope and safety statement.
