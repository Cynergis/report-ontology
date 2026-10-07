"""Port the flow ontology to OTO: two units written under oto/.

  oto/flow         the `flow:` vocabulary of ontology/ontology.ttl (how work is executed: steps,
                   checks, transitions, artifacts, tests), its 17 competency questions in the
                   pattern language, the rules that derive what the SPARQL joined on the fly, and
                   the 5 task types of questions/competency_questions.yaml as briefs.
  fixtures/pdf-to-template/graph.json
                   the pdf-to-template flow instance as a project graph on flow and report: what
                   tools/kgctl.py builds from flow.json, bindings.ttl and derive_tests.rq. A real
                   flow with its real gaps is a project's facts, not an ontology's sample.

    python tools/flow_port.py --flow-root ../pdf-to-template --check

The flow instance is read from --flow-root (or FLOW_ROOT), like kgctl. Nothing here calls an LLM.
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
OUT_FLOW = os.path.join(HERE, "oto", "flow")
OUT_GRAPH = os.path.join(HERE, "fixtures", "pdf-to-template", "graph.json")
FLOW = "https://cynergis.ai/ont/flow#"
DT = "https://cynergis.ai/ont/doctemplate#"
RPT = "https://cynergis.ai/ont/report#"
STEP_KINDS = {"deterministic": "DeterministicStep", "ocr": "OcrStep", "claude": "ClaudeStep", "human": "HumanStep", "terminal": "TerminalStep"}
#: The steps a builder implements: what the implement-step and write-tests briefs are about.
IMPLEMENTABLE = "DeterministicStep|OcrStep|ClaudeStep"
#: Attributes the original declares once per value: lists here.
LISTS = {"readsStatePath", "writesOnly", "decisionOption", "requiredField", "carries", "concerns"}

sys.path.insert(0, os.path.join(HERE, "tools"))
from oto_port import q, edge, node, not_edge, optional, _oto  # noqa: E402


# ============================ the vocabularies ============================

def _subgraph(whole, prefix):
    """The triples about one namespace's terms, blank-node closures included."""
    from rdflib import Graph, BNode
    out = Graph()
    for p, ns in whole.namespaces():
        out.bind(p, ns)
    for s, p, o in whole:
        if str(s).startswith(prefix) or str(s) == prefix.rstrip("#"):
            out.add((s, p, o))
    changed = True
    while changed:
        changed = False
        for s, p, o in list(out):
            if isinstance(o, BNode):
                for pp, oo in whole.predicate_objects(o):
                    if (o, pp, oo) not in out:
                        out.add((o, pp, oo))
                        changed = True
    return out


def _import(graph, work, name):
    from oto.model import rdf_import
    path = os.path.join(work, name + ".ttl")
    graph.serialize(path, format="turtle")
    classes, properties, notes = rdf_import.read([path])
    return classes, properties, rdf_import.read.attributes, rdf_import.read.namespaces, rdf_import.read.rationale, notes


def _rename(classes, properties, attributes, namespaces, class_names, relation_names):
    def kinds(sig):
        return "|".join(class_names.get(x, x) for x in (sig or "").split("|") if x)
    for old, new in class_names.items():
        classes[new] = classes.pop(old)
        if old in attributes:
            attributes[new] = attributes.pop(old)
    for spec in classes.values():
        if spec.get("subclass_of"):
            spec["subclass_of"] = [class_names.get(x, x) for x in spec["subclass_of"]]
    for old, new in relation_names.items():
        properties[new] = properties.pop(old)
    for spec in properties.values():
        spec["domain"], spec["range"] = kinds(spec.get("domain")), kinds(spec.get("range"))
    for ns in namespaces.values():
        ns["terms"] = [class_names.get(t, relation_names.get(t, t)) for t in ns.get("terms") or []]


def flow_vocabulary(work):
    from rdflib import Graph
    whole = Graph()
    whole.parse(os.path.join(HERE, "ontology", "ontology.ttl"), format="turtle")
    classes, properties, attributes, namespaces, rationale, notes = _import(_subgraph(whole, FLOW), work, "flow")
    for note in notes:
        print("  importer:", note)
    # three names the report ontology uses for other things (a report's Field and Parameter, a
    # release's producedBy); a project composes both, so the flow's are renamed, new IRIs and all
    _rename(classes, properties, attributes, namespaces, {"Field": "ArtifactField", "Parameter": "ConfigParameter"},
            {"hasField": "hasArtifactField", "producedBy": "outputOf"})
    # the prompt and the review page are selected on any step by FL8: declared on Step, not the kind
    for name in ("promptRef", "reviewPage"):
        for kind in ("ClaudeStep", "HumanStep"):
            spec = (attributes.get(kind) or {}).pop(name, None)
            if spec is not None:
                attributes.setdefault("Step", {})[name] = spec
    # `carries` and `concerns` range over classes (owl:Class): a list of concept names on the node
    properties.pop("carries", None)
    properties.pop("concerns", None)
    attributes.setdefault("Artifact", {})["carries"] = {
        "type": "list", "label": "carries",
        "definition": "The domain concepts this artifact holds, by class name: what the file is about, so a step's inputs and outputs are read as domain things, not paths."}
    attributes.setdefault("Invariant", {})["concerns"] = {
        "type": "list", "label": "concerns", "definition": "The domain concepts the invariant constrains, by class name."}
    for kind, declared in attributes.items():
        for name, spec in declared.items():
            if name in LISTS:
                spec["type"] = "list"
    # what the SPARQL joined with UNIONs, as relations the rules derive
    properties["dependsOn"] = {
        "domain": "Step", "range": "ConfigParameter", "inverse": "dependedOnBy", "label": "depends on",
        "definition": "A configuration parameter the step's behaviour depends on: compared to by one of its checks, read by "
                      "a guard of one of its transitions, or used by its action. Derived; never stated."}
    properties["affectedBy"] = {
        "domain": "Check|Transition|Step|TestObligation", "range": "ConfigParameter", "inverse": "affects", "label": "affected by",
        "definition": "What a change of the parameter reaches: the check compared to it, the transition whose guard reads it, "
                      "the step whose action uses it, the test of a check compared to it. Derived; never stated."}
    properties["readBy"] = {
        "domain": "Artifact", "range": "Step", "inverse": "consumesArtifact", "label": "read by",
        "definition": "A step that reads the artifact, required or optional. Derived from reads and readsOptional, so one "
                      "question covers both."}
    config = {
        "_about": "The flow ontology as an OTO unit, ported from the flow: terms of ontology/ontology.ttl by tools/flow_port.py: "
                  "how work is executed. Steps with typed executors, gated by checks, connected by guarded transitions, "
                  "exchanging artifacts; tests derived from checks, transitions and invariants. Every term keeps its IRI "
                  "under https://cynergis.ai/ont/flow#. A relation is {domain, range, inverse, definition}. Use A|B for a union.",
        "_summary": "Executable process graphs: steps with typed executors (script, OCR, Claude, human, terminal), gated by "
                    "checks against metrics and parameters, connected by guarded transitions with effects, exchanging "
                    "artifacts with fields; invariants and the tests derived from them. The briefs an agent reads before "
                    "implementing or testing a step, building the engine, or changing a parameter or an artifact.",
        "name": "Flow", "ontology_version": 1, "strict_domains": False, "languages": ["en"],
        "classes": classes, "properties": properties, "attributes": attributes, "namespaces": namespaces,
    }
    return config, rationale


