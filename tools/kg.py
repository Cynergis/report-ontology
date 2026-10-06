"""kg — the query surface of the report ontology. Everything a consumer (plugin, agent, action) needs is one of:

  python kg.py questions [--vocabulary report|flow]      the competency questions and the parameters each needs
  python kg.py ask CQ14                                   one report question across the catalogue
  python kg.py ask CQ5 --report fund-profile-balanced     (also --field, --column, --component)
  python kg.py ask flow:CQ04 --step B10_verify            one flow question (also --param, --artifact)
  python kg.py explain sourcedFrom                        a class or property: definition, domain, range, where it is written
  python kg.py explain                                    the index of every class
  python kg.py requirements [--provided-by analyst]       what a new report must provide, and who provides each part
  python kg.py gaps <report folder>                       what a draft report still lacks, and where each answer goes
  python kg.py export-sqlite [--out build/catalogue.db] [--with-flow]   the validated catalogue as a SQLite file

Beyond the questions, the catalogue graph can be walked:
  python kg.py resolve "management expense ratio"         a name, label (any locale), alias or id → the entities it names
  python kg.py entity mer [--report fund-profile-equity]  one entity: its values, its edges both ways, its history
  python kg.py neighbors mer --depth 2 [--property sourcedFrom] [--direction out|in|both]
  python kg.py search "sums to 100" [--type Field]         full text over labels, meanings, purposes, rules and notes
  python kg.py overview                                   the map: counts, lifecycle, mapping, shared fields, recent revisions
  python kg.py stale [--days 30]                          what is out of date: unaccepted changes, unverified mappings, idle statuses
  python kg.py history <report> [--as-of DATE] [--fact TEXT]   the accepted revisions, or the definition as it stood on a date

Reports are read from --catalogue, REPORTS_ROOT, or ./reports: a folder of report folders (<report>/semantic/report.yaml).
Flow questions read the flow instance from --flow-root or FLOW_ROOT.
Every command prints JSON. Reports are validated and compiled in memory on each call, so an answer is never
stale; a report that fails validation is left out of the answer and named under "skipped".
The same functions are served over MCP by mcp_server.py.
"""
import argparse, contextlib, datetime, difflib, functools, io, json, os, pathlib, re, sqlite3, sys
from rdflib import Graph, Literal, URIRef, RDF, RDFS, OWL
from rdflib.collection import Collection
from rdflib.namespace import SKOS

import kgctl, ledger, semantic, vocabulary
from paths import ONT, SCHEMAS, QUESTIONS, BUILD, flow_root

VOCAB = {"rpt": semantic.RPT, "dt": semantic.DT, "flow": str(kgctl.FLOW)}
OTHER = {"rdfs": str(RDFS), "rdf": str(RDF), "owl": str(OWL), "xsd": "http://www.w3.org/2001/XMLSchema#",
         "skos": str(SKOS), "prov": semantic.PROV, "dct": "http://purl.org/dc/terms/"}
KIND = {OWL.Class: "class", OWL.ObjectProperty: "object property", OWL.DatatypeProperty: "datatype property"}
FLOW_PARAMS = {"STEP": "step/", "PARAM": "param/", "ARTIFACT": "artifact/"}
PROVIDERS = {"analyst": "ask the analyst",
             "agent": "the agent writes it (drafted from the sample PDF or the table, or recorded as the work progresses), and the analyst confirms",
             "flow": "recorded by a step of the flow; never asked"}


class KgError(Exception):
    """A request the surface cannot serve; the message says what to change."""


def short(iri):
    s = str(iri)
    for pfx, ns in {**VOCAB, **OTHER}.items():
        if s.startswith(ns):
            return f"{pfx}:{s[len(ns):]}"
    return s


def expand(term):
    pfx, _, local = term.partition(":")
    return {**VOCAB, **OTHER}.get(pfx, pfx + ":") + local


# ───────────────────────────── the ontology ─────────────────────────────
@functools.lru_cache(maxsize=1)
def ontology_graph():
    g = Graph(); g.parse(ONT / "report.ttl"); g.parse(ONT / "ontology.ttl")
    return g


def versions():
    g = ontology_graph()
    return {name: str(g.value(URIRef(f"https://cynergis.ai/ont/{path}"), OWL.versionInfo))
            for name, path in (("report", "report"), ("flow", "flow"), ("doctemplate", "doctemplate"))}


@functools.lru_cache(maxsize=1)
def all_terms():
    """{prefixed term: (iri, kind)} for every class and property the three vocabularies declare."""
    g, out = ontology_graph(), {}
    for T, kind in KIND.items():
        for s in g.subjects(RDF.type, T):
            if isinstance(s, URIRef) and any(str(s).startswith(ns) for ns in VOCAB.values()):
                out[short(s)] = (s, kind)
    return out


def members(node):
    """A class, or the members of a union of classes, as prefixed names."""
    g = ontology_graph()
    if node is None:
        return []
    union = g.value(node, OWL.unionOf)
    return [short(x) for x in Collection(g, union)] if union is not None else [short(node)]


@functools.lru_cache(maxsize=1)
def written_in():
    """{term: ['semantic/lineage.yaml → fields.*.column', …]}: where a person or the flow writes each term."""
    used, _ = kgctl.schema_terms()
    out = {}
    for term, where in used.items():
        for w in sorted(set(where)):
            name, _, path = w.partition(":")
            out.setdefault(term, []).append(f"{semantic.FILE_OF[name]} → {path.lstrip('.') or '(the file itself)'}")
    return out


def asked_by(term):
    """The competency questions that read a term."""
    cq, out = semantic.questions()["questions"], []
    pat = re.compile(re.escape(term) + r"\b")
    for qid, q in cq.items():
        if pat.search(q.get("answer", "") + q.get("gaps", "")) or term in q.get("terms", []):
            out.append(qid)
    s, kind = all_terms()[term]
    if kind == "class" and term.startswith("rpt:"):       # classes cite their questions in brackets: [CQ1, CQ4-6]
        m = re.search(r"\[(CQ[^\]]*)\]", str(ontology_graph().value(s, SKOS.definition) or ""))
        for i in re.findall(r"CQ(\d+)(?:-(\d+))?", m.group(1) if m else ""):
            out += [f"CQ{n}" for n in range(int(i[0]), int(i[1] or i[0]) + 1)]
    for qid, q in kgctl.CQS["questions"].items():
        if pat.search(q.get("answer", "") + q.get("gaps", "")):
            out.append("flow:" + qid)
    order = lambda x: (x.startswith("flow:"), int(re.sub(r"\D", "", x)))
    return sorted(set(out), key=order)


