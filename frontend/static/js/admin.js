// Кабінет адміністратора: користувачі й підрозділи — пошук, фільтри, пагінація, створення та редагування.
(function () {
  "use strict";
  const el = Api.el;
  let departments = [];
  let users = [];
  let editingUserId = null;
  let editingDepartmentId = null;

  document.querySelectorAll("[data-tab]").forEach(function (button) {
    button.addEventListener("click", function () {
      document.querySelectorAll("[data-tab]").forEach(function (tab) {
        tab.setAttribute("aria-selected", String(tab === button));
      });
      document.querySelectorAll("[data-panel]").forEach(function (panel) {
        panel.classList.toggle("hidden", panel.dataset.panel !== button.dataset.tab);
      });
    });
  });

  // ---------- пошук, фільтри, пагінація ----------
  const PAGE_SIZES = [10, 25, 50, 100];
  const userPage = { page: 1, size: readSize("users", 25) };
  const departmentPage = { page: 1, size: readSize("departments", 25) };

  function readSize(key, def) {
    try {
      const v = Number(localStorage.getItem("anticor_admin_size_" + key));
      return PAGE_SIZES.indexOf(v) !== -1 ? v : def;
    } catch (e) { return def; }
  }
  function saveSize(key, v) {
    try { localStorage.setItem("anticor_admin_size_" + key, String(v)); } catch (e) { /* без збереження */ }
  }

  function norm(v) { return String(v == null ? "" : v).toLocaleLowerCase("uk"); }

  // Збіг усіх слів запиту з будь-якими полями запису (у довільному порядку).
  function matchesQuery(fields, query) {
    if (!query) return true;
    const hay = fields.map(norm).join(" ");
    return query.split(/\s+/).every(function (word) { return hay.indexOf(word) !== -1; });
  }

  // Панель сторінок (спільна з кабінетом керівника — Api.renderPager).
  function renderPager(box, state, total, key, rerender) {
    Api.renderPager(box, state, total, {
      sizes: PAGE_SIZES, rerender: rerender, onSize: function (v) { saveSize(key, v); },
    });
  }

  function departmentNameOf(id) {
    const d = departments.find(function (x) { return x.id === id; });
    return d ? d.name : id;
  }

  function filteredUsers() {
    const query = norm(document.getElementById("user-search").value.trim());
    const role = document.getElementById("user-role-filter").value;
    const dept = document.getElementById("user-dept-filter").value;
    return users.filter(function (user) {
      if (role && user.role_id !== role) return false;
      if (dept === "-" && user.department_id) return false;
      if (dept && dept !== "-" && user.department_id !== dept) return false;
      return matchesQuery([
        user.id, user.login, user.role_id, (Api.ROLES[user.role_id] || {}).name,
        user.department_id, user.department_id ? departmentNameOf(user.department_id) : "",
        user.position, user.program_id,
      ], query);
    });
  }

  function renderUsers() {
    const tbody = document.getElementById("users");
    tbody.innerHTML = "";
    const all = filteredUsers();
    ["user-pager-top", "user-pager"].forEach(function (id) {
      renderPager(document.getElementById(id), userPage, all.length, "users", renderUsers);
    });
    const start = (userPage.page - 1) * userPage.size;
    const matches = all.slice(start, start + userPage.size);
    if (!matches.length) {
      tbody.appendChild(el("tr", {}, [el("td", {
        colspan: "7",
        class: "muted",
        text: users.length ? "Користувачів за цим запитом не знайдено." : "Користувачів немає.",
      })]));
      return;
    }
    const departmentNames = Object.fromEntries(departments.map(function (d) { return [d.id, d.name]; }));
    matches.forEach(function (user) {
      tbody.appendChild(el("tr", { "data-user-id": String(user.id) }, [
        el("td", { text: String(user.id) }),
        el("td", { text: user.login }),
        el("td", { text: (Api.ROLES[user.role_id] || {}).name || user.role_id }),
        el("td", { text: user.department_id ? (departmentNames[user.department_id] || user.department_id) : "—" }),
        el("td", { text: user.position || "—" }),
        el("td", { text: user.program_id || "—" }),
        el("td", {}, [el("button", {
          type: "button",
          class: "btn",
          text: "Змінити",
          onclick: function () { openUserEditor(user); },
        })]),
      ]));
    });
  }

  async function loadUsers() {
    users = await Api.getAll("/api/users/", 100, "skip");
    renderUsers();
  }

  async function loadDepartments() {
    departments = await Api.get("/api/departments/");
    const deptFilter = document.getElementById("user-dept-filter");
    const keepDept = deptFilter.value;
    deptFilter.replaceChildren(el("option", { value: "", text: "Усі підрозділи" }), el("option", { value: "-", text: "Без підрозділу" }));
    departments.slice().sort(function (a, b) { return a.name.localeCompare(b.name, "uk"); }).forEach(function (d) {
      deptFilter.appendChild(el("option", { value: d.id, text: d.name }));
    });
    deptFilter.value = keepDept;
    const typeFilter = document.getElementById("department-type-filter");
    const keepType = typeFilter.value;
    typeFilter.replaceChildren(el("option", { value: "", text: "Усі типи" }));
    Array.from(new Set(departments.map(function (d) { return d.department_type; }).filter(Boolean))).sort().forEach(function (t) {
      typeFilter.appendChild(el("option", { value: t, text: t }));
    });
    typeFilter.value = keepType;
    fillParentSelect(document.querySelector("#department-form [name=parent_id]"), null);
    ["#user-form", "#user-edit-form"].forEach(function (formSelector) {
      const select = document.querySelector(formSelector + " [name=department_id]");
      select.replaceChildren(el("option", { value: "", text: "— Не призначено —" }));
      departments.forEach(function (department) {
        select.appendChild(el("option", {
          value: department.id,
          text: department.id + " — " + department.name,
        }));
      });
    });
    renderDepartments();
  }

  // Список «Підпорядкованість»: деревом, з відступами; без самого підрозділу та його підлеглих.
  function fillParentSelect(select, selfId) {
    const keep = select.value;
    const children = {};
    departments.forEach(function (d) { (children[d.parent_id || ""] = children[d.parent_id || ""] || []).push(d); });
    Object.keys(children).forEach(function (k) {
      children[k].sort(function (a, b) { return a.name.localeCompare(b.name, "uk"); });
    });
    const known = {};
    departments.forEach(function (d) { known[d.id] = true; });
    select.replaceChildren(el("option", { value: "", text: "— Верхній рівень (не підпорядкований) —" }));
    function walk(parentKey, depth) {
      (children[parentKey] || []).forEach(function (d) {
        if (d.id === selfId) return; // підрозділ і вся його гілка недоступні як вищий рівень
        select.appendChild(el("option", { value: d.id, text: "\u00a0\u00a0".repeat(depth) + (depth ? "└ " : "") + d.name + " (" + d.id + ")" }));
        walk(d.id, depth + 1);
      });
    }
    walk("", 0);
    // Підрозділи з неіснуючим батьком теж показуємо, щоб їх можна було обрати.
    departments.forEach(function (d) {
      if (d.parent_id && !known[d.parent_id] && d.id !== selfId) select.appendChild(el("option", { value: d.id, text: d.name + " (" + d.id + ")" }));
    });
    select.value = keep;
  }

  function renderDepartments() {
    const tbody = document.getElementById("departments");
    tbody.innerHTML = "";
    const query = norm(document.getElementById("department-search").value.trim());
    const type = document.getElementById("department-type-filter").value;
    const all = departments.filter(function (d) {
      if (type && d.department_type !== type) return false;
      const parent = d.parent_id ? departmentNameOf(d.parent_id) : "";
      return matchesQuery([d.id, d.name, d.department_type, d.notes, d.parent_id, parent, d.parent_id ? "" : "верхній рівень"], query);
    });
    ["department-pager-top", "department-pager"].forEach(function (id) {
      renderPager(document.getElementById(id), departmentPage, all.length, "departments", renderDepartments);
    });
    const start = (departmentPage.page - 1) * departmentPage.size;
    const matches = all.slice(start, start + departmentPage.size);

    matches.forEach(function (department) {
      tbody.appendChild(el("tr", {}, [
        el("td", { class: "nowrap", text: department.id }),
        el("td", { text: department.name }),
        el("td", { text: department.department_type }),
        el("td", { text: department.parent_id ? departmentNameOf(department.parent_id) : "Верхній рівень", class: department.parent_id ? "" : "muted" }),
        el("td", { text: department.notes || "—" }),
        el("td", {}, [el("button", {
          type: "button",
          class: "btn",
          text: "Змінити",
          onclick: function () { openDepartmentEditor(department); },
        })]),
      ]));
    });

    if (!matches.length) {
      tbody.appendChild(el("tr", {}, [el("td", {
        colspan: "6",
        class: "muted",
        text: departments.length ? "Підрозділів за цим запитом не знайдено." : "Підрозділів немає.",
      })]));
    }
  }

  const editDialog = document.getElementById("user-edit-dialog");
  const editForm = document.getElementById("user-edit-form");
  const editError = document.getElementById("user-edit-error");
  const editMessage = document.getElementById("user-edit-msg");
  const editRole = editForm.elements.role_id;
  const editHint = document.getElementById("user-edit-hint");

  function openUserEditor(user) {
    editingUserId = user.id;
    editForm.elements.login.value = user.login;
    editRole.value = user.role_id;
    editForm.elements.department_id.value = user.department_id || "";
    editForm.elements.position.value = user.position || "";
    editForm.elements.password.value = "";
    document.getElementById("user-edit-id").textContent = "ID " + user.id;
    editError.textContent = "";
    editError.classList.add("hidden");
    editMessage.textContent = "";

    const isCurrentUser = Number(Api.userId()) === Number(user.id);
    editRole.disabled = isCurrentUser;
    editHint.textContent = isCurrentUser
      ? "Не можна змінити власну роль адміністратора."
      : "Залиште пароль порожнім, щоб не змінювати його.";
    editHint.classList.remove("hidden");
    editDialog.showModal();
  }

  // Будь-яка зміна запиту чи фільтра повертає на першу сторінку.
  function resetTo(state, render) { return function () { state.page = 1; render(); }; }
  ["user-search", "user-role-filter", "user-dept-filter"].forEach(function (id) {
    document.getElementById(id).addEventListener(id === "user-search" ? "input" : "change", resetTo(userPage, renderUsers));
  });
  ["department-search", "department-type-filter"].forEach(function (id) {
    document.getElementById(id).addEventListener(id === "department-search" ? "input" : "change", resetTo(departmentPage, renderDepartments));
  });

  // Вікна створення.
  const userCreateDialog = document.getElementById("user-create-dialog");
  const departmentCreateDialog = document.getElementById("department-create-dialog");
  document.getElementById("user-create-open").addEventListener("click", function () {
    document.getElementById("user-msg").textContent = "";
    userCreateDialog.showModal();
  });
  document.getElementById("department-create-open").addEventListener("click", function () {
    document.getElementById("department-msg").textContent = "";
    fillParentSelect(document.querySelector("#department-form [name=parent_id]"), null);
    departmentCreateDialog.showModal();
  });
  document.querySelectorAll("dialog [data-close]").forEach(function (b) {
    b.addEventListener("click", function () { b.closest("dialog").close(); });
  });
  document.getElementById("user-edit-cancel").addEventListener("click", function () {
    editDialog.close();
    editingUserId = null;
  });

  editForm.addEventListener("submit", async function (event) {
    event.preventDefault();
    editError.textContent = "";
    editError.classList.add("hidden");
    if (!editForm.reportValidity()) return;
    if (editingUserId === null) return;

    const data = {
      login: editForm.elements.login.value.trim(),
      role_id: editRole.value,
      department_id: editForm.elements.department_id.value || null,
      position: editForm.elements.position.value.trim() || null,
    };
    const password = editForm.elements.password.value;
    if (password) data.password = password;

    const saveButton = editForm.querySelector("button[type=submit]");
    saveButton.disabled = true;
    try {
      await Api.patch("/api/users/" + editingUserId, data);
      editDialog.close();
      editMessage.className = "msg ok";
      editMessage.textContent = "Зміни користувача збережено.";
      editingUserId = null;
      await loadUsers();
    } catch (error) {
      editError.textContent = "Не вдалося зберегти: " + error.message;
      editError.classList.remove("hidden");
    } finally {
      saveButton.disabled = false;
    }
  });

  const departmentEditDialog = document.getElementById("department-edit-dialog");
  const departmentEditForm = document.getElementById("department-edit-form");
  const departmentEditError = document.getElementById("department-edit-error");
  const departmentEditMessage = document.getElementById("department-edit-msg");

  function openDepartmentEditor(department) {
    editingDepartmentId = department.id;
    departmentEditForm.elements.name.value = department.name;
    departmentEditForm.elements.department_type.value = department.department_type;
    departmentEditForm.elements.notes.value = department.notes || "";
    fillParentSelect(departmentEditForm.elements.parent_id, department.id);
    departmentEditForm.elements.parent_id.value = department.parent_id || "";
    document.getElementById("department-edit-id").textContent = "Код " + department.id;
    departmentEditError.textContent = "";
    departmentEditError.classList.add("hidden");
    departmentEditMessage.textContent = "";
    departmentEditDialog.showModal();
  }

  document.getElementById("department-edit-cancel").addEventListener("click", function () {
    departmentEditDialog.close();
    editingDepartmentId = null;
  });

  departmentEditForm.addEventListener("submit", async function (event) {
    event.preventDefault();
    departmentEditError.textContent = "";
    departmentEditError.classList.add("hidden");
    if (!departmentEditForm.reportValidity()) return;
    if (editingDepartmentId === null) return;

    const data = {
      name: departmentEditForm.elements.name.value.trim(),
      department_type: departmentEditForm.elements.department_type.value.trim(),
      notes: departmentEditForm.elements.notes.value.trim(),
      parent_id: departmentEditForm.elements.parent_id.value || null,
    };
    const saveButton = departmentEditForm.querySelector("button[type=submit]");
    saveButton.disabled = true;
    try {
      await Api.patch("/api/departments/" + encodeURIComponent(editingDepartmentId), data);
      departmentEditDialog.close();
      departmentEditMessage.className = "msg ok";
      departmentEditMessage.textContent = "Зміни підрозділу збережено.";
      editingDepartmentId = null;
      await loadDepartments();
      await loadUsers();
    } catch (error) {
      departmentEditError.textContent = "Не вдалося зберегти: " + error.message;
      departmentEditError.classList.remove("hidden");
    } finally {
      saveButton.disabled = false;
    }
  });

  const userForm = document.getElementById("user-form");
  const userMsg = document.getElementById("user-msg");
  userForm.addEventListener("submit", async function (event) {
    event.preventDefault();
    userMsg.textContent = "";
    if (!userForm.reportValidity()) return;

    const data = Object.fromEntries(new FormData(userForm).entries());
    ["department_id", "position"].forEach(function (key) {
      if (!data[key]) data[key] = null;
    });
    try {
      const user = await Api.post("/api/users/", data);
      userForm.reset();
      userCreateDialog.close();
      editMessage.className = "msg ok";
      editMessage.textContent = "Створено користувача " + user.login + ".";
      await loadUsers();
    } catch (error) {
      userMsg.className = "msg err";
      userMsg.textContent = "Помилка: " + error.message;
    }
  });

  const departmentForm = document.getElementById("department-form");
  const departmentMsg = document.getElementById("department-msg");
  departmentForm.addEventListener("submit", async function (event) {
    event.preventDefault();
    departmentMsg.textContent = "";
    if (!departmentForm.reportValidity()) return;

    const data = Object.fromEntries(new FormData(departmentForm).entries());
    if (!data.notes) data.notes = "";
    if (!data.parent_id) data.parent_id = null;
    try {
      const department = await Api.post("/api/departments/", data);
      departmentForm.reset();
      departmentCreateDialog.close();
      departmentEditMessage.className = "msg ok";
      departmentEditMessage.textContent = "Створено підрозділ " + department.id + ".";
      await loadDepartments();
      await loadUsers();
    } catch (error) {
      departmentMsg.className = "msg err";
      departmentMsg.textContent = "Помилка: " + error.message;
    }
  });

  (async function () {
    if (!await Api.requireRole("ADMIN")) return;
    try {
      await loadDepartments();
      await loadUsers();
    } catch (error) {
      Api.showError(error.status === 403 ? new Error("Розділ доступний лише адміністратору.") : error);
    }
  })();
})();
