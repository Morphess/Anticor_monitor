// Кабінет керівника: показники, прогноз, управлінські рекомендації, заходи під ризиком.
(function () {
  "use strict";
  const el = Api.el;
  Summary.start(function (d) {
    Summary.cards(Summary.countBy(d.measures, d.executions));
    Summary.insight(d);
    Summary.bySection(d);
    Summary.flagsByCode(d);

    const tbody = document.getElementById("attention");
    tbody.innerHTML = "";
    const list = d.insight.items.filter(function (it) { return it.status !== "done" && it.level !== "low"; });
    if (!list.length) return Summary.emptyRow(tbody, 7, "Заходів, що потребують уваги, немає.");
    list.forEach(function (it) {
      const m = it.m;
      tbody.appendChild(el("tr", {}, [
        el("td", { class: "nowrap num-cell", text: Api.measureNo(m) }),
        el("td", { text: m.description }),
        el("td", { text: Api.deptName(m.responsible_department_id) }),
        el("td", { class: "nowrap" }, [
          el("div", { text: m.deadline_on ? Api.fmtDate(m.deadline_on) : (m.deadline_description || "—") }),
          Insights.deadlineChip(it),
        ]),
        el("td", {}, [Api.statusBadge(it.status)]),
        el("td", {}, [Insights.riskChip(it)]),
        el("td", { class: "small muted", text: it.reasons.join("; ") }),
      ]));
    });
  }, "KER");
})();
