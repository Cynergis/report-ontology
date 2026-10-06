"""ledger — the accepted history of a report's definition: supersession, never overwrite.

A report's files say what its definition is now. semantic/history.yaml says what it was: every revision anyone
accepted, appended and never rewritten. Revision 1 holds every fact of the definition as first accepted; each later
revision holds the facts it added, changed or removed, with the value before and after, who accepted it, when it was
recorded, from which date it applies, and why. Replaying the revisions gives the definition as it stood on any date.

A fact is one value of report.yaml, lineage.yaml or manifest.json, named by its file and its path, the way gaps and
explain name the place an answer is written: "semantic/lineage.yaml → fields.mer.column". provenance.yaml is a log
already (lifecycle, runs) and is not repeated here.

  semantic.py diff   <report>                            what differs from the last accepted revision
  semantic.py accept <report> --by <you> [--why <text>]   record it; a changed or removed fact needs a why
  kg.py history <report> [--as-of DATE] [--fact TEXT]    the revisions, or the definition as it stood on a date

Changing a fact without accepting it is allowed while a report is drafted: the change is pending and every tool says
so. A report in production refuses it: what was true when its documents were produced must stay answerable.
"""
import datetime, json
import yaml

from paths import FILE_OF

FACT_FILES = ("report", "lineage", "manifest")
KEYS = ("id", "name", "family")             # what names an entry of a list, in this order
NAME = "history.yaml"
HEADER = ("# The accepted history of this report's definition. Written by `semantic.py accept`, never edited by hand:\n"
          "# revision 1 holds every fact as first accepted, each later revision the facts it added, changed or removed.\n"
          "# Replaying them gives the definition as it stood on any date (`kg.py history --as-of`).\n")
MISSING = object()


def fact_name(file, path):
    return f"{FILE_OF[file]} → {path}"


def flatten(value, path, out):
    """Every leaf of a YAML/JSON document as {path: value}. A list of named entries (sections, parameters, fonts) is
    keyed by name, and its order is a fact of its own; a list of plain values is one value."""
    if isinstance(value, dict) and value:
        for k, v in value.items():
            flatten(v, f"{path}.{k}" if path else str(k), out)
    elif isinstance(value, list) and value and all(isinstance(x, dict) for x in value):
        key = next((k for k in KEYS if all(k in x for x in value)), None)
        names = [str(x[key]) for x in value] if key else [str(i) for i in range(len(value))]
        if key:
            out[path] = names
        for n, x in zip(names, value):
            flatten({k: v for k, v in x.items() if k != key}, f"{path}.{n}", out)
    else:
        out[path] = value
    return out


def facts(files):
    """The definition as the files state it now: {fact name: value}."""
    out = {}
    for name in FACT_FILES:
        if files.get(name) is not None:
            for path, v in flatten(files[name], "", {}).items():
                out[fact_name(name, path)] = v
    return dict(sorted(out.items()))


def revisions(files):
    return ((files.get("history") or {}).get("revisions")) or []


def replay(revs, as_of=None, known_on=None):
    """The accepted definition: every revision applied in order. as_of keeps the revisions that apply on that date
    (their effective date); known_on keeps the ones recorded by then. Both are YYYY-MM-DD."""
    state = {}
    for r in revs:
        if as_of and str(r.get("effective") or r["at"])[:10] > as_of:
            continue
        if known_on and str(r["at"])[:10] > known_on:
            continue
        if "facts" in r:
            state = dict(r["facts"])
        for c in r.get("changes") or []:
            if c["kind"] == "removed":
                state.pop(c["fact"], None)
            else:
                state[c["fact"]] = c.get("to")
    return state


def diff(old, new):
    """{added, changed, removed}: lists of {fact, from, to}."""
    return {"added": [{"fact": f, "to": new[f]} for f in sorted(set(new) - set(old))],
            "changed": [{"fact": f, "from": old[f], "to": new[f]} for f in sorted(set(old) & set(new)) if old[f] != new[f]],
            "removed": [{"fact": f, "from": old[f]} for f in sorted(set(old) - set(new))]}


def pending(files):
    """What the files say that no accepted revision does, or None when nothing was ever accepted."""
    revs = revisions(files)
    return diff(replay(revs), facts(files)) if revs else None


def count(d):
    return sum(len(v) for v in d.values()) if d else 0


def lifecycle_status(files):
    log = ((files.get("provenance") or {}).get("lifecycle")) or []
    return log[-1].get("status") if log and isinstance(log[-1], dict) else None


