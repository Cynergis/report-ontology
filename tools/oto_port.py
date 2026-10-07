#!/usr/bin/env python3
"""Port the report ontology to an OTO ontology unit: oto/report/.

    python tools/oto_port.py [--oto <path to the OTO repository>] [--check]

Reads ontology/report.ttl (the terms, with the three doctemplate classes it reuses taken from
ontology/ontology.ttl), ontology/report-shapes.ttl (the shapes OTO can hold: counts; the rest
become policy rules or are listed in the unit's README), and the fixture
fixtures/fund-profile-balanced (its compiled graph becomes the sample). The 21 competency
questions of questions/report_cq.yaml are rewritten here in OTO's pattern language, by hand: the
SPARQL stays the rendering, the pattern form becomes the source the engine runs.

The unit's namespace is the ontology's own (https://cynergis.ai/ont/report#), so every term keeps
its IRI. Needs rdflib; needs the OTO engine importable (`--oto`, or OTO_HOME, or ../oto).
"""
import argparse
import datetime
import json
import os
import re
import sys
import tempfile
import types

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(HERE, "oto", "report")
RPT = "https://cynergis.ai/ont/report#"
DT = "https://cynergis.ai/ont/doctemplate#"
SH = "http://www.w3.org/ns/shacl#"
KG = "https://cynergis.ai/kg/"
FIXTURE = os.path.join(HERE, "fixtures", "fund-profile-balanced", "semantic", "report.graph.json")
#: The doctemplate classes the report ontology reuses, with their meaning here.
DT_CLASSES = ("TemplateRelease", "SourceDocument", "Component")
#: Datatype properties that carry one value per occurrence: lists in OTO.
LISTS = ("audience", "locale", "alias", "allowedValue", "publishFormat", "alertRecipient", "step", "fileHash", "font",
         "assetPending", "waiver", "sha256", "pageKind", "note")
#: Controlled values the shapes fix (sh:in), as enums; the attribute keeps its name.
ENUMS = {"lifecycleStatus": "inception|saved|in_validation|in_production",
         "fieldType": "text|enum|number|integer|percent|currency|currency_pair|percent_by_series|date|list|grouped_list|series|list_of_text|boolean",
         "lineageStatus": "unmapped|proposed|verified",
         "result": "draft|signed_off|frozen",
         "cadence": "daily|weekly|monthly|quarterly|semi_annual|annual|on_demand",
         "changeKind": "added|changed|removed"}
#: The locale of a field meaning is one language; on a report type it is a list of them (LISTS).
NUMERIC = {"goldenStaticSsimMin": "number", "fidelityMin": "number", "sampleRate": "number", "maxFailureRate": "number",
           "sampleMin": "integer", "retentionDays": "integer", "deliverWithinHours": "integer", "order": "integer",
           "regulatory": "boolean", "overflowBlocking": "boolean", "fullReviewAfterRelease": "boolean", "frozen": "boolean"}
SAMPLE_DATE = "2026-10-05"
SAMPLE_DOC = "fund-profile-balanced"


def _oto(path):
    path = path or os.environ.get("OTO_HOME") or os.path.join(os.path.dirname(HERE), "oto")
    if os.path.exists(os.path.join(path, "oto", "__init__.py")):
        sys.path.insert(0, path)
    try:
        import oto  # noqa: F401
    except ImportError:
        raise SystemExit("the OTO engine was not found at %s and is not installed: pass --oto <path>, or pip install oto-kg" % path)


# ============================ the vocabulary ============================

