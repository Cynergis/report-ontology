/* How it is built: the product's flow from the knowledge base, step by step. */
(function () {
  "use strict";
  var B = window.__BUILD__ || {};
  var St = window.Studio;
  var esc = St.esc;
  var KIND = {DeterministicStep: "A script", OcrStep: "Reads a document", ClaudeStep: "Done by an AI model", HumanStep: "A person decides",
              TerminalStep: "The end", Step: "A step"};
  function cap(t) { return t ? t.charAt(0).toUpperCase() + t.slice(1) : ""; }
  function human(name) { return /^[a-z0-9_]+$/.test(name || "") ? cap(String(name).replace(/_/g, " ")) : (name || ""); }
  function and(parts) { parts = parts.filter(Boolean); return parts.length < 2 ? parts.join("") : parts.slice(0, -1).join(", ") + " and " + parts[parts.length - 1]; }
  function unique(refs) {
    var seen = {};
    return (refs || []).filter(function (r) { if (!r || !r.name || seen[r.id]) return false; seen[r.id] = true; return true; });
  }
  // a move between steps has no name a reader knows: it is "where the run goes next"
  function links(refs) {
    var moves = false;
    var named = unique(refs).filter(function (r) { if (r.type === "Transition") { moves = true; return false; } return true; })
      .map(function (r) { return St.link(r.id, human(r.name)); });
    return and(named.concat(moves ? ["where the run goes next"] : []));
  }
  function line(lead, refs) { var l = links(refs); return l ? "<span>" + lead + " " + l + ".</span>" : ""; }
  function text(t) { return t ? "<span>" + t + "</span>" : ""; }
  function missing(t) { return '<span class="studio-none">' + esc(t) + "</span>"; }
  function tag(t, on) { return t ? '<span class="tag' + (on ? " on" : "") + '">' + esc(t) + "</span>" : ""; }
  function facts(list) { var s = list.filter(Boolean); return s.length ? '<div class="facts">' + s.join("") + "</div>" : ""; }
  function card(item, inner, tags) {
    return '<div class="studio-card" id="' + esc(item.id) + '"><h3>' + esc(human(item.name)) + "</h3>" + (tags || "") +
      (item.summary && item.summary !== item.name ? "<p>" + esc(cap(item.summary)) + "</p>" : "") + inner + "</div>";
  }
  function built(s) {
    if (s.type === "TerminalStep" || s.type === "HumanStep") return "";
    var exists = s.implemented === true || (s.implementation || []).some(function (i) { return i.exists; });
    return exists ? tag("Built", true) : tag("Not built yet");
  }

  function flows() {
    return (B.flows || []).map(function (f) {
      return card(f, facts([f.value ? text(/^[0-9][0-9.]*$/.test(f.value) ? "Version " + esc(f.value) + "." : esc(cap(f.value))) : "", f.trigger ? text("It starts " + esc(f.trigger.replace(/^on /, "on ")) + ".") : "",
        f.resumable ? text("It can resume where it stopped.") : "",
        text(((f.steps || []).length === 1 ? "One step." : (f.steps || []).length + " steps.") )]));
    }).join("");
  }

  function steps() {
    // in the order the run takes them: by their position, the end last
    var ordered = (B.steps || []).slice().sort(function (a, b) {
      var ea = a.type === "TerminalStep" ? 1 : 0, eb = b.type === "TerminalStep" ? 1 : 0;
      return ea - eb || String(a.stepId || "~").localeCompare(String(b.stepId || "~")) || a.name.localeCompare(b.name);
    });
    return ordered.map(function (s) {
      var checks = (s.checks || []).map(function (c) {
        return St.link(c.id, human(c.name)) + (String(c.blocking) === "true" || c.blocking === true ? " (it stops the run when it fails)" : "");
      });
      var next = (s.next || []).map(function (t) {
        return (t.on && t.on.length ? "when " + links(t.on) + ", " : "") + "on to " + links(t.to);
      });
      return card(s, facts([
        line("In", s.phase), line("After", (s.waits || []).concat(s.after || [])), line("It reads", s.reads), line("It may read", s.maybe),
        line("It writes", s.writes), checks.length ? text("Checked by " + and(checks) + ".") : "",
        s.options && s.options.length ? text("The choices: " + esc(and(s.options.map(human))) + ".") : "",
        s.retries ? text("Retried up to " + esc(s.retries) + " times.") : "",
        line("It depends on the settings", (s.settings || []).concat(s.depends || [])),
        next.length ? text(cap(next.join("; ")) + ".") : "",
        (s.owed || []).length ? line("Tests it owes:", s.owed) : ""
      ]), tag(KIND[s.type] || "A step") + built(s));
    }).join("");
  }

  function artifacts() {
    return (B.artifacts || []).map(function (a) {
      var fields = (a.fields || []).map(function (f) { return esc(human(f.name || f.path)); });
      return card(a, facts([a.format ? text("A " + esc(String(a.format).toUpperCase()) + " file" + (a.optional ? ", not always there" : "") + ".") : "",
        line("Written by", a.written_by), line("Read by", a.read_by), fields.length ? text("It holds " + and(fields) + ".") : ""]));
    }).join("");
  }

  function settings() {
    return (B.settings || []).map(function (p) {
      return card(p, facts([p.value != null && p.value !== "" ? text("Set to <strong>" + esc(p.value) + "</strong>.") : missing("No value set yet."),
        line("Used by", p.used_by), line("Compared by", p.compared_by)]));
    }).join("");
  }

  function checks() {
    return (B.checks || []).map(function (c) {
      var against = (c.against || []).map(function (p) { return St.link(p.id, human(p.name)) + (p.value ? " (" + esc(p.value) + ")" : ""); });
      return card(c, facts([line("On", c.on), against.length ? text("Compared with " + and(against) + ".") : "",
        String(c.blocking) === "true" || c.blocking === true ? text("When it fails, the run stops.") : "",
        line("When it fails:", c.on_fail), line("It enforces", c.enforces)]));
    }).join("");
  }

  function owed() {
    var tests = (B.obligations || []).map(function (o) {
      return card(o, facts([line("For", o.step), line("It tests", o.tests)]), tag(human(o.kind)));
    }).join("");
    var rules = (B.invariants || []).map(function (i) {
      return card(i, facts([i.statement ? text(esc(cap(i.statement))) : "", line("Enforced by", i.enforced_by)]));
    }).join("");
    return tests + (rules ? "<h3>What must always hold</h3>" + rules : "");
  }

  var SECTIONS = [["flows", "The flow", flows, true], ["steps", "Its steps, in order", steps, true], ["artifacts", "What it produces", artifacts],
                  ["checks", "Its checks", checks], ["settings", "Its settings", settings], ["owed", "The tests it owes", owed]];

  St.ready(function () {
    var toc = [], body = [];
    SECTIONS.forEach(function (s) {
      var html = s[2]();
      if (!html && !s[3]) return;
      toc.push('<li><a href="#section-' + s[0] + '">' + esc(s[1]) + "</a></li>");
      body.push('<section id="section-' + s[0] + '"><h2>' + esc(s[1]) + "</h2>" +
                (html || '<p class="studio-none">Nothing recorded yet.</p>') + "</section>");
    });
    document.getElementById("toc").innerHTML = toc.join("");
    document.getElementById("sections").innerHTML = body.join("");
    St.focus();
  });
})();
