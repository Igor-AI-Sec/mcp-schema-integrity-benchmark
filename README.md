# mcp-schema-integrity-benchmark

I built this to answer a narrow question: if an MCP tool's schema changes
between when an agent first trusts it and when it actually calls the
tool, can you catch that from the schema alone? And if you can, how well
can you tell *what* changed?

Short answer: yes, trivially, if you're willing to hash the schema and
compare. The harder part — figuring out what kind of change it was —
worked on every case I built for it, and broke in one specific way I
didn't expect going in. That break is the more interesting result here,
more than the 100% detection number is.

Two things worth knowing before you read further:

- The fixtures are shaped like real MCP Tool objects (`name`,
  `description`, `inputSchema`, `annotations`), written by hand. Nothing
  here talks to a real MCP server, uses the MCP SDK, or opens a network
  connection. See "MCP scope" below.
- Calling this an "integrity" tool rather than a "poisoning detector" is
  deliberate. It notices a schema changed. It has no way to know who
  changed it or why. See "Threat model" below.

## What it does

Three pieces:

1. A `ToolRegistry` "registers" a tool schema and stores a SHA-256
   fingerprint of its canonical form — a deep copy, so mutating the
   original dict after registration can't quietly change what's trusted.
2. A `SchemaIntegrityMonitor` checks a later "presented" schema against
   that fingerprint.
3. If the fingerprints don't match, a structural diff runs and gets
   classified into one of a handful of buckets: parameter type change,
   required-field change, description change, enum expansion, annotation
   change, an unexpected new field, or — when none of those fit —
   unclassified.

`src/detector/evaluate.py` runs all of this over a fixture corpus and
writes `results/results.json`.

## How I tested it

I wrote 17 cases by hand: 13 with a single mutation injected, and 4
controls. Each case is a pair of MCP Tool objects — an `original_schema`
and a `presented_schema` — shaped like this:

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

`inputSchema` is plain JSON Schema — `type`, `properties`, `required` —
and `annotations` uses the hint fields MCP tools actually define
(`readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint`,
`title`). One case also carries an `outputSchema`.

One case adds a `_meta` field between registration and presentation.
`_meta` is a field MCP itself permits, so this isn't testing whether the
resulting schema is valid — it's testing whether the detector notices
*anything* showing up that wasn't in the trusted baseline, valid MCP
field or not. That's what `unexpected_additional_fields` actually means
here: not present at registration time. It says nothing about whether the
new field would be fine on its own.

For each case, I register the original schema, present the (possibly
mutated) version, and check whether the detector's verdict matches what I
know I actually did to it. That's the whole methodology — nothing more
elaborate than that.

Three of the four controls are exact duplicates, so nothing should get
flagged. The fourth one I built to be annoying on purpose: same enum
values, different order. `["ops", "alerts"]` became `["alerts", "ops"]`.
Nothing about what the tool can do changed. I wanted to see if the
detector would notice anyway.

It did. Canonicalization sorts dictionary keys but not the contents of
lists, so a reordered list still produces a different hash, and the
detector calls it mutated. Worse, it gets classified as
`parameter_type_change`, which is wrong — the enum-expansion rule only
fires when the new list is a strict superset of the old one, and a
reorder doesn't qualify, so it falls through to the wrong bucket.

If someone asked me what this project actually shows, that's the answer,
not the 100% detection figure. 100% is close to guaranteed once you're
comparing cryptographic hashes — any content change flips the hash, so of
course every genuine mutation gets caught. The useful result is the
failure: a change that clearly shouldn't matter got flagged and
mislabeled, and I know exactly why.

## Results

| Metric | Value |
|---|---|
| Mutation detection | 13 of 13 |
| False positives | 1 out of 4 controls |
| Undetected mutations | 0 |
| Correctly classified mutations | 13 of 13 |

Every mutation category came back at 100% detection too, but with only
1–2 cases per category that's not saying much statistically — it means
the classifier's rules work on the specific cases I wrote to exercise
them, not that they'd hold up on a larger or less friendly corpus. Full
per-case output is in `results/results.json`; a longer write-up is in
`reports/evaluation_report.md`.