def vocabulary(work):
    """ontology.config.json content, through OTO's own importer, from a Turtle that holds the
    report terms and the three doctemplate classes they reuse."""
    from rdflib import Graph, Namespace, RDF, RDFS, OWL, URIRef
    from oto.model import rdf_import
    src = Graph()
    src.parse(os.path.join(HERE, "ontology", "report.ttl"), format="turtle")
    whole = Graph()
    whole.parse(os.path.join(HERE, "ontology", "ontology.ttl"), format="turtle")
    for name in DT_CLASSES:
        iri = URIRef(DT + name)
        for p, o in whole.predicate_objects(iri):
            if p in (RDF.type, RDFS.label, RDFS.comment) or str(p).startswith("http://www.w3.org/2004/02/skos/core#"):
                src.add((iri, p, o))
        src.add((iri, RDF.type, OWL.Class))
    # the shapes OTO holds: counts, on shapes that are not warnings
    shapes = Graph()
    shapes.parse(os.path.join(HERE, "ontology", "report-shapes.ttl"), format="turtle")
    kept = Graph()
    for shape in shapes.subjects(RDF.type, URIRef(SH + "NodeShape")):
        if shapes.value(shape, URIRef(SH + "severity")) is not None:
            continue
        for p, o in shapes.predicate_objects(shape):
            if p == URIRef(SH + "property"):
                if shapes.value(o, URIRef(SH + "severity")) is not None:
                    continue
                kept.add((shape, p, o))
                for pp, oo in shapes.predicate_objects(o):
                    kept.add((o, pp, oo))
            elif p != URIRef(SH + "sparql"):
                kept.add((shape, p, o))
    terms_path = os.path.join(work, "report-terms.ttl")
    shapes_path = os.path.join(work, "report-counts.ttl")
    src.serialize(terms_path, format="turtle")
    kept.serialize(shapes_path, format="turtle")
    classes, properties, notes = rdf_import.read([terms_path, shapes_path])
    attributes, schemes, namespaces, rationale = rdf_import.read.attributes, rdf_import.read.schemes, rdf_import.read.namespaces, rdf_import.read.rationale
    for note in notes:
        print("  importer:", note)
    # the shapes' sh:in become enums, one value per occurrence becomes a list, numbers are numbers
    for kind, declared in attributes.items():
        for name, spec in declared.items():
            if name in ENUMS and not (name == "locale" and kind == "ReportType"):
                spec["type"] = "enum:" + ENUMS[name]
            if name in LISTS and not (name == "locale" and kind == "FieldMeaning"):
                spec["type"] = "list"
            if name in NUMERIC:
                spec["type"] = NUMERIC[name]
    config = {
        "_about": "The report ontology as an OTO ontology unit, ported from ontology/report.ttl by tools/oto_port.py. "
                  "Every term keeps its IRI under https://cynergis.ai/ont/report#; the three doctemplate classes it reuses "
                  "keep theirs. A relation is {domain, range, inverse, definition}. Use A|B for a union.",
        "_summary": "A report type: what it is for, its sections and fields with their meaning per locale, the rules that apply, "
                    "the column of the table that supplies each value, the runs and approvals that produced its template, "
                    "its operating contract (schedule, policies), its lifecycle and the accepted history of its definition.",
        "name": "Report ontology", "ontology_version": 1, "strict_domains": False, "languages": ["en"],
        "classes": classes, "properties": properties, "attributes": attributes,
    }
    if schemes:
        config["schemes"] = schemes
    config["namespaces"] = namespaces
    return config, rationale


# ============================ the sample ============================

def node_id(iri):
    tail = str(iri)[len(KG):].strip("/") if str(iri).startswith(KG) else str(iri).rsplit("/", 1)[-1]
    return re.sub(r"[^a-z0-9_.-]+", "-", tail.replace("/", ".").lower())


def sample(config):
    """The fixture's compiled graph as OTO nodes and edges, typed by the vocabulary."""
    from rdflib import Graph, RDF, RDFS, Literal
    from oto.model.vocabulary import declared_attributes
    g = Graph().parse(FIXTURE, format="json-ld")
    properties = config["properties"]
    stamp = {"as_of": SAMPLE_DATE, "valid_from": SAMPLE_DATE, "source_doc": SAMPLE_DOC, "status": "current", "sources": [SAMPLE_DOC]}
    nodes, edges = {}, []
    for s, t in g.subject_objects(RDF.type):
        kind = str(t).rsplit("#", 1)[-1]
        if kind not in config["classes"]:
            continue
        nid = node_id(s)
        label = g.value(s, RDFS.label)
        node = dict(id=nid, type=kind, label=str(label) if label is not None else nid.rsplit(".", 1)[-1],
                    aliases=[], summary="", attributes={}, tags=[SAMPLE_DOC], **stamp)
        declared = declared_attributes(config, kind)
        for p, o in g.predicate_objects(s):
            name = str(p).rsplit("#", 1)[-1]
            if p in (RDF.type, RDFS.label):
                continue
            if name in properties and not isinstance(o, Literal):
                edges.append({"from": nid, "rel": name, "to": node_id(o)})
            elif name in declared:
                value = o.toPython() if isinstance(o, Literal) else str(o)
                if hasattr(value, "isoformat"):
                    value = value.isoformat()
                typed = declared[name]["type"]
                if typed == "list":
                    node["attributes"].setdefault(name, []).append(str(value))
                elif typed in ("number",):
                    node["attributes"][name] = float(value)
                elif typed == "integer":
                    node["attributes"][name] = int(value)
                elif typed == "boolean":
                    node["attributes"][name] = bool(value)
                else:
                    node["attributes"][name] = str(value)
            elif name == "alias":
                node["aliases"].append(str(o))
        node["attributes"].pop("compiledAt", None)            # the source tooling's compile time, not a fact of the report
        if "alias" in node["attributes"]:
            node["aliases"] = list(node["attributes"]["alias"])
        if "definition" in node["attributes"] and not node["summary"]:
            node["summary"] = node["attributes"]["definition"]
        for name in list(node["attributes"]):
            if declared.get(name, {}).get("type") == "list":
                node["attributes"][name] = sorted(node["attributes"][name])
        nodes[nid] = node
    ids = set(nodes)
    edges = [e for e in edges if e["from"] in ids and e["to"] in ids]
    edges.sort(key=lambda e: (e["from"], e["rel"], e["to"]))
    return {"_about": "The fund-profile-balanced fixture of the report-ontology repository, an invented report type, "
                      "compiled from its semantic/ files and converted by tools/oto_port.py. Replace it.",
            "nodes": [nodes[k] for k in sorted(nodes)], "edges": edges}


