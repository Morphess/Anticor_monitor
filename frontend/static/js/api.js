// Спільний клієнт API та допоміжні функції кабінетів.
// Усі запити йдуть на той самий сервер (закритий контур, без зовнішніх ресурсів).
(function () {
  "use strict";

  const TOKEN_KEY = "anticor_token";
  const ROLE_KEY = "anticor_role";

  function store() {
    try { return window.localStorage; } catch (e) { return null; }
  }
  function getItem(key) {
    try { const s = store(); return s ? s.getItem(key) : null; } catch (e) { return null; }
  }
  function setItem(key, value) {
    try {
      const s = store();
      if (!s) return;
      if (value === null || value === undefined) s.removeItem(key); else s.setItem(key, value);
    } catch (e) { /* сховище недоступне — працюємо без нього */ }
  }

  class ApiError extends Error {
    constructor(status, detail, body) {
      super(detail);
      this.status = status;
      this.body = body || null;
    }
  }

  function detailText(body, status) {
    if (!body) return "Помилка " + status;
    if (typeof body.detail === "string") return body.detail;
    if (body.detail && typeof body.detail === "object" && body.detail.message) return body.detail.message;
    if (Array.isArray(body.detail)) {
      return body.detail.map(function (d) { return d.msg || JSON.stringify(d); }).join("; ");
    }
    return "Помилка " + status;
  }

  async function request(method, url, body, opts) {
    opts = opts || {};
    const headers = { Accept: "application/json" };
    const token = getItem(TOKEN_KEY);
    if (token) headers.Authorization = "Bearer " + token;
    let payload;
    if (body instanceof FormData) {
      payload = body;
    } else if (body instanceof URLSearchParams) {
      payload = body;
      headers["Content-Type"] = "application/x-www-form-urlencoded";
    } else if (body !== undefined) {
      payload = JSON.stringify(body);
      headers["Content-Type"] = "application/json";
    }
    const res = await fetch(url, { method: method, headers: headers, body: payload });
    if (res.status === 401 && !opts.noRedirect) {
      Api.logout(true);
      throw new ApiError(401, "Сесія завершилась");
    }
    if (res.status === 204) return null;
    let data = null;
    const text = await res.text();
    if (text) {
      try { data = JSON.parse(text); } catch (e) { data = null; }
    }
    if (!res.ok) throw new ApiError(res.status, detailText(data, res.status), data);
    return data;
  }

  const Api = {
    ApiError: ApiError,
    get: function (url, o) { return request("GET", url, undefined, o); },
    post: function (url, b, o) { return request("POST", url, b, o); },
    patch: function (url, b, o) { return request("PATCH", url, b, o); },
    del: function (url, o) { return request("DELETE", url, undefined, o); },

    token: function () { return getItem(TOKEN_KEY); },
    setToken: function (t) { setItem(TOKEN_KEY, t); },
    role: function () { return getItem(ROLE_KEY); },
    setRole: function (r) { setItem(ROLE_KEY, r); },
    pref: function (k, v) {
      if (v === undefined) return getItem("anticor_" + k);
      setItem("anticor_" + k, v);
    },

    logout: function (expired) {
      setItem(TOKEN_KEY, null);
      setItem(ROLE_KEY, null);
      const next = expired ? "?next=" + encodeURIComponent(location.pathname) : "";
      location.href = "/login" + next;
    },

    // Сторінка доступна лише з токеном.
    requireLogin: function () {
      if (!getItem(TOKEN_KEY)) {
        location.href = "/login?next=" + encodeURIComponent(location.pathname);
        return false;
      }
      return true;
    },

    // Завантажує всі сторінки списку (API віддає не більше limit записів за раз).
    getAll: async function (url, pageSize, skipParam) {
      skipParam = skipParam || "skip";
      const out = [];
      const sep = url.indexOf("?") === -1 ? "?" : "&";
      for (let skip = 0; skip < 20000; skip += pageSize) {
        const page = await request("GET", url + sep + skipParam + "=" + skip + "&limit=" + pageSize);
        if (!Array.isArray(page)) throw new Error("API повернув не список: " + url);
        out.push.apply(out, page);
        if (!page || page.length < pageSize) break;
      }
      return out;
    },

    measures: function (programId) {
      const q = programId ? "/api/measures/?program_id=" + encodeURIComponent(programId) : "/api/measures/";
      return Api.getAll(q, 100, "skip");
    },
    executions: function (period) {
      return Api.getAll("/api/executions/?period=" + encodeURIComponent(period), 500, "offset");
    },
    executionUrl: function (executionId) {
      return "/api/executions/" + encodeURIComponent(executionId);
    },
  };

  // ---------- Ролі ----------
  Api.ROLES = {
    VYK: { name: "Виконавець", home: "/executor" },
    MAIN_KOORD: { name: "Головний координатор", home: "/main-coordinator" },
    KOORD: { name: "Координатор підрозділу", home: "/coordinator" },
    KER: { name: "Керівник", home: "/manager" },
    ANAL: { name: "Аналітик", home: "/analyst" },
    ADMIN: { name: "Адміністратор", home: "/admin" },
  };

  // ---------- Звітні періоди (півріччя) ----------
  Api.currentPeriod = function (d) {
    d = d || new Date();
    return d.getFullYear() + "-H" + (d.getMonth() < 6 ? 1 : 2);
  };
  Api.periodsBetween = function (start, end) {
    const out = [];
    const a = new Date(start), b = new Date(end);
    if (isNaN(a) || isNaN(b)) return out;
    for (let y = a.getFullYear(); y <= b.getFullYear(); y++) {
      for (let h = 1; h <= 2; h++) {
        const ps = new Date(y, h === 1 ? 0 : 6, 1), pe = new Date(y, h === 1 ? 5 : 11, 30);
        if (pe >= a && ps <= b) out.push(y + "-H" + h);
      }
    }
    return out;
  };
  Api.periodLabel = function (p) {
    const m = /^(\d{4})-H([12])$/.exec(p || "");
    return m ? (m[2] === "1" ? "I півріччя " : "II півріччя ") + m[1] : p;
  };
  // Заповнює <select> періодів і запам'ятовує вибір.
  Api.fillPeriods = function (select, programs) {
    const set = new Set([Api.currentPeriod()]);
    (programs || []).forEach(function (p) {
      Api.periodsBetween(p.start_date, p.end_date).forEach(function (x) { set.add(x); });
    });
    const list = Array.from(set).sort();
    const saved = Api.pref("period");
    select.innerHTML = "";
    list.forEach(function (p) {
      const o = document.createElement("option");
      o.value = p;
      o.textContent = Api.periodLabel(p);
      select.appendChild(o);
    });
    select.value = list.indexOf(saved) !== -1 ? saved : Api.currentPeriod();
    if (!select.dataset.periodPreferenceBound) {
      select.addEventListener("change", function () { Api.pref("period", select.value); });
      select.dataset.periodPreferenceBound = "true";
    }
    return select.value;
  };

  Api.requireRole = async function (expectedRole) {
    if (!Api.requireLogin()) return false;

    try {
      const me = await Api.get("/api/auth/me", { noRedirect: true });
      const role = me && me.role_id;
      const cabinet = Api.ROLES[role];

      if (!cabinet) {
        Api.logout(false);
        return false;
      }

      Api.setRole(role);
      Api.me = me;
      document.querySelectorAll('[data-nav-role]').forEach(function (a) {
        a.hidden = a.dataset.navRole !== role;
        a.setAttribute('aria-current', a.pathname === location.pathname ? 'page' : 'false');
      });
      if (!(Array.isArray(expectedRole) ? expectedRole.includes(role) : role === expectedRole)) {
        location.replace(cabinet.home);
        return false;
      }
      return true;
    } catch (err) {
      if (err.status === 401) {
        Api.logout(true);
      } else {
        Api.showError(err);
      }
      return false;
    }
  };

  // Статус перевірки, а не старий прогрес виконання.
  Api.STATUS = {
    done: { label: "Погоджено", cls: "st-done" },
    review: { label: "Очікує рішення", cls: "st-review" },
    rework: { label: "Повернуто", cls: "st-rework" },
    not: { label: "Не подано", cls: "st-not" },
    work: { label: "Очікує рішення", cls: "st-review" },
    none: { label: "Не подано", cls: "" },
  };
  Api.statusOf = function (ex) {
    if (!ex) return "none";
    if (ex.document_changed) return "rework";
    if (ex.status === "approved") return "done";
    if (ex.status === "pending") return "review";
    if (ex.status === "rejected") return "rework";
    return "none";
  };
  Api.orderNumber = function (ex) { return ex && ex.order_number || ""; };
  Api.noteOf = function (ex) { return ex && ex.rejection_reason || ""; };
  Api.withOrder = function (description, number) { return String(description || "") + String(number || ""); };

  // ---------- Підрозділи ----------
  Api.DEPARTMENTS = {};
  Api.loadDepartmentNames = async function () {
    // Загальний довідник підрозділів належить ADMIN. Не робимо зайвий
    // заборонений HTTP-запит від MAIN_KOORD, KOORD чи VYK.
    if (!Api.me || Api.me.role_id !== "ADMIN") return;
    const rows = await Api.get("/api/departments/");
    (rows || []).forEach(function (r) { Api.DEPARTMENTS[r.id] = r.name; });
  };
  Api.deptName = function (id) {
    return id ? (Api.DEPARTMENTS[id] || "Підрозділ " + id) : "Не призначено";
  };

  // ---------- Розділи ----------
  // Для MAIN_KOORD / KOORD / VYK список розділів доступної програми
  // отримуємо через program-routing (не через ADMIN-only /api/sections/).
  Api.sections = async function (programIds) {
    const ids = Array.from(new Set(programIds || []));
    const map = {};
    await Promise.all(ids.map(async function (id) {
      const rows = await Api.get("/api/program-routing/programs/" +
        encodeURIComponent(id) + "/sections");
      (rows || []).forEach(function (section) { map[section.id] = section; });
    }));
    return map;
  };
  Api.sectionTitle = function (map, id) {
    const s = (map || {})[id];
    if (s) return s.number + ". " + s.title;
    return "Розділ " + (id || "—");
  };

  // ---------- Поточний користувач ----------
  // Токен містить лише id користувача (поле sub). Підпис перевіряє сервер;
  // тут id потрібен тільки, щоб показати виконавцю його заходи.
  Api.userId = function () {
    if (Api.me && Api.me.id !== undefined) return Number(Api.me.id);
    const t = Api.token();
    if (!t) return null;
    try {
      const part = t.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
      const json = decodeURIComponent(atob(part).split("").map(function (c) {
        return "%" + ("00" + c.charCodeAt(0).toString(16)).slice(-2);
      }).join(""));
      const id = parseInt(JSON.parse(json).sub, 10);
      return isNaN(id) ? null : id;
    } catch (e) {
      return null;
    }
  };

  // ---------- Накази, підтвердження, перенесення ----------
  // Сервер сам обмежує видимість: виконавець бачить лише свої заходи,
  // координатор/керівник/аналітик — свою програму.
  Api.groupBy = function (list, key) {
    const map = {};
    (list || []).forEach(function (x) { (map[x[key]] = map[x[key]] || []).push(x); });
    return map;
  };

  // Таблицю evidences видалено. Документ прив’язаний до executions.
  // SHA-256 не обчислюється з номера наказу у браузері.
  // Для підтвердження сервер використовує хеш фактичної order_versions.

  // Сповіщення про зміну наказів (новий бекенд). null — бекенд їх не підтримує (404).
  Api.orderAlerts = async function () {
    try {
      return await Api.get("/api/order-change-alerts/?limit=100", { noRedirect: true });
    } catch (e) {
      if (e.status === 404 || e.status === 405) return null;
      throw e;
    }
  };

  Api.deadlineChanges = function () { return Api.getAll("/api/deadline-changes/", 100, "skip"); };
  // Не дає впасти сторінці, якщо роль не має доступу до допоміжних даних.
  Api.optional = async function (promise) {
    try { return { ok: true, data: await promise }; }
    catch (e) { return { ok: false, data: [], error: e }; }
  };
  Api.normNumber = function (s) {
    return String(s || "").replace(/^№\s*/, "").replace(/\s+/g, "").toLowerCase();
  };
  Api.findOrder = function (orders, number) {
    const n = Api.normNumber(number);
    return (orders || []).filter(function (o) { return Api.normNumber(o.number) === n; })[0] || null;
  };
  Api.docLink = function (url, text) {
    if (!url || !/^https?:\/\//i.test(url)) return document.createTextNode(text);
    return Api.el("a", { href: url, target: "_blank", rel: "noopener noreferrer", text: text });
  };


  // ---------- Risk Flags (обов'язковий program_id; RF8 доступний у поточному періоді) ----------
  Api.FLAGS = {
    RF1: "Прострочений захід", RF2: "Немає підтвердження",
    RF3: "Формальне закриття", RF4: "Формальний опис результату",
    RF5: "Показник нижче цілі", RF6: "Перенесення строків / прострочення",
    RF7a: "Виконання поза періодом", RF7b: "Пізнє підтвердження",
    RF7c: "Відсутнє пояснення", RF7d: "Високий ризик без заходів",
    RF7e: "Передчасний опис", RF8: "Невідомий номер наказу",
  };
  Api.OBJECT_TYPES = { zakhid: "Захід", pidrozdil: "Підрозділ", ryzyk: "Ризик" };
  Api.flagsAsOf = function (period) {
    const m = /^(\d{4})-H([12])$/.exec(period || "");
    if (!m) return Api.today();
    const end = m[1] + (m[2] === "1" ? "-06-30" : "-12-31");
    return Api.today() > end ? Api.today() : end;
  };
  Api.riskFlags = async function (programId, period, code) {
    if (!programId || !/^(\d{4})-H[12]$/.test(period || "")) {
      return { ok: false, data: [], reason: "Оберіть програму та звітний період" };
    }
    const startOfPeriod = period.slice(0, 4) + (period.endsWith('H1') ? '-01-01' : '-07-01');
    if (startOfPeriod > Api.today()) return {ok:false,data:[],reason:'Цей період ще не почався'};
    const end = Api.flagsAsOf(period);
    const periodEnd = period.slice(0, 4) + (period.endsWith('H1') ? '-06-30' : '-12-31');
    // API вимагає завершеного періоду для RF1–RF7, але RF8 можна дивитися зараз.
    const onlyRF8 = periodEnd > Api.today();
    if (onlyRF8 && code && code !== "RF8") return {ok: true, data: []};
    let url = "/api/risk-flags/?program_id=" + encodeURIComponent(programId)
      + "&period=" + encodeURIComponent(period)
      + "&as_of=" + encodeURIComponent(onlyRF8 ? Api.today() : end);
    if (onlyRF8 || code) url += "&code=" + encodeURIComponent(onlyRF8 ? "RF8" : code);
    const result = await Api.optional(Api.get(url));
    if (onlyRF8) result.note = "Триває звітний період: наразі доступний лише RF8";
    return result;
  };
  Api.flagBadge = function (f) {
    return Api.el("span", { class: "flag", title: (Api.FLAGS[f.code] || f.message) + (f.explanation ? ": " + f.explanation : ""), text: f.code });
  };

  // Документи API закриті Bearer JWT; звичайне <a href> неавторизоване.
  Api.downloadProtected = async function (path, filename) {
    if (!path || !path.startsWith("/api/")) throw new Error("Некоректний маршрут документа");
    const token = Api.token();
    if (!token) { Api.logout(true); return; }
    const response = await fetch(path, { headers: { Authorization: "Bearer " + token } });
    if (response.status === 401) { Api.logout(true); return; }
    if (!response.ok) {
      let detail = "Помилка відкриття документа: " + response.status;
      try { const j = await response.json(); detail = detailText(j, response.status); } catch (_) {}
      throw new Api.ApiError(response.status, detail);
    }
    const blobUrl = URL.createObjectURL(await response.blob());
    const link = document.createElement("a");
    link.href = blobUrl; link.download = filename || "document";
    document.body.appendChild(link); link.click(); link.remove();
    setTimeout(function () { URL.revokeObjectURL(blobUrl); }, 60000);
  };
  // Open a protected PDF in a new tab; Bearer JWT stays in fetch, never in URL.
  Api.openProtected = async function (path) {
    if (!path || !path.startsWith('/api/')) throw new Error('Некоректний маршрут документа');
    // Must open synchronously from button click to avoid the popup blocker.
    const tab = window.open('about:blank', '_blank');
    if (!tab) throw new Error('Дозвольте відкриття вкладок у браузері');
    try {
      tab.document.title = 'Перегляд наказу';
      tab.document.body.textContent = 'Відкриваємо документ…';
      const response = await fetch(path, { headers: {Authorization: 'Bearer ' + Api.token()} });
      if (!response.ok) {
        let message = 'Не вдалося відкрити документ (' + response.status + ')';
        try { message = detailText(await response.json(), response.status); } catch (_) {}
        throw new Error(message);
      }
      const blob = await response.blob();
      const blobUrl = URL.createObjectURL(blob);
      tab.location.href = blobUrl;
      // Keep URL alive while the browser loads; revoke on delay to limit memory usage.
      setTimeout(function () { URL.revokeObjectURL(blobUrl); }, 300000);
    } catch (error) {
      tab.close(); throw error;
    }
  };
  // ---------- Дрібниці ----------
  Api.fmtDate = function (iso) {
    if (!iso) return "";
    const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
    return m ? m[3] + "." + m[2] + "." + m[1] : iso;
  };
  Api.today = function () {
    const d = new Date();
    const z = function (n) { return (n < 10 ? "0" : "") + n; };
    return d.getFullYear() + "-" + z(d.getMonth() + 1) + "-" + z(d.getDate());
  };
  // Номер розділу з ідентифікатора (R2 -> 2).
  Api.sectionNo = function (id) {
    return String(id == null ? "" : id).replace(/^[A-Za-zА-Яа-я]+/, "");
  };
  Api.compareSections = function (a, b) {
    return String(a).localeCompare(String(b), "uk", { numeric: true });
  };
  Api.measureNo = function (m) {
    return m.sequence_number == null ? String(m.id || "—") : Api.sectionNo(m.section_id) + "." + m.sequence_number;
  };
  Api.byMeasureOrder = function (a, b) {
    return Api.compareSections(a.section_id, b.section_id) || (a.sequence_number - b.sequence_number);
  };
  Api.el = function (tag, attrs, children) {
    const n = document.createElement(tag);
    if (attrs) Object.keys(attrs).forEach(function (k) {
      if (k === "class") n.className = attrs[k];
      else if (k === "text") n.textContent = attrs[k];
      else if (k.slice(0, 2) === "on") n.addEventListener(k.slice(2), attrs[k]);
      else if (attrs[k] !== null && attrs[k] !== undefined && attrs[k] !== false) n.setAttribute(k, attrs[k]);
    });
    (children || []).forEach(function (c) {
      if (c === null || c === undefined) return;
      n.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
    });
    return n;
  };
  Api.statusBadge = function (key) {
    const s = Api.STATUS[key] || Api.STATUS.none;
    return Api.el("span", { class: "st " + s.cls, text: s.label });
  };
  // ---------- Пагінація ----------
  // Номери сторінок: 1 … 4 5 6 … 20.
  Api.pageList = function (page, pages) {
    const out = [];
    for (let i = 1; i <= pages; i++) {
      if (i === 1 || i === pages || Math.abs(i - page) <= 1) out.push(i);
      else if (out[out.length - 1] !== "…") out.push("…");
    }
    return out;
  };
  // Панель: «Показано 1–25 з 1126», розмір сторінки, перемикач сторінок.
  // state = {page, size}; opts = {sizes, rerender, onSize, noun}.
  Api.renderPager = function (box, state, total, opts) {
    const el = Api.el;
    const pages = Math.max(1, Math.ceil(total / state.size));
    if (state.page > pages) state.page = pages;
    const from = total ? (state.page - 1) * state.size + 1 : 0;
    const to = Math.min(total, state.page * state.size);
    const size = el("select", { "aria-label": "Записів на сторінці" });
    opts.sizes.forEach(function (n) { size.appendChild(el("option", { value: String(n), text: String(n) })); });
    size.value = String(state.size);
    size.addEventListener("change", function () {
      state.size = Number(size.value);
      state.page = 1;
      if (opts.onSize) opts.onSize(state.size);
      opts.rerender();
    });
    function pageBtn(label, target, aria, current) {
      const b = el("button", { type: "button", class: "icon-btn" + (current ? " current" : ""), text: label, "aria-label": aria });
      if (current) b.setAttribute("aria-current", "page");
      if (target < 1 || target > pages) b.disabled = true;
      else b.addEventListener("click", function () { state.page = target; opts.rerender(); });
      return b;
    }
    const nav = el("nav", { class: "pages", "aria-label": "Сторінки" });
    nav.appendChild(pageBtn("‹", state.page - 1, "Попередня сторінка", false));
    Api.pageList(state.page, pages).forEach(function (p) {
      nav.appendChild(p === "…" ? el("span", { class: "gap", text: "…" }) : pageBtn(String(p), p, "Сторінка " + p, p === state.page));
    });
    nav.appendChild(pageBtn("›", state.page + 1, "Наступна сторінка", false));
    box.replaceChildren(
      el("span", { class: "pager-info", text: total ? "Показано " + from + "–" + to + " з " + total + (opts.noun ? " " + opts.noun : "") : "Нічого не знайдено" }),
      el("label", { class: "pager-size" }, ["На сторінці", size]),
      pages > 1 ? nav : el("span")
    );
  };

  Api.showError = function (err) {
    const box = document.getElementById("page-error");
    if (!box) return;
    if (!err) { box.classList.add("hidden"); return; }
    box.textContent = err.message || String(err);
    box.classList.remove("hidden");
  };

  // ---------- Тема ----------
  // Без вибору користувача діє системна тема; вибір зберігається в localStorage.
  Api.theme = function () {
    const set = document.documentElement.getAttribute("data-theme");
    if (set === "light" || set === "dark") return set;
    return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  };
  Api.setTheme = function (theme) {
    document.documentElement.setAttribute("data-theme", theme);
    setItem("anticor_theme", theme);
  };

  document.addEventListener("click", function (e) {
    const t = e.target.closest("[data-logout]");
    if (t) { e.preventDefault(); Api.logout(false); return; }
    const th = e.target.closest("[data-theme-toggle]");
    if (th) { e.preventDefault(); Api.setTheme(Api.theme() === "dark" ? "light" : "dark"); }
  });
  document.addEventListener("DOMContentLoaded", function () {
    const r = document.querySelector("[data-role-name]");
    const role = Api.ROLES[Api.role()];
    if (r && role && !r.textContent.trim()) r.textContent = role.name;
    labelTables();
    // Таблиці малюються скриптами — підписуємо нові клітинки після кожної зміни DOM.
    let queued = false;
    new MutationObserver(function () {
      if (queued) return;
      queued = true;
      requestAnimationFrame(function () { queued = false; labelTables(); });
    }).observe(document.body, { childList: true, subtree: true });
  });

  // Підписи клітинок для мобільного вигляду таблиць (CSS показує data-label поруч зі значенням).
  function labelTables() {
    document.querySelectorAll("table.grid").forEach(function (table) {
      const heads = Array.from(table.querySelectorAll("thead th")).map(function (th) { return th.querySelector(".sr-only") ? "" : th.textContent.trim(); });
      if (!heads.length) return;
      table.querySelectorAll("tbody tr").forEach(function (tr) {
        let col = 0;
        Array.from(tr.children).forEach(function (td) {
          const span = Number(td.getAttribute("colspan")) || 1;
          const label = span === 1 ? heads[col] : "";
          if (label && td.getAttribute("data-label") !== label) td.setAttribute("data-label", label);
          col += span;
        });
      });
    });
  }

  window.Api = Api;
})();
