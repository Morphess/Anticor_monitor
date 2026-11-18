// Кабінет виконавця: заходи, закріплені за користувачем; номер наказу перевіряється
// за реєстром /api/orders, після успіху звіт іде координатору через /api/executions.
(function () {
  "use strict";
  const el = Api.el;
  const periodSel = document.getElementById("period");
  const tbody = document.getElementById("rows");
  const unitName = document.getElementById("unit-name");

  let measures = [];       // лише заходи, закріплені за цим користувачем
  let programs = {};
  let executions = {};     // measure_id -> звіт за обраний період
  let ordersByMeasure = {};
  let ordersOk = true;
  let evidenceCount = {};

  async function init() {
    if (!await Api.requireRole("VYK")) return;
    try {
      const [progList, ms, orders, evid] = await Promise.all([
        Api.get("/api/programs"), Api.measures(), Api.optional(Api.orders()), Api.optional(Api.evidences()),
      ]);
      progList.forEach(function (p) { programs[p.id] = p; });
      ordersOk = orders.ok;
      ordersByMeasure = Api.groupBy(orders.data, "measure_id");
      evid.data.forEach(function (e) { evidenceCount[e.measure_id] = (evidenceCount[e.measure_id] || 0) + 1; });

      // Виконавець бачить тільки свої заходи (assigned_user_id), чужі не показуються.
      const me = Api.userId();
      measures = ms.filter(function (m) { return me !== null && m.assigned_user_id === me; }).sort(Api.byMeasureOrder);
      Api.fillPeriods(periodSel, progList);
      periodSel.addEventListener("change", load);
      await load();
    } catch (err) {
      Api.showError(err);
      tbody.innerHTML = "";
    }
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

  // Назва підрозділу: найчастіший відповідальний серед заходів користувача.
  function unitTitle(list) {
    if (!list.length) return "Заходів немає";
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

  // Нагадування про строк: прострочено або менше 30 днів (для непогоджених).
  function deadlineChip(m, ex) {
    if (!m.deadline_on || (ex && ex.approved_by_coordinator)) return null;
    const d = Math.round((new Date(m.deadline_on + "T00:00:00") - new Date(Api.today() + "T00:00:00")) / 86400000);
    if (d < 0) return el("span", { class: "chip late", text: "прострочено " + -d + " дн." });
    if (d <= 30) return el("span", { class: "chip soon", text: "ще " + d + " дн." });
    return null;
  }

  function render() {
    const list = measures;
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
      el("td", { class: "nowrap" }, [el("div", { text: endDate(m) }), deadlineChip(m, ex)]),
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
