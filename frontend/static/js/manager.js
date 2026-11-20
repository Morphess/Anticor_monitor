// Кабінет KER: тільки читання, лише API /api/management/*.
// Не звертається до маршрутів /management/programs чи /management/measures: їх немає.
(function () {
  "use strict";
  const el = Api.el;
  const periodSel = document.getElementById("period");
  const PAGE_SIZES = [10, 25, 50, 100];
  const state = {};
  ["programs", "recs", "risks", "depts"].forEach(function (id) { state[id] = { page: 1, size: 25 }; });
  let dashboard = null;
  let recommendations = [];
  let risks = [];
  let deadlines = [];

  const LEVELS = {
    critical: ["Критичний", "risk-high"], high: ["Високий", "risk-high"],
    medium: ["Середній", "risk-mid"], low: ["Низький", "risk-low"],
  };
  const TRENDS = {
    improved: "Покращується", worsened: "Погіршується",
    unchanged: "Без змін", no_data: "Немає вимірювань",
  };
  function q(id) { return (document.getElementById(id + "-search").value || "").trim().toLowerCase(); }
  function matches(fields, query) { return !query || fields.join(" ").toLowerCase().includes(query); }
  function asText(v) { return v === null || v === undefined ? "—" : String(v); }
  function label(id, n) {
    const node = document.getElementById("tab-" + id + "-n");
    if (node) node.textContent = n ? "(" + n + ")" : "";
  }
  function paginate(id, rows, redraw) {
    const cfg = state[id];
    const totalPages = Math.max(1, Math.ceil(rows.length / cfg.size));
    cfg.page = Math.min(cfg.page, totalPages);
    const from = (cfg.page - 1) * cfg.size;
    [id + "-pager-top", id + "-pager"].forEach(function (key) {
      Api.renderPager(document.getElementById(key), cfg, rows.length, {
        sizes: PAGE_SIZES, rerender: redraw,
      });
    });
    return rows.slice(from, from + cfg.size);
  }
  function emptyBox(container, message) {
    container.replaceChildren(el("p", { class: "muted", text: message }));
  }
  function miniCard(labelText, value, tone) {
    return el("div", { class: "card", "data-tone": tone || undefined }, [
      el("div", { class: "n", text: String(value) }),
      el("div", { class: "l", text: labelText }),
    ]);
  }
  function drawOverview() {
    const d = dashboard;
    const kind = "Керівник підрозділу";
    document.getElementById("ker-kind").textContent = kind;
    document.getElementById("dept-title").textContent = d.department_name;
    document.getElementById("dept-scope").textContent =
      "Підрозділ " + d.department_id + " та підлеглі: " + d.scope_department_ids.length +
      ". Лише перегляд · станом на " + Api.fmtDate(d.as_of) + ".";
    const c = document.getElementById("cards");
    c.replaceChildren(
      miniCard("Усього заходів", d.total),
      miniCard("Погоджено виконаних", d.approved_completed, "ok"),
      miniCard("Очікують погодження", d.awaiting_approval, "review"),
      miniCard("Прострочені", d.overdue, "bad"),
      miniCard("Строк наближається", d.due_soon, "warn"),
      miniCard("Ризики високі / критичні", d.high_risks + " / " + d.critical_risks, "warn"),
    );
    const stack = document.getElementById("stack");
    stack.replaceChildren(el("div", { class: "table-wrap" }, [
      el("h2", { text: "На що звернути увагу" }),
      ...(recommendations.length ? recommendations.slice(0, 5).map(recommendationCard) :
        [el("p", { class: "muted", text: "Наразі немає рекомендацій за вибраний період." })]),
    ]));
  }
  function recommendationCard(rec) {
    const level = LEVELS[rec.priority] || LEVELS.low;
    return el("article", { class: "rec" }, [
      el("h3", { text: rec.title }),
      el("div", { class: "small muted", text: rec.code + " · Програма " + rec.program_id +
        " · " + rec.object_type + ": " + rec.object_id }),
      el("p", { text: rec.reason }),
      el("p", {}, [el("b", { text: "Рекомендація: " }), rec.suggestion]),
      el("span", { class: "risk " + level[1], text: level[0] }),
    ]);
  }
  function drawPrograms() {
    const box = document.getElementById("programs");
    const query = q("programs");
    const filter = document.getElementById("programs-filter").value;
    let rows = (dashboard.program_ids || []).map(function (id) {
      const relatedRec = recommendations.filter(function (r) { return r.program_id === id; });
      const relatedDue = deadlines.filter(function (r) { return r.program_id === id; });
      return { id: id, recs: relatedRec, deadlines: relatedDue };
    }).filter(function (p) {
      if (!matches([p.id, ...p.recs.map(function (r) { return r.title; })], query)) return false;
      if (filter === "flagged") return p.recs.length > 0;
      if (filter === "overdue") return p.deadlines.some(function (r) { return r.category === "overdue"; });
      if (filter === "pending") return p.recs.some(function (r) { return /погоджен/i.test(r.reason); });
      return true;
    });
    label("programs", dashboard.program_ids.length);
    const page = paginate("programs", rows, drawPrograms);
    box.replaceChildren(...(page.length ? page.map(function (p) {
      return el("article", { class: "prog" }, [
        el("div", { class: "row-head" }, [
          el("b", { text: "Програма " + p.id }),
          el("span", { class: "muted small", text: "Рекомендацій: " + p.recs.length +
            " · контрольних строків: " + p.deadlines.length }),
        ]),
        el("div", { class: "prog-body" }, [
          el("p", { class: "muted small", text: "Список усіх заходів недоступний для KER через поточний API. Тут показано лише доступні управлінські сигнали." }),
          ...p.deadlines.slice(0, 8).map(function (d) {
            return el("p", { class: "small", text: d.measure_id + " · " + d.description +
              " · до " + Api.fmtDate(d.deadline_on) + " (" + d.category + ")" });
          }),
        ]),
      ]);
    }) : [el("p", { class: "muted", text: "Програм за цим запитом не знайдено." })]));
  }
  function drawRecs() {
    const box = document.getElementById("recs");
    const query = q("recs"), filter = document.getElementById("recs-filter").value;
    const rows = recommendations.filter(function (r) {
      return (!filter || r.priority === filter) &&
        matches([r.title, r.reason, r.suggestion, r.program_id, r.object_id, r.code], query);
    });
    label("recs", recommendations.length);
    const page = paginate("recs", rows, drawRecs);
    if (!page.length) return emptyBox(box, "Рекомендацій не знайдено.");
    box.replaceChildren(...page.map(recommendationCard));
  }
  function tableRow(cells) { return el("tr", {}, cells.map(function (t) { return el("td", { text: asText(t) }); })); }
  function drawRisks() {
    const body = document.getElementById("risks");
    const query = q("risks"), filter = document.getElementById("risks-filter").value;
    const rows = risks.filter(function (r) { return (!filter || r.level === filter) &&
      matches([r.title, r.risk_id, r.indicator_name, r.program_id], query); });
    label("risks", risks.length);
    const page = paginate("risks", rows, drawRisks);
    body.replaceChildren(...(page.length ? page.map(function (r) {
      return tableRow([r.risk_id + " · " + r.title, LEVELS[r.level]?.[0] || r.level,
        r.indicator_name, asText(r.baseline) + " → " + asText(r.target),
        r.actual, TRENDS[r.trend] || r.trend, r.has_measures_in_program ? "Є" : "Немає"]);
    }) : [tableRow(["Ризиків не знайдено", "", "", "", "", "", ""])]));
  }
  function drawDepts() {
    const body = document.getElementById("by-dept");
    const query = q("depts"), filter = document.getElementById("depts-filter").value;
    const source = dashboard.departments || [];
    const rows = source.filter(function (d) {
      return matches([d.department_id, d.department_name], query) &&
        (filter !== "overdue" || d.overdue > 0) && (filter !== "pending" || d.awaiting_approval > 0);
    });
    label("depts", source.length);
    const page = paginate("depts", rows, drawDepts);
    body.replaceChildren(...(page.length ? page.map(function (d) {
      return tableRow([d.department_name, d.total, d.approved_completed + " / " + d.total,
        d.overdue, d.awaiting_approval]);
    }) : [tableRow(["Підрозділів не знайдено", "", "", "", ""])]));
  }
  function renderAll() {
    drawOverview(); drawPrograms(); drawRecs(); drawRisks(); drawDepts();
  }
  async function reload() {
    Api.showError(null);
    const qs = "?period=" + encodeURIComponent(periodSel.value);
    try {
      const [d, rec, riskList, due] = await Promise.all([
        Api.get("/api/management/dashboard" + qs),
        Api.get("/api/management/recommendations" + qs + "&limit=500"),
        Api.get("/api/management/risks" + qs),
        Api.get("/api/management/deadlines" + qs),
      ]);
      dashboard = d; recommendations = rec.recommendations || [];
      risks = riskList; deadlines = due;
      renderAll();
    } catch (e) { Api.showError(e); }
  }
  async function start() {
    if (!await Api.requireRole("KER")) return;
    const y = new Date().getFullYear();
    Api.fillPeriods(periodSel, [{ start_date: (y - 2) + "-01-01", end_date: (y + 1) + "-12-31" }]);
    periodSel.addEventListener("change", reload);
    document.querySelectorAll("[data-tab]").forEach(function (tab) {
      tab.addEventListener("click", function () {
        document.querySelectorAll("[data-tab]").forEach(function (t) {
          t.setAttribute("aria-selected", String(t === tab));
        });
        document.querySelectorAll("[data-panel]").forEach(function (panel) {
          panel.classList.toggle("hidden", panel.dataset.panel !== tab.dataset.tab);
        });
      });
    });
    ["programs", "recs", "risks", "depts"].forEach(function (key) {
      [key + "-search", key + "-filter"].forEach(function (id) {
        document.getElementById(id).addEventListener(id.endsWith("-search") ? "input" : "change", function () {
          state[key].page = 1;
          ({ programs: drawPrograms, recs: drawRecs, risks: drawRisks, depts: drawDepts })[key]();
        });
      });
    });
    await reload();
  }
  start();
})();
