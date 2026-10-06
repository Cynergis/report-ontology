"""vocabulary — what a change to the ontology breaks, and why each term exists.

The vocabularies (rpt:, flow:, dt:, meta:), their SHACL shapes and their competency questions are the contract every
consumer pins. ontology/ontology.lock.json holds them as last accepted; `kgctl.py ontology check` compares the files
with it and sorts every difference:

  breaking   a consumer or an existing report can fail: a term removed, a domain or range narrowed, a Violation
             constraint added, removed or changed, a question removed, or its parameters or answer columns changed
  additive   new capability, nothing invalidated: a term, a question or an answer column added, a domain or range
             widened, a Warning constraint, a Violation shape on classes added in the same change, a query rewritten
  cosmetic   wording: labels, definitions, messages, rationale, confirmations

and refuses a version that does not say so: breaking needs the next major, additive the next minor (on 0.x, one step
lower). Each breaking change is counted against the catalogue: how many nodes, triples or violations it touches.
`kgctl.py ontology accept --by <you>` writes the lock and appends what was accepted to ontology/changelog.yaml.

The rationale is written next to what it explains (meta:rationale, meta:alternatives, meta:validatedBy,
meta:validatedOn on terms and node shapes; why, validated_by, validated_on on questions). `kgctl.py rationale`
counts what is recorded and what a person confirmed.
"""
import datetime, hashlib, json, re
import yaml
from rdflib import Graph, Namespace, URIRef, BNode, Literal, RDF, RDFS, OWL
from rdflib.collection import Collection
from rdflib.namespace import SKOS
from rdflib.plugins.sparql import prepareQuery

from paths import ONT, QUESTIONS

META = Namespace("https://cynergis.ai/ont/meta#")
SH = Namespace("http://www.w3.org/ns/shacl#")
NS = {"rpt": "https://cynergis.ai/ont/report#", "dt": "https://cynergis.ai/ont/doctemplate#", "flow": "https://cynergis.ai/ont/flow#",
      "meta": str(META), "sh": str(SH), "rdf": str(RDF), "rdfs": str(RDFS), "owl": str(OWL), "skos": str(SKOS),
      "xsd": "http://www.w3.org/2001/XMLSchema#", "dct": "http://purl.org/dc/terms/", "prov": "http://www.w3.org/ns/prov#",
      "pt": "https://cynergis.ai/kg/pdf-to-template/"}
PREFIX_OF = {"report": "rpt", "flow": "flow", "doctemplate": "dt", "meta": "meta"}         # vocabulary → prefix
VOCABULARY_OF = {p: v for v, p in PREFIX_OF.items()}
ONTOLOGY_IRI = {v: "https://cynergis.ai/ont/" + v for v in PREFIX_OF}
TERM_FILES = ("report.ttl", "ontology.ttl", "meta.ttl")
SHAPE_FILES = {"report-shapes.ttl": "report", "shapes.ttl": "flow"}
QUESTION_FILES = {"report_cq.yaml": ("report", "version"), "competency_questions.yaml": ("flow", "ontology_version")}
KIND = {OWL.Class: "class", OWL.ObjectProperty: "object property", OWL.DatatypeProperty: "datatype property",
        OWL.AnnotationProperty: "annotation property"}
NOTES = (("rationale", META.rationale), ("alternatives", META.alternatives), ("validated_by", META.validatedBy), ("validated_on", META.validatedOn))
BREAKING, ADDITIVE, COSMETIC = "breaking", "additive", "cosmetic"
ORDER = {BREAKING: 0, ADDITIVE: 1, COSMETIC: 2}
LOCK, CHANGELOG = "ontology.lock.json", "changelog.yaml"
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def short(iri):
    s = str(iri)
    for pfx, ns in sorted(NS.items(), key=lambda kv: -len(kv[1])):
        if s.startswith(ns):
            return f"{pfx}:{s[len(ns):]}"
    return s


def expand(term):
    pfx, _, local = term.partition(":")
    return NS.get(pfx, pfx + ":") + local


# ───────────────────────────── snapshot: the contract as it stands in the files ─────────────────────────────
def ontology_graph(ont=ONT):
    g = Graph()
    for name in TERM_FILES:
        if (ont / name).exists():
            g.parse(ont / name)
    return g


def members(g, node):
    """A class, or the members of a union of classes, as sorted prefixed names."""
    if node is None:
        return []
    union = g.value(node, OWL.unionOf)
    return sorted(short(x) for x in Collection(g, union)) if union is not None else [short(node)]


