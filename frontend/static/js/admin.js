// Кабінет адміністратора: створення користувачів і підрозділів.
(function () {
  "use strict";
  const el = Api.el;
  let departments = [];
  let programs = [];
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

  function renderUsers() {
    const tbody = document.getElementById("users");
    tbody.innerHTML = "";
    const query = document.getElementById("user-search").value.trim().toLocaleLowerCase("uk");
    const matches = users.filter(function (user) {
      return String(user.id).includes(query) || user.login.toLocaleLowerCase("uk").includes(query);
    });
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

  async function loadPrograms() {
    programs = await Api.getAll("/api/programs", 100, "skip");
    ["#user-form", "#user-edit-form"].forEach(function (formSelector) {
      const select = document.querySelector(formSelector + " [name=program_id]");
      select.replaceChildren(el("option", { value: "", text: "— Не призначено —" }));
      programs.forEach(function (program) {
        select.appendChild(el("option", {
          value: program.id,
          text: program.id + " — " + program.title,
        }));
      });
      updateProgramRequirement(document.querySelector(formSelector));
    });
  }

  function updateProgramRequirement(form) {
    const required = form.elements.role_id.value !== "ADMIN";
    form.elements.program_id.required = required;
    form.querySelector("[data-program-required-hint]").classList.toggle("hidden", !required);
  }

  async function loadDepartments() {
    departments = await Api.get("/api/departments/");
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

  function renderDepartments() {
    const tbody = document.getElementById("departments");
    tbody.innerHTML = "";
    const query = document.getElementById("department-search").value.trim().toLocaleLowerCase("uk");
    const matches = departments.filter(function (department) {
      return department.id.toLocaleLowerCase("uk").includes(query) ||
        department.name.toLocaleLowerCase("uk").includes(query);
    });

    matches.forEach(function (department) {
      tbody.appendChild(el("tr", {}, [
        el("td", { class: "nowrap", text: department.id }),
        el("td", { text: department.name }),
        el("td", { text: department.department_type }),
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
        colspan: "5",
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
    updateProgramRequirement(editForm);
    editForm.elements.program_id.value = user.program_id || "";
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

  document.getElementById("user-search").addEventListener("input", renderUsers);
  editRole.addEventListener("change", function () {
    updateProgramRequirement(editForm);
  });
  document.getElementById("department-search").addEventListener("input", renderDepartments);
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
      program_id: editForm.elements.program_id.value || null,
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
  userForm.elements.role_id.addEventListener("change", function () {
    updateProgramRequirement(userForm);
  });
  userForm.addEventListener("submit", async function (event) {
    event.preventDefault();
    userMsg.textContent = "";
    if (!userForm.reportValidity()) return;

    const data = Object.fromEntries(new FormData(userForm).entries());
    ["program_id", "department_id", "position"].forEach(function (key) {
      if (!data[key]) data[key] = null;
    });
    try {
      const user = await Api.post("/api/users/", data);
      userMsg.className = "msg ok";
      userMsg.textContent = "Створено користувача " + user.login;
      userForm.reset();
      editMessage.textContent = "";
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
    try {
      const department = await Api.post("/api/departments/", data);
      departmentMsg.className = "msg ok";
      departmentMsg.textContent = "Створено підрозділ " + department.id;
      departmentForm.reset();
      departmentEditMessage.textContent = "";
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
      await Promise.all([loadPrograms(), loadDepartments()]);
      await loadUsers();
    } catch (error) {
      Api.showError(error.status === 403 ? new Error("Розділ доступний лише адміністратору.") : error);
    }
  })();
})();
