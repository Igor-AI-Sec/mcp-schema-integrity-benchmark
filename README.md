# mcp-schema-integrity-benchmark

I built this to answer a narrow question: if an MCP tool's schema changes
between when an agent first trusts it and when it actually calls the
tool, can you catch that from the schema alone? And if you can, how well
can you tell *what* changed?

Short answer: yes, trivially, if you're willing to hash the schema and
compare. The harder part, figuring out what kind of change it was, worked
on every genuine mutation in the fixture corpus, and broke in several
specific, related ways. Those breaks are the more interesting result here,
more than the 100% detection number is.

Two things worth knowing before you read further:

- The fixtures are synthetic MCP-like Tool objects (`name`, `description`,
  `inputSchema`, `annotations`), a purpose-built fixture corpus with
  explicitly stored ground-truth categories. Nothing here talks to a real
  MCP server, uses the MCP SDK, or opens a network connection. See "MCP
  scope" below.
- Calling this an "integrity" tool rather than a "poisoning detector" is
  deliberate. It notices a schema changed. It has no way to know who
  changed it or why. See "Threat model" below.

## What it does

Three pieces:

1. A `ToolRegistry` "registers" a tool schema and stores a SHA-256
   fingerprint of its canonical form, from a deep copy, so mutating the
   original dict after registration can't quietly change what's trusted.
2. A `SchemaIntegrityMonitor` checks a later "presented" schema against
   that fingerprint.
3. If the fingerprints don't match, a structural diff runs and gets
   classified into one of a handful of buckets: parameter type change,
   required-field change, description change, enum expansion, annotation
   change, an unexpected new field, or, when none of those fit,
   unclassified. A fingerprint mismatch is always authoritative: if the
   diff can't explain it, the result still comes back `mutated=True`,
   just with the fallback category rather than a specific one.

`src/detector/evaluate.py` runs all of this over a fixture corpus and
writes `results/results.json`.

## How I tested it

The fixture corpus (`fixtures/mutation_corpus.json`) has 19 purpose-built
cases: 13 with a single mutation injected, and 6 unmutated controls. Each
case is a pair of synthetic MCP-like Tool objects, an `original_schema`
and a `presented_schema`, with the expected label stored explicitly as
`ground_truth_category`. One shaped like this:

```json
{
  "name": "read_file",
  "description": "Reads the contents of a file from the sandboxed workspace directory.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "path": {"type": "string", "description": "Relative path to the file within the sandbox."},
      "encoding": {"type": "string", "description": "Text encoding to use.", "enum": ["utf-8", "ascii"]}
    },
    "required": ["path"]
  },
  "annotations": {
    "title": "Read File",
    "readOnlyHint": true,
    "destructiveHint": false,
    "idempotentHint": true,
    "openWorldHint": false
  }
}
```

`inputSchema` is plain JSON Schema (`type`, `properties`, `required`) and
`annotations` uses the hint fields MCP tools actually define
(`readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint`,
`title`). The five `query_database` cases also carry an `outputSchema`,
identical in the original and presented schemas.

One case adds a `_meta` field between registration and presentation.
`_meta` is a field MCP itself permits, so this isn't testing whether the
resulting schema is valid. It's testing whether the detector notices
*anything* showing up that wasn't in the trusted baseline, valid MCP field
or not. That's what `unexpected_additional_fields` actually means here:
not present at registration time. It says nothing about whether the new
field would be fine on its own.

For each case, the evaluation registers the original schema, presents the
(possibly mutated) version, and checks whether the detector's verdict
matches the stored ground truth. That's the whole methodology, nothing
more elaborate than that.

Three of the six controls are exact duplicates, so nothing should get
flagged. The other three are deliberately adversarial: changes that
shouldn't matter semantically, built to see whether the detector notices
anyway.

- **Enum reorder.** Same permitted values, different order:
  `["ops", "alerts"]` became `["alerts", "ops"]`. Nothing about what the
  tool can do changed.
- **Required-list reorder.** Same required fields, different order:
  `["channel", "message"]` became `["message", "channel"]`. The set of
  required fields is unchanged.
- **Explicit annotation default.** A schema that omits `readOnlyHint`
  (which the MCP spec treats as defaulting to `false`) against a presented
  schema that sets `readOnlyHint: false` explicitly. Nothing about the
  tool's declared behavior changed; the field just went from implicit to
  explicit.

All three came back flagged as mutated. Canonicalization sorts dictionary
keys but not the contents of lists, so a reordered list still produces a
different hash. And the detector has no concept of an MCP-defined default
value, so writing one out explicitly looks exactly like adding a new
annotation. Each also gets a label that doesn't describe it, or the
fallback, since the rule that would explain each one correctly (an
unordered list comparison, or a default-aware annotation comparison)
doesn't exist:

