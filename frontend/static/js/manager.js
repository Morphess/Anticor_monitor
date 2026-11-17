// Кабінет керівника, вкладка «Рекомендації»: сигнали правил і рішення за ними.
// Дані — /api/manager/overview; рішення — POST /api/manager/decisions (лише роль KER).
// Вкладки «Аналітичні звіти» і «Програми й заходи» малюють reports.js і coordinator.js.
(function () {
  var DATA = null, view = "pending", openForm = null, busy = false, formError = {};
  var SEVERITY = { high: "Висока увага", medium: "Середня увага" };
  var BADGE = {
    high: "bg-danger-subtle text-danger-emphasis border-danger-subtle",
    medium: "bg-warning-subtle text-warning-emphasis border-warning-subtle",
    assign: "bg-success-subtle text-success-emphasis border-success-subtle",
    dismiss: "bg-secondary-subtle text-secondary-emphasis border-secondary-subtle"
  };
  function badge(kind, text) { return el("span", "badge border text-uppercase fw-semibold " + BADGE[kind], text); }

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined) e.textContent = text;
    return e;
  }
  function depName(id) {
    var d = DATA.departments.filter(function (x) { return x.id === id; })[0];
    return d ? d.name : "";
  }

  function factList(items) {
    var ul = el("ul", "small mb-0 mt-1 ps-3");
    items.forEach(function (t) { ul.appendChild(el("li", "", t)); });
    return ul;
  }

  // Форма рішення під карткою: «Доручити» (підрозділ + строк + коментар) або «Відхилити» (причина)
  function decisionForm(s, kind) {
    var f = el("form", "mt-2");
    f.noValidate = true;
    var fields = el("div", "row g-3");
    var dep, due;
    if (kind === "assign") {
      var c1 = el("div", "col-md-6");
      var l1 = el("label", "form-label fw-semibold", "Відповідальний підрозділ");
      l1.htmlFor = "dep-" + s.key;
      dep = el("select", "form-select");
      dep.id = l1.htmlFor;
      dep.required = true;
      var empty = el("option", "", "— оберіть підрозділ —"); empty.value = ""; dep.appendChild(empty);
      DATA.departments.forEach(function (d) {
        var o = el("option", "", d.name); o.value = d.id; dep.appendChild(o);
      });
      dep.value = s.suggested_department_id || "";
      c1.appendChild(l1);
      c1.appendChild(dep);
      fields.appendChild(c1);
      var c2 = el("div", "col-md-6");
      var l2 = el("label", "form-label fw-semibold", "Строк виконання");
      l2.htmlFor = "due-" + s.key;
      due = el("input", "form-control");
      due.id = l2.htmlFor;
      due.type = "date";
      due.required = true;
      due.value = s.suggested_due;
      due.min = new Date().toISOString().slice(0, 10);
      c2.appendChild(l2);
      c2.appendChild(due);
      fields.appendChild(c2);
    }
    var c3 = el("div", "col-12");
    var l3 = el("label", "form-label fw-semibold", kind === "assign" ? "Коментар до доручення " : "Причина відхилення ");
    l3.htmlFor = "comment-" + s.key;
    l3.appendChild(el("span", "fw-normal text-secondary", kind === "assign" ? "(необов'язково)" : "(обов'язково)"));
    var comment = el("textarea", "form-control");
    comment.id = l3.htmlFor;
    comment.rows = 2;
    comment.maxLength = 2000;
    comment.placeholder = kind === "assign" ? "Наприклад: доповісти на нараді" : "Наприклад: строк перенесено рішенням від…";
    c3.appendChild(l3);
    c3.appendChild(comment);
    fields.appendChild(c3);
    f.appendChild(fields);

    var err = el("div", "text-danger small mt-2", formError[s.key] || "");
    err.setAttribute("role", "alert");
    f.appendChild(err);

    var actions = el("div", "d-flex justify-content-end gap-2 mt-3");
    var cancel = el("button", "btn btn-outline-dark", "Скасувати");
    cancel.type = "button";
    cancel.onclick = function () { openForm = null; delete formError[s.key]; render(); };
    var ok = el("button", "btn btn-dark", kind === "assign" ? "Доручити" : "Відхилити рекомендацію");
    ok.type = "submit";
    ok.disabled = busy;
    actions.appendChild(cancel);
    actions.appendChild(ok);
    f.appendChild(actions);

    f.onsubmit = function (e) {
      e.preventDefault();
      if (kind === "assign" && !dep.value) { err.textContent = "Оберіть відповідальний підрозділ"; dep.focus(); return; }
      if (kind === "assign" && !due.value) { err.textContent = "Вкажіть строк виконання"; due.focus(); return; }
      if (kind === "dismiss" && !comment.value.trim()) { err.textContent = "Вкажіть причину відхилення"; comment.focus(); return; }
      busy = true;
      ok.disabled = true;
      Api.post("/api/manager/decisions", {
        signal_key: s.key, decision: kind,
        department_id: kind === "assign" ? dep.value : null,
        due_on: kind === "assign" ? due.value : null,
        comment: comment.value.trim()
      }).then(function (d) {
        DATA.signals = DATA.signals.filter(function (x) { return x.key !== s.key; });
        DATA.decisions.unshift(d);
        openForm = null;
        delete formError[s.key];
        flash = (kind === "assign" ? "Доручення збережено: " : "Рекомендацію відхилено: ") + s.title.toLowerCase();
        render();
      }).catch(function (ex) {
        formError[s.key] = ex.message;
        err.textContent = ex.message;
      }).finally(function () { busy = false; ok.disabled = false; });
    };
    setTimeout(function () { (dep || comment).focus(); }, 0);
    return f;
  }

  // Деталі перед рішенням: програма, розділ, підрозділи, накази, статус (або всі заходи підрозділу, або картка ризику)
  var DETAILS_TITLE = { RF6b: "Переглянути заходи підрозділу", RF7d: "Переглянути картку ризику" };
  function contextBlock(s) {
    var d = el("details", "small mt-2 context");
    d.appendChild(el("summary", "fw-semibold", DETAILS_TITLE[s.code] || "Переглянути деталі: розділ, підрозділи, наказ"));
    var body = el("div", "border rounded p-3 mt-2");
    var dl = el("dl", "row mb-0");
    s.context.facts.forEach(function (f) {
      dl.appendChild(el("dt", "col-sm-4 col-lg-3 fw-normal text-secondary", f[0]));
      dl.appendChild(el("dd", "col-sm-8 col-lg-9 mb-2", f[1]));
    });
    body.appendChild(dl);
    var t = s.context.table;
    if (t) {
      body.appendChild(el("div", "fw-semibold mt-2 mb-1", t.title));
      var wrap = el("div", "table-responsive");
      var table = el("table", "table table-sm align-top mb-0 context-table");
      var hr = el("tr");
      t.head.forEach(function (h) { hr.appendChild(el("th", "small text-secondary fw-normal", h)); });
      var thead = el("thead"); thead.appendChild(hr); table.appendChild(thead);
      var tbody = el("tbody");
      t.rows.forEach(function (r) {
        var tr = el("tr");
        r.cells.forEach(function (c) { tr.appendChild(el("td", "", c)); });
        var st = el("td", "text-nowrap");
        st.appendChild(el("span", "st st-" + r.st, STATUS_LABELS[r.st]));
        tr.appendChild(st);
        tbody.appendChild(tr);
      });
      table.appendChild(tbody);
      wrap.appendChild(table);
      body.appendChild(wrap);
    }
    d.appendChild(body);
    return d;
  }
  var STATUS_LABELS = { done: "Виконано", review: "На розгляді", rework: "На доопрацюванні", not: "Не виконано" };

  function signalCard(s) {
    var outer = el("article", "card mb-3 rec rec-" + s.severity);
    var card = el("div", "card-body");
    outer.appendChild(card);
    var top = el("div", "d-flex flex-wrap justify-content-between align-items-center gap-2");
    top.appendChild(badge(s.severity, SEVERITY[s.severity]));
    top.appendChild(el("span", "small text-secondary", "Правило " + s.code));
    card.appendChild(top);
    card.appendChild(el("h3", "h5 mt-2 mb-1", s.title));
    card.appendChild(el("p", "fw-medium mb-0", s.object));
    if (s.program) card.appendChild(el("p", "small text-secondary mb-0", "Програма: " + s.program));

    var why = el("div", "small mt-2");
    why.appendChild(el("b", "", "Чому з'явилась рекомендація"));
    why.appendChild(factList(s.why));
    card.appendChild(why);

    var rule = el("details", "small mt-2");
    rule.appendChild(el("summary", "fw-semibold", "Яке правило спрацювало"));
    rule.appendChild(el("p", "mt-1 mb-0 text-body-secondary", s.rule));
    card.appendChild(rule);
    if (s.context) card.appendChild(contextBlock(s));

    var rec = el("div", "bg-body-tertiary rounded p-3 mt-3 small");
    rec.appendChild(el("b", "", "Що пропонує система"));
    rec.appendChild(el("p", "mt-1 mb-0", s.recommendation));
    if (s.suggested_department_id) {
      rec.appendChild(el("p", "text-secondary mt-1 mb-0", "Пропонований виконавець: " + depName(s.suggested_department_id) +
        " · строк до " + s.suggested_due.split("-").reverse().join(".")));
    }
    card.appendChild(rec);

    if (!DATA.can_decide) return outer;
    var form = openForm && openForm.key === s.key ? openForm.kind : null;
    if (form) {
      card.appendChild(el("h4", "h6 mt-4 mb-1", form === "assign" ? "Доручення" : "Відхилення рекомендації"));
      card.appendChild(decisionForm(s, form));
    } else {
      var actions = el("div", "d-flex flex-wrap gap-2 mt-3");
      var a = el("button", "btn btn-dark", "Доручити");
      a.type = "button";
      a.onclick = function () { openForm = { key: s.key, kind: "assign" }; render(); };
      var d = el("button", "btn btn-outline-dark", "Відхилити");
      d.type = "button";
      d.onclick = function () { openForm = { key: s.key, kind: "dismiss" }; render(); };
      actions.appendChild(a);
      actions.appendChild(d);
      card.appendChild(actions);
    }
    return outer;
  }

  function decisionCard(d) {
    var outer = el("article", "card mb-3 rec rec-decided");
    var card = el("div", "card-body");
    outer.appendChild(card);
    var top = el("div", "d-flex flex-wrap justify-content-between align-items-center gap-2");
    top.appendChild(badge(d.decision, d.decision === "assign" ? "Доручено" : "Відхилено"));
    top.appendChild(el("span", "small text-secondary", d.at + " · " + d.by));
    card.appendChild(top);
    card.appendChild(el("h3", "h5 mt-2 mb-1", d.title));
    card.appendChild(el("p", "fw-medium mb-2", d.object));
    var facts = [];
    if (d.decision === "assign") facts.push("Відповідальний: " + d.department, "Строк: до " + d.due);
    if (d.comment) facts.push((d.decision === "assign" ? "Коментар: " : "Причина: ") + d.comment);
    card.appendChild(factList(facts));
    return outer;
  }

  var flash = "";
  function render() {
    document.getElementById("n-pending").textContent = DATA.signals.length;
    document.getElementById("n-done").textContent = DATA.decisions.length;
    var badge = document.getElementById("recs-count");
    badge.textContent = DATA.signals.length;
    badge.hidden = !DATA.signals.length;
    [["show-pending", "pending"], ["show-done", "done"]].forEach(function (b) {
      var btn = document.getElementById(b[0]);
      btn.setAttribute("aria-pressed", view === b[1]);
      btn.classList.toggle("active", view === b[1]);
    });

    var box = document.getElementById("recs");
    box.textContent = "";
    if (flash) { box.appendChild(el("div", "alert alert-success py-2", "✓ " + flash)); flash = ""; }
    if (!DATA.can_decide && view === "pending" && DATA.signals.length) {
      box.appendChild(el("div", "alert alert-light border py-2", "Ви переглядаєте рекомендації. Ухвалювати рішення може лише керівник."));
    }
    if (view === "pending") {
      if (!DATA.signals.length) box.appendChild(el("p", "text-success fw-semibold", "Нових рекомендацій немає: усі сигнали опрацьовано."));
      DATA.signals.forEach(function (s) { box.appendChild(signalCard(s)); });
    } else {
      if (!DATA.decisions.length) box.appendChild(el("p", "text-secondary fw-semibold", "У цьому звітному періоді рішень ще не ухвалено."));
      DATA.decisions.forEach(function (d) { box.appendChild(decisionCard(d)); });
    }
  }

  document.getElementById("show-pending").onclick = function () { view = "pending"; render(); };
  document.getElementById("show-done").onclick = function () { view = "done"; openForm = null; render(); };

  var guide = document.getElementById("recs-guide");
  try {
    if (!localStorage.getItem("manager_guide_seen")) guide.open = true;
    guide.addEventListener("toggle", function () { if (!guide.open) localStorage.setItem("manager_guide_seen", "1"); });
  } catch (e) { guide.open = true; }

  Api.get("/api/manager/overview")
    .then(function (data) {
      DATA = data;
      document.getElementById("unit").textContent = data.unit;
      var p = data.period.split("-H");
      document.getElementById("recs-period").textContent = "Звітний період: " + (p[1] === "1" ? "І" : "ІІ") +
        " півріччя " + p[0] + " р. · дані на " + data.today + ". Спершу — рекомендації з високою увагою.";
      render();
    })
    .catch(function (ex) { document.getElementById("page-error").textContent = ex.message; });
})();
