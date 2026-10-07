# Report ontology

The vocabulary, validation rules and competency questions for report templates: what a report type is,
what its sections and fields mean, which column of which table supplies each field, when and under which
policies it runs, and how the flow that builds and runs it is described.

This package is separate from the tools that use it. The pdf-to-template plugin, the code-generating
GitHub Action and the deployed knowledge graph all read it and pin its version; none of them holds a copy.

Current versions: report ontology `rpt:` **2.1.0**, flow `flow:` and document template `dt:` **0.1.1**, rationale `meta:` **0.1.0**.
The structure of the flow vocabulary is frozen until the software factory contract is written; its terms are
all defined.

## What is here

| Folder | Contents |
|---|---|
| `ontology/report.ttl` | `rpt:` classes and properties. Every term exists because a competency question needs it, and carries a label, a definition, a domain and a range. |
| `ontology/ontology.ttl` | `flow:` (steps, checks, transitions, artifacts, tests) and `dt:` (pages, regions, slots, components, renders), every term defined the same way. |
| `ontology/report-shapes.ttl`, `shapes.ttl` | SHACL. Violation = a question cannot be answered. Warning = answered with a gap. |
| `ontology/meta.ttl` | `meta:`: why a term, shape or question exists, what was considered instead, and who confirmed it. |
| `ontology/ontology.lock.json`, `changelog.yaml` | The vocabularies, shapes and questions as last accepted, and the log of who accepted each change. Written by `kgctl.py ontology accept`. |
| `ontology/bindings.ttl`, `derive_tests.rq` | Which `dt:` concept each flow artifact carries, the invariants, and the rules that derive test obligations. |
| `questions/report_cq.yaml` | 21 report questions (analyst, compliance, data team, engineer, operations), each with an answer query and, where a silent empty answer would mislead, a gaps query. |
| `questions/competency_questions.yaml` | 17 flow questions an agent asks before it implements or tests a step. |
| `schemas/` | JSON Schemas for `report.yaml`, `provenance.yaml`, `lineage.yaml`, `history.yaml` and `manifest.json`. Every property names its ontology term (`x-term`) and who provides it (`x-provided-by`). |
| `tools/kg.py`, `mcp_server.py` | The query surface: what every consumer calls. |
| `tools/semantic.py`, `kgctl.py` | The maintainer's tools: validate, compile, conform, accept a definition, check and accept a vocabulary change, and the consistency and flow graph commands. |
| `tools/ledger.py`, `vocabulary.py` | The history of a report's definition; the change control and rationale of the vocabularies. |
| `fixtures/` | Two example reports used by the tests. `fund-profile-equity` is synthetic: it exists so questions across reports return more than one row. |

## Setup

```bash
python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt   # requirements.txt alone to run, not test
.venv/bin/pytest -q
```

## The query surface

Consumers do not read the files or run SPARQL. They call these operations, from the command line or over MCP.
Every result is JSON. Reports are validated and compiled in memory on each call, so an answer is never stale;
a report that fails validation is left out and named under `skipped`.

| Operation | Returns | Example |
|---|---|---|
| `questions` | The 38 competency questions (21 report, 17 flow), who asks each, the parameters each needs, why it exists | `kg.py questions --vocabulary report` |
| `ask` | The rows of one question, its gaps, and a status: `answered`, `gap` or `empty` | `kg.py ask CQ7 --report fund-profile-balanced` |
| `explain` | A class or edge: label, definition, domain, range, the questions that read it, the file it is written in, why it exists and who confirmed it | `kg.py explain sourcedFrom` |
| `requirements` | Everything a new report must provide: where, whether required, what it means, who provides it | `kg.py requirements --provided-by analyst` |
| `gaps` | What a draft report still lacks, blocking items and warnings, with the place each answer is written; its last accepted revision and what is pending | `kg.py gaps reports/my-report` |

The questions answer what was foreseen. For the rest, the catalogue is a graph to walk:

| Operation | Returns | Example |
|---|---|---|
| `resolve` | The entities a name designates (id, label in any locale, alias, column or table name), best first, and the ontology terms of that name | `kg.py resolve "management expense ratio"` |
| `entity` | One entity: its values, its edges both ways, and for a report or field its accepted history and pending changes | `kg.py entity mer --report fund-profile-equity` |
| `neighbors` | The entities around one, up to 3 edges away, optionally along one property | `kg.py neighbors bar_chart --direction in --depth 2` |
| `search` | Entities whose labels, meanings, purposes, rules or notes hold every word, ranked, with a snippet | `kg.py search "sums to 100" --type Section` |
| `overview` | The map: reports by status, nodes and edges by kind, mapping progress, shared fields and components, recent revisions, how much of the ontology says why | `kg.py overview` |
| `stale` | What is out of date: unaccepted changes, reports with no history, mappings proposed and not verified, idle statuses, reports that no longer validate | `kg.py stale --days 30` |
| `history` | A report's accepted revisions, or its definition as it stood on a date | `kg.py history fund-profile-balanced --as-of 2026-10-03 --fact fields.mer.` |

```bash
export REPORTS_ROOT=/path/to/reports          # a folder of report folders; or pass --catalogue
python tools/kg.py ask CQ14                   # which report types exist
python tools/kg.py ask flow:CQ04 --step B10_verify --flow-root /path/to/pdf-to-template
python tools/kg.py explain                    # the index of every class
```

`requirements` and `gaps` are derived from the schemas and the shapes, so a tool that elicits a new report from
an analyst never hardcodes what to ask. Each item says who provides it:

| `provided_by` | Meaning |
|---|---|
| `analyst` | Ask the analyst. |
| `agent` | The agent drafts it from the sample PDF or the table, and the analyst confirms. |
| `flow` | Recorded by a step of the flow; never asked. |

### MCP server

```json
{"mcpServers": {"report-ontology": {
  "command": "python", "args": ["/path/to/report-ontology/tools/mcp_server.py"],
  "env": {"REPORTS_ROOT": "/path/to/reports", "FLOW_ROOT": "/path/to/pdf-to-template"}}}}
```

Tools: `list_questions`, `ask`, `explain`, `requirements`, `gaps`, `resolve`, `entity`, `neighbors`, `search`, `overview`,
`stale`, `history`. All are read-only. A request the server
cannot serve returns `{"error": "…"}` with what to change.

### SQLite export

```bash
python tools/kg.py export-sqlite --out build/catalogue.db [--with-flow]
```

A read-only copy for consumers that want SQL, rebuilt from the files each time; nobody edits it. The export is
refused when any report fails validation or breaks a shape.

| Table | Holds |
|---|---|
| `nodes` | One row per instance: `id`, `type`, `label`, `report`, and its literal values as JSON in `properties` |
| `edges` | `source`, `property`, `target`; `property` joins `terms.term`, which explains the edge |
| `terms` | Every class and property of the three vocabularies with label, definition, domain, range, rationale and who confirmed it |
| `questions` | The competency questions with their SPARQL |
| `meta` | Ontology versions, export time, the reports included |

## Maintainer commands: reports

A report folder holds `manifest.json` and `semantic/{report,provenance,lineage,history}.yaml`. A catalogue is a folder
of report folders. Every command takes either.

```bash
python tools/semantic.py validate <report>/semantic      # schemas + completeness; exit 1 on a blocking gap
python tools/semantic.py compile  <report>/semantic      # → semantic/report.graph.json (JSON-LD)
python tools/semantic.py conform  <report>/semantic      # SHACL: can the graph answer the questions?
python tools/semantic.py ask      <report>/semantic CQ10 # one question about that report
python tools/semantic.py ask      <catalogue> CQ14       # one question across every report
python tools/semantic.py diff     <report>/semantic      # what differs from the last accepted revision; exit 1 if anything
python tools/semantic.py accept   <report>/semantic --by ana [--why "…"] [--effective 2026-11-01]
python tools/kgctl.py terms                              # schemas ↔ ontology ↔ questions agree; every term defined
```

`compile` refuses an undeclared predicate and a manifest written for another ontology major.minor.
Compiled graphs carry a timestamp and are build output: they are ignored by git.

### The questions