# ============================ the questions ============================

def q(who, question, why, when, select, gate="any", params=None, gaps=None, terms=None):
    out = {"who": who, "question": question, "why": why, "validated_by": ""}
    if params:
        out["params"] = {name: {"type": kind} for name, kind in params.items()}
    out["ask"] = {"when": when, "select": select}
    out["gate"] = gate
    if gaps:
        out["gaps"] = [{"when": w, "say": s} for w, s in gaps] if isinstance(gaps, list) else {"when": gaps[0], "say": gaps[1]}
    if terms:
        out["terms"] = terms
    return out


def edge(a, rel, b):
    return {"edge": [a, rel, b]}


def node(var, kind=None, where=None):
    out = {"node": var}
    if kind:
        out["type"] = kind
    if where:
        out["where"] = where
    return out


def not_edge(a, rel, b):
    return {"not_edge": [a, rel, b]}


def optional(*patterns):
    return {"optional": list(patterns)}


QUESTIONS = {
    "CQ1": q("analyst", "What does field $FIELD mean, and what is its label in each locale?",
             "A field's meaning per locale is what the report promises its reader; a reader of a figure must be able to ask it.",
             [edge("$FIELD", "hasMeaning", "m"), node("m", "FieldMeaning")],
             ["m.locale", "m.label", "m.definition"], gate="non_empty", params={"FIELD": "Field"},
             gaps=[([edge("$FIELD", "inReport", "r"), node("r", "ReportType", {"locale": {"contains": "fr"}}),
                     {"not_edge": ["$FIELD", "hasMeaning", "*"]}], "no meaning in a locale the report is offered in")],
             terms=["Field.fieldType"]),
    "CQ2": q("analyst", "Which sections and fields make up report $REPORT, in order, and which are layout-dependent?",
             "The structure of a report is read from its sections and their fields, in order; a section present only in some layouts must say so.",
             [edge("$REPORT", "hasSection", "s"), node("s", "Section"), edge("s", "hasField", "f"), node("f", "Field")],
             ["s.order", "s", "s.purpose", "s.presentWhen", "f.order", "f.fieldId"], gate="non_empty", params={"REPORT": "ReportType"},
             gaps=[([not_edge("$REPORT", "hasSection", "*")], "the report has no section")],
             terms=["Field.order"]),
    "CQ3": q("compliance", "Which source document, run and approvals produced the template of report $REPORT?",
             "Provenance of a template: the sample PDF it reproduces, the run that built it, the human decisions at its gates.",
             [edge("$REPORT", "derivedFrom", "src"), node("src", "SourceDocument"),
              optional(edge("run", "usedSource", "src"), node("run", "Run"),
                       optional(edge("run", "hasApproval", "a"), node("a", "Approval")))],
             ["src.repoUrl", "src.sha256", "src.role", "src.referenceKind", "run", "run.flow", "run.flowVersion", "run.engineVersion",
              "run.startedAt", "run.result", "a.gate", "a.decision", "a.reviewer", "a.at"],
             gate="non_empty", params={"REPORT": "ReportType"},
             gaps=[([not_edge("$REPORT", "derivedFrom", "*")], "report has no source document")],
             terms=["SourceDocument.pageKind", "SourceDocument.receivedOn", "SourceDocument.note", "Run.step", "Approval.reviewedHash", "producedBy"]),
    "CQ4": q("compliance", "Which fields of report $REPORT carry rules, and which rules are regulatory?",
             "A regulatory rule on a field is what compliance checks before a document goes out.",
             [edge("f", "inReport", "$REPORT"), node("f", "Field"), edge("f", "hasRule", "ru"), node("ru", "Rule")],
             ["f.fieldId", "ru.ruleText", "ru.regulatory"], params={"REPORT": "ReportType"}),
    "CQ5": q("data team", "Which column of which table supplies each field of report $REPORT, what type is each field, and which fields are still unmapped?",
             "The field-to-column mapping is the data team's contract; an unmapped field blocks a production release.",
             [edge("f", "inReport", "$REPORT"), node("f", "Field"),
              optional(edge("f", "sourcedFrom", "c"), node("c", "Column"), edge("c", "inTable", "t"), node("t", "Table"))],
             ["f.fieldId", "f.lineageStatus", "t.dataset", "t.tableName", "c.columnName", "f.fieldType", "f.lineageNote"],
             gate="non_empty", params={"REPORT": "ReportType"},
             gaps=[([edge("f", "inReport", "$REPORT"), node("f", "Field", {"lineageStatus": "unmapped"})], "field not mapped to a column")]),
    "CQ6": q("data team", "If column $COLUMN changes, which reports and fields are affected?",
             "A column change must be checked against every field that reads it, across reports.",
             [edge("$COLUMN", "inTable", "t"), node("t", "Table"), edge("f", "sourcedFrom", "$COLUMN"), node("f", "Field"), edge("f", "inReport", "r")],
             ["r", "f.fieldId", "f.lineageStatus", "t.dataset", "t.tableName"], params={"COLUMN": "Column"}),
    "CQ7": q("data team", "Which data source and table does report $REPORT read, and which column carries each parameter?",
             "The loader needs the source, the table and the parameter columns to select the rows of one document.",
             [edge("$REPORT", "readsTable", "t"), node("t", "Table"),
              optional(edge("t", "inDataSource", "s"), node("s", "DataSource")),
              optional(edge("$REPORT", "hasParameter", "p"), node("p", "Parameter"), edge("p", "boundToColumn", "c"), node("c", "Column"))],
             ["s.label", "s.sourceKind", "s.database", "t.dataset", "t.tableName", "p.label", "c.columnName"],
             gate="non_empty", params={"REPORT": "ReportType"},
             gaps=[([not_edge("$REPORT", "readsTable", "*")], "report names no table"),
                   ([edge("$REPORT", "readsTable", "t"), not_edge("t", "inDataSource", "*")], "table is not attached to a data source")]),
    "CQ8": q("engineer", "Which component renders field $FIELD, in which template release?",
             "A change to a component must be checked against the fields it draws, release by release.",
             [edge("$FIELD", "inSection", "s"), node("s", "Section"), edge("s", "renderedBy", "c"), node("c", "Component"),
              edge("$FIELD", "inReport", "r"), optional(edge("r", "releasedAs", "rel"), node("rel", "TemplateRelease"))],
             ["s", "c", "rel", "rel.version", "rel.frozen"], gate="non_empty", params={"FIELD": "Field"},
             gaps=[([not_edge("$FIELD", "inSection", "*")], "the field sits in no section")],
             terms=["Field.rowStructure", "Field.members", "ReportType.kind", "ReportType.audience", "ReportType.layout"]),
    "CQ9": q("engineer", "Which reports share the field $FIELD?",
             "Fields are compared across reports by their id; a shared field means a shared meaning to keep.",
             [node("g", "Field", {"fieldId": "$FIELD.fieldId"}), edge("g", "inReport", "r"), edge("g", "inSection", "s")],
             ["r", "s"], params={"FIELD": "Field"}),
    "CQ10": q("operations", "When does report $REPORT run: cadence, day, as-of rule, calendar, timezone, and at which template version?",
              "The dispatcher reads the schedule from the release; nothing else holds it.",
              [edge("$REPORT", "releasedAs", "rel"), node("rel", "TemplateRelease"), edge("rel", "hasSchedule", "s"), node("s", "Schedule")],
              ["rel.version", "rel.frozen", "s.cadence", "s.runOn", "s.asOfRule", "s.calendar", "s.timezone"],
              gate="non_empty", params={"REPORT": "ReportType"},
              gaps=[([edge("$REPORT", "releasedAs", "rel"), not_edge("rel", "hasSchedule", "*")], "release declares no schedule")],
              terms=["ofReport", "TemplateRelease.frozenAt"]),
    "CQ11": q("compliance", "What verification thresholds and approval policy govern production runs of report $REPORT?",
              "A produced document must meet its thresholds and get the review its policy says, or it does not go out.",
              [edge("$REPORT", "releasedAs", "rel"), node("rel", "TemplateRelease"),
               optional(edge("rel", "hasVerificationPolicy", "v"), node("v", "VerificationPolicy")),
               optional(edge("rel", "hasApprovalPolicy", "a"), node("a", "ApprovalPolicy"))],
              ["rel.version", "v.goldenStaticSsimMin", "v.overflowBlocking", "v.fidelityMin", "a.sampleRate", "a.sampleMin",
               "a.fullReviewAfterRelease", "a.reviewerRole"], gate="non_empty", params={"REPORT": "ReportType"},
              gaps=[([edge("$REPORT", "releasedAs", "rel"), not_edge("rel", "hasVerificationPolicy", "*")], "no verification policy"),
                    ([edge("$REPORT", "releasedAs", "rel"), not_edge("rel", "hasApprovalPolicy", "*")], "no approval policy")]),
    "CQ12": q("operations", "What identifies one document of report $REPORT, where do the allowed values of each parameter come from, and where is the document published?",
              "The dispatcher expands a batch from the parameters' universes and publishes each document where the policy says.",
              [edge("$REPORT", "releasedAs", "rel"), node("rel", "TemplateRelease"), edge("rel", "hasParameter", "p"), node("p", "Parameter"),
               optional(edge("p", "universeQuery", "u"), node("u", "UniverseQuery")),
               optional(edge("rel", "hasPublishPolicy", "pub"), node("pub", "PublishPolicy"))],
              ["p.label", "p.definition", "u.label", "u.sql", "p.allowedValue", "p.boundBy", "pub.pathPattern", "pub.publishFormat", "pub.retentionDays"],
              gate="non_empty", params={"REPORT": "ReportType"},
              gaps=[([edge("$REPORT", "releasedAs", "rel"), edge("rel", "hasParameter", "p"),
                      node("p", "Parameter", {"allowedValue": {"exists": False}, "boundBy": {"exists": False}}), not_edge("p", "universeQuery", "*")],
                     "parameter has no universe: dispatcher cannot expand the batch")],
              terms=["hasUniverseQuery", "UniverseQuery.returnsParameter", "UniverseQuery.note"]),
    "CQ13": q("engineer", "What does the release of report $REPORT need to render: engine, ontology and library versions, fonts, files, pending assets, waivers?",
              "A frozen release pins what it renders with; a missing pin is a render that cannot be reproduced.",
              [edge("$REPORT", "releasedAs", "rel"), node("rel", "TemplateRelease")],
              ["rel.version", "rel.engineVersion", "rel.ontologyVersion", "rel.libraryVersion", "rel.font", "rel.fileHash", "rel.assetPending", "rel.waiver"],
              gate="non_empty", params={"REPORT": "ReportType"},
              gaps=[([edge("$REPORT", "releasedAs", "rel"), node("rel", "TemplateRelease", {"frozen": True, "engineVersion": {"exists": False}})], "frozen release pins no engine version"),
                    ([edge("$REPORT", "releasedAs", "rel"), node("rel", "TemplateRelease", {"frozen": True, "ontologyVersion": {"exists": False}})], "frozen release pins no ontology version"),
                    ([edge("$REPORT", "releasedAs", "rel"), node("rel", "TemplateRelease", {"assetPending": {"exists": True}})], "an asset is still pending")],
              terms=["ReportType.compiledAt", "ReportType.ontologyVersion", "ReportType.version", "TemplateRelease.repoUrl", "TemplateRelease.sha256"]),
    "CQ14": q("analyst", "Which report types exist: what is each for, where is it in its lifecycle, how often does it run, who owns it, and which template version is released?",
              "The catalogue is the first thing a reader asks for.",
              [node("r", "ReportType"), optional(edge("r", "releasedAs", "rel"), node("rel", "TemplateRelease"),
                                                 optional(edge("rel", "hasSchedule", "s"), node("s", "Schedule")))],
              ["r.reportId", "r.label", "r.lifecycleStatus", "r.kind", "r.cadence", "s.cadence", "r.owner", "rel.version", "rel.frozen", "r.purpose"],
              gate="non_empty",
              gaps=[([node("r", "ReportType", {"owner": {"exists": False}})], "report names no owner")]),
    "CQ15": q("analyst", "Which other reports show the same fields as report $REPORT, and which fields do they share?",
              "A field shared by two reports is one meaning to keep in step; the overlap is where a change propagates.",
              [edge("f", "inReport", "$REPORT"), node("f", "Field"), node("g", "Field", {"fieldId": "$f.fieldId"}), edge("g", "inReport", "o"),
               node("o", "ReportType", {"id": {"!=": "$REPORT"}})],
              ["o", "f.fieldId"], params={"REPORT": "ReportType"}),
    "CQ16": q("engineer", "Which report types use component $COMPONENT, and in which sections?",
              "Reports that share a component are affected together when it changes.",
              [edge("s", "renderedBy", "$COMPONENT"), node("s", "Section"), edge("r", "hasSection", "s"), node("r", "ReportType")],
              ["r.reportId", "s"], params={"COMPONENT": "Component"}),
    "CQ17": q("operations", "What is expected of each run of report $REPORT: delivery deadline and tolerated failures, who is alerted, and where is the run history?",
              "What a production run must achieve, and who hears when it does not, is the operating promise.",
              [edge("$REPORT", "releasedAs", "rel"), node("rel", "TemplateRelease"), edge("rel", "hasObservabilityPolicy", "o"), node("o", "ObservabilityPolicy")],
              ["rel.version", "o.deliverWithinHours", "o.maxFailureRate", "o.alertRecipient", "o.runLog"],
              gate="non_empty", params={"REPORT": "ReportType"},
              gaps=[([edge("$REPORT", "releasedAs", "rel"), not_edge("rel", "hasObservabilityPolicy", "*")], "release declares no observability policy")]),
    "CQ18": q("analyst", "Which fields does the catalogue already define: id, type, English label, definition and the other names readers use, and which reports use each?",
              "A new report reuses a field id instead of inventing a second name for the same information.",
              [node("f", "Field"), edge("f", "inReport", "r"), edge("f", "hasMeaning", "m"), node("m", "FieldMeaning", {"locale": "en"})],
              ["f.fieldId", "f.fieldType", "r", "m.label", "m.definition", "f.alias"], gate="non_empty"),
    "CQ19": q("operations", "Where is report $REPORT in its lifecycle: inception, saved to the graph, in validation, in production; and who recorded each step, when?",
              "The lifecycle log is how a reader tells a draft from a report in production, and who moved it.",
              [edge("$REPORT", "hasStatusChange", "c"), node("c", "StatusChange")],
              ["c.order", "c.lifecycleStatus", "c.changedBy", "c.at", "c.note", "$REPORT.lifecycleStatus"],
              gate="non_empty", params={"REPORT": "ReportType"},
              gaps=[([not_edge("$REPORT", "hasStatusChange", "*")], "report records no lifecycle status")]),
    "CQ20": q("compliance", "How has the definition of report $REPORT changed: each accepted revision, who accepted it, when, from which date it applies, why, and which facts it added, changed or removed?",
              "A definition that is corrected in place loses what was true when earlier documents were produced; compliance must be able to show it, with who decided and why.",
              [edge("$REPORT", "hasRevision", "v"), node("v", "Revision"), optional(edge("v", "hasChange", "c"), node("c", "Change"))],
              ["v.order", "v.at", "v.changedBy", "v.effectiveFrom", "v.reason", "c.fact", "c.changeKind", "c.previousValue", "c.newValue"],
              gate="non_empty", params={"REPORT": "ReportType"},
              gaps=[([not_edge("$REPORT", "hasRevision", "*")], "report has no accepted revision: its definition can change without a record")]),
    "CQ21": q("analyst", "Has anything about field $FIELD changed in any report: its meaning, label, type or column; what was it before, when, who accepted the change, and why?",
              "Before reusing a field or trusting a figure, an analyst needs to know whether its meaning or its column moved, and since when.",
              [node("r", "ReportType"), edge("r", "hasRevision", "v"), node("v", "Revision"), edge("v", "hasChange", "c"),
               node("c", "Change", {"fact": {"contains": "fields.$FIELD.fieldId."}})],
              ["r.reportId", "v.order", "v.at", "v.effectiveFrom", "v.changedBy", "v.reason", "c.fact", "c.changeKind", "c.previousValue", "c.newValue"],
              params={"FIELD": "Field"},
              gaps=[([edge("$FIELD", "inReport", "r"), not_edge("r", "hasRevision", "*")], "report has no accepted history: earlier changes to this field were not recorded")]),
}

