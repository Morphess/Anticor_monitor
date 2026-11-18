// Вхід через API: роль і кабінет визначаються профілем із /api/auth/me.
(function () {
  "use strict";
  const form = document.getElementById("login-form");
  const errBox = document.getElementById("login-error");
  const button = form.querySelector("button[type=submit]");

  function fail(message) {
    errBox.textContent = message;
    errBox.classList.remove("hidden");
  }

  function setBusy(busy) {
    button.disabled = busy;
    form.elements.username.disabled = busy;
    form.elements.password.disabled = busy;
  }

  async function loadCabinet() {
    const me = await Api.get("/api/auth/me", { noRedirect: true });
    const role = me && me.role_id;
    const cabinet = Api.ROLES[role];
    if (!cabinet) throw new Error("Для вашої ролі кабінет не налаштований.");
    Api.setRole(role);
    return cabinet.home;
  }

  function openCabinet(path) {
    location.replace(path);
  }

  // Якщо сесія вже є, одразу відкриваємо кабінет без повторного входу.
  if (Api.token()) {
    setBusy(true);
    loadCabinet().then(openCabinet).catch(function (err) {
      Api.setToken(null);
      Api.setRole(null);
      setBusy(false);
      if (!err.status || err.status !== 401) {
        fail(err.status ? err.message : "Не вдалося зв'язатися із сервером. Спробуйте ще раз.");
      }
    });
  }

  form.addEventListener("submit", async function (e) {
    e.preventDefault();
    errBox.classList.add("hidden");
    const username = form.elements.username.value.trim();
    const password = form.elements.password.value;
    if (!username || !password) return fail("Введіть логін і пароль.");

    setBusy(true);
    try {
      const body = new URLSearchParams({ username: username, password: password });
      const result = await Api.post("/api/auth/token", body, { noRedirect: true });
      Api.setToken(result.access_token);
      openCabinet(await loadCabinet());
    } catch (err) {
      Api.setToken(null);
      Api.setRole(null);
      fail(err.status === 401 ? "Неправильний логін або пароль." : err.message);
      setBusy(false);
    }
  });
})();
