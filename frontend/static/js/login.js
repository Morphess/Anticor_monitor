// Вхід: OAuth2-форма -> JWT у localStorage -> сторінка за роллю
document.getElementById("login-form").addEventListener("submit", async function (e) {
  e.preventDefault();
  var err = document.getElementById("login-error");
  var btn = this.querySelector("button[type=submit]");
  var login = document.getElementById("login").value.trim();
  var password = document.getElementById("password").value;
  err.textContent = "";
  if (!login || !password) { err.textContent = "Введіть логін і пароль"; return; }

  btn.disabled = true;
  try {
    var res = await fetch("/api/auth/token", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ username: login, password: password })
    });
    var data = await res.json().catch(function () { return {}; });
    if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Не вдалося увійти");
    Api.setToken(data.access_token);

    var next = new URLSearchParams(location.search).get("next") || "";
    if (/^\/(?!\/)/.test(next) && next !== "/login") { location.href = next; return; }
    var me = await Api.get("/api/auth/me");
    location.href = { VYK: "/executor", ADMIN: "/admin", ANAL: "/analyst" }[me.role_id] || "/coordinator";
  } catch (ex) {
    err.textContent = ex.message === "Failed to fetch" ? "Немає зв'язку з сервером" : ex.message;
  } finally {
    btn.disabled = false;
  }
});