# ============================ the flow instance ============================

def nid(kind, *parts):
    local = ".".join(re.sub(r"[^a-z0-9_]+", "-", str(p).lower()).strip("-.") for p in parts)
    return "%s.%s" % (kind, local)


def _stamp(source):
    return {"status": "current", "as_of": "2026-10-07", "valid_from": "2026-10-07", "source_doc": source, "sources": [source],
            "aliases": [], "tags": []}


def _flatten(d, prefix=""):
    for k, v in d.items():
        key = prefix + k
        if isinstance(v, dict):
            yield from _flatten(v, key + ".")
        else:
            yield key, v


def sample(flow_root):
    """The pdf-to-template flow as OTO nodes and edges: what kgctl build makes of flow.json, bindings.ttl and
    derive_tests.rq, with the same ids read the OTO way (`step.b10_verify`, `check.b10_verify.fidelity`)."""
    flow = json.load(open(os.path.join(flow_root, "flow", "flow.json"), encoding="utf-8"))
    src = "flow.json"
    nodes, edges = {}, []

    def add(node_id, kind, label, summary="", **attributes):
        attributes = {k: v for k, v in attributes.items() if v not in (None, "", [])}
        nodes[node_id] = dict(id=node_id, type=kind, label=label, summary=summary or label, attributes=attributes, **_stamp(src))
        return node_id

    def link(a, rel, b):
        edges.append({"from": a, "rel": rel, "to": b})

    params = dict(_flatten(flow["config"]))
    known = set(params)

    def param(name):
        cands = [p for p in known if name == p or name.startswith(p + ".")]
        name = max(cands, key=len) if cands else name
        pid = nid("param", name)
        if pid not in nodes:
            add(pid, "ConfigParameter", name, "Configuration parameter %s." % name, paramName=name)
        return pid

    for name, value in params.items():
        add(nid("param", name), "ConfigParameter", name, "Configuration parameter %s." % name, paramName=name,
            value=json.dumps(value) if isinstance(value, (list, dict)) else str(value), sourceRef="flow.json#/config/" + name.replace(".", "/"))

    flow_id = add(nid("flow", flow["id"]), "Flow", flow["title"], flow.get("description") or flow["title"], value=flow["version"])
    for phase in flow["phases"]:
        pid = add(nid("phase", phase["id"]), "Phase", phase["title"])
        link(pid, "entrypoint", nid("step", flow["entrypoints"][phase["id"]]))
        for step in phase["nodes"]:
            link(nid("step", step), "inPhase", pid)

    def metric(step_id, name):
        mid = nid("metric", step_id, name)
        if mid not in nodes:
            add(mid, "Metric", name, "Metric %s of %s." % (name, step_id), metricName=name)
        return mid

    def config_refs(text):
        return set(re.findall(r"config\.([A-Za-z_][\w\.]*)", text or ""))

    step_ids = {n["id"] for n in flow["nodes"]}
    for n in flow["nodes"]:
        sid = nid("step", n["id"])
        act = n.get("action") or {}
        attrs = dict(stepId=n["id"], sourceRef="flow.json#/nodes/" + n["id"], usesOcr=bool(n.get("uses_ocr")) or None, foreach=n.get("foreach"))
        if n["type"] != "terminal":
            attrs["isImplemented"] = bool(act.get("implemented"))
        if act.get("kind") == "command":
            attrs["command"] = act["command"]
        if act.get("kind") == "claude":
            attrs.update(promptRef=act["prompt_ref"], promptVersion=act["prompt_version"], outputSchema=act.get("output_schema"),
                         writesOnly=list(act.get("writes_only") or []))
        if act.get("kind") == "human_review":
            attrs.update(reviewPage=act["review_page"], decisionOption=list(act["decision_options"]), requiredField=list(act["required_fields"]))
        if n.get("retry"):
            attrs["retryMax"] = n["retry"]["max_attempts"]
        add(sid, STEP_KINDS[n["type"]], n["name"], n["description"], **attrs)
        link(flow_id, "hasStep", sid)
        optional_inputs = set(n.get("inputs_optional") or [])
        for a in n.get("inputs") or []:
            link(sid, "readsOptional" if a in optional_inputs else "reads", nid("artifact", a))
        for a in n.get("outputs") or []:
            link(sid, "writes", nid("artifact", a))
        for m in n.get("metrics") or []:
            link(sid, "records", metric(n["id"], m))
        for oname, odesc in (n.get("outcomes") or {}).items():
            oid = add(nid("outcome", n["id"], oname), "Outcome", oname, odesc, outcomeName=oname)
            link(sid, "hasOutcome", oid)
        if act.get("kind") == "command":
            script = act["command"].split()[1]
            impl = nid("impl", script.replace("{skill_dir}/", ""))
            add(impl, "Implementation", script.replace("{skill_dir}/", ""), "The script that executes %s." % n["id"],
                path=script, exists=os.path.exists(os.path.join(flow_root, script.replace("{skill_dir}/", ""))))
            link(sid, "implementedBy", impl)
        for ref in sorted(config_refs(json.dumps(act))):
            link(sid, "usesParameter", param(ref))
        for v in n.get("validations") or []:
            cid = nid("check", n["id"], v["id"])
            blocking = str(v["blocking"]).lower() if isinstance(v["blocking"], bool) else v["blocking"]
            state_paths = []
            if v["kind"] == "metric":
                state_paths = ["state." + sp for sp in re.findall(r"state\.([\w\.]+)", v["check"] + " " + str(v["blocking"]))]
            add(cid, "Check", v["id"], v["description"], checkId=v["id"], checkKind=v["kind"], expression=v["check"],
                blocking=blocking, readsStatePath=sorted(set(state_paths)))
            link(sid, "hasCheck", cid)
            link(cid, "onFail", nid("outcome", n["id"], v["on_fail"]))
            if v["kind"] == "metric":
                own = re.sub(r"state\.nodes\.\w+\.metrics\.\w+", "", v["check"])
                for m in sorted(set(re.findall(r"metrics\.(\w+)", own))):
                    link(cid, "measures", metric(n["id"], m))
                for ref in sorted(config_refs(v["check"])):
                    link(cid, "comparedTo", param(ref))

    for a_id, a in flow["artifacts"].items():
        aid = nid("artifact", a_id)
        add(aid, "Artifact", a_id, a["description"], path=a["path"], format=a["format"], optional=bool(a.get("optional")) or None,
            outputSchema=a.get("schema"), sourceRef="flow.json#/artifacts/" + a_id)
        if a["produced_by"] in step_ids:
            link(aid, "outputOf", nid("step", a["produced_by"]))
        for i, fp in enumerate(a.get("key_fields") or []):
            fid = add(nid("field", a_id, i), "ArtifactField", fp, "Field %s of %s." % (fp, a_id), fieldPath=fp)
            link(aid, "hasArtifactField", fid)

    for e in flow["edges"]:
        tid = nid("transition", e["id"])
        guard = e.get("guard")
        state_paths = []
        if guard:
            state_paths = ["state." + sp for sp in re.findall(r"state\.([\w\.]+)", guard)]
            state_paths += ["state.nodes.%s.metrics.%s" % (e["from"], m) for m in re.findall(r"(?<![\w.])metrics\.(\w+)", guard)]
        add(tid, "Transition", "%s: %s on %s" % (e["id"], e["from"], e["on"]), e.get("description") or "",
            priority=e.get("priority", 0), sourceRef="flow.json#/edges/" + e["id"], guard=guard,
            toDynamic=e["to"] if e["to"].startswith("$") else None, readsStatePath=sorted(set(state_paths)))
        link(tid, "from", nid("step", e["from"]))
        link(tid, "onOutcome", nid("outcome", e["from"], e["on"]))
        if not e["to"].startswith("$"):
            link(tid, "to", nid("step", e["to"]))
        for ref in sorted(config_refs(guard or "")):
            link(tid, "usesParameter", param(ref))
        for i, eff in enumerate(e.get("effects") or []):
            fid = add(nid("effect", e["id"], i), "Effect", "%s %s" % (eff["op"], eff["path"]), "", op=eff["op"], statePath="state." + eff["path"])
            link(tid, "hasEffect", fid)

    # bindings.ttl: what each artifact carries, and the invariants
    from rdflib import Graph, URIRef, RDF
    b = Graph()
    b.parse(os.path.join(HERE, "ontology", "bindings.ttl"), format="turtle")
    F = lambda t: URIRef(FLOW + t)  # noqa: E731
    for art, concept in sorted(b.subject_objects(F("carries"))):
        aid = nid("artifact", str(art).rsplit("/", 1)[-1])
        if aid in nodes:
            nodes[aid]["attributes"].setdefault("carries", []).append(str(concept).split("#")[-1])
    for inv in sorted(b.subjects(RDF.type, F("Invariant"))):
        iid = nid("invariant", str(inv).rsplit("/", 1)[-1])
        statement = str(b.value(inv, F("statement")))
        add(iid, "Invariant", str(inv).rsplit("/", 1)[-1], statement, statement=statement,
            concerns=sorted(str(c).split("#")[-1] for c in b.objects(inv, F("concerns"))))
        nodes[iid]["source_doc"] = nodes[iid]["sources"][0] = "bindings.ttl"
        for check in sorted(b.objects(inv, F("enforcedBy"))):
            parts = str(check).split("/step/")[1].split("/check/")
            link(iid, "enforcedBy", nid("check", parts[0], parts[1]))
    for n_ in nodes.values():
        if "carries" in n_["attributes"]:
            n_["attributes"]["carries"] = sorted(set(n_["attributes"]["carries"]))

    # derive_tests.rq, mechanically: a pass and a fail case per check, a route per transition,
    # a property per invariant on each step whose check enforces it
    by_id = nodes
    outcome_name = lambda oid: by_id[oid]["attributes"]["outcomeName"]  # noqa: E731
    for e_ in list(edges):
        if e_["rel"] == "hasCheck":
            sid, cid = e_["from"], e_["to"]
            check = by_id[cid]["attributes"]
            on_fail = next(x["to"] for x in edges if x["from"] == cid and x["rel"] == "onFail")
            for kind, text in (("pass_case", "Fixture where '%s' holds (%s) -> check passes" % (check["checkId"], check["expression"])),
                               ("fail_case", "Fixture where '%s' is violated -> check fails and the step outcome is '%s'"
                                % (check["checkId"], outcome_name(on_fail)))):
                tid = add(nid("test", cid.split(".", 1)[1], kind.split("_")[0]), "TestObligation", text, text, obligationKind=kind)
                nodes[tid]["source_doc"] = nodes[tid]["sources"][0] = "derive_tests.rq"
                link(tid, "tests", cid)
                link(tid, "forStep", sid)
    for t_id, t_node in [(k, v) for k, v in nodes.items() if v["type"] == "Transition"]:
        sid = next(x["to"] for x in edges if x["from"] == t_id and x["rel"] == "from")
        oid = next(x["to"] for x in edges if x["from"] == t_id and x["rel"] == "onOutcome")
        to = next((x["to"] for x in edges if x["from"] == t_id and x["rel"] == "to"), None)
        target = by_id[to]["attributes"]["stepId"] if to else t_node["attributes"].get("toDynamic")
        guard = t_node["attributes"].get("guard")
        text = "Outcome '%s'%s -> engine moves to %s" % (outcome_name(oid), " with guard [%s] true" % guard if guard else "", target)
        tid = add(nid("test", t_id.split(".", 1)[1], "route"), "TestObligation", text, text, obligationKind="route")
        nodes[tid]["source_doc"] = nodes[tid]["sources"][0] = "derive_tests.rq"
        link(tid, "tests", t_id)
        link(tid, "forStep", sid)
    for inv_id, inv in [(k, v) for k, v in nodes.items() if v["type"] == "Invariant"]:
        for check in [x["to"] for x in edges if x["from"] == inv_id and x["rel"] == "enforcedBy"]:
            sid = next(x["from"] for x in edges if x["to"] == check and x["rel"] == "hasCheck")
            text = "Property test: " + inv["attributes"]["statement"]
            tid = add(nid("test", inv_id.split(".", 1)[1], by_id[sid]["attributes"]["stepId"]), "TestObligation", text, text, obligationKind="property")
            nodes[tid]["source_doc"] = nodes[tid]["sources"][0] = "derive_tests.rq"
            link(tid, "tests", inv_id)
            link(tid, "forStep", sid)
    seen, unique = set(), []
    for e_ in edges:
        key = (e_["from"], e_["rel"], e_["to"])
        if key not in seen:
            seen.add(key)
            unique.append(e_)
    return {"_about": "The pdf-to-template flow (flow.json %s) as a project graph on the flow and report vocabularies: what "
                      "tools/kgctl.py builds from flow.json, bindings.ttl and derive_tests.rq. Rebuilt by tools/flow_port.py; "
                      "never edited by hand." % flow["version"],
            "nodes": list(nodes.values()), "edges": unique}


