// Кабінет керівника: зведення, заходи, що потребують уваги, сигнали, прогрес за розділами.
(function () {
  "use strict";
  const el = Api.el;
  Summary.start(function (d) {
    Summary.cards(Summary.countBy(d.measures, d.executions));
    Summary.bySection(d);
    Summary.flagsByCode(d);
    const tbody = document.getElementById("attention");
    tbody.innerHTML = "";
    const today = Api.today();
    const list = d.measures.filter(function (m) {
      const late = m.deadline_on && m.deadline_on < today && Api.statusOf(d.executions[m.id]) !== "done";
      return late || (d.flagsByMeasure[m.id] || []).length;
    });
    if (!list.length) return Summary.emptyRow(tbody, 6, "Заходів, що потребують уваги, немає.");
    list.forEach(function (m) {
      tbody.appendChild(el("tr", {}, [
        el("td", { class: "nowrap", text: Api.measureNo(m) }),
        el("td", { text: m.description }),
        el("td", { text: Api.deptName(m.responsible_department_id) }),
        el("td", { class: "nowrap", text: m.deadline_on ? Api.fmtDate(m.deadline_on) : (m.deadline_description || "—") }),
        el("td", {}, [Api.statusBadge(Api.statusOf(d.executions[m.id]))]),
        el("td", {}, [el("span", { class: "flags" }, (d.flagsByMeasure[m.id] || []).map(Api.flagBadge))]),
      ]));
    });
  });
})();
