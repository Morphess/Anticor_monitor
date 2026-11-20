/* BORDER GROUP — журнал дій у кабінеті адміністратора.
 * API: GET /api/action-logs/feed (сторінки, пошук, фільтри), GET /api/action-logs/facets,
 * довідники /api/users/ і /api/departments. Права перевіряє сервер (лише ADMIN).
 */
(function () {
  "use strict";
  const E = Api.el;
  const UI = window.AdminUI;
  const $ = (id) => document.getElementById(id);
  const PAGE_SIZES = [10, 25, 50, 100];

  const ACTIONS = {
    create: "Створено",
    update: "Змінено",
    delete: "Видалено",
    change_order_number: "Замінено номер наказу",
  };
  const ENTITIES = {
    users: "Користувач",
    departments: "Підрозділ",
    programs: "Програма",
    program_departments: "Направлення програми",
    sections: "Розділ",
    measures: "Захід",
    measure_assignments: "Призначення виконавця",
    measure_collaborators: "Співвиконавець заходу",
    risks: "Корупційний ризик",
    risk_measurements: "Вимірювання ризику",
    executions: "Виконання заходу",
    execution: "Виконання заходу",
    execution_analyses: "Аналіз ШІ",
    orders: "Наказ",
    order_versions: "Версія файла наказу",
    order_change_alerts: "Сповіщення про зміну наказу",
    order_change_alert_reads: "Прочитане сповіщення",
    invalid_order_references: "Неіснуючий номер наказу",
    deadline_changes: "Перенесення строку",
    reports: "Звіт",
    roles: "Роль",
  };
  const FIELDS = {
    status: "Статус", status_label: "Підпис статусу", login: "Логін", role_id: "Роль",
    department_id: "Підрозділ", position: "Посада", password_hash: "Пароль", program_id: "Програма",
    title: "Назва", name: "Назва", description: "Опис", order_id: "Наказ", order_version_id: "Версія наказу",
    number: "Номер", deadline_on: "Строк", deadline_type: "Тип строку", responsible_department_id: "Відповідальний підрозділ",
    rejection_reason: "Причина відхилення", reviewed_by_user_id: "Перевірив", reviewed_at: "Час перевірки",
    submitted_at: "Час подання", approved_by_coordinator: "Погоджено", result_description: "Опис результату",
    completed_on: "Фактична дата", outcome_status: "Стан виконання", order_number: "Номер наказу",
    parent_id: "Батьківський підрозділ", approval_status: "Стан затвердження", goals: "Мета",
    export_file_path: "Файл звіту", generated_at: "Час формування", generated_by_user_id: "Сформував",
    version: "Версія", document_changed: "Документ змінено", submitted_by_user_id: "Подав",
    submitted_department_id: "Підрозділ виконавця", submitted_sha256: "Контрольна сума документа",
    indicator_actual: "Фактичне значення індикатора", issued_on: "Дата наказу", document_url: "Посилання на документ",
  };
  // Службові значення, які варто показати людською мовою.
  const VALUES = {
    pending: "Очікує погодження", approved: "Погоджено", rejected: "Відхилено",
    draft: "Чернетка", generated: "Сформовано", submitted: "Подано",
    completed: "Виконано", partial: "Частково виконано", not_completed: "Не виконано",
    True: "Так", False: "Ні", true: "Так", false: "Ні",
    date: "Конкретна дата", ongoing: "Постійно", recurring: "Періодично",
    "[REDACTED]": "приховано",
  };
  const loginsById = new Map();
  function human(value, field) {
    if (value == null || value === "") return "—";
    const text = String(value);
    // Поля *_user_id → логін користувача замість числового ID.
    if (field && /_user_id$/.test(field) && loginsById.has(text)) return loginsById.get(text) + " (ID " + text + ")";
    if (Object.prototype.hasOwnProperty.call(VALUES, text)) return VALUES[text];
    // Дата-час ISO → місцевий формат
    if (/^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}/.test(text)) return fmtDateTime(text.replace(" ", "T"));
    return text;
  }
  const ROLE_NAMES = {
    ADMIN: "Адміністратор", MAIN_KOORD: "Головний координатор", KOORD: "Координатор підрозділу",
    VYK: "Виконавець", KER: "Керівник",
  };

  const state = { page: 1, size: readSize(25) };
  let loaded = false;
  let seq = 0;
  let timer = null;

  function readSize(fallback) {
    try {
      const v = Number(localStorage.getItem("anticor_admin_size_audit"));
      return PAGE_SIZES.includes(v) ? v : fallback;
    } catch (_) { return fallback; }
  }
  function writeSize(v) { try { localStorage.setItem("anticor_admin_size_audit", String(v)); } catch (_) { /* private mode */ } }
  function refresh(select) { if (UI && UI.refreshSelect) UI.refreshSelect(select); }

  // Час у базі — UTC без часового поясу; показуємо в місцевому часі.
  function parseUtc(value) { return new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(value) ? value : value + "Z"); }
  function two(n) { return (n < 10 ? "0" : "") + n; }
  function fmtDateTime(value) {
    const d = parseUtc(value);
    if (isNaN(d)) return value;
    return two(d.getDate()) + "." + two(d.getMonth() + 1) + "." + d.getFullYear() + " " +
      two(d.getHours()) + ":" + two(d.getMinutes()) + ":" + two(d.getSeconds());
  }
  // Дата з поля (місцева північ) → UTC без часового поясу, як очікує API.
  function toUtcParam(dateStr, endOfDay) {
    if (!dateStr) return null;
    const d = new Date(dateStr + (endOfDay ? "T23:59:59.999" : "T00:00:00"));
    return isNaN(d) ? null : d.toISOString().slice(0, 23);
  }

  function option(value, text) { return E("option", { value: value, text: text }); }

  async function loadDictionaries() {
    const [users, departments, facets] = await Promise.all([
      Api.getAll("/api/users/", 100, "skip").catch(() => []),
      Api.get("/api/departments").catch(() => []),
      Api.get("/api/action-logs/facets").catch(() => ({ actions: [], entity_types: [] })),
    ]);
    const userSel = $("audit-user");
    (users || []).slice().sort((a, b) => String(a.login).localeCompare(String(b.login), "uk"))
      .forEach((u) => {
        loginsById.set(String(u.id), u.login);
        userSel.appendChild(option(String(u.id), u.login + (u.position ? " — " + u.position : "")));
      });
    refresh(userSel);

    const deptSel = $("audit-dept");
    (Array.isArray(departments) ? departments : (departments.items || []))
      .slice().sort((a, b) => String(a.name).localeCompare(String(b.name), "uk"))
      .forEach((d) => deptSel.appendChild(option(d.id, d.name + " (" + d.id + ")")));
    refresh(deptSel);

    const actSel = $("audit-action");
    const actions = new Set(Object.keys(ACTIONS).concat(facets.actions || []));
    actions.forEach((a) => actSel.appendChild(option(a, ACTIONS[a] || a)));
    refresh(actSel);

    const entSel = $("audit-entity");
    (facets.entity_types || []).slice()
      .sort((a, b) => (ENTITIES[a] || a).localeCompare(ENTITIES[b] || b, "uk"))
      .forEach((t) => entSel.appendChild(option(t, ENTITIES[t] ? ENTITIES[t] + " (" + t + ")" : t)));
    refresh(entSel);
  }

  function query() {
    const p = new URLSearchParams({ page: String(state.page), page_size: String(state.size) });
    const q = $("audit-search").value.trim();
    if (q) p.set("q", q);
    [["actor_user_id", "audit-user"], ["department_id", "audit-dept"], ["action", "audit-action"], ["entity_type", "audit-entity"]]
      .forEach(([key, id]) => { const v = $(id).value; if (v) p.set(key, v); });
    const since = toUtcParam($("audit-from").value, false);
    const until = toUtcParam($("audit-to").value, true);
    if (since) p.set("since", since);
    if (until) p.set("until", until);
    return p;
  }

  function actorCell(item) {
    if (!item.actor) {
      return E("td", { "data-label": "Користувач" }, [E("span", { class: "audit-system", text: "Система" })]);
    }
    const a = item.actor;
    const login = E("button", {
      type: "button", class: "audit-link", text: a.login,
      title: "Показати всі дії цього користувача",
      onclick: () => { $("audit-user").value = String(a.id); refresh($("audit-user")); state.page = 1; load(); },
    });
    return E("td", { "data-label": "Користувач" }, [
      login,
      E("div", { class: "audit-sub", text: [ROLE_NAMES[a.role_id] || a.role_id, a.position].filter(Boolean).join(" · ") }),
    ]);
  }

  function deptCell(item) {
    const a = item.actor;
    if (!a || !a.department_id) return E("td", { "data-label": "Підрозділ", class: "muted", text: "—" });
    return E("td", { "data-label": "Підрозділ" }, [
      E("span", { text: a.department_name || a.department_id }),
      E("div", { class: "audit-sub", text: a.department_id }),
    ]);
  }

  function changeCell(item) {
    if (item.action === "create") return E("td", { "data-label": "Що змінено", class: "muted", text: "Створено новий запис" });
    if (item.action === "delete") return E("td", { "data-label": "Що змінено", class: "muted", text: "Запис видалено" });
    const field = item.field_name ? (FIELDS[item.field_name] || item.field_name) : "";
    const old = human(item.old_value, item.field_name);
    const neu = human(item.new_value, item.field_name);
    return E("td", { "data-label": "Що змінено" }, [
      field ? E("div", { class: "audit-field", text: field }) : null,
      E("div", { class: "audit-diff" }, [
        E("span", { class: "audit-old", text: old, title: "Було" }),
        E("span", { class: "audit-arrow", text: " → ", "aria-label": "змінено на" }),
        E("span", { class: "audit-new", text: neu, title: "Стало" }),
      ]),
    ]);
  }

  function render(page) {
    const tbody = $("audit-rows");
    $("audit-count").textContent = page.total
      ? "Знайдено записів: " + page.total
      : "За цими умовами записів немає";
    if (!page.items.length) {
      tbody.replaceChildren(E("tr", {}, [E("td", { colspan: "6", class: "admin-empty-cell" }, [
        E("span", { class: "admin-empty-title", text: "Записів не знайдено" }),
        E("span", { class: "admin-empty-subtitle", text: "Змініть пошук або фільтри й спробуйте ще раз." }),
      ])]));
    } else {
      tbody.replaceChildren(...page.items.map((item) => E("tr", {}, [
        E("td", { "data-label": "Дата і час", class: "audit-time", text: fmtDateTime(item.occurred_at) }),
        actorCell(item),
        deptCell(item),
        E("td", { "data-label": "Дія" }, [
          E("span", { class: "audit-badge audit-" + item.action, text: ACTIONS[item.action] || item.action }),
        ]),
        E("td", { "data-label": "Об'єкт" }, [
          E("span", { text: ENTITIES[item.entity_type] || item.entity_type }),
          E("div", { class: "audit-sub", text: "ID " + item.entity_id }),
        ]),
        changeCell(item),
      ])));
    }
    ["audit-pager-top", "audit-pager"].forEach((id) => Api.renderPager($(id), state, page.total, {
      sizes: PAGE_SIZES, noun: "записів", rerender: load, onSize: writeSize,
    }));
  }

  async function load() {
    const my = ++seq;
    $("audit-count").textContent = "Завантаження журналу…";
    try {
      const page = await Api.get("/api/action-logs/feed?" + query().toString());
      if (my !== seq) return; // відповідь на застарілий запит
      render(page);
    } catch (error) {
      if (my !== seq) return;
      $("audit-count").textContent = "Не вдалося завантажити журнал: " + (error && error.message || "помилка сервера");
      $("audit-rows").replaceChildren();
    }
  }

  function reload() { state.page = 1; load(); }

  $("audit-search").addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(reload, 300); });
  ["audit-user", "audit-dept", "audit-action", "audit-entity", "audit-from", "audit-to"].forEach((id) => {
    $(id).addEventListener("change", reload);
  });
  $("audit-reset").addEventListener("click", () => {
    $("audit-search").value = "";
    ["audit-user", "audit-dept", "audit-action", "audit-entity"].forEach((id) => { $(id).value = ""; refresh($(id)); });
    $("audit-from").value = "";
    $("audit-to").value = "";
    reload();
  });

  // Журнал завантажується лише при першому відкритті вкладки.
  $("tab-audit").addEventListener("click", async () => {
    if (loaded) return;
    loaded = true;
    await loadDictionaries();
    load();
  });
})();