# ============================ the questions ============================

STEP = {"STEP": "Step"}
IMPL = {"STEP": IMPLEMENTABLE}
QUESTIONS = {
    "FL1": q("a builder", "What is step $STEP for, and what kind of executor runs it?",
             "CQ01. The first fact an implementer needs: the step's purpose and whether it is a script, an OCR run, Claude or a person.",
             [node("$STEP", "Step")], ["$STEP.stepId", "$STEP.label", "$STEP.type", "$STEP.usesOcr", "$STEP.foreach", "$STEP.retryMax", "$STEP.sourceRef"],
             gate="non_empty", params=STEP),
    "FL2": q("a builder", "Which artifacts does $STEP read and write, where, in what format?",
             "CQ02. The step's contract with its neighbours: the files it takes and leaves, by path and format.",
             [edge("$STEP", "reads|readsOptional|writes", "a"), node("a", "Artifact")], ["a.label", "a.path", "a.format", "a.optional", "a.outputSchema", "a.sourceRef"],
             gate="non_empty", params=IMPL, gaps=([not_edge("$STEP", "reads|readsOptional|writes", "*")], "the step reads and writes nothing on record")),
    "FL3": q("a builder", "What structure (fields) must each JSON artifact $STEP writes have?",
             "CQ03. A JSON output without a field specification cannot be written to a contract; the gap names the artifact.",
             [edge("$STEP", "writes", "a"), node("a", "Artifact"), edge("a", "hasArtifactField", "f"), node("f", "ArtifactField")], ["a.label", "f.fieldPath"], gate="no_gaps", params=STEP,
             gaps=([edge("$STEP", "writes", "a"), node("a", "Artifact", {"format": {"in": ["json", "json-schema"]}}), not_edge("a", "hasArtifactField", "*")],
                   "JSON output has no field specification")),
    "FL4": q("a builder", "Which checks gate $STEP: what does each measure, against which threshold, and what happens on failure?",
             "CQ04. The checks are the step's acceptance; a metric check that measures no metric cannot be implemented.",
             [edge("$STEP", "hasCheck", "c"), node("c", "Check"), edge("c", "onFail", "o"), node("o", "Outcome"),
              optional(edge("c", "measures", "m"), node("m", "Metric")), optional(edge("c", "comparedTo", "p"), node("p", "ConfigParameter"))],
             ["c.checkId", "c.checkKind", "c.expression", "m.metricName", "p.paramName", "p.value", "c.blocking", "c.readsStatePath", "o.outcomeName"],
             gate="no_gaps", params=STEP,
             gaps=([edge("$STEP", "hasCheck", "c"), node("c", "Check", {"checkKind": "metric"}), not_edge("c", "measures", "*")], "metric check measures no metric")),
    "FL5": q("a builder", "Which metrics must $STEP record in state, and are all checked metrics recorded?",
             "CQ05. A check that reads a metric the step never records can never pass.",
             [edge("$STEP", "records", "m"), node("m", "Metric")], ["m.metricName"], gate="no_gaps", params=STEP,
             gaps=([edge("$STEP", "hasCheck", "c"), edge("c", "measures", "m"), not_edge("$STEP", "records", "m")],
                   "a check reads a metric the step does not declare as recorded")),
    "FL6": q("a builder", "Which configuration parameters does $STEP depend on, and their current values?",
             "CQ06. Thresholds, limits and seeds live in config; the step reads them, never owns them. A parameter without a value is a gap.",
             [edge("$STEP", "dependsOn", "p"), node("p", "ConfigParameter")], ["p.paramName", "p.value", "p.sourceRef"], gate="no_gaps", params=STEP,
             gaps=([edge("$STEP", "dependsOn", "p"), node("p", "ConfigParameter", {"value": {"exists": False}})], "parameter referenced but has no value in config")),
    "FL7": q("a builder", "Which domain invariants does $STEP enforce?",
             "CQ07. The statements that must always hold, enforced by this step's checks; the property tests come from them.",
             [edge("$STEP", "hasCheck", "c"), node("c", "Check"), edge("inv", "enforcedBy", "c"), node("inv", "Invariant")],
             ["inv.label", "inv.statement", "inv.concerns", "c.checkId"],
             gate="any", params=STEP),
    "FL8": q("a builder", "How is $STEP executed (command, Claude prompt, or human review), and does an implementation exist?",
             "CQ08. A step with no execution spec cannot be run; one marked implemented whose script is missing is a lie the graph must not carry.",
             [node("$STEP", "Step"), optional(edge("$STEP", "implementedBy", "i"), node("i", "Implementation"))],
             ["$STEP.command", "$STEP.promptRef", "$STEP.reviewPage", "$STEP.isImplemented", "i.path", "i.exists"], gate="no_gaps", params=STEP, terms=["TerminalStep"],
             gaps=([node("$STEP", "DeterministicStep|OcrStep|ClaudeStep|HumanStep",
                         {"command": {"exists": False}, "promptRef": {"exists": False}, "reviewPage": {"exists": False}})],
                   "no execution spec (command, prompt or review page)")),
    "FL9": q("a builder", "Which later steps consume what $STEP writes?",
             "CQ09. Field names must match on both sides; the consumers are who breaks when the output changes.",
             [edge("$STEP", "writes", "a"), edge("a", "readBy", "s2"), node("s2", "Step", {"id": {"!=": "$STEP"}})], ["a.label", "s2.stepId"],
             gate="any", params=STEP),
    "FL10": q("a builder", "Which domain concepts do the inputs and outputs of $STEP carry?",
              "CQ10. An artifact is a domain thing, not a path; one bound to no concept is a gap. The concept's meaning is its class's definition.",
              [edge("$STEP", "reads|readsOptional|writes", "a"), node("a", "Artifact", {"carries": {"exists": True}})], ["a.label", "a.carries"],
              gate="no_gaps", params=STEP,
              gaps=([edge("$STEP", "reads|readsOptional|writes", "a"), node("a", "Artifact", {"carries": {"exists": False}})], "artifact not bound to any domain concept")),
    "FL11": q("a builder", "For each outcome of $STEP, which transition fires, under which guard, and where does it go?",
              "CQ11. Outcomes are the only thing transitions branch on; an outcome with no transition strands the run.",
              [edge("t", "from", "$STEP"), node("t", "Transition"), edge("t", "onOutcome", "o"), node("o", "Outcome"), optional(edge("t", "to", "s2"), node("s2", "Step"))],
              ["o.outcomeName", "t.guard", "t.priority", "s2.stepId", "t.toDynamic", "t.sourceRef"], gate="no_gaps", params=STEP,
              gaps=([edge("$STEP", "hasOutcome", "o"), not_edge("*", "onOutcome", "o")], "outcome has no transition")),
    "FL12": q("a test writer", "Which tests must exist for $STEP, derived mechanically from its checks, transitions and invariants?",
              "CQ12. A pass and a fail case per check, a route per transition, a property per invariant: the tests exist before the implementation.",
              [edge("t", "forStep", "$STEP"), node("t", "TestObligation")], ["t.obligationKind", "t.label"], gate="non_empty", params=IMPL,
              gaps=([not_edge("*", "forStep", "$STEP")], "no test obligation: the step has no check, transition or invariant")),
    "FL13": q("an engine builder", "Which state paths and config parameters do transition guards read?",
              "CQ13. The runner must expose exactly these paths to guards.",
              [node("t", "Transition", {"guard": {"exists": True}}), optional(edge("t", "usesParameter", "p"), node("p", "ConfigParameter"))],
              ["t.label", "t.guard", "t.readsStatePath", "p.paramName"], gate="non_empty"),
    "FL14": q("an engine builder", "What must every human step record before the flow can continue?",
              "CQ14. The decision options and the required fields: what the runner waits for.",
              [node("s", "HumanStep")], ["s.stepId", "s.decisionOption", "s.requiredField", "s.reviewPage"], gate="non_empty"),
    "FL15": q("an engine builder", "Which steps have no implementation yet, and which claim one whose script is missing?",
              "CQ15. The honest state of the build: unimplemented is fine, implemented-but-missing is not.",
              [node("s", IMPLEMENTABLE, {"isImplemented": False})], ["s.stepId", "s.type"], gate="no_gaps",
              gaps=([node("s", "Step", {"isImplemented": True}), edge("s", "implementedBy", "i"), node("i", "Implementation", {"exists": False})],
                    "marked implemented but script missing")),
    "FL16": q("anyone changing config", "If parameter $PARAM changes, which checks, transitions, steps and tests are affected?",
              "CQ16. The blast radius of a threshold change, read from the graph before the change.",
              [edge("x", "affectedBy", "$PARAM")], ["x.label", "x.type"], gate="any", params={"PARAM": "ConfigParameter"}),
    "FL17": q("anyone changing an artifact", "If the structure of $ARTIFACT changes, who writes it and who reads it?",
              "CQ17. Writers and readers are who must change together.",
              [edge("s", "reads|readsOptional|writes", "$ARTIFACT")], ["s.stepId", "s.type"], gate="any", params={"ARTIFACT": "Artifact"}),
    "FL18": q("a builder", "Which phase is $STEP in, and which step does the phase start at?",
              "The phase is how a run is scoped; the entrypoint is where it begins.",
              [edge("$STEP", "inPhase", "ph"), node("ph", "Phase"), optional(edge("ph", "entrypoint", "e"), node("e", "Step")), optional(edge("fl", "hasStep", "$STEP"), node("fl", "Flow"))],
              ["ph.label", "e.stepId", "fl.label", "fl.value"], gate="any", params=STEP),
    "FL19": q("an engine builder", "Which effects does transition $TRANSITION apply to run state, and which artifact produced by which step does a step read?",
              "Effects and provenance: what a transition changes, and where an artifact comes from.",
              [node("$TRANSITION", "Transition"), optional(edge("$TRANSITION", "hasEffect", "ef"), node("ef", "Effect")),
               optional(edge("a", "outputOf", "s"), node("a", "Artifact"), node("s", "Step"))],
              ["ef.op", "ef.statePath", "a.label", "s.stepId"], gate="any", params={"TRANSITION": "Transition"}),
    "FL20": q("a builder", "Which prompt, at which version, with which output schema and write scope does Claude step $CLAUDE run with?",
              "A Claude step is a versioned prompt with a required output schema and a write scope; the cache key and the scope check come from these.",
              [node("$CLAUDE", "ClaudeStep")], ["$CLAUDE.promptRef", "$CLAUDE.promptVersion", "$CLAUDE.outputSchema", "$CLAUDE.writesOnly"],
              gate="non_empty", params={"CLAUDE": "ClaudeStep"}),
    "FL21": q("a test writer", "What does test obligation $TEST exercise: which check, transition or invariant?",
              "A test obligation names what it proves; the test writer cites it.",
              [edge("$TEST", "tests", "x")], ["x.label", "x.type", "$TEST.obligationKind"], gate="non_empty", params={"TEST": "TestObligation"}),
}

