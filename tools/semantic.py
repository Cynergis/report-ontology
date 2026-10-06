"""Semantic layer for a report template: validate the YAML files and the release manifest, compile them into a graph.

  python semantic.py skeleton --data data/doc.json --i18n config/i18n.json --out semantic/report.yaml
        derive a first report.yaml (sections + fields, meanings left as TODO) from a data file
  python semantic.py validate semantic/            schema (schemas/*.schema.json, additionalProperties=false)
                                                   + completeness checks; exit 1 on any blocking gap
  python semantic.py compile  semantic/ --out semantic/report.graph.json [--md semantic/report.md]
        JSON-LD graph (rpt: ontology). Refuses to write if any emitted predicate is not declared in the
        ontology, or if a schema / the manifest was written against another ontology version.
  python semantic.py conform  semantic/            SHACL: can the graph answer the competency questions?
  python semantic.py ask      semantic/ CQ10 --report fund-profile-balanced
  python semantic.py diff     semantic/            what the files say that the last accepted revision does not; exit 1 if any
  python semantic.py accept   semantic/ --by <you> [--why <reason>] [--effective YYYY-MM-DD]
        append a revision to semantic/history.yaml (ledger.py): refused while the report does not validate or breaks
        a shape, and while a changed or removed fact has no reason

The directory is one report's semantic/ folder, or a folder of report folders (<report>/semantic/report.yaml):
the catalogue. On a catalogue, validate and compile run per report, conform and ask run over all of them together.

Files in semantic/: report.yaml (meaning), provenance.yaml (what led to it), lineage.yaml (which column of which
table supplies each field), history.yaml (every accepted revision of the definition; written by accept). ../manifest.json (release operating contract: schedule, parameter universes, policies,
observability) is read when present.
Each file has a JSON Schema in schemas/ whose every property names its ontology term (x-term); the manifest
and lineage.queries are compiled purely from those annotations, so a property with no term cannot reach the graph.
Everything here is deterministic; definitions are written by people (drafted by Claude, approved at the blueprint gate).
"""
import argparse, datetime, functools, json, pathlib, re, sys
import yaml

import ledger
from paths import ONT, SCHEMAS, QUESTIONS, FILE_OF

CQ_FILE = QUESTIONS / "report_cq.yaml"

DT = "https://cynergis.ai/ont/doctemplate#"
RPT = "https://cynergis.ai/ont/report#"
PROV = "http://www.w3.org/ns/prov#"
RDFS = "http://www.w3.org/2000/01/rdf-schema#"
SKOS = "http://www.w3.org/2004/02/skos/core#"
CONTEXT = {
    "@vocab": RPT, "rpt": RPT, "dt": DT, "prov": PROV, "rdfs": RDFS, "skos": SKOS, "xsd": "http://www.w3.org/2001/XMLSchema#",
    "label": "rdfs:label",
    "hasParameter": {"@type": "@id"}, "hasSection": {"@type": "@id"}, "hasField": {"@type": "@id"}, "inSection": {"@type": "@id"},
    "inReport": {"@type": "@id"}, "hasMeaning": {"@type": "@id"}, "hasRule": {"@type": "@id"}, "renderedBy": {"@type": "@id"},
    "releasedAs": {"@type": "@id"}, "derivedFrom": {"@type": "@id"}, "sourcedFrom": {"@type": "@id"}, "inTable": {"@type": "@id"},
    "readsTable": {"@type": "@id"}, "inDataSource": {"@type": "@id"}, "boundToColumn": {"@type": "@id"}, "hasStatusChange": {"@type": "@id"},
    "producedBy": {"@type": "@id"}, "usedSource": {"@type": "@id"},
    "hasApproval": {"@type": "@id"}, "hasRevision": {"@type": "@id"}, "hasChange": {"@type": "@id"}, "order": {"@type": "xsd:integer"}, "frozen": {"@type": "xsd:boolean"}, "regulatory": {"@type": "xsd:boolean"},
}
FILES = ("report", "provenance", "lineage", "history")


def jsonable(o):
    """YAML dates/datetimes → strings so JSON Schema sees the same document the graph will."""
    return json.loads(json.dumps(o, default=str))


def load(d):
    d = pathlib.Path(d)
    files = {"_dir": d}
    for n in FILES:
        p = d / f"{n}.yaml"
        files[n] = jsonable(yaml.safe_load(p.read_text())) if p.exists() else None
    mp = d.parent / "manifest.json"
    files["manifest"] = json.loads(mp.read_text()) if mp.exists() else None
    return files


def report_dirs(d):
    """One report's semantic/ folder, or every <report>/semantic under a catalogue folder."""
    d = pathlib.Path(d)
    if (d / "report.yaml").exists():
        return [d]
    return sorted(p.parent for p in d.glob("*/semantic/report.yaml"))


def schema(name):
    return json.loads((SCHEMAS / f"{name}.schema.json").read_text())


def ontology_version():
    m = re.search(r'owl:versionInfo\s+"([^"]+)"', (ONT / "report.ttl").read_text())
    return m.group(1) if m else None


def minor(v):
    return ".".join(str(v).split(".")[:2])


# ───────────────────────────── skeleton ─────────────────────────────
def guess_type(v):
    if isinstance(v, bool): return "boolean"
    if isinstance(v, (int, float)): return "number"
    if isinstance(v, str):
        s = v.strip()
        if s.endswith("%"): return "percent"
        if s[:1] in "$C" and "$" in s: return "currency"
        if len(s) == 10 and s[2] == "/" and s[5] == "/": return "date"
        return "text"
    if isinstance(v, list):
        return "list_of_text" if all(isinstance(x, str) for x in v) else "list"
    if isinstance(v, dict): return "object"
    return "unknown"


