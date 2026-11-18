// Кабінет координатора: створення й редагування програм, програма → розділ → захід → підрозділ,
// перенесення строків, сигнали Risk Flags, зміна статусу виконання і дзвіночок сповіщень.
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
  let changesByMeasure = {};
  let flagsByMeasure = {};
  // Регіональний / обласний координатор: програм не створює й не редагує, лише призначає виконавців.
  // ЗАГЛУШКА: бекенд не розрізняє рівні координаторів — визначаємо за підрозділом користувача.
  let regional = false;
  const assignees = {};    // measure_id -> [id відділу/підрозділу] (макет, лише в пам'яті)
  const open = new Set(); // розгорнуті вузли: p:ID, s:ID:R, m:ID

  async function init() {

    if (!await Api.requireRole("KOORD")) return;
    regional = !!(Api.me && Api.REGIONAL_UNITS[Api.me.department_id]);
    if (regional) {
      document.getElementById("coord-kind").textContent = "Регіональний координатор";
      document.getElementById("create-program").classList.add("hidden");
      document.getElementById("assign-open").classList.remove("hidden");
    }
    try {
      const [progList, measures, secs, orders, changes] = await Promise.all([
        Api.get("/api/programs"), Api.measures(), Api.sections(),
        Api.optional(Api.orders()), Api.optional(Api.deadlineChanges()),
      ]);
      programs = progList;
      sections = secs;
      ordersByMeasure = Api.groupBy(orders.data, "measure_id");
      changesByMeasure = Api.groupBy(changes.data, "measure_id");
      measuresByProg = Api.groupBy(measures.sort(Api.byMeasureOrder), "program_id");
      // Підрозділ самого координатора; якщо не вказано — підрозділ-координатор програми.
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
    if (!shown) root.appendChild(el("p", { class: "muted", text: q ? "Нічого не знайдено." : "Програм ще немає. Створіть першу." }));
  }

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
          deptSummary(p),
        ]),
        regional ? null : el("button", { type: "button", class: "btn", onclick: function () { openDialog(p); } }, ["Редагувати програму"]),
      ]),
    ]);
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
    return el("div", { class: "detail" }, [
      unitsTable(m),
      flagsBlock(m),
      changesBlock(m),
    ]);
  }

  // ---------- призначення виконавців — відділів і підрозділів (регіональний координатор) ----------
  // ЗАГЛУШКА: умовний перелік структури регіонального управління. У бекенді для заходу є лише один
  // responsible_department_id / assigned_user_id, тож вибір кількох виконавців живе в пам'яті сторінки.
  const UNIT_GROUPS = [
    ["Апарат управління", [
      "Відділ кадрового забезпечення", "Відділ закупівель", "Фінансово-економічний відділ", "Юридичний відділ",
      "Відділ документального забезпечення", "Сектор з питань запобігання корупції", "Відділ внутрішнього аудиту",
      "Відділ цифрової трансформації", "Відділ комунікацій", "Відділ контролю та звітності",
    ]],
    ["Територіальні відділи", [
      "Білоцерківський районний відділ", "Бориспільський районний відділ", "Броварський районний відділ",
      "Бучанський районний відділ", "Вишгородський районний відділ", "Обухівський районний відділ",
      "Фастівський районний відділ",
    ]],
    ["Підпорядковані установи", [
      "Обласний центр комплектування (умовний)", "Навчальний центр «Умовний»", "Обласний госпітальний центр (умовний)",
      "База матеріально-технічного забезпечення (умовна)", "Ремонтна майстерня (умовна)",
      "Інформаційно-аналітичний центр (умовний)", "Центр обслуговування громадян (умовний)",
    ]],
    ["Служби", [
      "Служба логістики", "Служба зв'язку", "Служба охорони праці", "Служба психологічної підтримки",
      "Прес-служба", "Служба безпеки інформації",
    ]],
  ];
  const UNITS_FLAT = [];
  UNIT_GROUPS.forEach(function (g, gi) {
    g[1].forEach(function (name, i) { UNITS_FLAT.push({ id: "U" + (gi + 1) + "-" + (i + 1), name: name, group: g[0] }); });
  });

  function unitLabel(id) {
    const u = UNITS_FLAT.find(function (x) { return x.id === id; });
    return u ? u.name : id;
  }

  function assigneeText(m) {
    const ids = assignees[m.id] || [];
    return ids.length ? ids.map(unitLabel).join(", ") : "Не призначено";
  }

  // Поле з чипами, що саме є рядком пошуку; під ним розкривається список із галочками.
  // chosen — масив id, змінюється на місці.
  function multiPick(chosen, label) {
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
          unitLabel(id),
          el("span", { class: "x", role: "button", "aria-label": "Прибрати " + unitLabel(id), title: "Прибрати", text: "×",
            onclick: function (e) { e.stopPropagation(); toggleUnit(id); } }),
        ]));
      });
      input.placeholder = chosen.length ? "Додати ще…" : "Оберіть відділи та підрозділи";
    }

    function toggleUnit(id) {
      const i = chosen.indexOf(id);
      if (i === -1) chosen.push(id); else chosen.splice(i, 1);
      drawChips();
      if (!pop.classList.contains("hidden")) drawList();
    }

    function drawList() {
      const q = input.value.trim().toLowerCase();
      list.innerHTML = "";
      let any = false;
      UNIT_GROUPS.forEach(function (g) {
        const items = UNITS_FLAT.filter(function (u) { return u.group === g[0] && (!q || matches(u.name, q) || matches(u.group, q)); });
        if (!items.length) return;
        any = true;
        list.appendChild(el("div", { class: "mpick-group", text: g[0] }));
        items.forEach(function (u) {
          const box = el("input", { type: "checkbox", value: u.id });
          box.checked = chosen.indexOf(u.id) !== -1;
          box.addEventListener("change", function () { toggleUnit(u.id); });
          list.appendChild(el("label", { class: "dept-item" }, [box, u.name]));
        });
      });
      if (!any) list.appendChild(el("p", { class: "small muted", style: "margin:6px 0", text: "Нічого не знайдено." }));
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
      if (e.key === "Backspace" && !input.value && chosen.length) toggleUnit(chosen[chosen.length - 1]);
    });
    pop.close = function () { setOpen(false); };
    drawChips();
    return el("div", { class: "mpick" }, [field, pop]);
  }

  function closeAllPicks(except) {
    document.querySelectorAll(".mpick-pop").forEach(function (p) { if (p !== except && p.close && !p.classList.contains("hidden")) p.close(); });
  }
  document.addEventListener("click", function (e) { if (!e.target.closest(".mpick")) closeAllPicks(null); });

  // ---------- вікно «Призначити виконавця» ----------
  const assignDialog = document.getElementById("assign-dialog");
  const assignBody = document.getElementById("assign-body");
  const assignSearch = document.getElementById("assign-search");
  const assignMsg = document.getElementById("assign-msg");
  let draft = {}; // чернетка призначень у вікні: measure_id -> [unit id]

  function openAssign() {
    draft = {};
    Object.keys(assignees).forEach(function (k) { draft[k] = assignees[k].slice(); });
    assignSearch.value = "";
    assignMsg.textContent = "";
    assignMsg.className = "msg";
    renderAssign();
    assignDialog.showModal();
  }

  const aOpen = new Set(); // розгорнуті у вікні: p:ID, s:ID:R

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
          if (sOpen) sec.appendChild(el("div", { class: "assign-rows" }, bySec[sid].map(assignRow)));
          body.appendChild(sec);
        });
        node.appendChild(body);
      }
      assignBody.appendChild(node);
    });
    if (!shown) assignBody.appendChild(el("p", { class: "muted", text: q ? "Нічого не знайдено." : "Заходів немає." }));
  }

  function assignRow(m) {
    const chosen = draft[m.id] = draft[m.id] || [];
    return el("div", { class: "assign-row" }, [
      el("div", {}, [
        el("div", {}, [el("span", { class: "num", text: Api.measureNo(m) + " " }), m.description]),
        el("div", { class: "small muted", text: "Виконати до: " + deadlineText(m) }),
      ]),
      multiPick(chosen, "Виконавці заходу " + Api.measureNo(m)),
    ]);
  }

  function saveAssign() {
    Object.keys(draft).forEach(function (k) { assignees[k] = draft[k].slice(); });
    assignDialog.close();
    render();
  }

  if (document.getElementById("assign-open")) {
    document.getElementById("assign-open").addEventListener("click", openAssign);
    document.getElementById("assign-cancel").addEventListener("click", function () { assignDialog.close(); });
    document.getElementById("assign-save").addEventListener("click", saveAssign);
    assignSearch.addEventListener("input", renderAssign);
  }

  function deadlineText(m) {
    if (m.deadline_on) return Api.fmtDate(m.deadline_on);
    if (m.deadline_type === "ongoing") return "Постійно";
    return m.deadline_description || "—";
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
          el("th", { text: "Підрозділ" }), regional ? el("th", { text: "Виконавці" }) : null, el("th", { text: "Виконати до" }), el("th", { text: "Фактично виконано" }),
          el("th", { text: "№ наказу" }),
          el("th", { text: "Примітка" }), el("th", { text: "Статус" }),
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

  // ---------- підрозділи для координації (МАКЕТ) ----------
  // ЗАГЛУШКА: бекенд поки зберігає в програмі лише один coordinator_department_id, а довідник
  // /api/departments доступний тільки адміністратору. Тому список підрозділів вигаданий,
  // а вибір живе лише в пам'яті сторінки й зникає після перезавантаження.
  const UNITS = Object.keys(Api.REGIONAL_UNITS).map(function (id) { return { id: id, name: Api.REGIONAL_UNITS[id] }; });
  const unitsByProgram = {}; // program_id -> [unit id]
  const deptList = document.getElementById("dept-list");
  const deptCount = document.getElementById("dept-count");

  function unitName(id) {
    const u = UNITS.find(function (x) { return x.id === id; });
    return u ? u.name : id;
  }

  function deptSummary(p) {
    const ids = unitsByProgram[p.id] || [];
    if (!ids.length) return el("div", { class: "small muted", text: "Підрозділи для координації не обрано" });
    return el("div", { class: "small", style: "margin-top:2px", text: "Надіслано на координацію: " + ids.map(unitName).join(", ") });
  }

  function checkedUnits() {
    return Array.from(deptList.querySelectorAll("input:checked")).map(function (i) { return i.value; });
  }

  function updateDeptCount() {
    const n = checkedUnits().length;
    deptCount.textContent = n ? "Обрано: " + n + " з " + UNITS.length : "Не обрано";
  }

  function fillUnits(selected) {
    deptList.innerHTML = "";
    UNITS.forEach(function (u) {
      const box = el("input", { type: "checkbox", value: u.id });
      box.checked = selected.indexOf(u.id) !== -1;
      box.addEventListener("change", updateDeptCount);
      deptList.appendChild(el("label", { class: "dept-item" }, [box, u.name]));
    });
    updateDeptCount();
  }

  document.getElementById("dept-all").addEventListener("click", function () {
    const boxes = Array.from(deptList.querySelectorAll("input"));
    const all = boxes.every(function (b) { return b.checked; });
    boxes.forEach(function (b) { b.checked = !all; });
    updateDeptCount();
  });

  // ---------- створення й редагування програми ----------
  // POST /api/programs — нова; PATCH /api/programs/{id} — зміна (код програми не змінюється).
  const APPROVAL = { draft: "Проєкт", approved: "Затверджено" };
  function approvalLabel(v) { return APPROVAL[v] || v; }

  const dialog = document.getElementById("program-dialog");
  const form = document.getElementById("program-form");
  const formErr = document.getElementById("program-error");
  const FIELDS = ["id", "title", "organization_name", "start_date", "end_date", "approval_reference", "approval_status", "goals"];
  let editing = null; // програма, що редагується; null — створення

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
    fillUnits(p ? unitsByProgram[p.id] || [] : []);
    document.getElementById("program-dialog-title").textContent = p ? "Редагування програми " + p.id : "Нова програма";
    document.getElementById("program-submit").textContent = p ? "Зберегти зміни" : "Створити програму";
    dialog.showModal();
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
        unitsByProgram[saved.id] = checkedUnits();
        open.add("p:" + saved.id);
      } else {
        data.notes = "";
        const created = await Api.post("/api/programs", data);
        programs.push(created);
        unitsByProgram[created.id] = checkedUnits();
        open.add("p:" + created.id);
      }
      dialog.close();
      render();
    } catch (err) {
      formErr.textContent = err.message;
      formErr.classList.remove("hidden");
    }
  });

  init();
})();
