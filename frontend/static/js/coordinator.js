// Сторінка координатора: список програм, пошук, розділи, підпункти, органи і зміна статусу.
// Дані — з /api/coordinator/programs; змінювати статус можуть ADMIN і KOORD.
// Також підключається на сторінці аналітика: там can_edit=false, тож усе лише для перегляду.
var PROGRAMS = [], LABEL = {}, CAN_EDIT = false;
var ORDER = ["done", "review", "rework", "not"];
var openProgram = null, openItem = null, choosing = null, lastError = null;

function el(tag, cls, text) {
  var e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}

// Рахунок: підпункт — скільки органів виконали; розділ і програма — сума по підпунктах
function itemCount(i) {
  return { done: i.units.filter(function (u) { return u.st === "done"; }).length, total: i.units.length };
}
function sectionCount(s) {
  var d = 0, t = 0;
  s.items.forEach(function (i) { var c = itemCount(i); d += c.done; t += c.total; });
  return { done: d, total: t };
}
function programCount(p) {
  if (p.archive) return p.archive;
  var d = 0, t = 0;
  p.sections.forEach(function (s) { var c = sectionCount(s); d += c.done; t += c.total; });
  return { done: d, total: t };
}
function itemStatus(i) {
  var c = itemCount(i);
  var anyReview = i.units.some(function (u) { return u.st === "review"; });
  var cls = c.done === c.total ? "done" : (anyReview ? "review" : "not");
  var span = el("span", "st st-" + cls, "Виконано");
  span.appendChild(el("span", "fw-bold ms-1", c.done + "/" + c.total));
  return span;
}

function changeStatus(program, item, index, status) {
  Api.post("/api/coordinator/status", { measure_id: item.measure_id, status: status })
    .then(function (res) { item.units[index].st = res.status; lastError = null; choosing = null; render(); })
    .catch(function () { lastError = item.n + "/" + index; render(); });
}

function statusNode(program, item, u, index) {
  var key = item.n + "/" + index;
  var wrap = el("div");
  if (!CAN_EDIT) { wrap.appendChild(el("span", "st st-" + u.st, LABEL[u.st])); return wrap; }
  var b = el("button", "btn btn-sm d-inline-flex align-items-center gap-2 " + (u.st === "review" ? "btn-dark" : "btn-outline-secondary text-body"));
  b.type = "button";
  b.setAttribute("aria-expanded", choosing === key);
  b.setAttribute("aria-label", "Статус: " + LABEL[u.st] + ". Змінити");
  b.appendChild(el("span", "st st-" + u.st, LABEL[u.st]));
  b.appendChild(el("span", "small", "▾"));
  b.onclick = function () { choosing = choosing === key ? null : key; render(); };
  wrap.appendChild(b);
  if (choosing === key) {
    var ch = el("div", "d-flex flex-wrap gap-2 mt-2");
    ORDER.forEach(function (st) {
      if (st === u.st) return;
      var o = el("button", "btn btn-sm btn-outline-dark", st === "rework" ? "На доопрацювання" : LABEL[st]);
      o.type = "button";
      o.onclick = function () { changeStatus(program, item, index, st); };
      ch.appendChild(o);
    });
    wrap.appendChild(ch);
  }
  if (lastError === key) wrap.appendChild(el("div", "text-danger small mt-1", "Не вдалося змінити статус. Спробуйте ще раз."));
  return wrap;
}

function unitsTable(program, item) {
  var card = el("div", "card mb-3 ms-md-5");
  var box = el("div", "table-responsive");
  var table = el("table", "table table-sm align-top mb-0 units-table");
  var thead = el("thead"), head = el("tr");
  ["Орган, що опрацював", "Дата", "Номер наказу", "Статус"].forEach(function (t) { head.appendChild(el("th", "small text-secondary fw-normal", t)); });
  thead.appendChild(head);
  table.appendChild(thead);
  var body = el("tbody");
  item.units.forEach(function (u, k) {
    var tr = el("tr");
    tr.appendChild(el("td", "", u.organ));
    var hasDoc = u.st !== "not" && u.order;
    tr.appendChild(el("td", "text-nowrap", hasDoc ? u.date : "—"));
    var td = el("td");
    if (hasDoc) {
      var a = el("a", "fw-semibold text-nowrap link-dark", "Наказ № " + u.order);
      a.href = u.link;
      if (/^https?:/.test(u.link)) { a.target = "_blank"; a.rel = "noopener"; }
      td.appendChild(a);
    } else td.textContent = "—";
    tr.appendChild(td);
    var st = el("td");
    st.appendChild(statusNode(program, item, u, k));
    tr.appendChild(st);
    body.appendChild(tr);
  });
  table.appendChild(body);
  box.appendChild(table);
  card.appendChild(box);
  return card;
}

