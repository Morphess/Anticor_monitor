// Кабінет виконавця: заходи підрозділу, подання номера наказу через /api/executions.
(function () {
  "use strict";
  if (!Api.requireLogin()) return;
  const el = Api.el;
  const deptSel = document.getElementById("dept");
  const periodSel = document.getElementById("period");
  const tbody = document.getElementById("rows");
  const unitName = document.getElementById("unit-name");

  let measures = [];
  let programs = {};
  let executions = {}; // measure_id -> execution за обраний період

  async function init() {
    try {
      const [progList, ms] = await Promise.all([Api.get("/api/programs"), Api.measures()]);
      progList.forEach(function (p) { programs[p.id] = p; });
      measures = ms.sort(Api.byMeasureOrder);
      Api.fillPeriods(periodSel, progList);
      fillDepartments();
      deptSel.addEventListener("change", function () { Api.pref("dept", deptSel.value); render(); });
      periodSel.addEventListener("change", load);
      await load();
    } catch (err) {
      Api.showError(err);
      tbody.innerHTML = "";
    }
  }

  // ЗАГЛУШКА: підрозділ користувача сервер поки не повертає — обирається вручну.
  function fillDepartments() {
    const ids = Array.from(new Set(measures.map(function (m) { return m.responsible_department_id || ""; }))).sort();
    deptSel.innerHTML = "";
    ids.forEach(function (id) {
      deptSel.appendChild(el("option", { value: id, text: Api.deptName(id) }));
    });
    const saved = Api.pref("dept");
    if (saved !== null && ids.indexOf(saved) !== -1) deptSel.value = saved;
  }

  async function load() {
    Api.showError(null);
    tbody.innerHTML = '<tr><td colspan="8" class="muted">Завантаження…</td></tr>';
    try {
      const list = await Api.executions(periodSel.value);
      executions = {};
      list.forEach(function (x) { executions[x.measure_id] = x; });
      render();
    } catch (err) {
      Api.showError(err);
    }
  }

  function endDate(m) {
    if (m.deadline_on) return Api.fmtDate(m.deadline_on);
    if (m.deadline_type === "ongoing") return "постійно";
    return m.deadline_description || "—";
  }

  function render() {
    unitName.textContent = Api.deptName(deptSel.value);
    const mine = measures.filter(function (m) { return (m.responsible_department_id || "") === deptSel.value; });
    tbody.innerHTML = "";
    if (!mine.length) {
      tbody.appendChild(el("tr", {}, [el("td", { colspan: "8", class: "muted", text: "Для підрозділу немає заходів." })]));
      return;
    }
    mine.forEach(function (m) { tbody.appendChild(row(m)); });
  }

  function row(m) {
    const ex = executions[m.id];
    const prog = programs[m.program_id];
    const key = Api.statusOf(ex);
    const msgId = "msg-" + m.id;
    const input = el("input", {
      class: "order-input", value: Api.orderNumber(ex), placeholder: "№ і Enter",
      "aria-label": "Номер наказу для заходу " + Api.measureNo(m), "aria-describedby": msgId,
    });
    const msg = el("div", { id: msgId, class: "msg", role: "status" });
    const statusCell = el("td", {}, [Api.statusBadge(key)]);
    if (ex && ex.approved_by_coordinator) {
      input.readOnly = true;
      input.title = "Погоджено координатором";
    }
    input.addEventListener("input", function () { input.className = "order-input"; msg.textContent = ""; msg.className = "msg"; });
    input.addEventListener("keydown", function (e) {
      if (e.key !== "Enter") return;
      e.preventDefault();
      submit(m, input, msg, statusCell);
    });

    const goal = el("td", {}, [
      el("div", { style: "font-weight:500", text: m.description }),
      m.completion_indicator ? el("div", { class: "small muted", style: "margin-top:4px",
        text: m.completion_indicator + (m.indicator_target != null ? " — " + m.indicator_target + (m.indicator_unit ? " " + m.indicator_unit : "") : "") }) : null,
    ]);
    return el("tr", {}, [
      el("td", { class: "muted", title: "З'явиться з реєстром наказів", text: "—" }),
      el("td", { class: "muted", text: "—" }),
      el("td", { class: "nowrap", text: prog ? Api.fmtDate(prog.start_date) : "—" }),
      el("td", { class: "nowrap", text: endDate(m) }),
      el("td", {}, [input, msg]),
      statusCell,
      goal,
      el("td", { class: "muted", text: Api.noteOf(ex) || "—" }),
    ]);
  }

  function setMsg(input, msg, ok, text) {
    input.className = "order-input " + (ok ? "ok" : "err");
    msg.className = "msg " + (ok ? "ok" : "err");
    msg.textContent = text;
  }

  async function submit(m, input, msg, statusCell) {
    const number = input.value.replace(/^№\s*/, "").trim();
    const period = periodSel.value;
    const ex = executions[m.id];
    if (!number) return setMsg(input, msg, false, "Введіть номер наказу");
    if (/\s/.test(number) || number.length > 40) return setMsg(input, msg, false, "Помилка: номер наказу без пробілів, до 40 символів");
    if (ex && ex.approved_by_coordinator) return setMsg(input, msg, false, "Уже погоджено координатором — зміни недоступні");
    // ЗАГЛУШКА перевірки по реєстру наказів: лише повтор серед звітів періоду.
    const taken = Object.keys(executions).some(function (id) {
      return id !== m.id && Api.orderNumber(executions[id]) === number;
    });
    if (taken) return setMsg(input, msg, false, "Помилка: наказ № " + number + " уже використано для іншого заходу");

    input.disabled = true;
    try {
      const fields = {
        status: "completed",
        status_label: "На розгляді",
        completed_on: Api.today(),
        result_description: Api.withOrder(ex ? ex.result_description : "", number),
      };
      let saved;
      if (ex) {
        saved = await Api.patch(Api.executionUrl(m.id, period), fields);
      } else {
        saved = await Api.post("/api/executions/", Object.assign({ measure_id: m.id, period: period }, fields));
      }
      executions[m.id] = saved;
      statusCell.innerHTML = "";
      statusCell.appendChild(Api.statusBadge(Api.statusOf(saved)));
      setMsg(input, msg, true, "Успіх");
    } catch (err) {
      setMsg(input, msg, false, "Помилка: " + err.message);
    } finally {
      input.disabled = false;
    }
  }

  init();
})();
