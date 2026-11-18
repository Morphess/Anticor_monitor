// Кабінет адміністратора: користувачі (/api/users), програми, журнал дій (/api/action-logs).
(function () {
  "use strict";
  const el = Api.el;
  let programs = [];
  let logSkip = 0;
  const LOG_PAGE = 50;

  document.querySelectorAll("[data-tab]").forEach(function (b) {
    b.addEventListener("click", function () {
      document.querySelectorAll("[data-tab]").forEach(function (x) { x.setAttribute("aria-selected", String(x === b)); });
      document.querySelectorAll("[data-panel]").forEach(function (p) { p.classList.toggle("hidden", p.dataset.panel !== b.dataset.tab); });
      if (b.dataset.tab === "log" && logSkip === 0) loadLog();
      if (b.dataset.tab === "flags" && !flagsLoaded) loadFlags();
    });
  });

  async function loadUsers() {
    const tbody = document.getElementById("users");
    tbody.innerHTML = "";
    const users = await Api.getAll("/api/users/", 100, "skip");
    users.forEach(function (u) {
      tbody.appendChild(el("tr", {}, [
        el("td", { text: String(u.id) }),
        el("td", { text: u.login }),
        el("td", { text: (Api.ROLES[u.role_id] || {}).name || u.role_id }),
        el("td", { text: u.department_id ? Api.deptName(u.department_id) : "—" }),
        el("td", { text: u.position || "—" }),
        el("td", { text: u.program_id || "—" }),
      ]));
    });
  }

  async function loadPrograms() {
    programs = await Api.get("/api/programs");
    const periodSel = document.getElementById("flags-period");
    Api.fillPeriods(periodSel, programs);
    periodSel.addEventListener("change", syncAsOf);
    syncAsOf();
    const tbody = document.getElementById("programs");
    tbody.innerHTML = "";
    const sel = document.querySelector("#user-form [name=program_id]");
    programs.forEach(function (p) {
      sel.appendChild(el("option", { value: p.id, text: p.id }));
      tbody.appendChild(el("tr", {}, [
        el("td", { text: p.id }), el("td", { text: p.title }),
        el("td", { class: "nowrap", text: Api.fmtDate(p.start_date) }),
        el("td", { class: "nowrap", text: Api.fmtDate(p.end_date) }),
        el("td", { text: p.approval_status }),
      ]));
    });
  }

  function fillDepartments() {
    // ЗАГЛУШКА: довідник підрозділів поки статичний (немає /api/departments).
    const sel = document.querySelector("#user-form [name=department_id]");
    Object.keys(Api.DEPARTMENTS).forEach(function (id) {
      sel.appendChild(el("option", { value: id, text: id + " — " + Api.DEPARTMENTS[id] }));
    });
  }

  async function loadLog() {
    const tbody = document.getElementById("log");
    try {
      const page = await Api.get("/api/action-logs/?skip=" + logSkip + "&limit=" + LOG_PAGE);
      if (logSkip === 0) tbody.innerHTML = "";
      page.forEach(function (r) {
        tbody.appendChild(el("tr", {}, [
          el("td", { class: "nowrap", text: new Date(r.occurred_at).toLocaleString("uk-UA") }),
          el("td", { text: r.actor_user_id != null ? String(r.actor_user_id) : "система" }),
          el("td", { text: r.action }),
          el("td", { text: r.entity_type + " " + r.entity_id }),
          el("td", { text: r.field_name || "" }),
          el("td", { class: "small", text: r.old_value || "" }),
          el("td", { class: "small", text: r.new_value || "" }),
        ]));
      });
      logSkip += page.length;
      document.getElementById("log-more").classList.toggle("hidden", page.length < LOG_PAGE);
      if (logSkip === 0) emptyLog(tbody);
    } catch (err) { Api.showError(err); }
  }
  function emptyLog(tbody) {
    tbody.appendChild(el("tr", {}, [el("td", { colspan: "7", class: "muted", text: "Записів немає." })]));
  }
  document.getElementById("log-more").addEventListener("click", loadLog);

  // ---------- Сигнали Risk Flags ----------
  let flagsLoaded = false;
  const flagsForm = document.getElementById("flags-form");
  const flagsMsg = document.getElementById("flags-msg");
  Object.keys(Api.FLAGS).forEach(function (c) {
    flagsForm.elements.code.appendChild(el("option", { value: c, text: c + " — " + Api.FLAGS[c] }));
  });
  function syncAsOf() { flagsForm.elements.as_of.value = Api.flagsAsOf(flagsForm.elements.period.value); }
  async function loadFlags() {
    flagsLoaded = true;
    const tbody = document.getElementById("flags");
    const f = flagsForm.elements;
    flagsMsg.className = "msg";
    flagsMsg.textContent = "Перевірка…";
    const res = await Api.riskFlags(f.period.value, f.as_of.value, f.code.value);
    tbody.innerHTML = "";
    if (!res.ok) {
      flagsMsg.className = "msg err";
      flagsMsg.textContent = "Помилка: " + res.error.message;
      return;
    }
    flagsMsg.textContent = "Знайдено сигналів: " + res.data.length;
    if (!res.data.length) {
      tbody.appendChild(el("tr", {}, [el("td", { colspan: "4", class: "muted", text: "Сигналів немає." })]));
      return;
    }
    res.data.forEach(function (x) {
      tbody.appendChild(el("tr", {}, [
        el("td", {}, [Api.flagBadge(x)]),
        el("td", { class: "nowrap", text: (Api.OBJECT_TYPES[x.object_type] || x.object_type) + " " + x.object_id }),
        el("td", { text: x.message }),
        el("td", { class: "small", text: x.explanation }),
      ]));
    });
  }
  flagsForm.addEventListener("submit", function (e) {
    e.preventDefault();
    if (flagsForm.reportValidity()) loadFlags();
  });

  const form = document.getElementById("user-form");
  const msg = document.getElementById("user-msg");
  form.addEventListener("submit", async function (e) {
    e.preventDefault();
    if (!form.reportValidity()) return;
    const data = Object.fromEntries(new FormData(form).entries());
    ["program_id", "department_id", "position"].forEach(function (k) { if (!data[k]) data[k] = null; });
    try {
      const u = await Api.post("/api/users/", data);
      msg.className = "msg ok";
      msg.textContent = "Створено користувача " + u.login;
      form.reset();
      await loadUsers();
    } catch (err) {
      msg.className = "msg err";
      msg.textContent = "Помилка: " + err.message;
    }
  });

  (async function () {
    if (!await Api.requireRole("ADMIN")) return;

    fillDepartments();
    try {
      await Promise.all([loadUsers(), loadPrograms()]);
    } catch (err) {
      Api.showError(err.status === 403 ? new Error("Розділ доступний лише адміністратору.") : err);
    }
  })();
})();
