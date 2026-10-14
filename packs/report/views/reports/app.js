/* The reports: the report catalogue from the knowledge base, written for the people who read and run it. */
(function () {
  "use strict";
  var R = window.__REPORTS__ || {};
  var St = window.Studio;
  var esc = St.esc;
  var WORDS = {
    status: {inception: "Just started", saved: "Defined", in_validation: "Being validated", in_production: "In production"},
    cadence: {daily: "Daily", weekly: "Weekly", monthly: "Monthly", quarterly: "Quarterly", semi_annual: "Twice a year", annual: "Yearly", on_demand: "On demand"},
    type: {text: "Text", "enum": "One of a list", number: "A number", integer: "A whole number", percent: "A percentage", currency: "An amount", currency_pair: "Two amounts"},
    lineage: {unmapped: "Not mapped yet", proposed: "Proposed", verified: "Verified"},
    change: {added: "Added", changed: "Changed", removed: "Removed"}
  };
  var LANG = {en: "English", fr: "French", es: "Spanish", de: "German", it: "Italian", pt: "Portuguese", nl: "Dutch"};
  function word(k, v) { return (WORDS[k] && WORDS[k][v]) || ""; }
  function cap(t) { return t ? t.charAt(0).toUpperCase() + t.slice(1) : ""; }
  function and(parts) { parts = parts.filter(Boolean); return parts.length < 2 ? parts.join("") : parts.slice(0, -1).join(", ") + " and " + parts[parts.length - 1]; }
  // a name written as an identifier ("fund_name") reads as words ("Fund name")
  function human(name) { return /^[a-z0-9_]+$/.test(name || "") ? cap(String(name).replace(/_/g, " ")) : (name || ""); }
  var MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
  function date(v) { var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(v || ""); return m ? (+m[3]) + " " + MONTHS[+m[2] - 1] + " " + m[1] : (v || ""); }
  function lang(code) { var k = String(code || "").toLowerCase().slice(0, 2); return LANG[k] || String(code || ""); }
  function text(t) { return t ? "<span>" + t + "</span>" : ""; }
  function missing(t) { return '<span class="studio-none">' + esc(t) + "</span>"; }
  function tag(t, on) { return t ? '<span class="tag' + (on ? " on" : "") + '">' + esc(t) + "</span>" : ""; }
  function facts(list) { var s = list.filter(Boolean); return s.length ? '<div class="facts">' + s.join("") + "</div>" : ""; }
  function links(refs) { return and((refs || []).filter(function (r) { return r && r.name; }).map(function (r) { return St.link(r.id, r.name); })); }

  function fieldRow(f, locales) {
    var meanings = f.meanings || [];
    var first = meanings.filter(function (m) { return m.locale === locales[0]; })[0] || meanings[0] || {};
    var others = meanings.filter(function (m) { return m !== first && m.label; }).map(function (m) {
      return '<span class="other">' + esc(lang(m.locale)) + ": " + esc(m.label) + "</span>";
    });
    var col = (f.column || [])[0];
    var source = col ? St.link(col.id, col.name) + ((col.pipeline || []).length ? '<br><span class="other">in the pipeline: ' + links(col.pipeline) + "</span>" : "") : "";
    var computed = (f.computed || [])[0];
    var from = source || (computed ? "Calculated" + (computed.inputs && computed.inputs.length ? " from " + links(computed.inputs) : "") : missing("Not mapped yet"));
    var rules = (f.rules || []).map(function (r) { return esc(r.text || r.name); });
    return '<tr id="' + esc(f.id) + '"><td class="label"><strong>' + esc(first.label || human(f.name)) + "</strong>" + others.join("<br>") + "</td>" +
      "<td>" + esc(first.definition || (f.summary !== f.name ? f.summary : "") || "") + (rules.length ? '<br><span class="other">Rule: ' + rules.join("; ") + "</span>" : "") + "</td>" +
      "<td>" + esc(word("type", f.type)) + "</td><td>" + from + (col && f.lineage && f.lineage !== "verified" ? '<br><span class="other">' + esc(word("lineage", f.lineage)) + "</span>" : "") + "</td></tr>";
  }

  function sections(r) {
    var locales = (r.locales && r.locales.length) ? r.locales : ["en"];
    return (r.sections || []).map(function (s) {
      var rows = (s.fields || []).map(function (f) { return fieldRow(f, locales); });
      return '<div class="studio-card" id="' + esc(s.id) + '"><h3>' + esc(s.name) + "</h3>" +
        (s.purpose ? "<p>" + esc(cap(s.purpose)) + "</p>" : "") + (s.when ? facts([text("Shown when " + esc(s.when) + ".")]) : "") +
        (rows.length ? '<div class="table-wrap"><table class="fields"><thead><tr><th>What it shows</th><th>What it means</th><th>Kind</th><th>Where it comes from</th></tr></thead><tbody>' +
                       rows.join("") + "</tbody></table></div>" : facts([missing("No field recorded yet.")])) + "</div>";
    }).join("");
  }

  function runs(r) {
    return (r.releases || []).map(function (rel) {
      var sch = (rel.schedule || [])[0], pub = (rel.publish || [])[0], watch = (rel.watch || [])[0], ok = (rel.approval || [])[0];
      var keep = pub && pub.retention ? (pub.retention % 365 === 0 ? (pub.retention / 365) + " years" : pub.retention + " days") : "";
      var title = rel.version ? "Template release " + rel.version : (rel.name && rel.name.length > 2 ? rel.name : "Template release");
      return '<div class="studio-card" id="' + esc(rel.id) + '"><h3>' + esc(title) + "</h3>" + (rel.frozen ? tag("Frozen", true) : "") + facts([
        sch ? text(esc(word("cadence", sch.cadence) || "Runs") + (sch.runOn ? ", " + esc(sch.runOn) : "") + (sch.asOf ? "; figures as of " + esc(sch.asOf) : "") +
                   (sch.timezone ? " (" + esc(sch.timezone) + " time)" : "") + ".") : missing("Nobody has said when it runs."),
        pub ? text("Published as " + esc(and((pub.formats || []).map(String))) + (keep ? ", kept " + esc(keep) : "") + ".") : "",
        watch ? text((watch.within ? "Delivered within " + esc(watch.within) + " hours" : "") +
                     (watch.alert && watch.alert.length ? (watch.within ? "; " : "") + "if it fails, " + esc(and(watch.alert)) + " " + (watch.alert.length > 1 ? "are" : "is") + " alerted" : "") + ".") : "",
        ok ? text("Before release, " + (ok.sampleRate ? esc(Math.round(ok.sampleRate * 100)) + "% of documents" : "a sample") + (ok.sampleMin ? " (at least " + esc(ok.sampleMin) + ")" : "") +
                  " are reviewed" + (ok.reviewer ? " by " + esc(ok.reviewer) : "") + ".") : ""
      ]) + "</div>";
    }).join("");
  }

  function history(r) {
    var items = (r.history || []).map(function (h) {
      return "<li>" + esc(word("status", h.status) || h.status) + (h.at ? ", " + esc(date(h.at)) : "") + (h.by ? ", by " + esc(h.by) : "") + (h.note ? ": " + esc(h.note) : "") + ".</li>";
    }).concat((r.revisions || []).map(function (v) {
      var n = (v.changes || []).length;
      return "<li>Revised" + (v.at ? " on " + esc(date(v.at)) : "") + (v.by ? " by " + esc(v.by) : "") + (v.reason ? ": " + esc(v.reason.replace(/\.$/, "")) : "") +
             (n ? " (" + (n === 1 ? "one change" : n + " changes") + ")" : "") + ".</li>";
    }));
    return items.length ? '<ul class="facts">' + items.join("") + "</ul>" : "";
  }

  function report(r) {
    var how = [word("cadence", r.cadence), r.locales && r.locales.length ? "in " + and(r.locales.map(lang)) : ""].filter(Boolean).join(", ");
    var table = (r.table || [])[0];
    var params = (r.parameters || []).map(function (p) {
      return "<li>" + St.link(p.id, human(p.name)) + (p.definition ? ": " + esc(p.definition) : "") + ((p.bound || []).length ? " (from " + links(p.bound) + ")" : "") + "</li>";
    });
    var rules = (r.rules || []).map(function (x) { return "<li>" + esc(x.text || x.name) + (x.regulatory ? " " + tag("Regulatory") : "") + "</li>"; });
    var parts = [
      "<p>" + esc(cap(r.purpose || r.summary || "")) + "</p>",
      facts([how ? text(esc(cap(how)) + ".") : "", r.audience && r.audience.length ? text("For " + esc(and(r.audience)) + ".") : "",
             r.owner ? text("Owned by " + esc(r.owner) + ".") : "", r.version ? text("Version " + esc(r.version) + ".") : ""]),
      params.length ? "<h3>What identifies a document</h3><ul class=\"facts\">" + params.join("") + "</ul>" : "",
      "<h3>Where its data comes from</h3>" + facts([table ? text(St.link(table.id, table.name) + ((table.source || []).length ? ", in " + links(table.source) : "") + ".") :
                                                            missing("Nobody has said which table it reads."),
                                                    table && (table.pipeline || []).length ? text("Fed by the pipeline's " + links(table.pipeline) + ".") : ""]),
      rules.length ? "<h3>Its rules</h3><ul class=\"facts\">" + rules.join("") + "</ul>" : "",
      "<h3>What it shows</h3>" + (sections(r) || facts([missing("No section recorded yet.")])),
      (r.releases || []).length ? "<h3>When it runs and where it goes</h3>" + runs(r) : "",
      history(r) ? "<h3>Its history</h3>" + history(r) : ""
    ];
    return '<section class="report" id="' + esc(r.id) + '"><h2>' + esc(r.name) + "</h2>" +
      tag(word("status", r.status), r.status === "in_production") + parts.join("") + "</section>";
  }

  St.ready(function () {
    var list = R.reports || [];
    document.getElementById("toc").innerHTML = list.length > 1 ? list.map(function (r) {
      return '<li><a href="#' + esc(r.id) + '">' + esc(r.name) + "</a></li>"; }).join("") : "";
    document.getElementById("reports").innerHTML = list.length ? list.map(report).join("") :
      '<p class="studio-none">No report type is defined yet.</p>';
    St.focus();
  });
})();