#: The shapes OTO cannot hold as counts, as policy rules; each names the question it protects.
RULES = [
    {"id": "field-has-english-meaning", "kind": "policy", "severity": "blocking", "answers": "CQ1",
     "when": [node("f", "Field"), {"not_edge": ["f", "hasMeaning", "*"]}],
     "then": {"flag": "Field has no meaning in any locale"},
     "why": "A field without a meaning is a slot, not information; the English meaning is the one every reader and the catalogue rely on.", "validated_by": ""},
    {"id": "mapping-claims-a-column", "kind": "policy", "severity": "blocking", "answers": "CQ5",
     "when": [node("f", "Field", {"lineageStatus": {"in": ["proposed", "verified"]}}), {"not_edge": ["f", "sourcedFrom", "*"]}],
     "then": {"flag": "Mapping says proposed/verified but no column is attached"},
     "why": "A status without the column it claims is a mapping nobody can run.", "validated_by": ""},
    {"id": "column-in-the-reports-table", "kind": "policy", "severity": "blocking", "answers": "CQ7",
     "when": [node("f", "Field"), edge("f", "sourcedFrom", "c"), edge("c", "inTable", "t"), edge("f", "inReport", "r"), {"not_edge": ["r", "readsTable", "t"]}],
     "then": {"flag": "Field is mapped to a column outside the report's table"},
     "why": "A report reads one table; a field read from another table is a join nobody declared.", "validated_by": ""},
    {"id": "change-keeps-the-value-before", "kind": "policy", "severity": "blocking", "answers": "CQ21",
     "when": [node("c", "Change", {"changeKind": {"in": ["changed", "removed"]}, "previousValue": {"exists": False}})],
     "then": {"flag": "A changed or removed fact does not keep the value it had before"},
     "why": "The value before is the whole point of supersession: without it the history says that a fact changed but not what was true.", "validated_by": ""},
    {"id": "parameter-has-a-universe", "kind": "policy", "severity": "warn", "answers": "CQ12",
     "when": [node("p", "Parameter", {"allowedValue": {"exists": False}, "boundBy": {"exists": False}}), {"not_edge": ["p", "universeQuery", "*"]}],
     "then": {"flag": "Parameter has no universe (query, values or run-time binding): the dispatcher cannot expand a batch"},
     "why": "A batch is expanded from the parameters' allowed values; a parameter with none produces no document.", "validated_by": ""},
    {"id": "field-has-french-meaning", "kind": "policy", "severity": "warn", "answers": "CQ1",
     "when": [node("f", "Field"), edge("f", "inReport", "r"), node("r", "ReportType", {"locale": {"contains": "fr"}}),
              {"not_edge": ["f", "hasMeaning", "*"]}],
     "then": {"flag": "Field has no meaning although the report is offered in fr"},
     "why": "A report offered in French with an English-only field prints a label nobody translated.", "validated_by": ""},
    {"id": "field-is-mapped", "kind": "policy", "severity": "warn", "answers": "CQ5",
     "when": [node("f", "Field", {"lineageStatus": "unmapped"})],
     "then": {"flag": "Field not mapped to a column (blocks production release)"},
     "why": "An unmapped field renders nothing; a production release with one is incomplete.", "validated_by": ""},
    {"id": "report-reads-one-table", "kind": "policy", "severity": "warn", "answers": "CQ7",
     "when": [node("r", "ReportType"), {"not_edge": ["r", "readsTable", "*"]}],
     "then": {"flag": "Report does not name its table (blocks production release)"},
     "why": "The loader needs the one table that holds every column the report needs.", "validated_by": ""},
    {"id": "report-names-an-owner", "kind": "policy", "severity": "warn", "answers": "CQ14",
     "when": [node("r", "ReportType", {"owner": {"exists": False}})],
     "then": {"flag": "Report names no owner"},
     "why": "A report without an analyst responsible for its definition has nobody to verify its mapping.", "validated_by": ""},
    {"id": "table-has-a-source", "kind": "policy", "severity": "warn", "answers": "CQ7",
     "when": [node("t", "Table"), {"not_edge": ["t", "inDataSource", "*"]}],
     "then": {"flag": "Table is not attached to a data source"},
     "why": "A table with no source is a name the loader cannot connect to.", "validated_by": ""},
    {"id": "release-is-frozen", "kind": "policy", "severity": "warn", "answers": "CQ13",
     "when": [node("rel", "TemplateRelease", {"frozen": {"!=": True}})],
     "then": {"flag": "Template release not frozen"},
     "why": "Only a frozen release produces documents; an unfrozen one is still being built.", "validated_by": ""},
    {"id": "release-has-its-contract", "kind": "policy", "severity": "warn", "answers": "CQ10",
     "when": [node("rel", "TemplateRelease", {"frozen": True}), {"not_edge": ["rel", "hasSchedule", "*"]}],
     "then": {"flag": "Frozen release declares no schedule (blocks production)"},
     "why": "A frozen release with no schedule is a release nobody can run.", "validated_by": ""},
    {"id": "release-has-observability", "kind": "policy", "severity": "warn", "answers": "CQ17",
     "when": [node("rel", "TemplateRelease", {"frozen": True}), {"not_edge": ["rel", "hasObservabilityPolicy", "*"]}],
     "then": {"flag": "Frozen release declares no observability policy (blocks production)"},
     "why": "A run nobody watches fails silently.", "validated_by": ""},
    {"id": "report-has-a-history", "kind": "policy", "severity": "warn", "answers": "CQ20",
     "when": [node("r", "ReportType"), {"not_edge": ["r", "hasRevision", "*"]}],
     "then": {"flag": "Report has no accepted revision: its definition can change without a record (blocks production)"},
     "why": "A warning, not a violation: reports written before 2.1.0 have no history yet and must keep compiling until someone accepts their definition.", "validated_by": ""},
]

