// Кабінет координатора.
// Головний координатор (власник програми): створення й редагування програм, розсилка програми
// підрозділам (/api/program-routing/programs/{id}/departments).
// Координатор підрозділу (отримувач програми): бачить лише надіслані йому програми й заходи своєї
// гілки та призначає виконавців зі свого й підпорядкованих підрозділів (/measures/{id}/assign).
// Спільне: програма → розділ → захід, статус виконання, сигнали Risk Flags, дзвіночок сповіщень.
(function () {
  "use strict";
  const el = Api.el;
  const ROUTING = "/api/program-routing";
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
  let changesByMeasure = {};
  let flagsByMeasure = {};
  let access = {};          // program_id -> owner | department_coordinator | admin
  let regional = false;     // координатор-отримувач без власних програм
  const assignments = {};   // measure_id -> [{user_id, department_id}]
  const people = {};        // user_id -> {id, login, department_id}
  const sentTo = {};        // program_id -> [department_id], надіслані в цій сесії
  const open = new Set();   // розгорнуті вузли: p:ID, s:ID:R, m:ID

  async function init() {
    if (!await Api.requireRole("KOORD")) return;
    try {
      const mine = await Api.optional(Api.get(ROUTING + "/my/programs", { noRedirect: true }));
      mine.data.forEach(function (row) { access[row.id] = row.access_type; });
      const types = mine.data.map(function (row) { return row.access_type; });
      regional = types.indexOf("department_coordinator") !== -1 && types.indexOf("owner") === -1;
      if (regional) {
        document.getElementById("coord-kind").textContent = "Координатор підрозділу";
        document.getElementById("create-program").classList.add("hidden");
        document.getElementById("assign-open").classList.remove("hidden");
      }

      const [progList, measures, secs, orders, changes] = await Promise.all([
        Api.get("/api/programs"), Api.measures(), Api.sections(),
        Api.optional(Api.orders()), Api.optional(Api.deadlineChanges()),
      ]);
      sections = secs;
      ordersByMeasure = Api.groupBy(orders.data, "measure_id");
      changesByMeasure = Api.groupBy(changes.data, "measure_id");

      if (regional) {
        // Лише надіслані програми й заходи, які бекенд відкриває цьому координатору.
        programs = progList.filter(function (p) { return access[p.id]; });
        const visible = {};
        await Promise.all(programs.map(async function (p) {
          const list = await Api.optional(Api.get(ROUTING + "/programs/" + encodeURIComponent(p.id) + "/measures"));
          list.data.forEach(function (m) { visible[m.id] = true; });
          await loadDepartments(p.id);
        }));
        measuresByProg = Api.groupBy(measures.filter(function (m) { return visible[m.id]; }).sort(Api.byMeasureOrder), "program_id");
        await loadAssignments(measures.filter(function (m) { return visible[m.id]; }));
      } else {
        programs = progList;
        measuresByProg = Api.groupBy(measures.sort(Api.byMeasureOrder), "program_id");
      }

      const coordDept = (Api.me && Api.me.department_id) ||
        programs.map(function (p) { return p.coordinator_department_id; }).filter(Boolean)[0];
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
      render();
    } catch (err) {
      Api.showError(err);
    }
  }

  // ---------- довідник підрозділів і виконавців (з бекенду розсилки) ----------

  const deptCache = {};     // program_id -> [{id, name, parent_id}]
  const execCache = {};     // program_id -> [{dept, users:[{id, login, department_id}]}]

  // Підрозділи, доступні для вибору в цій програмі; заодно поповнюємо довідник назв.
  async function loadDepartments(programId) {
    if (deptCache[programId]) return deptCache[programId];
    const res = await Api.optional(Api.get(ROUTING + "/programs/" + encodeURIComponent(programId) + "/available-departments"));
    deptCache[programId] = res.ok ? res.data : null;
    (res.data || []).forEach(function (d) { Api.DEPARTMENTS[d.id] = d.name; });
    return deptCache[programId];
  }

  // Виконавці (VYK) кожного підрозділу гілки координатора.
  async function loadExecutors(programId) {
    if (execCache[programId]) return execCache[programId];
    const depts = await loadDepartments(programId) || [];
    const groups = await Promise.all(depts.map(async function (d) {
      const res = await Api.optional(Api.get(ROUTING + "/programs/" + encodeURIComponent(programId) +
        "/departments/" + encodeURIComponent(d.id) + "/executors"));
      res.data.forEach(function (u) { people[u.id] = u; });
      return { dept: d, users: res.data };
    }));
    execCache[programId] = groups.filter(function (g) { return g.users.length; });
    return execCache[programId];
  }

  async function loadAssignments(measures) {
    await Promise.all(measures.map(async function (m) {
      const res = await Api.optional(Api.get(ROUTING + "/measures/" + encodeURIComponent(m.id) + "/assignments"));
      assignments[m.id] = res.data.map(function (a) { return { user_id: a.user_id, department_id: a.department_id }; });
    }));
  }

  // Призначені заходу підрозділи (без повторів).
  function assignedDepts(m) {
    const out = [];
    (assignments[m.id] || []).forEach(function (a) { if (out.indexOf(a.department_id) === -1) out.push(a.department_id); });
    return out;
  }

  function assigneeText(m) {
    const list = assignedDepts(m);
    return list.length ? list.map(Api.deptName).join(", ") : "Не призначено";
  }

  // ---------- дерево програм ----------

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
    return el("div", { class: "count", text: "Виконано " + done + " / " + list.length });
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
    renderNotifs();
    const q = search.value.trim().toLowerCase();
    root.innerHTML = "";
    let shown = 0;
    programs.forEach(function (p) {
      const all = measuresByProg[p.id] || [];
      const progHit = !q || matches(p.title, q) || matches(p.id, q) || matches(p.organization_name, q);
      const list = progHit ? all : all.filter(function (m) {
        return measureMatches(m, q) || matches(Api.sectionTitle(sections, m.section_id), q);
      });
      if (q && !progHit && !list.length) return;
      shown++;
      root.appendChild(programNode(p, all, list, q && !progHit));
    });
    if (!shown) {
      const empty = regional ? "Вашому підрозділу ще не надіслано програм." : "Програм ще немає. Створіть першу.";
      root.appendChild(el("p", { class: "muted", text: q ? "Нічого не знайдено." : empty }));
    }
  }

  function canEdit(p) { return !regional && access[p.id] !== "department_coordinator"; }

  function programNode(p, all, list, forceOpen) {
    const key = "p:" + p.id;
    const isOpen = forceOpen || open.has(key);
    const node = el("div", { class: "prog" }, [
      el("button", { type: "button", class: "row-head", "aria-expanded": String(isOpen), onclick: function () { toggle(key); } }, [
        el("span", { class: "title" }, [
          el("span", { class: "code", text: p.id }),
          p.title,
          el("span", { class: "sub", text: p.organization_name || "" }),
        ]),
        el("span", { class: "meta", text: Api.fmtDate(p.start_date) + " – " + Api.fmtDate(p.end_date) }),
        counter(all),
      ]),
    ]);
    if (!isOpen) return node;
    const body = el("div", { class: "prog-body" }, [
      el("div", { class: "prog-tools" }, [
        el("div", {}, [
          el("div", { class: "small muted", text: (p.approval_reference || "") + (p.approval_status ? " · " + approvalLabel(p.approval_status) : "") }),
          sentSummary(p),
        ]),
        canEdit(p) ? el("button", { type: "button", class: "btn", onclick: function () { openDialog(p); } }, ["Редагувати програму"]) : null,
      ]),
    ]);
    const bySec = Api.groupBy(list, "section_id");
    const secIds = Object.keys(bySec).sort(Api.compareSections);
    if (!secIds.length) body.appendChild(el("p", { class: "muted", style: "padding:8px 18px", text: "У програмі ще немає заходів." }));
    secIds.forEach(function (sid) { body.appendChild(sectionNode(p, sid, bySec[sid], forceOpen)); });
    node.appendChild(body);
    return node;
  }

  function sentSummary(p) {
    const ids = sentTo[p.id] || [];
    if (!ids.length) return null;
    return el("div", { class: "small", style: "margin-top:2px", text: "Надіслано на координацію: " + ids.map(Api.deptName).join(", ") });
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
    const node = el("div", { class: "measure", id: "row-" + m.id }, [
      el("button", { type: "button", class: "row-head", "aria-expanded": String(isOpen), onclick: function () { toggle(key); } }, [
        el("span", { class: "num", text: Api.measureNo(m) }),
        el("span", { text: m.description }),
        el("span", { class: "flags" }, flags.map(Api.flagBadge)),
        Api.statusBadge(Api.statusOf(executions[m.id])),
      ]),
    ]);
    if (isOpen) node.appendChild(detailNode(m));
    return node;
  }

  function detailNode(m) {
    return el("div", { class: "detail" }, [unitsTable(m), flagsBlock(m), changesBlock(m)]);
  }

  function deadlineText(m) {
    if (m.deadline_on) return Api.fmtDate(m.deadline_on);
    if (m.deadline_type === "ongoing") return "Постійно";
    return m.deadline_description || "—";
  }

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
          el("th", { text: "Підрозділ" }), regional ? el("th", { text: "Виконавці" }) : null,
          el("th", { text: "Виконати до" }), el("th", { text: "Фактично виконано" }),
          el("th", { text: "№ наказу" }), el("th", { text: "Примітка" }), el("th", { text: "Статус" }),
        ])]),
        el("tbody", {}, [el("tr", {}, [
          el("td", { text: Api.deptName(m.responsible_department_id) }),
          regional ? el("td", { text: assigneeText(m) }) : null,
          el("td", { class: "nowrap", text: deadlineText(m) }),
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
      render();
    } catch (err) {
      select.disabled = false;
      msg.className = "msg err";
      msg.textContent = "Помилка: " + err.message;
    }
  }

  // ---------- випадний список із пошуком і множинним вибором ----------
  // Поле з чипами саме є рядком пошуку; під ним розкривається список із галочками.
  // groups: [{name, items: [{id, label}]}]; chosen — масив id, змінюється на місці.
  function multiPick(groups, chosen, label, placeholder) {
    const labels = {};
    groups.forEach(function (g) { g.items.forEach(function (it) { labels[it.id] = it.label; }); });
    const nameOf = function (id) { return labels[id] || String(id); };
    const chips = el("span", { class: "mpick-chips" });
    const input = el("input", { type: "text", class: "mpick-input", autocomplete: "off", "aria-label": label, "aria-expanded": "false" });
    const arrow = el("button", { type: "button", class: "mpick-arrow-btn", "aria-label": "Показати список", tabindex: "-1" }, [
      el("span", { class: "mpick-arrow", "aria-hidden": "true" }),
    ]);
    const field = el("div", { class: "mpick-field" }, [chips, input, arrow]);
    const list = el("div", { class: "mpick-list", role: "group", "aria-label": label });
    const pop = el("div", { class: "mpick-pop hidden" }, [list]);

    function drawChips() {
      chips.innerHTML = "";
      chosen.forEach(function (id) {
        chips.appendChild(el("span", { class: "mpick-chip" }, [
          nameOf(id),
          el("span", { class: "x", role: "button", "aria-label": "Прибрати " + nameOf(id), title: "Прибрати", text: "×",
            onclick: function (e) { e.stopPropagation(); toggleItem(id); } }),
        ]));
      });
      input.placeholder = chosen.length ? "Додати ще…" : placeholder;
    }

    function toggleItem(id) {
      const i = chosen.indexOf(id);
      if (i === -1) chosen.push(id); else chosen.splice(i, 1);
      drawChips();
      if (!pop.classList.contains("hidden")) drawList();
    }

    function drawList() {
      const q = input.value.trim().toLowerCase();
      list.innerHTML = "";
      let any = false;
      groups.forEach(function (g) {
        const items = g.items.filter(function (it) { return !q || matches(it.label, q) || matches(g.name, q); });
        if (!items.length) return;
        any = true;
        list.appendChild(el("div", { class: "mpick-group", text: g.name }));
        items.forEach(function (it) {
          const box = el("input", { type: "checkbox" });
          box.checked = chosen.indexOf(it.id) !== -1;
          box.addEventListener("change", function () { toggleItem(it.id); });
          list.appendChild(el("label", { class: "dept-item" }, [box, it.label]));
        });
      });
      if (!any) list.appendChild(el("p", { class: "small muted", style: "margin:6px 0", text: groups.length ? "Нічого не знайдено." : "Список порожній." }));
    }

    function setOpen(show) {
      if (show) closeAllPicks(pop);
      pop.classList.toggle("hidden", !show);
      field.classList.toggle("open", show);
      input.setAttribute("aria-expanded", String(show));
      if (show) drawList(); else input.value = "";
    }

    field.addEventListener("click", function () { input.focus(); if (pop.classList.contains("hidden")) setOpen(true); });
    arrow.addEventListener("click", function (e) { e.stopPropagation(); setOpen(pop.classList.contains("hidden")); if (!pop.classList.contains("hidden")) input.focus(); });
    input.addEventListener("input", function () { if (pop.classList.contains("hidden")) setOpen(true); else drawList(); });
    input.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && !pop.classList.contains("hidden")) { e.stopPropagation(); e.preventDefault(); setOpen(false); }
      if (e.key === "Backspace" && !input.value && chosen.length) toggleItem(chosen[chosen.length - 1]);
      if (e.key === "Enter") e.preventDefault(); // не відправляти форму
    });
    pop.close = function () { setOpen(false); };
    drawChips();
    return el("div", { class: "mpick" }, [field, pop]);
  }

  function closeAllPicks(except) {
    document.querySelectorAll(".mpick-pop").forEach(function (p) { if (p !== except && p.close && !p.classList.contains("hidden")) p.close(); });
  }
  document.addEventListener("click", function (e) { if (!e.target.closest(".mpick")) closeAllPicks(null); });

  // Групування підрозділів за батьківським: «Назва батька» → дочірні.
  // all — повний перелік для пошуку назв батьків (за замовчуванням — самі depts).
  function deptGroups(depts, all) {
    const byId = {};
    (all || depts).forEach(function (d) { byId[d.id] = d; });
    const groups = {};
    depts.forEach(function (d) {
      const parent = d.parent_id && byId[d.parent_id] ? byId[d.parent_id].name : "Верхній рівень";
      (groups[parent] = groups[parent] || []).push({ id: d.id, label: d.name });
    });
    return Object.keys(groups).map(function (name) { return { name: name, items: groups[name] }; });
  }

  // ---------- вікно «Призначити виконавця» (координатор підрозділу) ----------
  const assignDialog = document.getElementById("assign-dialog");
  const assignBody = document.getElementById("assign-body");
  const assignSearch = document.getElementById("assign-search");
  const assignMsg = document.getElementById("assign-msg");
  const aOpen = new Set();  // розгорнуті у вікні: p:ID, s:ID:R
  let draft = {};           // measure_id -> [department_id]
  const deptUsers = {};     // department_id -> [user_id] виконавців підрозділу
  let pickGroups = {};      // program_id -> групи для multiPick

  async function openAssign() {
    assignSearch.value = "";
    setAssignMsg("", "Завантаження виконавців…");
    assignBody.innerHTML = "";
    assignDialog.showModal();
    pickGroups = {};
    // Для вибору — лише підрозділи гілки, у яких є виконавці; сам координатор свій підрозділ не обирає.
    const own = Api.me && Api.me.department_id;
    await Promise.all(programs.map(async function (p) {
      const groups = await loadExecutors(p.id);
      groups.forEach(function (g) { deptUsers[g.dept.id] = g.users.map(function (u) { return u.id; }); });
      const depts = groups.map(function (g) { return g.dept; }).filter(function (d) { return d.id !== own; });
      pickGroups[p.id] = deptGroups(depts, deptCache[p.id] || depts);
    }));
    draft = {};
    Object.keys(assignments).forEach(function (k) {
      draft[k] = assignedDepts({ id: k });
    });
    setAssignMsg("", "");
    renderAssign();
  }

  function setAssignMsg(kind, text) {
    assignMsg.className = "msg" + (kind ? " " + kind : "");
    assignMsg.textContent = text;
  }

  function aToggle(key) { aOpen.has(key) ? aOpen.delete(key) : aOpen.add(key); renderAssign(); }

  function renderAssign() {
    const q = assignSearch.value.trim().toLowerCase();
    assignBody.innerHTML = "";
    let shown = 0;
    programs.forEach(function (p) {
      const all = measuresByProg[p.id] || [];
      const progHit = !q || matches(p.title, q) || matches(p.id, q);
      const list = progHit ? all : all.filter(function (m) { return matches(m.description, q) || matches(Api.measureNo(m), q); });
      if (!list.length) return;
      shown++;
      const key = "p:" + p.id;
      const isOpen = !!q || aOpen.has(key);
      const node = el("div", { class: "prog" }, [
        el("button", { type: "button", class: "row-head", "aria-expanded": String(isOpen), onclick: function () { aToggle(key); } }, [
          el("span", { class: "title" }, [el("span", { class: "code", text: p.id }), p.title]),
          el("span"),
        ]),
      ]);
      if (isOpen) {
        const body = el("div", { class: "prog-body" });
        const bySec = Api.groupBy(list, "section_id");
        Object.keys(bySec).sort(Api.compareSections).forEach(function (sid) {
          const sKey = "s:" + p.id + ":" + sid;
          const sOpen = !!q || aOpen.has(sKey);
          const sec = el("div", { class: "sec" }, [
            el("button", { type: "button", class: "row-head", "aria-expanded": String(sOpen), onclick: function () { aToggle(sKey); } }, [
              el("span", { class: "title", text: Api.sectionTitle(sections, sid) }),
              el("span"),
            ]),
          ]);
          if (sOpen) sec.appendChild(el("div", { class: "assign-rows" }, bySec[sid].map(function (m) { return assignRow(p, m); })));
          body.appendChild(sec);
        });
        node.appendChild(body);
      }
      assignBody.appendChild(node);
    });
    if (!shown) assignBody.appendChild(el("p", { class: "muted", text: q ? "Нічого не знайдено." : "Заходів немає." }));
  }

  function assignRow(p, m) {
    const chosen = draft[m.id] = draft[m.id] || [];
    return el("div", { class: "assign-row" }, [
      el("div", {}, [
        el("div", {}, [el("span", { class: "num", text: Api.measureNo(m) + " " }), m.description]),
        el("div", { class: "small muted", text: "Виконати до: " + deadlineText(m) }),
      ]),
      multiPick(pickGroups[p.id] || [], chosen, "Виконавці заходу " + Api.measureNo(m), "Оберіть відділи та підрозділи"),
    ]);
  }

  // Різниця між чернеткою й поточними призначеннями: нові — POST, зняті — DELETE.
  async function saveAssign() {
    const btn = document.getElementById("assign-save");
    btn.disabled = true;
    setAssignMsg("", "Збереження…");
    const failed = [];
    const all = [];
    Object.keys(measuresByProg).forEach(function (k) { all.push.apply(all, measuresByProg[k]); });
    // Бекенд призначає людей, тож підрозділ = усі його виконавці (VYK).
    for (const m of all) {
      const before = assignedDepts(m);
      const after = draft[m.id] || before;
      const url = ROUTING + "/measures/" + encodeURIComponent(m.id);
      for (const dep of after) {
        if (before.indexOf(dep) !== -1) continue;
        for (const uid of deptUsers[dep] || []) {
          try {
            await Api.post(url + "/assign", { department_id: dep, user_id: uid });
          } catch (err) { failed.push(Api.measureNo(m) + " — " + Api.deptName(dep) + ": " + err.message); }
        }
      }
      for (const a of assignments[m.id] || []) {
        if (after.indexOf(a.department_id) !== -1) continue;
        try {
          await Api.del(url + "/assign/" + encodeURIComponent(a.user_id));
        } catch (err) { failed.push(Api.measureNo(m) + " — зняти " + Api.deptName(a.department_id) + ": " + err.message); }
      }
    }
    await loadAssignments(all);
    btn.disabled = false;
    render();
    if (failed.length) {
      Object.keys(assignments).forEach(function (k) { draft[k] = assignedDepts({ id: k }); });
      renderAssign();
      setAssignMsg("err", "Не все збережено: " + failed.join("; "));
      return;
    }
    assignDialog.close();
  }

  if (document.getElementById("assign-open")) {
    document.getElementById("assign-open").addEventListener("click", openAssign);
    document.getElementById("assign-cancel").addEventListener("click", function () { assignDialog.close(); });
    document.getElementById("assign-save").addEventListener("click", saveAssign);
    assignSearch.addEventListener("input", renderAssign);
  }

  // ---------- сповіщення ----------

  // Для координатора: звіти, що чекають розгляду; прострочені й термінові заходи без звіту.
  function renderNotifs() {
    const out = [];
    programs.forEach(function (p) {
      (measuresByProg[p.id] || []).forEach(function (m) {
        const st = Api.statusOf(executions[m.id]);
        if (st === "done") return;
        const which = p.id + " · " + Api.measureNo(m) + " " + m.description + " · " + Api.deptName(m.responsible_department_id);
        const go = function () { goTo(p, m); };
        if (st === "review") { out.push({ lvl: "review", rank: 1, what: "Звіт очікує розгляду", which: which, go: go }); return; }
        const d = Notify.daysLeft(m);
        if (d === null) return;
        if (d < 0) out.push({ lvl: "late", rank: 0, days: d, what: "Прострочено на " + -d + " дн.", which: which, go: go });
        else if (d <= 30) out.push({ lvl: "soon", rank: 2, days: d, what: (d === 0 ? "Строк сьогодні" : "Строк через " + d + " дн.") + ", звіту немає", which: which, go: go });
      });
    });
    out.sort(function (a, b) { return a.rank - b.rank || (a.days || 0) - (b.days || 0); });
    Notify.render(out, "Нових сповіщень немає.");
  }

  function goTo(p, m) {
    search.value = "";
    open.add("p:" + p.id);
    open.add("s:" + p.id + ":" + m.section_id);
    open.add("m:" + m.id);
    render();
    Notify.flash(document.getElementById("row-" + m.id));
  }

  // ---------- створення й редагування програми, розсилка підрозділам ----------
  // POST /api/programs — нова; PATCH /api/programs/{id} — зміна (код програми не змінюється).
  // Розсилка: POST /api/program-routing/programs/{id}/departments — лише для існуючої програми.
  const APPROVAL = { draft: "Проєкт", approved: "Затверджено" };
  function approvalLabel(v) { return APPROVAL[v] || v; }

  const dialog = document.getElementById("program-dialog");
  const form = document.getElementById("program-form");
  const formErr = document.getElementById("program-error");
  const pickBox = document.getElementById("dept-pick-box");
  const pickNote = document.getElementById("dept-pick-note");
  const FIELDS = ["id", "title", "organization_name", "start_date", "end_date", "approval_reference", "approval_status", "goals"];
  let editing = null;   // програма, що редагується; null — створення
  let toSend = [];      // обрані підрозділи для розсилки

  async function fillDeptPicker(p) {
    toSend = [];
    pickBox.innerHTML = "";
    pickNote.textContent = "Завантаження підрозділів…";
    // Для нової програми довідник підрозділів беремо з будь-якої власної програми:
    // власнику бекенд віддає всі підрозділи відомства.
    const source = p ? p.id : Object.keys(access).filter(function (id) { return access[id] === "owner"; })[0];
    const depts = source ? await loadDepartments(source) : null;
    if (editing !== p) return; // вікно вже перемкнули
    if (!depts) {
      pickNote.textContent = p
        ? "Надсилати цю програму може лише її власник — координатор, який її створив."
        : "Не вдалося отримати перелік підрозділів.";
      return;
    }
    const own = Api.me && Api.me.department_id;
    const choices = depts.filter(function (d) { return d.id !== own; });
    pickNote.textContent = p && (sentTo[p.id] || []).length
      ? "Уже надіслано в цій сесії: " + sentTo[p.id].map(Api.deptName).join(", ") + "."
      : "У кожному обраному підрозділі має бути координатор.";
    pickBox.appendChild(multiPick(deptGroups(choices, depts), toSend, "Підрозділи для координації", "Оберіть підрозділи для координації"));
  }

  function openDialog(p) {
    editing = p || null;
    form.reset();
    formErr.classList.add("hidden");
    const status = form.elements.approval_status;
    Array.from(status.options).forEach(function (o) { if (o.dataset.extra) o.remove(); });
    if (p) {
      if (p.approval_status && !APPROVAL[p.approval_status]) {
        status.appendChild(el("option", { value: p.approval_status, text: p.approval_status, "data-extra": "1" }));
      }
      FIELDS.forEach(function (f) { form.elements[f].value = p[f] == null ? "" : p[f]; });
    }
    form.elements.id.readOnly = !!p;
    document.getElementById("program-dialog-title").textContent = p ? "Редагування програми " + p.id : "Нова програма";
    document.getElementById("program-submit").textContent = p ? "Зберегти зміни" : "Створити програму";
    dialog.showModal();
    fillDeptPicker(editing);
  }

  async function dispatch(programId) {
    if (!toSend.length) return;
    const res = await Api.post(ROUTING + "/programs/" + encodeURIComponent(programId) + "/departments", { department_ids: toSend.slice() });
    const ids = res.departments.map(function (d) { return d.department_id; });
    sentTo[programId] = Array.from(new Set((sentTo[programId] || []).concat(ids)));
  }

  document.getElementById("create-program").addEventListener("click", function () { openDialog(null); });
  document.getElementById("program-cancel").addEventListener("click", function () { dialog.close(); });
  form.addEventListener("submit", async function (e) {
    e.preventDefault();
    if (!form.reportValidity()) return;
    const data = Object.fromEntries(new FormData(form).entries());
    try {
      if (editing) {
        delete data.id;
        const saved = await Api.patch("/api/programs/" + encodeURIComponent(editing.id), data);
        programs[programs.indexOf(editing)] = saved;
        editing = saved;
        open.add("p:" + saved.id);
        await dispatch(saved.id);
      } else {
        data.notes = "";
        const created = await Api.post("/api/programs", data);
        programs.push(created);
        access[created.id] = "owner";
        open.add("p:" + created.id);
        editing = created;
        form.elements.id.readOnly = true;
        document.getElementById("program-dialog-title").textContent = "Редагування програми " + created.id;
        document.getElementById("program-submit").textContent = "Зберегти зміни";
        try {
          await dispatch(created.id);
        } catch (err) {
          render();
          throw new Error("Програму створено, але не надіслано підрозділам: " + err.message);
        }
      }
      dialog.close();
      render();
    } catch (err) {
      formErr.textContent = err.message;
      formErr.classList.remove("hidden");
      render();
    }
  });

  init();
})();
