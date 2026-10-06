"""kgctl — build, validate and query the pdf-to-template knowledge graph.

  python kgctl.py build                       flow.json + ontology + bindings → graph.ttl (+ derived tests)
  python kgctl.py validate                    SHACL "executable shape" report (violations + warnings)
  python kgctl.py ask CQ04 --step B10_verify  run one competency question
  python kgctl.py brief --task implement-step --step B10_verify [--out brief.json]
                                              the domain brief an agent reads before acting; exit 1 if BLOCKED
  python kgctl.py readiness                   which steps are ready to implement / to test
  python kgctl.py terms                       schemas ↔ report ontology ↔ competency questions agree (needs no flow)
  python kgctl.py ontology check [--strict]   what changed since the accepted lock: breaking / additive / cosmetic,
                                              the catalogue it touches, and whether each version says so; exit 1 if not
  python kgctl.py ontology accept --by <you>  write the lock and append the accepted changes to ontology/changelog.yaml
  python kgctl.py rationale [--missing]       how many terms, shapes and questions say why they exist, and how many a
                                              person confirmed (--strict: exit 1 while a class, shape or question has no why)

The flow instance is not part of this package: build and readiness read it from --flow-root (or FLOW_ROOT),
the other flow commands read the graph build wrote to build/graph.ttl.

Nothing here calls an LLM. The graph is built deterministically from flow.json (factory process),
ontology.ttl (vocabulary), bindings.ttl (authored domain links) and derive_tests.rq (rules).
"""
import argparse, datetime, hashlib, json, pathlib, re, sys
import yaml
from rdflib import Graph, Literal, Namespace, URIRef, RDF, RDFS
from rdflib.namespace import XSD, DCTERMS as DCT, SKOS

from paths import ONT, SCHEMAS, QUESTIONS, BUILD, EXAMPLE, flow_root

GRAPH_TTL = BUILD / "graph.ttl"
CQ_FILE = QUESTIONS / "competency_questions.yaml"
FLOW_ROOT = None        # set from --flow-root / FLOW_ROOT by the commands that read the flow instance


def flow_json():
    return json.loads((FLOW_ROOT / "flow" / "flow.json").read_text())

FLOW = Namespace("https://cynergis.ai/ont/flow#")
DT = Namespace("https://cynergis.ai/ont/doctemplate#")
PT = "https://cynergis.ai/kg/pdf-to-template/"
PREFIXES = f"""PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
PREFIX dct: <http://purl.org/dc/terms/>
PREFIX flow: <{FLOW}>
PREFIX dt: <{DT}>
PREFIX pt: <{PT}>
"""
STEP_CLASS = {"deterministic": FLOW.DeterministicStep, "ocr": FLOW.OcrStep, "claude": FLOW.ClaudeStep,
              "human": FLOW.HumanStep, "terminal": FLOW.TerminalStep}


def I(*parts):
    return URIRef(PT + "/".join(str(p) for p in parts))


def short(term):
    s = str(term)
    for pfx, ns in (("pt:", PT), ("flow:", str(FLOW)), ("dt:", str(DT)), ("rpt:", str(RPT))):
        if s.startswith(ns):
            return pfx + s[len(ns):]
    return s


def flatten(d, prefix=""):
    for k, v in d.items():
        name = f"{prefix}{k}"
        if isinstance(v, dict):
            yield from flatten(v, name + ".")
        else:
            yield name, v


