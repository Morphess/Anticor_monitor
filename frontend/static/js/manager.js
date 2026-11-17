// Кабінет керівника, вкладка «Рекомендації»: сигнали правил і рішення за ними.
// Дані — /api/manager/overview; рішення — POST /api/manager/decisions (лише роль KER).
// Вкладки «Панелі» і «Програми й заходи» малюють analyst.js і coordinator.js.
(function () {
  var DATA = null, view = "pending", openForm = null, busy = false, formError = {};
  var SEVERITY = { high: "Висока увага", medium: "Середня увага" };

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
    var ul = el("ul", "facts");
    items.forEach(function (t) { ul.appendChild(el("li", "", t)); });
    return ul;
  }

  // Форма рішення під карткою: «Доручити» (підрозділ + строк + коментар) або «Відхилити» (причина)
  function decisionForm(s, kind) {
    var f = el("form", "decide-form");
    f.noValidate = true;
    var fields = el("div", "fields");
    var dep, due;
    if (kind === "assign") {
      var l1 = el("label", "", "Відповідальний підрозділ");
      dep = el("select");
      dep.required = true;
      var empty = el("option", "", "— оберіть підрозділ —"); empty.value = ""; dep.appendChild(empty);
      DATA.departments.forEach(function (d) {
        var o = el("option", "", d.name); o.value = d.id; dep.appendChild(o);
      });
      dep.value = s.suggested_department_id || "";
      l1.appendChild(dep);
      fields.appendChild(l1);
      var l2 = el("label", "", "Строк виконання");
      due = el("input");
      due.type = "date";
      due.required = true;
      due.value = s.suggested_due;
      due.min = new Date().toISOString().slice(0, 10);
      l2.appendChild(due);
      fields.appendChild(l2);
    }
    var l3 = el("label", "wide", kind === "assign" ? "Коментар до доручення " : "Причина відхилення ");
    l3.appendChild(el("span", "muted", kind === "assign" ? "(необов'язково)" : "(обов'язково)"));
    var comment = el("textarea");
    comment.rows = 2;
    comment.maxLength = 2000;
    comment.placeholder = kind === "assign" ? "Наприклад: доповісти на нараді" : "Наприклад: строк перенесено рішенням від…";
    l3.appendChild(comment);
    fields.appendChild(l3);
    f.appendChild(fields);

    var err = el("p", "error-line", formError[s.key] || "");
    err.setAttribute("role", "alert");
    f.appendChild(err);

    var actions = el("div", "form-actions");
    var cancel = el("button", "btn-plain", "Скасувати");
    cancel.type = "button";
    cancel.onclick = function () { openForm = null; delete formError[s.key]; render(); };
    var ok = el("button", "create", kind === "assign" ? "Доручити" : "Відхилити рекомендацію");
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

  function signalCard(s) {
    var card = el("article", "rec rec-" + s.severity);
    var top = el("div", "rec-top");
    top.appendChild(el("span", "sev sev-" + s.severity, SEVERITY[s.severity]));
    top.appendChild(el("span", "muted", "Правило " + s.code));
    card.appendChild(top);
    card.appendChild(el("h3", "", s.title));
    card.appendChild(el("p", "rec-obj", s.object));

    var why = el("div", "rec-block");
    why.appendChild(el("b", "", "Чому з'явилась рекомендація"));
    why.appendChild(factList(s.why));
    card.appendChild(why);

    var rule = el("details", "rec-rule");
    rule.appendChild(el("summary", "", "Яке правило спрацювало"));
    rule.appendChild(el("p", "", s.rule));
    card.appendChild(rule);

    var rec = el("div", "rec-block rec-advice");
    rec.appendChild(el("b", "", "Що пропонує система"));
    rec.appendChild(el("p", "", s.recommendation));
    if (s.suggested_department_id) {
      rec.appendChild(el("p", "muted", "Пропонований виконавець: " + depName(s.suggested_department_id) +
        " · строк до " + s.suggested_due.split("-").reverse().join(".")));
    }
    card.appendChild(rec);

    if (!DATA.can_decide) return card;
    var form = openForm && openForm.key === s.key ? openForm.kind : null;
    if (form) {
      card.appendChild(el("h4", "", form === "assign" ? "Доручення" : "Відхилення рекомендації"));
      card.appendChild(decisionForm(s, form));
    } else {
      var actions = el("div", "rec-actions");
      var a = el("button", "create", "Доручити");
      a.type = "button";
      a.onclick = function () { openForm = { key: s.key, kind: "assign" }; render(); };
      var d = el("button", "btn-plain", "Відхилити");
      d.type = "button";
      d.onclick = function () { openForm = { key: s.key, kind: "dismiss" }; render(); };
      actions.appendChild(a);
      actions.appendChild(d);
      card.appendChild(actions);
    }
    return card;
  }

  function decisionCard(d) {
    var card = el("article", "rec rec-decided");
    var top = el("div", "rec-top");
    top.appendChild(el("span", "sev " + (d.decision === "assign" ? "sev-assign" : "sev-dismiss"),
      d.decision === "assign" ? "Доручено" : "Відхилено"));
    top.appendChild(el("span", "muted", d.at + " · " + d.by));
    card.appendChild(top);
    card.appendChild(el("h3", "", d.title));
    card.appendChild(el("p", "rec-obj", d.object));
    var facts = [];
    if (d.decision === "assign") facts.push("Відповідальний: " + d.department, "Строк: до " + d.due);
    if (d.comment) facts.push((d.decision === "assign" ? "Коментар: " : "Причина: ") + d.comment);
    card.appendChild(factList(facts));
    return card;
  }

  var flash = "";
  function render() {
    document.getElementById("n-pending").textContent = DATA.signals.length;
    document.getElementById("n-done").textContent = DATA.decisions.length;
    var badge = document.getElementById("recs-count");
    badge.textContent = DATA.signals.length;
    badge.hidden = !DATA.signals.length;
    document.getElementById("show-pending").setAttribute("aria-pressed", view === "pending");
    document.getElementById("show-done").setAttribute("aria-pressed", view === "done");

    var box = document.getElementById("recs");
    box.textContent = "";
    if (flash) { box.appendChild(el("p", "flash ok", "✓ " + flash)); flash = ""; }
    if (!DATA.can_decide && view === "pending" && DATA.signals.length) {
      box.appendChild(el("p", "view-only", "Ви переглядаєте рекомендації. Ухвалювати рішення може лише керівник."));
    }
    if (view === "pending") {
      if (!DATA.signals.length) box.appendChild(el("p", "ok empty-note", "Нових рекомендацій немає: усі сигнали опрацьовано."));
      DATA.signals.forEach(function (s) { box.appendChild(signalCard(s)); });
    } else {
      if (!DATA.decisions.length) box.appendChild(el("p", "muted empty-note", "У цьому звітному періоді рішень ще не ухвалено."));
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
      var p = data.period.split("-H");
      document.getElementById("recs-period").textContent = "Звітний період: " + (p[1] === "1" ? "І" : "ІІ") +
        " півріччя " + p[0] + " р. · дані на " + data.today + ". Спершу — рекомендації з високою увагою.";
      render();
    })
    .catch(function (ex) { document.getElementById("page-error").textContent = ex.message; });
})();
