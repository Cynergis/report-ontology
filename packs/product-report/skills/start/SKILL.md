---
name: start
description: >-
  Start or extend an OTO knowledge project in this domain: A report product's specification: which report types it must produce, where their data must come from, what layout and fidelity, which channels, which rules and sign-offs, what a run must guarantee, what must stay answerable afterwards, what identifies a document, who owns what, and when a report type is ready. The pack 'product-report' (release 2) embeds the ontology 'product-report' (release 3), which declares . Use when someone wants a knowledge graph, a vocabulary or an interview for this domain.
---

# Report product

A report product's specification: which report types it must produce, where their data must come from, what layout and fidelity, which channels, which rules and sign-offs, what a run must guarantee, what must stay answerable afterwards, what identifies a document, who owns what, and when a report type is ready.

This skill comes with the `product-report` pack. The ontology is inside the pack, so nothing is fetched.

1. **Start a project from this pack.**

   ```bash
   oto init --name "<project name>" --pack "${CLAUDE_PLUGIN_ROOT}" --project <root>
   ```

   `${CLAUDE_PLUGIN_ROOT}` is this pack's directory; Claude Code fills it in. Outside Claude Code,
   with the pack on the machine (`oto pack add product-report` from the cynergis registry), `oto init --pack product-report` does the same.
   The project records the ontology's origin, so `oto status` says when a newer release exists and
   `oto ontology diff` shows what changed. Add `--ontology <name>,...` to merge other ontologies
   with the pack's (a product type, the flow).

2. **Run the ontology-interview skill** to fit the vocabulary to the documents at hand.

3. **Hand over** to the build-knowledge-base skill for the documents, and to the query-knowledge
   skill for questions. The engine plugin `oto` comes with this pack: the `kg_*` tools and the
   generic skills are available once it is installed.

## What the ontology declares