def skeleton(data_path, i18n_path, out):
    data = json.loads(pathlib.Path(data_path).read_text())
    i18n = json.loads(pathlib.Path(i18n_path).read_text()) if i18n_path else {}
    labels = i18n.get("en", {})
    sections, fields = [], {}
    for key, val in data.items():
        if key in ("layout",):
            continue
        ftype = guess_type(val)
        fields[key] = {"type": ftype, "meaning": "TODO"}
        if isinstance(val, dict) and "rows" in val:
            fields[key]["row"] = {"label": {"type": "text"}, "value": {"type": guess_type(val["rows"][0][1]) if val["rows"] and len(val["rows"][0]) > 1 else "text"}}
        if isinstance(val, dict) and "asof" in val:
            fields[f"{key}_as_of"] = {"type": "date", "meaning": "TODO"}
        sections.append({"id": key, "title": {"en": labels.get(key, key.replace("_", " ").title())}, "purpose": "TODO",
                         "component": "TODO", "fields": [k for k in (key, f"{key}_as_of") if k in fields]})
    doc = {"report": {"id": "TODO", "version": "0.1.0", "title": "TODO", "kind": "TODO", "purpose": "TODO",
                      "audience": [], "cadence": "TODO", "parameters": [], "locales": list(i18n.keys()) or ["en"]},
           "sections": sections, "fields": fields}
    pathlib.Path(out).write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=110))
    print(f"skeleton: {len(sections)} sections, {len(fields)} fields -> {out}  (fill every TODO)")


# ───────────────────────────── validate ─────────────────────────────
LIFECYCLE = ["inception", "saved", "in_validation", "in_production"]      # the statuses of a report type, in order


def schema_issues(name, doc):
    """JSON Schema validation with additionalProperties=false: an undeclared key is an error, never a silent drop.
    Returns (path, message) pairs."""
    import jsonschema
    sch = schema(name)
    out = []
    ov = ontology_version()
    if sch.get("x-ontology-version") != ov:
        out.append(("", f"{name}.schema.json is written for ontology {sch.get('x-ontology-version')} but ontology/report.ttl is {ov}"))
    for e in sorted(jsonschema.Draft202012Validator(sch).iter_errors(doc), key=lambda e: [str(x) for x in e.absolute_path]):
        path = ".".join(str(x) for x in e.absolute_path) or "<root>"
        msg = e.message
        if e.validator == "required":                        # point at the missing key, not at its parent
            key = re.match(r"'([^']+)' is a required property", msg)
            if key:
                out.append((".".join(str(x) for x in (*e.absolute_path, key.group(1))), f"{name}: {path}: {msg[:220]}")); continue
        if e.validator == "additionalProperties":
            msg = re.sub(r"(was|were) unexpected", r"\1 not declared in the schema: add the property with its x-term to schemas/, and the term to the ontology through a competency question (kgctl terms)", msg)
        out.append((path, f"{name}: {path}: {msg[:220]}"))
    return out


