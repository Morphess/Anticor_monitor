// Кабінет керівника (KER). Дані беруться лише з /api/management/*: бекенд сам рахує показники
// по гілці підрозділу керівника, строки, ризики й рекомендації.
(function () {
  "use strict";
  const el = Api.el;

  const PRIORITY = {
    critical: { label: "Критичний", level: "high" },
    high: { label: "Високий", level: "high" },
    medium: { label: "Середній", level: "mid" },
    low: { label: "Низький", level: "low" },
  };
  const RISK_LEVEL = {
    critical: { label: "Критичний", cls: "risk-high" },
    high: { label: "Високий", cls: "risk-high" },
    medium: { label: "Середній", cls: "risk-mid" },
    low: { label: "Низький", cls: "risk-low" },
  };
  const TREND = {
    improved: { label: "Покращився", cls: "risk-low" },
    worsened: { label: "Погіршився", cls: "risk-high" },
    unchanged: { label: "Без змін", cls: "" },
    no_data: { label: "Немає даних", cls: "" },
  };
  const OBJECT = { zakhid: "Захід", ryzyk: "Ризик" };
  const REC_LIMIT = 10;

  const programSel = document.getElementById("program");
  const periodSel = document.getElementById("period");
  let deptNames = {};
  let showAllRecs = false;

  function query() {
    const q = new URLSearchParams({ period: periodSel.value });
    if (programSel.value) q.set("program_id", programSel.value);
    return "?" + q.toString();
  }
  function deptName(id) { return id ? (deptNames[id] || Api.deptName(id)) : "Співвиконання"; }
  function num(v) { return v === null || v === undefined ? "—" : String(Number(v)); }
  function emptyRow(tbody, cols, text) {
    tbody.appendChild(el("tr", {}, [el("td", { colspan: String(cols), class: "muted", text: text })]));
  }

  // Періоди: поточний рік ± 2 (програм керівник не отримує, тож меж програми не знаємо).
  function fillPeriods() {
    const y = new Date().getFullYear();
    Api.fillPeriods(periodSel, [{ start_date: (y - 2) + "-01-01", end_date: (y + 1) + "-12-31" }]);
  }

  function fillPrograms(ids) {
    const keep = programSel.value;
    programSel.innerHTML = "";
    programSel.appendChild(el("option", { value: "", text: "Усі програми (" + ids.length + ")" }));
    ids.forEach(function (id) { programSel.appendChild(el("option", { value: id, text: id })); });
    programSel.value = ids.indexOf(keep) !== -1 ? keep : "";
  }

  function renderHeader(d) {
    document.getElementById("dept-title").textContent = d.department_name;
    const other = d.scope_department_ids.length - 1;
    document.getElementById("dept-scope").textContent =
      (other > 0 ? "Разом із підпорядкованими підрозділами: " + other + ". " : "") +
      "Станом на " + Api.fmtDate(d.as_of) + ", " + Api.periodLabel(d.period) + ".";
  }

  function renderCards(d) {
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
    const parts = [
      ["s-done", d.approved_completed, "Виконано й погоджено", "var(--ok)"],
      ["s-review", d.completed - d.approved_completed + d.partial, "Виконано / частково, без погодження", "var(--review)"],
      ["s-rework", d.in_progress, "У роботі", "var(--warn)"],
      ["s-not", d.not_completed, "Не виконано", "var(--bad)"],
      ["s-idle", d.not_started, "Не розпочато", "var(--idle)"],
    ];
    if (!d.total) return;
    stack.appendChild(el("div", { class: "stack", role: "img", "aria-label": "Розподіл заходів за станом" },
      parts.filter(function (p) { return p[1] > 0; }).map(function (p) {
        return el("span", { class: p[0], style: "flex:" + p[1], title: p[2] + ": " + p[1] });
      })));
    stack.appendChild(el("ul", { class: "legend" }, parts.map(function (p) {
      return el("li", {}, [el("i", { style: "background:" + p[3] }), p[2] + " · " + p[1]]);
    })));
  }

  function renderRecs(r) {
    const box = document.getElementById("recs");
    box.innerHTML = "";
    document.getElementById("recs-sub").textContent =
      "Сформовано автоматично (" + r.total + "); рішення ухвалює керівник";
    if (!r.recommendations.length) {
      box.appendChild(el("p", { class: "muted", text: "Відхилень, що потребують управлінських рішень, не виявлено." }));
      return;
    }
    const list = showAllRecs ? r.recommendations : r.recommendations.slice(0, REC_LIMIT);
    box.appendChild(el("div", { class: "recs" }, list.map(function (x) {
      const p = PRIORITY[x.priority] || PRIORITY.low;
      return el("article", { class: "rec", "data-level": p.level }, [
        el("div", {}, [
          el("h3", { text: x.title }),
          el("p", { text: x.reason }),
          el("div", { class: "action" }, [el("b", { text: "Рекомендована дія: " }), x.suggestion]),
          el("div", { class: "refs" }, [
            el("span", { class: "chip", text: (OBJECT[x.object_type] || x.object_type) + " " + x.object_id }),
            el("span", { class: "chip", text: "Програма " + x.program_id }),
          ]),
        ]),
        el("div", { class: "who-acts" }, [
          el("span", { class: "lvl", text: p.label + " пріоритет" }),
          x.source === "risk_flag" ? "Сигнал Risk Flags" : "Контроль виконання",
        ]),
      ]);
    })));
    if (r.recommendations.length > REC_LIMIT) {
      const btn = el("button", { type: "button", class: "btn",
        text: showAllRecs ? "Згорнути" : "Показати всі (" + r.recommendations.length + ")" });
      btn.addEventListener("click", function () { showAllRecs = !showAllRecs; renderRecs(r); });
      box.appendChild(el("p", { class: "note" }, [btn]));
    }
  }

  function renderDeadlines(list) {
    const tbody = document.getElementById("deadlines");
    tbody.innerHTML = "";
    if (!list.length) return emptyRow(tbody, 5, "Прострочених і найближчих строків немає.");
    list.forEach(function (x) {
      const chip = x.days_left < 0
        ? el("span", { class: "chip late", text: "прострочено " + -x.days_left + " дн." })
        : el("span", { class: "chip soon", text: x.days_left ? "ще " + x.days_left + " дн." : "сьогодні" });
      tbody.appendChild(el("tr", {}, [
        el("td", { class: "nowrap num-cell", text: x.measure_id }),
        el("td", { text: x.description }),
        el("td", { text: deptName(x.responsible_department_id) }),
        el("td", { class: "nowrap" }, [el("div", { text: Api.fmtDate(x.deadline_on) }), chip]),
        el("td", {}, [Api.statusBadge(Api.statusOf({ status: x.status, approved_by_coordinator: x.approved }))]),
      ]));
    });
  }

  function bar(done, total) {
    const pct = total ? Math.round(done * 100 / total) : 0;
    return el("div", {}, [
      el("div", { class: "small", text: done + " / " + total + " · " + pct + " %" }),
      el("div", { class: "bar", "aria-hidden": "true" }, [el("span", { style: "width:" + pct + "%" })]),
    ]);
  }

  function renderDepartments(rows) {
    const tbody = document.getElementById("by-dept");
    tbody.innerHTML = "";
    if (!rows.length) return emptyRow(tbody, 5, "Заходів немає.");
    rows.forEach(function (r) {
      tbody.appendChild(el("tr", {}, [
        el("td", { text: r.department_name }),
        el("td", { class: "num-cell", text: String(r.total) }),
        el("td", {}, [bar(r.approved_completed, r.total)]),
        el("td", { class: "num-cell" + (r.overdue ? " risk-high" : ""), text: String(r.overdue) }),
        el("td", { class: "num-cell", text: String(r.awaiting_approval) }),
      ]));
    });
  }

  function renderRisks(list) {
    const tbody = document.getElementById("risks");
    tbody.innerHTML = "";
    if (!list.length) return emptyRow(tbody, 7, "Ризиків для підрозділу немає.");
    const order = { critical: 0, high: 1, medium: 2, low: 3 };
    list.slice().sort(function (a, b) { return order[a.level] - order[b.level]; }).forEach(function (r) {
      const lv = RISK_LEVEL[r.level] || RISK_LEVEL.low;
      const tr = TREND[r.trend] || TREND.no_data;
      const arrow = r.indicator_direction === "decrease" ? "↓" : "↑";
      tbody.appendChild(el("tr", {}, [
        el("td", {}, [el("div", { text: r.title }), el("div", { class: "small muted", text: r.risk_id + " · " + r.program_id })]),
        el("td", {}, [el("span", { class: "risk " + lv.cls, text: lv.label })]),
        el("td", { text: r.indicator_name }),
        el("td", { class: "nowrap", text: num(r.baseline) + " → " + num(r.target) + " " + arrow }),
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

  async function load() {
    Api.showError(null);
    const q = query();
    try {
      const [dash, recs, deadlines, risks] = await Promise.all([
        Api.get("/api/management/dashboard" + q),
        Api.get("/api/management/recommendations" + q),
        Api.get("/api/management/deadlines" + q),
        Api.get("/api/management/risks" + q),
      ]);
      deptNames = {};
      dash.departments.forEach(function (r) { if (r.department_id) deptNames[r.department_id] = r.department_name; });
      if (!programSel.value) fillPrograms(dash.program_ids);
      renderHeader(dash);
      renderCards(dash);
      renderRecs(recs);
      renderDeadlines(deadlines);
      renderDepartments(dash.departments);
      renderRisks(risks);
    } catch (err) { Api.showError(err); }
  }

  (async function start() {
    if (!await Api.requireRole("KER")) return;
    fillPeriods();
    periodSel.addEventListener("change", load);
    programSel.addEventListener("change", function () { showAllRecs = false; load(); });
    load();
  })();
})();
