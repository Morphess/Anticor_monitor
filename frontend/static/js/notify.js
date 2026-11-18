// Дзвіночок сповіщень у верхній панелі (розмітка — templates/_bell.html).
// Кабінет сам вирішує, що вважати сповіщенням, і передає список у Notify.render.
(function () {
  "use strict";
  const el = Api.el;
  const bell = document.getElementById("bell");
  const panel = document.getElementById("notif-panel");
  const badge = document.getElementById("bell-count");
  const ul = document.getElementById("notif-list");

  function setPanel(show) {
    panel.classList.toggle("hidden", !show);
    bell.setAttribute("aria-expanded", String(show));
  }

  if (bell) {
    bell.addEventListener("click", function (e) { e.stopPropagation(); setPanel(panel.classList.contains("hidden")); });
    panel.addEventListener("click", function (e) { e.stopPropagation(); });
    document.addEventListener("click", function () { setPanel(false); });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && !panel.classList.contains("hidden")) { setPanel(false); bell.focus(); }
    });
  }

  window.Notify = {
    // list: [{lvl: "late"|"soon"|"rework"|"review", what, which, go: function}]
    render: function (list, emptyText) {
      if (!bell) return;
      badge.textContent = list.length > 99 ? "99+" : String(list.length);
      badge.classList.toggle("hidden", !list.length);
      bell.setAttribute("aria-label", "Сповіщення: " + list.length);
      ul.innerHTML = "";
      if (!list.length) {
        ul.appendChild(el("li", { class: "notif-empty", text: emptyText || "Нових сповіщень немає." }));
        return;
      }
      list.forEach(function (n) {
        ul.appendChild(el("li", {}, [el("button", { type: "button", onclick: function () { setPanel(false); n.go(); } }, [
          el("span", { class: "lvl " + n.lvl, "aria-hidden": "true" }),
          el("span", {}, [el("div", { class: "what", text: n.what }), el("div", { class: "which", text: n.which })]),
        ])]));
      });
    },

    // Прокрутити до рядка й коротко підсвітити його.
    flash: function (row) {
      if (!row) return;
      row.scrollIntoView({ behavior: "smooth", block: "center" });
      row.classList.add("flash");
      setTimeout(function () { row.classList.remove("flash"); }, 1700);
    },

    daysLeft: function (m) {
      if (!m.deadline_on) return null;
      return Math.round((new Date(m.deadline_on + "T00:00:00") - new Date(Api.today() + "T00:00:00")) / 86400000);
    },
  };
})();