def issues(files, data_schema_path=None, with_pending=True):
    """Every problem of one report folder, as {level, file, path, message}. An error blocks compile; a warn does not.
    file and path say where the answer is written, so a caller can ask for exactly what is missing.
    with_pending=False leaves out the one problem accept exists to resolve: a production definition not yet accepted."""
    rep, prov, lin, man = files["report"], files["provenance"], files["lineage"], files["manifest"]
    out = []
    def err(name, path, message): out.append({"level": "error", "file": FILE_OF[name], "path": path, "message": message})
    def warn(name, path, message): out.append({"level": "warn", "file": FILE_OF[name], "path": path, "message": message})
    if rep is None:
        err("report", "", "report.yaml missing"); return out
    for name, doc in (("report", rep), ("provenance", prov), ("lineage", lin), ("manifest", man), ("history", files.get("history"))):
        if doc is not None:
            for path, message in schema_issues(name, doc): err(name, path, message)
    r = rep.get("report", {})
    if man is not None:
        if man.get("template_id") != r.get("id"):
            err("manifest", "template_id", f"manifest.template_id {man.get('template_id')!r} != report.id {r.get('id')!r}")
        if minor(man.get("ontology_version", "")) != minor(ontology_version()):
            err("manifest", "ontology_version", f"manifest.ontology_version {man.get('ontology_version')} is not compatible with ontology {ontology_version()} (same major.minor required)")
        t = (prov or {}).get("template") or {}
        if t and t.get("version") != man.get("version"):
            err("manifest", "version", f"manifest.version {man.get('version')} != provenance.template.version {t.get('version')}")
        for name, p in man.get("parameters", {}).items():
            if "universe" in p:
                qn = p["universe"].replace("lineage:queries.", "")
                if qn not in ((lin or {}).get("queries") or {}):
                    err("manifest", f"parameters.{name}.universe", f"manifest.parameters.{name}.universe points at lineage query '{qn}' which lineage.yaml does not define")
        declared = {p["name"] for p in r.get("parameters", [])}
        for name in man.get("parameters", {}):
            if name not in declared:
                err("manifest", f"parameters.{name}", f"manifest.parameters.{name} is not declared in report.parameters (no meaning)")
    else:
        warn("manifest", "", "no manifest.json next to semantic/: schedule, parameter universes, policies and observability undeclared (blocks production release)")
    todo = lambda d, k: k in d and (not d[k] or d[k] == "TODO")      # a missing key is the schemas' finding
    for k in ("id", "version", "title", "kind", "purpose", "parameters", "locales"):
        if todo(r, k):
            err("report", f"report.{k}", f"report.{k} missing or TODO")
    fields = rep.get("fields", {})
    sections = rep.get("sections", [])
    in_sections = set()
    for s in sections:
        for k in ("id", "title", "purpose", "component", "fields"):
            if todo(s, k):
                err("report", f"sections.{s.get('id', '?')}.{k}", f"section {s.get('id','?')}: {k} missing or TODO")
        for f in s.get("fields", []):
            if f not in fields:
                err("report", f"fields.{f}", f"section {s['id']}: field '{f}' not defined in fields")
            in_sections.add(f)
    for fid, f in fields.items():
        if todo(f, "type"):
            err("report", f"fields.{fid}.type", f"field {fid}: no type")
        if todo(f, "meaning"):
            err("report", f"fields.{fid}.meaning", f"field {fid}: no meaning")
        if fid not in in_sections:
            err("report", f"sections.*.fields", f"field {fid}: not placed in any section")
        if f.get("type") in ("list", "grouped_list", "series") and not f.get("row"):
            warn("report", f"fields.{fid}.row", f"field {fid}: list type without row structure")
    if data_schema_path:
        sch = json.loads(pathlib.Path(data_schema_path).read_text())
        for p in sch.get("properties", {}):
            if p not in fields:
                err("report", f"fields.{p}", f"schema field '{p}' has no semantic definition")
    if lin is None:
        err("lineage", "", "lineage.yaml missing")
    else:
        lf = lin.get("fields", {})
        for fid in fields:
            if fid not in lf:
                err("lineage", f"fields.{fid}", f"lineage: no entry for field {fid}")
        for fid, v in lf.items():
            if fid not in fields:
                err("lineage", f"fields.{fid}", f"lineage: field {fid} is not defined in report.yaml")
            if v.get("status") in ("proposed", "verified") and not v.get("column"):
                err("lineage", f"fields.{fid}.column", f"lineage: field {fid} is {v['status']} but names no column")
            if v.get("status") == "unmapped" and v.get("column"):
                err("lineage", f"fields.{fid}.status", f"lineage: field {fid} names a column but is still unmapped (use proposed until the analyst verifies it)")
        mapped = [fid for fid, v in lf.items() if v.get("column")]
        if (mapped or lin.get("parameters")) and not lin.get("table"):
            err("lineage", "table", "lineage: columns are named but no table is declared (lineage.table)")
        if lin.get("table") and not lin.get("source"):
            warn("lineage", "source", "lineage: table declared without a data source (lineage.source)")
        declared = {p["name"] for p in r.get("parameters", [])}
        for name in lin.get("parameters", {}):
            if name not in declared:
                err("lineage", f"parameters.{name}", f"lineage.parameters.{name} is not declared in report.parameters")
        unmapped = [fid for fid, v in lf.items() if v.get("status") == "unmapped"]
        if unmapped:
            warn("lineage", "fields", f"lineage: {len(unmapped)}/{len(lf)} fields unmapped (allowed while the analyst maps the table; blocks production release)")
    if prov is None:
        err("provenance", "", "provenance.yaml missing")
    else:
        # the lifecycle is a log: it starts at inception, moves forward one status at a time (it may move back), and never goes back in time
        log = [e for e in prov.get("lifecycle") or [] if isinstance(e, dict) and e.get("status") in LIFECYCLE]
        if log and log[0]["status"] != "inception":
            err("provenance", "lifecycle.0.status", f"lifecycle: the first status is {log[0]['status']}; a report starts at inception")
        for i in range(1, len(log)):
            before, now = log[i - 1], log[i]
            if LIFECYCLE.index(now["status"]) > LIFECYCLE.index(before["status"]) + 1:
                err("provenance", f"lifecycle.{i}.status", f"lifecycle: {now['status']} cannot follow {before['status']}; "
                    f"the status after {before['status']} is {LIFECYCLE[LIFECYCLE.index(before['status']) + 1]}")
            if str(now.get("at", ""))[:10] < str(before.get("at", ""))[:10]:
                err("provenance", f"lifecycle.{i}.at", f"lifecycle: step {i + 1} ({now.get('at')}) is dated before step {i} ({before.get('at')})")
        if log and log[-1]["status"] == "in_production" and not (man or {}).get("frozen"):
            err("provenance", f"lifecycle.{len(log) - 1}.status", "lifecycle: in_production needs a frozen release (manifest.frozen is not true)")
        for i, src in enumerate(prov.get("source_reports", [])):
            for k in ("repo_url", "sha256"):
                if str(src.get(k, "")).startswith("<") or "<org>" in str(src.get(k, "")):
                    warn("provenance", f"source_reports.{i}.{k}", f"provenance: source {src.get('id','?')} {k} is a placeholder")
    if not any(i["file"] == FILE_OF["history"] and i["level"] == "error" for i in out):      # a malformed history cannot be replayed
        out += ledger.issues(files, with_pending)
    return out


def validate(files, data_schema_path=None):
    """(errors, warnings) as messages; see issues() for where each one is written."""
    found = issues(files, data_schema_path)
    return [i["message"] for i in found if i["level"] == "error"], [i["message"] for i in found if i["level"] == "warn"]


# ───────────────────────────── schema-driven emission ─────────────────────────────
def resolve(root, ps):
    while "$ref" in ps:
        ref = root["$defs"][ps["$ref"].split("/")[-1]]
        ps = {**ref, **{k: v for k, v in ps.items() if k != "$ref"}}
    return ps


