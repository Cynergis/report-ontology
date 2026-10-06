# Report ontology, as an OTO unit

The report ontology of the report-ontology repository (`ontology/report.ttl`, version 2.1.0),
ported by `tools/oto_port.py`: 23 classes (the report's own and the three doctemplate classes it
reuses), the relations and attributes, the 21 competency questions rewritten in OTO's pattern
language, the shapes OTO holds as counts, and the rest of the shapes as policy rules. Every term
keeps its IRI under `https://cynergis.ai/ont/report#`.

**Edit the questions, not the SPARQL.** `questions.json` is the source the engine runs; the build
renders each as SPARQL into `questions.yaml`. `questions/report_cq.yaml` in the source repository
remains the SPARQL form of the same questions for its own tooling.

## The sample

`sample.graph.json` is the fund-profile-balanced fixture, an invented report type, compiled from
`fixtures/fund-profile-balanced/semantic/` and converted. It answers every question it must.
Replace it with your own report types once the catalogue is yours.

## What the port could not hold

Constraints of `ontology/report-shapes.ttl` that are neither a count nor a pattern:

- sh:minLength 8 on FieldMeaning.definition, sh:minLength 20 on ReportType.purpose
- sh:pattern on Approval.reviewer and Revision.changedBy (no placeholder), SourceDocument.sha256 (64 hex), Schedule.runOn, PublishPolicy.pathPattern ({template_id})
- sh:minInclusive / sh:maxInclusive on VerificationPolicy.goldenStaticSsimMin (0.9), ApprovalPolicy.sampleRate (0..1) and sampleMin (1), ObservabilityPolicy.deliverWithinHours (1) and maxFailureRate (0..1)
- the frozen-release contract as one disjunction (schedule, policies, parameters, engine/ontology/library versions): ported as separate policies for the schedule and the observability policy only

They remain in the source repository's shapes; a reader with pyshacl can still apply them to the
`graph.ttl` a build writes.

## Have a report analyst validate it

Every class carries the question it exists to answer and a reason, drawn from the [CQ] citations
of the definitions; nobody has confirmed an entry (`validated_by` is empty). Sit with the analyst
who owns a report and confirm the entries that name their work.