# ───────────────────────────── build ─────────────────────────────
def build():
    f = flow_json()
    g = Graph()
    for p, ns in (("flow", FLOW), ("dt", DT), ("dct", DCT), ("skos", SKOS)):
        g.bind(p, ns)
    g.parse(ONT / "ontology.ttl")
    g.parse(ONT / "bindings.ttl")
    params = dict(flatten(f["config"]))
    known_params = set(params)

    def param(name):
        # longest known prefix wins: config.claude.model → claude.model
        cands = [p for p in known_params if name == p or name.startswith(p + ".")]
        name = max(cands, key=len) if cands else name
        p = I("param", name)
        g.add((p, RDF.type, FLOW.Parameter)); g.add((p, FLOW.paramName, Literal(name)))
        return p

    for name, v in params.items():
        p = param(name)
        g.add((p, FLOW["value"], Literal(json.dumps(v) if isinstance(v, (list, dict)) else str(v))))
        g.add((p, FLOW.sourceRef, Literal(f"flow.json#/config/{name.replace('.', '/')}")))

    fl = I("flow", f["id"])
    g.add((fl, RDF.type, FLOW.Flow)); g.add((fl, RDFS.label, Literal(f["title"])))
    g.add((fl, FLOW["value"], Literal(f["version"])))
    for ph in f["phases"]:
        p = I("phase", ph["id"])
        g.add((p, RDF.type, FLOW.Phase)); g.add((p, RDFS.label, Literal(ph["title"])))
        g.add((p, FLOW.entrypoint, I("step", f["entrypoints"][ph["id"]])))
        for nid in ph["nodes"]:
            g.add((I("step", nid), FLOW.inPhase, p))

    def metric(step_id, name):
        m = I("step", step_id, "metric", name)
        g.add((m, RDF.type, FLOW.Metric)); g.add((m, FLOW.metricName, Literal(name)))
        return m

    def config_refs(text):
        return set(re.findall(r"config\.([A-Za-z_][\w\.]*)", text or ""))

    for n in f["nodes"]:
        s = I("step", n["id"])
        g.add((s, RDF.type, STEP_CLASS[n["type"]])); g.add((fl, FLOW.hasStep, s))
        g.add((s, FLOW.stepId, Literal(n["id"]))); g.add((s, RDFS.label, Literal(n["name"])))
        g.add((s, DCT.description, Literal(n["description"])))
        g.add((s, FLOW.sourceRef, Literal(f"flow.json#/nodes/{n['id']}")))
        if n.get("uses_ocr"):
            g.add((s, FLOW.usesOcr, Literal(True)))
        if n.get("foreach"):
            g.add((s, FLOW.foreach, Literal(n["foreach"])))
        opt = set(n.get("inputs_optional", []))
        for a in n.get("inputs", []):
            g.add((s, FLOW.readsOptional if a in opt else FLOW.reads, I("artifact", a)))
        for a in n.get("outputs", []):
            g.add((s, FLOW.writes, I("artifact", a)))
        for m in n.get("metrics", []):
            g.add((s, FLOW.records, metric(n["id"], m)))
        for oname, odesc in n.get("outcomes", {}).items():
            o = I("step", n["id"], "outcome", oname)
            g.add((o, RDF.type, FLOW.Outcome)); g.add((o, FLOW.outcomeName, Literal(oname)))
            g.add((o, DCT.description, Literal(odesc))); g.add((s, FLOW.hasOutcome, o))
        act = n.get("action", {})
        if n["type"] != "terminal":
            g.add((s, FLOW.isImplemented, Literal(bool(act.get("implemented")))))
        if act.get("kind") == "command":
            g.add((s, FLOW.command, Literal(act["command"])))
            script = act["command"].split()[1]
            impl = I("impl", script.replace("{skill_dir}/", ""))
            g.add((impl, RDF.type, FLOW.Implementation)); g.add((impl, FLOW["path"], Literal(script)))
            g.add((impl, FLOW.exists, Literal((FLOW_ROOT / script.replace("{skill_dir}/", "")).exists())))
            g.add((s, FLOW.implementedBy, impl))
        if act.get("kind") == "claude":
            g.add((s, FLOW.promptRef, Literal(act["prompt_ref"]))); g.add((s, FLOW.promptVersion, Literal(act["prompt_version"])))
            if act.get("output_schema"):
                g.add((s, FLOW.outputSchema, Literal(act["output_schema"])))
            for w in act.get("writes_only", []):
                g.add((s, FLOW.writesOnly, Literal(w)))
        if act.get("kind") == "human_review":
            g.add((s, FLOW.reviewPage, Literal(act["review_page"])))
            for d in act["decision_options"]:
                g.add((s, FLOW.decisionOption, Literal(d)))
            for r in act["required_fields"]:
                g.add((s, FLOW.requiredField, Literal(r)))
        if n.get("retry"):
            g.add((s, FLOW.retryMax, Literal(n["retry"]["max_attempts"], datatype=XSD.integer)))
        for ref in config_refs(json.dumps(act)):
            g.add((s, FLOW.usesParameter, param(ref)))
        for v in n.get("validations", []):
            c = I("step", n["id"], "check", v["id"])
            g.add((c, RDF.type, FLOW.Check)); g.add((s, FLOW.hasCheck, c))
            g.add((c, FLOW.checkId, Literal(v["id"]))); g.add((c, DCT.description, Literal(v["description"])))
            g.add((c, FLOW.checkKind, Literal(v["kind"]))); g.add((c, FLOW.expression, Literal(v["check"])))
            g.add((c, FLOW.blocking, Literal(str(v["blocking"]).lower() if isinstance(v["blocking"], bool) else v["blocking"])))
            g.add((c, FLOW.onFail, I("step", n["id"], "outcome", v["on_fail"])))
            if v["kind"] == "metric":
                own = re.sub(r"state\.nodes\.\w+\.metrics\.\w+", "", v["check"])
                for m in set(re.findall(r"metrics\.(\w+)", own)):
                    g.add((c, FLOW.measures, metric(n["id"], m)))
                for ref in config_refs(v["check"]):
                    g.add((c, FLOW.comparedTo, param(ref)))
                for sp in re.findall(r"state\.([\w\.]+)", v["check"] + " " + str(v["blocking"])):
                    g.add((c, FLOW.readsStatePath, Literal("state." + sp)))

    for a_id, a in f["artifacts"].items():
        art = I("artifact", a_id)
        g.add((art, RDF.type, FLOW.Artifact)); g.add((art, RDFS.label, Literal(a_id)))
        g.add((art, FLOW["path"], Literal(a["path"]))); g.add((art, FLOW["format"], Literal(a["format"])))
        g.add((art, DCT.description, Literal(a["description"])))
        g.add((art, FLOW.sourceRef, Literal(f"flow.json#/artifacts/{a_id}")))
        if a.get("optional"):
            g.add((art, FLOW.optional, Literal(True)))
        if a.get("schema"):
            g.add((art, FLOW.outputSchema, Literal(a["schema"])))
        if a["produced_by"] in {n["id"] for n in f["nodes"]}:
            g.add((art, FLOW.producedBy, I("step", a["produced_by"])))
        for i, fp in enumerate(a.get("key_fields", [])):
            fld = I("artifact", a_id, "field", i)
            g.add((fld, RDF.type, FLOW.Field)); g.add((fld, FLOW.fieldPath, Literal(fp))); g.add((art, FLOW.hasField, fld))

    for e in f["edges"]:
        t = I("edge", e["id"])
        g.add((t, RDF.type, FLOW.Transition)); g.add((t, FLOW["from"], I("step", e["from"])))
        g.add((t, FLOW.onOutcome, I("step", e["from"], "outcome", e["on"])))
        g.add((t, DCT.description, Literal(e.get("description", ""))))
        g.add((t, FLOW.priority, Literal(e.get("priority", 0), datatype=XSD.integer)))
        g.add((t, FLOW.sourceRef, Literal(f"flow.json#/edges/{e['id']}")))
        if e["to"].startswith("$"):
            g.add((t, FLOW.toDynamic, Literal(e["to"])))
        else:
            g.add((t, FLOW.to, I("step", e["to"])))
        if e.get("guard"):
            gd = e["guard"]
            g.add((t, FLOW.guard, Literal(gd)))
            for sp in re.findall(r"state\.([\w\.]+)", gd):
                g.add((t, FLOW.readsStatePath, Literal("state." + sp)))
            for m in re.findall(r"(?<![\w.])metrics\.(\w+)", gd):
                g.add((t, FLOW.readsStatePath, Literal(f"state.nodes.{e['from']}.metrics.{m}")))
            for ref in config_refs(gd):
                g.add((t, FLOW.usesParameter, param(ref)))
        for i, eff in enumerate(e.get("effects", [])):
            ef = I("edge", e["id"], "effect", i)
            g.add((ef, RDF.type, FLOW.Effect)); g.add((ef, FLOW.op, Literal(eff["op"])))
            g.add((ef, FLOW.statePath, Literal("state." + eff["path"]))); g.add((t, FLOW.hasEffect, ef))

    # rules: derive test obligations
    rules = (ONT / "derive_tests.rq").read_text()
    head = "\n".join(l for l in rules.splitlines() if l.startswith("PREFIX"))
    body = "\n".join(l for l in rules.splitlines() if not l.startswith("PREFIX") and not l.startswith("#"))
    derived = 0
    for q in [b for b in re.split(r"^\s*;\s*$", body, flags=re.M) if b.strip()]:
        for triple in g.query(head + "\n" + q):
            g.add(triple); derived += 1
    GRAPH_TTL.parent.mkdir(parents=True, exist_ok=True)
    g.serialize(GRAPH_TTL, format="turtle")
    stats = {k: len(set(g.subjects(RDF.type, c))) for k, c in [
        ("steps", FLOW.Step), ("checks", FLOW.Check), ("transitions", FLOW.Transition), ("artifacts", FLOW.Artifact),
        ("fields", FLOW.Field), ("metrics", FLOW.Metric), ("parameters", FLOW.Parameter), ("invariants", FLOW.Invariant),
        ("test_obligations", FLOW.TestObligation)]}
    stats["steps"] = sum(len(set(g.subjects(RDF.type, c))) for c in STEP_CLASS.values())
    print(f"graph.ttl: {len(g)} triples  {stats}")
    return g