def emit(obj, sch, subj, root, nodes, errors, base, path):
    """Walk `obj` with its schema; every key must carry x-term (emit) or x-structural (skip). Anything else is an error."""
    node = nodes.setdefault(subj, {"@id": subj})
    if sch.get("x-class"):
        node["@type"] = sch["x-class"]
    props = sch.get("properties", {})
    for k, v in obj.items():
        p = f"{path}.{k}"
        if k in props:
            ps = resolve(root, props[k])
        else:
            errors.append(f"{p}: key not declared in schema"); continue
        if ps.get("x-structural"):
            continue
        term = ps.get("x-term")
        if not term:
            errors.append(f"{p}: schema property has no x-term (and is not x-structural)"); continue
        if ps.get("x-emit") == "json":
            node[term] = json.dumps(v, ensure_ascii=False, default=str); continue
        ap = ps.get("additionalProperties")
        if ps.get("type") == "object" and isinstance(ap, dict):           # map of entries → one node each
            es = resolve(root, ap)
            for key, entry in v.items():
                cid = (es.get("x-id") or "{subject}/" + k + "/{key}").format(base=base, key=key, subject=subj)
                child = nodes.setdefault(cid, {"@id": cid})
                if ps.get("x-key"):
                    child[ps["x-key"]] = key
                emit(entry, es, cid, root, nodes, errors, base, f"{p}.{key}")
                node.setdefault(term, []).append({"@id": cid})
            continue
        if ps.get("type") == "object" and ps.get("x-class"):                # nested node
            cid = (ps.get("x-id") or "{subject}/" + k).format(base=base, subject=subj, key=k)
            emit(v, ps, cid, root, nodes, errors, base, p)
            node[term] = {"@id": cid}; continue
        if ps.get("type") == "array" and isinstance(ps.get("items"), dict) and resolve(root, ps["items"]).get("x-class"):
            its = resolve(root, ps["items"])
            for i, item in enumerate(v):
                key = item.get("id") or item.get("name") or str(i + 1)
                cid = (its.get("x-id") or "{subject}/" + k + "/{key}").format(base=base, subject=subj, key=key)
                emit(item, its, cid, root, nodes, errors, base, f"{p}[{key}]")
                node.setdefault(term, []).append({"@id": cid})
            continue
        if ps.get("x-ref"):                                                  # scalar that names another node
            vals = v if isinstance(v, list) else [v]
            refs = [{"@id": ps["x-ref"].format(base=base, subject=subj, value=str(x).replace(ps.get("x-strip", ""), ""))} for x in vals]
            node[term] = refs if isinstance(v, list) else refs[0]; continue
        node[term] = v
    return node


# ───────────────────────────── compile ─────────────────────────────
REGULATORY_WORDS = ("disclaimer", "prospectus", "regulat", "rating organization", "compliance")


def lang_labels(d):
    return [{"@value": v, "@language": k} for k, v in (d or {}).items() if v]


