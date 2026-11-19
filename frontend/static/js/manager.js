// Кабінет керівника (KER): лише перегляд, вигляд і поведінка як в адмінці —
// вкладки, на кожній «пошук + фільтр», сторінки зверху й знизу.
// Керівник відомства бачить усі програми й підрозділи, на які їх координовано;
// керівник підрозділу — програми, координовані на його підрозділ, і відділи-виконавці.
// Дані — лише /api/management/*; рекомендації бекенду показуються й біля заходів.
(function () {
  "use strict";
  const el = Api.el;

  const PRIORITY = {
    critical: { label: "Критичний", level: "high", chip: "late", rank: 0 },
    high: { label: "Високий", level: "high", chip: "late", rank: 1 },
    medium: { label: "Середній", level: "mid", chip: "soon", rank: 2 },
    low: { label: "Низький", level: "low", chip: "", rank: 3 },
  };
  const RISK_LEVEL = {
    critical: { label: "Критичний", cls: "risk-high", rank: 0 },
    high: { label: "Високий", cls: "risk-high", rank: 1 },
    medium: { label: "Середній", cls: "risk-mid", rank: 2 },
    low: { label: "Низький", cls: "risk-low", rank: 3 },
  };
  const TREND = {
    improved: { label: "Покращився", cls: "risk-low" },
    worsened: { label: "Погіршився", cls: "risk-high" },
    unchanged: { label: "Без змін", cls: "" },
    no_data: { label: "Немає даних", cls: "" },
  };
  const OBJECT = { zakhid: "Захід", ryzyk: "Ризик", order_change_alert: "Зміна наказу", pidrozdil: "Підрозділ" };

  const periodSel = document.getElementById("period");
  const open = new Set();
  let agency = false;
  let programs = [], measures = [], recsByMeasure = {}, allRecs = [], risks = [], depts = [];

  // ---------- пошук і пагінація (як в адмінці)
  const PAGE_SIZES = [10, 25, 50, 100];
  const PAGES = {};
  ["programs", "recs", "risks", "depts"].forEach(function (key) {
    PAGES[key] = { page: 1, size: readSize(key) };
  });
  function readSize(key) {
    try {
      const v = Number(localStorage.getItem("anticor_ker_size_" + key));
      return PAGE_SIZES.indexOf(v) !== -1 ? v : (key === "programs" ? 10 : 25);
    } catch (e) { return key === "programs" ? 10 : 25; }
  }
  function norm(v) { return String(v == null ? "" : v).toLocaleLowerCase("uk"); }
  function query(key) { return norm(document.getElementById(key + "-search").value.trim()); }
  function filterValue(key) { return document.getElementById(key + "-filter").value; }
  // Збіг усіх слів запиту з будь-якими полями (у довільному порядку).
  function matchesQuery(fields, q) {
    if (!q) return true;
    const hay = fields.map(norm).join(" ");
    return q.split(/\s+/).every(function (w) { return hay.indexOf(w) !== -1; });
  }
  // Малює панелі сторінок зверху й знизу; повертає видимий шматок списку.
  function pageSlice(key, items, rerender, noun) {
    const state = PAGES[key];
    [key + "-pager-top", key + "-pager"].forEach(function (id) {
      Api.renderPager(document.getElementById(id), state, items.length, {
        sizes: PAGE_SIZES, noun: noun, rerender: rerender,
        onSize: function (v) { try { localStorage.setItem("anticor_ker_size_" + key, String(v)); } catch (e) { /* без збереження */ } },
      });
    });
    const start = (state.page - 1) * state.size;
    return items.slice(start, start + state.size);
  }
  function setCount(key, n) { document.getElementById("tab-" + key + "-n").textContent = n ? "(" + n + ")" : ""; }

  // ---------- дрібні помічники
  function num(v) { return v === null || v === undefined ? "—" : String(Number(v)); }
  function emptyRow(tbody, cols, text) {
    tbody.appendChild(el("tr", {}, [el("td", { colspan: String(cols), class: "muted", text: text })]));
  }
  function isDone(m) { return m.status === "completed" && m.approved; }
  function measureNo(m) {
    return (m.section_number != null ? m.section_number + "." : "") + (m.sequence_number != null ? m.sequence_number : m.measure_id);
  }
  function statusBadge(m) {
    return Api.statusBadge(Api.statusOf(m.status === "not_started" && !m.submitted_at ? null : { status: m.status, approved_by_coordinator: m.approved }));
  }
  function counter(list) {
    return el("div", { class: "count", text: "Виконано " + list.filter(isDone).length + " / " + list.length });
  }
  function toggle(key) { open.has(key) ? open.delete(key) : open.add(key); renderPrograms(); }
  function daysLeft(m) {
    if (!m.deadline_on) return null;
    return Math.round((new Date(m.deadline_on) - new Date(new Date().toDateString())) / 864e5);
  }
  function deadlineText(m) {
    if (m.deadline_on) return Api.fmtDate(m.deadline_on);
    if (m.deadline_type === "ongoing") return "Постійно";
    return m.deadline_description || "—";
  }
  function deadlineChip(m) {
    const days = daysLeft(m);
    if (days === null || isDone(m)) return null;
    if (days < 0) return el("span", { class: "chip late", text: "прострочено " + -days + " дн." });
    if (days <= 14) return el("span", { class: "chip soon", text: days ? "ще " + days + " дн." : "сьогодні" });
    return null;
  }
  function topPriority(recs) {
    return recs.reduce(function (best, r) {
      const p = PRIORITY[r.priority] || PRIORITY.low;
      return !best || p.rank < best.rank ? p : best;
    }, null);
  }
  function measureLabel(id) {
    const m = measures.find(function (x) { return x.measure_id === id; });
    return m ? "Захід " + measureNo(m) + " (" + id + ")" : "Захід " + id;
  }

  // ---------- шапка й «Огляд»
  function renderHeader(d) {
    agency = d.scope === "agency";
    const kind = agency ? "Керівник відомства" : "Керівник підрозділу";
    document.getElementById("ker-kind").textContent = kind;
    document.querySelectorAll("[data-role-name]").forEach(function (n) { n.textContent = kind; });
    document.getElementById("dept-title").textContent = d.department_name;
    const other = d.scope_department_ids.length - 1;
    document.getElementById("dept-scope").textContent = (agency
      ? "Усі програми відомства"
      : "Програми, координовані на підрозділ" + (other > 0 ? "; підпорядкованих підрозділів: " + other : "")) +
      ". Лише перегляд. Станом на " + Api.fmtDate(d.as_of) + ".";
  }

  function renderOverview(d) {
    const box = document.getElementById("cards");
    box.innerHTML = "";
    const pct = function (n) { return d.total ? Math.round(n * 100 / d.total) + " %" : "—"; };
    [["Заходів", d.total, null, null],
     ["Виконано й погоджено", d.approved_completed, d.approved_completion_percent + " %", "ok"],
     ["Очікують погодження", d.awaiting_approval, pct(d.awaiting_approval), "review"],
     ["Строк ≤ 14 днів", d.due_soon, null, "warn"],
     ["Прострочено", d.overdue, pct(d.overdue), "bad"],
     ["Ризики: високі / критичні", d.high_risks + " / " + d.critical_risks, null, d.critical_risks ? "bad" : (d.high_risks ? "warn" : null)],
    ].forEach(function (x) {
      box.appendChild(el("div", { class: "card", "data-tone": x[3] || undefined }, [
        el("div", { class: "n", text: String(x[1]) }),
        el("div", { class: "l", text: x[0] }),
        x[2] ? el("div", { class: "sub", text: x[2] }) : null,
      ]));
    });
    const stack = document.getElementById("stack");
    stack.innerHTML = "";
    if (!d.total) return;
    const parts = [
      ["s-done", d.approved_completed, "Виконано й погоджено", "var(--ok)"],
      ["s-review", d.completed - d.approved_completed + d.partial, "Виконано / частково, без погодження", "var(--review)"],
      ["s-rework", d.in_progress, "У роботі", "var(--warn)"],
      ["s-not", d.not_completed, "Не виконано", "var(--bad)"],
      ["s-idle", d.not_started, "Не розпочато", "var(--idle)"],
    ];
    stack.appendChild(el("div", { class: "stack", role: "img", "aria-label": "Розподіл заходів за станом" },
      parts.filter(function (p) { return p[1] > 0; }).map(function (p) {
        return el("span", { class: p[0], style: "flex:" + p[1], title: p[2] + ": " + p[1] });
      })));
    stack.appendChild(el("ul", { class: "legend" }, parts.map(function (p) {
      return el("li", {}, [el("i", { style: "background:" + p[3] }), p[2] + " · " + p[1]]);
    })));
  }

  // ---------- «Програми»: дерево як у координатора, без дій
  function measureHit(m, q, f) {
    if (f === "flagged" && !(recsByMeasure[m.measure_id] || []).length) return false;
    if (f === "overdue" && !(daysLeft(m) !== null && daysLeft(m) < 0 && !isDone(m))) return false;
    if (f === "pending" && !(m.submitted_at && !m.approved)) return false;
    return matchesQuery([m.description, measureNo(m), m.measure_id, m.responsible_department_name, m.section_title,
      m.assigned_units.map(function (u) { return u.department_name; }).join(" ")], q);
  }

  function renderPrograms() {
    const root = document.getElementById("programs");
    const q = query("programs"), f = filterValue("programs");
    const byProg = Api.groupBy(measures, "program_id");
    const rows = [];
    programs.forEach(function (p) {
      const all = byProg[p.id] || [];
      const progHit = !f && q && matchesQuery([p.title, p.id, p.coordinator_department_name,
        p.dispatched_to.map(function (x) { return x.department_name; }).join(" ")], q);
      const list = !q && !f ? all : (progHit ? all : all.filter(function (m) { return measureHit(m, q, f); }));
      if ((q || f) && !progHit && !list.length) return;
      rows.push([p, all, list, !!(q || f) && !progHit]);
    });
    setCount("programs", programs.length);
    root.innerHTML = "";
    pageSlice("programs", rows, renderPrograms, "програм").forEach(function (r) {
      root.appendChild(programNode(r[0], r[1], r[2], r[3]));
    });
    if (!rows.length) {
      root.appendChild(el("p", { class: "muted", text: q || f ? "Нічого не знайдено."
        : (agency ? "Програм ще не створено." : "На ваш підрозділ ще не координовано жодної програми.") }));
    }
  }

  function programNode(p, all, list, forceOpen) {
    const key = "p:" + p.id;
    const isOpen = forceOpen || open.has(key);
    const node = el("div", { class: "prog" }, [
      el("button", { type: "button", class: "row-head", "aria-expanded": String(isOpen), onclick: function () { toggle(key); } }, [
        el("span", { class: "title" }, [
          el("span", { class: "code", text: p.id }),
          p.title,
          p.coordinator_department_name ? el("span", { class: "sub", text: "Координатор: " + p.coordinator_department_name }) : null,
        ]),
        el("span", { class: "meta", text: Api.fmtDate(p.start_date) + " – " + Api.fmtDate(p.end_date) }),
        counter(all),
      ]),
    ]);
    if (!isOpen) return node;
    const sent = p.dispatched_to.map(function (x) { return x.department_name; });
    const body = el("div", { class: "prog-body" }, [
      el("div", { class: "prog-tools" }, [
        el("div", { class: "small", text: sent.length ? "Координовано на: " + sent.join(", ") : "Ще не координовано на підрозділи" }),
      ]),
    ]);
    const bySec = {};
    list.forEach(function (m) { (bySec[m.section_id || "-"] = bySec[m.section_id || "-"] || []).push(m); });
    const secIds = Object.keys(bySec).sort(function (a, b) {
      return (bySec[a][0].section_number || 0) - (bySec[b][0].section_number || 0);
    });
    if (!secIds.length) body.appendChild(el("p", { class: "muted", style: "padding:8px 18px", text: "Заходів у вашій зоні немає." }));
    secIds.forEach(function (sid) { body.appendChild(sectionNode(p, sid, bySec[sid], forceOpen)); });
    node.appendChild(body);
    return node;
  }

  function finalDeadline(list) {
    const dates = list.map(function (m) { return m.deadline_on; }).filter(Boolean).sort();
    return dates.length ? "Кінцевий строк: " + Api.fmtDate(dates[dates.length - 1]) : "Строк: постійно";
  }

  function sectionNode(p, sid, list, forceOpen) {
    const key = "s:" + p.id + ":" + sid;
    const isOpen = forceOpen || open.has(key);
    const first = list[0];
    const title = first.section_number != null ? first.section_number + ". " + (first.section_title || "") : (first.section_title || "Без розділу");
    const node = el("div", { class: "sec" }, [
      el("button", { type: "button", class: "row-head", "aria-expanded": String(isOpen), onclick: function () { toggle(key); } }, [
        el("span", { class: "title", text: title }),
        el("span", { class: "meta", text: finalDeadline(list) }),
        counter(list),
      ]),
    ]);
    if (!isOpen) return node;
    const body = el("div", { class: "sec-body" });
    list.slice().sort(function (a, b) { return (a.sequence_number || 0) - (b.sequence_number || 0); })
      .forEach(function (m) { body.appendChild(measureNode(m)); });
    node.appendChild(body);
    return node;
  }

  function measureNode(m) {
    const key = "m:" + m.measure_id;
    const isOpen = open.has(key);
    const recs = recsByMeasure[m.measure_id] || [];
    const top = topPriority(recs);
    const node = el("div", { class: "measure", id: "row-" + m.measure_id }, [
      el("button", { type: "button", class: "row-head", "aria-expanded": String(isOpen), onclick: function () { toggle(key); } }, [
        el("span", { class: "num", text: measureNo(m) }),
        el("span", { text: m.description }),
        el("span", { class: "flags" }, [
          top ? el("span", { class: "chip " + top.chip, title: top.label + " пріоритет", text: "увага: " + recs.length }) : null,
        ]),
        statusBadge(m),
      ]),
    ]);
    if (isOpen) node.appendChild(el("div", { class: "detail" }, [unitsTable(m), recsBlock(recs)]));
    return node;
  }

  function actualDate(m) {
    if (!m.approved) return "—";
    const d = m.completed_on || (m.submitted_at || "").slice(0, 10);
    return d ? Api.fmtDate(d) : "—";
  }

  function unitsTable(m) {
    const units = m.assigned_units.map(function (u) { return u.department_name; }).join(", ");
    return el("div", { class: "units table-wrap" }, [
      el("table", { class: "grid" }, [
        el("thead", {}, [el("tr", {}, [
          el("th", { text: "Підрозділ" }), agency ? null : el("th", { text: "Відділи" }),
          el("th", { text: "Виконати до" }), el("th", { text: "Фактично виконано" }),
          el("th", { text: "Показник" }), el("th", { text: "Статус" }), el("th", { text: "Погодження" }),
        ])]),
        el("tbody", {}, [el("tr", {}, [
          el("td", { text: m.responsible_department_name || "Співвиконання" }),
          agency ? null : el("td", { text: units || "Не доручено" }),
          el("td", { class: "nowrap" }, [el("div", { text: deadlineText(m) }), deadlineChip(m)]),
          el("td", { class: "nowrap", text: actualDate(m) }),
          el("td", { class: "nowrap", text: m.indicator_target != null ? num(m.indicator_actual) + " / " + num(m.indicator_target) : "—" }),
          el("td", {}, [statusBadge(m)]),
          el("td", { text: m.approved ? "Погоджено" : (m.submitted_at ? "Очікує" : "—") }),
        ])]),
      ]),
    ]);
  }

  function recItem(r, withRefs) {
    const p = PRIORITY[r.priority] || PRIORITY.low;
    return el("article", { class: "rec", "data-level": p.level }, [
      el("div", {}, [
        el("h3", { text: r.title }),
        el("p", { text: r.reason }),
        el("div", { class: "action" }, [el("b", { text: "Рекомендована дія: " }), r.suggestion]),
        withRefs ? el("div", { class: "refs" }, [
          el("span", { class: "chip", text: r.object_type === "zakhid" ? measureLabel(r.object_id)
            : (OBJECT[r.object_type] || r.object_type) + " " + r.object_id }),
          el("span", { class: "chip", text: "Програма " + r.program_id }),
        ]) : null,
      ]),
      el("div", { class: "who-acts" }, [
        el("span", { class: "lvl", text: p.label + " пріоритет" }),
        r.source === "risk_flag" ? "Сигнал Risk Flags" : "Контроль виконання",
      ]),
    ]);
  }

  function recsBlock(recs) {
    if (!recs.length) return el("p", { class: "small muted", text: "Зауважень до заходу немає." });
    return el("div", {}, [
      el("h3", { text: "На що звернути увагу" }),
      el("div", { class: "recs" }, recs.map(function (r) { return recItem(r, false); })),
    ]);
  }

  // ---------- «Рекомендації»
  function renderRecs() {
    const box = document.getElementById("recs");
    const q = query("recs"), f = filterValue("recs");
    const list = allRecs.filter(function (r) {
      if (f && r.priority !== f) return false;
      return matchesQuery([r.title, r.reason, r.suggestion, r.object_id, r.program_id,
        r.object_type === "zakhid" ? measureLabel(r.object_id) : OBJECT[r.object_type]], q);
    });
    setCount("recs", allRecs.length);
    box.innerHTML = "";
    const page = pageSlice("recs", list, renderRecs, "рекомендацій");
    if (!list.length) {
      box.appendChild(el("p", { class: "muted", text: allRecs.length ? "Нічого не знайдено."
        : "Відхилень, що потребують управлінських рішень, не виявлено." }));
      return;
    }
    box.appendChild(el("div", { class: "recs" }, page.map(function (r) { return recItem(r, true); })));
  }

  // ---------- «Ризики»
  function renderRisks() {
    const tbody = document.getElementById("risks");
    const q = query("risks"), f = filterValue("risks");
    const list = risks.filter(function (r) {
      if (f && r.level !== f) return false;
      return matchesQuery([r.title, r.risk_id, r.program_id, r.indicator_name, (RISK_LEVEL[r.level] || {}).label], q);
    }).sort(function (a, b) { return (RISK_LEVEL[a.level] || RISK_LEVEL.low).rank - (RISK_LEVEL[b.level] || RISK_LEVEL.low).rank; });
    setCount("risks", risks.length);
    tbody.innerHTML = "";
    const page = pageSlice("risks", list, renderRisks, "ризиків");
    if (!list.length) return emptyRow(tbody, 7, risks.length ? "Нічого не знайдено." : "Ризиків немає.");
    page.forEach(function (r) {
      const lv = RISK_LEVEL[r.level] || RISK_LEVEL.low;
      const tr = TREND[r.trend] || TREND.no_data;
      tbody.appendChild(el("tr", {}, [
        el("td", {}, [el("div", { text: r.title }), el("div", { class: "small muted", text: r.risk_id + " · " + r.program_id })]),
        el("td", {}, [el("span", { class: "risk " + lv.cls, text: lv.label })]),
        el("td", { text: r.indicator_name }),
        el("td", { class: "nowrap", text: num(r.baseline) + " → " + num(r.target) + " " + (r.indicator_direction === "decrease" ? "↓" : "↑") }),
        el("td", { class: "nowrap" }, [
          el("div", { text: num(r.actual) }),
          r.measured_on ? el("div", { class: "small muted", text: Api.fmtDate(r.measured_on) }) : null,
        ]),
        el("td", {}, [
          tr.cls ? el("span", { class: "risk " + tr.cls, text: tr.label }) : el("span", { class: "muted", text: tr.label }),
          r.target_reached ? el("div", { class: "small muted", text: "ціль досягнуто" }) : null,
        ]),
        el("td", { text: r.has_measures_in_program ? "Є" : "Немає" }),
      ]));
    });
  }

  // ---------- «За підрозділами»
  function renderDepts() {
    const tbody = document.getElementById("by-dept");
    const q = query("depts"), f = filterValue("depts");
    const list = depts.filter(function (r) {
      if (f === "overdue" && !r.overdue) return false;
      if (f === "pending" && !r.awaiting_approval) return false;
      return matchesQuery([r.department_name, r.department_id], q);
    });
    setCount("depts", depts.length);
    tbody.innerHTML = "";
    const page = pageSlice("depts", list, renderDepts, "підрозділів");
    if (!list.length) return emptyRow(tbody, 5, depts.length ? "Нічого не знайдено." : "Заходів немає.");
    page.forEach(function (r) {
      const pct = r.total ? Math.round(r.approved_completed * 100 / r.total) : 0;
      tbody.appendChild(el("tr", {}, [
        el("td", { text: r.department_name }),
        el("td", { class: "num-cell", text: String(r.total) }),
        el("td", {}, [
          el("div", { class: "small", text: r.approved_completed + " / " + r.total + " · " + pct + " %" }),
          el("div", { class: "bar", "aria-hidden": "true" }, [el("span", { style: "width:" + pct + "%" })]),
        ]),
        el("td", { class: "num-cell" + (r.overdue ? " risk-high" : ""), text: String(r.overdue) }),
        el("td", { class: "num-cell", text: String(r.awaiting_approval) }),
      ]));
    });
  }

  // ---------- вкладки (як в адмінці) і завантаження
  function initTabs() {
    const tabs = document.querySelectorAll("[data-tab]");
    function show(name) {
      tabs.forEach(function (t) { t.setAttribute("aria-selected", String(t.dataset.tab === name)); });
      document.querySelectorAll("[data-panel]").forEach(function (panel) {
        panel.classList.toggle("hidden", panel.dataset.panel !== name);
      });
      try { localStorage.setItem("anticor_ker_tab", name); } catch (e) { /* без збереження */ }
    }
    tabs.forEach(function (t) { t.addEventListener("click", function () { show(t.dataset.tab); }); });
    let saved = null;
    try { saved = localStorage.getItem("anticor_ker_tab"); } catch (e) { /* немає сховища */ }
    if (saved && document.querySelector('[data-tab="' + saved + '"]')) show(saved);
  }

  function bindFilters(key, rerender) {
    const reset = function () { PAGES[key].page = 1; rerender(); };
    document.getElementById(key + "-search").addEventListener("input", reset);
    document.getElementById(key + "-filter").addEventListener("change", reset);
  }

  async function load() {
    Api.showError(null);
    const qs = "?period=" + encodeURIComponent(periodSel.value);
    try {
      const [dash, progs, list, recs, riskList] = await Promise.all([
        Api.get("/api/management/dashboard" + qs),
        Api.get("/api/management/programs" + qs),
        Api.get("/api/management/measures" + qs),
        Api.get("/api/management/recommendations" + qs + "&limit=500"),
        Api.get("/api/management/risks" + qs),
      ]);
      programs = progs;
      measures = list;
      risks = riskList;
      depts = dash.departments;
      allRecs = recs.recommendations;
      recsByMeasure = {};
      allRecs.forEach(function (r) {
        if (r.object_type === "zakhid") (recsByMeasure[r.object_id] = recsByMeasure[r.object_id] || []).push(r);
      });
      if (!open.size && programs.length) open.add("p:" + programs[0].id);
      renderHeader(dash);
      renderOverview(dash);
      renderPrograms();
      renderRecs();
      renderRisks();
      renderDepts();
    } catch (err) {
      document.getElementById("programs").innerHTML = "";
      Api.showError(err);
    }
  }

  (async function start() {
    if (!await Api.requireRole("KER")) return;
    initTabs();
    const y = new Date().getFullYear();
    Api.fillPeriods(periodSel, [{ start_date: (y - 2) + "-01-01", end_date: (y + 1) + "-12-31" }]);
    periodSel.addEventListener("change", load);
    bindFilters("programs", renderPrograms);
    bindFilters("recs", renderRecs);
    bindFilters("risks", renderRisks);
    bindFilters("depts", renderDepts);
    load();
  })();
})();