def load():
    if not GRAPH_TTL.exists():
        return build()
    g = Graph(); g.parse(GRAPH_TTL)
    return g


def graph_hash():
    return hashlib.sha256(GRAPH_TTL.read_bytes()).hexdigest()[:16]


# ───────────────────────────── validate ─────────────────────────────
def validate(g):
    from pyshacl import validate as shacl
    shapes = Graph(); shapes.parse(ONT / "shapes.ttl")
    conforms, rg, _ = shacl(g, shacl_graph=shapes, inference="none", allow_warnings=True, advanced=True)
    SH = Namespace("http://www.w3.org/ns/shacl#")
    rows = []
    for r in rg.subjects(RDF.type, SH.ValidationResult):
        rows.append((short(rg.value(r, SH.resultSeverity)).split("#")[-1], short(rg.value(r, SH.focusNode)), str(rg.value(r, SH.resultMessage))))
    rows.sort()
    for sev in ("Violation", "Warning"):
        sel = [r for r in rows if r[0] == sev]
        print(f"\n{sev}s: {len(sel)}")
        for _, node, msg in sel:
            print(f"  {node:<58} {msg}")
    print(f"\nconforms (violations only): {conforms}")
    return conforms


# ───────────────────────────── questions ─────────────────────────────
CQS = yaml.safe_load(CQ_FILE.read_text())