def notes(g, s):
    return {k: str(g.value(s, p)) for k, p in NOTES if g.value(s, p) is not None}


def terms(g):
    out = {}
    for T, kind in KIND.items():
        for s in g.subjects(RDF.type, T):
            t = short(s)
            if not isinstance(s, URIRef) or t.split(":")[0] not in VOCABULARY_OF:
                continue
            d = {"kind": kind, "label": str(g.value(s, RDFS.label) or ""), "definition": str(g.value(s, SKOS.definition) or "")}
            if kind == "class":
                d["subclass_of"] = sorted(short(o) for o in g.objects(s, RDFS.subClassOf) if isinstance(o, URIRef))
            elif kind != "annotation property":
                d["domain"], d["range"] = members(g, g.value(s, RDFS.domain)), members(g, g.value(s, RDFS.range))
                inverse = g.value(s, OWL.inverseOf)
                d["inverse_of"] = short(inverse) if inverse is not None else None
                d["subproperty_of"] = sorted(short(o) for o in g.objects(s, RDFS.subPropertyOf))
            out[t] = {**d, **notes(g, s)}
    return dict(sorted(out.items()))


def plain(g, o):
    """A SHACL parameter as JSON data: an RDF list becomes a list, a nested shape a mapping."""
    if o == RDF.nil:
        return []
    if isinstance(o, BNode):
        if g.value(o, RDF.first) is not None:
            return [plain(g, x) for x in Collection(g, o)]
        return {short(p): plain(g, v) for p, v in sorted(g.predicate_objects(o))}
    if isinstance(o, Literal):
        v = o.toPython()
        return v if isinstance(v, (bool, int, float, str)) else str(o)
    return short(o)


def shapes(ont=ONT):
    """{file#Shape: {vocabulary, targets, constraints: {key: signature}, rationale…}} for every named node shape.
    A property constraint is keyed by its path, a SPARQL constraint by its query, so a reworded message stays the
    same constraint. A constraint's severity is its own (SHACL's default is Violation)."""
    out = {}
    for name, vocab in SHAPE_FILES.items():
        g = Graph(); g.parse(ont / name)
        for s in sorted(x for x in g.subjects(RDF.type, SH.NodeShape) if isinstance(x, URIRef)):
            constraints = {}
            props = sorted(({short(k): plain(g, v) for k, v in g.predicate_objects(p)} for p in g.objects(s, SH.property)),
                           key=lambda d: json.dumps(d, sort_keys=True, default=str))
            for sig in props:
                key = f"property {json.dumps(sig.pop('sh:path'), default=str).strip(chr(34))}"
                n = 2
                while key in constraints:
                    key = re.sub(r" #\d+$", "", key) + f" #{n}"; n += 1
                sig.setdefault("sh:severity", "sh:Violation")
                constraints[key] = sig
            for q in g.objects(s, SH.sparql):
                select = " ".join(str(g.value(q, SH.select)).split())
                constraints["sparql " + hashlib.sha1(select.encode()).hexdigest()[:10]] = {
                    "sh:select": select, "sh:message": str(g.value(q, SH.message) or ""), "sh:severity": short(g.value(q, SH.severity) or SH.Violation)}
            out[f"{name}#{str(s).rpartition('#')[2]}"] = {"vocabulary": vocab, "targets": sorted(short(t) for t in g.objects(s, SH.targetClass)),
                                                          "constraints": constraints, **notes(g, s)}
    return out


def digest(text):
    return hashlib.sha1(" ".join((text or "").split()).encode()).hexdigest()[:12]


def columns(query):
    """The names of the columns a question's answer returns: what a consumer reads from each row."""
    return [str(v) for v in prepareQuery(query, initNs=NS).algebra["PV"]]


def questions(qdir=QUESTIONS):
    out, versions = {}, {}
    for name, (vocab, version_key) in QUESTION_FILES.items():
        doc = yaml.safe_load((qdir / name).read_text())
        versions[vocab] = str(doc.get(version_key))
        tasks = doc.get("task_types", {})
        for qid, q in doc["questions"].items():
            d = {"vocabulary": vocab, "question": q["question"],
                 "who": q.get("who") or sorted(t for t, v in tasks.items() if qid in v.get("required", []) + v.get("optional", [])),
                 "parameters": sorted(set(re.findall(r"\$([A-Z]+)", q["answer"] + q.get("gaps", "")))),
                 "columns": columns(doc.get("prefixes", "") + q["answer"]), "answer": digest(q["answer"]), "gaps": digest(q.get("gaps"))}
            if q.get("gate"):
                d["gate"] = q["gate"]
            d.update({k: str(q[k]) for k in ("why", "validated_by", "validated_on") if q.get(k)})
            out[("" if vocab == "report" else "flow:") + qid] = d
    return out, versions


