// Кабінет виконавця: заходи, закріплені за користувачем; номер наказу перевіряється
// за реєстром /api/orders, після успіху звіт іде координатору через /api/executions.
(function () {
  "use strict";
  if (!Api.requireLogin()) return;
  const el = Api.el;
  const deptSel = document.getElementById("dept");
  const periodSel = document.getElementById("period");
  const tbody = document.getElementById("rows");
  const unitName = document.getElementById("unit-name");

  let measures = [];       // заходи, які бачить цей виконавець
  let programs = {};
  let executions = {};     // measure_id -> звіт за обраний період
  let ordersByMeasure = {};
  let ordersOk = true;
  let evidenceCount = {};
  let byAssignment = false;

  async function init() {
    try {
      const [progList, ms, orders, evid] = await Promise.all([
        Api.get("/api/programs"), Api.measures(), Api.optional(Api.orders()), Api.optional(Api.evidences()),
      ]);
      progList.forEach(function (p) { programs[p.id] = p; });
      ordersOk = orders.ok;
      ordersByMeasure = Api.groupBy(orders.data, "measure_id");
      evid.data.forEach(function (e) { evidenceCount[e.measure_id] = (evidenceCount[e.measure_id] || 0) + 1; });

      const me = Api.userId();
      const mine = ms.filter(function (m) { return me !== null && m.assigned_user_id === me; });
      byAssignment = mine.length > 0;
      measures = (byAssignment ? mine : ms).sort(Api.byMeasureOrder);
      Api.fillPeriods(periodSel, progList);
      if (!byAssignment) setupDepartmentStub();
      periodSel.addEventListener("change", load);
      await load();
    } catch (err) {
      Api.showError(err);
      tbody.innerHTML = "";
    }
  }

  // ЗАГЛУШКА: заходів за користувачем немає — даємо обрати підрозділ вручну.
  function setupDepartmentStub() {
    document.getElementById("dept-field").classList.remove("hidden");
    document.getElementById("dept-stub").classList.remove("hidden");
    const ids = Array.from(new Set(measures.map(function (m) { return m.responsible_department_id || ""; }))).sort();
    ids.forEach(function (id) { deptSel.appendChild(el("option", { value: id, text: Api.deptName(id) })); });
    const saved = Api.pref("dept");
    if (saved !== null && ids.indexOf(saved) !== -1) deptSel.value = saved;
    deptSel.addEventListener("change", function () { Api.pref("dept", deptSel.value); render(); });
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

  function visible() {
    if (byAssignment) return measures;
    return measures.filter(function (m) { return (m.responsible_department_id || "") === deptSel.value; });
  }

  // Назва підрозділу: найчастіший відповідальний серед заходів користувача.
  function unitTitle(list) {
    if (!byAssignment) return Api.deptName(deptSel.value);
    const count = {};
    list.forEach(function (m) { const k = m.responsible_department_id || ""; count[k] = (count[k] || 0) + 1; });
    const top = Object.keys(count).sort(function (a, b) { return count[b] - count[a]; })[0];
    return Api.deptName(top);
  }

  function endDate(m) {
    if (m.deadline_on) return Api.fmtDate(m.deadline_on);
    if (m.deadline_type === "ongoing") return "постійно";
    return m.deadline_description || "—";
  }

  function render() {
    const list = visible();
    unitName.textContent = unitTitle(list);
    tbody.innerHTML = "";
    if (!list.length) {
      tbody.appendChild(el("tr", {}, [el("td", { colspan: "8", class: "muted", text: "За вами не закріплено заходів." })]));
      return;
    }
    list.forEach(function (m) { tbody.appendChild(row(m)); });
  }

  // Наказ, який показуємо в рядку: поданий виконавцем, інакше перший у реєстрі.
  function shownOrder(m) {
    const orders = ordersByMeasure[m.id] || [];
    return Api.findOrder(orders, Api.orderNumber(executions[m.id])) || orders[0] || null;
  }

  function orderNameCell(m) {
    const o = shownOrder(m);
    if (o) return el("td", { class: "order-name" }, [Api.docLink(o.document_url, o.title)]);
    return el("td", { class: "muted", text: ordersOk ? "Наказу ще немає в реєстрі" : "Реєстр наказів недоступний" });
  }

  function organCell(m) {
    // ЗАГЛУШКА: у моделі наказу немає поля «орган, що видав» — беремо організацію з паспорта програми.
    const p = programs[m.program_id];
    return el("td", { class: shownOrder(m) ? "" : "muted", title: "З паспорта програми (поле органу в наказі ще не додано)", text: p ? p.organization_name : "—" });
  }

  function row(m) {
    const ex = executions[m.id];
    const prog = programs[m.program_id];
    const msgId = "msg-" + m.id;
    const input = el("input", {
      class: "order-input", value: Api.orderNumber(ex), placeholder: "№ і Enter",
      "aria-label": "Номер наказу для заходу " + Api.measureNo(m), "aria-describedby": msgId,
    });
    const msg = el("div", { id: msgId, class: "msg", role: "status" });
    const statusCell = el("td", {}, [Api.statusBadge(Api.statusOf(ex))]);
    const nameCell = orderNameCell(m);
    if (ex && ex.approved_by_coordinator) {
      input.readOnly = true;
      input.title = "Погоджено координатором";
    }
    input.addEventListener("input", function () { input.className = "order-input"; msg.textContent = ""; msg.className = "msg"; });
    input.addEventListener("keydown", function (e) {
      if (e.key !== "Enter") return;
      e.preventDefault();
      submit(m, input, msg, statusCell, nameCell);
    });

    const target = m.completion_indicator
      ? m.completion_indicator + (m.indicator_target != null ? " — " + Number(m.indicator_target) + (m.indicator_unit ? " " + m.indicator_unit : "") : "")
      : "";
    const note = Api.noteOf(ex);
    const ev = evidenceCount[m.id] || 0;
    return el("tr", {}, [
      nameCell,
      organCell(m),
      el("td", { class: "nowrap", text: prog ? Api.fmtDate(prog.start_date) : "—" }),
      el("td", { class: "nowrap", text: endDate(m) }),
      el("td", {}, [input, msg]),
      statusCell,
      el("td", {}, [
        el("div", { style: "font-weight:500", text: m.description }),
        target ? el("div", { class: "small muted", style: "margin-top:4px", text: target }) : null,
      ]),
      el("td", {}, [
        el("div", { class: "muted", text: note || "—" }),
        el("div", { class: "small", style: "margin-top:6px", text: "Підтверджень: " + ev }),
      ]),
    ]);
  }

  function setMsg(input, msg, ok, text) {
    input.className = "order-input " + (ok ? "ok" : "err");
    msg.className = "msg " + (ok ? "ok" : "err");
    msg.textContent = text;
  }

  // Перевірка: наказ є в реєстрі саме для цього заходу і не поданий для іншого.
  function check(m, number) {
    if (!number) return "Введіть номер наказу";
    if (!ordersOk) return "Помилка: реєстр наказів недоступний, спробуйте пізніше";
    const own = Api.findOrder(ordersByMeasure[m.id], number);
    if (!own) {
      const elsewhere = Object.keys(ordersByMeasure).some(function (id) {
        return id !== m.id && Api.findOrder(ordersByMeasure[id], number);
      });
      return elsewhere
        ? "Помилка: наказ № " + number + " стосується іншого заходу"
        : "Помилка: наказу № " + number + " немає в реєстрі для цього заходу";
    }
    const taken = Object.keys(executions).some(function (id) {
      return id !== m.id && Api.normNumber(Api.orderNumber(executions[id])) === Api.normNumber(number);
    });
    if (taken) return "Помилка: наказ № " + number + " уже використано для іншого заходу";
    return null;
  }

  async function submit(m, input, msg, statusCell, nameCell) {
    const number = input.value.replace(/^№\s*/, "").trim();
    const period = periodSel.value;
    const ex = executions[m.id];
    if (ex && ex.approved_by_coordinator) return setMsg(input, msg, false, "Уже погоджено координатором — зміни недоступні");
    const problem = check(m, number);
    if (problem) return setMsg(input, msg, false, problem);

    const order = Api.findOrder(ordersByMeasure[m.id], number);
    input.disabled = true;
    try {
      const fields = {
        status: "completed",
        status_label: "На розгляді",
        completed_on: Api.today(),
        result_description: Api.withOrder(ex ? ex.result_description : "", order.number),
      };
      const saved = ex
        ? await Api.patch(Api.executionUrl(m.id, period), fields)
        : await Api.post("/api/executions/", Object.assign({ measure_id: m.id, period: period }, fields));
      executions[m.id] = saved;
      statusCell.innerHTML = "";
      statusCell.appendChild(Api.statusBadge(Api.statusOf(saved)));
      const fresh = orderNameCell(m);
      nameCell.className = fresh.className;
      nameCell.replaceChildren.apply(nameCell, Array.from(fresh.childNodes));
      input.value = order.number;
      setMsg(input, msg, true, "Успіх");
    } catch (err) {
      setMsg(input, msg, false, "Помилка: " + err.message);
    } finally {
      input.disabled = false;
    }
  }

  init();
})();
