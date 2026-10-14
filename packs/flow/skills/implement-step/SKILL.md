---
name: implement-step
description: >-
  Implement or test one step of a flow with the brief in hand: ask the knowledge base what the
  step's script must know (what it reads and writes, the fields of each artifact, the checks and
  their thresholds, the metrics, the parameters, the outcomes and transitions), write the tests the
  graph derives first, then the script, and be BLOCKED by name when a fact is missing. Use when the
  user wants to "implement step X", "write the verify step", "write the tests for a step", "build
  the engine that runs the flow", or asks what a step needs before coding it.
---

# Implement a step, with the brief

The flow is facts in the knowledge base (the `flow` pack: steps, checks, transitions, artifacts,
parameters). A brief is what an agent must know before a task, as the questions it must be able to
answer; the engine runs it and says READY, with every fact, or BLOCKED, naming the questions and
their gaps. **No code before READY.**

## Talking with the person

- **Plain, natural language, in the person's words.** Never say question numbers, ids, class or
  field names, file names or commands, and never paste what a command printed.
- **Technical details only when the person asks for them.** Never offer them, not even as a choice.
- **The same clear shape every time:** say what we are about to do, ask a few questions at a time,
  read back what you understood in plain sentences, confirm, then say what is next.

## 1. Which step, and is it ready

```bash
oto query --project <root> brief implement-step            # every implementable step: READY or BLOCKED FLn
```

`kg_brief implement-step` without a parameter is the same table. Pick the step; say in plain words what
holds the others back.

## 2. Tests first

```bash
oto query --project <root> brief write-tests STEP=<step id>
```

FL12 lists what a test must exercise: each check (a pass and a fail case), each transition from
the step (a route: given the outcome and the guard, the engine moves to the target), each
invariant its checks enforce (a property). FL4 gives every check's expression, threshold and
outcome on failure; FL11 every outcome's transition and guard. Write the tests in the project's
stack, one per obligation, citing the graph (`# tests check.<scope>.<check id>`).

## 3. The implementation brief

```bash
oto query --project <root> brief implement-step STEP=<step id>
```

READY: the brief's facts are the specification you implement, and nothing else is:

- FL1 what the step is for and its executor (script, OCR, Claude, human);
- FL2 what it reads and writes, by path and format; FL3 the fields of each JSON it writes;
- FL4 the checks that gate it, FL5 the metrics it must record in state, FL6 the config
  parameters it depends on and their current values — read them from config, never hard-code;
- FL8 how it is executed (the command, the prompt, the review page) and whether an
  implementation already exists;
- FL10 the domain concepts its inputs and outputs carry; FL11 the outcomes and where each goes;
- FL7, FL9, FL18 (optional): the invariants it enforces, who consumes what it writes, its phase.

**BLOCKED**: stop. Report the blocking questions and gaps verbatim ("FL3: JSON output has no
field specification"), and have the person capture the missing fact (OTO's **capture-form**
skill); then re-ask. Never guess the fact, never implement around it.

## 4. Write the script, run the tests

Inside the declared reads and writes, recording the declared metrics, reading the declared
parameters, producing one of the declared outcomes. Cite what you implement:
`# implements check.<scope>.<check id>`, `# route transition.<scope>.<id>`. Run the tests; fix
the code or the test honestly; if a failure reveals the flow and the code disagree, say so.

## 5. Record what became true

The step is implemented: capture `isImplemented: true` on the step and the `Implementation`
(its path, that it exists) through the gates, so FL15 (which steps have no implementation)
stops listing it and the engine builder's brief (`build-engine`) stays true.

## Changing a parameter or an artifact

Before changing a threshold: `kg_brief impact-parameter PARAM=<parameter>` — the checks,
transitions, steps and tests it reaches. Before changing an artifact's structure: `kg_brief
impact-artifact ARTIFACT=<artifact>` — who writes it, who reads it.