def snapshot(ont=ONT, qdir=QUESTIONS):
    g = ontology_graph(ont)
    qs, qversions = questions(qdir)
    return {"versions": {v: str(g.value(URIRef(iri), OWL.versionInfo)) for v, iri in ONTOLOGY_IRI.items() if g.value(URIRef(iri), OWL.versionInfo)},
            "question_versions": qversions, "terms": terms(g), "shapes": shapes(ont), "questions": qs}


# ───────────────────────────── diff: what a change does ─────────────────────────────
def change(vocab, severity, kind, subject, detail=""):
    return {"vocabulary": vocab, "severity": severity, "kind": kind, "subject": subject, **({"detail": detail} if detail else {})}


def words(xs):
    return " | ".join(xs) if isinstance(xs, list) else str(xs)


def note_changes(vocab, subject, a, b):
    """Rationale and confirmations: never a change of meaning, always worth seeing."""
    out = []
    if (a.get("rationale"), a.get("alternatives")) != (b.get("rationale"), b.get("alternatives")):
        out.append(change(vocab, COSMETIC, "rationale changed" if a.get("rationale") else "rationale recorded", subject))
    if (a.get("validated_by"), a.get("validated_on")) != (b.get("validated_by"), b.get("validated_on")):
        out.append(change(vocab, COSMETIC, "validated", subject, f"by {b['validated_by']} on {b.get('validated_on')}") if b.get("validated_by")
                   else change(vocab, COSMETIC, "validation withdrawn", subject))
    return out


def term_changes(old, new):
    out, added = [], set(new) - set(old)
    for t in sorted(added):
        out.append(change(VOCABULARY_OF[t.split(":")[0]], ADDITIVE, f"{new[t]['kind']} added", t))
    for t in sorted(set(old) - set(new)):
        out.append(change(VOCABULARY_OF[t.split(":")[0]], BREAKING, f"{old[t]['kind']} removed", t, "instances or triples using it are no longer declared"))
    for t in sorted(set(old) & set(new)):
        a, b, v = old[t], new[t], VOCABULARY_OF[t.split(":")[0]]
        if a["kind"] != b["kind"]:
            out.append(change(v, BREAKING, "kind changed", t, f"{a['kind']} → {b['kind']}")); continue
        for k in ("domain", "range"):
            if a.get(k) != b.get(k):
                wider = set(a[k]) < set(b[k])         # a union that gained members: nothing written before becomes wrong
                out.append(change(v, ADDITIVE if wider else BREAKING, f"{k} {'widened' if wider else 'changed'}", t, f"{words(a[k])} → {words(b[k])}"))
        if a.get("subclass_of") != b.get("subclass_of"):
            out.append(change(v, BREAKING, "superclass changed", t, f"{words(a['subclass_of'])} → {words(b['subclass_of'])}"))
        for k in ("inverse_of", "subproperty_of"):
            if a.get(k) != b.get(k):
                out.append(change(v, ADDITIVE, k.replace("_", " ") + " changed", t, f"{words(a.get(k))} → {words(b.get(k))}"))
        for k in ("label", "definition"):
            if a.get(k) != b.get(k):
                out.append(change(v, COSMETIC, f"{k} changed", t))
        out += note_changes(v, t, a, b)
    return out, added


