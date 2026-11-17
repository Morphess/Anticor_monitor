// Спільні графіки й зведення: вкладка аналітика, попередній перегляд і перегляд аналітичного звіту.
// Зріз (snapshot) має ту саму форму, що й у analytics_report_service.build_snapshot на сервері.
var Charts = (function () {
  var ORDER = ["done", "review", "rework", "not"];
  var LABELS = { done: "Виконано", review: "На розгляді", rework: "На доопрацюванні", not: "Не виконано" };

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

  // ---------- Зведення з рядків /api/analyst/overview ----------
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
  function summarize(data, programId) {
    var names = {};
    data.programs.forEach(function (p) { names[p.id] = p.name; });
    var list = data.measures.filter(function (m) { return !programId || m.program_id === programId; });
    var attention = list.filter(function (m) { return m.overdue || m.due_soon; })
      .sort(function (a, b) { return a.days_left - b.days_left; });
    return {
      scope: programId ? names[programId] : "Усі програми",
      period: data.period, today: data.today, soon_days: data.soon_days, statuses: data.statuses,
      counts: count(list),
      sections: groupBy(list, "section"),
      departments: groupBy(list, "department").sort(function (a, b) {
        return pct(a.c.done, a.c.total) - pct(b.c.done, b.c.total) || b.c.total - a.c.total;
      }),
      show_program: !programId && data.programs.length > 1,
      attention: attention.map(function (m) {
        return { n: m.n, t: m.t, program: names[m.program_id], department: m.department, deadline: m.deadline,
                 st: m.st, overdue: m.overdue, days_left: m.days_left };
      }),
      attention_total: attention.length
    };
  }

  function periodText(period) {
    var p = period.split("-H");
    return (p[1] === "1" ? "І" : "ІІ") + " півріччя " + p[0] + " р.";
  }

  // ---------- Підказка при наведенні ----------
  var tip = null;
  function showTip(e, text) {
    if (!tip) {
      tip = el("div", "chart-tip");
      tip.setAttribute("role", "tooltip");
      document.body.appendChild(tip);
    }
    tip.textContent = text;
    tip.hidden = false;
    var x = Math.min(e.clientX + 14, window.innerWidth - tip.offsetWidth - 8);
    tip.style.left = Math.max(8, x) + "px";
    tip.style.top = (e.clientY + 16) + "px";
  }
  function hideTip() { if (tip) tip.hidden = true; }

  // ---------- Складена смуга: виконано / на розгляді / на доопрацюванні / не виконано ----------
  function stackBar(c, title) {
    var bar = el("div", "stack");
    bar.setAttribute("role", "img");
    bar.setAttribute("aria-label", title + ": " + ORDER.map(function (st) {
      return LABELS[st].toLowerCase() + " " + c[st];
    }).join(", ") + " з " + c.total);
    if (!c.total) { bar.appendChild(el("div", "seg seg-empty")); return bar; }
    ORDER.forEach(function (st) {
      if (!c[st]) return;
      var s = el("div", "seg seg-" + st);
      s.style.flexGrow = c[st];
      var text = title + " — " + LABELS[st] + ": " + measures(c[st]) + " (" + pct(c[st], c.total) + "%)";
      s.addEventListener("mousemove", function (e) { showTip(e, text); });
      s.addEventListener("mouseleave", hideTip);
      bar.appendChild(s);
    });
    return bar;
  }

  function legend() {
    var box = el("div", "d-flex flex-wrap gap-2 column-gap-4 mt-3 small");
    ORDER.forEach(function (st) { box.appendChild(el("span", "st st-" + st, LABELS[st])); });
    return box;
  }

  // Ті самі числа таблицею — для тих, кому так зручніше, і для читачів екрана
  function numbersTable(groups, firstCol) {
    var d = el("details", "mt-3 small");
    d.appendChild(el("summary", "fw-semibold py-1", "Показати таблицею"));
    var box = el("div", "table-responsive mt-2");
    var t = el("table", "table table-sm mb-0");
    var head = el("tr");
    [firstCol].concat(ORDER.map(function (st) { return LABELS[st]; }), ["Строк минув", "Усього", "Виконано, %"])
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

  function kpis(c) {
    var items = [
      ["Усього заходів", c.total, "у вибраній програмі", ""],
      ["Виконано", c.done, pct(c.done, c.total) + "% від усіх заходів", "st-done"],
      ["На розгляді", c.review, "чекають на рішення координатора", "st-review"],
      ["На доопрацюванні", c.rework, "повернуті підрозділам на виправлення", "st-rework"],
      ["Не виконано", c.not, "підтвердження ще не подано", "st-not"],
      ["Строк минув", c.overdue, "строк настав, а захід не погоджено", "alert"]
    ];
    var box = el("div", "row row-cols-2 row-cols-md-3 row-cols-xl-6 g-3 mb-3");
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
    return box;
  }

  function attentionTable(snap) {
    var rows = snap.attention;
    if (!rows.length) return el("p", "text-success fw-semibold mb-0", "Усе гаразд: прострочених заходів і близьких строків немає.");
    var wrap = el("div", "table-responsive");
    var t = el("table", "table table-sm table-hover align-top mb-0 attention-table");
    var head = el("tr");
    // Номери заходів повторюються в різних програмах: для «Усіх програм» показуємо й програму
    ["№", "Захід"].concat(snap.show_program ? ["Програма"] : [], ["Підрозділ", "Строк", "Статус", "Стан строку"])
      .forEach(function (h) { head.appendChild(el("th", "small text-secondary fw-normal", h)); });
    t.appendChild(head);
    rows.forEach(function (m) {
      var tr = el("tr");
      tr.appendChild(el("td", "text-secondary", m.n));
      tr.appendChild(el("td", "", m.t));
      if (snap.show_program) tr.appendChild(el("td", "small text-secondary", m.program));
      tr.appendChild(el("td", "", m.department));
      tr.appendChild(el("td", "text-nowrap", m.deadline));
      var st = el("td"); st.appendChild(el("span", "st st-" + m.st, LABELS[m.st])); tr.appendChild(st);
      tr.appendChild(el("td", m.overdue ? "text-danger fw-semibold text-nowrap" : "text-nowrap",
        m.overdue ? "⚠ прострочено на " + (-m.days_left) + " дн." :
          (m.days_left === 0 ? "строк сьогодні" : "залишилось " + m.days_left + " дн.")));
      t.appendChild(tr);
    });
    wrap.appendChild(t);
    if (snap.attention_total > rows.length) {
      wrap.appendChild(el("p", "small text-secondary mt-2 mb-0", "Показано " + rows.length + " з " + snap.attention_total + " найтерміновіших."));
    }
    return wrap;
  }

  function panel(title, hint, body) {
    var sec = el("section", "card mb-3 chart-panel");
    var b = el("div", "card-body");
    b.appendChild(el("h2", "h5 mb-1", title));
    if (hint) b.appendChild(el("p", "small text-secondary", hint));
    b.appendChild(body);
    sec.appendChild(b);
    return sec;
  }

  // ---------- Повне зведення: показники, графіки, таблиця строків ----------
  function render(box, snap) {
    box.textContent = "";
    var c = snap.counts;
    box.appendChild(kpis(c));

    var total = el("div");
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
    box.appendChild(panel("Загальний стан виконання",
      "Уся смуга — це всі заходи вибраної програми. Що більша зелена частина, то більше заходів виконано.", total));

    [["Виконання за розділами програми", "Кожен рядок — розділ програми. Праворуч — скільки заходів розділу вже виконано.",
      snap.sections, "Розділ"],
     ["Виконання за підрозділами", "Кожен рядок — відповідальний підрозділ. Угорі ті, що відстають найбільше: на них варто звернути увагу першими.",
      snap.departments, "Підрозділ"]].forEach(function (cfg) {
      var body = el("div");
      if (!cfg[2].length) body.appendChild(el("p", "text-secondary mb-0", "Немає даних."));
      else {
        body.appendChild(barRows(cfg[2]));
        body.appendChild(legend());
        body.appendChild(numbersTable(cfg[2], cfg[3]));
      }
      box.appendChild(panel(cfg[0], cfg[1], body));
    });

    box.appendChild(panel("Потребують уваги",
      "Заходи, у яких строк уже минув, і ті, що мають бути виконані протягом " + snap.soon_days + " днів. Найтерміновіші — вгорі.",
      attentionTable(snap)));
  }

  return { el: el, pct: pct, summarize: summarize, render: render, periodText: periodText };
})();