Each case result also records `detection_correct` (did the yes/no
mutated call match reality — meaningful for every case, controls
included) separately from `category_classification_correct` (did the
predicted category match — only meaningful for actual mutations, `null`
for controls, since there was never a category to get right there).
Collapsing those into one field made a correct "unmutated" call on a
control look identical to a missed classification, which was wrong, so
they're two fields now.

## Threat model

There are basically four reasons a schema shown at invocation might not
match what was trusted at registration: someone tampers with it on
purpose; someone ships a legitimate update and nobody refreshes the trust
baseline; the registry gets compromised and starts serving something
different than what was originally registered; or the schema is
semantically the same but ordered differently — a reordered `enum` list,
for instance, which is the real case demonstrated below.

This detector can't tell those apart. It only compares against whatever
was most recently registered as trusted. If a registry is compromised
*after* a legitimate schema was already registered, and it later starts
serving something different, that difference still shows up as a hash
mismatch — so it does get flagged as *a* change. What it can't tell you
is why: a legitimate update, tampering in transit, and a compromised
registry all look identical from a schema diff.

What it genuinely can't catch at all: if the registry is already
compromised at the moment a tool is first registered, that compromised
schema just becomes the new trusted baseline, and nothing about it looks
wrong afterward. Same story if an attacker can change both the registered
baseline and the presented schema together — keep them in sync and the
hashes still match.

The name says "integrity," not "attribution," on purpose. It checks
whether a schema still matches what was trusted. It doesn't know who
changed it or why.

## MCP scope

This evaluates schemas shaped like real MCP Tool objects — `name`,
`description`, `inputSchema` (JSON Schema), and `annotations` — written
by hand as plain dictionaries, not fetched from or validated against a
live server. It doesn't import the MCP SDK, doesn't open a connection to
anything, and never talks to a real MCP server, mine or anyone else's. If
you're looking for evidence about MCP protocol-level security, this isn't
it. It's evidence about one integrity-checking technique — hash the
canonical form, diff it, classify the diff — applied to data shaped like
what an MCP tool would actually send.

## Reproducing this

From this directory:

```bash
python -m unittest discover -s tests -v
python -c "import sys; sys.path.insert(0, 'src'); from detector.evaluate import main; raise SystemExit(main())"
```

The second command reruns the evaluation and overwrites
`results/results.json`. Both are deterministic — no network calls,
nothing random — so running them again should give you the same numbers
as in `reports/evaluation_report.md`.

(`python -m detector.evaluate` won't work directly, because `src/` isn't
on the path by default here. The one-liner above handles that without an
editable install. `pip install -e .` would also work if you'd rather have
`import detector` resolve normally.)

## Limitations

- The corpus is small — 17 cases, 3 mock tools. Enough to exercise every
  category at least once and catch the enum-reorder issue, not enough to
  say anything about a real-world false-positive rate. Every mutated case
  changes exactly one field; nothing tests removing a parameter from
  `required`, only adding one or changing an existing value, and there's
  no benign equivalence case beyond the enum reorder — numeric type
  coercion, Unicode normalization, and similar are all untested.
- The classifier is a fixed set of rules keyed on where in the schema
  something changed, not anything learned. It will flag a mutation it
  doesn't recognize (falling back to "unclassified"), but it can mislabel
  one, the way it did with the reorder case.
- Nothing here tests compound mutations — every case changes one thing at
  a time. Real tampering probably wouldn't be that considerate.
- I used the standard library and `unittest` instead of `pytest` and the
  MCP SDK named in the original project proposal. `pytest` isn't
  installed in this environment, and a synthetic evaluation doesn't need
  a live protocol implementation. `pyproject.toml` lists `pytest` as an
  optional dependency if you'd rather run these same tests under it.
- This isn't a production security tool. It measures one specific
  technique — hash comparison plus rule-based diffing — against a corpus
  I wrote myself. Don't read the numbers above as evidence about how this
  would hold up in a real deployment.

## License

MIT — see [LICENSE](LICENSE).
