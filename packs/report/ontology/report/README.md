# Report domain — starter vocabulary

Exported from the project **Report domain** (vocabulary version 1) with `oto ontology export`.

A first draft, not a finished model. **Edit it.** An ontology adopted unchanged is a worse outcome than no ontology, because nobody owns it and nobody recognizes the words.

In the source project, 23 of 23 classes had been confirmed by a named domain expert. That confirmation does not carry over: `validated_by` is empty here until someone who knows *your* domain confirms each class.

## Classes, and the question each answers

- **ReportType**: A family of documents sharing one purpose, one set of sections and fields, one table and one template; identified by id and version, with a lifecycle and an owner.
  - *Question:* Which report types exist: what is each for, for whom, in which locales and formats, how often, and where is it in its lifecycle?
  - *Why a class:* Needed by Q1, Q17: a thing with its own identity, dates or relationships, not a value about another; the catalogue is the first thing a reader asks for
- **StatusChange**: One step in the lifecycle of a report type: the status it reached, who recorded it and when. Appended, never rewritten; the last one is the report's current status.
  - *Question:* Where is $REPORT in its lifecycle, and who recorded each step, when?
  - *Why a class:* Needed by Q17: a thing with its own identity, dates or relationships, not a value about another; the lifecycle log tells a draft from a report in production
- **Parameter**: A value that identifies one document of a report type (fund, series, as-of month, locale), with where its allowed values come from at run time.
  - *Question:* What identifies one document of $REPORT, and where do the allowed values of each identifier come from at run time?
  - *Why a class:* Needed by Q2: a thing with its own identity, dates or relationships, not a value about another; a batch is expanded from the identifiers' universes
- **UniverseQuery**: A named query that lists the allowed values of a parameter at run time.
  - *Question:* What identifies one document of $REPORT, and where do the allowed values of each identifier come from at run time?
  - *Why a class:* Needed by Q2: a thing with its own identity, dates or relationships, not a value about another; a batch is expanded from the identifiers' universes
- **Section**: A named part of a report with one purpose, rendered by one component, holding an ordered set of fields; present in every layout or only in some.
  - *Question:* Which sections and fields make up $REPORT, in what order, and which appear only in some layouts?
  - *Why a class:* Needed by Q7: a thing with its own identity, dates or relationships, not a value about another; the structure of a report is read from its sections in order
- **Field**: A piece of information the report shows: typed, ordered in its section, with a meaning per locale, rules, and the column that supplies it. Shared across reports by its id.
  - *Question:* What does field $FIELD mean, and what label does it carry, in each language the report is offered in?
  - *Why a class:* Needed by Q3, Q4, Q7, Q16, Q20: a thing with its own identity, dates or relationships, not a value about another; a field's meaning per locale is what the report promises its reader
- **FieldMeaning**: The label and definition of a field in one locale.
  - *Question:* What does field $FIELD mean, and what label does it carry, in each language the report is offered in?
  - *Why a class:* Needed by Q3: a thing with its own identity, dates or relationships, not a value about another; a field's meaning per locale is what the report promises its reader
- **Rule**: A constraint or regulatory requirement on a field or on the report as a whole.
  - *Question:* Which fields of $REPORT carry rules, and which rules are regulatory?
  - *Why a class:* Needed by Q18: a thing with its own identity, dates or relationships, not a value about another; a regulatory rule is what compliance checks before a document goes out
- **DataSource**: A database the analyst names as the origin of a report's data: a kind and a database; credentials never here.
  - *Question:* Which data source and table does $REPORT read, and which column carries each identifier?
  - *Why a class:* Needed by Q5: a thing with its own identity, dates or relationships, not a value about another; the loader needs the source, the table and the parameter columns
- **Table**: A table of a data source, identified by dataset and name; a report reads one.
  - *Question:* Which column of which table supplies each field of $REPORT, and which fields have no column yet?
  - *Why a class:* Needed by Q4, Q5: a thing with its own identity, dates or relationships, not a value about another; the mapping is the data team's contract; an unmapped field blocks production
- **Column**: A column of a table; the one that supplies a field's value, or binds a parameter.
  - *Question:* Which column of which table supplies each field of $REPORT, and which fields have no column yet?
  - *Why a class:* Needed by Q4, Q5, Q6: a thing with its own identity, dates or relationships, not a value about another; the mapping is the data team's contract; an unmapped field blocks production
- **Run**: One execution of the template-build flow: which flow and engine version, which source documents it used, what it produced.
  - *Question:* Which source document, run and approvals produced the template of $REPORT?
  - *Why a class:* Needed by Q14: a thing with its own identity, dates or relationships, not a value about another; provenance of a template: the sample, the run, the decisions
- **Approval**: A recorded human decision at a gate of a run: reviewer, decision, time.
  - *Question:* Which source document, run and approvals produced the template of $REPORT?
  - *Why a class:* Needed by Q14: a thing with its own identity, dates or relationships, not a value about another; provenance of a template: the sample, the run, the decisions
- **Schedule**: When documents of a release are produced: cadence, day, as-of rule, calendar, timezone.
  - *Question:* When does $REPORT run: cadence, day, as-of rule, calendar, timezone, and at which template version?
  - *Why a class:* Needed by Q11: a thing with its own identity, dates or relationships, not a value about another; the dispatcher reads the schedule from the release
- **VerificationPolicy**: Thresholds a produced document must meet: static-region similarity, overflow, fidelity.
  - *Question:* Which sample document does the template of $REPORT reproduce, and what thresholds must a produced document meet?
  - *Why a class:* Needed by Q9, Q19: a thing with its own identity, dates or relationships, not a value about another; the template is held to the sample and to its thresholds