| Id | Asked by | Question | Option |
|---|---|---|---|
| CQ1 | analyst | What does a field mean, and what is its label in each locale? | `--field` |
| CQ2 | analyst | Which sections and fields make up a report, in order? | `--report` |
| CQ3 | compliance | Which source document, run and approvals produced the template? | `--report` |
| CQ4 | compliance | Which fields carry rules, and which rules are regulatory? | `--report` |
| CQ5 | data team | Which column of which table supplies each field, is it a value or JSON, and which fields are unmapped? | `--report` |
| CQ6 | data team | If a column changes, which reports and fields are affected? | `--column` |
| CQ7 | data team | Which data source and table does a report read, and which column carries each parameter? | `--report` |
| CQ8 | engineer | Which component renders a field, in which template release? | `--field` |
| CQ9 | engineer | Which reports share a field? | `--field` |
| CQ10 | operations | When does a report run, and at which template version? | `--report` |
| CQ11 | compliance | What verification thresholds and approval policy govern production runs? | `--report` |
| CQ12 | operations | What identifies one document, where do parameter values come from, where is it published? | `--report` |
| CQ13 | engineer | What does a release need to render? | `--report` |
| CQ14 | analyst | Which report types exist, what is each for, its lifecycle status, who owns it, which version is released? | none |
| CQ15 | analyst | Which other reports show the same fields as a report? | `--report` |
| CQ16 | engineer | Which report types use a component, and in which sections? | `--component` |
| CQ17 | operations | What is expected of each run, who is alerted, where is the run history? | `--report` |
| CQ18 | analyst | Which fields does the catalogue already define, under which other names, and how many reports use each? | none |
| CQ19 | operations | Where is a report in its lifecycle, and who recorded each step, when? | `--report` |
| CQ20 | compliance | How has a report's definition changed: each revision, who accepted it, when, from when, why, and which facts? | `--report` |
| CQ21 | analyst | Has anything about a field changed in any report: what was it before, when, who accepted it, and why? | `--field` |

`--report` defaults to the report itself when the command points at one report folder.

### The lifecycle of a report

`provenance.yaml` keeps a report's status history. One entry is appended each time the report reaches a status;
earlier entries are never rewritten, and the last entry is the current status.

```yaml
lifecycle:
  - {status: inception,     by: ana, at: 2026-10-01}   # the definition has been started
  - {status: saved,         by: ana, at: 2026-10-02}   # it validates and is part of the catalogue graph
  - {status: in_validation, by: raj, at: 2026-10-06}   # definition and template are being checked
  - {status: in_production, by: lee, at: 2026-10-20}   # deployed: who, and when
```

| Rule | Why |
|---|---|
| Every entry names who (`by`) and when (`at`) | So "who deployed it, and when" always has an answer. |
| The first status is `inception` | A report starts there. |
| A status moves forward one step at a time; it may move back | A report sent back from validation returns to `saved`. |
| Dates never go backwards | The history is a log. |
| `in_production` needs a frozen release | Only a frozen release produces documents. |

`CQ19` returns the history of one report, `CQ14` the current status of every report. A report that does not
validate yet is not in the graph; it appears under `skipped` with the status its own file records.

### The history of a definition

The files say what a definition is now. `semantic/history.yaml` says what it was. A changed meaning, column, type or
owner is superseded, never overwritten: the old value stays answerable, with who replaced it, when, and why.

```bash
python tools/semantic.py diff   reports/my-report/semantic                    # ~ semantic/report.yaml → fields.mer.meaning: "…" → "…"
python tools/semantic.py accept reports/my-report/semantic --by ana --why "MER is shown net of waivers since the 2026 prospectus"
python tools/kg.py history my-report --as-of 2026-10-03 --fact fields.mer.   # the definition as it stood that day
```

A fact is one value of `report.yaml`, `lineage.yaml` or `manifest.json`, named by its file and path the way `gaps`
names the place of an answer (`semantic/lineage.yaml → fields.mer.column`); the order of sections is a fact too.
Revision 1 holds every fact as first accepted, each later revision the facts it added, changed or removed with the
value before and after. `history.yaml` is written by `accept` and never by hand: a change that does not start from the
value the history holds is an error.