def describe(term):
    g = ontology_graph()
    s, kind = all_terms()[term]
    d = {"term": term, "kind": kind, "label": str(g.value(s, RDFS.label) or ""), "definition": str(g.value(s, SKOS.definition) or "")}
    if kind == "class":
        d["subclass_of"] = [short(o) for o in g.objects(s, RDFS.subClassOf) if isinstance(o, URIRef)]
        props = {t: p for t, (p, k) in all_terms().items() if k != "class"}
        d["properties"] = [{"term": t, "to": members(g.value(p, RDFS.range))} for t, p in sorted(props.items()) if term in members(g.value(p, RDFS.domain))]
        d["referenced_by"] = [{"term": t, "from": members(g.value(p, RDFS.domain))} for t, p in sorted(props.items()) if term in members(g.value(p, RDFS.range))]
    else:
        d["domain"] = members(g.value(s, RDFS.domain)); d["range"] = members(g.value(s, RDFS.range))
        if g.value(s, OWL.inverseOf) is not None:
            d["inverse_of"] = short(g.value(s, OWL.inverseOf))
    d["questions"] = asked_by(term)
    d["written_in"] = written_in().get(term, [])
    d.update({k: str(g.value(s, p)) for k, p in vocabulary.NOTES if g.value(s, p) is not None})
    d["validated"] = bool(d.get("validated_by"))
    return d


def explain(query=None):
    """One term by name or label ('sourcedFrom', 'rpt:Field', 'sourced from'), or with no query the index of classes."""
    g, terms = ontology_graph(), all_terms()
    norm = lambda x: re.sub(r"[\s_\-]", "", x).lower()
    if not query or not query.strip():
        return {"ontology": versions(),
                "classes": [{"term": t, "label": str(g.value(s, RDFS.label) or ""), "definition": str(g.value(s, SKOS.definition) or "")}
                            for t, (s, k) in sorted(terms.items()) if k == "class"],
                "hint": "explain <term> gives a class's properties, or a property's domain, range, questions and where it is written"}
    q = query.strip()
    pfx, _, local = q.rpartition(":")
    hits = [t for t in terms if norm(t.split(":")[1]) == norm(local)] or [t for t, (s, k) in terms.items() if norm(str(g.value(s, RDFS.label) or "")) == norm(q)]
    if pfx:
        hits = [t for t in hits if t.startswith(pfx + ":")]
    if not hits:
        by_name = {norm(t.split(":")[1]): t for t in terms}
        return {"query": q, "matches": [], "did_you_mean": [by_name[m] for m in difflib.get_close_matches(norm(local), list(by_name), n=5, cutoff=0.6)]}
    return {"query": q, "matches": [describe(t) for t in sorted(hits)]}


# ───────────────────────────── questions ─────────────────────────────
def questions(vocabulary=None):
    if vocabulary not in (None, "report", "flow"):
        raise KgError("vocabulary is report or flow")
    out = []
    if vocabulary in (None, "report"):
        for qid, q in semantic.questions()["questions"].items():
            out.append({"id": qid, "vocabulary": "report", "asked_by": q["who"], "question": q["question"],
                        "parameters": [p.lower() for p in semantic.question_params(q)], "reports_gaps": bool(q.get("gaps")),
                        **{k: str(q[k]) for k in ("why", "validated_by", "validated_on") if q.get(k)}})
    if vocabulary in (None, "flow"):
        tasks = kgctl.CQS["task_types"]
        for qid, q in kgctl.CQS["questions"].items():
            out.append({"id": "flow:" + qid, "vocabulary": "flow", "asked_for": [t for t, v in tasks.items() if qid in v["required"] + v["optional"]],
                        "question": q["question"], "parameters": [p.lower() for p in flow_question_params(q)],
                        "reports_gaps": bool(q.get("gaps")), "needs": "a flow root"})
    return {"ontology": versions(), "questions": out}


def flow_question_params(q):
    return sorted(set(re.findall(r"\$([A-Z]+)", q["answer"] + q.get("gaps", ""))))


# ───────────────────────────── the catalogue ─────────────────────────────
_cache = {}


def catalogue_root(arg=None):
    p = arg or os.environ.get("REPORTS_ROOT") or ("reports" if pathlib.Path("reports").is_dir() else None)
    if not p:
        raise KgError("no catalogue: pass --catalogue <folder of report folders>, set REPORTS_ROOT, or run where a reports/ folder exists")
    p = pathlib.Path(p).expanduser().resolve()
    if not p.is_dir():
        raise KgError(f"catalogue folder {p} does not exist")
    return p


def catalogue(root):
    """Every report under root, validated and compiled in memory →
    {reports: [{id, folder}], skipped: [{report, errors}], data: the instance graph, graph: instances + ontologies}."""
    dirs = semantic.report_dirs(root)
    watched = [f for d in dirs for f in (*d.glob("*.yaml"), d.parent / "manifest.json")] + [*ONT.iterdir(), *SCHEMAS.iterdir()]
    key = (str(root), tuple(sorted((str(f), f.stat().st_mtime_ns) for f in watched if f.exists())))
    if _cache.get("catalogue", (None,))[0] == key:
        return _cache["catalogue"][1]
    reports, skipped, graphs, seen = [], [], [], {}
    for d in dirs:
        files = semantic.load(d)
        problems = [i["message"] for i in semantic.issues(files) if i["level"] == "error"]
        graph = None
        if not problems:
            rid = files["report"]["report"]["id"]
            if rid in seen:
                problems = [f"report id {rid} is already used by {seen[rid]}"]
            else:
                graph, problems = semantic.build_graph(files)
        if problems:
            skipped.append({"report": d.parent.name, "lifecycle_status": lifecycle_status(files), "errors": problems}); continue
        seen[rid] = d.parent.name
        reports.append({"id": rid, "folder": str(d.parent)}); graphs.append(graph)
    data = semantic.graph_of(graphs)
    full = Graph()
    for t in data:
        full.add(t)
    value = {"reports": reports, "skipped": skipped, "data": data, "graph": semantic.with_ontologies(full)}
    _cache["catalogue"] = (key, value)
    return value