def issues(files, with_pending=True):
    """Problems with the history itself, as {level, file, path, message}: a revision out of order, a change that does
    not start from the value the history holds (the file was edited by hand), and, for a report in production, a
    definition that changed without being accepted."""
    out, revs = [], revisions(files)
    def err(path, message): out.append({"level": "error", "file": FILE_OF["history"], "path": path, "message": message})
    if not revs:              # a draft without history is the shapes' warning (rpt:hasRevision); in production it is an error
        if files.get("report") is not None and lifecycle_status(files) == "in_production":
            err("", "history: a report in production needs an accepted definition (`semantic.py accept <report> --by <you>`)")
        return out
    state, last = {}, ""
    for i, r in enumerate(revs):
        n, where = i + 1, f"revisions.{i}"
        if r.get("revision") != n:
            err(f"{where}.revision", f"history: entry {n} is numbered {r.get('revision')}; revisions are numbered 1, 2, 3… in the order they were accepted")
        if str(r.get("at", "")) < last:
            err(f"{where}.at", f"history: revision {n} ({r.get('at')}) is recorded before revision {n - 1} ({last})")
        last = max(last, str(r.get("at", "")))
        if (n == 1) != ("facts" in r) or (n > 1 and "changes" not in r):
            err(where, f"history: revision {n} must hold " + ("the facts of the first accepted definition" if n == 1 else "changes, not facts"))
            continue
        if n == 1:
            state = dict(r["facts"]); continue
        for j, c in enumerate(r["changes"]):
            held = state.get(c["fact"], MISSING)
            if c["kind"] == "added" and held is not MISSING:
                err(f"{where}.changes.{j}", f"history: revision {n} adds {c['fact']}, which the history already holds")
            elif c["kind"] != "added" and held is MISSING:
                err(f"{where}.changes.{j}", f"history: revision {n} {c['kind']} {c['fact']}, which the history does not hold")
            elif c["kind"] != "added" and held != c.get("from", MISSING):
                err(f"{where}.changes.{j}.from", f"history: revision {n} says {c['fact']} was {c.get('from')!r}, but the history holds {held!r}: "
                    "the file was edited by hand")
            if c["kind"] == "removed":
                state.pop(c["fact"], None)
            else:
                state[c["fact"]] = c.get("to")
    if with_pending and not any(o["level"] == "error" for o in out) and lifecycle_status(files) == "in_production":
        d = diff(state, facts(files))
        overwritten = d["changed"] + d["removed"]
        if overwritten:
            err("", f"history: the definition of a report in production changed without being accepted: {len(overwritten)} fact(s), first "
                f"{overwritten[0]['fact']}. Accept it with who and why (`semantic.py accept <report> --by <you> --why <reason>`)")
    return out


def revision(files, by, why=None, effective=None, now=None):
    """The next revision for what the files say now, or None when nothing changed. Raises ValueError when a person
    is not named, or a changed or removed fact has no reason."""
    if not by or str(by).startswith("<"):
        raise ValueError("accept needs --by: the person accepting the definition")
    now = now or datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    if effective and not (len(effective) == 10 and effective[4] == effective[7] == "-"):
        raise ValueError(f"--effective {effective} is not a YYYY-MM-DD date")
    revs, current = revisions(files), facts(files)
    head = {"revision": len(revs) + 1, "at": now, "by": by}
    if not revs:
        return {**head, "why": why or "the definition as first accepted", "effective": effective or now[:10], "facts": current}
    d = diff(replay(revs), current)
    if not count(d):
        return None
    if (d["changed"] or d["removed"]) and not why:
        shown = [c["fact"] for c in d["changed"] + d["removed"]]
        raise ValueError(f"{len(shown)} accepted fact(s) would change or go: say why with --why (" + "; ".join(shown[:5]) + ("; …" if len(shown) > 5 else "") + ")")
    changes = [{"fact": c["fact"], "kind": kind, **({"from": c["from"]} if "from" in c else {}), **({"to": c["to"]} if "to" in c else {})}
               for kind in ("added", "changed", "removed") for c in d[kind]]
    return {**head, "why": why or f"{len(d['added'])} fact(s) added", "effective": effective or now[:10],
            "changes": sorted(changes, key=lambda c: c["fact"])}


def append(semantic_dir, rev):
    """Append one revision to semantic/history.yaml; the file is created with its header the first time."""
    p = semantic_dir / NAME
    text = p.read_text() if p.exists() else HEADER + "revisions:\n"
    if not text.endswith("\n"):
        text += "\n"
    p.write_text(text + yaml.safe_dump([json.loads(json.dumps(rev, default=str))], sort_keys=False, allow_unicode=True, width=120))
    return p


def value_text(v):
    """A value as one literal for the graph: text stays text, anything else is JSON."""
    return v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)


def summary(rev):
    """One revision without its facts: who, when, why and what it touched."""
    out = {k: rev.get(k) for k in ("revision", "at", "by", "why", "effective")}
    if "facts" in rev:
        out["facts"] = len(rev["facts"])
    else:
        out["changes"] = rev.get("changes") or []
    return out


def last_set(revs, fact, value):
    """The revision from which a fact has held its present value: (revision number, effective date), or None."""
    since = None
    for r in revs:
        if "facts" in r and r["facts"].get(fact, MISSING) == value:
            since = since or (r["revision"], str(r.get("effective") or r["at"])[:10])
        for c in r.get("changes") or []:
            if c["fact"] == fact:
                since = (r["revision"], str(r.get("effective") or r["at"])[:10]) if c.get("to", MISSING) == value else None
    return since