def shape_changes(old, new, new_terms):
    out = []
    violation = lambda sig: sig.get("sh:severity") == "sh:Violation"
    for k in sorted(set(new) - set(old)):
        s = new[k]
        hard = any(violation(c) for c in s["constraints"].values()) and not set(s["targets"]) <= new_terms
        out.append(change(s["vocabulary"], BREAKING if hard else ADDITIVE, "shape added", k,
                          "existing data may now fail it" if hard else "applies to new classes, or warns only"))
    for k in sorted(set(old) - set(new)):
        s = old[k]
        out.append(change(s["vocabulary"], BREAKING if any(violation(c) for c in s["constraints"].values()) else ADDITIVE, "shape removed", k,
                          "consumers lose the guarantees it gave"))
    for k in sorted(set(old) & set(new)):
        a, b, v = old[k], new[k], new[k]["vocabulary"]
        if a["targets"] != b["targets"]:
            out.append(change(v, BREAKING, "shape targets changed", k, f"{words(a['targets'])} → {words(b['targets'])}"))
        ca, cb = a["constraints"], b["constraints"]
        for c in sorted(set(cb) - set(ca)):           # even on a new property: minCount 1 fails every report written before it
            out.append(change(v, BREAKING if violation(cb[c]) else ADDITIVE, "constraint added", f"{k} {c}", cb[c].get("sh:message", "")))
        for c in sorted(set(ca) - set(cb)):
            out.append(change(v, BREAKING if violation(ca[c]) else ADDITIVE, "constraint removed", f"{k} {c}", ca[c].get("sh:message", "")))
        for c in sorted(set(ca) & set(cb)):
            if ca[c] == cb[c]:
                continue
            same = {x: y for x, y in ca[c].items() if x != "sh:message"} == {x: y for x, y in cb[c].items() if x != "sh:message"}
            sev = COSMETIC if same else BREAKING if violation(ca[c]) or violation(cb[c]) else ADDITIVE
            out.append(change(v, sev, "message changed" if same else "constraint changed", f"{k} {c}"))
        out += note_changes(v, k, a, b)
    return out


def question_changes(old, new):
    out = []
    for q in sorted(set(new) - set(old)):
        out.append(change(new[q]["vocabulary"], ADDITIVE, "question added", q, new[q]["question"]))
    for q in sorted(set(old) - set(new)):
        out.append(change(old[q]["vocabulary"], BREAKING, "question removed", q, "a consumer that asks it gets an error"))
    for q in sorted(set(old) & set(new)):
        a, b, v = old[q], new[q], new[q]["vocabulary"]
        if a["parameters"] != b["parameters"]:
            out.append(change(v, BREAKING, "parameters changed", q, f"{words(a['parameters'])} → {words(b['parameters'])}"))
        gone, came = [c for c in a["columns"] if c not in b["columns"]], [c for c in b["columns"] if c not in a["columns"]]
        if gone:
            out.append(change(v, BREAKING, "answer columns removed", q, ", ".join(gone)))
        if came:
            out.append(change(v, ADDITIVE, "answer columns added", q, ", ".join(came)))
        if (a["answer"], a["gaps"], a.get("gate")) != (b["answer"], b["gaps"], b.get("gate")) and not (gone or came):
            out.append(change(v, ADDITIVE, "query changed", q, "same columns; the rows it returns may differ"))
        if (a["question"], a["who"]) != (b["question"], b["who"]):
            out.append(change(v, COSMETIC, "question reworded", q))
        out += note_changes(v, q, a, b)
    return out


def diff(old, new):
    """Every difference from the lock to the files, most severe first."""
    out, added = term_changes(old["terms"], new["terms"])
    out += shape_changes(old["shapes"], new["shapes"], added)
    out += question_changes(old["questions"], new["questions"])
    return sorted(out, key=lambda c: (ORDER[c["severity"]], c["vocabulary"], c["kind"], c["subject"]))


def semver(v):
    return tuple(int(x) for x in re.findall(r"\d+", str(v))[:3])


def needed(version, severity):
    M, m, p = semver(version)
    if severity == BREAKING:
        return (M + 1, 0, 0) if M else (0, m + 1, 0)
    if severity == ADDITIVE:
        return (M, m + 1, 0) if M else (0, m, p + 1)
    return (M, m, p)


def version_problems(old, new, changes):
    """A version that does not say what changed, or questions written for another version."""
    out = []
    for vocab, b in new["versions"].items():
        a = old["versions"].get(vocab)
        if a is None:
            continue
        worst = min((c["severity"] for c in changes if c["vocabulary"] == vocab), key=ORDER.get, default=None)
        if semver(b) < semver(a):
            out.append(f"{vocab}: version went back from {a} to {b}")
        elif worst and semver(b) < needed(a, worst):
            out.append(f"{vocab}: {worst} change(s) since {a} need version {'.'.join(map(str, needed(a, worst)))} or later; the files say {b}")
    for vocab, qv in new["question_versions"].items():
        if new["versions"].get(vocab) and qv != new["versions"][vocab]:
            file = next(f for f, (v, _) in QUESTION_FILES.items() if v == vocab)
            out.append(f"questions/{file} is written for {vocab} {qv}; the ontology is {new['versions'][vocab]}")
    return out