def lifecycle_status(files):
    """The current status a report's own files record, readable even when the report does not compile yet."""
    log = (files.get("provenance") or {}).get("lifecycle") or []
    last = log[-1] if log and isinstance(log[-1], dict) else {}
    return last.get("status")


def flow_graph(flow_dir=None):
    try:
        root = flow_root(flow_dir)
    except SystemExit as e:
        raise KgError(str(e))
    key = (str(root), (root / "flow" / "flow.json").stat().st_mtime_ns, tuple(f.stat().st_mtime_ns for f in sorted(ONT.iterdir())))
    if _cache.get("flow", (None,))[0] != key:
        kgctl.FLOW_ROOT = root
        with contextlib.redirect_stdout(io.StringIO()):       # build prints its statistics; our output is JSON only
            _cache["flow"] = (key, kgctl.build())
    return _cache["flow"][1]


def ask(question, params=None, catalogue_dir=None, flow_dir=None):
    """One competency question → {id, vocabulary, question, status, rows, gaps}. Flow questions are named flow:CQ04."""
    params = {k.upper(): v for k, v in (params or {}).items() if v}
    vocab, _, qid = question.strip().rpartition(":")
    qid = qid.upper()
    if vocab.lower() == "flow":
        cqs = kgctl.CQS["questions"]
        if qid not in cqs:
            raise KgError(f"unknown flow question {qid}; known: {', '.join('flow:' + k for k in cqs)}")
        missing = [m for m in flow_question_params(cqs[qid]) if m not in params]
        if missing:
            raise KgError(f"flow:{qid} needs: " + ", ".join(m.lower() for m in missing))
        r = kgctl.ask(flow_graph(flow_dir), qid, {k: kgctl.PT + FLOW_PARAMS[k] + v for k, v in params.items() if k in FLOW_PARAMS}, True)
        return {"id": "flow:" + qid, "vocabulary": "flow", "question": r["question"], "status": r["status"],
                "rows": [{k: v for k, v in row.items() if v is not None} for row in r["answer"]], "gaps": r["gaps"]}
    cat = catalogue(catalogue_root(catalogue_dir))
    known = [x["id"] for x in cat["reports"]]
    if "REPORT" in params and params["REPORT"] not in known:
        bad = next((s for s in cat["skipped"] if s["report"] == params["REPORT"]), None)
        raise KgError(f"report {params['REPORT']} fails validation: " + "; ".join(bad["errors"][:5]) if bad else
                      f"unknown report {params['REPORT']}; known: {', '.join(known) or 'none'}")
    try:
        r = semantic.run_question(cat["graph"], qid, params)
    except ValueError as e:
        raise KgError(str(e).replace("needs --", "needs: ").replace(", --", ", "))
    return {"id": r["id"], "vocabulary": "report", "asked_by": r["who"], "question": r["question"], "status": r["status"],
            "rows": r["rows"], "gaps": r["gaps"], "reports": known, "skipped": cat["skipped"]}


# ───────────────────────────── requirements ─────────────────────────────
def requirements(provided_by=None):
    """Everything a report's files hold, from the four schemas: where it is written, whether it is required,
    who provides it, and what it means (the definition of its ontology term)."""
    if provided_by not in (None, *PROVIDERS):
        raise KgError("provided-by is one of: " + ", ".join(PROVIDERS))
    g, items = ontology_graph(), []

    def meaning(term):
        if not term or term == "rdfs:label":
            return "The name of the item." if term else None
        d = g.value(URIRef(expand(term)), SKOS.definition)
        return str(d) if d is not None else None

    def resolve(root, node):
        while "$ref" in node:
            node = {**root["$defs"][node["$ref"].split("/")[-1]], **{k: v for k, v in node.items() if k != "$ref"}}
        return node

    def walk(root, name, node, path, required, when, provider):
        """required: in its parent. when: the condition under which the node applies at all (None = always)."""
        node = resolve(root, node)
        provider = node.get("x-provided-by", provider)
        whole = node.get("x-emit") == "json"                 # written as one value, however deep
        ap, its = node.get("additionalProperties"), node.get("items")
        inner = when if required or not path else f"{path} is given"
        if node.get("properties") and not whole:
            for k, ps in node["properties"].items():
                walk(root, name, ps, f"{path}.{k}" if path else k, k in node.get("required", []), inner, provider)
            return
        entries = (ap if isinstance(ap, dict) and not whole and resolve(root, ap).get("properties") else None,
                   its if isinstance(its, dict) and resolve(root, its).get("properties") else None)
        if any(entries):                                     # a set of entries: say that the set exists, then describe one entry
            items.append({k: v for k, v in {
                "file": semantic.FILE_OF[name], "path": path, "required": required, "when": when, "provided_by": provider,
                "type": "entries by name" if entries[0] else "list of entries", "at_least": node.get("minItems"),
                "term": node.get("x-term"), "meaning": meaning(node.get("x-term")), "hint": node.get("description")}.items() if v is not None})
            if entries[0]:
                return walk(root, name, ap, path + ".*", True, f"for each entry of {path}", provider)
            return walk(root, name, its, path + "[]", True, inner if node.get("minItems") else f"for each entry of {path}", provider)
        leaf = resolve(root, its) if isinstance(its, dict) else node
        items.append({k: v for k, v in {
            "file": semantic.FILE_OF[name], "path": path, "required": required, "when": when, "provided_by": provider,
            "type": node.get("type"), "allowed": leaf.get("enum"), "pattern": leaf.get("pattern"),
            "term": node.get("x-term") or node.get("x-class"), "meaning": meaning(node.get("x-term")), "hint": node.get("description")}.items() if v is not None})

    for name in ("report", "lineage", "manifest", "provenance"):
        sch = semantic.schema(name)
        walk(sch, name, sch, "", True, None, sch.get("x-provided-by", "analyst"))
    if provided_by:
        items = [i for i in items if i["provided_by"] == provided_by]
    return {"ontology": versions(), "provided_by": PROVIDERS, "count": len(items), "items": items}