function render() {
  var q = document.getElementById("q").value.trim().toLowerCase();
  var box = document.getElementById("programs");
  box.textContent = "";
  var shown = PROGRAMS.filter(function (p) {
    return !q || p.name.toLowerCase().indexOf(q) >= 0 || p.start.indexOf(q) >= 0 || p.end.indexOf(q) >= 0;
  });
  shown.forEach(function (p) {
    var open = openProgram === p.id, c = programCount(p);
    var wrap = el("div", "list-group-item p-0");
    var btn = el("button", "btn w-100 text-start rounded-0 px-3 py-3 row-btn" + (open ? " bg-body-tertiary" : ""));
    btn.type = "button";
    btn.setAttribute("aria-expanded", open);
    var row = el("div", "row g-2 align-items-center");
    var name = el("div", "col-12 col-md-6 d-flex gap-2 align-items-baseline fw-semibold");
    name.appendChild(el("span", "small text-secondary fw-normal", open ? "▼" : "▶"));
    name.appendChild(el("span", "", p.name));
    row.appendChild(name);
    row.appendChild(el("div", "col-md-2 d-none d-md-block", p.start));
    row.appendChild(el("div", "col-md-2 d-none d-md-block", p.end));
    var cnt = el("div", "col-12 col-md-2 text-md-end fs-5 fw-bold");
    cnt.appendChild(el("span", "small fw-normal text-secondary d-md-none me-2", "Виконано"));
    cnt.appendChild(document.createTextNode(c.done + "/" + c.total));
    row.appendChild(cnt);
    btn.appendChild(row);
    btn.onclick = function () { openProgram = open ? null : p.id; render(); };
    wrap.appendChild(btn);

    var det = el("div", "bg-body-tertiary border-top px-3 px-md-4 pb-3");
    det.hidden = !open;
    if (!p.sections.length) det.appendChild(el("p", "text-secondary small pt-3 mb-0", "У програмі ще немає заходів."));
    p.sections.forEach(function (s) {
      var sec = el("div", "pt-3");
      var sc = sectionCount(s);
      var h = el("div", "d-flex flex-wrap align-items-baseline gap-3 border-bottom border-dark pb-2");
      h.appendChild(el("b", "me-auto", s.n + ". " + s.title));
      h.appendChild(el("span", "small text-secondary", "кінцевий термін " + s.deadline));
      h.appendChild(el("span", "fs-5 fw-bold", sc.done + "/" + sc.total));
      sec.appendChild(h);
      s.items.forEach(function (i) {
        var isOpen = openItem === i.n;
        var row = el("div", "border-bottom");
        var ib = el("button", "btn w-100 text-start rounded-0 px-0 py-2 small row-btn" + (isOpen ? " fw-semibold" : ""));
        ib.type = "button";
        ib.setAttribute("aria-expanded", isOpen);
        var r = el("div", "row g-2 align-items-baseline");
        r.appendChild(el("div", "col-auto text-secondary d-none d-md-block item-n", i.n));
        r.appendChild(el("div", "col", i.t));
        r.appendChild(el("div", "col-md-2 text-secondary d-none d-md-block", i.d));
        var stc = el("div", "col-auto");
        stc.appendChild(itemStatus(i));
        r.appendChild(stc);
        ib.appendChild(r);
        ib.onclick = function () { openItem = isOpen ? null : i.n; choosing = null; render(); };
        row.appendChild(ib);
        if (isOpen) row.appendChild(unitsTable(p, i));
        sec.appendChild(row);
      });
      det.appendChild(sec);
    });
    wrap.appendChild(det);
    box.appendChild(wrap);
  });
  var empty = document.getElementById("empty");
  empty.hidden = shown.length > 0;
  empty.textContent = "Програм за запитом «" + document.getElementById("q").value + "» не знайдено";
}

document.getElementById("q").addEventListener("input", render);

Api.get("/api/coordinator/programs")
  .then(function (data) {
    PROGRAMS = data.programs;
    LABEL = data.statuses;
    CAN_EDIT = data.can_edit;
    openProgram = PROGRAMS.length ? PROGRAMS[0].id : null;
    document.getElementById("unit").textContent = data.unit;
    var create = document.getElementById("create");
    if (create) create.hidden = !CAN_EDIT;
    render();
  })
  .catch(function (ex) { document.getElementById("page-error").textContent = ex.message; });
