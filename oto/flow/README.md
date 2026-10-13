# Flow — how work is executed

Ported from the `flow:` terms of `ontology/ontology.ttl` (0.1.1) and the 17 competency questions of
`questions/competency_questions.yaml` by `tools/flow_port.py`. Every term keeps its IRI under
`https://cynergis.ai/ont/flow#`.

A flow is a versioned process graph: phases with entrypoints, steps with a typed executor
(script, OCR, Claude, human, terminal), checks that gate a step against metrics and parameters,
transitions taken on an outcome under a guard with effects on run state, artifacts with fields
exchanged between steps, invariants enforced by checks, and the test obligations derived from all
of that.

## What changed in the port

- `carries` and `concerns` ranged over classes; here they are list attributes naming the concept
  (`Artifact.carries`, `Invariant.concerns`). What a concept means is its class's definition.
- The questions the original wrote with `UNION` read one derived relation instead: `dependsOn`
  (a step and the parameters it depends on, FL6), `affectedBy` (what a parameter change reaches,
  FL16), `readBy` (an artifact's consumers, FL9), `requiresTest` (what the tests of a step must
  exercise, FL12). The rules derive them; a relation declared `derived` is never captured.
- The engine derives edges and attributes, not nodes, so a captured flow's test obligations are
  the `requiresTest` edges; `TestObligation` nodes with an id code can cite are what the port
  materialises (as `derive_tests.rq` did) and FL21 reads.
- The original's `gaps_only` gate is `no_gaps`: the answer may be empty, a gap makes it unanswered.
- Four names other ontologies use for other things are renamed, new IRIs and all, so a project
  composes them: `Field` is `ArtifactField` (`hasArtifactField`), `Parameter` is
  `ConfigParameter`, `producedBy` is `outputOf` (the report ontology's), and `measures` is
  `measuresMetric` (the product ontology's `measures`: a success criterion measures what it judges). The prompt reference and the review page are
  declared on `Step`, so one question (FL8) reads the execution spec of any step.
- Test obligations are materialised by the port (as `kgctl build` derived them with SPARQL
  CONSTRUCT) in the fixture graph, cited to `derive_tests.rq`.
- Four questions were added, so every term is cited by a question that runs: FL18 (phase and
  entrypoint), FL19 (effects and provenance), FL20 (a Claude step's prompt, schema and scope),
  FL21 (what a test obligation exercises).
- Release 2 adds what a flow declared as dependencies needs (a pipeline's batch run), beside the
  state machine of transitions. These terms are the port's own: the TTL vocabulary stays frozen
  until the software factory contract is written. `waitsFor` (a join: the steps that must finish
  first), the derived `after` (through any number of waits), `Step.stepKind` (what the step does,
  in its flow kind's vocabulary), `Step.parallelGroup`, and on `Flow` the `flowKind`, `trigger`
  and `resumable`. FL22 to FL24 ask for them; three policies keep a declared flow runnable: a step
  comes after the writer of what it reads, steps of one parallel group touch no artifact one of
  them writes, and no step comes after itself. A flow kind's own vocabulary and rules (a medallion
  pipeline's step kinds, gates and layers) live in that kind's ontology.

## The briefs

`briefs.json` carries the five task types: `implement-step`, `write-tests`, `build-engine`,
`impact-parameter`, `impact-artifact`. `oto query brief implement-step STEP=<step>` is READY or
BLOCKED by name; without the step, the table for every implementable step (what `kgctl
readiness` printed).
