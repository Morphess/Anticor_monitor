// Кабінет координатора: програма → розділ → захід → підрозділ, накази, підтвердження,
// перенесення строків, сигнали Risk Flags і зміна статусу виконання.
(function () {
  "use strict";
  const el = Api.el;
  const root = document.getElementById("programs");
  const flagsNote = document.getElementById("flags-note");
  const periodSel = document.getElementById("period");
  const search = document.getElementById("search");
  const STATUSES = ["done", "review", "rework", "not"];

  let programs = [];
  let measuresByProg = {};
  let sections = {};
  let executions = {};
  let ordersByMeasure = {};
  let evidenceByMeasure = {};
  let changesByMeasure = {};
  let flagsByMeasure = {};
  let riskById = {};
  const open = new Set(); // розгорнуті вузли: p:ID, s:ID:R, m:ID

  async function init() {

    if (!await Api.requireRole("KOORD")) return;
    try {
      const [progList, measures, secs, orders, evid, changes] = await Promise.all([
        Api.get("/api/programs"), Api.measures(), Api.sections(),
        Api.optional(Api.orders()), Api.optional(Api.evidences()), Api.optional(Api.deadlineChanges()),
      ]);
      programs = progList;
      sections = secs;
      ordersByMeasure = Api.groupBy(orders.data, "measure_id");
      evidenceByMeasure = Api.groupBy(evid.data, "measure_id");
      changesByMeasure = Api.groupBy(changes.data, "measure_id");
      measuresByProg = Api.groupBy(measures.sort(Api.byMeasureOrder), "program_id");
      const coordDept = programs.map(function (p) { return p.coordinator_department_id; }).filter(Boolean)[0];
      document.getElementById("unit-name").textContent = coordDept ? Api.deptName(coordDept) : "Координатор програми";
      if (programs.length === 1) open.add("p:" + programs[0].id);
      Api.fillPeriods(periodSel, programs);
      periodSel.addEventListener("change", load);
      search.addEventListener("input", render);
      await load();
    } catch (err) {
      Api.showError(err);
      root.innerHTML = "";
    }
  }

  async function load() {
    Api.showError(null);
    try {
      const [list, flags] = await Promise.all([Api.executions(periodSel.value), Api.riskFlags(periodSel.value)]);
      executions = {};
      list.forEach(function (x) { executions[x.measure_id] = x; });
      flagsByMeasure = Api.groupBy(flags.data.filter(function (f) { return f.object_type === "zakhid"; }), "object_id");
      renderFlagsNote(flags);
      assess();
      render();
    } catch (err) {
      Api.showError(err);
    }
  }

  // Оцінка ризику та завдання координатора (лише рекомендації з роллю KOORD).
  function assess() {
    const all = [];
    Object.keys(measuresByProg).forEach(function (k) { all.push.apply(all, measuresByProg[k]); });
    const res = Insights.assess({
      measures: all, executions: executions, period: periodSel.value, role: "KOORD",
      evidenceByMeasure: evidenceByMeasure, changesByMeasure: changesByMeasure, flagsByMeasure: flagsByMeasure,
    });
    riskById = {};
    res.items.forEach(function (it) { riskById[it.m.id] = it; });
    Insights.renderRecs(document.getElementById("recs"), res.recs, 5);
  }

  function renderFlagsNote(flags) {
    flagsNote.innerHTML = "";
    if (!flags.ok) return; // ролі без доступу до сигналів блок не показується
    const n = flags.data.length;
    flagsNote.appendChild(el("p", { class: "small", style: "margin:0 0 14px" }, [
      el("strong", { text: "Сигналів за період: " + n + ". " }),
      n ? "Заходи з сигналами позначені кодами RF — наведіть курсор, щоб побачити причину." : "Порушень правил не виявлено.",
    ]));
  }

  function isDone(m) { return Api.statusOf(executions[m.id]) === "done"; }
  function counter(list) {
    const done = list.filter(isDone).length;
    const pct = list.length ? Math.round(done * 100 / list.length) : 0;
    return el("div", {}, [
      el("div", { class: "count", text: done + " / " + list.length }),
      el("div", { class: "bar", "aria-hidden": "true" }, [el("span", { style: "width:" + pct + "%" })]),
    ]);
  }
  function toggle(key) { open.has(key) ? open.delete(key) : open.add(key); render(); }

  function matches(text, q) { return (text || "").toLowerCase().indexOf(q) !== -1; }
  function measureMatches(m, q) {
    return matches(m.description, q) || matches(Api.measureNo(m), q) || matches(m.id, q) ||
      matches(Api.deptName(m.responsible_department_id), q) || matches(Api.orderNumber(executions[m.id]), q) ||
      (ordersByMeasure[m.id] || []).some(function (o) { return matches(o.number, q) || matches(o.title, q); }) ||
      (flagsByMeasure[m.id] || []).some(function (f) { return matches(f.code, q); });
  }

  function render() {
    const q = search.value.trim().toLowerCase();
    root.innerHTML = "";
    let shown = 0;
    programs.forEach(function (p) {
      const all = measuresByProg[p.id] || [];
      const progHit = !q || matches(p.title, q) || matches(p.id, q);
      const list = progHit ? all : all.filter(function (m) {
        return measureMatches(m, q) || matches(Api.sectionTitle(sections, m.section_id), q);
      });
      if (q && !progHit && !list.length) return;
      shown++;
      root.appendChild(programNode(p, all, list, q && !progHit));
    });
    if (!shown) root.appendChild(el("p", { class: "muted", text: q ? "Нічого не знайдено." : "Програм ще немає. Створіть першу." }));
  }

  function programNode(p, all, list, forceOpen) {
    const key = "p:" + p.id;
    const isOpen = forceOpen || open.has(key);
    const node = el("div", { class: "prog" }, [
      el("button", { type: "button", class: "row-head", "aria-expanded": String(isOpen), onclick: function () { toggle(key); } }, [
        el("span", { class: "title", text: p.title }),
        el("span", { class: "meta", text: Api.fmtDate(p.start_date) + " – " + Api.fmtDate(p.end_date) }),
        counter(all),
      ]),
    ]);
    if (!isOpen) return node;
    const body = el("div", { class: "prog-body" });
    const bySec = Api.groupBy(list, "section_id");
    const secIds = Object.keys(bySec).sort(Api.compareSections);
    if (!secIds.length) body.appendChild(el("p", { class: "muted", style: "padding:8px 18px", text: "У програмі ще немає заходів." }));
    secIds.forEach(function (sid) { body.appendChild(sectionNode(p, sid, bySec[sid], forceOpen)); });
    node.appendChild(body);
    return node;
  }

  function finalDeadline(list) {
    const dates = list.map(function (m) { return m.deadline_on; }).filter(Boolean).sort();
    return dates.length ? "Кінцевий строк: " + Api.fmtDate(dates[dates.length - 1]) : "Строк: постійно";
  }

  function sectionNode(p, sid, list, forceOpen) {
    const key = "s:" + p.id + ":" + sid;
    const isOpen = forceOpen || open.has(key);
    const node = el("div", { class: "sec" }, [
      el("button", { type: "button", class: "row-head", "aria-expanded": String(isOpen), onclick: function () { toggle(key); } }, [
        el("span", { class: "title", text: Api.sectionTitle(sections, sid) }),
        el("span", { class: "meta", text: finalDeadline(list) }),
        counter(list),
      ]),
    ]);
    if (!isOpen) return node;
    const body = el("div", { class: "sec-body" });
    list.forEach(function (m) { body.appendChild(measureNode(m)); });
    node.appendChild(body);
    return node;
  }

  function measureNode(m) {
    const key = "m:" + m.id;
    const isOpen = open.has(key);
    const flags = flagsByMeasure[m.id] || [];
    const node = el("div", { class: "measure" }, [
      el("button", { type: "button", class: "row-head", "aria-expanded": String(isOpen), onclick: function () { toggle(key); } }, [
        el("span", { class: "num", text: Api.measureNo(m) }),
        el("span", { text: m.description }),
        el("span", { class: "flags" }, flags.map(Api.flagBadge)),
        riskById[m.id] ? Insights.riskChip(riskById[m.id]) : el("span"),
        Api.statusBadge(Api.statusOf(executions[m.id])),
      ]),
    ]);
    if (isOpen) node.appendChild(detailNode(m));
    return node;
  }

  function detailNode(m) {
    return el("div", { class: "detail" }, [
      unitsTable(m),
      flagsBlock(m),
      ordersBlock(m),
      evidenceBlock(m),
      changesBlock(m),
    ]);
  }

  // ЗАГЛУШКА: співвиконавців API не віддає — показуємо відповідальний підрозділ.
  function unitsTable(m) {
    const ex = executions[m.id];
    const key = Api.statusOf(ex);
    const select = el("select", { "aria-label": "Статус виконання заходу " + Api.measureNo(m) });
    if (STATUSES.indexOf(key) === -1) select.appendChild(el("option", { value: "", text: Api.STATUS[key].label }));
    STATUSES.forEach(function (k) { select.appendChild(el("option", { value: k, text: Api.STATUS[k].label })); });
    select.value = STATUSES.indexOf(key) !== -1 ? key : "";
    const msg = el("div", { class: "msg", role: "status" });
    select.addEventListener("change", function () { changeStatus(m, select.value, select, msg); });

    const number = Api.orderNumber(ex);
    const order = Api.findOrder(ordersByMeasure[m.id], number);
    let orderCell;
    if (!number) orderCell = el("td", { text: "—" });
    else if (order) orderCell = el("td", {}, [Api.docLink(order.document_url, "№ " + order.number)]);
    else orderCell = el("td", {}, ["№ " + number, el("div", { class: "msg err", text: "немає в реєстрі" })]);

    return el("div", { class: "units table-wrap" }, [
      el("table", { class: "grid" }, [
        el("thead", {}, [el("tr", {}, [
          el("th", { text: "Підрозділ" }), el("th", { text: "Дата" }), el("th", { text: "№ наказу" }),
          el("th", { text: "Примітка" }), el("th", { text: "Статус" }),
        ])]),
        el("tbody", {}, [el("tr", {}, [
          el("td", { text: Api.deptName(m.responsible_department_id) }),
          el("td", { class: "nowrap", text: ex && ex.completed_on ? Api.fmtDate(ex.completed_on) : "—" }),
          orderCell,
          el("td", { class: "muted", text: Api.noteOf(ex) || "—" }),
          el("td", {}, [select, msg]),
        ])]),
      ]),
    ]);
  }

  function flagsBlock(m) {
    const flags = flagsByMeasure[m.id] || [];
    if (!flags.length) return null;
    return el("div", {}, [
      el("h3", { text: "Сигнали для перевірки" }),
      el("ul", { class: "plain" }, flags.map(function (f) {
        return el("li", {}, [Api.flagBadge(f), " " + f.message + (f.explanation ? " (" + f.explanation + ")" : "")]);
      })),
    ]);
  }

  function ordersBlock(m) {
    const orders = ordersByMeasure[m.id] || [];
    function orderItem(order) {
      const fileInput = el("input", {
        type: "file",
        accept: ".pdf,.docx,.txt,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain",
        "aria-label": "Документ наказу для аналізу",
      });
      const message = el("div", { class: "msg", role: "status" });
      const result = el("pre", { class: "analysis-result hidden" });
      const analyzeButton = el("button", {
        class: "btn",
        type: "button",
        text: "Проаналізувати документ",
        onclick: async function () {
          const file = fileInput.files && fileInput.files[0];
          if (!file) {
            message.className = "msg err";
            message.textContent = "Спочатку виберіть файл наказу (PDF, DOCX або TXT).";
            return;
          }
          if (file.size > 15 * 1024 * 1024) {
            message.className = "msg err";
            message.textContent = "Максимальний розмір файла — 15 МБ.";
            return;
          }

          analyzeButton.disabled = true;
          result.classList.add("hidden");
          message.className = "msg";
          message.textContent = "Документ аналізується локальною моделлю на сервері…";
          const formData = new FormData();
          formData.append("file", file);
          try {
            const response = await Api.post(
              "/api/orders/" + encodeURIComponent(order.id) + "/analyze",
              formData,
            );
            result.textContent = response.analysis;
            result.classList.remove("hidden");
            message.className = "msg ok";
            message.textContent = "Аналіз завершено моделлю " + response.model +
              (response.text_truncated ? "; для аналізу використано лише початок документа." : "") +
              " Перевірте висновки за оригіналом.";
          } catch (error) {
            message.className = "msg err";
            message.textContent = "Не вдалося проаналізувати документ: " + error.message;
          } finally {
            analyzeButton.disabled = false;
          }
        },
      });

      return el("li", { class: "order-analysis" }, [
        el("div", {}, [Api.docLink(order.document_url, "№ " + order.number + " — " + order.title), order.issued_on ? " від " + Api.fmtDate(order.issued_on) : ""]),
        el("div", { class: "analysis-controls" }, [
          el("label", { class: "field" }, ["Файл наказу для аналізу", fileInput]),
          analyzeButton,
        ]),
        message,
        result,
      ]);
    }
    const list = orders.length
      ? el("ul", { class: "plain order-list" }, orders.map(orderItem))
      : el("p", { class: "small muted", style: "margin:0 0 8px", text: "Наказів у реєстрі немає — виконавець не зможе подати звіт." });

    const form = el("form", { class: "inline-form", style: "margin-top:8px" }, [
      el("label", { class: "field" }, ["№ наказу", el("input", { name: "number", required: "required", maxlength: "150" })]),
      el("label", { class: "field", style: "flex:1" }, ["Назва", el("input", { name: "title", required: "required" })]),
      el("label", { class: "field" }, ["Дата", el("input", { name: "issued_on", type: "date" })]),
      el("label", { class: "field" }, ["Посилання на документ", el("input", { name: "document_url", type: "url", placeholder: "https://" })]),
      el("button", { class: "btn", type: "submit", text: "Додати наказ" }),
    ]);
    const msg = el("div", { class: "msg", role: "status" });
    form.addEventListener("submit", async function (e) {
      e.preventDefault();
      if (!form.reportValidity()) return;
      const data = Object.fromEntries(new FormData(form).entries());
      const body = {
        id: ("O-" + m.id + "-" + Date.now().toString(36)).slice(0, 50),
        number: data.number.trim(),
        title: data.title.trim(),
        issued_on: data.issued_on || null,
        document_url: data.document_url.trim() || null,
        measure_id: m.id,
      };
      if (Api.findOrder(orders, body.number)) {
        msg.className = "msg err";
        msg.textContent = "Наказ № " + body.number + " уже є для цього заходу";
        return;
      }
      try {
        const created = await Api.post("/api/orders/", body);
        (ordersByMeasure[m.id] = ordersByMeasure[m.id] || []).push(created);
        render();
      } catch (err) {
        msg.className = "msg err";
        msg.textContent = "Помилка: " + err.message;
      }
    });
    return el("div", {}, [
      el("h3", { text: "Накази" }),
      list,
      orders.length ? el("p", { class: "small muted", text: "Файл передається на локальну модель на сервері й не зберігається в системі." }) : null,
      form,
      msg,
    ]);
  }

  function evidenceBlock(m) {
    const list = evidenceByMeasure[m.id] || [];
    return el("div", {}, [
      el("h3", { text: "Підтвердні матеріали (" + list.length + ")" }),
      list.length
        ? el("ul", { class: "plain" }, list.map(function (e) {
            return el("li", {}, [Api.docLink(e.source_url, e.title), " — " + e.document_type + (e.document_date ? ", " + Api.fmtDate(e.document_date) : "")]);
          }))
        : el("p", { class: "small muted", style: "margin:0", text: "Підтверджень немає." }),
    ]);
  }

  function changesBlock(m) {
    const list = changesByMeasure[m.id] || [];
    if (!list.length) return null;
    return el("div", {}, [
      el("h3", { text: "Перенесення строку (" + list.length + ")" }),
      el("ul", { class: "plain" }, list.map(function (c) {
        return el("li", { text: Api.fmtDate(c.previous_deadline) + " → " + Api.fmtDate(c.new_deadline) + " (рішення " + Api.fmtDate(c.decision_date) + "): " + c.reason });
      })),
    ]);
  }

  async function changeStatus(m, key, select, msg) {
    if (!key) return;
    const period = periodSel.value;
    select.disabled = true;
    msg.className = "msg";
    msg.textContent = "Збереження…";
    try {
      let ex = executions[m.id];
      const fields = Object.assign({}, Api.STATUS_PATCH[key]);
      ex = ex
        ? await Api.patch(Api.executionUrl(m.id, period), fields)
        : await Api.post("/api/executions/", Object.assign({ measure_id: m.id, period: period, result_description: "" }, fields));
      const approve = key === "done";
      if (ex.approved_by_coordinator !== approve) {
        ex = await Api.patch(Api.executionUrl(m.id, period) + "/approval", { approved_by_coordinator: approve });
      }
      executions[m.id] = ex;
      assess();
      render();
    } catch (err) {
      select.disabled = false;
      msg.className = "msg err";
      msg.textContent = "Помилка: " + err.message;
    }
  }

  // Створення програми (POST /api/programs).
  const dialog = document.getElementById("program-dialog");
  const form = document.getElementById("program-form");
  const formErr = document.getElementById("program-error");
  document.getElementById("create-program").addEventListener("click", function () {
    form.reset();
    formErr.classList.add("hidden");
    dialog.showModal();
  });
  document.getElementById("program-cancel").addEventListener("click", function () { dialog.close(); });
  form.addEventListener("submit", async function (e) {
    e.preventDefault();
    if (!form.reportValidity()) return;
    const data = Object.fromEntries(new FormData(form).entries());
    data.notes = "";
    try {
      const created = await Api.post("/api/programs", data);
      programs.push(created);
      open.add("p:" + created.id);
      dialog.close();
      render();
    } catch (err) {
      formErr.textContent = err.message;
      formErr.classList.remove("hidden");
    }
  });

  init();
})();
