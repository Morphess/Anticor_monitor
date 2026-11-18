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
    constructor(status, detail) {
      super(detail);
      this.status = status;
    }
  }

  function detailText(body, status) {
    if (!body) return "Помилка " + status;
    if (typeof body.detail === "string") return body.detail;
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
    if (body instanceof URLSearchParams) {
      payload = body;
      headers["Content-Type"] = "application/x-www-form-urlencoded";
    } else if (typeof FormData !== "undefined" && body instanceof FormData) {
      payload = body;
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
    if (!res.ok) throw new ApiError(res.status, detailText(data, res.status));
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
        out.push.apply(out, page || []);
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
    executionUrl: function (measureId, period) {
      return "/api/executions/" + encodeURIComponent(measureId) + "/" + encodeURIComponent(period);
    },
  };

  // ---------- Ролі ----------
  Api.ROLES = {
    VYK: { name: "Виконавець", home: "/executor" },
    KOORD: { name: "Координатор програми", home: "/coordinator" },
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
    select.addEventListener("change", function () { Api.pref("period", select.value); });
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
      if (role !== expectedRole) {
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

  // ---------- Статуси ----------
  // Чотири статуси координатора + службові стани з поля status.
  Api.STATUS = {
    done: { label: "Виконано", cls: "st-done" },
    review: { label: "На розгляді", cls: "st-review" },
    rework: { label: "На доопрацюванні", cls: "st-rework" },
    not: { label: "Не виконано", cls: "st-not" },
    work: { label: "У роботі", cls: "st-work" },
    none: { label: "Не розпочато", cls: "" },
  };
  Api.statusOf = function (ex) {
    if (!ex) return "not";
    if (ex.approved_by_coordinator) return "done";
    const label = (ex.status_label || "").toLowerCase();
    if (label.indexOf("доопрац") !== -1) return "rework";
    if (label.indexOf("розгляд") !== -1) return "review";
    switch (ex.status) {
      case "completed":
      case "partial": return "review";
      case "in_progress": return "work";
      case "not_started": return "none";
      default: return "not";
    }
  };
  // Тіло запиту для кожного статусу координатора (approval оновлюється окремо).
  Api.STATUS_PATCH = {
    done: { status: "completed", status_label: "Виконано" },
    review: { status: "completed", status_label: "На розгляді" },
    rework: { status: "in_progress", status_label: "На доопрацюванні" },
    not: { status: "not_completed", status_label: "Не виконано" },
  };

  // ---------- Номер наказу ----------
  // Поки немає API наказів, номер зберігається першим рядком result_description.
  const ORDER_RE = /^Наказ №\s*(\S+)\s*\n?/;
  Api.orderNumber = function (ex) {
    const m = ex && ORDER_RE.exec(ex.result_description || "");
    return m ? m[1] : "";
  };
  Api.withOrder = function (description, number) {
    const rest = (description || "").replace(ORDER_RE, "");
    return "Наказ № " + number + (rest ? "\n" + rest : "");
  };
  Api.noteOf = function (ex) {
    return ex ? (ex.result_description || "").replace(ORDER_RE, "").trim() : "";
  };

  // ---------- Підрозділи ----------
  // ЗАГЛУШКА: API довідника підрозділів ще немає, назви з синтетичного набору.
  Api.DEPARTMENTS = {
    P01: "Сектор з питань запобігання та виявлення корупції",
    P02: "Департамент кадрового забезпечення",
    P03: "Департамент закупівель",
    P04: "Фінансово-економічний департамент",
    P05: "Управління матеріально-технічного забезпечення",
    P06: "Юридичний департамент",
    P07: "Департамент освіти і науки",
    P08: "Управління цифрової трансформації",
    P09: "Управління внутрішнього аудиту",
    P10: "Управління майна і землекористування",
    P11: "Управління комунікацій",
    P12: "Військовий навчальний заклад «Умовний»",
    P13: "Військово-медичний центр «Умовний»",
    P14: "Державне підприємство «Умовний ремонтний завод»",
  };
  Api.deptName = function (id) {
    return id ? (Api.DEPARTMENTS[id] || "Підрозділ " + id) : "Не призначено";
  };

  // ---------- Розділи ----------
  // GET /api/sections зараз лише для адміністратора; для інших — номер розділу.
  Api.sections = async function () {
    try {
      const list = await Api.get("/api/sections/", { noRedirect: true });
      const map = {};
      (list || []).forEach(function (s) { map[s.id] = s; });
      return map;
    } catch (e) {
      return {};
    }
  };
  Api.sectionTitle = function (map, id) {
    const s = map[id];
    if (s) return s.number + ". " + s.title;
    return "Розділ " + Api.sectionNo(id);
  };

  // ---------- Поточний користувач ----------
  // Токен містить лише id користувача (поле sub). Підпис перевіряє сервер;
  // тут id потрібен тільки, щоб показати виконавцю його заходи.
  Api.userId = function () {
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
  Api.orders = function () { return Api.getAll("/api/orders/", 100, "skip"); };
  Api.evidences = function () { return Api.getAll("/api/evidences/", 100, "skip"); };
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

  // ---------- Risk Flags ----------
  Api.FLAGS = {
    RF1: "Прострочений захід",
    RF2: "Немає підтверджень",
    RF3: "Формальне закриття",
    RF4: "Опис повторює зміст заходу",
    RF5: "Показник нижче цільового",
    RF6: "Повторні перенесення / прострочення",
    RF7a: "Дата виконання поза періодом",
    RF7b: "Документи пізніші за виконання",
    RF7c: "Немає пояснення невиконання",
    RF7d: "Ризик без заходів",
    RF7e: "Опис для заходу, строк якого не настав",
  };
  Api.OBJECT_TYPES = { zakhid: "Захід", pidrozdil: "Підрозділ", ryzyk: "Ризик" };
  // Дата зрізу: сьогодні, але не раніше кінця періоду (так вимагає сервер).
  Api.flagsAsOf = function (period) {
    const m = /^(\d{4})-H([12])$/.exec(period || "");
    const end = m ? m[1] + (m[2] === "1" ? "-06-30" : "-12-31") : Api.today();
    return Api.today() > end ? Api.today() : end;
  };
  // Повертає {ok, data}; ok=false, коли роль не має доступу (зараз лише ADMIN).
  Api.riskFlags = function (period, asOf, code) {
    let url = "/api/risk-flags/?period=" + encodeURIComponent(period) + "&as_of=" + encodeURIComponent(asOf || Api.flagsAsOf(period));
    if (code) url += "&code=" + encodeURIComponent(code);
    return Api.optional(Api.get(url, { noRedirect: true }));
  };
  Api.flagBadge = function (f) {
    return Api.el("span", { class: "flag", title: (Api.FLAGS[f.code] || f.message) + (f.explanation ? ": " + f.explanation : ""), text: f.code });
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
    return Api.sectionNo(m.section_id) + "." + m.sequence_number;
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
  });

  window.Api = Api;
})();