# ───────────────────────────── gaps ─────────────────────────────
def report_folder(report, catalogue_dir=None):
    """A report's semantic/ folder, from a path to the report folder (or its semantic/), or a folder name in the catalogue."""
    p = pathlib.Path(report).expanduser()
    if not p.exists():
        if os.sep in str(report):
            raise KgError(f"no report folder at {report}")
        p = catalogue_root(catalogue_dir) / report
        if not p.exists():
            raise KgError(f"no report folder {report} in the catalogue {p.parent}")
    return (p if p.name == "semantic" or (p / "report.yaml").exists() else p / "semantic").resolve()


def gaps(report, catalogue_dir=None):
    """What a draft report still lacks. blocking = it cannot be compiled or cannot answer a question;
    warnings = it answers with a gap. Each item says where the missing answer is written."""
    d = report_folder(report, catalogue_dir)
    files = semantic.load(d)
    found = semantic.issues(files)
    item = lambda i: {"source": "validation", "file": i["file"], "path": i["path"], "message": i["message"]}
    blocking = [item(i) for i in found if i["level"] == "error"]
    warnings = [item(i) for i in found if i["level"] == "warn"]
    rid = ((files["report"] or {}).get("report") or {}).get("id")
    shapes_checked = False
    if not blocking:
        graph, problems = semantic.build_graph(files)
        blocking += [{"source": "compile", "message": m} for m in problems]
        if graph:
            shapes_checked = True
            _, results = semantic.shape_results(semantic.with_ontologies(semantic.graph_of([graph])))
            grouped = {}
            for r in results:
                term = short(r["path"]) if r["path"] else None
                g = grouped.setdefault((r["severity"], r["message"], term), [])
                g.append(r["node"].split("/kg/")[-1].replace(f"report/{rid}/", "", 1) or "report")
            for (sev, message, term), subjects in sorted(grouped.items(), key=lambda kv: (kv[0][0], kv[0][1])):
                entry = {"source": "shape", "message": message, "count": len(subjects), "subjects": sorted(subjects)}
                if term:
                    entry["term"] = term; entry["written_in"] = written_in().get(term, [])
                (blocking if sev == "Violation" else warnings).append(entry)
    count = lambda xs: sum(x.get("count", 1) for x in xs)
    return {"report": rid or d.parent.name, "folder": str(d.parent), "lifecycle_status": lifecycle_status(files),
            "status": "blocked" if blocking else "incomplete" if warnings else "complete",
            "summary": {"blocking": count(blocking), "warnings": count(warnings)}, "shapes_checked": shapes_checked,
            "blocking": blocking, "warnings": warnings, **history_state(files, blocking)}


def history_state(files, blocking=()):
    """The last accepted revision and what the files say beyond it. Pending changes are not gaps: they are the
    definition moving on, and accept (with who and why) is what makes them part of its history."""
    if any(b.get("file") == semantic.FILE_OF["history"] for b in blocking):
        return {"history": None, "pending": None}               # a history that does not validate cannot be replayed
    revs, p = ledger.revisions(files), ledger.pending(files)
    last = {k: revs[-1].get(k) for k in ("revision", "at", "by", "why", "effective")} if revs else None
    return {"history": {"revisions": len(revs), "last": last},
            "pending": None if p is None else {"count": ledger.count(p), **p}}


# ───────────────────────────── navigation: the catalogue as a graph to walk ─────────────────────────────
KG = "https://cynergis.ai/kg/"
NAME_PROPS = ("rpt:reportId", "rpt:fieldId", "rpt:columnName", "rpt:tableName", "rdfs:label", "rpt:label", "rpt:alias")
TYPE_RANK = ("rpt:ReportType", "rpt:Field", "rpt:Section", "rpt:Column", "rpt:Table", "rpt:DataSource", "dt:Component", "rpt:Parameter")
UNSEARCHED = {"rpt:FieldMeaning", "rpt:Change"}        # folded into their field; read through entity and history


def node_id(iri):
    return str(iri)[len(KG):] if str(iri).startswith(KG) else str(iri)


def norm(x):
    return re.sub(r"[\s_\-]+", " ", str(x)).strip().lower()


def rank(n):
    return next((i for i, t in enumerate(TYPE_RANK) if t in n["types"]), len(TYPE_RANK))


def index(cat):
    """{iri: {id, types, label, report, props, names, text}} for every instance of the catalogue, built once per catalogue.
    A field is also known by the labels of its meanings in every locale, and described by their definitions."""
    if "index" in cat:
        return cat["index"]
    g, nodes = cat["data"], {}
    for s in set(g.subjects(RDF.type, None)):
        if isinstance(s, URIRef):
            props = {}
            for p, o in sorted(g.predicate_objects(s)):
                if isinstance(o, Literal):
                    props.setdefault(short(p) + (f"@{o.language}" if o.language else ""), []).append(str(o))
            nodes[str(s)] = {"id": node_id(s), "types": sorted(short(t) for t in g.objects(s, RDF.type)), "props": props, "names": set(), "text": []}
    for s, o in g.subject_objects(URIRef(semantic.RPT + "hasMeaning")):
        if str(s) in nodes and str(o) in nodes:
            m = nodes[str(o)]["props"]
            nodes[str(s)]["names"] |= {norm(v) for v in m.get("rpt:label", [])}
            nodes[str(s)]["text"] += m.get("rpt:label", []) + m.get("rpt:definition", [])
    for iri, n in nodes.items():
        p = n["props"]
        n["names"] |= {norm(v) for k, vs in p.items() if k.split("@")[0] in NAME_PROPS for v in vs} | {norm(n["id"].rstrip("/").rsplit("/", 1)[-1])}
        n["label"] = next((p[k][0] for k in ("rdfs:label", "rdfs:label@en", "rpt:fieldId", "rpt:reportId", "rpt:columnName", "rpt:tableName", "rpt:fact", "rpt:label")
                           if p.get(k)), n["id"].rstrip("/").rsplit("/", 1)[-1])
        m = re.match(r"https://cynergis\.ai/kg/report/([^/]+)/", iri)
        n["report"] = m.group(1) if m else None
        n["text"] += [v for vs in p.values() for v in vs]
    cat["index"] = nodes
    return nodes


