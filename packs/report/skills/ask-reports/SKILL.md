---
name: ask-reports
description: >-
  Answer questions about the report catalogue from the report knowledge base: which report types
  exist, what sections and fields a report shows and what they mean, which data source, table and
  column each value comes from, when a report runs and under which policies, where a report is in
  its lifecycle, how its definition changed, which fields the catalogue already defines, what a term
  means. Use when the user asks "what reports do we have", "what does this report show", "where does
  this data come from", "when does it run", "what does <term> mean", or any question about a report
  definition.
---

# Answer questions from the report knowledge base

The answers live in the project's knowledge graph, built from captured facts through the curate
gates. You reach it through the engine's tools, read-only: `kg_questions` (every question and
whether the graph answers it), `kg_ask <id> params` (one question, run: the rows, or the gap),
`kg_define <term>` (what a class, relation or attribute means), `kg_entity`, `kg_neighbors`,
`kg_search`. On the command line: `oto query --project <root> questions | ask | define | entity`.

The graph answers a fixed set of competency questions (Q1–Q26 of the report ontology; RP1–RP10
when the `product-report` pack is composed; FL1–FL21 for the flow). That is deliberate: each
answer is a query someone wrote, confirmed and tested, so it is the same answer every time and
it can say what is missing. Your job is to match what the person asked to the right question,
run it, and report the result faithfully.

## How to answer

1. **Find the question.** `kg_questions` once per conversation; do not rely on a remembered list,
   the ontology adds questions over time. Pick the question whose wording covers what was asked.
   Several may be needed: "tell me about this report" is Q1 (the catalogue entry), Q7 (its
   sections and fields), Q4 and Q5 (its data), Q11 (its schedule), Q17 (its status).
2. **Fill its parameters.** Each question names what it needs (`REPORT`, `FIELD`, `COLUMN`,
   `THING`). An entity is named by its id, its label or an alias; if the person named a report
   loosely ("the balanced fund sheet"), run Q1 first and match. If two fit, ask which.
3. **Run it** and read `status`:
   - `answered` — report the rows.
   - `unanswered` with a gap — the graph knows what is missing; say the gap in plain words ("the
     report has no section yet") and never fill it from your own knowledge.
   - `empty` — the graph holds nothing for this. Say so; an empty answer is a fact about the
     catalogue, not a failure to cover up.
   - `violated` / `clean` — an `empty`-gated question: rows are findings.
4. **Say where the answer came from**: the question id, the entity it concerns, and the source
   document the facts cite (`kg_entity` shows `source_doc` and the evidence quote).

## Questions about meaning

"What is lineage status", "what does `sourcedFrom` connect": `kg_define <term>` returns the
definition, the domain and range of a relation, the choices of an enum. For the reasoning behind
a term (why it exists, who confirmed it), the project's `ontology.rationale.json`.

## Questions about readiness and history

"Is the report ready for production" is a computed answer, never an assertion: `kg_ask RP10`
(with `product-report`) or Q4 + Q19 + Q17. "What changed" is Q15 (the revisions of the
definition) and Q16 (a field's history); "as of a date" is `kg_entity --as-of`.

## When no question fits

Do not improvise an answer from file contents or general knowledge and present it as the
graph's. Say that the graph has no question for this yet; offer the nearest question's part and
name what it leaves out; and write the person's question, as asked, with today's date, to
`notes/UNANSWERED.md` in the project. That file is how a missing question reaches the ontology's
owner: a new term or question always starts as a competency question.

## Presenting answers

Lead with the answer in a sentence, then the rows as a short table when there are several. Use the
report's title and the fields' labels where the rows give them; keep ids in code formatting so the
person can reuse them. Translate codes the first time (`business_day:3` is "the third business
day"; `lineageStatus: proposed` is "a column was proposed, nobody verified it").
