// Кабінет координатора: програма → розділ → захід → підрозділи; зміна статусу виконання.
(function () {
  "use strict";
  if (!Api.requireLogin()) return;
  const el = Api.el;
  const root = document.getElementById("programs");
  const periodSel = document.getElementById("period");
  const search = document.getElementById("search");

  let programs = [];
  let measuresByProg = {};
  let sections = {};
  let executions = {};
  const open = new Set(); // ключі розгорнутих вузлів: p:ID, s:ID:N, m:ID

  async function init() {
    try {
      const [progList, measures, secs] = await Promise.all([
        Api.get("/api/programs"), Api.measures(), Api.sections(),
      ]);
      programs = progList;
      sections = secs;
      measuresByProg = {};
      measures.sort(Api.byMeasureOrder).forEach(function (m) {
        (measuresByProg[m.program_id] = measuresByProg[m.program_id] || []).push(m);
      });
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
      const list = await Api.executions(periodSel.value);
      executions = {};
      list.forEach(function (x) { executions[x.measure_id] = x; });
      render();
    } catch (err) {
      Api.showError(err);
    }
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
    return matches(m.description, q) || matches(Api.measureNo(m), q) ||
      matches(Api.deptName(m.responsible_department_id), q) || matches(Api.orderNumber(executions[m.id]), q);
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
    const head = el("button", { type: "button", class: "row-head", "aria-expanded": String(isOpen), onclick: function () { toggle(key); } }, [
      el("span", { class: "title", text: p.title }),
      el("span", { class: "meta", text: Api.fmtDate(p.start_date) + " – " + Api.fmtDate(p.end_date) }),
      counter(all),
    ]);
    const node = el("div", { class: "prog" }, [head]);
    if (!isOpen) return node;
    const body = el("div", { class: "prog-body" });
    const bySec = {};
    list.forEach(function (m) { (bySec[m.section_id] = bySec[m.section_id] || []).push(m); });
    const secIds = Object.keys(bySec).sort(Api.compareSections);
    if (!secIds.length) body.appendChild(el("p", { class: "muted", style: "padding:8px 18px", text: "У програмі ще немає заходів." }));
    secIds.forEach(function (sid) { body.appendChild(sectionNode(p, sid, bySec[sid], forceOpen)); });
    node.appendChild(body);
    return node;
  }

  function finalDeadline(list) {
    const dates = list.map(function (m) { return m.deadline_on; }).filter(Boolean).sort();
    if (dates.length) return "Кінцевий строк: " + Api.fmtDate(dates[dates.length - 1]);
    return "Строк: постійно";
  }

  function sectionNode(p, sid, list, forceOpen) {
    const key = "s:" + p.id + ":" + sid;
    const isOpen = forceOpen || open.has(key);
    const head = el("button", { type: "button", class: "row-head", "aria-expanded": String(isOpen), onclick: function () { toggle(key); } }, [
      el("span", { class: "title", text: Api.sectionTitle(sections, sid) }),
      el("span", { class: "meta", text: finalDeadline(list) }),
      counter(list),
    ]);
    const node = el("div", { class: "sec" }, [head]);
    if (!isOpen) return node;
    const body = el("div", { class: "sec-body" });
    list.forEach(function (m) { body.appendChild(measureNode(m)); });
    node.appendChild(body);
    return node;
  }

  function measureNode(m) {
    const key = "m:" + m.id;
    const isOpen = open.has(key);
    const head = el("button", { type: "button", class: "row-head", "aria-expanded": String(isOpen), onclick: function () { toggle(key); } }, [
      el("span", { class: "num", text: Api.measureNo(m) }),
      el("span", { text: m.description }),
      Api.statusBadge(Api.statusOf(executions[m.id])),
    ]);
    const node = el("div", { class: "measure" }, [head]);
    if (isOpen) node.appendChild(unitsNode(m));
    return node;
  }

  // ЗАГЛУШКА: співвиконавців API не віддає — показуємо відповідальний підрозділ.
  function unitsNode(m) {
    const ex = executions[m.id];
    const key = Api.statusOf(ex);
    const select = el("select", { "aria-label": "Статус виконання заходу " + Api.measureNo(m) });
    if (["done", "review", "rework", "not"].indexOf(key) === -1) {
      select.appendChild(el("option", { value: "", text: Api.STATUS[key].label }));
    }
    ["done", "review", "rework", "not"].forEach(function (k) {
      select.appendChild(el("option", { value: k, text: Api.STATUS[k].label }));
    });
    select.value = ["done", "review", "rework", "not"].indexOf(key) !== -1 ? key : "";
    const msg = el("div", { class: "msg", role: "status" });
    select.addEventListener("change", function () { changeStatus(m, select.value, select, msg); });
    const order = Api.orderNumber(ex);
    return el("div", { class: "units table-wrap" }, [
      el("table", { class: "grid" }, [
        el("thead", {}, [el("tr", {}, [
          el("th", { text: "Підрозділ" }), el("th", { text: "Дата" }), el("th", { text: "№ наказу" }),
          el("th", { text: "Примітка" }), el("th", { text: "Статус" }),
        ])]),
        el("tbody", {}, [el("tr", {}, [
          el("td", { text: Api.deptName(m.responsible_department_id) }),
          el("td", { class: "nowrap", text: ex && ex.completed_on ? Api.fmtDate(ex.completed_on) : "—" }),
          el("td", { title: order ? "Посилання на документ з'явиться з реєстром наказів" : null, text: order ? "№ " + order : "—" }),
          el("td", { class: "muted", text: Api.noteOf(ex) || "—" }),
          el("td", {}, [select, msg]),
        ])]),
      ]),
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
      if (!ex) {
        ex = await Api.post("/api/executions/", Object.assign({ measure_id: m.id, period: period, result_description: "" }, fields));
      } else {
        ex = await Api.patch(Api.executionUrl(m.id, period), fields);
      }
      const approve = key === "done";
      if (ex.approved_by_coordinator !== approve) {
        ex = await Api.patch(Api.executionUrl(m.id, period) + "/approval", { approved_by_coordinator: approve });
      }
      executions[m.id] = ex;
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
