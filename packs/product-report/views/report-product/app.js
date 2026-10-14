/* The front page of a report product: what it produces and for whom, its pages, what is still open. */
(function () {
  "use strict";
  var F = window.__FRONT__ || {};
  var St = window.Studio;
  var D = (St && St.data) || {};
  var esc = St.esc;
  var STATUS = {inception: "Just started", saved: "Defined", in_validation: "Being validated", in_production: "In production"};
  var CADENCE = {daily: "Daily", weekly: "Weekly", monthly: "Monthly", quarterly: "Quarterly", semi_annual: "Twice a year",
                 annual: "Yearly", on_demand: "On demand"};
  var STAGE = {idea: "An idea", discovery: "Being explored", specified: "Specified", building: "Being built", live: "Live", retired: "Retired"};
  var LANG = {en: "English", fr: "French", es: "Spanish", de: "German", it: "Italian", pt: "Portuguese", nl: "Dutch"};

  function and(parts) {
    parts = parts.filter(Boolean);
    return parts.length < 2 ? parts.join("") : parts.slice(0, -1).join(", ") + " and " + parts[parts.length - 1];
  }
  function languages(list) {
    return and((list || []).map(function (l) { var k = String(l).toLowerCase().slice(0, 2); return LANG[k] || String(l); }));
  }
  function section(title, html) { return html ? "<h2>" + esc(title) + "</h2>" + html : ""; }

  function reports() {
    var list = F.reports || [];
    if (!list.length) return '<p class="studio-none">No report type is defined yet.</p>';
    return list.map(function (r) {
      var how = [CADENCE[r.cadence] || "", r.locales && r.locales.length ? "in " + languages(r.locales) : ""].filter(Boolean).join(", ");
      return '<div class="studio-card" id="' + esc(r.id) + '"><h3>' + St.link(r.id, r.name) + "</h3>" +
        (r.purpose || r.summary ? "<p>" + esc(r.purpose || r.summary) + "</p>" : "") +
        '<p class="studio-muted">' + (STATUS[r.status] ? '<span class="front-tag">' + esc(STATUS[r.status]) + "</span> " : "") +
        esc(how ? how.charAt(0).toUpperCase() + how.slice(1) + "." : "") +
        (r.audience && r.audience.length ? " For " + esc(and(r.audience)) + "." : "") + "</p></div>";
    }).join("");
  }

  function people() {
    var list = F.people || [];
    if (!list.length) return "";
    return "<p>" + and(list.map(function (x) { return St.link(x.id, x.name); })) + ".</p>";
  }

  function pages() {
    var byName = {};
    (D.pages || []).forEach(function (p) { byName[p.name] = p; });
    var cards = [];
    (D.places || []).forEach(function (place) {
      place.pages.forEach(function (n) {
        var p = byName[n];
        if (!p || p.place === "technical") return;
        cards.push('<a class="front-page" href="../' + esc(p.path) + '"><div class="studio-card"><strong>' + esc(p.title) + "</strong>" +
                   (p.summary ? '<br><span class="studio-muted">' + esc(p.summary) + "</span>" : "") + "</div></a>");
      });
    });
    return cards.length ? '<div class="front-grid">' + cards.join("") + "</div>" : "";
  }

  function stillOpen() {
    var byName = {};
    (D.pages || []).forEach(function (p) { byName[p.name] = p; });
    var lines = [];
    Object.keys(D.open || {}).forEach(function (name) {
      var count = 0;
      (D.open[name] || []).forEach(function (e) { count += (e.items || []).length; });
      var p = byName[name];
      if (count && p) {
        lines.push('<li><a href="../' + esc(p.path) + '#studio-open">' + esc(p.title) + "</a>: " +
                   (count === 1 ? "one thing is still open" : count + " things are still open") + ".</li>");
      }
    });
    return '<div class="studio-open front-open"><h2>Still open</h2>' +
      (lines.length ? "<ul>" + lines.join("") + "</ul>" : '<p class="studio-none">Nothing is open on any page.</p>') + "</div>";
  }

  St.ready(function () {
    var prod = F.product || {};
    var name = prod.name || (D.project && D.project.name) || "The product";
    document.getElementById("title").textContent = name;
    document.title = name;
    document.getElementById("lead").innerHTML = esc(prod.summary || prod.vision || "") +
      (STAGE[prod.stage] ? ' <span class="front-tag">' + esc(STAGE[prod.stage]) + "</span>" : "");
    document.getElementById("front").innerHTML =
      section("What it produces", reports()) + section("Who it is for", people()) +
      section("The product, page by page", pages()) + stillOpen();
    St.focus();
  });
})();