| Rule | Why |
|---|---|
| `accept` names a person (`--by`) | The history says who decided, not who typed. |
| A changed or removed fact needs `--why` | An overwrite without a reason cannot be told from a mistake. Additions need none. |
| `accept` refuses a definition that does not validate, compile and conform | Only a valid definition becomes part of the history. |
| `--effective` may differ from the day of recording | A correction can apply retroactively, a change from a future run. `--as-of` reads the effective date, `--known-on` the date of recording. |
| While drafting, changes may stay pending | `diff`, `gaps`, `entity` and `stale` say so; `CQ20` and `CQ21` answer from accepted revisions only. |
| In production, a pending change or removal blocks | What was true when documents were produced must stay answerable: accept it, with a reason. |
| A report with no history is a warning (`shp:ReportHistory`) | Reports written before 2.1.0 keep compiling until someone accepts their definition. |

### The data mapping

`lineage.yaml` records what the analyst provides and verifies: the data source, the one table that holds
every column of the report, the column that carries each parameter, and the column behind each field.

```yaml
source: {name: warehouse, kind: bigquery, database: my-project}
table:  {dataset: reports, name: fund_profile_balanced}
parameters: {fund_id: fund_id, as_of: as_of}
fields:
  mer:       {status: verified, column: mer}     # confirmed by the analyst
  returns:   {status: proposed, column: returns} # suggested, not yet confirmed
  fund_name: {status: unmapped}                  # blocks a production release
```

By convention a field id is the snake_case form of its English label and its column has the same name.
One field reads one column. A single-valued field reads the column's value; a structured field (`list`,
`grouped_list`, `series`, `list_of_text`, `currency_pair`, `percent_by_series`) reads JSON text from its column:
for a list, an array of rows in the shape the field's `row` declares. `CQ5` returns `stored: value` or
`stored: json` for each field.
How the table is populated belongs to the data team's medallion module, not to this graph.

## Maintainer commands: flow

The flow instance (`flow/flow.json` and its step scripts) belongs to whoever runs the flow, not to this
package. Point at it with `--flow-root` or `FLOW_ROOT`.

```bash
export FLOW_ROOT=/path/to/pdf-to-template
python tools/kgctl.py build        # flow.json + ontology + bindings → build/graph.ttl
python tools/kgctl.py validate     # SHACL report on the flow graph
python tools/kgctl.py readiness    # which steps are specified well enough to implement or test
python tools/kgctl.py brief --task implement-step --step B10_verify
```

A brief is READY or BLOCKED. A required question with gaps blocks: absent is not "none". Sample briefs
are in `docs/examples/`.

## Changing the ontology

A new property starts as a question. This is the only path:

1. `questions/report_cq.yaml` — write or extend the question that needs it, and say `why:` it is asked.
2. `ontology/report.ttl` — add the term with its label, definition, domain and range; cite the question; record
   `meta:rationale` (and `meta:alternatives` when something else was considered); bump `owl:versionInfo`.
3. `schemas/*.schema.json` — add the property with `"x-term"`, and `"x-provided-by"` when it differs from its parent; bump `x-ontology-version` to match.
4. `ontology/report-shapes.ttl` — add a shape if the question must be answerable.
5. `python tools/kgctl.py terms` — fails on a property without a term, a term without a question, a term without
   a label, definition, domain or range, a version mismatch, or a confirmation that does not say who and when.
6. `python tools/kgctl.py ontology check` — sorts every change since the lock and refuses a version that does not say so:

   | Severity | Examples | Version |
   |---|---|---|
   | breaking | a term, question or answer column removed; a domain or range narrowed; a Violation constraint added, removed or changed; a question's parameters changed | next major (0.x: next minor) |
   | additive | a term, question or answer column added; a domain or range widened; a Warning constraint; a Violation shape on classes added in the same change; a query rewritten with the same columns | next minor (0.x: next patch) |
   | cosmetic | labels, definitions, messages, rationale, confirmations | none |

   Each breaking change is counted against the catalogue (`--catalogue`, default `REPORTS_ROOT`, else `fixtures/`):
   how many instances, triples or shape violations it touches. A term, shape or question that a person confirmed
   before its meaning changed is listed under `RECONFIRM`.
7. `python tools/kgctl.py ontology accept --by <you>` — writes `ontology/ontology.lock.json` and appends what was
   accepted to `ontology/changelog.yaml`. The test suite fails while the lock is behind the files.
