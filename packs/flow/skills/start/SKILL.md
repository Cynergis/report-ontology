---
name: start
description: >-
  Start or extend an OTO knowledge project in this domain: Executable process graphs: steps with typed executors (script, OCR, Claude, human, terminal), gated by checks against metrics and parameters, connected by guarded transitions with effects, exchanging artifacts with fields; invariants and the tests derived from them. The briefs an agent reads before implementing or testing a step, building the engine, or changing a parameter or an artifact. The pack 'flow' (release 2) embeds the ontology 'flow' (release 2), which declares Artifact, Check, ClaudeStep, DeterministicStep, Effect, Flow, HumanStep, Implementation and more. Use when someone wants a knowledge graph, a vocabulary or an interview for this domain.
---

# Flow

Executable process graphs: steps with typed executors (script, OCR, Claude, human, terminal), gated by checks against metrics and parameters, connected by guarded transitions with effects, exchanging artifacts with fields; invariants and the tests derived from them. The briefs an agent reads before implementing or testing a step, building the engine, or changing a parameter or an artifact.

This skill comes with the `flow` pack. The ontology is inside the pack, so nothing is fetched.

1. **Start a project from this pack.**

   ```bash
   oto init --name "<project name>" --pack "${CLAUDE_PLUGIN_ROOT}" --project <root>
   ```

   `${CLAUDE_PLUGIN_ROOT}` is this pack's directory; Claude Code fills it in. Outside Claude Code,
   with the pack on the machine (`oto pack add flow` from the cynergis registry), `oto init --pack flow` does the same.
   The project records the ontology's origin, so `oto status` says when a newer release exists and
   `oto ontology diff` shows what changed. Add `--ontology <name>,...` to merge other ontologies
   with the pack's (a product type, the flow).

2. **Go on with this pack's skills**, written for this domain:

   - **flow:implement-step**: Implement or test one step of a flow with the brief in hand.

3. **For anything else, the engine's skills**: capture-form to answer the vocabulary's
   questions in an interview, ontology-interview to fit the vocabulary to the documents at hand,
   build-knowledge-base for a folder of documents, query-knowledge for questions. The engine
   plugin `oto` comes with this pack: the `kg_*` tools and the generic skills are available once
   it is installed.

## What the ontology declares

- **Artifact**: A file or folder exchanged between steps, with a path, format and field structure.
- **Check**: A deterministic validation run after a step; a blocking failure sets the step's outcome.
- **ClaudeStep**: Claude with a versioned prompt and a required output schema; cached by input hash; never routes.
- **DeterministicStep**: A script: same inputs, same outputs.
- **Effect**: A state mutation applied when a transition is taken (set, increment, reset, append…).
- **Flow**: A versioned process graph with entrypoints, phases, steps and transitions.
- **HumanStep**: A person records a decision; the flow pauses until it exists.
- **Implementation**: The script that executes a step.
- **Invariant**: A statement that must always hold; enforced by one or more checks.
- **Metric**: A named measurement a step records in run state and checks compare against parameters.
- **OcrStep**: An OCR engine run; output carries per-word confidence.
- **Outcome**: A named result of a step (pass, fail, approve, …); the only thing transitions branch on.
- **Phase**: A named group of steps run together (e.g. template build, production run).
- **Step**: A unit of work with declared inputs, outputs, checks and outcomes.
- **TerminalStep**: An end state.
- **TestObligation**: A test that must exist before a step's implementation is accepted; derived mechanically from the graph.
- **Transition**: A directed edge from a step, taken on an outcome when its guard holds; may apply effects to run state.
- **ArtifactField**: A named path inside a structured artifact (e.g. pages[].regions[].bbox).
- **ConfigParameter**: A configuration value (threshold, limit, seed) owned by config, never by steps.
