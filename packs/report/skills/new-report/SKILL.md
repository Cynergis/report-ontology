---
name: new-report
description: >-
  Define a new report type with a report analyst, in the report knowledge base: capture what the
  report is, what identifies a document, where its data comes from, when it runs, where documents
  go and what a run must achieve; draft its sections and fields from the sample PDF; map each field
  to a column; and repeat until the report ontology's own gates find nothing blocking. Use when the
  user wants to "define a new report", "onboard a report", "start a new report type", "capture the
  requirements of a report", or hands over a sample PDF to turn into a report type.
---

# Define a new report type with the analyst

You are working with a report analyst. They know the report, its readers and the table its data
comes from; they are not expected to know the ontology. At the end of this skill the report type
exists **as facts in the project's knowledge base**, through the curate gates, with its lifecycle
at `inception` or `saved`, and the catalogue answers the report ontology's questions about it.
The template is then built from the sample PDF with the `pdf-to-template` skill, and the flow runs
it.

## Talking with the person

- **Plain, natural language, in the person's words.** Never say question numbers, ids, class or
  field names, file names or commands, and never paste what a command printed.
- **Technical details only when the person asks for them.** Never offer them, not even as a choice.
- **The same clear shape every time:** say what we are about to do, ask a few questions at a time,
  read back what you understood in plain sentences, confirm, then say what is next.

## The ontology decides what to ask

Run the interview with OTO's **capture-form** skill: it reads the project's `capture.json`, asks
the report ontology's questions group by group, and sends every confirmed group through the curate
gates. What a question asks for and who can answer it are in `capture.json`, not in this file. This
skill adds what a report needs on top: the catalogue checked first, the sample PDF, what you draft
yourself, the column mapping and the report's status.

## Before the first question

1. `kg_ask Q1` (which report types exist) and `kg_ask Q20` (which fields the catalogue already
   defines, with their ids and meanings). You need both: to avoid a duplicate report, to borrow
   defaults from a similar one, and to reuse field ids.
2. Ask for the sample PDF and the analyst's name. Agree a report id (lower case, hyphens): it is the
   `scope` of every capture of this report, so its items never collide with another report's.
3. Inspect the PDF yourself (the `pdf-to-template` plugin's `inspect_pdf.py`, when installed, writes
   page images and text spans; otherwise read it). If a page is raster, say now that fidelity will be
   capped and ask whether a production PDF exists.
4. Record the report as started: the first capture holds the `ReportType` (its `reportId`,
   `purpose`, `lifecycleStatus: inception`, audience, cadence, locales) and its first `StatusChange`
   (`inception`, by the analyst, today). From this moment the report is visible as started.

## The interview

Offer a similar report's value as the default ("the monthly statement goes out on the third
business day; the same here?"). The report ontology asks, in this order:

1. **What the report is** (the analyst, Q1, Q17): title, kind, purpose, audience, owner, locales,
   layout.
2. **What identifies a document** (operations, Q2): the parameters (the customer or account, the period, the language)
   and where each one's allowed values come from at run time (`UniverseQuery`).
3. **Where the data comes from** (the data team, Q5, Q4): the data source and the one table that
   holds every column of this report; which column carries each parameter.
4. **How it runs and where documents go** (operations, Q11, Q10, Q12): the schedule (cadence, day,
   as-of rule, calendar, timezone), the publish policy (formats, path, retention), the
   observability policy (delivery deadline, tolerated failure rate, who is alerted, the run log).
5. **Rules, verification and approval** (compliance, Q18, Q19): the rules on fields, which are
   regulatory; the verification thresholds and the approval policy.

## What you draft yourself

From the sample PDF, draft the `Section`s and `Field`s (Q7, Q3):

- One section per visual box, with its purpose and its order; the macro that renders it when the
  template exists.
- One field per piece of information shown. The field id is the snake_case form of the English
  label (`total_amount_due`). **Before naming a field, look it up in Q20's list**: if another report
  already shows the same information, use its id, type and meaning, so the two reports are
  recognised as sharing it. Invent a new id only for information the catalogue does not have.
- A `FieldMeaning` per language the report is offered in: the label the report prints and what the
  value is, precisely enough that someone could check a number against it.
- A list or table is a field with a list type and the structure of one row.

Show the analyst the sections and fields as a table and correct what they change. Their approval
of this table is the point of the session: take the time to get it right.

## The data mapping

Every field is supplied by one column of the report's table (`sourcedFrom`, Q4). Propose a column
per field (`lineageStatus: proposed`); if the analyst pastes the table's columns, match the real
names. Set `verified` only for what they confirm; leave `unmapped` what nobody can place yet. Tell
the analyst that a structured field (a list, a series) reads JSON text from its column, an array of
rows in the field's row shape, and show the expected JSON for one such field.

## Every confirmed group goes through the gates

capture-form contributes each confirmed group. For a report, its capture file has `doc`
`<report id>-interview`, `as_of` today and `scope` the report id, and is written to
`captures/<report id>-<group>.json`; a field item looks like `{"type": "Field", "id": "mer",
"label": "MER", "fields": {...}, "links": {"inReport": ["RT"], "sourcedFrom": ["COL-MER"]},
"where": "p.1", "quote": "..."}`.

What the report ontology's check tends to say:

- **blocking**: a mapping that claims a column the table does not hold, a column outside the
  report's table, a report type past inception with no section.
- **gap**: `question Q4 unanswered: … 12 fields have no column`, a field with no French meaning,
  a report that names no owner.

Apply after each group, `--by` the analyst, and tell the analyst in plain words what is now settled
about this report and what is still open.

## The report's status

`lifecycleStatus` lives on the report type and in its `StatusChange` history, appended, never
rewritten; the last one is the current status (Q17). Record a status when it is reached, only the
next one:

| Status | Recorded when |
|---|---|
| `inception` | by you, in the first capture, `changedBy` the analyst |
| `saved` | by you, when `oto curate check` finds nothing blocking after the sections, fields and mapping are approved and the schedule and policies are captured |
| `in_validation`, `in_production` | not in this skill: by whoever sends the template to validation, by whoever deploys |

If the session ends before `saved`, the report stays at `inception`, which is the truth.

## Finishing

Tell the analyst, in this order: that the report is defined, its status and its id; what is still
owed before production, from the last check's gaps and `kg_ask Q4` (fields with no column), `Q3`
(meanings missing in a language), `Q22`/`RP10` when the product pack is composed (what blocks
production readiness), with who can supply each; and that the next step is the template from the
sample PDF (`pdf-to-template`) and the flow that builds and runs it (`flow` pack, `kg_brief`).
If `Q20` now shows another report sharing many fields with this one, say so.

Do not edit the facts of other reports, the vocabulary, or anything outside this report's scope.

## Where people see it

The report shows on the product's studio page **The reports**: its sections and fields, what each
value means in each language and where it comes from, its rules, when it runs and where it goes, and
its history, with what is still open. Say so when a group is saved, in plain words.