def brief(n, **extra):
    return {"id": n["id"], "type": n["types"][0] if len(n["types"]) == 1 else n["types"], "label": n["label"],
            **({"report": n["report"]} if n["report"] else {}), **extra}


def matching_terms(q):
    g = ontology_graph()
    return [{"term": t, "kind": k, "label": str(g.value(s, RDFS.label) or "")} for t, (s, k) in sorted(all_terms().items())
            if norm(t.split(":")[1]) == norm(q).replace(" ", "") or norm(g.value(s, RDFS.label) or "") == norm(q)]


def find(term, report=None, catalogue_dir=None):
    """The entities a name designates, best first: an id, then a name (id, label in any locale, alias, column or table
    name), then the start of a word of a name. Ties go to the more central kind (report, field, section, column…)."""
    if not term or not str(term).strip():
        raise KgError("name something to look up")
    cat = catalogue(catalogue_root(catalogue_dir))
    idx, raw, q = index(cat), str(term).strip(), norm(term)
    part = re.compile(r"\b" + re.escape(q))
    hits = []
    for iri, n in idx.items():
        if (report and n["report"] != report) or set(n["types"]) & UNSEARCHED:
            continue
        if raw in (iri, n["id"]) or ("/" in raw and n["id"].endswith("/" + raw.strip("/"))):
            score, how = 3, "id"
        elif q in n["names"]:
            score, how = 2, "name"
        elif len(q) >= 3 and any(part.search(x) for x in n["names"]):
            score, how = 1, "part of a name"
        else:
            continue
        hits.append((-score, rank(n), n["id"], iri, how))
    return cat, [(iri, how) for *_, iri, how in sorted(hits)]


def resolve(term, report=None, catalogue_dir=None, limit=10):
    """A name in the reader's words → the entities of the catalogue it designates, and the ontology terms of that name."""
    cat, hits = find(term, report, catalogue_dir)
    idx = index(cat)
    out = {"query": term, "entities": [brief(idx[i], matched=how) for i, how in hits[:limit]], "terms": matching_terms(term)}
    if len(hits) > limit:
        out["more"] = len(hits) - limit
    if not hits:
        names = sorted({x for n in idx.values() for x in n["names"]})
        out["did_you_mean"] = difflib.get_close_matches(norm(term), names, n=5, cutoff=0.6)
    return out


def report_files(cat, rid):
    folder = next((r["folder"] for r in cat["reports"] if r["id"] == rid), None)
    return semantic.load(pathlib.Path(folder) / "semantic") if folder else None


def field_changes(revs, fid):
    keep = lambda f: f".fields.{fid}." in f.replace(" → ", ".") or f.endswith(f"fields.{fid}")
    return [{**{k: r.get(k) for k in ("revision", "at", "by", "why", "effective")}, **c}
            for r in revs for c in r.get("changes") or [] if keep(c["fact"])]


def entity(term, report=None, catalogue_dir=None):
    """One entity: its values, its edges both ways with what is at their other end, and, for a report or a field,
    its accepted history and what is not accepted yet. Other entities of the same name are listed, not shown."""
    cat, hits = find(term, report, catalogue_dir)
    idx, g = index(cat), cat["data"]
    if not hits:
        return {"query": term, "entity": None, "terms": matching_terms(term), "did_you_mean": resolve(term, report, catalogue_dir)["did_you_mean"],
                "hint": "search finds text inside meanings, purposes and rules; explain describes ontology terms"}
    iri = hits[0][0]
    n, s = idx[iri], URIRef(iri)
    edge = lambda p, o, key: {"property": short(p), key: node_id(o), **({"label": idx[str(o)]["label"], "type": idx[str(o)]["types"][0]} if str(o) in idx else {})}
    card = {**brief(n), "types": n["types"], "values": n["props"],
            "out": [edge(p, o, "to") for p, o in sorted(g.predicate_objects(s)) if isinstance(o, URIRef) and p != RDF.type],
            "in": [edge(p, x, "from") for x, p in sorted(g.subject_predicates(s)) if isinstance(x, URIRef)]}
    files = report_files(cat, n["report"]) if n["report"] else None
    if files is not None and ("rpt:Field" in n["types"] or "rpt:ReportType" in n["types"]):
        revs = ledger.revisions(files)
        if "rpt:Field" in n["types"]:
            card["history"] = field_changes(revs, n["props"]["rpt:fieldId"][0])
        else:
            card.update(history_state(files))
    return {"query": term, "entity": card, "other_matches": [brief(idx[i], matched=how) for i, how in hits[1:6]]}


def neighbors(term, prop=None, direction="both", depth=1, report=None, catalogue_dir=None):
    """The entities around one, up to depth edges away (at most 3), optionally along one property only."""
    if direction not in ("out", "in", "both"):
        raise KgError("direction is out, in or both")
    depth = max(1, min(int(depth), 3))
    cat, hits = find(term, report, catalogue_dir)
    if not hits:
        raise KgError(f"nothing in the catalogue is called {term!r}; resolve or search may find it")
    idx, g, start = index(cat), cat["data"], hits[0][0]
    wanted = lambda p: prop is None or norm(short(p).split(":")[1]) == norm(prop.split(":")[-1]).replace(" ", "")
    edges, seen, frontier = set(), {start}, {start}
    for _ in range(depth):
        nxt = set()
        for x in frontier:
            if direction in ("out", "both"):
                for p, o in g.predicate_objects(URIRef(x)):
                    if isinstance(o, URIRef) and p != RDF.type and wanted(p):
                        edges.add((x, short(p), str(o))); nxt.add(str(o))
            if direction in ("in", "both"):
                for o, p in g.subject_predicates(URIRef(x)):
                    if isinstance(o, URIRef) and wanted(p):
                        edges.add((str(o), short(p), x)); nxt.add(str(o))
        frontier = nxt - seen; seen |= nxt
    edges = sorted(edges)
    return {"from": brief(idx[start]), "depth": depth, "direction": direction, **({"property": prop} if prop else {}),
            "nodes": {idx[i]["id"]: brief(idx[i]) for i in sorted(seen) if i in idx},
            "edges": [{"source": node_id(a), "property": p, "target": node_id(b)} for a, p, b in edges[:500]],
            **({"truncated": len(edges) - 500} if len(edges) > 500 else {})}


