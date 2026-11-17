// Кабінет аналітика, вкладка «Аналітика»: зведення й графіки за даними /api/analyst/overview.
// Графіки — charts.js, вкладки — tabs.js, «Програми й заходи» — coordinator.js, «Запити й звіти» — reports.js.
(function () {
  var DATA = null;

  function render() {
    Charts.render(document.getElementById("analytics-view"),
      Charts.summarize(DATA, document.getElementById("program").value));
  }

  // Підказку «Як читати» відкриваємо при першому візиті
  var guide = document.getElementById("guide");
  try {
    if (!localStorage.getItem("analyst_guide_seen")) guide.open = true;
    guide.addEventListener("toggle", function () { if (!guide.open) localStorage.setItem("analyst_guide_seen", "1"); });
  } catch (e) { guide.open = true; }

  document.getElementById("program").addEventListener("change", render);

  Api.get("/api/analyst/overview")
    .then(function (data) {
      DATA = data;
      document.getElementById("unit").textContent = data.unit;
      document.getElementById("period").textContent =
        "Звітний період: " + Charts.periodText(data.period) + " · дані на " + data.today;
      var sel = document.getElementById("program");
      data.programs.forEach(function (p) {
        var o = Charts.el("option", "", p.name + " (" + p.start + " – " + p.end + ")");
        o.value = p.id;
        sel.appendChild(o);
      });
      render();
    })
    .catch(function (ex) { document.getElementById("page-error").textContent = ex.message; });
})();
