// Запити до аналітика й аналітичні звіти (вкладка в кабінетах керівника й аналітика).
// Керівник (KER) надсилає запит і читає звіти; аналітик (ANAL) бере запит у роботу й надсилає звіт.
// Дані — /api/analytics/*; графіки звіту — charts.js.
(function () {
  var el = Charts.el;
  var app = document.getElementById("reports-app");
  var badge = document.getElementById("reports-count");
  var INBOX = null, view = { name: "list" }, flash = "", analystData = null;

  var STATUS = {
    KER: { new: "Надіслано, очікує аналітика", in_progress: "Аналітик готує звіт", answered: "Звіт готовий" },
    ANAL: { new: "Новий запит", in_progress: "У роботі", answered: "Звіт надіслано" }
  };
  var STATUS_BADGE = {
    new: "bg-warning-subtle text-warning-emphasis border-warning-subtle",
    in_progress: "bg-primary-subtle text-primary-emphasis border-primary-subtle",
    answered: "bg-success-subtle text-success-emphasis border-success-subtle"
  };

  function statusBadge(r) {
    return el("span", "badge border fw-semibold " + STATUS_BADGE[r.status], STATUS[INBOX.role][r.status]);
  }
  function isoIn(days) {
    var d = new Date();
    d.setDate(d.getDate() + days);
    return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
  }
  function field(label, control, help) {
    var box = el("div");
    var l = el("label", "form-label fw-semibold", label);
    control.id = control.id || "f-" + Math.random().toString(36).slice(2);
    l.htmlFor = control.id;
    box.appendChild(l);
    box.appendChild(control);
    if (help) box.appendChild(el("div", "form-text", help));
    return box;
  }
  function programSelect(value) {
    var s = el("select", "form-select");
    var all = el("option", "", "Усі програми"); all.value = ""; s.appendChild(all);
    INBOX.programs.forEach(function (p) { var o = el("option", "", p.name); o.value = p.id; s.appendChild(o); });
    s.value = value || "";
    return s;
  }
  function backButton(text) {
    var b = el("button", "btn btn-link link-dark px-0 mb-2 d-print-none", "← " + text);
    b.type = "button";
    b.onclick = function () { view = { name: "list" }; render(); };
    return b;
  }
  function guide(key, summary, items) {
    var d = el("details", "card card-body mb-3 small guide");
    d.appendChild(el("summary", "fw-semibold", summary));
    var ul = el("ul", "mt-2 mb-0 ps-3");
    items.forEach(function (t) { ul.appendChild(el("li", "", t)); });
    d.appendChild(ul);
    try {
      if (!localStorage.getItem(key)) d.open = true;
      d.addEventListener("toggle", function () { if (!d.open) localStorage.setItem(key, "1"); });
    } catch (e) { d.open = true; }
    return d;
  }
  function updateBadge() {
    var n = INBOX.role === "KER"
      ? INBOX.reports.filter(function (r) { return r.unread; }).length
      : INBOX.requests.filter(function (r) { return r.status === "new"; }).length;
    badge.textContent = n;
    badge.hidden = !n;
  }

  // ---------- Список звітів (спільний) ----------
  function reportList() {
    if (!INBOX.reports.length) {
      return el("p", "text-secondary", INBOX.role === "KER"
        ? "Звітів ще немає. Надішліть запит аналітику — звіт з'явиться тут."
        : "Ви ще не надсилали звітів.");
    }
    var list = el("div", "list-group mb-4");
    INBOX.reports.forEach(function (r) {
      var b = el("button", "list-group-item list-group-item-action py-3");
      b.type = "button";
      var top = el("div", "d-flex justify-content-between gap-2 align-items-start");
      top.appendChild(el("span", "fw-semibold", r.title));
      if (r.unread) top.appendChild(el("span", "badge rounded-pill text-bg-danger", "Новий"));
      b.appendChild(top);
      b.appendChild(el("div", "small text-secondary", r.program + " · " + r.created_at + " · " + r.author));
      if (r.request_topic) b.appendChild(el("div", "small text-secondary", "На запит: «" + r.request_topic + "»"));
      b.onclick = function () { view = { name: "report", id: r.id }; render(); };
      list.appendChild(b);
    });
    return list;
  }

  // ---------- Керівник ----------
  function requestForm() {
    var f = el("form", "card card-body mb-4");
    f.noValidate = true;
    f.appendChild(el("h3", "h5 mb-3", "Запит аналітичного звіту"));
    var topic = el("input", "form-control");
    topic.maxLength = 200;
    topic.placeholder = "Наприклад: чому відстає розділ «Прозорість закупівель»";
    var question = el("textarea", "form-control");
    question.rows = 3;
    question.maxLength = 4000;
    question.placeholder = "Що саме потрібно з'ясувати, для якого рішення";
    var program = programSelect("");
    var due = el("input", "form-control");
    due.type = "date";
    due.min = isoIn(0);
    due.value = isoIn(7);

    var row = el("div", "row g-3");
    var c1 = el("div", "col-12"); c1.appendChild(field("Тема", topic)); row.appendChild(c1);
    var c2 = el("div", "col-12"); c2.appendChild(field("Що потрібно з'ясувати", question, "Чим конкретніше питання, тим кориснішим буде звіт.")); row.appendChild(c2);
    var c3 = el("div", "col-md-8"); c3.appendChild(field("Програма", program)); row.appendChild(c3);
    var c4 = el("div", "col-md-4"); c4.appendChild(field("Потрібно до", due)); row.appendChild(c4);
    f.appendChild(row);

    var err = el("div", "text-danger small mt-3");
    err.setAttribute("role", "alert");
    f.appendChild(err);
    var actions = el("div", "d-flex justify-content-end gap-2 mt-3");
    var cancel = el("button", "btn btn-outline-dark", "Скасувати");
    cancel.type = "button";
    cancel.onclick = function () { view = { name: "list" }; render(); };
    var ok = el("button", "btn btn-dark", "Надіслати аналітику");
    ok.type = "submit";
    actions.appendChild(cancel);
    actions.appendChild(ok);
    f.appendChild(actions);

    f.onsubmit = function (e) {
      e.preventDefault();
      if (!topic.value.trim()) { err.textContent = "Вкажіть тему запиту"; topic.focus(); return; }
      if (!due.value) { err.textContent = "Вкажіть, до якої дати потрібен звіт"; due.focus(); return; }
      ok.disabled = true;
      Api.post("/api/analytics/requests", {
        topic: topic.value.trim(), question: question.value.trim(), program_id: program.value || null, due_on: due.value
      }).then(function (r) {
        INBOX.requests.unshift(r);
        flash = "Запит «" + r.topic + "» надіслано аналітику";
        view = { name: "list" };
        render();
      }).catch(function (ex) { err.textContent = ex.message; ok.disabled = false; });
    };
    setTimeout(function () { topic.focus(); }, 0);
    return f;
  }

  function managerList() {
    app.appendChild(guide("reports_guide_ker", "Як отримати аналітику", [
      "Аналітичні дані для вас готує аналітик. Натисніть «Запросити аналітичний звіт», опишіть, що потрібно з'ясувати, і вкажіть строк.",
      "Стан запиту видно в таблиці «Мої запити»: надіслано → аналітик готує звіт → звіт готовий.",
      "У звіті — висновки й пропозиції аналітика та графіки, зафіксовані на дату звіту. Нові звіти позначено червоною міткою."
    ]));
    var head = el("div", "d-flex flex-wrap justify-content-between align-items-center gap-2 mb-3");
    head.appendChild(el("h2", "h5 mb-0", "Отримані звіти"));
    if (view.name !== "new-request") {
      var b = el("button", "btn btn-dark", "Запросити аналітичний звіт");
      b.type = "button";
      b.onclick = function () { view = { name: "new-request" }; render(); };
      head.appendChild(b);
    }
    app.appendChild(head);
    if (view.name === "new-request") app.appendChild(requestForm());
    app.appendChild(reportList());

    app.appendChild(el("h2", "h5 mb-3", "Мої запити"));
    if (!INBOX.requests.length) { app.appendChild(el("p", "text-secondary", "Запитів ще не було.")); return; }
    var wrap = el("div", "table-responsive border rounded");
    var t = el("table", "table align-middle mb-0 requests-table");
    var thead = el("thead"), hr = el("tr");
    ["Тема", "Програма", "Потрібно до", "Стан", ""].forEach(function (h) { hr.appendChild(el("th", "small text-secondary fw-normal", h)); });
    thead.appendChild(hr);
    t.appendChild(thead);
    var body = el("tbody");
    INBOX.requests.forEach(function (r) {
      var tr = el("tr");
      var td = el("td");
      td.appendChild(el("div", "fw-semibold", r.topic));
      if (r.question) td.appendChild(el("div", "small text-secondary text-prewrap", r.question));
      tr.appendChild(td);
      tr.appendChild(el("td", "small", r.program));
      var dueTd = el("td", "text-nowrap", r.due);
      if (r.overdue) dueTd.appendChild(el("div", "small text-danger fw-semibold", "строк минув"));
      tr.appendChild(dueTd);
      var st = el("td"); st.appendChild(statusBadge(r)); tr.appendChild(st);
      var act = el("td", "text-end");
      if (r.report_id) {
        var o = el("button", "btn btn-sm btn-outline-dark text-nowrap", "Відкрити звіт");
        o.type = "button";
        o.onclick = function () { view = { name: "report", id: r.report_id }; render(); };
        act.appendChild(o);
      }
      tr.appendChild(act);
      body.appendChild(tr);
    });
    t.appendChild(body);
    wrap.appendChild(t);
    app.appendChild(wrap);
  }

  // ---------- Аналітик ----------
  function requestCard(r) {
    var card = el("article", "card mb-3");
    var b = el("div", "card-body");
    var top = el("div", "d-flex flex-wrap justify-content-between align-items-center gap-2");
    top.appendChild(statusBadge(r));
    top.appendChild(el("span", "small " + (r.overdue ? "text-danger fw-semibold" : "text-secondary"),
      (r.overdue ? "⚠ строк минув: " : "Потрібно до ") + r.due));
    b.appendChild(top);
    b.appendChild(el("h3", "h5 mt-2 mb-1", r.topic));
    if (r.question) b.appendChild(el("p", "text-prewrap mb-2", r.question));
    var meta = "Програма: " + r.program + " · від: " + r.requested_by + ", " + r.requested_at;
    if (r.analyst) meta += " · виконує: " + r.analyst;
    b.appendChild(el("p", "small text-secondary mb-0", meta));
    var actions = el("div", "d-flex flex-wrap gap-2 mt-3");
    if (r.status === "new") {
      var take = el("button", "btn btn-outline-dark", "Взяти в роботу");
      take.type = "button";
      take.onclick = function () {
        take.disabled = true;
        Api.post("/api/analytics/requests/" + r.id + "/take").then(function (upd) {
          INBOX.requests = INBOX.requests.map(function (x) { return x.id === upd.id ? upd : x; });
          flash = "Запит «" + upd.topic + "» узято в роботу";
          render();
        }).catch(function (ex) { take.disabled = false; flash = ""; showError(ex.message); });
      };
      actions.appendChild(take);
    }
    var write = el("button", "btn btn-dark", "Підготувати звіт");
    write.type = "button";
    write.onclick = function () { view = { name: "compose", request: r }; render(); };
    actions.appendChild(write);
    b.appendChild(actions);
    card.appendChild(b);
    return card;
  }

  function analystList() {
    app.appendChild(guide("reports_guide_anal", "Як працювати із запитами", [
      "Керівник надсилає запит: що потрібно з'ясувати, щодо якої програми й до якої дати.",
      "Натисніть «Взяти в роботу», щоб керівник бачив, що запит опрацьовується.",
      "«Підготувати звіт» відкриває форму: напишіть висновки й пропозиції. Графіки й таблиці додаються автоматично — це зріз даних на момент надсилання, згодом він не змінюється.",
      "Звіт можна надіслати й без запиту, з власної ініціативи."
    ]));
    var head = el("div", "d-flex flex-wrap justify-content-between align-items-center gap-2 mb-3");
    head.appendChild(el("h2", "h5 mb-0", "Запити керівника"));
    var own = el("button", "btn btn-outline-dark", "Звіт з власної ініціативи");
    own.type = "button";
    own.onclick = function () { view = { name: "compose", request: null }; render(); };
    head.appendChild(own);
    app.appendChild(head);
    var active = INBOX.requests.filter(function (r) { return r.status !== "answered"; });
    if (!active.length) app.appendChild(el("p", "text-success fw-semibold", "Нових запитів немає."));
    active.forEach(function (r) { app.appendChild(requestCard(r)); });
    app.appendChild(el("h2", "h5 mt-4 mb-3", "Надіслані звіти"));
    app.appendChild(reportList());
  }

  function compose(r) {
    app.appendChild(backButton("До запитів"));
    app.appendChild(el("h2", "h4 mb-3", "Аналітичний звіт"));
    if (r) {
      var q = el("div", "alert alert-light border");
      q.appendChild(el("div", "small text-secondary", "Запит керівника · потрібно до " + r.due));
      q.appendChild(el("div", "fw-semibold", r.topic));
      if (r.question) q.appendChild(el("div", "text-prewrap mt-1", r.question));
      app.appendChild(q);
    }
    var f = el("form", "card card-body mb-3");
    f.noValidate = true;
    var title = el("input", "form-control");
    title.maxLength = 200;
    title.value = r ? r.topic : "";
    var program = programSelect(r ? r.program_id : "");
    var findings = el("textarea", "form-control");
    findings.rows = 7;
    findings.placeholder = "Наприклад: виконано 52% заходів; найбільше відстає Відділ закупівель — 3 прострочені заходи…";
    var proposals = el("textarea", "form-control");
    proposals.rows = 4;
    proposals.placeholder = "Наприклад: доручити Відділу закупівель подати план усунення прострочень до 01.12…";
    var row = el("div", "row g-3");
    var c1 = el("div", "col-md-7"); c1.appendChild(field("Назва звіту", title)); row.appendChild(c1);
    var c2 = el("div", "col-md-5"); c2.appendChild(field("Програма", program, "Від неї залежать дані, додані до звіту.")); row.appendChild(c2);
    var c3 = el("div", "col-12"); c3.appendChild(field("Висновки", findings, "Що показують дані: головні тенденції, проблемні розділи й підрозділи. Пишіть простими словами.")); row.appendChild(c3);
    var c4 = el("div", "col-12"); c4.appendChild(field("Пропозиції керівнику (необов'язково)", proposals, "Конкретні дії: що зробити, кому доручити, до якого строку.")); row.appendChild(c4);
    f.appendChild(row);
    var err = el("div", "text-danger small mt-3");
    err.setAttribute("role", "alert");
    f.appendChild(err);
    var actions = el("div", "d-flex justify-content-end gap-2 mt-3");
    var cancel = el("button", "btn btn-outline-dark", "Скасувати");
    cancel.type = "button";
    cancel.onclick = function () { view = { name: "list" }; render(); };
    var ok = el("button", "btn btn-dark", "Надіслати керівнику");
    ok.type = "submit";
    actions.appendChild(cancel);
    actions.appendChild(ok);
    f.appendChild(actions);
    app.appendChild(f);

    var preview = el("section", "mb-3");
    preview.appendChild(el("h3", "h5 mb-1", "Дані, які буде додано до звіту"));
    preview.appendChild(el("p", "small text-secondary", "Зріз фіксується в момент надсилання й надалі не змінюється. Керівник побачить саме ці показники й графіки."));
    var previewBox = el("div");
    previewBox.appendChild(el("p", "text-secondary", "Завантаження…"));
    preview.appendChild(previewBox);
    app.appendChild(preview);

    function drawPreview() { if (analystData) Charts.render(previewBox, Charts.summarize(analystData, program.value)); }
    program.addEventListener("change", drawPreview);
    if (analystData) drawPreview();
    else Api.get("/api/analyst/overview").then(function (d) { analystData = d; drawPreview(); })
      .catch(function (ex) { previewBox.textContent = ex.message; });

    f.onsubmit = function (e) {
      e.preventDefault();
      if (!title.value.trim()) { err.textContent = "Вкажіть назву звіту"; title.focus(); return; }
      if (!findings.value.trim()) { err.textContent = "Опишіть висновки: що показують дані"; findings.focus(); return; }
      ok.disabled = true;
      Api.post("/api/analytics/reports", {
        request_id: r ? r.id : null, program_id: program.value || null, title: title.value.trim(),
        findings: findings.value.trim(), proposals: proposals.value.trim()
      }).then(function (rep) {
        return Api.get("/api/analytics/inbox").then(function (data) {
          INBOX = data;
          flash = "Звіт «" + rep.title + "» надіслано керівнику";
          view = { name: "report", id: rep.id, data: rep };
          render();
        });
      }).catch(function (ex) { err.textContent = ex.message; ok.disabled = false; });
    };
    setTimeout(function () { (r ? findings : title).focus(); }, 0);
  }

  // ---------- Перегляд звіту (спільний) ----------
  function showReport(rep) {
    var bar = el("div", "d-flex flex-wrap justify-content-between align-items-center gap-2 d-print-none");
    bar.appendChild(backButton(INBOX.role === "KER" ? "До звітів" : "До запитів"));
    var print = el("button", "btn btn-sm btn-outline-dark", "Друкувати");
    print.type = "button";
    print.onclick = function () { window.print(); };
    bar.appendChild(print);
    app.appendChild(bar);

    var art = el("article");
    art.appendChild(el("div", "small text-secondary", "Аналітичний звіт"));
    art.appendChild(el("h2", "h3 mb-1", rep.title));
    art.appendChild(el("p", "small text-secondary", rep.program + " · " + rep.created_at + " · підготував: " + rep.author));
    if (rep.request_topic) {
      var q = el("div", "alert alert-light border small");
      q.appendChild(el("div", "fw-semibold", "На запит керівника: «" + rep.request_topic + "»"));
      if (rep.request_question) q.appendChild(el("div", "text-prewrap mt-1", rep.request_question));
      art.appendChild(q);
    }
    [["Висновки аналітика", rep.findings], ["Пропозиції", rep.proposals]].forEach(function (s) {
      if (!s[1]) return;
      var c = el("section", "card mb-3");
      var b = el("div", "card-body");
      b.appendChild(el("h3", "h5", s[0]));
      b.appendChild(el("p", "text-prewrap mb-0", s[1]));
      c.appendChild(b);
      art.appendChild(c);
    });
    var snap = rep.snapshot;
    art.appendChild(el("h3", "h5 mt-4 mb-1", "Дані на момент звіту"));
    art.appendChild(el("p", "small text-secondary", "Станом на " + snap.today + ", " + Charts.periodText(snap.period) +
      " Обсяг: " + snap.scope + ". Ці цифри зафіксовано й не змінюються."));
    var box = el("div");
    Charts.render(box, snap);
    art.appendChild(box);
    app.appendChild(art);
  }

  function openReport() {
    if (view.data) { showReport(view.data); return; }
    app.appendChild(el("p", "text-secondary", "Завантаження звіту…"));
    Api.get("/api/analytics/reports/" + view.id).then(function (rep) {
      INBOX.reports.forEach(function (r) { if (r.id === rep.id) r.unread = false; });
      updateBadge();
      view.data = rep;
      render();
    }).catch(function (ex) { app.textContent = ""; app.appendChild(backButton("Назад")); showError(ex.message); });
  }

  function showError(msg) { document.getElementById("page-error").textContent = msg; }

  function render() {
    app.textContent = "";
    updateBadge();
    if (flash) { app.appendChild(el("div", "alert alert-success py-2", "✓ " + flash)); flash = ""; }
    if (view.name === "report") openReport();
    else if (view.name === "compose") compose(view.request);
    else if (INBOX.role === "KER") managerList();
    else analystList();
    window.scrollTo({ top: Math.min(window.scrollY, app.getBoundingClientRect().top + window.scrollY - 16) });
  }

  Api.get("/api/analytics/inbox")
    .then(function (data) { INBOX = data; render(); })
    .catch(function (ex) { app.textContent = ""; showError(ex.message); });
})();
