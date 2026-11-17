// Кабінет аналітика: розріз за підрозділами й розділами, вивантаження CSV.
(function () {
  "use strict";
  const el = Api.el;
  let last = null;

  Summary.start(function (d) {
    last = d;
    Summary.cards(Summary.countBy(d.measures, d.executions));
    Summary.bySection(d);
    const tbody = document.getElementById("by-dept");
    tbody.innerHTML = "";
    const groups = {};
    d.measures.forEach(function (m) {
      const k = m.responsible_department_id || "";
      (groups[k] = groups[k] || []).push(m);
    });
    const keys = Object.keys(groups).sort();
    if (!keys.length) return Summary.emptyRow(tbody, 7, "Заходів немає.");
    keys.forEach(function (k) {
      const c = Summary.countBy(groups[k], d.executions);
      tbody.appendChild(el("tr", {}, [
        el("td", { text: Api.deptName(k) }),
        el("td", { text: String(c.total) }),
        el("td", { text: String(c.done) }),
        el("td", { text: String(c.review) }),
        el("td", { text: String(c.rework) }),
        el("td", { text: String(c.not + c.work + c.none) }),
        el("td", {}, [Summary.bar(c.done, c.total)]),
      ]));
    });
  });

  // Вивантаження таблиці заходів у CSV (формується в браузері, без сервера).
  document.getElementById("export-csv").addEventListener("click", function () {
    if (!last) return;
    const q = function (v) { return '"' + String(v == null ? "" : v).replace(/"/g, '""') + '"'; };
    const lines = [["№", "Захід", "Підрозділ", "Строк", "Статус", "№ наказу", "Дата"].map(q).join(";")];
    last.measures.forEach(function (m) {
      const ex = last.executions[m.id];
      lines.push([Api.measureNo(m), m.description, Api.deptName(m.responsible_department_id),
        m.deadline_on ? Api.fmtDate(m.deadline_on) : (m.deadline_description || ""),
        Api.STATUS[Api.statusOf(ex)].label, Api.orderNumber(ex), ex && ex.completed_on ? Api.fmtDate(ex.completed_on) : ""].map(q).join(";"));
    });
    const blob = new Blob(["﻿" + lines.join("\r\n")], { type: "text/csv;charset=utf-8" });
    const a = el("a", { href: URL.createObjectURL(blob), download: "vykonannia-" + last.period + ".csv" });
    document.body.appendChild(a);
    a.click();
    a.remove();
  });
})();