def search(text, type_=None, report=None, limit=10, catalogue_dir=None):
    """Entities whose text holds every word of the query (labels and meanings in every locale, purposes, rules, notes,
    reasons), ranked: a word in a name counts more, the exact phrase most. Ontology terms are searched the same way."""
    words = [w for w in re.findall(r"\w+", (text or "").lower()) if len(w) > 1]
    if not words:
        raise KgError("search needs at least one word")
    has = lambda blob, w: re.search(r"\b" + re.escape(w), blob) is not None
    phrase = " ".join(text.lower().split())
    cat = catalogue(catalogue_root(catalogue_dir))
    hits = []
    for n in index(cat).values():
        if set(n["types"]) & UNSEARCHED or (report and n["report"] != report):
            continue
        if type_ and not any(norm(t.split(":")[-1]) == norm(type_.split(":")[-1]) for t in n["types"]):
            continue
        blob, names = " ".join(n["text"]).lower(), " ".join(n["names"])
        if not all(has(blob, w) or has(names, w) for w in words):
            continue
        score = sum(3 if has(names, w) else 1 for w in words) + (5 if phrase in blob else 0)
        where = next((v for v in n["text"] if phrase in v.lower()), None) or next((v for v in n["text"] if has(v.lower(), words[0])), "")
        hits.append((-score, rank(n), n["id"], brief(n, score=score, snippet=where[:160])))
    g, terms = ontology_graph(), []
    for t, (s, k) in sorted(all_terms().items()):
        blob = f"{t} {g.value(s, RDFS.label) or ''} {g.value(s, SKOS.definition) or ''}".lower()
        if all(has(blob, w) for w in words):
            terms.append({"term": t, "kind": k, "label": str(g.value(s, RDFS.label) or "")})
    hits.sort(key=lambda h: h[:3])
    return {"query": text, "count": len(hits), "entities": [h[3] for h in hits[:limit]], "terms": terms[:5]}


def overview(limit=10, catalogue_dir=None):
    """The map of the catalogue for a question that starts from no entity: what it holds, where each report is, how far
    the mapping has got, what is shared, what changed lately and what is not accepted. A synthesis drawn from it must
    say which of these facts it rests on."""
    from collections import Counter
    cat = catalogue(catalogue_root(catalogue_dir))
    idx, g = index(cat), cat["data"]
    of_type = lambda t: [n for n in idx.values() if t in n["types"]]
    first = lambda n, k: (n["props"].get(k) or [None])[0]
    reports = [{"report": first(n, "rpt:reportId"), "title": n["label"], "status": first(n, "rpt:lifecycleStatus"), "owner": first(n, "rpt:owner")}
               for n in sorted(of_type("rpt:ReportType"), key=lambda n: n["id"])]
    shared = Counter(first(n, "rpt:fieldId") for n in of_type("rpt:Field"))
    used = Counter(idx[str(o)]["label"] for _, o in g.subject_objects(URIRef(semantic.RPT + "renderedBy")) if str(o) in idx)
    revisions, unaccepted, without = [], [], []
    for r in cat["reports"]:
        files = semantic.load(pathlib.Path(r["folder"]) / "semantic")
        revs, p = ledger.revisions(files), ledger.pending(files)
        if not revs:
            without.append(r["id"])
        elif ledger.count(p):
            unaccepted.append({"report": r["id"], "facts": ledger.count(p)})
        revisions += [{"report": r["id"], **{k: v.get(k) for k in ("revision", "at", "by", "why")},
                       **({"facts": len(v["facts"])} if "facts" in v else {"changes": len(v.get("changes") or [])})} for v in revs]
    confirmed = vocabulary.rationale()["summary"]
    return {"ontology": versions(),
            "reports": {"count": len(reports), "by_status": dict(Counter(r["status"] for r in reports)), "list": reports,
                        "skipped": [{"report": s["report"], "errors": len(s["errors"])} for s in cat["skipped"]]},
            "nodes_by_class": dict(Counter(t for n in idx.values() for t in n["types"]).most_common()),
            "edges_by_property": dict(Counter(short(p) for _, p, o in g if isinstance(o, URIRef) and p != RDF.type).most_common(limit)),
            "mapping": dict(Counter(first(n, "rpt:lineageStatus") for n in of_type("rpt:Field"))),
            "shared_fields": [{"field": f, "reports": c} for f, c in sorted(shared.items(), key=lambda x: (-x[1], x[0])) if c > 1][:limit],
            "components": [{"component": c, "sections": k} for c, k in sorted(used.items(), key=lambda x: (-x[1], x[0]))[:limit]],
            "history": {"recent": sorted(revisions, key=lambda x: str(x["at"]), reverse=True)[:limit], "not_accepted": unaccepted, "no_history": without},
            "rationale": {v: {"total": sum(s["total"] for s in groups.values()), "with_why": sum(s["rationale"] for s in groups.values()),
                              "confirmed": sum(s["validated"] for s in groups.values())} for v, groups in confirmed.items()},
            "hint": "a map, not an answer: read the entities it names (entity, neighbors) or ask a question, and cite the facts a synthesis rests on"}


def iso(day, name):
    try:
        return day and datetime.date.fromisoformat(str(day)).isoformat()
    except ValueError:
        raise KgError(f"{name} is a date: YYYY-MM-DD, not {day!r}")


