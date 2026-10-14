---
name: start
description: >-
  Start or extend an OTO knowledge project in this domain: A report product's specification: which report types it must produce, where their data must come from, what layout and fidelity, which channels, which rules and sign-offs, what a run must guarantee, what must stay answerable afterwards, what identifies a document, who owns what, and when a report type is ready. The pack 'product-report' (release 2) embeds the ontology 'product-report' (release 3), which declares . Use when someone wants a knowledge graph, a vocabulary or an interview for this domain.
---

# Report product

A report product's specification: which report types it must produce, where their data must come from, what layout and fidelity, which channels, which rules and sign-offs, what a run must guarantee, what must stay answerable afterwards, what identifies a document, who owns what, and when a report type is ready.

This skill comes with the `product-report` pack. The ontology is inside the pack, so nothing is fetched.

## Talking with the person

- **Plain, natural language, in the person's words.** Never say question numbers, ids, class or
  field names, file names or commands, and never paste what a command printed.
- **Technical details only when the person asks for them.** Never offer them, not even as a choice.
- **The same clear shape every time:** say what we are about to do, ask a few questions at a time,
  read back what you understood in plain sentences, confirm, then say what is next.

1. **Start a project from this pack.**

   ```bash
   oto init --name "<project name>" --pack "${CLAUDE_PLUGIN_ROOT}" --project <root>
   ```

   `${CLAUDE_PLUGIN_ROOT}` is this pack's directory; Claude Code fills it in. Outside Claude Code,
   with the pack on the machine (`oto pack add product-report`), `oto init --pack product-report` does the same.
   The project records the ontology's origin, so `oto status` says when a newer release exists and
   `oto ontology diff` shows what changed. Add `--ontology <name>,...` to merge other ontologies
   with the pack's (a product type, the flow).

2. **Run the ontology-interview skill** to fit the vocabulary to the documents at hand.

3. **Hand over** to the build-knowledge-base skill for the documents, and to the query-knowledge
   skill for questions. The engine plugin `oto` comes with this pack: the `kg_*` tools and the
   generic skills are available once it is installed.

## What the ontology declares

