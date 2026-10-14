# Report domain

A report type: its meaning per locale, its sections and fields, the rules that apply, the column that supplies each value, the runs and approvals that produced its template, its operating contract, its lifecycle and the accepted history of its definition.

An OTO pack: the ontology `report` (release 5) under `ontology/`, the skill `start` that begins a project from it, and the views under `views/`. Install it in Claude Code from the registry's marketplace, or `oto pack add report` on a machine.

`oto pack check` validates it; `oto pack refresh` re-embeds the ontology when the registry holds a newer release; `oto pack publish --to <registry>` releases it.
