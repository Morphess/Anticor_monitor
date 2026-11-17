// Вхід: POST /api/auth/token (OAuth2-форма), далі перехід до кабінету.
(function () {
  "use strict";
  const form = document.getElementById("login-form");
  const errBox = document.getElementById("login-error");
  const roleSel = form.elements.role;
  if (Api.role() && Api.ROLES[Api.role()]) roleSel.value = Api.role();

  function fail(text) {
    errBox.textContent = text;
    errBox.classList.remove("hidden");
  }

  form.addEventListener("submit", async function (e) {
    e.preventDefault();
    errBox.classList.add("hidden");
    const username = form.elements.username.value.trim();
    const password = form.elements.password.value;
    if (!username || !password) return fail("Введіть логін і пароль.");
    const btn = form.querySelector("button[type=submit]");
    btn.disabled = true;
    try {
      const body = new URLSearchParams({ username: username, password: password });
      const res = await Api.post("/api/auth/token", body, { noRedirect: true });
      Api.setToken(res.access_token);
      // ЗАГЛУШКА: коли з'явиться GET /api/auth/me, роль братиметься з сервера.
      let role = roleSel.value;
      try {
        const me = await Api.get("/api/auth/me", { noRedirect: true });
        if (me && me.role_id) role = me.role_id;
      } catch (ignored) { /* ендпоінта ще немає */ }
      Api.setRole(role);
      const next = new URLSearchParams(location.search).get("next");
      location.href = next && next.charAt(0) === "/" && next.charAt(1) !== "/" ? next : Api.ROLES[role].home;
    } catch (err) {
      fail(err.status === 401 ? "Неправильний логін або пароль." : err.message);
    } finally {
      btn.disabled = false;
    }
  });
})();