#: Constraints of report-shapes.ttl that neither a count nor a rule can hold; listed in the README.
NOT_PORTED = [
    "the frozen-release contract as one disjunction (schedule, policies, parameters, engine/ontology/library versions): ported as separate policies for the schedule and the observability policy only",
]


# ============================ rationale, manifest, readme ============================

def rationale(config, imported):
    """A question and a reason per class, drawn from the definitions' [CQ..] citations and the
    questions they name; the meta: annotations report.ttl carries are kept. A first draft: nobody
    has confirmed an entry."""
    record = {"_about": "Why each class exists and who confirmed it; ported from the definitions' [CQ] citations and the meta: "
                        "annotations of ontology/report.ttl. `validated_by` is empty until a person who knows the domain confirms the entry.",
              "classes": {}, "properties": {}}
    for name, spec in config["classes"].items():
        definition = spec.get("definition") or ""
        cited = re.findall(r"CQ(\d+)(?:-(\d+))?", definition)
        ids = []
        for a, b in cited:
            ids += ["CQ%d" % i for i in range(int(a), int(b or a) + 1)]
        ids = [i for i in dict.fromkeys(ids) if i in QUESTIONS]
        entry = dict((imported.get("classes") or {}).get(name) or {})
        if ids:
            entry.setdefault("question", QUESTIONS[ids[0]]["question"])
            entry.setdefault("why", "Needed by %s: without it the graph cannot answer %s" % (", ".join(ids), ids[0]))
        else:
            entry.setdefault("question", "Which %s does the report's template reuse from the document-template ontology?" % name)
            entry.setdefault("why", "Reused from doctemplate so the report side and the rendering side name the same thing")
        entry.setdefault("alternatives", "")
        entry.setdefault("validated_by", "")
        record["classes"][name] = entry
        spec["definition"] = re.sub(r"\s*\[CQ[^\]]*\]", "", definition).strip()
    for name, entry in (imported.get("properties") or {}).items():
        record["properties"][name] = dict(entry, validated_by=entry.get("validated_by", ""))
    return record


