// Підтримка управлінських рішень: оцінка ризику невиконання кожного заходу,
// прогноз виконання на кінець періоду й автоматичні рекомендації.
// Усе рахується в браузері з даних /api/measures, /api/executions, /api/evidences,
// /api/deadline-changes і (якщо доступно ролі) /api/risk-flags. Правила прозорі:
// кожен бал має текстову причину, яку бачить користувач.
(function () {
  "use strict";
  const el = Api.el;
  const DAY = 86400000;

  function parse(iso) {
    const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso || "");
    return m ? new Date(+m[1], +m[2] - 1, +m[3]) : null;
  }
  function days(a, b) { return Math.round((b - a) / DAY); }
  function plural(n, one, few, many) {
    const n10 = n % 10, n100 = n % 100;
    if (n10 === 1 && n100 !== 11) return n + " " + one;
    if (n10 >= 2 && n10 <= 4 && (n100 < 12 || n100 > 14)) return n + " " + few;
    return n + " " + many;
  }

  const Insights = {
    LEVELS: {
      high: { label: "Високий", cls: "risk-high" },
      mid: { label: "Середній", cls: "risk-mid" },
      low: { label: "Низький", cls: "risk-low" },
    },

    periodBounds: function (period) {
      const m = /^(\d{4})-H([12])$/.exec(period || "");
      if (!m) return null;
      const y = +m[1];
      return m[2] === "1"
        ? { start: new Date(y, 0, 1), end: new Date(y, 5, 30) }
        : { start: new Date(y, 6, 1), end: new Date(y, 11, 31) };
    },

    levelOf: function (score) { return score >= 60 ? "high" : score >= 30 ? "mid" : "low"; },

    // Оцінка одного заходу: бал 0–100 і причини.
    score: function (m, ctx) {
      const ex = ctx.executions[m.id];
      const status = Api.statusOf(ex);
      const reasons = [];
      let s = 0;
      const add = function (pts, text) { s += pts; reasons.push(text); };
      const evidence = (ctx.evidenceByMeasure[m.id] || []).length;
      const changes = (ctx.changesByMeasure[m.id] || []).length;
      const flags = ctx.flagsByMeasure[m.id] || [];
      const deadline = parse(m.deadline_on);
      const daysLeft = deadline ? days(ctx.today, deadline) : null;

      if (status === "done") {
        if (!evidence) add(15, "погоджено без підтвердних матеріалів");
      } else {
        if (daysLeft !== null && daysLeft < 0) add(45, "строк минув " + plural(-daysLeft, "день", "дні", "днів") + " тому");
        else if (daysLeft !== null && daysLeft <= 30) add(30, "до строку " + plural(daysLeft, "день", "дні", "днів"));
        else if (daysLeft !== null && daysLeft <= 90) add(15, "до строку " + plural(daysLeft, "день", "дні", "днів"));
        else if (daysLeft === null && ctx.elapsed > .5 && (status === "none" || status === "not")) {
          add(15, "постійний захід без звіту за період");
        }
        if (status === "rework") add(20, "звіт повернуто на доопрацювання");
        else if (status === "not") add(ex ? 25 : 15, ex ? "позначено як невиконаний" : "звіт не подано");
        else if (status === "none") add(15, "виконання не розпочато");
        else if (status === "work") add(10, "у роботі, звіту немає");
        if (status === "review" && !evidence) add(15, "на розгляді без підтвердних матеріалів");
      }
      if (changes) add(Math.min(20, changes * 10), "строк переносили " + plural(changes, "раз", "рази", "разів"));
      if (flags.length) add(Math.min(30, flags.length * 10), "сигнали " + flags.map(function (f) { return f.code; }).join(", "));
      if (ex && ex.indicator_actual != null && m.indicator_target != null && Number(ex.indicator_actual) < Number(m.indicator_target)) {
        add(15, "показник " + Number(ex.indicator_actual) + " з " + Number(m.indicator_target) + (m.indicator_unit ? " " + m.indicator_unit : ""));
      }
      s = Math.min(100, s);
      return { m: m, ex: ex, status: status, score: s, level: Insights.levelOf(s), reasons: reasons, daysLeft: daysLeft, evidence: evidence, changes: changes, flags: flags };
    },

    // ctx: {measures, executions, evidenceByMeasure, changesByMeasure, flagsByMeasure, period, flagsOk}
    assess: function (ctx) {
      const b = Insights.periodBounds(ctx.period);
      const today = parse(Api.today());
      const elapsed = b ? Math.max(0, Math.min(1, (today - b.start) / (b.end - b.start))) : 1;
      const full = Object.assign({ evidenceByMeasure: {}, changesByMeasure: {}, flagsByMeasure: {} }, ctx, { today: today, elapsed: elapsed });
      const items = ctx.measures.map(function (m) { return Insights.score(m, full); });
      items.sort(function (a, b2) { return b2.score - a.score || Api.byMeasureOrder(a.m, b2.m); });
      const forecast = Insights.forecast(items, elapsed, b, today);
      const role = ctx.role || Api.role();
      const recs = Insights.recommend(items, forecast, full).filter(function (r) { return r.roles.indexOf(role) !== -1; });
      return { items: items, forecast: forecast, recs: recs };
    },

    // Імовірність виконання заходу ≈ 1 − бал/100; погоджені — 1.
    forecast: function (items, elapsed, bounds, today) {
      const n = items.length || 1;
      const c = { done: 0, review: 0, rework: 0, open: 0 };
      let expected = 0;
      items.forEach(function (it) {
        if (it.status === "done") { c.done++; expected += 1; return; }
        if (it.status === "review") c.review++;
        else if (it.status === "rework") c.rework++;
        else c.open++;
        expected += Math.max(0, 1 - it.score / 100) * (it.status === "review" ? 1 : .9);
      });
      return {
        elapsed: elapsed,
        donePct: Math.round(c.done * 100 / n),
        reportedPct: Math.round((c.done + c.review) * 100 / n),
        projectedPct: items.length ? Math.round(expected * 100 / n) : 0,
        atRisk: items.filter(function (it) { return it.level === "high" && it.status !== "done"; }).length,
        watch: items.filter(function (it) { return it.level === "mid" && it.status !== "done"; }).length,
        daysToEnd: bounds ? Math.max(0, days(today, bounds.end)) : null,
        lag: Math.round(elapsed * 100) - Math.round(c.done * 100 / n),
      };
    },

    // Правила рекомендацій. Кожна адресована ролям (roles), які мають виконати дію:
    // кабінет показує лише рекомендації своєї ролі. Порядок: рівень, далі кількість заходів.
    recommend: function (items, f, ctx) {
      const recs = [];
      const open = items.filter(function (it) { return it.status !== "done"; });
      const nums = function (list) { return list.map(function (it) { return Api.measureNo(it.m); }); };
      const push = function (r) { recs.push(r); };

      const overdue = open.filter(function (it) { return it.daysLeft !== null && it.daysLeft < 0; });
      if (overdue.length) push({
        level: "high", roles: ["KER"], owner: "Керівник → підрозділи",
        title: "Прострочено " + plural(overdue.length, "захід", "заходи", "заходів"),
        text: "Строк виконання минув, а погодженого звіту немає. За критеріями програми такі заходи отримують статус «Не виконано».",
        action: "Доручити відповідальним підрозділам у 5-денний строк подати звіт або пояснення причин невиконання з обґрунтованим запитом на перенесення строку.",
        refs: nums(overdue),
      });

      if (f.lag >= 20 && items.length >= 3) push({
        level: f.lag >= 40 ? "high" : "mid", roles: ["KER"], owner: "Керівник",
        title: "Темп виконання відстає від графіка",
        text: "Минуло " + Math.round(f.elapsed * 100) + " % періоду, погоджено " + f.donePct + " % заходів. Прогноз на кінець періоду — близько " + f.projectedPct + " %.",
        action: "Винести стан виконання на засідання Робочої групи з оцінювання корупційних ризиків і затвердити графік проміжного контролю.",
        refs: [],
      });

      const soon = open.filter(function (it) { return it.daysLeft !== null && it.daysLeft >= 0 && it.daysLeft <= 30 && it.status !== "review"; });
      if (soon.length) push({
        level: "high", roles: ["KOORD"], owner: "Координатор",
        title: plural(soon.length, "захід", "заходи", "заходів") + " зі строком у найближчі 30 днів без звіту",
        text: "Найвища ймовірність невиконання: строк близько, а результат ще не подано.",
        action: "Запровадити щотижневий контроль і запитати у виконавців проміжний стан готовності.",
        refs: nums(soon),
      });

      // Системні проблеми підрозділів: ≥ 3 заходи середнього/високого ризику.
      const byDept = {};
      open.forEach(function (it) {
        if (it.level === "low") return;
        const k = it.m.responsible_department_id || "";
        (byDept[k] = byDept[k] || []).push(it);
      });
      Object.keys(byDept).filter(function (k) { return byDept[k].length >= 3; })
        .sort(function (a, b) { return byDept[b].length - byDept[a].length; }).slice(0, 3)
        .forEach(function (k) {
          const title = "Концентрація ризиків: " + Api.deptName(k);
          const text = plural(byDept[k].length, "захід", "заходи", "заходів") + " підрозділу мають середній або високий ризик невиконання.";
          push({
            level: "mid", roles: ["KER"], owner: "Керівник", title: title, text: text, refs: nums(byDept[k]),
            action: "Заслухати керівника підрозділу; за потреби ініціювати позапланову антикорупційну перевірку стану виконання.",
          });
          push({
            level: "mid", roles: ["ANAL"], owner: "Аналітик", title: title, text: text, refs: nums(byDept[k]),
            action: "Підготувати для керівника аналітичну довідку про причини відставання підрозділу.",
          });
        });

      const stale = items.filter(function (it) {
        if (it.status !== "review" || !it.ex || !it.ex.submitted_at) return false;
        return days(parse(it.ex.submitted_at.slice(0, 10)), ctx.today) > 10;
      });
      const review = items.filter(function (it) { return it.status === "review"; });
      if (review.length) push({
        level: stale.length ? "mid" : "low", roles: ["KOORD"], owner: "Координатор",
        title: plural(review.length, "звіт", "звіти", "звітів") + " очікують розгляду",
        text: stale.length ? plural(stale.length, "звіт", "звіти", "звітів") + " без рішення понад 10 днів." : "Звіти подано виконавцями й чекають рішення координатора.",
        action: "Розглянути звіти: погодити або повернути на доопрацювання з конкретними зауваженнями.",
        refs: nums(stale.length ? stale : review),
      });

      const noEvidence = items.filter(function (it) { return (it.status === "done" || it.status === "review") && !it.evidence; });
      if (noEvidence.length) push({
        level: "mid", roles: ["KOORD"], owner: "Координатор → виконавці",
        title: "Немає підтвердних матеріалів",
        text: plural(noEvidence.length, "захід", "заходи", "заходів") + " позначено виконаними або поданими без жодного документа. Це ознака формального закриття (RF2).",
        action: "Витребувати накази, акти або звіти та додати їх до електронного архіву підтверджень.",
        refs: nums(noEvidence),
      });

      const rework = items.filter(function (it) { return it.status === "rework"; });
      if (rework.length) push({
        level: "mid", roles: ["KOORD"], owner: "Координатор",
        title: plural(rework.length, "звіт", "звіти", "звітів") + " на доопрацюванні",
        text: "Повернуті звіти без визначеного строку доопрацювання часто переходять у прострочення.",
        action: "Встановити виконавцям конкретний строк повторного подання.",
        refs: nums(rework),
      });

      const moved = items.filter(function (it) { return it.changes >= 2; });
      if (moved.length) push({
        level: "mid", roles: ["KOORD"], owner: "Координатор (уповноважений підрозділ)",
        title: "Повторні перенесення строків",
        text: "Строк переносили двічі й більше — захід може бути нереалістичним або втратив актуальність.",
        action: "Розглянути зміни до Антикорупційної програми (розділ IV, перегляд програми) щодо цих заходів.",
        refs: nums(moved),
      });

      const below = items.filter(function (it) {
        return it.ex && it.ex.indicator_actual != null && it.m.indicator_target != null && Number(it.ex.indicator_actual) < Number(it.m.indicator_target);
      });
      if (below.length) push({
        level: "mid", roles: ["ANAL"], owner: "Аналітик",
        title: "Показник нижче цільового",
        text: "Фактичне значення індикатора не досягло плану (RF5).",
        action: "Проаналізувати причини й оцінити, чи знижено рівень відповідного корупційного ризику.",
        refs: nums(below),
      });

      // Найслабший розділ.
      const bySec = Api.groupBy(items.map(function (it) { return { sid: it.m.section_id, it: it }; }), "sid");
      let worst = null;
      Object.keys(bySec).forEach(function (sid) {
        const list = bySec[sid];
        if (list.length < 3) return;
        const pct = list.filter(function (x) { return x.it.status === "done"; }).length / list.length;
        if (pct < .5 && (!worst || pct < worst.pct)) worst = { sid: sid, pct: pct, n: list.length };
      });
      if (worst && f.elapsed > .5) push({
        level: "low", roles: ["ANAL"], owner: "Аналітик",
        title: "Найнижче виконання — розділ " + Api.sectionNo(worst.sid),
        text: "Погоджено " + Math.round(worst.pct * 100) + " % із " + worst.n + " заходів розділу.",
        action: "Підготувати аналітичну довідку щодо причин і врахувати її під час оцінювання корупційних ризиків.",
        refs: [],
      });

      const order = { high: 0, mid: 1, low: 2 };
      recs.sort(function (a, b) { return order[a.level] - order[b.level] || b.refs.length - a.refs.length; });
      return recs;
    },

    // ---------- Відображення ----------
    riskChip: function (it) {
      const lv = Insights.LEVELS[it.level];
      return el("span", { class: "risk " + lv.cls, title: "Ризик невиконання " + it.score + "/100" + (it.reasons.length ? ": " + it.reasons.join("; ") : ""), text: it.status === "done" && it.level === "low" ? "—" : String(it.score) });
    },

    deadlineChip: function (it) {
      if (it.status === "done" || it.daysLeft === null) return null;
      if (it.daysLeft < 0) return el("span", { class: "chip late", text: "прострочено " + -it.daysLeft + " дн." });
      if (it.daysLeft <= 30) return el("span", { class: "chip soon", text: "ще " + it.daysLeft + " дн." });
      return null;
    },

    renderRecs: function (box, recs, limit) {
      box.innerHTML = "";
      const list = limit ? recs.slice(0, limit) : recs;
      if (!list.length) {
        box.appendChild(el("p", { class: "muted", text: "Відхилень, що потребують управлінських рішень, не виявлено." }));
        return;
      }
      box.appendChild(el("div", { class: "recs" }, list.map(function (r) {
        const refs = r.refs.slice(0, 12).map(function (n) { return el("span", { class: "chip", text: n }); });
        if (r.refs.length > 12) refs.push(el("span", { class: "chip", text: "+" + (r.refs.length - 12) }));
        return el("article", { class: "rec", "data-level": r.level }, [
          el("div", {}, [
            el("h3", { text: r.title }),
            el("p", { text: r.text }),
            el("div", { class: "action" }, [el("b", { text: "Рекомендована дія: " }), r.action]),
            refs.length ? el("div", { class: "refs", "aria-label": "Заходи" }, refs) : null,
          ]),
          el("div", { class: "who-acts" }, [
            el("span", { class: "lvl", text: Insights.LEVELS[r.level].label + " пріоритет" }),
            r.owner,
          ]),
        ]);
      })));
      if (limit && recs.length > limit) {
        box.appendChild(el("p", { class: "note", text: "Показано " + limit + " з " + recs.length + " рекомендацій." }));
      }
    },

    renderForecast: function (box, f) {
      box.innerHTML = "";
      const tone = f.projectedPct >= 85 ? "ok" : f.projectedPct >= 60 ? "warn" : "bad";
      const card = function (n, l, sub, t) {
        return el("div", { class: "card", "data-tone": t || null }, [
          el("div", { class: "n", text: n }), el("div", { class: "l", text: l }), sub ? el("div", { class: "sub", text: sub }) : null,
        ]);
      };
      box.appendChild(card(f.projectedPct + " %", "Прогноз виконання на кінець періоду", "погоджено зараз " + f.donePct + " %", tone));
      box.appendChild(card(String(f.atRisk), "Заходів під загрозою невиконання", f.watch ? "ще " + f.watch + " — під наглядом" : "", f.atRisk ? "bad" : "ok"));
      box.appendChild(card(Math.round(f.elapsed * 100) + " %", "Минуло часу періоду", f.daysToEnd !== null ? "до кінця " + f.daysToEnd + " дн." : "", f.lag >= 20 ? "warn" : null));
    },
  };

  window.Insights = Insights;
})();