RULES = [
    {"id": "step-depends-on-checked-parameter", "kind": "derive",
     "when": [edge("s", "hasCheck", "c"), edge("c", "comparedTo", "p")], "then": {"edge": ["s", "dependsOn", "p"]},
     "why": "A step depends on every parameter one of its checks compares to (CQ06).", "validated_by": ""},
    {"id": "step-depends-on-guarded-parameter", "kind": "derive",
     "when": [edge("t", "from", "s"), edge("t", "usesParameter", "p")], "then": {"edge": ["s", "dependsOn", "p"]},
     "why": "A step depends on every parameter a guard of one of its transitions reads (CQ06).", "validated_by": ""},
    {"id": "step-depends-on-used-parameter", "kind": "derive",
     "when": [node("s", "Step"), edge("s", "usesParameter", "p")], "then": {"edge": ["s", "dependsOn", "p"]},
     "why": "A step depends on every parameter its action uses (CQ06).", "validated_by": ""},
    {"id": "check-affected-by-parameter", "kind": "derive",
     "when": [edge("c", "comparedTo", "p")], "then": {"edge": ["c", "affectedBy", "p"]},
     "why": "A check compared to a parameter changes meaning when the parameter does (CQ16).", "validated_by": ""},
    {"id": "transition-affected-by-parameter", "kind": "derive",
     "when": [node("t", "Transition"), edge("t", "usesParameter", "p")], "then": {"edge": ["t", "affectedBy", "p"]},
     "why": "A transition whose guard reads a parameter routes differently when it changes (CQ16).", "validated_by": ""},
    {"id": "step-affected-by-parameter", "kind": "derive",
     "when": [node("s", "Step"), edge("s", "usesParameter", "p")], "then": {"edge": ["s", "affectedBy", "p"]},
     "why": "A step whose action uses a parameter behaves differently when it changes (CQ16).", "validated_by": ""},
    {"id": "test-affected-by-parameter", "kind": "derive",
     "when": [edge("t", "tests", "c"), edge("c", "comparedTo", "p")], "then": {"edge": ["t", "affectedBy", "p"]},
     "why": "A test of a check compared to a parameter must be revisited when the parameter changes (CQ16).", "validated_by": ""},
    {"id": "artifact-read-by-step", "kind": "derive",
     "when": [edge("s", "reads|readsOptional", "a")], "then": {"edge": ["a", "readBy", "s"]},
     "why": "One relation for the consumers of an artifact, required or optional (CQ09).", "validated_by": ""},
    {"id": "implemented-step-has-its-script", "kind": "policy", "severity": "blocking",
     "when": [node("s", "Step", {"isImplemented": True}), edge("s", "implementedBy", "i"), node("i", "Implementation", {"exists": False})],
     "then": {"flag": "a step marked implemented has no script on disk"},
     "why": "The graph must not say a step is done when its script is missing; the build would carry a lie.", "validated_by": "", "answers": "FL15"},
    {"id": "outcome-has-a-transition", "kind": "policy", "severity": "warn",
     "when": [edge("s", "hasOutcome", "o"), not_edge("*", "onOutcome", "o"), node("s", "DeterministicStep|OcrStep|ClaudeStep|HumanStep")],
     "then": {"flag": "an outcome of a non-terminal step has no transition: a run that ends there is stranded"},
     "why": "Outcomes are the only thing transitions branch on.", "validated_by": "", "answers": "FL11"},
]