def readme(config, not_ported):
    classes = len(config["classes"])
    return """# Report ontology, as an OTO unit

The report ontology of the report-ontology repository (`ontology/report.ttl`, version 2.1.0),
ported by `tools/oto_port.py`: %d classes (the report's own and the three doctemplate classes it
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

## What the port holds since OTO 0.10.0

The value constraints of `report-shapes.ttl` (`sh:pattern`, `sh:minInclusive`, `sh:maxInclusive`,
`sh:minLength`) are held by the engine as `pattern`, `min_value`, `max_value` and `min_length` on
the attribute, evaluated at every gate and written back as the same SHACL.

## What the port could not hold

Constraints of `ontology/report-shapes.ttl` that are neither a count nor a pattern:

%s

They remain in the source repository's shapes; a reader with pyshacl can still apply them to the
`graph.ttl` a build writes.

## Have a report analyst validate it

Every class carries the question it exists to answer and a reason, drawn from the [CQ] citations
of the definitions; nobody has confirmed an entry (`validated_by` is empty). Sit with the analyst
who owns a report and confirm the entries that name their work.
""" % (classes, "\n".join("- " + line for line in not_ported))


def manifest(config):
    return {"name": "report", "release": 1, "domain": "reporting",
            "summary": "A report type: its meaning per locale, its sections and fields, the rules that apply, the column that supplies "
                       "each value, the runs and approvals that produced its template, its operating contract, its lifecycle and the "
                       "accepted history of its definition.",
            "extends": ["oto-core"], "namespace": RPT, "engine": ">=0.8",
            "carries": ["vocabulary", "rationale", "rules", "questions", "sample", "readme"],
            "maintainer": "Cynergis AI",
            "changelog": [{"release": 1, "at": datetime.date.today().isoformat(),
                           "note": "Ported from report-ontology 2.1.0 (ontology/report.ttl, questions/report_cq.yaml, ontology/report-shapes.ttl, "
                                   "the fund-profile-balanced fixture as the sample)."}]}


