# SmartIndex

[![tests](https://github.com/ScooterStuff/SmartIndex/actions/workflows/tests.yml/badge.svg)](https://github.com/ScooterStuff/SmartIndex/actions/workflows/tests.yml)
[![python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![license](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

SmartIndex is a MongoDB composite index recommendation tool. Given a CSV
that describes an application's query patterns, it produces a **minimal
set** of composite indexes that respect MongoDB's prefix rule, follow the
ESR ordering convention, and place the most selective fields first.

---

## Table of contents

1. [The problem](#the-problem)
2. [How SmartIndex solves it](#how-smartindex-solves-it)
3. [Theory](#theory)
   - [The composite-index prefix rule](#the-composite-index-prefix-rule)
   - [The ESR rule](#the-esr-rule)
   - [Shannon entropy and selectivity](#shannon-entropy-and-selectivity)
   - [Graph-based field ordering](#graph-based-field-ordering)
   - [MinSet / trie optimisation](#minset--trie-optimisation)
4. [Pipeline](#pipeline)
5. [Project layout](#project-layout)
6. [Quick start](#quick-start)
7. [CSV format](#csv-format)
8. [Output](#output)
9. [Tests](#tests)

---

## The problem

Designing MongoDB composite indexes by hand is hard:

- **Field order matters.** A composite index `{a:1, b:1, c:1}` only
  efficiently supports filters/sorts on its **leftmost prefixes**:
  `{a}`, `{a,b}`, `{a,b,c}`. It does _not_ efficiently serve `{b}`,
  `{c}`, `{b,c}`, or `{b,a}`.
- **Different operators want different positions.** Equality predicates,
  sort keys, and range predicates each behave differently inside an
  index and should appear in a specific order.
- **Indexes are expensive.** Each index costs memory, disk, and write
  throughput. A naive "one index per query" strategy explodes in both
  number and total size.
- **Queries overlap.** Many application queries share leading fields and
  can be served by a single, longer composite index — but only if the
  field order lines up exactly.

A correct recommendation must therefore choose **which fields**, in
**which order**, **per index**, and then **eliminate redundancy** across
indexes.

## How SmartIndex solves it

SmartIndex is a four-stage pipeline:

1. **Parse** the CSV of query patterns into structured `Query` objects.
2. **Score** each field's selectivity with **Shannon entropy**, either
   sampled live from MongoDB or estimated heuristically when no
   collection is available.
3. **Order** the fields of each query using a small **weighted directed
   graph** that combines ESR priority with selectivity differences.
4. **Minimise** the resulting candidate set with a **trie-based MinSet
   optimiser** that absorbs any index that is an exact leftmost prefix
   of a longer one.

The result is a small set of composite indexes, each annotated with the
queries it covers, the partial-index condition it should use (if any),
and a short justification.

---

## Theory

### The composite-index prefix rule

A composite index in MongoDB is an ordered list of fields. The index
can efficiently serve any query whose filter/sort uses a **leftmost
prefix** of that list, in the same order:

```text
Index:           [A, B, C]
Efficient for:   [A], [A, B], [A, B, C]
NOT efficient:   [B], [C], [B, C], [B, A]
```

This is the single most important rule in SmartIndex. Both the ordering
algorithm (which decides what the prefix should be) and the
minimisation algorithm (which removes indexes already implied by a
longer prefix) are built around it.

### The ESR rule

For a single composite index, MongoDB's recommended field order is:

```text
Equality  →  Sort  →  Range
```

- **Equality (E)** fields filter to a single value and shrink the
  remaining keys the most, so they should appear first.
- **Sort (S)** fields can be served in order from the index only if they
  come after equality and before range fields.
- **Range (R)** fields (`$gt`, `$lt`, `$gte`, …) scan a contiguous
  segment of the index. If they appear before sort or equality fields,
  they break the prefix and prevent the rest of the index from being
  used efficiently.

SmartIndex encodes this as a numeric priority used in graph edge
weights:

```python
ESR_PRIORITY = {"E": 3, "S": 2, "R": 1}
```

### Shannon entropy and selectivity

When several fields share the same ESR class (e.g. all equality),
SmartIndex breaks the tie using **selectivity** — a measure of how
effectively a filter on that field reduces the number of matching
documents.

A common shortcut is "count distinct values", but that can be
misleading: a field with 1,000 distinct values where 99% of documents
have the same value is in practice not very selective. **Shannon
entropy** captures both the number of values and how evenly they are
distributed:

$$
H(X) = -\sum_{i} p_i \log_2 p_i
$$

where $p_i$ is the probability of value $i$. Higher entropy means values
are spread more evenly, which usually makes the field a better filter.

Sample distributions:

| Distribution               | Entropy (bits) |
| -------------------------- | -------------- |
| `[0.5, 0.5]`               | 1.000          |
| `[0.25, 0.25, 0.25, 0.25]` | 2.000          |
| `[0.7, 0.1, 0.1, 0.1]`     | 1.356          |
| `[0.99, 0.01]`             | 0.081          |

**Equality fields** are scored directly from their entropy. **Range
fields** are continuous; SmartIndex either samples bucket counts from
MongoDB or falls back to the default distribution `[0.5, 0.5]`, then
multiplies the result by a **range penalty** (`0.4`) so range fields
keep a meaningful score but do not displace equality fields. **Sort
fields** receive a smaller `0.8` penalty.

Implementation: [smartindex/selectivity_calculator.py](smartindex/selectivity_calculator.py).

### Graph-based field ordering

For each query, SmartIndex builds a small **directed weighted graph**:

- **Nodes** = the fields used in that query.
- **Edges** = an edge `u → v` with weight $w(u, v)$ expresses how
  strongly `u` should come before `v`.

Edge weight combines three terms:

$$
w(u, v) = w_{ESR}(u, v) + w_{sel}(u, v) + w_{range}(u, v)
$$

- $w_{ESR}(u, v) = 10 \cdot (\text{prio}(u) - \text{prio}(v))$ —
  large positive if `u` belongs to a higher ESR class than `v`.
- $w_{sel}(u, v) = \text{sel}(u) - \text{sel}(v)$ —
  positive when `u` is more selective.
- $w_{range}(u, v)$ — explicit penalty that pushes range fields toward
  the end of the index.

Each node is then ranked by its **net pull**:

$$
\text{score}(v) = \sum_{u \neq v} w(v, u) - \sum_{u \neq v} w(u, v)
$$

Fields are sorted by `score` descending. The resulting list is the
candidate composite index for that query.

Why a graph instead of plain sorting? It lets us compose multiple
ordering signals (ESR, selectivity, the range penalty, and future
signals such as query frequency or partial-index bonuses) into a single
comparable quantity without writing brittle nested `if` chains.

Implementation: [smartindex/graph_ordering.py](smartindex/graph_ordering.py).

### MinSet / trie optimisation

After ordering, SmartIndex has one candidate index per unique query
shape. Many of these indexes overlap — a longer index can serve every
query whose required prefix it begins with.

A **trie** is the perfect structure for this. Each candidate is inserted
as a path from the root; shared prefixes share trie nodes:

```text
Candidates: [A, B, C], [A, B], [A], [D, E]

Trie:
    root
    ├── A          (candidate [A])
    │   └── B      (candidate [A, B])
    │       └── C  (candidate [A, B, C])
    └── D
        └── E      (candidate [D, E])
```

The optimiser walks the trie and **drops every candidate that has a
strict descendant**, since that descendant is a longer index with the
shorter one as an exact prefix. The query coverage of the absorbed
shorter indexes is propagated upward to the surviving longer index, so
nothing is forgotten.

Critically, this only collapses **true leftmost prefixes**:

- `[A, B, C]` absorbs `[A, B]` and `[A]`. ✅
- `[A, C, B]` does **not** absorb `[A, B]` — different order, different
  trie path. ✅
- `[B, C]` does **not** absorb `[A, B, C]` — not a prefix of it. ✅

Implementation: [smartindex/minset.py](smartindex/minset.py).

---

## Pipeline

```text
CSV file
   │
   ▼
CSVReader            ─── parse rows, expand [or] alternations
   │
   ▼
Encoder              ─── short symbols (a, b, c, …) for graph stages
   │
   ▼
SelectivityCalculator  ── Shannon entropy per field (live or heuristic)
   │
   ▼
GraphOrderer         ─── per-query weighted graph → ordered field list
   │
   ▼
IndexGenerator       ─── dedupe identical orderings, merge query coverage
   │
   ▼
MinSetOptimiser      ─── trie-based prefix absorption
   │
   ▼
(optional) MongoTester ── create indexes, run .explain(), collect metrics
   │
   ▼
ReportGenerator      ─── decode field names + print createIndex() lines
```

## Project layout

```text
smartindex/
  __init__.py
  main.py                    # CLI entry point
  models.py                  # Query / QueryField / IndexCandidate
  csv_reader.py              # CSV parsing
  encoder.py                 # field name ↔ short symbol
  selectivity_calculator.py  # Shannon entropy (live + heuristic)
  graph_ordering.py          # per-query field ordering
  index_generator.py         # candidate index generation
  minset.py                  # trie-based prefix optimiser
  mongo_tester.py            # optional .explain() runner
  kendall_tau_explorer.py    # optional add-on validator
  greedy_remover.py          # optional add-on optimiser
  report.py                  # human-readable output
tests/
  test_csv_reader.py
  test_encoder.py
  test_graph_ordering.py
  test_index_generator.py
  test_minset.py
  test_kendall_tau_explorer.py
  test_greedy_remover.py
synthetic_data/              # MongoDB synthetic data generators
safe/                        # legacy backup scripts (not used)
test_query.csv               # sample CSV (uses synthetic data fields)
query.csv                    # second sample CSV
```

## Quick start

```powershell
# 1. (Optional) populate MongoDB with synthetic data
python synthetic_data\mongodbscript3.py

# 2. Run SmartIndex on a query CSV (offline, heuristic selectivity)
python -m smartindex.main test_query.csv

# 3. Run SmartIndex against MongoDB and benchmark each recommendation
python -m smartindex.main test_query.csv `
    --mongo-uri mongodb://localhost:27017 `
    --db testdb --collection orders --test
```

When `--mongo-uri`, `--db`, and `--collection` are supplied,
`SelectivityCalculator` samples real distributions from MongoDB. When
`--test` is also passed, `MongoTester` creates each recommended index,
runs an `.explain()` for a representative query, collects the metrics,
and drops the index again.

### Optional add-on validators

Two opt-in validators run _after_ the main pipeline and require a live
MongoDB connection. They are off by default; enable each with a `-`
flag:

| Flag                      | Tool                 | Question it answers                               |
| ------------------------- | -------------------- | ------------------------------------------------- |
| `-kt` / `--kendall-tau`   | Kendall-Tau Explorer | Is there a better order _near_ the predicted one? |
| `-gr` / `--greedy-remove` | Greedy Remover       | Can we drop trailing fields without losing perf?  |

**Kendall-Tau Explorer** ([smartindex/kendall_tau_explorer.py](smartindex/kendall_tau_explorer.py))
generates permutations within Kendall-Tau distance ≤ `--kt-distance`
(default 2) of the graph-derived order, scores each via `.explain()`,
and keeps the best one. Tunables: `--kt-distance`, `--kt-max-perms`.

**Greedy Remover** ([smartindex/greedy_remover.py](smartindex/greedy_remover.py))
repeatedly drops the trailing field of one index, re-scores the whole
workload, and accepts the removal only if total degradation stays
within `--gr-degradation` (default `0.10` = 10%). Stops when no further
removal is acceptable. Tunables: `--gr-degradation`, `--gr-min-length`.

```powershell
python -m smartindex.main test_query.csv `
    --mongo-uri mongodb://localhost:27017 --db testdb --collection orders `
    --test -kt --kt-distance 2 -gr --gr-degradation 0.1
```

## CSV format

```text
Search/Combination,ESR,Range Criteria,Partial,Sorting Logic,Limit
"balance, name, string","R, E, E",None,None,"","200"
"string, date","E,R","date=30",None,"","200"
"name, age","E, R",None,None,"","200"
"city, age [or] fav","E, [R,R]","age=20,fav=10","age/lt/120","","200"
```

Column meanings:

| Column               | Description                                            |
| -------------------- | ------------------------------------------------------ |
| `Search/Combination` | Comma-separated field names used by the query          |
| `ESR`                | Per-field tag: `E` equality, `S` sort, `R` range       |
| `Range Criteria`     | Optional `field=value` or `field op value` constraints |
| `Partial`            | Optional partial-index filter (e.g. `balance/gt/50`)   |
| `Sorting Logic`      | Optional sort description                              |
| `Limit`              | Optional query `.limit()` value                        |

`[or]` expands a single row into one query per alternative:

```text
city, age [or] fav   →   (city, age) and (city, fav)
E, [R,R]             →   (E, R) and (E, R)
```

## Output

Example run on `test_query.csv`:

```text
[1] db.collection.createIndex({ "name": 1, "string": 1, "balance": 1, "age": 1 },
                              { name: "si_b_c_a_e" })
    encoded fields : ['b', 'c', 'a', 'e']
    queries covered: [1, 3]
    partial        : balance/gt/50,name/ne/Chris Doe
    reason         : ESR + selectivity ordering of …  (absorbs prefix)
```

Each line maps directly to a `db.<collection>.createIndex(...)`
command. The report also lists which input queries each index covers,
the partial filter (if any), and a short reason that records the
ordering decision.

## Tests

```powershell
python -m pytest -q
```

The test suite covers CSV parsing (including `[or]` expansion), the
encoder roundtrip, ESR + selectivity ordering, candidate generation
and deduplication, prefix absorption, non-prefix preservation, and an
end-to-end run from CSV to final indexes.
