// Сторінка координатора: список програм, пошук, розділи, підпункти, органи і зміна статусу.
var PROGRAMS = JSON.parse(document.getElementById("programs-data").textContent);
var LABEL = JSON.parse(document.getElementById("statuses-data").textContent);
var ORDER = ["done", "review", "rework", "not"];
var openProgram = PROGRAMS.length ? PROGRAMS[0].id : null, openItem = null, choosing = null, lastError = null;

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
  span.appendChild(el("span", "cnt", c.done + "/" + c.total));
  return span;
}

function changeStatus(program, item, index, status) {
  item.units[index].st = status;
  try { localStorage.setItem("monitor-preview-programs", JSON.stringify(PROGRAMS)); } catch (_) {}
  lastError = null;
  choosing = null;
  render();
}

try {
  var savedPrograms = JSON.parse(localStorage.getItem("monitor-preview-programs") || "null");
  if (Array.isArray(savedPrograms)) PROGRAMS = savedPrograms;
} catch (_) {}

function statusNode(program, item, u, index) {
  var key = item.n + "/" + index;
  var wrap = el("div");
  var b = el("button", "status-btn s-" + u.st);
  b.type = "button";
  b.setAttribute("aria-expanded", choosing === key);
  b.setAttribute("aria-label", "Статус: " + LABEL[u.st] + ". Змінити");
  b.appendChild(el("span", "st st-" + u.st, LABEL[u.st]));
  b.appendChild(el("span", "caret", "▾"));
  b.onclick = function () { choosing = choosing === key ? null : key; render(); };
  wrap.appendChild(b);
  if (choosing === key) {
    var ch = el("div", "choices");
    ORDER.forEach(function (st) {
      if (st === u.st) return;
      var o = el("button", "opt", st === "rework" ? "На доопрацювання" : LABEL[st]);
      o.type = "button";
      o.onclick = function () { changeStatus(program, item, index, st); };
      ch.appendChild(o);
    });
    wrap.appendChild(ch);
  }
  if (lastError === key) wrap.appendChild(el("div", "error-line", "Не вдалося змінити статус. Спробуйте ще раз."));
  return wrap;
}

function unitsTable(program, item) {
  var card = el("div", "card");
  var table = el("table");
  var head = el("tr");
  ["Орган, що опрацював", "Дата", "Номер наказу", "Статус"].forEach(function (t) { head.appendChild(el("th", "", t)); });
  table.appendChild(head);
  item.units.forEach(function (u, k) {
    var tr = el("tr");
    tr.appendChild(el("td", "", u.organ));
    var hasDoc = u.st !== "not" && u.order;
    tr.appendChild(el("td", "", hasDoc ? u.date : "—"));
    var td = el("td");
    if (hasDoc) {
      var a = el("a", "", "Наказ № " + u.order);
      a.href = u.link;
      if (/^https?:/.test(u.link)) { a.target = "_blank"; a.rel = "noopener"; }
      td.appendChild(a);
    } else td.textContent = "—";
    tr.appendChild(td);
    var st = el("td");
    st.appendChild(statusNode(program, item, u, k));
    tr.appendChild(st);
    table.appendChild(tr);
  });
  card.appendChild(table);
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
    var wrap = el("div", "prog" + (open ? " open" : ""));
    var btn = el("button", "row");
    btn.type = "button";
    btn.setAttribute("aria-expanded", open);
    var name = el("span", "name");
    name.appendChild(el("span", "arrow", open ? "▼" : "▶"));
    name.appendChild(el("span", "", p.name));
    btn.appendChild(name);
    btn.appendChild(el("span", "d", p.start));
    btn.appendChild(el("span", "d", p.end));
    btn.appendChild(el("span", "r big", c.done + "/" + c.total));
    btn.onclick = function () { openProgram = open ? null : p.id; render(); };
    wrap.appendChild(btn);

    var det = el("div", "detail");
    if (!p.sections.length) det.appendChild(el("p", "muted", "Програму завершено. Розділи архівної програми в демо не завантажено."));
    p.sections.forEach(function (s) {
      var sec = el("div", "sec");
      var sc = sectionCount(s);
      var h = el("div", "sec-h");
      h.appendChild(el("b", "", s.n + ". " + s.title));
      h.appendChild(el("span", "muted", "кінцевий термін " + s.deadline));
      h.appendChild(el("span", "r big", sc.done + "/" + sc.total));
      sec.appendChild(h);
      s.items.forEach(function (i) {
        var isOpen = openItem === i.n;
        var row = el("div", "item" + (isOpen ? " open" : ""));
        var ib = el("button");
        ib.type = "button";
        ib.setAttribute("aria-expanded", isOpen);
        ib.appendChild(el("span", "muted", i.n));
        ib.appendChild(el("span", "", i.t));
        ib.appendChild(el("span", "muted", i.d));
        ib.appendChild(itemStatus(i));
        ib.onclick = function () { openItem = isOpen ? null : i.n; choosing = null; render(); };
        row.appendChild(ib);
        row.appendChild(unitsTable(p, i));
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
render();
