/* Кабінет VYK. Доступ визначає сервер, не поле measures.assigned_user_id. */
(function () {
  "use strict";
  const el = Api.el;
  const $ = (id) => document.getElementById(id);
  const root = $("programs");
  const search = $("search");
  const filter = $("filter");
  const programFilter = $("executor-program");
  const period = $("period");
  const dialog = $("execution-dialog");
  const form = $("execution-form");
  const saveButton = $("execution-save");
  const formMessage = $("execution-message");
  const openIds = new Set();
  const state = {
    programs: [], byProgram: {}, measures: [], sections: {}, executions: {},
    deadlineReminders: {}, notices: {}, edit: null, loading: false,
  };
  const isApproved = (x) => !!(x && x.status === "approved" && !x.document_changed);
  const canSubmit = (x) => !x || !!x.document_changed || x.status === "rejected";
  const status = (m) => Api.statusOf(state.executions[m.id]);
  const safeList = (x) => Array.isArray(x) ? x : [];
  const getDays = (m) => {
    if (m.deadline_type && m.deadline_type !== "date") return null;
    const reminder = state.deadlineReminders[m.id];
    if (reminder && Number.isFinite(Number(reminder.days_left))) return Number(reminder.days_left);
    return Notify.daysLeft(m);
  };
  function needsAttention(m) {
    const days = getDays(m);
    return !isApproved(state.executions[m.id]) && days !== null && days <= 7;
  }
  function toast(message, kind) {
    const wrap = $("executor-toasts");
    const item = el("div", { class: "executor-toast", "data-kind": kind || "success", role: kind === "error" ? "alert" : "status" }, [
      el("span", { text: message }),
      el("button", { type: "button", "aria-label": "Закрити сповіщення", text: "×", onclick: () => item.remove() }),
    ]);
    wrap.appendChild(item);
    setTimeout(() => item.remove(), kind === "error" ? 6500 : 4200);
  }
  function errorText(err) { return (err && err.message) || "Не вдалося отримати дані"; }
  function noticeError(err) {
    root.innerHTML = "";
    root.appendChild(el("div", { class: "executor-inline-error", text: errorText(err) }));
    root.appendChild(el("button", { type: "button", class: "btn", text: "Спробувати знову", onclick: () => refresh(true) }));
  }
  function textCell(name, value, klass) {
    return el("div", { class: klass || "" }, [
      el("span", { class: "m-label", text: name + ": " }),
      el("span", { text: String(value || "—") }),
    ]);
  }
  function groupBy(list, key) {
    return list.reduce((acc, m) => {
      (acc[m[key]] = acc[m[key]] || []).push(m);
      return acc;
    }, {});
  }
  async function fetchMeasures() {
    // Не використовуємо глобальні /api/programs та /api/measures списки.
    const [assigned, programs] = await Promise.all([
      Api.get("/api/program-routing/my/measures"),
      Api.get("/api/program-routing/my/programs"),
    ]);
    const mine = safeList(assigned);
    const allowedPrograms = new Set(safeList(programs).map((p) => p.id));
    const chosen = mine.filter((m) => allowedPrograms.has(m.program_id));
    // Кожна повна картка заходу запитується ВИКЛЮЧНО за своїм ID.
    // Якщо GET /api/measures/{id} недоступний, показуємо короткі відомості
    // та не вигадуємо ні строків, ні показників.
    const enriched = [];
    for (let i = 0; i < chosen.length; i += 6) {
      const batch = chosen.slice(i, i + 6);
      const detail = await Promise.all(batch.map(async (m) => {
        try {
          const full = await Api.get("/api/measures/" + encodeURIComponent(m.id), { noRedirect: true });
          return Object.assign({}, m, full && full.id === m.id ? full : {});
        } catch (err) {
          if (err.status === 401) throw err;
          return m;
        }
      }));
      enriched.push(...detail);
    }
    const actualPrograms = safeList(programs).filter((p) => enriched.some((m) => m.program_id === p.id));
    const meta = await Promise.all(actualPrograms.map(async (p) => {
      let full = {}, sec = [];
      try { full = await Api.get("/api/program-routing/programs/" + encodeURIComponent(p.id), { noRedirect: true }); }
      catch (err) { if (err.status === 401) throw err; }
      try { sec = await Api.get("/api/program-routing/programs/" + encodeURIComponent(p.id) + "/sections", { noRedirect: true }); }
      catch (err) { if (err.status === 401) throw err; }
      return { program: Object.assign({}, p, full || {}), sections: safeList(sec) };
    }));
    state.programs = meta.map((x) => x.program);
    state.sections = {};
    meta.forEach((x) => x.sections.forEach((s) => { state.sections[s.id] = s; }));
    state.measures = enriched.sort(Api.byMeasureOrder);
    state.byProgram = groupBy(state.measures, "program_id");
    state.programs.sort((a, b) => String(a.title || a.id).localeCompare(String(b.title || b.id), "uk"));
    programFilter.innerHTML = "";
    programFilter.appendChild(el("option", { value: "", text: "Усі мої програми" }));
    state.programs.forEach((p) => programFilter.appendChild(el("option", { value: p.id, text: p.title || p.id })));
    Api.fillPeriods(period, state.programs);
    if (state.programs.length === 1) openIds.add("p:" + state.programs[0].id);
    if (state.measures.length === 1) openIds.add("s:" + state.measures[0].program_id + ":" + state.measures[0].section_id);
  }
  async function fetchReportData() {
    const [execs, deadlineResult] = await Promise.all([
      Api.executions(period.value),
      // Нагадування з сервера — додатковий, необов'язковий модуль.
      // За відсутності API працює локальна індикація за датою з картки заходу.
      Api.optional(Api.get("/api/deadline-reminders/?limit=100&offset=0", { noRedirect: true })),
    ]);
    const mineIds = new Set(state.measures.map((m) => m.id));
    state.executions = {};
    safeList(execs).forEach((x) => {
      if (mineIds.has(x.measure_id) && String(x.submitted_by_user_id) === String(Api.me.id)) state.executions[x.measure_id] = x;
    });
    state.deadlineReminders = {};
    if (deadlineResult.ok && deadlineResult.data && Array.isArray(deadlineResult.data.reminders)) {
      safeList(deadlineResult.data.reminders).forEach((reminder) => {
        if (mineIds.has(reminder.measure_id)) state.deadlineReminders[reminder.measure_id] = reminder;
      });
    }

  }
  function contextInfo() {
    const me = Api.me || {};
    const box = $("ident");
    box.textContent = [me.department_id || "", me.position || ""].filter(Boolean).join(" · ") || me.login || "Виконавець";
    box.title = box.textContent;
  }
  async function refresh(full) {
    if (state.loading) return;
    state.loading = true;
    const button = $("executor-refresh");
    button.disabled = true;
    button.textContent = "Оновлення…";
    root.setAttribute("aria-busy", "true");
    try {
      if (full || !state.programs.length) await fetchMeasures();
      await fetchReportData();
      render();
      if (full) toast("Дані кабінету оновлено");
    } catch (err) {
      noticeError(err);
      toast(errorText(err), "error");
    } finally {
      state.loading = false;
      root.setAttribute("aria-busy", "false");
      button.disabled = false;
      button.textContent = "Оновити дані";
    }
  }
  function matches(m, p, q) {
    const sec = state.sections[m.section_id];
    const ev = state.executions[m.id];
    return [p.id, p.title, m.id, m.description, m.sequence_number,
      sec && sec.title, ev && ev.order_number].some((v) => String(v || "").toLocaleLowerCase("uk").includes(q));
  }
  function matchesFilter(m, f) {
    if (!f) return true;
    const ex = state.executions[m.id];
    if (f === "todo") return !ex;
    if (f === "deadline") return needsAttention(m);
    if (f === "work") return !!ex && ex.status === "in_progress";
    return status(m) === f;
  }
  function updateCounters() {
    const all = state.measures;
    const counts = {
      "executor-total": all.length,
      "executor-attention": all.filter(needsAttention).length,
      "executor-review": all.filter((m) => status(m) === "review").length,
      "executor-approved": all.filter((m) => isApproved(state.executions[m.id])).length,
    };
    Object.entries(counts).forEach(([id, number]) => { $(id).textContent = String(number); });
    $("executor-program-count").textContent = state.programs.length + " програм";
    document.querySelectorAll(".executor-stat[data-stat-filter]").forEach((button) => {
      button.setAttribute("aria-pressed", String(button.dataset.statFilter === filter.value));
    });
  }
  function empty(title, hint, reset) {
    const content = el("div", { class: "executor-empty" }, [
      el("h3", { text: title }), el("p", { text: hint }),
    ]);
    if (reset) content.appendChild(el("button", {
      type: "button", class: "btn", style: "margin-top:12px", text: "Скинути фільтри",
      onclick: () => { search.value = ""; filter.value = ""; programFilter.value = ""; render(); },
    }));
    return content;
  }
  function render() {
    updateCounters();
    root.innerHTML = "";
    const q = search.value.trim().toLocaleLowerCase("uk");
    const f = filter.value;
    const pId = programFilter.value;
    const active = !!(q || f || pId);
    if (!state.measures.length) {
      root.appendChild(empty("Поки немає призначених заходів", "Координатор підрозділу призначає заходи через кабінет KOORD.", false));
      $("executor-result-count").textContent = "0 заходів";
      Notify.render([], "Немає термінових повідомлень");
      return;
    }
    let totalShown = 0;
    state.programs.forEach((p) => {
      if (pId && p.id !== pId) return;
      const all = state.byProgram[p.id] || [];
      const shown = all.filter((m) => matchesFilter(m, f) && (!q || matches(m, p, q)));
      if (!shown.length) return;
      totalShown += shown.length;
      root.appendChild(programNode(p, all, shown, active));
    });
    $("executor-result-count").textContent = "Показано " + totalShown + " із " + state.measures.length;
    if (!totalShown) root.appendChild(empty("Заходів не знайдено", "Спробуйте інший пошуковий запит або фільтр.", true));
    renderNotifications();
  }
  function toggle(key) { openIds.has(key) ? openIds.delete(key) : openIds.add(key); render(); }
  function counter(ms) {
    const completed = ms.filter((m) => isApproved(state.executions[m.id])).length;
    return el("span", { class: "count", text: "Погоджено " + completed + " / " + ms.length });
  }
  function programNode(p, all, shown, active) {
    const key = "p:" + p.id;
    const visible = active || openIds.has(key);
    const node = el("article", { class: "prog" }, [
      el("button", { type: "button", class: "row-head", "aria-expanded": String(visible), onclick: () => toggle(key) }, [
        el("span", { class: "title" }, [el("span", { class: "code", text: p.id }), p.title || p.id,
          p.organization_name ? el("span", { class: "sub", text: p.organization_name }) : null]),
        counter(all),
      ]),
    ]);
    if (!visible) return node;
    const body = el("div", { class: "prog-body" });
    const groups = groupBy(shown, "section_id");
    Object.keys(groups).sort(Api.compareSections).forEach((sid) => {
      body.appendChild(sectionNode(p, sid, all.filter((m) => m.section_id === sid), groups[sid], active));
    });
    node.appendChild(body);
    return node;
  }
  function sectionNode(p, sid, all, shown, active) {
    const key = "s:" + p.id + ":" + sid;
    const visible = active || openIds.has(key);
    const node = el("section", { class: "sec" }, [
      el("button", { type: "button", class: "row-head", "aria-expanded": String(visible), onclick: () => toggle(key) }, [
        el("span", { class: "title", text: Api.sectionTitle(state.sections, sid) }), counter(all),
      ]),
    ]);
    if (!visible) return node;
    node.appendChild(el("div", { class: "mrow head", "aria-hidden": "true" }, [
      el("span", { text: "Захід" }), el("span", { text: "Контрольний строк" }),
      el("span", { text: "Підтвердження" }), el("span", { text: "Виконання" }),
    ]));
    shown.forEach((m) => node.appendChild(measureRow(m)));
    return node;
  }
  function deadlineText(m) {
    if (m.deadline_on) return Api.fmtDate(m.deadline_on);
    if (m.deadline_type === "ongoing") return "Постійно";
    return m.deadline_description || "Не вказано";
  }
  function deadlineChip(m) {
    const d = getDays(m);
    if (d === null || isApproved(state.executions[m.id])) return null;
    if (d < 0) return el("span", { class: "chip late", text: "Прострочено на " + (-d) + " дн." });
    if (d === 0) return el("span", { class: "chip soon", text: "Строк сьогодні" });
    if (d <= 3) return el("span", { class: "chip soon", text: "Залишилося " + d + " дн. · D3" });
    if (d <= 7) return el("span", { class: "chip soon", text: "Залишилося " + d + " дн. · D7" });
    return null;
  }
  function measureRow(m) {
    const ex = state.executions[m.id];
    const ev = state.executions[m.id];
    const st = status(m);
    const done = isApproved(ex);
    const statusText = done ? "Погоджено координатором. Редагування заблоковане." :
      st === "review" ? "Результат подано, очікується перевірка KOORD." :
      st === "rework" ? "Перевірте зауваження координатора та уточніть результат." :
      ex ? "Результат можна уточнити до погодження." : "Звіт ще не подано.";
    const info = el("div", {}, [
      el("div", { class: "executor-measure-name" }, [
        el("span", { class: "num", text: Api.measureNo(m) }), document.createTextNode(m.description || m.id),
      ]),
      el("div", { class: "executor-measure-meta" }, [
        el("span", { text: "Код: " + m.id }),
        m.completion_indicator ? el("span", { text: "Очікуваний результат: " + m.completion_indicator }) : null,
      ]),
    ]);
    const deadline = el("div", {}, [textCell("Строк", deadlineText(m), "executor-deadline-label"), deadlineChip(m)]);
    const evidence = el("div", {}, [
      el("span", { class: "m-label", text: "Наказ: " }),
      el("span", { class: "executor-evidence-label", text: ev ? "№ " + ev.order_number : "Ще не подано" }),
      ex && ex.document_changed ? el("div", { class: "chip soon", text: "Наказ оновлено — перевірте" }) : null,
    ]);
    const action = el("div", {}, [
      Api.statusBadge(st), el("span", { class: "executor-status-hint", text: statusText }),
      canSubmit(ex) ? el("button", { type: "button", class: "btn", text: ex ? "Уточнити виконання" : "Внести виконання", onclick: () => openForm(m) }) : null,
      state.notices[m.id] ? el("div", { class: "msg", text: state.notices[m.id] }) : null,
    ]);
    return el("div", { class: "mrow", id: "executor-measure-" + m.id }, [info, deadline, evidence, action]);
  }
  function renderNotifications() {
    const notices = [];
    state.measures.forEach((m) => {
      if (isApproved(state.executions[m.id])) return;
      const ex = state.executions[m.id];
      const st = status(m);
      const p = state.programs.find((p) => p.id === m.program_id);
      const which = (p ? p.title : m.program_id) + " · " + m.id;
      const go = () => {
        search.value = ""; filter.value = ""; programFilter.value = "";
        openIds.add("p:" + m.program_id); openIds.add("s:" + m.program_id + ":" + m.section_id);
        render(); const row = $("executor-measure-" + m.id); if (row) Notify.flash(row);
      };
      if (st === "rework") notices.push({ lvl: "rework", rank: 1, what: "Потрібне доопрацювання", which, go });
      if (st === "review") return;
      const d = getDays(m);
      if (d === null) return;
      if (d < 0) notices.push({ lvl: "late", rank: 0, what: "Прострочення: " + (-d) + " днів", which, go });
      else if (d <= 7) notices.push({ lvl: "soon", rank: 2, what: d === 0 ? "Строк спливає сьогодні" : "До строку: " + d + " днів", which, go });
    });
    notices.sort((a, b) => a.rank - b.rank);
    Notify.render(notices, "Немає заходів із терміновими нагадуваннями.");
  }
  function formError(text) {
    formMessage.textContent = text;
    formMessage.className = "msg err";
  }
  function openForm(m) {
    if (!canSubmit(state.executions[m.id])) return;
    state.edit = m;
    state.editPeriod = period.value;
    const ex = state.executions[m.id];
    const p = state.programs.find((x) => x.id === m.program_id);
    form.reset();
    $("execution-title").textContent = "Захід " + Api.measureNo(m);
    $("execution-context").textContent = (p ? p.title : m.program_id) + " · " + Api.sectionTitle(state.sections, m.section_id) + " · " + Api.periodLabel(period.value);
    $("execution-description").textContent = m.description || m.id;
    $("execution-deadline").textContent = deadlineText(m);
    $("execution-target").textContent = m.indicator_target !== null && m.indicator_target !== undefined ?
      String(m.indicator_target) + (m.indicator_unit ? " " + m.indicator_unit : "") : m.completion_indicator || "Не визначено";
    const required = String(m.required_evidence || "").trim();
    $("execution-evidence-req").hidden = !required;
    $("execution-evidence-text").textContent = required;
    form.elements.order_number.value = ex && ex.order_number || "";
    formMessage.textContent = "";
    formMessage.className = "msg";
    saveButton.textContent = ex ? "Надіслати повторно" : "Надіслати на перевірку";
    dialog.showModal();
  }
  async function submit(event) {
    event.preventDefault();
    const m = state.edit;
    if (!m || saveButton.disabled) return;
    const prev = state.executions[m.id];
    if (!canSubmit(prev)) {
      formError("Подання вже очікує рішення або погоджене. Оновіть дані.");
      return;
    }
    if (!form.reportValidity()) return;
    const number = form.elements.order_number.value.trim();
    if (!number) { formError("Укажіть номер зареєстрованого наказу."); return; }
    const body = { measure_id: m.id, period: state.editPeriod, order_number: number };
    saveButton.disabled = true;
    saveButton.textContent = "Надсилання…";
    formMessage.textContent = "";
    try {
      state.executions[m.id] = await Api.post("/api/executions/submit", body);
      dialog.close();
      toast("Виконання подано. Очікуйте рішення координатора.");
      await refresh(false);
    } catch (err) {
      formError("Не вдалося подати виконання: " + errorText(err));
    } finally {
      saveButton.disabled = false;
      saveButton.textContent = prev ? "Надіслати повторно" : "Надіслати на перевірку";
    }
  }
  async function init() {
    if (!await Api.requireRole("VYK")) return;
    contextInfo();
    await refresh(false);
  }
  search.addEventListener("input", render);
  filter.addEventListener("change", render);
  programFilter.addEventListener("change", render);
  period.addEventListener("change", () => refresh(false));
  $("executor-refresh").addEventListener("click", () => refresh(true));
  document.querySelectorAll(".executor-stat[data-stat-filter]").forEach((b) => {
    b.addEventListener("click", () => { filter.value = b.dataset.statFilter; render(); $("executor-list-title").scrollIntoView({ behavior: "smooth", block: "start" }); });
  });
  form.addEventListener("submit", submit);
  $("execution-close").addEventListener("click", () => dialog.close());
  $("execution-cancel").addEventListener("click", () => dialog.close());
  dialog.addEventListener("close", () => { state.edit = null; });
  init();
})();