def stale(days=30, today=None, catalogue_dir=None):
    """What is out of date in the catalogue: definitions changed but not accepted, reports with no history, mappings
    proposed but not verified for more than `days`, reports idle in a status other than production for more than `days`,
    and reports left out because they no longer validate."""
    today = iso(today, "today") or datetime.date.today().isoformat()
    age = lambda d: (datetime.date.fromisoformat(today) - datetime.date.fromisoformat(str(d)[:10])).days
    cat, items = catalogue(catalogue_root(catalogue_dir)), []
    for r in cat["reports"]:
        files = semantic.load(pathlib.Path(r["folder"]) / "semantic")
        revs, p = ledger.revisions(files), ledger.pending(files)
        if not revs:
            items.append({"report": r["id"], "kind": "no history", "detail": "no accepted revision: the definition can change without a record"})
        elif ledger.count(p):
            changed = [c["fact"] for k in ("changed", "removed", "added") for c in p[k]]
            items.append({"report": r["id"], "kind": "not accepted", "since": str(revs[-1]["at"])[:10], "facts": len(changed), "first": changed[:5]})
        log = (files["provenance"] or {}).get("lifecycle") or []
        if log and log[-1].get("status") != "in_production" and age(log[-1]["at"]) > days:
            items.append({"report": r["id"], "kind": "status unchanged", "status": log[-1]["status"], "since": str(log[-1]["at"])[:10], "days": age(log[-1]["at"])})
        for fid, v in ((files["lineage"] or {}).get("fields") or {}).items():
            if v.get("status") == "proposed" and revs:
                since = ledger.last_set(revs, ledger.fact_name("lineage", f"fields.{fid}.status"), "proposed")
                if since and age(since[1]) > days:
                    items.append({"report": r["id"], "kind": "mapping not verified", "field": fid, "column": v.get("column"),
                                  "since": since[1], "days": age(since[1]), "revision": since[0]})
    items += [{"report": s["report"], "kind": "fails validation", "detail": s["errors"][0]} for s in cat["skipped"]]
    kinds = {}
    for i in items:
        kinds[i["kind"]] = kinds.get(i["kind"], 0) + 1
    return {"as_of": today, "days": days, "summary": kinds, "items": items}


def history(report, as_of=None, known_on=None, fact=None, catalogue_dir=None):
    """A report's accepted revisions and what is pending; or, with as_of (the date the revisions apply from) or
    known_on (the date they were recorded by), the definition as it stood then. fact keeps the facts whose name holds it."""
    as_of, known_on = iso(as_of, "as_of"), iso(known_on, "known_on")
    d = report_folder(report, catalogue_dir)
    files = semantic.load(d)
    problems = [i["message"] for i in semantic.issues(files) if i["file"] == semantic.FILE_OF["history"] and i["level"] == "error"]
    if problems:
        raise KgError("the history does not validate: " + "; ".join(problems[:3]))
    rid = ((files["report"] or {}).get("report") or {}).get("id") or d.parent.name
    revs, keep = ledger.revisions(files), (lambda f: fact is None or fact in f)
    if not revs:
        return {"report": rid, "revisions": [], "pending": None, "hint": "no accepted revision: `semantic.py accept <report> --by <you>` records one"}
    if as_of or known_on:
        state = {k: v for k, v in ledger.replay(revs, as_of, known_on).items() if keep(k)}
        applied = [r["revision"] for r in revs if (not as_of or str(r.get("effective") or r["at"])[:10] <= as_of)
                   and (not known_on or str(r["at"])[:10] <= known_on)]
        return {"report": rid, **({"as_of": as_of} if as_of else {}), **({"known_on": known_on} if known_on else {}),
                "revisions_applied": applied, "count": len(state), "facts": state}
    out = []
    for r in revs:
        s = ledger.summary(r)
        if "facts" in r and fact:
            s["facts"] = {k: v for k, v in r["facts"].items() if keep(k)}
        if "changes" in s:
            s["changes"] = [c for c in s["changes"] if keep(c["fact"])]
            if fact and not s["changes"]:
                continue
        out.append(s)
    p = ledger.pending(files)
    p = {k: [c for c in v if keep(c["fact"])] for k, v in p.items()}
    return {"report": rid, "revisions": out, "pending": {"count": ledger.count(p), **p}}


# ───────────────────────────── SQLite export ─────────────────────────────
SCHEMA_SQL = """
CREATE TABLE nodes (id TEXT PRIMARY KEY, type TEXT NOT NULL, label TEXT, report TEXT, properties TEXT NOT NULL);
CREATE TABLE edges (source TEXT NOT NULL, property TEXT NOT NULL, target TEXT NOT NULL, PRIMARY KEY (source, property, target));
CREATE TABLE terms (term TEXT PRIMARY KEY, iri TEXT NOT NULL, vocabulary TEXT NOT NULL, kind TEXT NOT NULL, label TEXT, definition TEXT, domain TEXT, range TEXT,
                    rationale TEXT, validated_by TEXT, validated_on TEXT);
CREATE TABLE questions (id TEXT PRIMARY KEY, vocabulary TEXT NOT NULL, question TEXT NOT NULL, parameters TEXT, answer_query TEXT, gaps_query TEXT);
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE INDEX edges_target ON edges (target, property);
CREATE INDEX nodes_type ON nodes (type);
CREATE INDEX nodes_report ON nodes (report);
"""


def instance_rows(g):
    """(nodes, edges) of a graph's instances: every IRI typed with a class of ours that the ontology itself does not declare.
    A node keeps its literal values as JSON; an edge is a link to another IRI, named by the property that explains it (terms.term)."""
    declared = set(ontology_graph().subjects())
    ours = lambda t: any(str(t).startswith(ns) for ns in VOCAB.values())
    nodes, edges = [], []
    for s in sorted(set(g.subjects(RDF.type, None))):
        types = sorted(short(t) for t in g.objects(s, RDF.type) if ours(t))
        if not isinstance(s, URIRef) or s in declared or not types:
            continue
        props, label = {}, None
        for p, o in sorted(g.predicate_objects(s)):
            if p == RDF.type:
                continue
            if isinstance(o, Literal):
                props.setdefault(short(p) + (f"@{o.language}" if o.language else ""), []).append(str(o))
                if p == RDFS.label and (label is None or o.language in (None, "en")):
                    label = str(o)
            elif isinstance(o, URIRef):
                edges.append((str(s), short(p), str(o)))
        m = re.match(r"https://cynergis\.ai/kg/report/([^/]+)/", str(s))
        nodes.append((str(s), " ".join(types), label or str(s).rstrip("/").rsplit("/", 1)[-1], m.group(1) if m else None,
                      json.dumps(props, ensure_ascii=False, sort_keys=True)))
    return nodes, sorted(set(edges))


