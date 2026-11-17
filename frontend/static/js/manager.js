// Кабінет керівника: зведення, прострочені заходи, прогрес за розділами.
(function () {
  "use strict";
  const el = Api.el;
  Summary.start(function (d) {
    Summary.cards(Summary.countBy(d.measures, d.executions));
    Summary.bySection(d);
    const tbody = document.getElementById("attention");
    tbody.innerHTML = "";
    const today = Api.today();
    const late = d.measures.filter(function (m) {
      return m.deadline_on && m.deadline_on < today && Api.statusOf(d.executions[m.id]) !== "done";
    });
    if (!late.length) return Summary.emptyRow(tbody, 5, "Прострочених заходів немає.");
    late.forEach(function (m) {
      tbody.appendChild(el("tr", {}, [
        el("td", { class: "nowrap", text: Api.measureNo(m) }),
        el("td", { text: m.description }),
        el("td", { text: Api.deptName(m.responsible_department_id) }),
        el("td", { class: "nowrap", text: Api.fmtDate(m.deadline_on) }),
        el("td", {}, [Api.statusBadge(Api.statusOf(d.executions[m.id]))]),
      ]));
    });
  });
})();
