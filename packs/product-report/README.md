# Report product

A report product's specification: which report types it must produce, where their data must come from, what layout and fidelity, which channels, which rules and sign-offs, what a run must guarantee, what must stay answerable afterwards, what identifies a document, who owns what, and when a report type is ready.

An OTO pack in the reporting domain: the ontology `product-report` (release 3) under `ontology/`, the skill `start` that begins a project from it, and the views under `views/`. Install it in Claude Code from the registry's marketplace, or `oto pack add product-report` on a machine.

`oto pack check` validates it; `oto pack refresh` re-embeds the ontology when the registry holds a newer release; `oto pack publish --to <registry>` releases it.