def reconfirm(old, new, changes):
    """What a person confirmed before its meaning changed: the confirmation covers the old text, not this one."""
    out = []
    for c in changes:
        if c["severity"] == COSMETIC and c["kind"] not in ("definition changed",):
            continue
        subject = c["subject"].split(" ")[0]
        for part in ("terms", "shapes", "questions"):
            a, b = old[part].get(subject), new[part].get(subject)
            if a and b and b.get("validated_by") and (a.get("validated_by"), a.get("validated_on")) == (b.get("validated_by"), b.get("validated_on")):
                out.append(f"{subject} was validated by {b['validated_by']} on {b.get('validated_on')}, before this change ({c['kind']}): "
                           "ask them to confirm it again and update the date")
    return sorted(set(out))


# ───────────────────────────── impact on the catalogue ─────────────────────────────
def catalogue_graph(root):
    """The instance graph of every report under root that validates and compiles → (graph, compiled, failing)."""
    import semantic
    graphs, failing = [], []
    for d in semantic.report_dirs(root):
        files = semantic.load(d)
        errors = [i["message"] for i in semantic.issues(files) if i["level"] == "error"]
        graph, problems = semantic.build_graph(files) if not errors else (None, errors)
        if graph:
            graphs.append(graph)
        else:
            failing.append({"report": d.parent.name, "first_error": problems[0]})
    return semantic.graph_of(graphs), len(graphs), failing


def shape_violations(graph, ont=ONT):
    """{file#Shape: number of violations} of the report shapes over a catalogue graph."""
    import semantic
    from pyshacl import validate as shacl
    shapes_graph = Graph(); shapes_graph.parse(ont / "report-shapes.ttl")
    _, rg, _ = shacl(semantic.with_ontologies(graph), shacl_graph=shapes_graph, inference="none", allow_warnings=True, advanced=True)
    counts = {}
    for r in rg.subjects(RDF.type, SH.ValidationResult):
        if rg.value(r, SH.resultSeverity) != SH.Violation:
            continue
        src = rg.value(r, SH.sourceShape)
        owner = src if isinstance(src, URIRef) else next(shapes_graph.subjects(SH.property, src), None) or next(shapes_graph.subjects(SH.sparql, src), None)
        if owner is not None:
            key = f"report-shapes.ttl#{str(owner).rpartition('#')[2]}"
            counts[key] = counts.get(key, 0) + 1
    return counts


def impact(changes, graph, ont=ONT):
    """Fill in, for each breaking change, how many instances, triples or violations of the catalogue it touches."""
    violations = None
    for c in changes:
        if c["severity"] != BREAKING:
            continue
        subject = c["subject"].split(" ")[0]
        if "#" in subject:
            if subject.startswith("report-shapes.ttl#"):
                violations = shape_violations(graph, ont) if violations is None else violations
                c["affected"] = violations.get(subject, 0)
            continue
        iri = URIRef(expand(subject))
        c["affected"] = len(set(graph.subjects(RDF.type, iri))) if c["kind"].startswith("class") or c["kind"] == "superclass changed" \
            else len(list(graph.triples((None, iri, None))))
    return changes


# ───────────────────────────── the lock and the changelog ─────────────────────────────
def read_lock(ont=ONT):
    p = ont / LOCK
    return json.loads(p.read_text()) if p.exists() else None


def check(ont=ONT, qdir=QUESTIONS, catalogue=None):
    """The files against the lock → {lock, versions, changes, problems, reconfirm, catalogue}."""
    new, old = snapshot(ont, qdir), read_lock(ont)
    if old is None:
        return {"lock": None, "versions": new["versions"], "changes": [], "problems": version_problems({"versions": {}}, new, []), "reconfirm": [],
                "snapshot": new}
    changes = diff(old, new)
    out = {"lock": {"accepted_by": old.get("accepted_by"), "accepted_at": old.get("accepted_at"), "versions": old["versions"]},
           "versions": new["versions"], "changes": changes, "problems": version_problems(old, new, changes),
           "reconfirm": reconfirm(old, new, changes), "snapshot": new}
    if catalogue is not None:
        graph, compiled, failing = catalogue_graph(catalogue)
        impact(changes, graph, ont)
        out["catalogue"] = {"folder": str(catalogue), "compiled": compiled, "failing": failing}
    return out