def bind(q, params):
    for k, v in params.items():
        q = q.replace(f"${k}", f"<{v}>")
    return PREFIXES + q


def run_rows(g, q, params):
    res = g.query(bind(q, params))
    return [{str(k): (short(v) if v is not None else None) for k, v in zip(res.vars, row)} for row in res]


def ask(g, cq_id, params, required):
    cq = CQS["questions"][cq_id]
    rows = run_rows(g, cq["answer"], params)
    gaps = run_rows(g, cq["gaps"], params) if cq.get("gaps") else []
    if gaps:
        status = "gap"
    elif cq["gate"] == "non_empty" and not rows:
        status = "empty"
    else:
        status = "answered"
    return {"id": cq_id, "question": cq["question"], "required": required, "status": status, "answer": rows, "gaps": gaps}


def params_for(args):
    p = {}
    if getattr(args, "step", None):
        p["STEP"] = PT + "step/" + args.step
    if getattr(args, "param", None):
        p["PARAM"] = PT + "param/" + args.param
    if getattr(args, "artifact", None):
        p["ARTIFACT"] = PT + "artifact/" + args.artifact
    return p


def brief(g, task, params):
    tt = CQS["task_types"][task]
    out = {"task": task, "description": tt["description"], "params": {k: short(URIRef(v)) for k, v in params.items()},
           "ontology_version": CQS["ontology_version"], "graph_sha256": graph_hash(),
           "as_of": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"), "questions": []}
    for cid in tt["required"]:
        out["questions"].append(ask(g, cid, params, True))
    for cid in tt["optional"]:
        out["questions"].append(ask(g, cid, params, False))
    blocking = [q for q in out["questions"] if q["required"] and q["status"] != "answered"]
    out["status"] = "BLOCKED" if blocking else "READY"
    out["blocking"] = [{"cq": q["id"], "status": q["status"], "gaps": q["gaps"] or "required question returned no facts"} for q in blocking]
    out["citation_rule"] = "Annotate code and tests with the pt: id of every check, transition, invariant and field they implement, e.g. `# implements pt:step/B10_verify/check/fidelity`."
    return out


def print_brief(b):
    print(f"{b['task']}  {b['params']}  → {b['status']}   (ontology {b['ontology_version']}, graph {b['graph_sha256']})")
    for q in b["questions"]:
        mark = {"answered": "✓", "gap": "✗", "empty": "∅"}[q["status"]]
        print(f"  {mark} {q['id']} {'REQ' if q['required'] else 'opt'}  {q['question']}  [{len(q['answer'])} facts]")
        for gp in q["gaps"]:
            print(f"        gap: {gp}")
    if b["status"] == "BLOCKED":
        print("  blocked on:", ", ".join(x["cq"] for x in b["blocking"]))


def readiness(g):
    steps = sorted(str(o) for o in g.objects(None, FLOW.stepId))
    f = flow_json()
    types = {n["id"]: n["type"] for n in f["nodes"]}
    print(f"{'step':<24}{'type':<15}{'implement-step':<34}{'write-tests':<22}")
    for sid in steps:
        if types[sid] in ("terminal", "human"):
            continue
        res = []
        for task in ("implement-step", "write-tests"):
            b = brief(g, task, {"STEP": PT + "step/" + sid})
            res.append("READY" if b["status"] == "READY" else "BLOCKED " + ",".join(x["cq"] for x in b["blocking"]))
        print(f"{sid:<24}{types[sid]:<15}{res[0]:<34}{res[1]:<22}")


# ───────────────────────────── terms: schema ↔ ontology ↔ competency questions ─────────────────────────────
RPT = Namespace("https://cynergis.ai/ont/report#")
REPORT_CQ = QUESTIONS / "report_cq.yaml"
EXAMPLE_GRAPH = EXAMPLE / "semantic" / "report.graph.json"
PREFIX_IRI = {"rpt": str(RPT), "dt": str(DT), "rdfs": str(RDFS), "skos": str(SKOS), "prov": "http://www.w3.org/ns/prov#"}


def expand(term):
    pfx, _, local = term.partition(":")
    return PREFIX_IRI.get(pfx, pfx + ":") + local


def schema_terms():
    """Walk every property of every schema in schemas/ that names its ontology (x-ontology).
    Returns (terms_used: {term: [schema.path]}, problems: [str]). A property must carry x-term or x-structural."""
    used, problems = {}, {}
    def walk(node, path, root, name, seen):
        if not isinstance(node, dict) or id(node) in seen:
            return
        seen.add(id(node))
        if "$ref" in node:
            node = {**root["$defs"][node["$ref"].split("/")[-1]], **{k: v for k, v in node.items() if k != "$ref"}}
        if node.get("x-emit") == "json":           # nested keys are serialized into one literal; no terms below
            for key in ("x-term",):
                if node.get(key): used.setdefault(node[key], []).append(f"{name}:{path}")
            return
        for key in ("x-term", "x-class", "x-key"):
            if node.get(key):
                used.setdefault(node[key], []).append(f"{name}:{path}")
        props = node.get("properties", {})
        for k, ps in props.items():
            r = ps if "$ref" not in ps else {**root["$defs"][ps["$ref"].split("/")[-1]], **{kk: v for kk, v in ps.items() if kk != "$ref"}}
            if not (r.get("x-term") or r.get("x-structural") or r.get("x-class") or r.get("x-key")):
                problems.setdefault("no_term", []).append(f"{name}:{path}.{k}")
            walk(r, f"{path}.{k}", root, name, seen)
        if isinstance(node.get("additionalProperties"), dict):
            walk(node["additionalProperties"], path + ".*", root, name, seen)
        if isinstance(node.get("items"), dict):
            walk(node["items"], path + "[]", root, name, seen)
    for sp in sorted(SCHEMAS.glob("*.schema.json")):
        sch = json.loads(sp.read_text())
        if "x-ontology" not in sch:
            continue
        ov = re.search(r'owl:versionInfo\s+"([^"]+)"', (ONT / "report.ttl").read_text()).group(1)
        if sch.get("x-ontology-version") != ov:
            problems.setdefault("version", []).append(f"{sp.name} is for ontology {sch.get('x-ontology-version')}, report.ttl is {ov}")
        walk(sch, "", sch, sp.stem.replace(".schema", ""), set())
    return used, problems


def terms_check(verbose=True):
    """Check A: every schema x-term exists in the ontology; every rpt: term is used by a schema or the compiler (example graph).
       Check B: every rpt: term is cited by a competency question (query text or terms list).
       Check C: every rpt:, flow: and dt: term explains itself: label and definition, and for a property its domain and range.
       Exit 1 on any failure. Implements the rule 'no property without a term, no term without a question,
       no term without a definition'."""
    from rdflib import OWL
    og = Graph(); og.parse(ONT / "report.ttl"); og.parse(ONT / "ontology.ttl")
    declared = set()
    for t in (OWL.Class, OWL.ObjectProperty, OWL.DatatypeProperty):
        declared |= {str(x) for x in og.subjects(RDF.type, t)}
    rpt_terms = sorted(t for t in declared if t.startswith(str(RPT)))
    used, problems = schema_terms()
    fails = []
    for k in problems.get("version", []): fails.append("VERSION  " + k)
    for k in problems.get("no_term", []): fails.append("NO-TERM  schema property has neither x-term nor x-structural: " + k)
    for term, where in sorted(used.items()):
        iri = expand(term)
        if iri not in declared and iri not in (str(RDFS.label), str(SKOS.definition)):
            fails.append(f"UNKNOWN  {term} used by {', '.join(where[:3])} is not declared in the ontology")
    # usage: schema or compiler output
    in_graph = set()
    if EXAMPLE_GRAPH.exists():
        eg = Graph(); eg.parse(data=EXAMPLE_GRAPH.read_text(), format="json-ld")
        in_graph = {str(p) for p in eg.predicates()} | {str(o) for o in eg.objects(None, RDF.type)}
    schema_iris = {expand(t) for t in used}
    orphans = [t for t in rpt_terms if t not in schema_iris and t not in in_graph]
    # citations
    cq = yaml.safe_load(REPORT_CQ.read_text())
    cited = set()
    for qid, q in cq["questions"].items():
        text = (q.get("answer", "") + q.get("gaps", ""))
        cited |= {expand(m) for m in re.findall(r"\brpt:[A-Za-z0-9_]+", text)}
        cited |= {expand(t) for t in q.get("terms", [])}
    ttl = (ONT / "report.ttl").read_text()
    for m in re.finditer(r"^(rpt:[A-Za-z0-9_]+)\s+a\s+owl:Class.*?\[(CQ[^\]]*)\]", ttl, flags=re.S | re.M):
        ids = re.findall(r"CQ\d+(?:-\d+)?", m.group(2))
        ok = True
        for i in ids:
            lo, _, hi = i[2:].partition("-")
            for n in range(int(lo), int(hi or lo) + 1):
                if f"CQ{n}" not in cq["questions"]:
                    ok = False; fails.append(f"CQ-REF   {m.group(1)} cites CQ{n} which report_cq.yaml does not define")
        if ok: cited.add(expand(m.group(1)))
    uncited = [t for t in rpt_terms if t not in cited]
    for t in orphans: fails.append(f"ORPHAN   rpt:{t.split('#')[1]} is declared but no schema property or compiled graph uses it")
    for t in uncited: fails.append(f"NO-CQ    rpt:{t.split('#')[1]} is declared but no competency question needs it")
    bad_cq = [f"{qid} cites rpt:{m.split('#')[1]} which the ontology does not declare" for qid, q in cq["questions"].items()
              for m in {expand(x) for x in re.findall(r"\brpt:[A-Za-z0-9_]+", q.get("answer", "") + q.get("gaps", ""))} | {expand(x) for x in q.get("terms", [])} if m not in declared]
    for b in bad_cq: fails.append("CQ-TERM  " + b)
    for t in sorted(x for x in declared if x.startswith((str(RPT), str(FLOW), str(DT)))):      # all three vocabularies explain themselves
        node = URIRef(t)
        need = [("label", RDFS.label), ("definition", SKOS.definition)]
        if (node, RDF.type, OWL.Class) not in og:
            need += [("domain", RDFS.domain), ("range", RDFS.range)]
        lacks = [name for name, pred in need if og.value(node, pred) is None]
        if lacks: fails.append(f"NO-DEF   {short(node)} has no {', '.join(lacks)}")
    import vocabulary
    for p in vocabulary.confirmation_problems(): fails.append("CONFIRM  " + p)
    if verbose:
        print(f"ontology report.ttl: {len(rpt_terms)} rpt: terms · schemas: {len(used)} distinct terms over {sum(len(v) for v in used.values())} properties · CQs: {len(cq['questions'])}")
        for f in fails: print("FAIL", f)
        print("terms: OK" if not fails else f"terms: {len(fails)} failure(s)")
    return not fails


# ───────────────────────────── ontology check / accept, rationale ─────────────────────────────
def ontology_check(catalogue, strict=False, as_json=False):
    import vocabulary
    r = vocabulary.check(catalogue=catalogue)
    r.pop("snapshot")
    pending = bool(r["changes"]) or r["lock"] is None
    if as_json:
        print(json.dumps(r, indent=1, ensure_ascii=False))
    elif r["lock"] is None:
        print("no lock yet: `kgctl.py ontology accept --by <you>` records the vocabularies as they stand")
    else:
        lock = r["lock"]
        print(f"against the lock accepted by {lock['accepted_by']} at {lock['accepted_at']}")
        for vocab, v in r["versions"].items():
            mine = [c for c in r["changes"] if c["vocabulary"] == vocab]
            print(f"\n{vocab} {lock['versions'].get(vocab, '(new)')} → {v}: " + (f"{len(mine)} change(s)" if mine else "no change"))
            for c in mine:
                hit = f"  [{c['affected']} in the catalogue]" if "affected" in c else ""
                print(f"  {c['severity']:<9} {c['kind']:<24} {c['subject']}" + (f" — {c['detail']}" if c.get("detail") else "") + hit)
        for n in r["reconfirm"]:
            print("\nRECONFIRM", n)
        cat = r.get("catalogue")
        if cat:
            print(f"\ncatalogue {cat['folder']}: {cat['compiled']} report(s) compile against the files" +
                  "".join(f"\n  FAILS {f['report']}: {f['first_error']}" for f in cat["failing"]))
    for p in r["problems"]:
        print("PROBLEM", p)
    if not as_json:
        print("\nontology: " + ("OK" if not r["problems"] else f"{len(r['problems'])} problem(s)") +
              ("; changes not accepted yet (`kgctl.py ontology accept --by <you>`)" if pending else "; the lock is current"))
    return not r["problems"] and not (strict and pending)


def ontology_accept(by):
    import vocabulary
    try:
        entry = vocabulary.accept(by)
    except ValueError as e:
        print(e); return False
    if entry is None:
        print("nothing to accept: the lock is current")
    else:
        print(f"accepted by {entry['by']} at {entry['at']}: " + (entry.get("note") or f"{len(entry['changes'])} change(s)") +
              f" → ontology/{vocabulary.LOCK}, ontology/{vocabulary.CHANGELOG}")
    return True


def rationale_report(vocab=None, missing=False, strict=False, as_json=False):
    import vocabulary
    r = vocabulary.rationale(vocabulary=vocab)
    if as_json:
        print(json.dumps(r, indent=1, ensure_ascii=False))
    else:
        print(f"{'vocabulary':<13}{'part':<12}{'total':>6}{'why':>6}{'confirmed':>11}")
        for v, groups in r["summary"].items():
            for g, s in groups.items():
                print(f"{v:<13}{g:<12}{s['total']:>6}{s['rationale']:>6}{s['validated']:>11}")
        for c in r["confirmed"]:
            print(f"  confirmed {c['subject']} by {c['by']} on {c['on']}")
        if missing:
            print("\nno recorded why:", *r["missing_rationale"], sep="\n  ")
    return not (strict and r["missing_rationale"])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["build", "validate", "ask", "brief", "readiness", "terms", "ontology", "rationale"])
    ap.add_argument("cq", nargs="?", help="ask: the question id; ontology: check or accept")
    ap.add_argument("--task"); ap.add_argument("--step"); ap.add_argument("--param"); ap.add_argument("--artifact")
    ap.add_argument("--out")
    ap.add_argument("--flow-root", help="folder holding flow/flow.json and the step scripts (or set FLOW_ROOT)")
    ap.add_argument("--by", help="ontology accept: the person accepting the change")
    ap.add_argument("--catalogue", help="ontology check: the reports to count the impact on (default REPORTS_ROOT, else fixtures/)")
    ap.add_argument("--strict", action="store_true", help="ontology check: fail while a change is not accepted; rationale: fail while a why is missing")
    ap.add_argument("--json", action="store_true"); ap.add_argument("--missing", action="store_true")
    ap.add_argument("--vocabulary", choices=["report", "flow", "doctemplate", "meta"])
    a = ap.parse_args()
    if a.cmd == "terms":
        sys.exit(0 if terms_check() else 1)
    if a.cmd == "ontology":
        from paths import FIXTURES
        import os
        if a.cq == "check":
            sys.exit(0 if ontology_check(pathlib.Path(a.catalogue or os.environ.get("REPORTS_ROOT") or FIXTURES), a.strict, a.json) else 1)
        if a.cq == "accept":
            sys.exit(0 if ontology_accept(a.by) else 1)
        sys.exit("kgctl.py ontology check | accept --by <you>")
    if a.cmd == "rationale":
        sys.exit(0 if rationale_report(a.vocabulary, a.missing, a.strict, a.json) else 1)
    if a.cmd in ("build", "readiness") or not GRAPH_TTL.exists():
        FLOW_ROOT = flow_root(a.flow_root)
    if a.cmd == "build":
        build(); sys.exit(0)
    g = load()
    if a.cmd == "validate":
        sys.exit(0 if validate(g) else 1)
    if a.cmd == "ask":
        r = ask(g, a.cq, params_for(a), True)
        print(json.dumps(r, indent=1, ensure_ascii=False))
    if a.cmd == "brief":
        b = brief(g, a.task, params_for(a))
        print_brief(b)
        if a.out:
            pathlib.Path(a.out).write_text(json.dumps(b, indent=1, ensure_ascii=False))
        sys.exit(0 if b["status"] == "READY" else 1)
    if a.cmd == "readiness":
        readiness(g)
