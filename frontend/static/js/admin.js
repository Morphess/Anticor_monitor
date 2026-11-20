/* BORDER GROUP — ADMIN UX refresh.
 * API contract unchanged: /api/users/, /api/departments/.
 * No trust boundary moved to the browser: server must enforce permissions.
 */
(function () {
  "use strict";
  const E = Api.el;
  const UI = window.AdminUI;
  if (!UI) throw new Error("AdminUI не підключено. Перевір admin-widgets.js");
  UI.initSelects(document);

  const $ = (id) => document.getElementById(id);
  const ROLE_NAMES = {
    ADMIN: "Адміністратор", MAIN_KOORD: "Головний координатор", KOORD: "Координатор підрозділу",
    VYK: "Виконавець", KER: "Керівник", ANAL: "Аналітик",
  };
  const ROLES_NEED_DEPARTMENT = new Set(["KOORD", "VYK", "KER"]);
  const PAGE_SIZES = [10, 25, 50, 100];
  const userPage = { page: 1, size: readSize("users", 25) };
  const deptPage = { page: 1, size: readSize("departments", 25) };
  const expanded = new Set();
  let users = [];
  let departments = [];
  let editingUserId = null;
  let editingDeptId = null;
  let deptMode = readPreference("anticor_admin_dept_view", "table") === "tree" ? "tree" : "table";
  let usersLoaded = false;
  let departmentsLoaded = false;
  let departmentInitialized = false;

  function readPreference(k, fallback) { try { return localStorage.getItem(k) || fallback; } catch (_) { return fallback; } }
  function writePreference(k, v) { try { localStorage.setItem(k, String(v)); } catch (_) { /* private mode */ } }
  function readSize(key, fallback) {
    const value = Number(readPreference("anticor_admin_size_" + key, fallback));
    return PAGE_SIZES.includes(value) ? value : fallback;
  }
  function notify(message, kind) { UI.toast(String(message), kind || "success"); }
  function failure(error) { notify(error && error.message ? error.message : "Сервер не відповідає.", "danger"); }
  function norm(value) { return String(value == null ? "" : value).toLocaleLowerCase("uk"); }
  function matchFields(values, query) {
    if (!query) return true;
    const haystack = values.map(norm).join(" ");
    return norm(query).split(/\s+/).filter(Boolean).every((part) => haystack.includes(part));
  }
  function deptName(id) { const d = departments.find((x) => x.id === id); return d ? d.name : id; }
  function roleName(role) { return (Api.ROLES && Api.ROLES[role] && Api.ROLES[role].name) || ROLE_NAMES[role] || role; }
  function pager(id, state, count, key, render) {
    Api.renderPager($(id), state, count, {
      sizes: PAGE_SIZES,
      rerender: render,
      onSize: (value) => writePreference("anticor_admin_size_" + key, value),
    });
  }
  function textNode(value, className) { return E("span", { class: className || "", text: String(value) }); }
  function cell(label, child, className) {
    return E("td", { "data-label": label, class: className || "" }, [
      typeof child === "string" ? textNode(child) : child,
    ]);
  }
  function emptyRow(tbody, count, message) {
    tbody.replaceChildren(E("tr", {}, [E("td", { colspan: String(count), class: "admin-empty-cell" }, [
      E("span", { class: "admin-empty-title", text: message }),
      E("span", { class: "admin-empty-subtitle", text: "Змініть пошук або фільтри й спробуйте ще раз." }),
    ])]));
  }
  function userIsMe(id) { return Number(Api.userId()) === Number(id); }

  // ---------- Compact tables ----------
  function filteredUsers() {
    const query = $("user-search").value.trim();
    const role = $("user-role-filter").value;
    const departmentId = $("user-dept-filter").value;
    return users.filter((user) => {
      if (role && user.role_id !== role) return false;
      if (departmentId === "-" && user.department_id) return false;
      if (departmentId && departmentId !== "-" && user.department_id !== departmentId) return false;
      return matchFields([
        user.id, user.login, user.role_id, roleName(user.role_id),
        user.department_id, deptName(user.department_id), user.position, user.program_id,
      ], query);
    });
  }
  function actionButtons(onEdit, onDelete, deleteDisabled, title) {
    return E("div", { class: "admin-row-actions" }, [
      E("button", { type: "button", class: "btn admin-edit-btn", text: "Змінити", onclick: onEdit }),
      E("button", {
        type: "button", class: "btn admin-delete-btn", text: "Видалити",
        disabled: Boolean(deleteDisabled),
        title: deleteDisabled ? "Не можна видаляти власний обліковий запис" : title,
        onclick: onDelete,
      }),
    ]);
  }
  function renderUsers() {
    const all = filteredUsers();
    $("users-count").textContent = usersLoaded ? "Знайдено: " + all.length + " з " + users.length : "Завантаження користувачів…";
    ["user-pager-top", "user-pager"].forEach((id) => pager(id, userPage, all.length, "users", renderUsers));
    const tbody = $("users");
    tbody.replaceChildren();
    if (!usersLoaded) { emptyRow(tbody, 6, "Завантаження користувачів…"); return; }
    const start = (userPage.page - 1) * userPage.size;
    const matches = all.slice(start, start + userPage.size);
    if (!matches.length) { emptyRow(tbody, 6, users.length ? "За цими умовами користувачів немає" : "Користувачів ще немає"); return; }
    matches.forEach((user) => {
      tbody.appendChild(E("tr", { "data-user-id": String(user.id) }, [
        cell("ID", "#" + user.id, "admin-id-cell"),
        cell("Логін", textNode(user.login, "admin-strong")),
        cell("Роль", textNode(roleName(user.role_id), "admin-strong")),
        cell("Підрозділ", user.department_id ? (deptName(user.department_id) + " (" + user.department_id + ")") : "—"),
        cell("Посада", user.position || "—", "admin-position-cell"),
        cell("Дії", actionButtons(
          () => openUserEditor(user), () => deleteUser(user), userIsMe(user.id), "Видалити " + user.login,
        ), "admin-actions-cell"),
      ]));
    });
  }
  async function loadUsers() {
    users = await Api.getAll("/api/users/", 100, "skip");
    usersLoaded = true;
    renderUsers();
  }

  function filteredDepartments() {
    const query = $("department-search").value.trim();
    const type = $("department-type-filter").value;
    return departments.filter((d) => (!type || d.department_type === type) && matchFields([
      d.id, d.name, d.department_type, d.notes, d.parent_id, d.parent_id ? deptName(d.parent_id) : "Верхній рівень",
    ], query));
  }
  function renderDepartmentTable() {
    const all = filteredDepartments();
    ["department-pager-top", "department-pager"].forEach((id) => pager(id, deptPage, all.length, "departments", renderDepartmentTable));
    const tbody = $("departments");
    tbody.replaceChildren();
    if (!departmentsLoaded) { emptyRow(tbody, 6, "Завантаження підрозділів…"); return; }
    const matches = all.slice((deptPage.page - 1) * deptPage.size, deptPage.page * deptPage.size);
    if (!matches.length) { emptyRow(tbody, 6, departments.length ? "Підрозділів за запитом не знайдено" : "Підрозділів ще немає"); return; }
    matches.forEach((d) => {
      tbody.appendChild(E("tr", { "data-department-id": d.id }, [
        cell("Код", d.id, "admin-id-cell"),
        cell("Назва", textNode(d.name, "admin-strong")),
        cell("Тип", d.department_type),
        cell("Підпорядкованість", d.parent_id ? deptName(d.parent_id) : "Верхній рівень"),
        cell("Примітки", d.notes || "—", "admin-notes-cell"),
        cell("Дії", actionButtons(() => openDeptEditor(d), () => deleteDepartment(d), false, "Видалити " + d.id), "admin-actions-cell"),
      ]));
    });
  }

  // ---------- Department tree (rendered from the already-authorized GET /api/departments/) ----------
  function renderDepartmentTree() {
    const container = $("department-tree");
    container.replaceChildren();
    if (!departmentsLoaded) {
      container.appendChild(E("p", { class: "admin-tree-empty", text: "Завантаження підрозділів…" }));
      return;
    }
    const filtered = filteredDepartments();
    const searchActive = Boolean($("department-search").value.trim() || $("department-type-filter").value);
    const byId = new Map(departments.map((d) => [d.id, d]));
    const children = new Map();
    for (const d of departments) {
      const parent = byId.has(d.parent_id) && d.parent_id !== d.id ? d.parent_id : null;
      const bucket = children.get(parent) || [];
      bucket.push(d);
      children.set(parent, bucket);
    }
    for (const arr of children.values()) arr.sort((a, b) => a.name.localeCompare(b.name, "uk"));
    const visible = new Set();
    if (searchActive) {
      for (const d of filtered) {
        let current = d;
        const seen = new Set();
        while (current && !seen.has(current.id)) {
          seen.add(current.id);
          visible.add(current.id);
          current = byId.get(current.parent_id);
        }
      }
    }
    const rendered = new Set();
    function walk(d, depth) {
      if (rendered.has(d.id) || (searchActive && !visible.has(d.id))) return;
      rendered.add(d.id);
      const childList = (children.get(d.id) || []).filter((child) => !searchActive || visible.has(child.id));
      const hasChildren = childList.length > 0;
      const isOpen = searchActive || expanded.has(d.id);
      const row = E("div", { class: "admin-tree-row", role: "treeitem", "aria-level": String(depth + 1),
        "data-department-id": d.id, "aria-expanded": hasChildren ? String(isOpen) : null });
      const main = E("div", { class: "admin-tree-main" });
      main.style.paddingLeft = Math.min(depth, 14) * 18 + "px";
      if (hasChildren) {
        main.appendChild(E("button", {
          type: "button", class: "admin-tree-toggle", text: isOpen ? "▾" : "▸",
          "aria-label": (isOpen ? "Згорнути " : "Розгорнути ") + d.name,
          "aria-expanded": String(isOpen),
          onclick: () => { isOpen ? expanded.delete(d.id) : expanded.add(d.id); renderDepartmentTree(); },
        }));
      } else main.appendChild(E("span", { class: "admin-tree-spacer", text: "·" }));
      main.appendChild(E("span", { class: "admin-tree-code", text: d.id }));
      main.appendChild(E("div", { class: "admin-tree-name" }, [
        E("strong", { text: d.name }),
        E("small", { class: "muted", text: d.department_type + (hasChildren ? " · підлеглих: " + childList.length : "") }),
      ]));
      row.appendChild(main);
      row.appendChild(actionButtons(() => openDeptEditor(d), () => deleteDepartment(d), false, "Видалити " + d.id));
      container.appendChild(row);
      if (hasChildren && isOpen) childList.forEach((child) => walk(child, depth + 1));
    }
    const reachable = new Set();
    function markReachable(d) {
      if (reachable.has(d.id)) return;
      reachable.add(d.id);
      (children.get(d.id) || []).forEach(markReachable);
    }
    (children.get(null) || []).forEach((root) => { markReachable(root); walk(root, 0); });
    // У випадку пошкодженої БД показуємо сироти або цикли окремо, але не розгортаємо
    // сховані вузли як нові кореневі елементи.
    departments.forEach((d) => {
      if (!reachable.has(d.id)) { markReachable(d); walk(d, 0); }
    });
    if (!rendered.size) container.appendChild(E("p", { class: "admin-tree-empty", text: departments.length ? "Підрозділів за запитом не знайдено." : "Структура ще порожня." }));
  }
  function renderDepartments() {
    const shown = filteredDepartments();
    $("departments-count").textContent = departmentsLoaded ? "Знайдено: " + shown.length + " з " + departments.length : "Завантаження підрозділів…";
    if (deptMode === "tree") renderDepartmentTree(); else renderDepartmentTable();
  }
  function setDeptMode(mode) {
    deptMode = mode;
    writePreference("anticor_admin_dept_view", mode);
    $("department-table-area").classList.toggle("hidden", mode !== "table");
    $("department-tree-area").classList.toggle("hidden", mode !== "tree");
    $("dept-view-table").setAttribute("aria-pressed", String(mode === "table"));
    $("dept-view-tree").setAttribute("aria-pressed", String(mode === "tree"));
    renderDepartments();
  }
  $("dept-view-table").addEventListener("click", () => setDeptMode("table"));
  $("dept-view-tree").addEventListener("click", () => setDeptMode("tree"));
  $("dept-expand-all").addEventListener("click", () => { departments.forEach((d) => expanded.add(d.id)); renderDepartmentTree(); });
  $("dept-collapse-all").addEventListener("click", () => { expanded.clear(); renderDepartmentTree(); });

  // ---------- Dropdown options / hierarchy ----------
  function fillParentSelect(select, selfId) {
    const keep = select.value;
    const byParent = new Map();
    const byId = new Map(departments.map((d) => [d.id, d]));
    departments.forEach((d) => {
      const key = d.parent_id && byId.has(d.parent_id) ? d.parent_id : null;
      const list = byParent.get(key) || [];
      list.push(d); byParent.set(key, list);
    });
    for (const arr of byParent.values()) arr.sort((a, b) => a.name.localeCompare(b.name, "uk"));
    select.replaceChildren(E("option", { value: "", text: "— Верхній рівень —" }));
    const visited = new Set();
    function walk(parent, depth) {
      for (const d of byParent.get(parent) || []) {
        if (visited.has(d.id) || d.id === selfId) continue; // Забороняємо власних нащадків
        visited.add(d.id);
        select.appendChild(E("option", { value: d.id, text: "  ".repeat(depth) + d.id + " — " + d.name }));
        walk(d.id, depth + 1);
      }
    }
    walk(null, 0);
    // Не пропонуємо пошкоджені гілки / цикли як батьківський підрозділ.
    select.value = Array.from(select.options).some((opt) => opt.value === keep) ? keep : "";
    UI.refreshSelect(select);
  }
  async function loadDepartments() {
    departments = await Api.get("/api/departments");
    departmentsLoaded = true;
    const deptFilter = $("user-dept-filter");
    const previousFilter = deptFilter.value;
    deptFilter.replaceChildren(E("option", { value: "", text: "Усі підрозділи" }), E("option", { value: "-", text: "Без підрозділу" }));
    departments.slice().sort((a, b) => a.name.localeCompare(b.name, "uk")).forEach((d) => {
      deptFilter.appendChild(E("option", { value: d.id, text: d.id + " — " + d.name }));
    });
    deptFilter.value = Array.from(deptFilter.options).some((o) => o.value === previousFilter) ? previousFilter : "";
    const typeFilter = $("department-type-filter");
    const previousType = typeFilter.value;
    typeFilter.replaceChildren(E("option", { value: "", text: "Усі типи" }));
    [...new Set(departments.map((d) => d.department_type).filter(Boolean))].sort((a, b) => a.localeCompare(b, "uk")).forEach((type) => {
      typeFilter.appendChild(E("option", { value: type, text: type }));
    });
    typeFilter.value = Array.from(typeFilter.options).some((o) => o.value === previousType) ? previousType : "";
    for (const id of ["user-form", "user-edit-form"]) {
      const select = $(id).elements.department_id;
      const keep = select.value;
      select.replaceChildren(E("option", { value: "", text: "— Не призначено —" }));
      departments.slice().sort((a, b) => a.name.localeCompare(b.name, "uk")).forEach((d) => {
        select.appendChild(E("option", { value: d.id, text: d.id + " — " + d.name }));
      });
      select.value = Array.from(select.options).some((o) => o.value === keep) ? keep : "";
    }
    fillParentSelect($("department-form").elements.parent_id, null);
    if (editingDeptId !== null) fillParentSelect($("department-edit-form").elements.parent_id, editingDeptId);
    UI.refreshAll();
    renderDepartments();
    renderUsers();
  }

  // ---------- Form validation / UX ----------
  function showFieldError(form, field, message) {
    const input = form.elements[field];
    if (!input) return;
    const box = input.closest(".field");
    if (!box) return;
    box.classList.add("admin-invalid-field");
    input.setAttribute("aria-invalid", "true");
    const err = E("span", { class: "admin-field-error", role: "alert", text: message });
    box.appendChild(err);
    const widgetButton = input.nextElementSibling && input.nextElementSibling.querySelector(".admin-search-trigger");
    const focusable = widgetButton || input;
    if (focusable && focusable.focus) focusable.focus({ preventScroll: false });
  }
  function clearErrors(form) {
    form.querySelectorAll(".admin-field-error").forEach((e) => e.remove());
    form.querySelectorAll(".admin-invalid-field").forEach((e) => e.classList.remove("admin-invalid-field"));
    form.querySelectorAll("[aria-invalid]").forEach((e) => e.removeAttribute("aria-invalid"));
    const box = form.querySelector(".msg[role=alert]");
    if (box) { box.textContent = ""; box.classList.add("hidden"); }
  }
  function formError(form, message) {
    const box = form.querySelector(".msg[role=alert]");
    if (box) { box.textContent = String(message); box.classList.remove("hidden"); }
    notify(message, "danger");
  }
  function updateRoleFields(form) {
    const role = form.elements.role_id.value;
    const need = ROLES_NEED_DEPARTMENT.has(role);
    form.querySelectorAll("[data-dept-required]").forEach((e) => e.classList.toggle("hidden", !need));
    form.querySelectorAll("[data-role-department-hint]").forEach((e) => {
      e.textContent = need
        ? "Обов'язково для ролі " + roleName(role) + ". Впливає на доступ до заходів."
        : "Можна залишити без підрозділу (відповідно до політики доступу).";
    });
    // Native select прихований під кастомним dropdown — required перевіряємо вручну.
    form.elements.department_id.required = false;
    if (form.elements.department_id.value) {
      const box = form.elements.department_id.closest(".field");
      if (box) { box.classList.remove("admin-invalid-field"); box.querySelectorAll(".admin-field-error").forEach((e) => e.remove()); }
    }
  }
  function checkForm(form, kind, editingId) {
    clearErrors(form);
    if (!form.checkValidity()) {
      // input/reportValidity працює навіть коли select замінений нашим UI.
      form.reportValidity();
      return false;
    }
    if (kind === "user") {
      const login = form.elements.login.value.trim();
      if (!login) { showFieldError(form, "login", "Введіть логін."); return false; }
      if (users.some((u) => norm(u.login) === norm(login) && Number(u.id) !== Number(editingId))) {
        showFieldError(form, "login", "Цей логін уже використовується."); return false;
      }
      if (ROLES_NEED_DEPARTMENT.has(form.elements.role_id.value) && !form.elements.department_id.value) {
        showFieldError(form, "department_id", "Оберіть підрозділ для цієї ролі."); return false;
      }
    } else {
      if (form.elements.id && departments.some((d) => norm(d.id) === norm(form.elements.id.value.trim()))) {
        showFieldError(form, "id", "Цей код підрозділу вже існує."); return false;
      }
      if (!form.elements.name.value.trim()) { showFieldError(form, "name", "Назва не може бути порожньою."); return false; }
      if (!form.elements.department_type.value.trim()) { showFieldError(form, "department_type", "Вкажіть тип підрозділу."); return false; }
    }
    return true;
  }
  function submitting(form, busy, label) {
    const btn = form.querySelector("button[type=submit]");
    if (!btn) return;
    if (busy) {
      btn.dataset.oldLabel = btn.textContent;
      btn.disabled = true;
      btn.textContent = label || "Збереження…";
      form.querySelectorAll("button[type=button]").forEach((b) => b.disabled = true);
    } else {
      btn.disabled = false;
      btn.textContent = btn.dataset.oldLabel || "Зберегти";
      form.querySelectorAll("button[type=button]").forEach((b) => b.disabled = false);
    }
  }
  function setupPasswordControls() {
    document.querySelectorAll("[data-password-target]").forEach((button) => {
      const input = $(button.dataset.passwordTarget);
      button.addEventListener("click", () => {
        const visible = input.type === "password";
        input.type = visible ? "text" : "password";
        button.textContent = visible ? "Сховати" : "Показати";
        button.setAttribute("aria-pressed", String(visible));
        button.setAttribute("aria-label", visible ? "Сховати пароль" : "Показати пароль");
        input.focus({ preventScroll: true });
      });
      input.addEventListener("input", () => {
        const hint = document.querySelector('[data-password-hint="' + input.id + '"]');
        if (!hint) return;
        const n = input.value.length;
        if (n === 0) hint.textContent = input.required ? "Мінімум 12 символів" : "Не змінюється, якщо поле порожнє";
        else hint.textContent = n >= 12 ? "Мінімальна довжина виконана" : "Ще " + (12 - n) + " символів до мінімуму";
        hint.classList.toggle("admin-valid-hint", n >= 12);
      });
    });
  }
  function setupFormEvents() {
    document.querySelectorAll(".admin-modal form").forEach((form) => {
      form.addEventListener("input", (event) => {
        const box = event.target.closest(".field");
        if (box) { box.classList.remove("admin-invalid-field"); box.querySelectorAll(".admin-field-error").forEach((e) => e.remove()); }
      });
      form.addEventListener("change", (event) => {
        const box = event.target.closest(".field");
        if (box) { box.classList.remove("admin-invalid-field"); box.querySelectorAll(".admin-field-error").forEach((e) => e.remove()); }
      });
      if (form.elements.role_id) {
        form.elements.role_id.addEventListener("change", () => updateRoleFields(form));
        updateRoleFields(form);
      }
    });
    setupPasswordControls();
  }

  // ---------- Confirm destructive actions ----------
  const deleteDialog = $("admin-delete-dialog");
  function confirmDeletion(entity, details) {
    UI.closeAll();
    $("admin-delete-title").textContent = "Видалити " + entity + "?";
    $("admin-delete-details").textContent = details;
    return new Promise((resolve) => {
      let finished = false;
      function finish(result) {
        if (finished) return;
        finished = true;
        $("admin-delete-confirm").removeEventListener("click", yes);
        $("admin-delete-cancel").removeEventListener("click", no);
        deleteDialog.removeEventListener("close", onClose);
        if (deleteDialog.open) deleteDialog.close();
        resolve(result);
      }
      const yes = () => finish(true);
      const no = () => finish(false);
      const onClose = () => finish(false);
      $("admin-delete-confirm").addEventListener("click", yes);
      $("admin-delete-cancel").addEventListener("click", no);
      deleteDialog.addEventListener("close", onClose);
      deleteDialog.showModal();
      $("admin-delete-cancel").focus();
    });
  }
  async function deleteUser(user) {
    if (userIsMe(user.id)) { notify("Власний обліковий запис не можна видаляти.", "warning"); return; }
    if (!await confirmDeletion("користувача", "Логін: " + user.login + " · ID: " + user.id)) return;
    try {
      await Api.del("/api/users/" + encodeURIComponent(user.id));
      notify("Користувача «" + user.login + "» видалено.");
      await loadUsers();
    } catch (error) { failure(error); }
  }
  async function deleteDepartment(dept) {
    if (!await confirmDeletion("підрозділ", dept.id + " — " + dept.name)) return;
    try {
      await Api.del("/api/departments/" + encodeURIComponent(dept.id));
      notify("Підрозділ " + dept.id + " видалено.");
      await loadDepartments(); await loadUsers();
    } catch (error) { failure(error); }
  }

  // ---------- Dialogs ----------
  const userCreate = $("user-create-dialog");
  const userEdit = $("user-edit-dialog");
  const deptCreate = $("department-create-dialog");
  const deptEdit = $("department-edit-dialog");
  const userForm = $("user-form");
  const userEditForm = $("user-edit-form");
  const deptForm = $("department-form");
  const deptEditForm = $("department-edit-form");

  function showDialog(dialog, form) {
    UI.closeAll();
    if (form) clearErrors(form);
    if (form && form.elements.role_id) updateRoleFields(form);
    UI.refreshAll();
    dialog.showModal();
    const first = dialog.querySelector("input:not([type=hidden])");
    if (first) first.focus({ preventScroll: true });
  }
  $("user-create-open").addEventListener("click", () => { userForm.reset(); showDialog(userCreate, userForm); });
  $("department-create-open").addEventListener("click", () => { deptForm.reset(); fillParentSelect(deptForm.elements.parent_id, null); showDialog(deptCreate, deptForm); });
  $("user-edit-cancel").addEventListener("click", () => userEdit.close());
  $("department-edit-cancel").addEventListener("click", () => deptEdit.close());
  document.querySelectorAll("dialog [data-close]").forEach((button) => button.addEventListener("click", () => button.closest("dialog").close()));
  document.querySelectorAll("dialog").forEach((dialog) => dialog.addEventListener("close", () => UI.closeAll()));

  function openUserEditor(user) {
    editingUserId = user.id;
    userEditForm.elements.login.value = user.login;
    userEditForm.elements.role_id.value = user.role_id;
    userEditForm.elements.department_id.value = user.department_id || "";
    userEditForm.elements.position.value = user.position || "";
    userEditForm.elements.password.value = "";
    $("user-edit-id").textContent = "ID " + user.id + " · " + user.login;
    const own = userIsMe(user.id);
    userEditForm.elements.role_id.disabled = own;
    $("user-edit-hint").textContent = own ? "Власну роль адміністратора змінити не можна." : "Пароль можна залишити порожнім.";
    $("user-edit-hint").classList.remove("hidden");
    showDialog(userEdit, userEditForm);
  }
  function openDeptEditor(dept) {
    editingDeptId = dept.id;
    deptEditForm.elements.name.value = dept.name;
    deptEditForm.elements.department_type.value = dept.department_type;
    deptEditForm.elements.notes.value = dept.notes || "";
    fillParentSelect(deptEditForm.elements.parent_id, dept.id);
    deptEditForm.elements.parent_id.value = dept.parent_id || "";
    $("department-edit-id").textContent = dept.id + " — " + dept.name;
    showDialog(deptEdit, deptEditForm);
  }
  function backendFormError(form, error) {
    const details = error && error.body && error.body.detail;
    // Pydantic 422 reports loc=['body','field_name']; mark the relevant field too.
    if (Array.isArray(details)) {
      for (const problem of details) {
        const loc = Array.isArray(problem.loc) ? problem.loc : [];
        const field = loc.find((part) => typeof part === "string" && form.elements[part]);
        if (field) {
          showFieldError(form, field, String(problem.msg || "Перевірте значення поля."));
          break;
        }
      }
    }
    formError(form, error && error.message ? error.message : "Помилка збереження.");
  }
  async function submitUser(form, edit) {
    if (!checkForm(form, "user", edit ? editingUserId : null)) return;
    const data = {
      login: form.elements.login.value.trim(),
      role_id: form.elements.role_id.value,
      department_id: form.elements.department_id.value || null,
      position: form.elements.position.value.trim() || null,
    };
    const password = form.elements.password.value;
    if (!edit || password) data.password = password;
    submitting(form, true, edit ? "Збереження…" : "Створення…");
    let saved = false;
    try {
      const result = edit
        ? await Api.patch("/api/users/" + encodeURIComponent(editingUserId), data)
        : await Api.post("/api/users/", data);
      saved = true;
      (edit ? userEdit : userCreate).close();
      if (edit) editingUserId = null;
      notify(edit ? "Користувача змінено." : "Створено користувача «" + result.login + "».");
    } catch (error) { backendFormError(form, error); }
    finally { submitting(form, false); }
    if (saved) { try { await loadUsers(); } catch (reloadError) { failure(reloadError); } }
  }
  async function submitDept(form, edit) {
    if (!checkForm(form, "department", edit ? editingDeptId : null)) return;
    const data = {
      name: form.elements.name.value.trim(),
      department_type: form.elements.department_type.value.trim(),
      notes: form.elements.notes.value.trim(),
      parent_id: form.elements.parent_id.value || null,
    };
    if (!edit) data.id = form.elements.id.value.trim();
    submitting(form, true, edit ? "Збереження…" : "Створення…");
    let saved = false;
    try {
      const result = edit
        ? await Api.patch("/api/departments/" + encodeURIComponent(editingDeptId), data)
        : await Api.post("/api/departments", data);
      saved = true;
      (edit ? deptEdit : deptCreate).close();
      if (edit) editingDeptId = null;
      notify(edit ? "Зміни підрозділу збережено." : "Створено підрозділ «" + result.id + "».");
    } catch (error) { backendFormError(form, error); }
    finally { submitting(form, false); }
    if (saved) { try { await loadDepartments(); await loadUsers(); } catch (reloadError) { failure(reloadError); } }
  }
  userForm.addEventListener("submit", (e) => { e.preventDefault(); submitUser(userForm, false); });
  userEditForm.addEventListener("submit", (e) => { e.preventDefault(); submitUser(userEditForm, true); });
  deptForm.addEventListener("submit", (e) => { e.preventDefault(); submitDept(deptForm, false); });
  deptEditForm.addEventListener("submit", (e) => { e.preventDefault(); submitDept(deptEditForm, true); });

  // ---------- Navigation / filter events ----------
  document.querySelectorAll("[data-tab]").forEach((tab) => {
    tab.addEventListener("click", () => {
      document.querySelectorAll("[data-tab]").forEach((t) => t.setAttribute("aria-selected", String(t === tab)));
      document.querySelectorAll("[data-panel]").forEach((p) => p.classList.toggle("hidden", p.dataset.panel !== tab.dataset.tab));
    });
  });
  document.querySelectorAll("#user-search, #user-role-filter, #user-dept-filter").forEach((input) => {
    input.addEventListener(input.tagName === "INPUT" ? "input" : "change", () => { userPage.page = 1; renderUsers(); });
  });
  document.querySelectorAll("#department-search, #department-type-filter").forEach((input) => {
    input.addEventListener(input.tagName === "INPUT" ? "input" : "change", () => { deptPage.page = 1; renderDepartments(); });
  });

  setupFormEvents();
  setDeptMode(deptMode);
  (async () => {
    if (!await Api.requireRole("ADMIN")) return;
    try { await loadDepartments(); await loadUsers(); }
    catch (error) {
      failure(error);
      Api.showError(error.status === 403 ? new Error("Цей розділ доступний лише адміністратору.") : error);
    }
  })();
})();
