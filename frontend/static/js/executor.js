// Кабінет виконавця: програма → розділ → заходи, лише заходи, закріплені за користувачем.
// У рядку заходу — номер наказу: перевірка за реєстром /api/orders,
// після успіху звіт іде координатору через /api/executions.
(function () {
  "use strict";
  const el = Api.el;
  const root = document.getElementById("programs");
  const periodSel = document.getElementById("period");
  const search = document.getElementById("search");
  const filterSel = document.getElementById("filter");

  let programs = [];
  let measuresByProg = {}; // лише заходи цього користувача
  let sections = {};
  let executions = {};     // measure_id -> звіт за обраний період
  let ordersByMeasure = {};
  let ordersOk = true;
  const open = new Set();  // розгорнуті вузли: p:ID, s:ID:R
  const msgs = {};         // measure_id -> {ok, text} останньої спроби подання

  async function init() {
    if (!await Api.requireRole("VYK")) return;
    showIdent(Api.me);
    try {
      const [progList, ms, secs, orders] = await Promise.all([
        Api.get("/api/programs"), Api.measures(), Api.sections(), Api.optional(Api.orders()),
      ]);
      sections = secs;
      ordersOk = orders.ok;
      ordersByMeasure = Api.groupBy(orders.data, "measure_id");

      // Виконавець бачить тільки свої заходи (assigned_user_id), чужі не показуються.
      const me = Api.userId();
      const mine = ms.filter(function (m) { return me !== null && m.assigned_user_id === me; }).sort(Api.byMeasureOrder);
      measuresByProg = Api.groupBy(mine, "program_id");
      programs = progList.filter(function (p) { return measuresByProg[p.id]; });
      if (programs.length === 1) open.add("p:" + programs[0].id);

      Api.fillPeriods(periodSel, progList);
      periodSel.addEventListener("change", load);
      search.addEventListener("input", render);
      filterSel.addEventListener("change", render);
      await load();
    } catch (err) {
      Api.showError(err);
      root.innerHTML = "";
    }
  }

  // «Підрозділ — посада» у верхній панелі.
  function showIdent(me) {
    const box = document.getElementById("ident");
    if (!box || !me) return;
    const parts = [me.department_id ? Api.deptName(me.department_id) : "", (me.position || "").trim()].filter(Boolean);
    box.textContent = parts.join(" — ") || me.login;
    box.title = box.textContent;
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

  // ---------- пошук і фільтр ----------

  function matches(text, q) { return (text || "").toLowerCase().indexOf(q) !== -1; }

  function measureMatches(m, q) {
    return matches(m.description, q) || matches(Api.measureNo(m), q) || matches(m.id, q) ||
      matches(Api.sectionTitle(sections, m.section_id), q) || matches(Api.orderNumber(executions[m.id]), q) ||
      (ordersByMeasure[m.id] || []).some(function (o) { return matches(o.number, q) || matches(o.title, q); });
  }

  const daysLeft = Notify.daysLeft;

  function passesFilter(m, f) {
    if (!f) return true;
    const ex = executions[m.id];
    const st = Api.statusOf(ex);
    if (f === "todo") return st !== "done" && st !== "review";
    if (f === "deadline") { const d = daysLeft(m); return d !== null && d <= 30 && !(ex && ex.approved_by_coordinator); }
    return st === f;
  }

  // ---------- дерево ----------

  function toggle(key) { open.has(key) ? open.delete(key) : open.add(key); render(); }

  function isDone(m) { return Api.statusOf(executions[m.id]) === "done"; }

  // «Виконано 7 / 10».
  function counter(list) {
    const done = list.filter(isDone).length;
    return el("div", { class: "count", text: "Виконано " + done + " / " + list.length });
  }

  function render() {
    renderNotifs();
    const q = search.value.trim().toLowerCase();
    const f = filterSel.value;
    const narrowed = !!(q || f);
    root.innerHTML = "";
    if (!programs.length) {
      root.appendChild(el("p", { class: "muted", text: "За вами не закріплено заходів." }));
      return;
    }
    let shown = 0;
    programs.forEach(function (p) {
      const all = measuresByProg[p.id] || [];
      const progHit = !!q && (matches(p.title, q) || matches(p.id, q) || matches(p.organization_name, q));
      const list = all.filter(function (m) {
        return passesFilter(m, f) && (!q || progHit || measureMatches(m, q));
      });
      if (narrowed && !list.length) return;
      shown++;
      root.appendChild(programNode(p, all, list, narrowed));
    });
    if (!shown) root.appendChild(el("p", { class: "muted", text: "Нічого не знайдено." }));
  }

  // Програма: код, назва, орган, що видав.
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
        el("span"),
        counter(all),
      ]),
    ]);
    if (!isOpen) return node;
    const body = el("div", { class: "prog-body" });
    const bySec = Api.groupBy(list, "section_id");
    Object.keys(bySec).sort(Api.compareSections).forEach(function (sid) {
      body.appendChild(sectionNode(p, sid, all.filter(function (m) { return m.section_id === sid; }), bySec[sid], forceOpen));
    });
    node.appendChild(body);
    return node;
  }

  // Розділ: назва і «Виконано X / Y» за всіма заходами розділу; розгорнутий — рядки заходів.
  function sectionNode(p, sid, all, list, forceOpen) {
    const key = "s:" + p.id + ":" + sid;
    const isOpen = forceOpen || open.has(key);
    const node = el("div", { class: "sec" }, [
      el("button", { type: "button", class: "row-head", "aria-expanded": String(isOpen), onclick: function () { toggle(key); } }, [
        el("span", { class: "title", text: Api.sectionTitle(sections, sid) }),
        el("span"),
        counter(all),
      ]),
    ]);
    if (!isOpen) return node;
    node.appendChild(el("div", { class: "mrow head", "aria-hidden": "true" }, [
      el("span", { text: "Захід" }), el("span", { text: "Термін виконання" }),
      el("span", { text: "№ наказу" }), el("span", { text: "Статус" }),
    ]));
    list.forEach(function (m) { node.appendChild(measureRow(m)); });
    return node;
  }

  // Нагадування про строк: прострочено або менше 30 днів (для непогоджених).
  function deadlineChip(m) {
    const ex = executions[m.id];
    const d = daysLeft(m);
    if (d === null || (ex && ex.approved_by_coordinator)) return null;
    if (d < 0) return el("span", { class: "chip late", text: "прострочено " + -d + " дн." });
    if (d <= 30) return el("span", { class: "chip soon", text: "ще " + d + " дн." });
    return null;
  }

  function endDate(m) {
    if (m.deadline_on) return Api.fmtDate(m.deadline_on);
    if (m.deadline_type === "ongoing") return "Постійно";
    return m.deadline_description || "—";
  }

  // Захід: назва | термін виконання | поле наказу | статус.
  function measureRow(m) {
    return el("div", { class: "mrow", id: "row-" + m.id }, [
      el("div", {}, [el("span", { class: "num", text: Api.measureNo(m) }), m.description]),
      el("div", { class: "nowrap" }, [el("div", { text: endDate(m) }), deadlineChip(m)]),
      orderField(m),
      el("div", {}, [Api.statusBadge(Api.statusOf(executions[m.id]))]),
    ]);
  }

  function orderField(m) {
    const ex = executions[m.id];
    const input = el("input", {
      class: "order-input", value: Api.orderNumber(ex), placeholder: "№ наказу і Enter",
      "aria-label": "Номер наказу для заходу " + Api.measureNo(m), "aria-describedby": "msg-" + m.id,
    });
    const msg = el("div", { id: "msg-" + m.id, class: "msg", role: "status" });
    const last = msgs[m.id];
    if (last) {
      input.className = "order-input " + (last.ok ? "ok" : "err");
      msg.className = "msg " + (last.ok ? "ok" : "err");
      msg.textContent = last.text;
    }
    if (ex && ex.approved_by_coordinator) {
      input.readOnly = true;
      input.title = "Погоджено координатором — зміни недоступні";
    }
    input.addEventListener("input", function () { delete msgs[m.id]; input.className = "order-input"; msg.textContent = ""; msg.className = "msg"; });
    input.addEventListener("keydown", function (e) {
      if (e.key !== "Enter") return;
      e.preventDefault();
      submit(m, input);
    });
    const order = Api.findOrder(ordersByMeasure[m.id], Api.orderNumber(ex));
    return el("div", {}, [
      input,
      msg,
      order ? el("div", { class: "order-title" }, [Api.docLink(order.document_url, order.title)]) : null,
    ]);
  }

  // ---------- сповіщення (дзвіночок) ----------

  // Що потребує уваги за обраний період: прострочено, строк ≤ 30 днів, повернуто на доопрацювання.
  // Заходи, уже подані на розгляд або виконані, не турбують.
  function renderNotifs() {
    const out = [];
    programs.forEach(function (p) {
      (measuresByProg[p.id] || []).forEach(function (m) {
        const st = Api.statusOf(executions[m.id]);
        if (st === "done" || st === "review") return;
        const which = p.id + " · " + Api.measureNo(m) + " " + m.description;
        const go = function () { goTo(p, m); };
        if (st === "rework") out.push({ lvl: "rework", rank: 1, what: "Повернуто на доопрацювання", which: which, go: go });
        const d = daysLeft(m);
        if (d === null) return;
        if (d < 0) out.push({ lvl: "late", rank: 0, days: d, what: "Прострочено на " + -d + " дн.", which: which, go: go });
        else if (d <= 30) out.push({ lvl: "soon", rank: 2, days: d, what: d === 0 ? "Строк спливає сьогодні" : "Строк спливає через " + d + " дн.", which: which, go: go });
      });
    });
    out.sort(function (a, b) { return a.rank - b.rank || (a.days || 0) - (b.days || 0); });
    Notify.render(out, "Усе гаразд — термінових справ немає.");
  }

  // Перехід до заходу зі сповіщення: скинути пошук і фільтр, розгорнути гілку, підсвітити рядок.
  function goTo(p, m) {
    search.value = "";
    filterSel.value = "";
    open.add("p:" + p.id);
    open.add("s:" + p.id + ":" + m.section_id);
    render();
    const row = document.getElementById("row-" + m.id);
    Notify.flash(row);
    const input = row && row.querySelector("input");
    if (input) input.focus({ preventScroll: true });
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

  function fail(m, text) { msgs[m.id] = { ok: false, text: text }; render(); }

  async function submit(m, input) {
    const number = input.value.replace(/^№\s*/, "").trim();
    const period = periodSel.value;
    const ex = executions[m.id];
    if (ex && ex.approved_by_coordinator) return fail(m, "Уже погоджено координатором — зміни недоступні");
    const problem = check(m, number);
    if (problem) return fail(m, problem);

    const order = Api.findOrder(ordersByMeasure[m.id], number);
    input.disabled = true;
    try {
      const fields = {
        status: "completed",
        status_label: "На розгляді",
        completed_on: Api.today(),
        result_description: Api.withOrder(ex ? ex.result_description : "", order.number),
      };
      executions[m.id] = ex
        ? await Api.patch(Api.executionUrl(m.id, period), fields)
        : await Api.post("/api/executions/", Object.assign({ measure_id: m.id, period: period }, fields));
      msgs[m.id] = { ok: true, text: "Успіх — звіт передано координатору" };
      render();
    } catch (err) {
      input.disabled = false;
      fail(m, "Помилка: " + err.message);
    }
  }

  init();
})();