def append_entry(path, key, header, entry):
    """Append one entry to an append-only YAML log; the file is created with its header the first time."""
    text = path.read_text() if path.exists() else header + f"{key}:\n"
    if not text.endswith("\n"):
        text += "\n"
    path.write_text(text + yaml.safe_dump([entry], sort_keys=False, allow_unicode=True, width=120))


CHANGELOG_HEADER = ("# Accepted changes to the vocabularies, their shapes and their questions. Appended by `kgctl.py ontology accept`,\n"
                    "# never rewritten: who accepted each change, when, and how severe it was. The lock (ontology.lock.json) holds the\n"
                    "# contract as last accepted; `kgctl.py ontology check` compares the files with it.\n")


def accept(by, ont=ONT, qdir=QUESTIONS, now=None):
    """Write the lock from the files and record what was accepted. Refuses while a version does not match its changes."""
    if not by or by.startswith("<"):
        raise ValueError("accept needs --by: the person accepting the change")
    result = check(ont, qdir)
    if result["problems"]:
        raise ValueError("refusing to accept: " + "; ".join(result["problems"]))
    if result["lock"] is not None and not result["changes"]:
        return None
    now = now or datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    snap = result["snapshot"]
    lock = {"_about": "The vocabularies, shapes and questions as last accepted. `kgctl.py ontology check` compares the files with it; "
                      "`kgctl.py ontology accept --by <you>` updates it. Generated: do not edit.",
            "accepted_by": by, "accepted_at": now, **snap}
    (ont / LOCK).write_text(json.dumps(lock, indent=1, ensure_ascii=False, sort_keys=False) + "\n")
    entry = {"at": now, "by": by, "versions": snap["versions"]}
    if result["lock"] is None:
        entry["note"] = (f"first lock: {len(snap['terms'])} terms, {len(snap['shapes'])} shapes, {len(snap['questions'])} questions")
    else:
        entry["changes"] = [{k: c[k] for k in ("severity", "kind", "subject", "detail") if k in c} for c in result["changes"]]
    append_entry(ont / CHANGELOG, "accepted", CHANGELOG_HEADER, entry)
    return entry


# ───────────────────────────── rationale ─────────────────────────────
GROUP = {"class": "classes", "object property": "properties", "datatype property": "properties"}


def rationale(snap=None, vocabulary=None):
    """How much of the contract says why it exists, and how much a person confirmed → {summary, unconfirmed, missing}."""
    snap = snap or snapshot()
    items = [(VOCABULARY_OF[t.split(":")[0]], GROUP[d["kind"]], t, d) for t, d in snap["terms"].items() if d["kind"] in GROUP]
    items += [(d["vocabulary"], "shapes", k, d) for k, d in snap["shapes"].items()]
    items += [(d["vocabulary"], "questions", q, {**d, "rationale": d.get("why")}) for q, d in snap["questions"].items()]
    if vocabulary:
        items = [i for i in items if i[0] == vocabulary]
    summary = {}
    for vocab, group, _, d in items:
        s = summary.setdefault(vocab, {}).setdefault(group, {"total": 0, "rationale": 0, "validated": 0})
        s["total"] += 1; s["rationale"] += bool(d.get("rationale")); s["validated"] += bool(d.get("validated_by"))
    return {"summary": summary,
            "missing_rationale": [s for _, g, s, d in items if not d.get("rationale") and g in ("classes", "shapes", "questions")],
            "unconfirmed": [s for _, _, s, d in items if not d.get("validated_by")],
            "confirmed": [{"subject": s, "by": d["validated_by"], "on": d.get("validated_on")} for _, _, s, d in items if d.get("validated_by")]}


def confirmation_problems(snap=None):
    """A confirmation must name who and when, and the date must be a date."""
    snap = snap or snapshot()
    out = []
    for part in ("terms", "shapes", "questions"):
        for s, d in snap[part].items():
            by, on = d.get("validated_by"), d.get("validated_on")
            if bool(by) != bool(on):
                out.append(f"{s} records {'who' if by else 'when'} it was validated but not {'when' if by else 'who'}")
            elif on and not ISO_DATE.match(on):
                out.append(f"{s} was validated on {on!r}, which is not a YYYY-MM-DD date")
    return out