# ============================ main ============================

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--oto", default=None, help="the OTO repository (default: $OTO_HOME or ../oto)")
    ap.add_argument("--check", action="store_true", help="self-check the unit after writing it")
    args = ap.parse_args(argv)
    _oto(args.oto)
    from oto.model import ontologies as _ontologies
    from oto.reason import questions as _questions

    os.makedirs(OUT, exist_ok=True)
    with tempfile.TemporaryDirectory() as work:
        config, imported = vocabulary(work)
    # oto-core brings Document, Action and the temporal terms; the unit declares the rest
    record = rationale(config, imported)
    graph = sample(config)
    unit = types.SimpleNamespace(data=OUT)
    for filename, payload in (("ontology.config.json", config), ("ontology.rationale.json", record), ("sample.graph.json", graph),
                              ("rules.json", {"_about": "The shapes of report-shapes.ttl that are not counts, as policy rules; each names "
                                                        "the question it protects.", "rules": RULES}),
                              ("manifest.json", manifest(config))):
        with open(os.path.join(OUT, filename), "w", encoding="utf-8", newline="\n") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
            f.write("\n")
    _questions.save(unit, QUESTIONS)
    with open(os.path.join(OUT, "README.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write(readme(config, NOT_PORTED))
    print("wrote %s: %d classes, %d relations, %d attributes, %d questions, %d rules, %d sample nodes, %d sample edges"
          % (OUT, len(config["classes"]), len(config["properties"]), sum(len(v) for v in config["attributes"].values()),
             len(QUESTIONS), len(RULES), len(graph["nodes"]), len(graph["edges"])))
    if args.check:
        problems = _ontologies.self_check("report", roots=[os.path.dirname(OUT)])
        for p in problems:
            print("  -", p)
        print("self-check:", "clean" if not problems else "%d problem(s)" % len(problems))
        return 1 if problems else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