def build_graph(files):
    """One validated report folder → (JSON-LD graph, problems). The graph is None when there are problems:
    a key the schemas do not declare, or a predicate the ontology does not declare."""
    rep, prov, lin, man = files["report"], files["provenance"], files["lineage"], files["manifest"]
    r = rep["report"]
    base = f"https://cynergis.ai/kg/report/{r['id']}/"
    comp = "https://cynergis.ai/kg/component/"
    nodes = []
    report = {"@id": base, "@type": "ReportType", "reportId": r["id"], "version": r["version"], "label": r["title"], "kind": r["kind"],
              "purpose": r["purpose"].strip(), "owner": r.get("owner"), "cadence": r.get("cadence"), "audience": r.get("audience", []),
              "locale": r.get("locales", []), "layout": r.get("layout"),
              "hasParameter": [base + "parameter/" + p["name"] for p in r.get("parameters", [])],
              "hasSection": [base + "section/" + s["id"] for s in rep["sections"]]}
    for p in r.get("parameters", []):
        nodes.append({"@id": base + "parameter/" + p["name"], "@type": "Parameter", "label": p["name"], "definition": p["meaning"]})
    for i, note in enumerate(r.get("regulatory_notes", [])):
        rid = base + "rule/report-" + str(i + 1)
        nodes.append({"@id": rid, "@type": "Rule", "ruleText": note, "regulatory": True})
        report.setdefault("hasRule", []).append(rid)
    nodes.append(report)
    comps = set()
    for i, s in enumerate(rep["sections"]):
        comps.add(s["component"])
        n = {"@id": base + "section/" + s["id"], "@type": "Section", "order": i + 1, "label": lang_labels(s["title"]),
             "purpose": s["purpose"].strip(), "renderedBy": comp + s["component"], "hasField": [base + "field/" + f for f in s["fields"]]}
        if s.get("present_when"):
            n["presentWhen"] = s["present_when"]
        nodes.append(n)
    for c in sorted(comps):
        nodes.append({"@id": comp + c, "@type": "dt:Component", "label": c})
    lf = (lin or {}).get("fields", {})
    # the data mapping: one table per report, in the data source the analyst named; fields and parameters point at its columns
    table_id = None
    if lin and lin.get("table"):
        src, t = lin.get("source"), lin["table"]
        table_id = "https://cynergis.ai/kg/table/" + (src["name"] + "." if src else "") + t["dataset"] + "." + t["name"]
        tn = {"@id": table_id, "@type": "Table", "dataset": t["dataset"], "tableName": t["name"]}
        if src:
            sid = "https://cynergis.ai/kg/datasource/" + src["name"]
            nodes.append({"@id": sid, "@type": "DataSource", "label": src["name"], "sourceKind": src.get("kind"), "database": src.get("database")})
            tn["inDataSource"] = sid
        nodes.append(tn)
        report["readsTable"] = table_id

    def column(name):
        cid = table_id + "/" + name
        nodes.append({"@id": cid, "@type": "Column", "columnName": name, "inTable": table_id})
        return cid

    for pname, col in ((lin or {}).get("parameters") or {}).items():
        nodes.append({"@id": base + "parameter/" + pname, "boundToColumn": column(col)})
    for fid, f in rep["fields"].items():
        sec = next((s for s in rep["sections"] if fid in s["fields"]), None)
        n = {"@id": base + "field/" + fid, "@type": "Field", "fieldId": fid, "fieldType": f.get("type"), "inReport": base,
             "inSection": base + "section/" + sec["id"] if sec else None, "order": (sec["fields"].index(fid) + 1) if sec else None}
        lab = f.get("label") if isinstance(f.get("label"), dict) else {}
        meanings = [{"@id": base + "field/" + fid + "/meaning/en", "@type": "FieldMeaning", "locale": "en",
                     "rpt:label": lab.get("en"), "definition": (f.get("meaning") or "").strip()}]
        if lab.get("fr") or f.get("meaning_fr"):
            meanings.append({"@id": base + "field/" + fid + "/meaning/fr", "@type": "FieldMeaning", "locale": "fr",
                             "rpt:label": lab.get("fr"), "definition": (f.get("meaning_fr") or f.get("meaning") or "").strip()})
        n["hasMeaning"] = [m["@id"] for m in meanings]
        nodes += [{k: v for k, v in m.items() if v is not None} for m in meanings]
        if f.get("row"):
            n["rowStructure"] = json.dumps(f["row"], ensure_ascii=False)
        if f.get("members"):
            n["members"] = json.dumps(f["members"], ensure_ascii=False)
        if f.get("aliases"):
            n["alias"] = f["aliases"]
        for j, rule in enumerate(f.get("rules", [])):
            rid = base + "field/" + fid + "/rule/" + str(j + 1)
            nodes.append({"@id": rid, "@type": "Rule", "ruleText": rule, "regulatory": any(w in rule.lower() for w in REGULATORY_WORDS)})
            n.setdefault("hasRule", []).append(rid)
        L = lf.get(fid, {})
        n["lineageStatus"] = L.get("status", "unmapped")
        if L.get("column"):
            n["sourcedFrom"] = column(L["column"])
        if L.get("note"):
            n["lineageNote"] = L["note"]
        nodes.append({k: v for k, v in n.items() if v is not None})
    release_id = None
    if prov:
        for i, c in enumerate(prov.get("lifecycle", [])):
            cid = base + "status/" + str(i + 1)
            nodes.append({"@id": cid, "@type": "StatusChange", "order": i + 1, "lifecycleStatus": c.get("status"), "changedBy": c.get("by"),
                          "at": str(c.get("at")), "note": c.get("note")})
            report.setdefault("hasStatusChange", []).append(cid)
            report["lifecycleStatus"] = c.get("status")          # the last step is the current status
        for s in prov.get("source_reports", []):
            nodes.append({"@id": base + "source/" + s["id"], "@type": "dt:SourceDocument", "label": s.get("title"), "repoUrl": s.get("repo_url"),
                          "sha256": s.get("sha256"), "role": s.get("role"), "receivedOn": s.get("received"), "referenceKind": s.get("reference_kind"),
                          "pageKind": s.get("page_kinds"), "note": s.get("notes")})
            report.setdefault("derivedFrom", []).append(base + "source/" + s["id"])
        t = prov.get("template")
        if t:
            release_id = base + "release/" + str(t.get("version"))
            nodes.append({"@id": release_id, "@type": "dt:TemplateRelease", "repoUrl": t.get("repo_url"), "version": t.get("version"),
                          "frozen": bool(t.get("frozen")), "ofReport": {"@id": base},
                          # fonts / pending assets: the manifest is the authority once it exists (written by freeze); provenance only until then
                          "font": None if man else (json.dumps(t.get("fonts", []), ensure_ascii=False) if t.get("fonts") else None),
                          "assetPending": None if man else t.get("assets_pending", [])})
            report["releasedAs"] = release_id
        for run in prov.get("runs", []):
            rid = base + "run/" + run["id"]
            approvals = []
            for k, d in enumerate(run.get("decisions", [])):
                aid = rid + "/approval/" + str(k + 1)
                approvals.append(aid)
                a = {"@id": aid, "@type": "Approval", "gate": d.get("gate"), "decision": d.get("decision"), "reviewer": d.get("reviewer"), "at": str(d.get("at"))}
                if d.get("hashes"): a["reviewedHash"] = json.dumps(d["hashes"])
                nodes.append(a)
            nodes.append({"@id": rid, "@type": "Run", "label": run["id"], "flow": run.get("flow"), "flowVersion": run.get("flow_version"),
                          "engineVersion": run.get("engine_version"), "startedAt": str(run.get("started")),
                          "usedSource": [base + "source/" + i for i in run.get("inputs", [])], "result": run.get("result"),
                          "step": json.dumps(run.get("steps", []), ensure_ascii=False, default=str) if run.get("steps") else None, "hasApproval": approvals})
            if t:
                for nd in nodes:
                    if nd.get("@type") == "dt:TemplateRelease":
                        nd.setdefault("producedBy", []).append(rid)
    for r in ledger.revisions(files):                          # the accepted history: who changed which fact, when, and why
        vid = base + "revision/" + str(r["revision"])
        nodes.append({"@id": vid, "@type": "Revision", "order": r["revision"], "changedBy": r["by"], "at": str(r["at"]), "reason": r["why"],
                      "effectiveFrom": str(r["effective"]) if r.get("effective") else None,
                      "hasChange": [f"{vid}/change/{j + 1}" for j in range(len(r.get("changes") or []))]})
        report.setdefault("hasRevision", []).append(vid)
        for j, c in enumerate(r.get("changes") or []):
            nodes.append({"@id": f"{vid}/change/{j + 1}", "@type": "Change", "fact": c["fact"], "changeKind": c["kind"],
                          "previousValue": ledger.value_text(c["from"]) if "from" in c else None,
                          "newValue": ledger.value_text(c["to"]) if "to" in c else None})
    nodes = [{k: v for k, v in n.items() if v is not None and v != []} for n in nodes]
    # merge by id, then add what the schemas drive: lineage queries, the release manifest
    byid = {}
    for n in nodes:
        byid.setdefault(n["@id"], {}).update(n)
    errors = []
    if lin and lin.get("queries"):
        ls = schema("lineage")
        emit({"queries": lin["queries"]}, {"properties": {"queries": ls["properties"]["queries"]}}, base, ls, byid, errors, base, "lineage")
    if man:
        ms = schema("manifest")
        rid = base + "release/" + man["version"]
        emit(man, ms, rid, ms, byid, errors, base, "manifest")
        byid[rid]["ofReport"] = {"@id": base}
        byid[base]["releasedAs"] = rid
    if errors:
        return None, errors
    byid[base]["compiledAt"] = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    byid[base]["ontologyVersion"] = ontology_version()
    graph = {"@context": CONTEXT, "@graph": list(byid.values())}
    undeclared = undeclared_predicates(graph)
    if undeclared:
        return None, [f"predicate not declared in the ontology: {u} (add the term through a competency question: "
                      "questions/report_cq.yaml → ontology/report.ttl, or fix the emitter)" for u in undeclared]
    return graph, []


