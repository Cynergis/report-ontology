---
name: start
description: >-
  Start or extend an OTO knowledge project in this domain: A report type: its meaning per locale, its sections and fields, the rules that apply, the column that supplies each value, the runs and approvals that produced its template, its operating contract, its lifecycle and the accepted history of its definition. The pack 'report' (release 2) embeds the ontology 'report' (release 5), which declares ReportType, StatusChange, Parameter, UniverseQuery, Section, Field, FieldMeaning, Rule and more. Use when someone wants a knowledge graph, a vocabulary or an interview for this domain.
---

# Report domain

A report type: its meaning per locale, its sections and fields, the rules that apply, the column that supplies each value, the runs and approvals that produced its template, its operating contract, its lifecycle and the accepted history of its definition.

This skill comes with the `report` pack. The ontology is inside the pack, so nothing is fetched.

1. **Start a project from this pack.**

   ```bash
   oto init --name "<project name>" --pack "${CLAUDE_PLUGIN_ROOT}" --project <root>
   ```

   `${CLAUDE_PLUGIN_ROOT}` is this pack's directory; Claude Code fills it in. Outside Claude Code,
   with the pack on the machine (`oto pack add report` from the cynergis registry), `oto init --pack report` does the same.
   The project records the ontology's origin, so `oto status` says when a newer release exists and
   `oto ontology diff` shows what changed. Add `--ontology <name>,...` to merge other ontologies
   with the pack's (a product type, the flow).

2. **Go on with this pack's skills**, written for this domain:

   - **report:ask-reports**: Answer questions about the report catalogue from the report knowledge base.
   - **report:new-report**: Define a new report type with a report analyst, in the report knowledge base.

3. **For anything else, the engine's skills**: capture-form to answer the vocabulary's
   questions in an interview, ontology-interview to fit the vocabulary to the documents at hand,
   build-knowledge-base for a folder of documents, query-knowledge for questions. The engine
   plugin `oto` comes with this pack: the `kg_*` tools and the generic skills are available once
   it is installed.

## What the ontology declares

- **ReportType**: A family of documents sharing one purpose, one set of sections and fields, one table and one template; identified by id and version, with a lifecycle and an owner.
- **StatusChange**: One step in the lifecycle of a report type: the status it reached, who recorded it and when. Appended, never rewritten; the last one is the report's current status.
- **Parameter**: A value that identifies one document of a report type (fund, series, as-of month, locale), with where its allowed values come from at run time.
- **UniverseQuery**: A named query that lists the allowed values of a parameter at run time.
- **Section**: A named part of a report with one purpose, rendered by one component, holding an ordered set of fields; present in every layout or only in some.
- **Field**: A piece of information the report shows: typed, ordered in its section, with a meaning per locale, rules, and the column that supplies it. Shared across reports by its id.
- **FieldMeaning**: The label and definition of a field in one locale.
- **Rule**: A constraint or regulatory requirement on a field or on the report as a whole.
- **DataSource**: A database the analyst names as the origin of a report's data: a kind and a database; credentials never here.
- **Table**: A table of a data source, identified by dataset and name; a report reads one.
- **Column**: A column of a table; the one that supplies a field's value, or binds a parameter.
- **Run**: One execution of the template-build flow: which flow and engine version, which source documents it used, what it produced.
- **Approval**: A recorded human decision at a gate of a run: reviewer, decision, time.
- **Schedule**: When documents of a release are produced: cadence, day, as-of rule, calendar, timezone.
- **VerificationPolicy**: Thresholds a produced document must meet: static-region similarity, overflow, fidelity.
- **ApprovalPolicy**: How much human review a production batch gets: sample rate and minimum, full review after a release, reviewer role.
- **PublishPolicy**: Where produced documents go: path pattern, formats, retention.
- **ObservabilityPolicy**: What a production run must achieve and who hears when it does not: deadline, tolerated failure rate, alert recipients, where the run history is recorded.
- **Revision**: One accepted revision of a report type's definition: who accepted it, when, from which date it applies, why, and the facts it changed.
- **Change**: One fact a revision added, changed or removed, with its value before and after.
- **TemplateRelease**: The versioned, frozen template folder that renders documents of a report type, carrying the operating contract and what it needs to render.
- **Macro**: A template macro of the shared library that draws a section; shared across reports. Named Macro, not Component, so a project that composes the report domain with the estate keeps the estate's Component.
- **SourceDocument**: The sample PDF the analyst provided, which the template reproduces, with its fingerprint.
- **Transformation**: The logic that computes a field's value from columns and other fields when it is not read from one column: a calculation, a mapping, a filter, an aggregation, a lookup, with its expression. Folded from report-generation on 2026-10-07; a product whose rule is 'never compute' declares none.
- **QualityCheck**: A rule that guards a field, a column or a table: what it tests, its threshold, how severe a failure is. Folded from report-generation on 2026-10-07.
- **Finding**: One dated failure of a quality check in one run, with its severity and whether it is resolved. Folded from report-generation on 2026-10-07.
