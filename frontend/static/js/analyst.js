// Кабінет аналітика: розріз за підрозділами й розділами, прогноз, рекомендації, вивантаження CSV.
(function () {
  "use strict";
  const el = Api.el;
  let last = null;

  Summary.start(function (d) {
    last = d;
    Summary.cards(Summary.countBy(d.measures, d.executions));
    Summary.insight(d);
    Summary.bySection(d);
    Summary.flagsByCode(d);

    const tbody = document.getElementById("by-dept");
    tbody.innerHTML = "";
    const groups = {};
    d.insight.items.forEach(function (it) {
      const k = it.m.responsible_department_id || "";
      (groups[k] = groups[k] || []).push(it);
    });
    const rows = Object.keys(groups).map(function (k) {
      const items = groups[k];
      const c = Summary.countBy(items.map(function (it) { return it.m; }), d.executions);
      const open = items.filter(function (it) { return it.status !== "done"; });
      return {
        k: k, c: c,
        atRisk: open.filter(function (it) { return it.level === "high"; }).length,
        avg: open.length ? Math.round(open.reduce(function (s, it) { return s + it.score; }, 0) / open.length) : 0,
      };
    }).sort(function (a, b) { return b.atRisk - a.atRisk || b.avg - a.avg; });
    if (!rows.length) return Summary.emptyRow(tbody, 9, "Заходів немає.");
    rows.forEach(function (r) {
      const c = r.c;
      tbody.appendChild(el("tr", {}, [
        el("td", { text: Api.deptName(r.k) }),
        el("td", { class: "num-cell", text: String(c.total) }),
        el("td", { class: "num-cell", text: String(c.done) }),
        el("td", { class: "num-cell", text: String(c.review) }),
        el("td", { class: "num-cell", text: String(c.rework) }),
        el("td", { class: "num-cell", text: String(c.not + c.work + c.none) }),
        el("td", { class: "num-cell" }, [r.atRisk ? el("span", { class: "risk risk-high", text: String(r.atRisk) }) : "0"]),
        el("td", {}, [el("span", { class: "risk " + Insights.LEVELS[Insights.levelOf(r.avg)].cls, text: String(r.avg) })]),
        el("td", {}, [Summary.bar(c.done, c.total)]),
      ]));
    });
  }, "ANAL");

  // Вивантаження таблиці заходів у CSV (формується в браузері, без сервера).
  document.getElementById("export-csv").addEventListener("click", function () {
    if (!last) return;
    const q = function (v) { return '"' + String(v == null ? "" : v).replace(/"/g, '""') + '"'; };
    const lines = [["№", "Захід", "Підрозділ", "Строк", "Статус", "№ наказу", "Дата", "Ризик невиконання", "Причини", "Сигнали"].map(q).join(";")];
    last.insight.items.slice().sort(function (a, b) { return Api.byMeasureOrder(a.m, b.m); }).forEach(function (it) {
      const m = it.m, ex = it.ex;
      lines.push([Api.measureNo(m), m.description, Api.deptName(m.responsible_department_id),
        m.deadline_on ? Api.fmtDate(m.deadline_on) : (m.deadline_description || ""),
        Api.STATUS[it.status].label, Api.orderNumber(ex), ex && ex.completed_on ? Api.fmtDate(ex.completed_on) : "",
        it.score, it.reasons.join("; "),
        it.flags.map(function (f) { return f.code; }).join(" ")].map(q).join(";"));
    });
    const blob = new Blob(["﻿" + lines.join("\r\n")], { type: "text/csv;charset=utf-8" });
    const a = el("a", { href: URL.createObjectURL(blob), download: "vykonannia-" + last.period + ".csv" });
    document.body.appendChild(a);
    a.click();
    a.remove();
  });
})();
