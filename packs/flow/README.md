# Flow

Executable process graphs: steps with typed executors (script, OCR, Claude, human, terminal), gated by checks against metrics and parameters, connected by guarded transitions with effects, exchanging artifacts with fields; invariants and the tests derived from them. The briefs an agent reads before implementing or testing a step, building the engine, or changing a parameter or an artifact.

An OTO pack in the software domain: the ontology `flow` (release 1) under `ontology/`, the skill `start` that begins a project from it, and the views under `views/`. Install it in Claude Code from the registry's marketplace, or `oto pack add flow` on a machine.

`oto pack check` validates it; `oto pack refresh` re-embeds the ontology when the registry holds a newer release; `oto pack publish --to <registry>` releases it.