def export_sqlite(catalogue_dir=None, out=None, with_flow=False, flow_dir=None):
    """The validated catalogue (and the flow graph, when asked for) as one SQLite file: read-only, rebuilt each time.
    Refuses when a report fails validation or breaks a shape: nothing is exported unless everything passes."""
    cat = catalogue(catalogue_root(catalogue_dir))
    if cat["skipped"]:
        raise KgError("refusing to export: " + "; ".join(f"{s['report']} fails validation ({len(s['errors'])} error(s))" for s in cat["skipped"]))
    violations = [r for r in semantic.shape_results(cat["graph"])[1] if r["severity"] == "Violation"]
    if violations:
        raise KgError(f"refusing to export: {len(violations)} shape violation(s), first: {violations[0]['node']} — {violations[0]['message']}")
    nodes, edges = instance_rows(cat["data"])
    if with_flow:
        fn, fe = instance_rows(flow_graph(flow_dir))
        nodes, edges = nodes + fn, sorted(set(edges + fe))
    g = ontology_graph()
    note = lambda s, p: str(g.value(s, p)) if g.value(s, p) is not None else None
    terms = [(t, str(s), t.split(":")[0], k, str(g.value(s, RDFS.label) or ""), str(g.value(s, SKOS.definition) or ""),
              " | ".join(members(g.value(s, RDFS.domain))) or None, " | ".join(members(g.value(s, RDFS.range))) or None,
              note(s, vocabulary.META.rationale), note(s, vocabulary.META.validatedBy), note(s, vocabulary.META.validatedOn))
             for t, (s, k) in sorted(all_terms().items())]
    rq, fq = semantic.questions()["questions"], kgctl.CQS["questions"]
    qs = [(qid, "report", q["question"], ",".join(p.lower() for p in semantic.question_params(q)), q["answer"], q.get("gaps")) for qid, q in rq.items()]
    qs += [("flow:" + qid, "flow", q["question"], ",".join(p.lower() for p in flow_question_params(q)), q["answer"], q.get("gaps")) for qid, q in fq.items()]
    v = versions()
    meta = {"report_ontology_version": v["report"], "flow_ontology_version": v["flow"], "doctemplate_ontology_version": v["doctemplate"],
            "exported_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
            "reports": ",".join(r["id"] for r in cat["reports"]), "includes_flow": str(with_flow).lower()}
    out = pathlib.Path(out) if out else BUILD / "catalogue.db"
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    tmp.unlink(missing_ok=True)
    db = sqlite3.connect(tmp)
    with db:
        db.executescript(SCHEMA_SQL)
        db.executemany("INSERT INTO nodes VALUES (?,?,?,?,?)", nodes)
        db.executemany("INSERT INTO edges VALUES (?,?,?)", edges)
        db.executemany("INSERT INTO terms VALUES (?,?,?,?,?,?,?,?,?,?,?)", terms)
        db.executemany("INSERT INTO questions VALUES (?,?,?,?,?,?)", qs)
        db.executemany("INSERT INTO meta VALUES (?,?)", meta.items())
    db.close()
    os.replace(tmp, out)
    return {"out": str(out), "reports": [r["id"] for r in cat["reports"]], "includes_flow": with_flow,
            "nodes": len(nodes), "edges": len(edges), "terms": len(terms), "questions": len(qs)}


if __name__ == "__main__":
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--catalogue", help="folder of report folders (or set REPORTS_ROOT)")
    common.add_argument("--flow-root", help="folder holding flow/flow.json (or set FLOW_ROOT)")
    ap = argparse.ArgumentParser(description="Query surface of the report ontology; every command prints JSON.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    add = lambda name: sub.add_parser(name, parents=[common])
    add("questions").add_argument("--vocabulary", choices=["report", "flow"])
    p = add("ask"); p.add_argument("question")
    PARAMS = ("report", "field", "column", "component", "step", "param", "artifact")
    for name in PARAMS:
        p.add_argument("--" + name)
    add("explain").add_argument("term", nargs="?")
    add("requirements").add_argument("--provided-by", choices=list(PROVIDERS))
    add("gaps").add_argument("report", help="report folder, or its name in the catalogue")
    p = add("export-sqlite"); p.add_argument("--out"); p.add_argument("--with-flow", action="store_true", help="also export the flow graph")
    for name in ("resolve", "entity", "neighbors"):
        p = add(name); p.add_argument("term"); p.add_argument("--report")
        if name == "neighbors":
            p.add_argument("--property"); p.add_argument("--direction", default="both", choices=["out", "in", "both"]); p.add_argument("--depth", type=int, default=1)
    p = add("search"); p.add_argument("text"); p.add_argument("--type"); p.add_argument("--report"); p.add_argument("--limit", type=int, default=10)
    add("overview").add_argument("--limit", type=int, default=10)
    p = add("stale"); p.add_argument("--days", type=int, default=30); p.add_argument("--today", help="YYYY-MM-DD (default: today)")
    p = add("history"); p.add_argument("report"); p.add_argument("--as-of"); p.add_argument("--known-on"); p.add_argument("--fact")
    a = ap.parse_args()
    try:
        if a.cmd == "questions": r = questions(a.vocabulary)
        elif a.cmd == "ask": r = ask(a.question, {k: getattr(a, k) for k in PARAMS}, a.catalogue, a.flow_root)
        elif a.cmd == "explain": r = explain(a.term)
        elif a.cmd == "requirements": r = requirements(a.provided_by)
        elif a.cmd == "gaps": r = gaps(a.report, a.catalogue)
        elif a.cmd == "resolve": r = resolve(a.term, a.report, a.catalogue)
        elif a.cmd == "entity": r = entity(a.term, a.report, a.catalogue)
        elif a.cmd == "neighbors": r = neighbors(a.term, a.property, a.direction, a.depth, a.report, a.catalogue)
        elif a.cmd == "search": r = search(a.text, a.type, a.report, a.limit, a.catalogue)
        elif a.cmd == "overview": r = overview(a.limit, a.catalogue)
        elif a.cmd == "stale": r = stale(a.days, a.today, a.catalogue)
        elif a.cmd == "history": r = history(a.report, a.as_of, a.known_on, a.fact, a.catalogue)
        else: r = export_sqlite(a.catalogue, a.out, a.with_flow, a.flow_root)
    except KgError as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False)); sys.exit(2)
    print(json.dumps(r, indent=1, ensure_ascii=False))