BRIEFS = {
    "implement-step": {"description": "An agent is about to write the script for one flow step (e.g. verify.py for B10_verify).",
                       "params": {"STEP": IMPLEMENTABLE},
                       "required": ["FL1", "FL2", "FL3", "FL4", "FL5", "FL6", "FL8", "FL10", "FL11"], "optional": ["FL7", "FL9", "FL18"]},
    "write-tests": {"description": "An agent writes the tests a step's implementation must pass, before the implementation exists.",
                    "params": {"STEP": IMPLEMENTABLE}, "required": ["FL4", "FL11", "FL12"], "optional": ["FL7", "FL3"]},
    "build-engine": {"description": "An agent writes the runner that executes the flow graph (state, guards, effects, human pauses).",
                     "params": {}, "required": ["FL13", "FL14", "FL15"], "optional": []},
    "impact-parameter": {"description": "A threshold or config value is about to change: what is affected?",
                         "params": {"PARAM": "ConfigParameter"}, "required": ["FL16"], "optional": []},
    "impact-artifact": {"description": "An artifact's structure is about to change: who reads it, who writes it?",
                        "params": {"ARTIFACT": "Artifact"}, "required": ["FL17"], "optional": []},
}


# ============================ the flow unit's own sample ============================

def flow_sample():
    """A three-step flow, invented, so the generic unit builds and answers on its own: a script that
    writes a JSON artifact with fields, a check against a parameter, a human review, an end."""
    src = "sample"
    nodes, edges = [], []

    def n(node_id, kind, label, summary="", **attributes):
        attributes = {k: v for k, v in attributes.items() if v not in (None, "", [])}
        nodes.append(dict(id=node_id, type=kind, label=label, summary=summary or label, attributes=attributes, **_stamp(src)))
        return node_id

    def e(a, rel, b):
        edges.append({"from": a, "rel": rel, "to": b})

    n("flow.sample", "Flow", "Sample flow", "Extract, check, review, done.", value="1.0.0")
    n("phase.build", "Phase", "Build")
    n("param.min_rows", "ConfigParameter", "min_rows", "The smallest table the extractor may accept.", paramName="min_rows", value="3", sourceRef="flow.json#/config/min_rows")
    n("step.s1_extract", "DeterministicStep", "Extract the table", "Reads the source and writes the rows as JSON.", stepId="S1_extract",
      isImplemented=True, command="python {skill_dir}/steps/extract.py --run-dir {run_dir}", sourceRef="flow.json#/nodes/S1_extract")
    n("impl.steps-extract-py", "Implementation", "steps/extract.py", "The extractor.", path="{skill_dir}/steps/extract.py", exists=True)
    n("step.s2_review", "HumanStep", "Review the rows", "A person confirms the rows.", stepId="S2_review", isImplemented=False,
      reviewPage="{run_dir}/review/S2_review.html", decisionOption=["approve", "reject"], requiredField=["reviewer", "decision"], sourceRef="flow.json#/nodes/S2_review")
    n("step.end_done", "TerminalStep", "Done", "The rows are accepted.", stepId="END_done", sourceRef="flow.json#/nodes/END_done")
    n("artifact.source", "Artifact", "source", "The source document.", path="{inputs.source}", format="pdf", carries=["Document"], sourceRef="flow.json#/artifacts/source")
    n("artifact.rows", "Artifact", "rows", "The extracted rows.", path="{run_dir}/rows.json", format="json", carries=["Document"], sourceRef="flow.json#/artifacts/rows")
    n("field.rows.0", "ArtifactField", "rows[].cells", "", fieldPath="rows[].cells")
    n("metric.s1_extract.row_count", "Metric", "row_count", "", metricName="row_count")
    n("check.s1_extract.enough_rows", "Check", "enough_rows", "At least min_rows rows were found.", checkId="enough_rows", checkKind="metric",
      expression="metrics.row_count >= config.min_rows", blocking="true", readsStatePath=["state.nodes.S1_extract.metrics.row_count"])
    n("outcome.s1_extract.pass", "Outcome", "pass", "Rows found.", outcomeName="pass")
    n("outcome.s1_extract.fail", "Outcome", "fail", "Too few rows.", outcomeName="fail")
    n("outcome.s2_review.approve", "Outcome", "approve", "The reviewer approved.", outcomeName="approve")
    n("outcome.s2_review.reject", "Outcome", "reject", "The reviewer rejected.", outcomeName="reject")
    n("transition.e1", "Transition", "e1: S1_extract on pass", "Rows go to review.", priority=0, sourceRef="flow.json#/edges/e1")
    n("transition.e2", "Transition", "e2: S1_extract on fail", "Retry while attempts remain.", priority=1, guard="state.counters.attempts < config.min_rows",
      readsStatePath=["state.counters.attempts"], sourceRef="flow.json#/edges/e2")
    n("effect.e2.0", "Effect", "increment counters.attempts", "", op="increment", statePath="state.counters.attempts")
    n("transition.e3", "Transition", "e3: S2_review on approve", "Approved rows end the flow.", priority=0, sourceRef="flow.json#/edges/e3")
    n("transition.e4", "Transition", "e4: S2_review on reject", "Rejected rows are extracted again.", priority=0, sourceRef="flow.json#/edges/e4")
    n("invariant.inv1", "Invariant", "INV1", "Every extracted row has as many cells as the header.", statement="Every extracted row has as many cells as the header.",
      concerns=["Document"])
    n("test.s1_extract.enough_rows.pass", "TestObligation", "Fixture where 'enough_rows' holds -> check passes", "", obligationKind="pass_case")
    n("test.s1_extract.enough_rows.fail", "TestObligation", "Fixture where 'enough_rows' is violated -> outcome 'fail'", "", obligationKind="fail_case")
    n("test.e1.route", "TestObligation", "Outcome 'pass' -> engine moves to S2_review", "", obligationKind="route")
    n("test.inv1.s1_extract", "TestObligation", "Property test: every extracted row has as many cells as the header.", "", obligationKind="property")
    for s in ("step.s1_extract", "step.s2_review", "step.end_done"):
        e("flow.sample", "hasStep", s)
        e(s, "inPhase", "phase.build")
    e("phase.build", "entrypoint", "step.s1_extract")
    e("step.s1_extract", "reads", "artifact.source"); e("step.s1_extract", "writes", "artifact.rows")
    e("artifact.rows", "outputOf", "step.s1_extract"); e("artifact.rows", "hasArtifactField", "field.rows.0")
    e("step.s2_review", "readsOptional", "artifact.rows")
    e("step.s1_extract", "records", "metric.s1_extract.row_count"); e("step.s1_extract", "hasCheck", "check.s1_extract.enough_rows")
    e("check.s1_extract.enough_rows", "measures", "metric.s1_extract.row_count"); e("check.s1_extract.enough_rows", "comparedTo", "param.min_rows")
    e("check.s1_extract.enough_rows", "onFail", "outcome.s1_extract.fail")
    e("step.s1_extract", "hasOutcome", "outcome.s1_extract.pass"); e("step.s1_extract", "hasOutcome", "outcome.s1_extract.fail")
    e("step.s2_review", "hasOutcome", "outcome.s2_review.approve"); e("step.s2_review", "hasOutcome", "outcome.s2_review.reject")
    e("step.s1_extract", "implementedBy", "impl.steps-extract-py"); e("step.s1_extract", "usesParameter", "param.min_rows")
    e("transition.e1", "from", "step.s1_extract"); e("transition.e1", "onOutcome", "outcome.s1_extract.pass"); e("transition.e1", "to", "step.s2_review")
    e("transition.e2", "from", "step.s1_extract"); e("transition.e2", "onOutcome", "outcome.s1_extract.fail"); e("transition.e2", "to", "step.s1_extract")
    e("transition.e2", "usesParameter", "param.min_rows"); e("transition.e2", "hasEffect", "effect.e2.0")
    e("transition.e3", "from", "step.s2_review"); e("transition.e3", "onOutcome", "outcome.s2_review.approve"); e("transition.e3", "to", "step.end_done")
    e("transition.e4", "from", "step.s2_review"); e("transition.e4", "onOutcome", "outcome.s2_review.reject"); e("transition.e4", "to", "step.s1_extract")
    e("invariant.inv1", "enforcedBy", "check.s1_extract.enough_rows")
    for t, target, step in (("test.s1_extract.enough_rows.pass", "check.s1_extract.enough_rows", "step.s1_extract"),
                            ("test.s1_extract.enough_rows.fail", "check.s1_extract.enough_rows", "step.s1_extract"),
                            ("test.e1.route", "transition.e1", "step.s1_extract"), ("test.inv1.s1_extract", "invariant.inv1", "step.s1_extract")):
        e(t, "tests", target); e(t, "forStep", step)
    return {"_about": "A three-step flow, invented, so the unit builds and answers on its own. Replace it.", "nodes": nodes, "edges": edges}