def compile_graph(files, out, md=None):
    rep, prov, lin, man = files["report"], files["provenance"], files["lineage"], files["manifest"]
    graph, problems = build_graph(files)
    if problems:
        for e in problems: print("ERROR", e)
        print(f"refusing to compile: {len(problems)} error(s)"); return False
    pathlib.Path(out).write_text(json.dumps(graph, indent=1, ensure_ascii=False, default=str))
    counts = {}
    for n in graph["@graph"]:
        counts[n.get("@type", "?")] = counts.get(n.get("@type", "?"), 0) + 1
    print(f"graph: {len(graph['@graph'])} nodes {counts} -> {out}")
    if md:
        write_md(rep, prov, lin, man, md)
    return True


@functools.lru_cache(maxsize=1)
def declared_terms():
    """Every IRI the two ontologies declare as a class or property, plus the external vocabulary we allow."""
    from rdflib import Graph, RDF, RDFS, OWL
    g = Graph(); g.parse(ONT / "report.ttl"); g.parse(ONT / "ontology.ttl")
    terms = set()
    for t in (OWL.Class, OWL.ObjectProperty, OWL.DatatypeProperty, OWL.AnnotationProperty, RDF.Property, RDFS.Class):
        terms |= {str(s) for s in g.subjects(RDF.type, t)}
    terms |= {str(RDF.type), str(RDFS.label), str(RDFS.comment), SKOS + "definition"}
    terms |= {PROV + x for x in ("wasGeneratedBy", "used", "wasAttributedTo", "Activity", "Entity")}
    return terms


def undeclared_predicates(graph_dict):
    from rdflib import Graph, RDF
    g = Graph(); g.parse(data=json.dumps(graph_dict, default=str), format="json-ld")
    declared = declared_terms()
    used = {str(p) for p in g.predicates()} | {str(o) for o in g.objects(None, RDF.type)}
    return sorted(u for u in used if u not in declared and (u.startswith(RPT) or u.startswith(DT)) or (u not in declared and not u.startswith("http://www.w3.org/")))


# ───────────────────────────── conform / ask ─────────────────────────────
def graph_of(graphs):
    """Compiled graphs (JSON-LD dicts) merged into one rdflib graph: the instance data, without the ontologies."""
    from rdflib import Graph
    g = Graph()
    for d in graphs:
        g.parse(data=json.dumps(d, default=str), format="json-ld")
    return g


def with_ontologies(g):
    g.parse(ONT / "report.ttl"); g.parse(ONT / "ontology.ttl")
    return g


def rdf_graph(graph_jsons):
    """The compiled graph of every report given, merged, plus the two ontologies."""
    for gj in graph_jsons:
        if not pathlib.Path(gj).exists():
            raise SystemExit(f"{gj} missing: run compile first")
    return with_ontologies(graph_of(json.loads(pathlib.Path(gj).read_text()) for gj in graph_jsons))


def shape_results(g):
    """SHACL results of a graph (instances + ontologies) as {severity, node, path, message}; (conforms, results)."""
    from pyshacl import validate as shacl
    from rdflib import Graph, Namespace, RDF
    shapes = Graph(); shapes.parse(ONT / "report-shapes.ttl")
    ok, rg, _ = shacl(g, shacl_graph=shapes, inference="none", allow_warnings=True, advanced=True)
    SH = Namespace("http://www.w3.org/ns/shacl#")
    rows = [{"severity": str(rg.value(r, SH.resultSeverity)).split("#")[-1], "node": str(rg.value(r, SH.focusNode)),
             "path": str(rg.value(r, SH.resultPath)) if rg.value(r, SH.resultPath) is not None else None,
             "message": str(rg.value(r, SH.resultMessage))} for r in rg.subjects(RDF.type, SH.ValidationResult)]
    return ok, sorted(rows, key=lambda x: (x["severity"], x["node"], x["message"]))


