// Кабінет аналітика: зведення й графіки за даними /api/analyst/overview.
// Вкладку «Програми й заходи» малює coordinator.js (там can_edit=false — лише перегляд).
(function () {
  var ORDER = ["done", "review", "rework", "not"];
  var DATA = null;

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined) e.textContent = text;
    return e;
  }
  function pct(part, total) { return total ? Math.round(part * 100 / total) : 0; }
  // 1 захід, 2 заходи, 5 заходів
  function measures(n) {
    var a = n % 10, b = n % 100;
    var w = a === 1 && b !== 11 ? "захід" : (a >= 2 && a <= 4 && (b < 12 || b > 14) ? "заходи" : "заходів");
    return n + " " + w;
  }
  function count(list) {
    var c = { done: 0, review: 0, rework: 0, not: 0, total: list.length, overdue: 0, soon: 0 };
    list.forEach(function (m) { c[m.st]++; if (m.overdue) c.overdue++; if (m.due_soon) c.soon++; });
    return c;
  }
  function groupBy(list, key) {
    var map = {}, keys = [];
    list.forEach(function (m) {
      if (!map[m[key]]) { map[m[key]] = []; keys.push(m[key]); }
      map[m[key]].push(m);
    });
    return keys.map(function (k) { return { name: k, c: count(map[k]) }; });
  }

  // ---------- Підказка при наведенні ----------
  var tip = document.getElementById("tip");
  function showTip(e, text) {
    tip.textContent = text;
    tip.hidden = false;
    var x = Math.min(e.clientX + 14, window.innerWidth - tip.offsetWidth - 8);
    tip.style.left = Math.max(8, x) + "px";
    tip.style.top = (e.clientY + 16) + "px";
  }
  function hideTip() { tip.hidden = true; }

  // ---------- Складена смуга: виконано / на розгляді / на доопрацюванні / не виконано ----------
  function stackBar(c, title) {
    var bar = el("div", "stack");
    bar.setAttribute("role", "img");
    bar.setAttribute("aria-label", title + ": " + ORDER.map(function (st) {
      return DATA.statuses[st].toLowerCase() + " " + c[st];
    }).join(", ") + " з " + c.total);
    if (!c.total) { bar.appendChild(el("div", "seg seg-empty")); return bar; }
    ORDER.forEach(function (st) {
      if (!c[st]) return;
      var s = el("div", "seg seg-" + st);
      s.style.flexGrow = c[st];
      var text = title + " — " + DATA.statuses[st] + ": " + measures(c[st]) + " (" + pct(c[st], c.total) + "%)";
      s.addEventListener("mousemove", function (e) { showTip(e, text); });
      s.addEventListener("mouseleave", hideTip);
      bar.appendChild(s);
    });
    return bar;
  }

  function legend() {
    var box = el("div", "d-flex flex-wrap gap-2 column-gap-4 mt-3 small");
    ORDER.forEach(function (st) { box.appendChild(el("span", "st st-" + st, DATA.statuses[st])); });
    return box;
  }

  // Ті самі числа таблицею — для тих, кому так зручніше, і для читачів екрана
  function numbersTable(groups, firstCol) {
    var d = el("details", "mt-3 small");
    d.appendChild(el("summary", "fw-semibold py-1", "Показати таблицею"));
    var box = el("div", "table-responsive mt-2");
    var t = el("table", "table table-sm mb-0");
    var head = el("tr");
    [firstCol].concat(ORDER.map(function (st) { return DATA.statuses[st]; }), ["Строк минув", "Усього", "Виконано, %"])
      .forEach(function (h, i) { head.appendChild(el("th", "small text-secondary fw-normal" + (i ? " text-end" : ""), h)); });
    t.appendChild(head);
    groups.forEach(function (g) {
      var tr = el("tr");
      tr.appendChild(el("td", "", g.name));
      ORDER.concat(["overdue", "total"]).forEach(function (k) { tr.appendChild(el("td", "text-end font-monospace-num", String(g.c[k]))); });
      tr.appendChild(el("td", "text-end font-monospace-num", pct(g.c.done, g.c.total) + "%"));
      t.appendChild(tr);
    });
    box.appendChild(t);
    d.appendChild(box);
    return d;
  }

  function barRows(groups) {
    var box = el("div", "d-grid gap-3");
    groups.forEach(function (g) {
      var row = el("div", "bar-row");
      row.appendChild(el("span", "bar-name", g.name));
      row.appendChild(stackBar(g.c, g.name));
      var v = el("span", "bar-val");
      v.appendChild(el("b", "", pct(g.c.done, g.c.total) + "%"));
      v.appendChild(el("span", "small text-secondary", g.c.done + " з " + g.c.total));
      row.appendChild(v);
      box.appendChild(row);
    });
    return box;
  }

  // ---------- Показники вгорі ----------
  function kpis(c) {
    var items = [
      ["Усього заходів", c.total, "у вибраній програмі", ""],
      ["Виконано", c.done, pct(c.done, c.total) + "% від усіх заходів", "st-done"],
      ["На розгляді", c.review, "чекають на рішення координатора", "st-review"],
      ["На доопрацюванні", c.rework, "повернуті підрозділам на виправлення", "st-rework"],
      ["Не виконано", c.not, "підтвердження ще не подано", "st-not"],
      ["Строк минув", c.overdue, "строк настав, а захід не погоджено", "alert"]
    ];
    var box = document.getElementById("kpis");
    box.textContent = "";
    items.forEach(function (k) {
      var alert = k[3] === "alert" && k[1];
      var col = el("div", "col");
      var card = el("div", "card h-100" + (alert ? " border-danger border-2" : ""));
      var body = el("div", "card-body p-3");
      body.appendChild(el("div", "small fw-semibold" + (k[3] && k[3] !== "alert" ? " st " + k[3] : ""), k[0]));
      body.appendChild(el("div", "fs-2 fw-bold lh-sm" + (alert ? " text-danger" : ""), String(k[1])));
      body.appendChild(el("div", "small text-secondary lh-sm", k[2]));
      card.appendChild(body);
      col.appendChild(card);
      box.appendChild(col);
    });
  }

  // ---------- Таблиця «Потребують уваги» ----------
  function attention(list) {
    var rows = list.filter(function (m) { return m.overdue || m.due_soon; })
      .sort(function (a, b) { return a.days_left - b.days_left; });
    document.getElementById("attention-hint").textContent =
      "Заходи, у яких строк уже минув, і ті, що мають бути виконані протягом " + DATA.soon_days +
      " днів. Найтерміновіші — вгорі.";
    var box = document.getElementById("attention");
    box.textContent = "";
    if (!rows.length) { box.appendChild(el("p", "text-success fw-semibold mb-0", "Усе гаразд: прострочених заходів і близьких строків немає.")); return; }
    var wrap = el("div", "table-responsive");
    var t = el("table", "table table-sm table-hover align-top mb-0 attention-table");
    var head = el("tr");
    ["№", "Захід", "Підрозділ", "Строк", "Статус", "Стан строку"].forEach(function (h) { head.appendChild(el("th", "small text-secondary fw-normal", h)); });
    t.appendChild(head);
    rows.forEach(function (m) {
      var tr = el("tr");
      tr.appendChild(el("td", "text-secondary", m.n));
      tr.appendChild(el("td", "", m.t));
      tr.appendChild(el("td", "", m.department));
      tr.appendChild(el("td", "text-nowrap", m.deadline));
      var st = el("td"); st.appendChild(el("span", "st st-" + m.st, DATA.statuses[m.st])); tr.appendChild(st);
      var d = -m.days_left;
      tr.appendChild(el("td", m.overdue ? "text-danger fw-semibold text-nowrap" : "text-nowrap",
        m.overdue ? "⚠ прострочено на " + d + " дн." : (m.days_left === 0 ? "строк сьогодні" : "залишилось " + m.days_left + " дн.")));
      t.appendChild(tr);
    });
    wrap.appendChild(t);
    box.appendChild(wrap);
  }

  function render() {
    var pid = document.getElementById("program").value;
    var list = DATA.measures.filter(function (m) { return !pid || m.program_id === pid; });
    var c = count(list);
    kpis(c);

    var total = document.getElementById("chart-total");
    total.textContent = "";
    if (!c.total) {
      total.appendChild(el("p", "text-secondary mb-0", "У цій програмі ще немає заходів."));
    } else {
      var big = el("p", "mb-2");
      big.appendChild(el("b", "fs-2 me-1", pct(c.done, c.total) + "%"));
      big.appendChild(document.createTextNode(" заходів виконано — " + c.done + " з " + c.total));
      total.appendChild(big);
      total.appendChild(stackBar(c, "Усі заходи"));
      total.appendChild(legend());
    }

    [["chart-sections", groupBy(list, "section"), "Розділ"],
     ["chart-departments", groupBy(list, "department").sort(function (a, b) {
       return pct(a.c.done, a.c.total) - pct(b.c.done, b.c.total) || b.c.total - a.c.total;
     }), "Підрозділ"]].forEach(function (cfg) {
      var box = document.getElementById(cfg[0]);
      box.textContent = "";
      if (!cfg[1].length) { box.appendChild(el("p", "text-secondary mb-0", "Немає даних.")); return; }
      box.appendChild(barRows(cfg[1]));
      box.appendChild(legend());
      box.appendChild(numbersTable(cfg[1], cfg[2]));
    });
    attention(list);
  }

  // ---------- Вкладки (кнопки role=tab у role=tablist; панель — за aria-controls) ----------
  var tabs = Array.prototype.slice.call(document.querySelectorAll("[role=tablist] [role=tab]"));
  var TAB_KEY = "tab:" + location.pathname;
  function selectTab(id) {
    if (!document.getElementById(id)) return;
    tabs.forEach(function (b) {
      var on = b.id === id;
      b.setAttribute("aria-selected", on);
      b.classList.toggle("active", on);
      b.tabIndex = on ? 0 : -1;
      document.getElementById(b.getAttribute("aria-controls")).hidden = !on;
    });
    try { sessionStorage.setItem(TAB_KEY, id); } catch (e) { /* без сховища */ }
  }
  tabs.forEach(function (b, i) {
    b.addEventListener("click", function () { selectTab(b.id); });
    b.addEventListener("keydown", function (e) {
      if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
      var next = tabs[(i + (e.key === "ArrowRight" ? 1 : tabs.length - 1)) % tabs.length];
      selectTab(next.id);
      next.focus();
    });
  });
  try { var saved = sessionStorage.getItem(TAB_KEY); if (saved) selectTab(saved); } catch (e) { /* без сховища */ }
  window.selectTab = selectTab;

  // Підказку «Як читати» відкриваємо при першому візиті
  var guide = document.getElementById("guide");
  try {
    if (!localStorage.getItem("analyst_guide_seen")) guide.open = true;
    guide.addEventListener("toggle", function () { if (!guide.open) localStorage.setItem("analyst_guide_seen", "1"); });
  } catch (e) { guide.open = true; }

  document.getElementById("program").addEventListener("change", render);

  Api.get("/api/analyst/overview")
    .then(function (data) {
      DATA = data;
      document.getElementById("unit").textContent = data.unit;
      var period = data.period.split("-H");
      document.getElementById("period").textContent =
        "Звітний період: " + (period[1] === "1" ? "І" : "ІІ") + " півріччя " + period[0] + " р. · дані на " + data.today;
      var sel = document.getElementById("program");
      data.programs.forEach(function (p) {
        var o = el("option", "", p.name + " (" + p.start + " – " + p.end + ")");
        o.value = p.id;
        sel.appendChild(o);
      });
      render();
    })
    .catch(function (ex) { document.getElementById("page-error").textContent = ex.message; });
})();