# ============================ rationale, readme, manifests ============================

def _cited(name):
    out = []
    for qid, q in QUESTIONS.items():
        body = json.dumps(q)
        if '"%s"' % name in body or name in [k for p in (q.get("params") or {}).values() for k in p.get("type", "").split("|")]:
            out.append(qid)
    return out


def rationale(config, imported, about):
    record = {"_about": about, "classes": {}, "properties": {}}
    for name, spec in config["classes"].items():
        entry = dict((imported.get("classes") or {}).get(name) or {})
        cited = _cited(name)
        entry.setdefault("question", QUESTIONS[cited[0]]["question"] if cited else "What is a %s in the flow?" % name)
        entry.setdefault("why", ("Needed by %s: without it the graph cannot answer %s." % (", ".join(cited), cited[0])) if cited
                         else "A concept an artifact of the flow carries; its meaning is what a step's input or output is about.")
        entry.setdefault("alternatives", "")
        entry["validated_by"] = ""
        record["classes"][name] = entry
    for name, entry in (imported.get("properties") or {}).items():
        record["properties"][name] = dict(entry, validated_by="")
    for name in ("dependsOn", "affectedBy", "readBy"):
        if name in config["properties"]:
            record["properties"][name] = {"question": "What does the original join with a UNION?",
                                          "why": "The pattern language has no UNION; the rules derive one relation the question reads.",
                                          "alternatives": "Several optional blocks in one question: rejected because the rows multiply and the count no longer means anything.",
                                          "validated_by": ""}
    return record