def conform(graph_jsons):
    ok, rows = shape_results(rdf_graph(graph_jsons))
    for sev in ("Violation", "Warning"):
        sel = [x for x in rows if x["severity"] == sev]
        print(f"{sev}s: {len(sel)}")
        for x in sel[:12]:
            print(f"  {x['node'].split('/kg/')[-1]:<60} {x['message']}")
        if len(sel) > 12:
            print(f"  … {len(sel) - 12} more")
    print("conforms:", ok)
    return ok


def questions():
    return yaml.safe_load(CQ_FILE.read_text())


def question_params(q):
    return sorted(set(re.findall(r"\$([A-Z]+)", q["answer"] + q.get("gaps", ""))))


def run_question(g, cq_id, params):
    """One competency question against a graph → {id, who, question, status, rows, gaps}.
    status: answered | gap (answered, but the gaps query found something missing) | empty (no rows)."""
    cq = questions()
    if cq_id not in cq["questions"]:
        raise ValueError(f"unknown question {cq_id}; known: {', '.join(cq['questions'])}")
    q = cq["questions"][cq_id]
    missing = [m for m in question_params(q) if m not in params]
    if missing:
        raise ValueError(f"{cq_id} needs " + ", ".join("--" + m.lower() for m in missing))
    def run(text):
        for k, v in params.items():
            text = text.replace("$" + k, json.dumps(v))
        res = g.query(cq["prefixes"] + text)
        return [{str(k): str(v) for k, v in zip(res.vars, row) if v is not None} for row in res]
    rows = run(q["answer"]); gaps = run(q["gaps"]) if q.get("gaps") else []
    return {"id": cq_id, "who": q["who"], "question": q["question"], "status": "gap" if gaps else ("empty" if not rows else "answered"),
            "rows": rows, "gaps": gaps}


def ask(graph_jsons, cq_id, params):
    try:
        r = run_question(rdf_graph(graph_jsons), cq_id, params)
    except ValueError as e:
        raise SystemExit(str(e))
    print(f"{r['id']} [{r['who']}] {r['question']}  → {r['status']}, {len(r['rows'])} rows")
    for row in r["rows"][:12]:
        print("   ", {k: v[:70] for k, v in row.items()})
    if len(r["rows"]) > 12:
        print(f"    … {len(r['rows']) - 12} more")
    for gp in r["gaps"][:8]:
        print("    gap:", gp)
    return r["status"]