8. `pytest` — the examples still compile, conform, answer every question, and match their accepted history.

A minor version of `rpt:` changes the major.minor that manifests must declare: after a release of the ontology,
each report's `manifest.json` moves its `ontology_version`, and `semantic.py accept` records the change.

### Why each term exists

`meta:rationale`, `meta:alternatives`, `meta:validatedBy` and `meta:validatedOn` are written next to each term and node
shape (`why`, `validated_by`, `validated_on` on each question). `validated_by` stays absent until a person who knows the
domain has confirmed the text; an agent never fills it in.

```bash
python tools/kgctl.py rationale            # per vocabulary: how many classes, properties, shapes and questions say why, and how many were confirmed
python tools/kgctl.py rationale --missing  # what has no recorded why
python tools/kgctl.py rationale --strict   # exit 1 while a class, shape or question has no why
```

## As an OTO ontology unit

`oto/report/` is the report ontology ported to [OTO](https://github.com/Cynergis/oto), the
Cynergis knowledge-graph engine, by `tools/oto_port.py`: the terms of `ontology/report.ttl` under
their own IRIs, the 21 competency questions rewritten in OTO's pattern language (`questions.json`,
the form the engine runs and renders back to SPARQL), the shapes OTO holds as counts and the rest
as policy rules, and the fund-profile-balanced fixture as the sample. It is installable as a
project's vocabulary and answers the same questions the SPARQL does:

```bash
oto init --name "Report catalogue" --slug catalogue --ontology ./oto/report
oto build --project catalogue
oto query --project catalogue questions                          # every question, and whether the graph answers it
oto query --project catalogue ask CQ1 FIELD=mer                  # one question, run: the rows, or the gap
```

`tests/test_oto_port.py` is the acceptance: for every question and every binding in the fixture,
the original SPARQL and the port give the same answers, OTO's own SPARQL rendering agrees with its
engine on this graph, and the committed unit is what the port writes. The port is regenerated
with `python tools/oto_port.py --oto <OTO checkout> --check` after a change to the Turtle, the
shapes or the questions; the questions in pattern form are edited in `tools/oto_port.py`.

### The flow ontology, ported

`oto/flow/` is the flow ontology (`flow:` terms of `ontology/ontology.ttl`, the 17 competency
questions of `questions/competency_questions.yaml`, the five task types) ported the same way by
`tools/flow_port.py`, with the task types as OTO **briefs**: `briefs.json`, what an agent must
know before implementing a step, writing its tests, building the engine, or changing a
parameter or an artifact. `fixtures/pdf-to-template/graph.json` is the pdf-to-template flow
instance as a project graph (what `kgctl build` made of `flow.json`, `bindings.ttl` and
`derive_tests.rq`); a real flow with its real gaps is a project's facts, not an ontology's
sample. Three names the report ontology uses for other things are renamed in the port
(`ArtifactField`, `ConfigParameter`, `outputOf`), so one project composes both:

```bash
oto init --name "pdf-to-template" --slug ptt --ontology ./oto/flow,./oto/report --empty --project ptt
cp fixtures/pdf-to-template/graph.json ptt/graph.json && oto build --project ptt
oto query --project ptt brief implement-step                     # kgctl readiness: 8 READY, 10 BLOCKED FL3
oto query --project ptt brief implement-step STEP=step.b10_verify   # kgctl brief: READY, every question's facts
```

`tests/test_flow_port.py` is the acceptance: the briefs give `kgctl`'s verdicts for every
implementable step and task, every brief question answers with as many facts as the original
SPARQL (where the two count alike), and the committed unit and graph are what the port writes.
The port is regenerated with `python tools/flow_port.py --flow-root <pdf-to-template> --check`.
The `dt:` concepts are not ported as classes: they are what a run's data is made of, and no graph
holds a run yet.

## Paths

| Variable | Meaning | Default |
|---|---|---|
| `REPORTS_ROOT` | The catalogue: a folder of report folders | `./reports` when that folder exists; otherwise `kg.py` and the MCP server stop without it or `--catalogue` |
| `FLOW_ROOT` | Folder holding `flow/flow.json` | none; flow commands stop without it |
| `ONTOLOGY_BUILD_DIR` | Where generated graphs are written | `build/` |
