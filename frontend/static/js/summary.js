// Спільне зведення для керівника й аналітика: рахує статуси на клієнті з /api/measures і /api/executions.
(function () {
  "use strict";
  const el = Api.el;

  window.Summary = {
    // Завантажує дані й викликає onData({programs, measures, executions, sections, period}).
    start: async function (onData) {
      if (!Api.requireLogin()) return;
      const periodSel = document.getElementById("period");
      try {
        const [programs, measures, sections] = await Promise.all([
          Api.get("/api/programs"), Api.measures(), Api.sections(),
        ]);
        measures.sort(Api.byMeasureOrder);
        document.getElementById("program-title").textContent =
          programs.length === 1 ? programs[0].title : "Програм: " + programs.length;
        Api.fillPeriods(periodSel, programs);
        const load = async function () {
          Api.showError(null);
          try {
            const list = await Api.executions(periodSel.value);
            const executions = {};
            list.forEach(function (x) { executions[x.measure_id] = x; });
            onData({ programs: programs, measures: measures, executions: executions, sections: sections, period: periodSel.value });
          } catch (err) { Api.showError(err); }
        };
        periodSel.addEventListener("change", load);
        await load();
      } catch (err) {
        Api.showError(err);
      }
    },

    countBy: function (measures, executions) {
      const c = { total: measures.length, done: 0, review: 0, rework: 0, not: 0, work: 0, none: 0 };
      measures.forEach(function (m) { c[Api.statusOf(executions[m.id])]++; });
      return c;
    },

    cards: function (c) {
      const box = document.getElementById("cards");
      box.innerHTML = "";
      [["Заходів", c.total], ["Виконано", c.done], ["На розгляді", c.review],
       ["На доопрацюванні", c.rework], ["Не виконано", c.not + c.work + c.none]].forEach(function (x) {
        box.appendChild(el("div", { class: "card" }, [el("div", { class: "n", text: String(x[1]) }), el("div", { class: "l", text: x[0] })]));
      });
    },

    bar: function (done, total) {
      const pct = total ? Math.round(done * 100 / total) : 0;
      return el("div", {}, [
        el("div", { class: "small", text: pct + " %" }),
        el("div", { class: "bar", "aria-hidden": "true" }, [el("span", { style: "width:" + pct + "%" })]),
      ]);
    },

    bySection: function (d) {
      const tbody = document.getElementById("by-section");
      tbody.innerHTML = "";
      const groups = {};
      d.measures.forEach(function (m) { (groups[m.section_id] = groups[m.section_id] || []).push(m); });
      Object.keys(groups).sort(Api.compareSections).forEach(function (sid) {
        const c = Summary.countBy(groups[sid], d.executions);
        tbody.appendChild(el("tr", {}, [
          el("td", { text: Api.sectionTitle(d.sections, sid) }),
          el("td", { class: "nowrap", text: c.done + " / " + c.total }),
          el("td", {}, [Summary.bar(c.done, c.total)]),
        ]));
      });
    },

    emptyRow: function (tbody, cols, text) {
      tbody.appendChild(el("tr", {}, [el("td", { colspan: String(cols), class: "muted", text: text })]));
    },
  };
})();