def write_md(rep, prov, lin, man, out):
    r = rep["report"]; lf = (lin or {}).get("fields", {})
    L = [f"# {r['title']}", "", r["purpose"].strip(), "",
         f"Kind: {r['kind']} · cadence: {r.get('cadence')} · locales: {', '.join(r.get('locales', []))} · version {r['version']}", "",
         "Parameters: " + "; ".join(f"`{p['name']}` {p['meaning']}" for p in r.get("parameters", [])), ""]
    if r.get("owner"):
        L += [f"Owner: {r['owner']}", ""]
    if prov and prov.get("lifecycle"):
        last = prov["lifecycle"][-1]
        L += [f"Status: {last['status']} (recorded by {last['by']} on {last['at']})", ""]
    if lin and lin.get("table"):
        src = lin.get("source") or {}
        L += [f"Data: table `{lin['table']['dataset']}.{lin['table']['name']}`" + (f" in data source `{src['name']}` ({src.get('kind')})" if src else ""), ""]
    if man:
        s = man["schedule"]
        L += [f"Release {man['version']} (engine {man['engine_version']}, ontology {man['ontology_version']}, library {man['library_version']})", "",
              f"Schedule: {s['cadence']} · {s['run_on']} · as of {s['as_of']} · {s.get('calendar', '')} {s['timezone']}", "",
              "Parameter universes: " + "; ".join(f"`{k}` ← {p.get('universe') or p.get('values') or p.get('from')}" for k, p in man["parameters"].items()), "",
              f"Verify: static SSIM ≥ {man['verify']['golden_static_ssim_min']}, overflow blocking {man['verify']['overflow_blocking']} · "
              f"Approval: sample {man['approval']['sample_rate']:.0%} (min {man['approval']['sample_min']}) · Publish: `{man['publish']['path']}`", "",
              f"Observability: deliver within {man['observability']['deliver_within_hours']} h · failure rate ≤ {man['observability']['max_failure_rate']:.0%} · "
              f"alert {', '.join(man['observability']['alert'])} · run log `{man['observability']['run_log']}`", ""]
    if prov:
        for s in prov.get("source_reports", []):
            L.append(f"Source report: [{s.get('title')}]({s.get('repo_url')}) · {s.get('reference_kind')} reference")
        L.append("")
    for s in rep["sections"]:
        L += [f"## {s['title'].get('en')} — *{s['title'].get('fr','')}*", "", s["purpose"].strip(), "", f"Component: `{s['component']}`", "",
              "| Field | Type | Meaning | Column | Mapping |", "| --- | --- | --- | --- | --- |"]
        for fid in s["fields"]:
            f = rep["fields"][fid]
            L.append(f"| `{fid}` | {f.get('type')} | {(f.get('meaning') or '').strip()} | {lf.get(fid, {}).get('column', '—')} | {lf.get(fid, {}).get('status', '—')} |")
        L.append("")
    pathlib.Path(out).write_text("\n".join(L))
    print(f"view: {out}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["skeleton", "validate", "compile", "conform", "ask", "diff", "accept"])
    ap.add_argument("--report"); ap.add_argument("--field"); ap.add_argument("--column"); ap.add_argument("--component")
    ap.add_argument("args", nargs="*", help="directory [cq id]")
    ap.add_argument("--data"); ap.add_argument("--i18n"); ap.add_argument("--schema", help="template data schema (schema/data.schema.json)")
    ap.add_argument("--out"); ap.add_argument("--md")
    ap.add_argument("--by", help="accept: the person accepting the definition"); ap.add_argument("--why", help="accept: why the facts changed")
    ap.add_argument("--effective", help="accept: the date from which the revision applies (default: today)")
    a = ap.parse_args()
    a.dir = next((x for x in a.args if not x.upper().startswith("CQ")), "semantic")
    a.cq = next((x.upper() for x in a.args if x.upper().startswith("CQ")), None)
    if a.cmd == "skeleton":
        skeleton(a.data, a.i18n, a.out or "report.yaml"); sys.exit(0)
    dirs = report_dirs(a.dir)
    if not dirs:
        sys.exit(f"no report.yaml in {a.dir} and no <report>/semantic/report.yaml under it")
    many = len(dirs) > 1
    if many and (a.out or a.md or a.schema):
        sys.exit("--out, --md and --schema apply to one report: point at its semantic/ folder")
    gjs = [str(d / "report.graph.json") for d in dirs]
    if a.cmd == "validate":
        failed = 0
        for d in dirs:
            files = load(d)
            errors, warns = validate(files, a.schema)
            tag = f"[{d.parent.name}] " if many else ""
            for w in warns: print(f"{tag}WARN ", w)
            for e in errors: print(f"{tag}ERROR", e)
            n = ledger.count(ledger.pending(files))
            if files["report"] is not None and not ledger.revisions(files):
                print(f"{tag}NO HISTORY no accepted revision yet (`semantic.py accept <report> --by <you>` records the definition)")
            if n:
                print(f"{tag}PENDING {n} fact(s) differ from the last accepted revision (semantic.py diff shows them)")
            print(tag + ("OK" if not errors else f"{len(errors)} error(s)"))
            failed += bool(errors)
        sys.exit(1 if failed else 0)
    if a.cmd == "diff":
        unaccepted = 0
        for d in dirs:
            files = load(d)
            tag, revs, p = f"[{d.parent.name}] " if many else "", ledger.revisions(files), ledger.pending(files)
            if p is None:
                print(f"{tag}no accepted revision: `semantic.py accept {d} --by <you>` records the definition as it stands"); unaccepted += 1; continue
            last = revs[-1]
            print(f"{tag}{ledger.count(p)} pending since revision {last['revision']} (by {last['by']} at {last['at']}): "
                  f"{len(p['added'])} added, {len(p['changed'])} changed, {len(p['removed'])} removed")
            show = lambda v: json.dumps(v, ensure_ascii=False, default=str)[:90]
            for c in p["added"]: print(f"  + {c['fact']} = {show(c['to'])}")
            for c in p["changed"]: print(f"  ~ {c['fact']}: {show(c['from'])} → {show(c['to'])}")
            for c in p["removed"]: print(f"  - {c['fact']} (was {show(c['from'])})")
            unaccepted += bool(ledger.count(p))
        sys.exit(1 if unaccepted else 0)
    if a.cmd == "accept":
        ok = True
        for d in dirs:
            files, tag = load(d), f"[{d.parent.name}] " if many else ""
            errors = [i["message"] for i in issues(files, a.schema, with_pending=False) if i["level"] == "error"]
            graph, problems = build_graph(files) if not errors else (None, [])
            violations = [] if errors or problems else [r for r in shape_results(with_ontologies(graph_of([graph])))[1] if r["severity"] == "Violation"]
            for e in errors + problems + [f"{v['node'].split('/kg/')[-1]}: {v['message']}" for v in violations]:
                print(f"{tag}ERROR", e)
            if errors or problems or violations:
                print(f"{tag}refusing to accept: the definition must validate, compile and conform first"); ok = False; continue
            try:
                rev = ledger.revision(files, a.by, a.why, a.effective)
            except ValueError as e:
                print(f"{tag}refusing to accept: {e}"); ok = False; continue
            if rev is None:
                print(f"{tag}nothing to accept: the files match revision {ledger.revisions(files)[-1]['revision']}"); continue
            ledger.append(d, rev)
            what = f"{len(rev['facts'])} facts" if "facts" in rev else f"{len(rev['changes'])} change(s)"
            print(f"{tag}accepted revision {rev['revision']} by {rev['by']} ({what}, effective {rev['effective']}) → {d / ledger.NAME}")
        sys.exit(0 if ok else 1)
    if a.cmd == "conform":
        sys.exit(0 if conform(gjs) else 1)
    if a.cmd == "ask":
        params = {k.upper(): v for k, v in {"report": a.report, "field": a.field, "column": a.column, "component": a.component}.items() if v}
        if "REPORT" not in params and not many:
            params["REPORT"] = load(dirs[0])["report"]["report"]["id"]
        sys.exit(0 if ask(gjs, a.cq, params) == "answered" else 1)
    if a.cmd == "compile":
        ok = True
        for d, gj in zip(dirs, gjs):
            files = load(d)
            errors, _ = validate(files, a.schema)
            if errors:
                for e in errors: print("ERROR", e)
                print(f"refusing to compile {d}: {len(errors)} validation error(s); run validate"); ok = False; continue
            ok = compile_graph(files, a.out or gj, a.md) and ok
        sys.exit(0 if ok else 1)