FLOW_README = """# Flow — how work is executed

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
  FL16), `readBy` (an artifact's consumers, FL9). The rules derive them.
- The original's `gaps_only` gate is `no_gaps`: the answer may be empty, a gap makes it unanswered.
- Three names the report ontology uses for other things are renamed, new IRIs and all, so a
  project composes both: `Field` is `ArtifactField` (`hasArtifactField`), `Parameter` is
  `ConfigParameter`, `producedBy` is `outputOf`. The prompt reference and the review page are
  declared on `Step`, so one question (FL8) reads the execution spec of any step.
- Test obligations are derived by the port (as `kgctl build` derived them with SPARQL CONSTRUCT),
  so they are nodes of the sample, cited to `derive_tests.rq`.
- Four questions were added, so every term is cited by a question that runs: FL18 (phase and
  entrypoint), FL19 (effects and provenance), FL20 (a Claude step's prompt, schema and scope),
  FL21 (what a test obligation exercises).

## The briefs

`briefs.json` carries the five task types: `implement-step`, `write-tests`, `build-engine`,
`impact-parameter`, `impact-artifact`. `oto query brief implement-step STEP=<step>` is READY or
BLOCKED by name; without the step, the table for every implementable step (what `kgctl
readiness` printed).
"""

def manifest(name, summary, extends, namespace, note):
    return {"name": name, "release": 1, "domain": "software", "summary": summary,
            "extends": extends, "namespace": namespace, "engine": ">=0.9",
            "carries": ["vocabulary", "rationale", "rules", "questions", "briefs", "sample", "readme"],
            "maintainer": "Cynergis AI",
            "changelog": [{"release": 1, "at": datetime.date.today().isoformat(), "note": note}]}


