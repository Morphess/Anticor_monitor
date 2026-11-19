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
  // SHA-256 у hex. crypto.subtle є лише в захищеному контексті (https, localhost),
  // тому для звичайного http у закритому контурі — власна реалізація.
  Api.sha256Hex = async function (text) {
    const bytes = new TextEncoder().encode(text);
    if (window.crypto && window.crypto.subtle) {
      const buf = await window.crypto.subtle.digest("SHA-256", bytes);
      return Array.from(new Uint8Array(buf)).map(function (b) { return b.toString(16).padStart(2, "0"); }).join("");
    }
    return sha256Fallback(bytes);
  };
  Api.sha256Fallback = function (bytes) { return sha256Fallback(bytes); }; // для перевірки
  function sha256Fallback(bytes) {
    const K = [0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5, 0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da, 0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070, 0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3, 0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2];
    const H = [0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19];
    const len = bytes.length;
    const total = ((len + 9 + 63) >> 6) << 6;
    const m = new Uint8Array(total);
    m.set(bytes);
    m[len] = 0x80;
    const bits = len * 8;
    for (let i = 0; i < 4; i++) m[total - 1 - i] = (bits >>> (8 * i)) & 0xff;
    m[total - 5] = Math.floor(bits / 0x100000000) & 0xff;
    const w = new Uint32Array(64);
    const rotr = function (x, n) { return (x >>> n) | (x << (32 - n)); };
    for (let off = 0; off < total; off += 64) {
      for (let i = 0; i < 16; i++) w[i] = (m[off + 4 * i] << 24) | (m[off + 4 * i + 1] << 16) | (m[off + 4 * i + 2] << 8) | m[off + 4 * i + 3];
      for (let i = 16; i < 64; i++) {
        const s0 = rotr(w[i - 15], 7) ^ rotr(w[i - 15], 18) ^ (w[i - 15] >>> 3);
        const s1 = rotr(w[i - 2], 17) ^ rotr(w[i - 2], 19) ^ (w[i - 2] >>> 10);
        w[i] = (w[i - 16] + s0 + w[i - 7] + s1) | 0;
      }
      let a = H[0], b = H[1], c = H[2], d = H[3], e = H[4], f = H[5], g = H[6], h = H[7];
      for (let i = 0; i < 64; i++) {
        const t1 = (h + (rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25)) + ((e & f) ^ (~e & g)) + K[i] + w[i]) | 0;
        const t2 = ((rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22)) + ((a & b) ^ (a & c) ^ (b & c))) | 0;
        h = g; g = f; f = e; e = (d + t1) | 0; d = c; c = b; b = a; a = (t1 + t2) | 0;
      }
      H[0] = (H[0] + a) | 0; H[1] = (H[1] + b) | 0; H[2] = (H[2] + c) | 0; H[3] = (H[3] + d) | 0;
      H[4] = (H[4] + e) | 0; H[5] = (H[5] + f) | 0; H[6] = (H[6] + g) | 0; H[7] = (H[7] + h) | 0;
    }
    return H.map(function (x) { return (x >>> 0).toString(16).padStart(8, "0"); }).join("");
  }

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

  Api.analyzeOrder = function (orderId, file) {
    const form = new FormData();
    form.append("file", file);
    return Api.post(
      "/api/orders/" + encodeURIComponent(orderId) + "/analyze",
      form
    );
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