- **ApprovalPolicy**: How much human review a production batch gets: sample rate and minimum, full review after a release, reviewer role.
  - *Question:* What verification thresholds and approval policy govern production runs of $REPORT?
  - *Why a class:* Needed by Q19: a thing with its own identity, dates or relationships, not a value about another; a produced document must meet its thresholds and get the review its policy says
- **PublishPolicy**: Where produced documents go: path pattern, formats, retention.
  - *Question:* Where do documents of $REPORT go, in which formats, and for how long are they kept?
  - *Why a class:* Needed by Q10: a thing with its own identity, dates or relationships, not a value about another; where documents go and how long they stay is a promise to readers
- **ObservabilityPolicy**: What a production run must achieve and who hears when it does not: deadline, tolerated failure rate, alert recipients, where the run history is recorded.
  - *Question:* What must a run of $REPORT achieve, who is alerted when it does not, and where is the run history?
  - *Why a class:* Needed by Q12: a thing with its own identity, dates or relationships, not a value about another; what a run must achieve, and who hears when it does not, is the operating promise
- **Revision**: One accepted revision of a report type's definition: who accepted it, when, from which date it applies, why, and the facts it changed.
  - *Question:* How has the definition of $REPORT changed: each revision, who accepted it, when, from when it applies, why, and which facts changed?
  - *Why a class:* Needed by Q15, Q16: a thing with its own identity, dates or relationships, not a value about another; a definition corrected in place loses what was true when earlier documents went out
- **Change**: One fact a revision added, changed or removed, with its value before and after.
  - *Question:* How has the definition of $REPORT changed: each revision, who accepted it, when, from when it applies, why, and which facts changed?
  - *Why a class:* Needed by Q15, Q16: a thing with its own identity, dates or relationships, not a value about another; a definition corrected in place loses what was true when earlier documents went out
- **TemplateRelease**: The versioned, frozen template folder that renders documents of a report type, carrying the operating contract and what it needs to render.
  - *Question:* Which component renders field $FIELD, in which template release, and which other reports use that component?
  - *Why a class:* Needed by Q8, Q9, Q11, Q13: a thing with its own identity, dates or relationships, not a value about another; a change to a component must be checked against the fields it draws
- **Component**: A template macro of the shared library that draws a section; shared across reports.
  - *Question:* Which component renders field $FIELD, in which template release, and which other reports use that component?
  - *Why a class:* Needed by Q8: a thing with its own identity, dates or relationships, not a value about another; a change to a component must be checked against the fields it draws
- **SourceDocument**: The sample PDF the analyst provided, which the template reproduces, with its fingerprint.
  - *Question:* Which sample document does the template of $REPORT reproduce, and what thresholds must a produced document meet?
  - *Why a class:* Needed by Q9, Q14: a thing with its own identity, dates or relationships, not a value about another; the template is held to the sample and to its thresholds

## Relations

| Relation | Domain | Range | Meaning |
| --- | --- | --- | --- |
| `hasSection` | ReportType | Section | The report type is made of this section. |
| `hasField` | Section | Field | The section shows this field. |
| `inSection` | Field | Section | The one section that shows the field. |
| `inReport` | Field | ReportType | The report type the field belongs to, stated on the field so fields compare across reports. |
| `hasMeaning` | Field | FieldMeaning | The label and definition of the field in one locale. |
| `hasRule` | Field|ReportType | Rule | A constraint or regulatory requirement that applies to the field, or to the report as a whole. |
| `renderedBy` | Section | Component | The component that draws the section. |
| `hasParameter` | ReportType|TemplateRelease | Parameter | A value that identifies one document; from a release, with where its allowed values come from at that version. |
| `universeQuery` | Parameter | UniverseQuery | The query that lists the parameter's allowed values at run time. |
| `boundToColumn` | Parameter | Column | The column whose value selects the rows of one document. |
| `hasStatusChange` | ReportType | StatusChange | A step in the report type's lifecycle; together they are its history. |
| `readsTable` | ReportType | Table | The table that holds every column the report needs. |
| `inDataSource` | Table | DataSource | The data source the table lives in. |
| `inTable` | Column | Table | The table the column belongs to. |
| `sourcedFrom` | Field | Column | The column that supplies the field's value: the mapping, proposed by the agent and verified by the analyst. |
| `derivedFrom` | ReportType | SourceDocument | The sample PDF the report's template reproduces. |
| `releasedAs` | ReportType | TemplateRelease | The versioned template that renders documents of the report type. |
| `usedSource` | Run | SourceDocument | A source document the run read as input. |
| `hasApproval` | Run | Approval | A human decision recorded at a gate of the run. |
| `hasSchedule` | TemplateRelease | Schedule | When documents of the release are produced. |
| `hasVerificationPolicy` | TemplateRelease | VerificationPolicy | The thresholds every produced document must meet. |
| `hasApprovalPolicy` | TemplateRelease | ApprovalPolicy | How much human review a production batch gets. |
| `hasPublishPolicy` | TemplateRelease | PublishPolicy | Where produced documents go, in which formats, for how long. |
| `hasObservabilityPolicy` | TemplateRelease | ObservabilityPolicy | What a run must achieve and who is alerted. |
| `hasRevision` | ReportType | Revision | An accepted revision of the report type's definition; together they are its history. |
| `hasChange` | Revision | Change | A fact the revision added, changed or removed. |
| `producedBy` | TemplateRelease | Run | The run of the template-build flow that produced the release. |

## Growing it

```bash
oto ontology check --project <root>      # what a change breaks, and conformance
oto ontology rationale --project <root>  # which classes still lack a confirmed reason
oto ontology accept --project <root>     # record the vocabulary as the baseline
```