| Control | Predicted category |
|---|---|
| Enum reorder | `schema_hash_mismatch_unclassified` (an enum edit is only called an expansion when it adds a new distinct value, so a reorder falls back) |
| Required-list reorder | `required_field_change` (correct category, wrong verdict: it isn't a mutation at all) |
| Explicit annotation default | `annotation_change` (correct category, wrong verdict, same reason) |

If someone asked me what this project actually shows, that's the answer,
not the 100% detection figure. 100% is close to guaranteed once you're
comparing cryptographic hashes: any content change flips the hash, so of
course every genuine mutation gets caught. The useful result is the
failure mode: three different changes that clearly shouldn't matter
semantically all got flagged, for two distinct underlying reasons
(list-order sensitivity, and no notion of protocol-level defaults), and I
know exactly why in each case.

## Results

| Metric | Value |
|---|---|
| Mutation detection | 13 of 13 |
| False positives | 3 out of 6 controls |
| Undetected mutations | 0 |
| Correctly classified mutations | 13 of 13 |

Every mutation category came back at 100% detection too, but with only
1-2 cases per category that's not saying much statistically. It means the
classifier's rules work on the specific cases in this corpus, not that
they'd hold up on a larger or less friendly one. Full per-case output is
in `results/results.json`; a longer write-up is in
`reports/evaluation_report.md`.

Each case result also records `detection_correct` (did the yes/no mutated
call match reality, meaningful for every case, controls included)
separately from `category_classification_correct` (did the predicted
category match exactly, only meaningful for actual mutations, `null` for
controls, since there was never a category to get right there). A
predicted category set with an extra, unrelated category alongside the
correct one no longer counts as correct either: these fixtures each
inject exactly one mutation, so anything beyond the one expected category
means the classification was wrong. Keeping detection and classification
as two separate fields, instead of collapsing them into one, matters
because a correct "unmutated" call on a control would otherwise look
identical to a missed classification, which isn't the same failure.

## Threat model

There are basically four reasons a schema shown at invocation might not
match what was trusted at registration: someone tampers with it on
purpose; someone ships a legitimate update and nobody refreshes the trust
baseline; the registry gets compromised and starts serving something
different than what was originally registered; or the schema is
semantically the same but represented differently, a reordered `enum`
list or `required` list, or an annotation written out explicitly instead
of left to its protocol default, all of which are demonstrated as real
cases above.

This detector can't tell those apart. It only compares against whatever
was most recently registered as trusted. If a registry is compromised
*after* a legitimate schema was already registered, and it later starts
serving something different, that difference still shows up as a hash
mismatch, so it does get flagged as *a* change. What it can't tell you is
why: a legitimate update, tampering in transit, and a compromised registry
all look identical from a schema diff.

What it genuinely can't catch at all: if the registry is already
compromised at the moment a tool is first registered, that compromised
schema just becomes the new trusted baseline, and nothing about it looks
wrong afterward. Same story if an attacker can change both the registered
baseline and the presented schema together: keep them in sync and the
hashes still match.

The name says "integrity," not "attribution," on purpose. It checks
whether a schema still matches what was trusted. It doesn't know who
changed it or why.

## MCP scope

This evaluates synthetic MCP-like Tool objects, plain dictionaries with
the fields real MCP Tool objects use (`name`, `description`, `inputSchema`
as JSON Schema, and `annotations`), not fetched from or validated against
a live server. It doesn't import the MCP SDK, doesn't open a connection to
anything, and never talks to a real MCP server, mine or anyone else's. If
you're looking for evidence about MCP protocol-level security, this isn't
it. It's evidence about one integrity-checking technique (hash the
canonical form, diff it, classify the diff) applied to data shaped like
what an MCP tool would actually send.

The fixtures also exercise a narrow slice of JSON Schema on purpose:
`type`, `properties`, `required`, `enum`, `default`, and one level of
nesting. MCP's `inputSchema`/`outputSchema` fields support the full JSON
Schema 2020-12 vocabulary, including `$ref`, `oneOf`/`anyOf`/`allOf`,
`patternProperties`, conditional schemas, and deeply nested structures,
none of which this corpus tests. Nothing here should be read as evidence
about how the classifier behaves on that broader surface.

## Reproducing this

From this directory:

```bash
python -m unittest discover -s tests -v
python -c "import sys; sys.path.insert(0, 'src'); from detector.evaluate import main; raise SystemExit(main())"
```

