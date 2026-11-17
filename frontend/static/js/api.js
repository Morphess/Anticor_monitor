// Спільне для сторінок: JWT-токен, запити до /api, вихід.
var Api = (function () {
  var KEY = "anticor_token";

  function getToken() {
    try { return localStorage.getItem(KEY); } catch (e) { return null; }
  }
  function setToken(t) {
    try { if (t) localStorage.setItem(KEY, t); else localStorage.removeItem(KEY); } catch (e) { /* без сховища */ }
  }
  function toLogin() {
    setToken(null);
    location.href = "/login?next=" + encodeURIComponent(location.pathname);
  }

  async function request(method, url, body) {
    var headers = {};
    var token = getToken();
    if (!token) { toLogin(); throw new Error("Потрібен вхід"); }
    headers.Authorization = "Bearer " + token;
    var init = { method: method, headers: headers };
    if (body !== undefined) {
      headers["Content-Type"] = "application/json";
      init.body = JSON.stringify(body);
    }
    var res;
    try { res = await fetch(url, init); }
    catch (e) { throw new Error("Немає зв'язку з сервером. Спробуйте ще раз."); }
    if (res.status === 401) { toLogin(); throw new Error("Сесія завершилась"); }
    var data = null;
    try { data = await res.json(); } catch (e) { /* не JSON */ }
    if (!res.ok) throw new Error(data && typeof data.detail === "string" ? data.detail : "Помилка сервера (" + res.status + ")");
    return data;
  }

  // Кнопка «Вийти» в шапці
  document.addEventListener("click", function (e) {
    if (e.target.closest && e.target.closest("[data-logout]")) setToken(null);
  });

  return {
    get: function (u) { return request("GET", u); },
    post: function (u, b) { return request("POST", u, b); },
    setToken: setToken
  };
})();
