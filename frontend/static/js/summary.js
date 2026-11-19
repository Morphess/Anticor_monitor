// Спільне зведення для керівника й аналітика: рахує статуси на клієнті з /api/measures і /api/executions,
// а оцінку ризику, прогноз і рекомендації — модулем Insights.
(function () {
  "use strict";
  const el = Api.el;

  window.Summary = {
    // Завантажує дані й викликає onData({programs, measures, executions, sections, period, flags, insight}).
    start: async function (onData, expectedRole) {
      if (!await Api.requireRole(expectedRole)) return;
      const periodSel = document.getElementById("period");
      try {
        const [programs, measures, sections, evid, changes] = await Promise.all([
          Api.get("/api/programs"), Api.measures(), Api.sections(),
          Api.optional(Api.evidences()), Api.optional(Api.deadlineChanges()),
        ]);
        measures.sort(Api.byMeasureOrder);
        document.getElementById("program-title").textContent =
          programs.length === 1 ? programs[0].title : "Усі програми (" + programs.length + ")";
        Api.fillPeriods(periodSel, programs);
        const evidenceByMeasure = Api.groupBy(evid.data, "measure_id");
        const changesByMeasure = Api.groupBy(changes.data, "measure_id");
        const load = async function () {
          Api.showError(null);
          try {
            const [list, flags] = await Promise.all([Api.executions(periodSel.value), Api.riskFlags(periodSel.value)]);
            const executions = {};
            list.forEach(function (x) { executions[x.measure_id] = x; });
            const flagsByMeasure = Api.groupBy(flags.data.filter(function (f) { return f.object_type === "zakhid"; }), "object_id");
            const insight = Insights.assess({
              measures: measures, executions: executions, period: periodSel.value, role: expectedRole,
              evidenceByMeasure: evidenceByMeasure, changesByMeasure: changesByMeasure, flagsByMeasure: flagsByMeasure,
            });
            onData({
              programs: programs, measures: measures, executions: executions, sections: sections, period: periodSel.value,
              flags: flags, flagsByMeasure: flagsByMeasure, insight: insight,
            });
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

    // Ключові показники + стрічка розподілу статусів.
    cards: function (c) {
      const box = document.getElementById("cards");
      box.innerHTML = "";
      const pct = function (n) { return c.total ? Math.round(n * 100 / c.total) + " %" : "—"; };
      const notDone = c.not + c.work + c.none;
      [["Заходів у програмі", c.total, null, null],
       ["Виконано", c.done, pct(c.done), "ok"],
       ["На розгляді", c.review, pct(c.review), "review"],
       ["На доопрацюванні", c.rework, pct(c.rework), "warn"],
       ["Не виконано", notDone, pct(notDone), "bad"]].forEach(function (x) {
        box.appendChild(el("div", { class: "card", "data-tone": x[3] }, [
          el("div", { class: "n", text: String(x[1]) }),
          el("div", { class: "l", text: x[0] }),
          x[2] ? el("div", { class: "sub", text: x[2] }) : null,
        ]));
      });
      const stack = document.getElementById("stack");
      if (!stack) return;
      stack.innerHTML = "";
      const parts = [["s-done", c.done, "Виконано", "var(--ok)"], ["s-review", c.review, "На розгляді", "var(--review)"],
        ["s-rework", c.rework, "На доопрацюванні", "var(--warn)"], ["s-not", c.not, "Не виконано", "var(--bad)"],
        ["s-idle", c.work + c.none, "Не розпочато / у роботі", "var(--idle)"]];
      stack.appendChild(el("div", { class: "stack", role: "img", "aria-label": "Розподіл заходів за статусами" },
        parts.filter(function (p) { return p[1]; }).map(function (p) {
          return el("span", { class: p[0], style: "flex:" + p[1], title: p[2] + ": " + p[1] });
        })));
      stack.appendChild(el("ul", { class: "legend" }, parts.map(function (p) {
        return el("li", {}, [el("i", { style: "background:" + p[3] }), p[2] + " · " + p[1]]);
      })));
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
          el("td", { class: "nowrap num-cell", text: c.done + " / " + c.total }),
          el("td", {}, [Summary.bar(c.done, c.total)]),
        ]));
      });
      if (!Object.keys(groups).length) Summary.emptyRow(tbody, 3, "Заходів немає.");
    },

    insight: function (d, recLimit) {
      Insights.renderForecast(document.getElementById("forecast"), d.insight.forecast);
      Insights.renderRecs(document.getElementById("recs"), d.insight.recs, recLimit);
    },

    // Таблиця сигналів за кодами правил; без доступу — пояснення-заглушка.
    flagsByCode: function (d) {
      const box = document.getElementById("flags-summary");
      if (!box) return;
      box.innerHTML = "";
      // Ролі без доступу до /api/risk-flags блок не бачать зовсім.
      const block = document.getElementById("flags-block");
      if (block) block.classList.toggle("hidden", !d.flags.ok);
      if (!d.flags.ok) return;
      const groups = Api.groupBy(d.flags.data, "code");
      const codes = Object.keys(groups).sort(function (a, b) { return a.localeCompare(b, "uk", { numeric: true }); });
      if (!codes.length) {
        box.appendChild(el("p", { class: "muted", text: "Сигналів за період немає." }));
        return;
      }
      box.appendChild(el("div", { class: "table-wrap" }, [el("table", { class: "grid" }, [
        el("thead", {}, [el("tr", {}, [el("th", { text: "Код" }), el("th", { text: "Правило" }), el("th", { text: "Кількість" }), el("th", { text: "Об'єкти" })])]),
        el("tbody", {}, codes.map(function (c) {
          return el("tr", {}, [
            el("td", {}, [Api.flagBadge(groups[c][0])]),
            el("td", { text: Api.FLAGS[c] || groups[c][0].message }),
            el("td", { class: "num-cell", text: String(groups[c].length) }),
            el("td", { class: "small", text: groups[c].map(function (f) { return f.object_id; }).join(", ") }),
          ]);
        })),
      ])]));
    },

    emptyRow: function (tbody, cols, text) {
      tbody.appendChild(el("tr", {}, [el("td", { colspan: String(cols), class: "muted", text: text })]));
    },
  };
})();