def _write(directory, files):
    os.makedirs(directory, exist_ok=True)
    for filename, payload in files:
        with open(os.path.join(directory, filename), "w", encoding="utf-8", newline="\n") as f:
            if isinstance(payload, str):
                f.write(payload)
            else:
                json.dump(payload, f, indent=2, ensure_ascii=False)
                f.write("\n")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--oto", default=None, help="the OTO repository (default: $OTO_HOME or ../oto)")
    ap.add_argument("--flow-root", default=os.environ.get("FLOW_ROOT"), help="folder holding flow/flow.json (or FLOW_ROOT)")
    ap.add_argument("--check", action="store_true", help="self-check both units after writing them")
    args = ap.parse_args(argv)
    if not args.flow_root:
        print("flow_port: --flow-root (or FLOW_ROOT) must point at the folder holding flow/flow.json", file=sys.stderr)
        return 2
    _oto(args.oto)
    from oto.model import ontologies as _ontologies
    from oto.reason import questions as _questions, briefs as _briefs

    with tempfile.TemporaryDirectory() as work:
        flow_config, flow_imported = flow_vocabulary(work)
    _write(OUT_FLOW, [
        ("ontology.config.json", flow_config),
        ("ontology.rationale.json", rationale(flow_config, flow_imported,
                                              "Why each term exists; ported from the definitions of ontology/ontology.ttl. `validated_by` is "
                                              "empty until a person who knows the domain confirms the entry.")),
        ("sample.graph.json", flow_sample()),
        ("rules.json", {"_about": "The relations the original's questions joined with UNION, derived; two policies naming the question "
                                  "each protects.", "rules": RULES}),
        ("manifest.json", manifest("flow", flow_config["_summary"], ["oto-core"], FLOW,
                                   "Ported from report-ontology's flow ontology 0.1.1 (ontology/ontology.ttl, questions/competency_questions.yaml): "
                                   "19 classes, 17 questions as FL1-FL17 plus FL18-FL21, 5 task types as briefs.")),
        ("README.md", FLOW_README),
    ])
    _questions.save(types.SimpleNamespace(data=OUT_FLOW), QUESTIONS)
    _briefs.save(types.SimpleNamespace(data=OUT_FLOW), BRIEFS)
    graph = sample(args.flow_root)
    _write(os.path.dirname(OUT_GRAPH), [(os.path.basename(OUT_GRAPH), graph)])
    print("wrote %s: %d classes, %d relations, %d questions, %d rules, %d briefs; %s: %d nodes, %d edges"
          % (OUT_FLOW, len(flow_config["classes"]), len(flow_config["properties"]), len(QUESTIONS), len(RULES), len(BRIEFS),
             OUT_GRAPH, len(graph["nodes"]), len(graph["edges"])))
    if args.check:
        problems = _ontologies.self_check("flow", roots=[os.path.dirname(OUT_FLOW)])
        for p in problems:
            print("  -", p)
        print("self-check:", "clean" if not problems else "%d problem(s)" % len(problems))
        return 1 if problems else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
