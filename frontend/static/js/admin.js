// Адміністратор: список користувачів, пошук і створення нового.
var ROLES = { ADMIN: "Адміністратор", KOORD: "Координатор", VYK: "Виконавець", KER: "Керівник", ANAL: "Аналітик" };
var users = [], departments = {};

function el(tag, cls, text) {
  var e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}

function fillSelect(select, options) {
  options.forEach(function (o) {
    var opt = el("option", "", o[1]);
    opt.value = o[0];
    select.appendChild(opt);
  });
}

function depName(id) { return id ? departments[id] || id : "—"; }

function render() {
  var qRaw = document.getElementById("q").value.trim(), q = qRaw.toLowerCase();
  var box = document.getElementById("users");
  box.textContent = "";
  var shown = users.filter(function (u) {
    return !q || [u.login, depName(u.department_id), u.position, ROLES[u.role_id] || u.role_id].some(function (s) {
      return String(s || "").toLowerCase().indexOf(q) >= 0;
    });
  });
  shown.forEach(function (u) {
    var row = el("tr");
    row.appendChild(el("td", "fw-semibold", u.login));
    row.appendChild(el("td", "", depName(u.department_id)));
    row.appendChild(el("td", "d-none d-md-table-cell", u.position || "—"));
    row.appendChild(el("td", "", ROLES[u.role_id] || u.role_id));
    box.appendChild(row);
  });
  var empty = document.getElementById("empty");
  empty.hidden = shown.length > 0;
  empty.textContent = qRaw ? "Користувачів за запитом «" + qRaw + "» не знайдено" : "Користувачів ще немає";
}

// ---------- Форма створення ----------
var form = document.getElementById("user-form");
var createBtn = document.getElementById("create");

function toggleForm(open) {
  form.hidden = !open;
  createBtn.setAttribute("aria-expanded", open);
  document.getElementById("form-error").textContent = "";
  if (open) { document.getElementById("saved").textContent = ""; form.elements.login.focus(); }
}

createBtn.addEventListener("click", function () { toggleForm(form.hidden); });
document.getElementById("cancel").addEventListener("click", function () { form.reset(); toggleForm(false); });

form.addEventListener("submit", function (e) {
  e.preventDefault();
  var err = document.getElementById("form-error");
  var f = form.elements;
  var data = {
    login: f.login.value.trim(),
    password: f.password.value,
    role_id: f.role_id.value,
    department_id: f.department_id.value || null,
    position: f.position.value.trim() || null,
    program_id: f.program_id.value || null
  };
  if (!data.login) { err.textContent = "Введіть логін"; return; }
  if (!/^[A-Za-z0-9_.-]{3,100}$/.test(data.login)) { err.textContent = "Логін: від 3 символів, латиниця, цифри, . _ -"; return; }
  if (data.password.length < 12) { err.textContent = "Пароль має містити щонайменше 12 символів"; return; }

  var submit = form.querySelector("button[type=submit]");
  submit.disabled = true;
  Api.post("/api/users/", data)
    .then(function (u) {
      users.push(u);
      users.sort(function (a, b) { return a.login.localeCompare(b.login); });
      form.reset();
      toggleForm(false);
      document.getElementById("saved").textContent = "Користувача «" + u.login + "» створено";
      render();
    })
    .catch(function (ex) { err.textContent = ex.message; })
    .finally(function () { submit.disabled = false; });
});

// ---------- Завантаження ----------
Promise.all([
  Api.get("/api/auth/me"),
  Api.get("/api/admin/departments"),
  Api.get("/api/programs?limit=100"),
  Api.get("/api/users/?limit=100")
])
  .then(function (res) {
    var me = res[0];
    res[1].forEach(function (d) { departments[d.id] = d.name; });
    document.getElementById("unit").textContent = me.department_id ? depName(me.department_id) : "Адміністрування системи";

    fillSelect(document.getElementById("f-role"), Object.keys(ROLES).map(function (r) { return [r, ROLES[r]]; }));
    document.getElementById("f-role").value = "VYK";
    fillSelect(document.getElementById("f-department"), [["", "— не вказано —"]].concat(res[1].map(function (d) { return [d.id, d.name]; })));
    fillSelect(document.getElementById("f-program"), [["", "— не вказано —"]].concat(res[2].map(function (p) { return [p.id, p.title]; })));

    users = res[3].sort(function (a, b) { return a.login.localeCompare(b.login); });
    render();
  })
  .catch(function (ex) {
    document.getElementById("page-error").textContent = ex.message;
    createBtn.hidden = true;
  });

document.getElementById("q").addEventListener("input", render);