The second command reruns the evaluation and overwrites
`results/results.json`. Both are deterministic, no network calls, nothing
random, so running them again should give you the same numbers as in
`reports/evaluation_report.md`. The results file also records a
`generated_at` timestamp, so regenerating it changes that line even though
the benchmark numbers stay the same.

(`python -m detector.evaluate` won't work directly, because `src/` isn't
on the path by default here. The one-liner above handles that without an
editable install. `pip install -e .` would also work if you'd rather have
`import detector` resolve normally.)

## Limitations

- The corpus is small: 19 cases, 4 mock tools. Enough to exercise every
  category at least once and to surface three distinct benign-equivalence
  false positives, not enough to say anything about a real-world
  false-positive rate. Every mutated case changes exactly one field. The
  `required` cases cover adding an entry (`read_file`) and removing the
  only entry (`query_database`); removing one of several entries is not in
  the corpus. Unicode normalization and whitespace-only string differences
  are still untested. A number written as `1.0` instead of `1`, and `true`
  against `1`, are covered as unit tests on the detector rather than as
  corpus fixtures. Both give a hash mismatch with an empty structural diff
  (Python treats each pair as equal), so both fall back to
  `schema_hash_mismatch_unclassified`, which is the honest answer but not a
  very informative fixture. They are different kinds of case: `1` vs `1.0`
  is benign, while `true` vs `1` is a real type change.
- The classifier is a fixed set of rules keyed on where in the schema
  something changed, not anything learned. It will flag a mutation it
  doesn't recognize (falling back to "unclassified"). For the
  benign-equivalence controls above it either falls back or names a
  category for a change that isn't one. The hash is order-sensitive, so a
  reordered `enum` or `required` list is always reported as a mutation. For
  classification, `enum` members are compared as a set, so a reorder is not
  called an expansion, but that does not change the verdict. The
  classifier also has no concept of MCP's own annotation defaults. Together
  these produce the three false positives; fixing them would mean teaching
  the detector what "semantically inert" means for a given field, which is
  a different, harder problem than diffing values.
- The corpus has no compound-mutation fixtures: every genuine-mutation
  case changes one thing at a time. The classifier returns the union of
  the categories matched by each diff entry, and unit tests cover that
  union (and that an extra predicted category makes a classification
  wrong), but how it performs on compound mutations in a corpus is not
  measured. Real tampering probably wouldn't be that considerate.
- Classification reads where a change sits, by key. A schema keyword such
  as `description`, `required`, `enum` or `type` selects a category. A
  property name directly under `properties` does not, even when it is
  called `description`, `type`, `enum`, `annotations` or `required`, or
  contains a dot; a new property is reported as an unexpected additional
  field. Values under `default`, `const` and `examples` are data, so keys
  inside them are never read as keywords. That is the whole structural
  model. Other constructs that carry names or nested schemas, such as
  `$defs`, `patternProperties` and `dependentSchemas`, are outside it, and
  a change there can fall back to `schema_hash_mismatch_unclassified` or be
  given a category that doesn't describe it.
- The classifier is shallow in other ways too. Added constraint keywords
  (`maximum`, `oneOf`, `additionalProperties`) are reported as unexpected
  additional fields. A removed property, a changed top-level
  `inputSchema.type`, a changed numeric constraint and a `type` change
  inside `outputSchema` all fall back to
  `schema_hash_mismatch_unclassified`; only `type` changes under
  `inputSchema.properties` count as `parameter_type_change`. An enum edit is
  labelled `enum_expansion` only when every old value is kept and a new
  distinct value is added (values are compared as JSON Schema does, so `1`
  and `1.0` are the same value while `true` and `1` are not). A reorder, a
  duplicate, a removal, a replacement, and an enum created or removed
  outright fall back as well.
- Syntactic equivalence also means that equal numbers written differently
  (`1` vs `1.0`, `100` vs `100.0`) produce different hashes. They are
  false positives of the same kind as the three controls above, but they
  are covered only by unit tests, not by the corpus.
- The fixtures cover a narrow slice of JSON Schema (`type`, `properties`,
  `required`, `enum`, `default`), not the full JSON Schema 2020-12
  vocabulary that MCP's `inputSchema`/`outputSchema` actually allow. See
  "MCP scope" above.
- This project uses only the standard library and `unittest`, so it has
  no dependencies to install. `pyproject.toml` lists `pytest` as an
  optional dependency if you'd rather run these same tests under it.
- This isn't a production security tool. It measures one specific
  technique, hash comparison plus rule-based diffing, against a synthetic,
  purpose-built corpus. Don't read the numbers above as evidence about how
  this would hold up in a real deployment.

## License

MIT, see [LICENSE](LICENSE).
