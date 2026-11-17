// Вкладки: кнопки role=tab у role=tablist, панель — за aria-controls. Вибрана вкладка запам'ятовується.
var Tabs = (function () {
  var tabs = Array.prototype.slice.call(document.querySelectorAll("[role=tablist] [role=tab]"));
  var KEY = "tab:" + location.pathname;

  function select(id) {
    if (!document.getElementById(id)) return;
    tabs.forEach(function (b) {
      var on = b.id === id;
      b.setAttribute("aria-selected", on);
      b.classList.toggle("active", on);
      b.tabIndex = on ? 0 : -1;
      document.getElementById(b.getAttribute("aria-controls")).hidden = !on;
    });
    try { sessionStorage.setItem(KEY, id); } catch (e) { /* без сховища */ }
  }

  tabs.forEach(function (b, i) {
    b.addEventListener("click", function () { select(b.id); });
    b.addEventListener("keydown", function (e) {
      if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
      var next = tabs[(i + (e.key === "ArrowRight" ? 1 : tabs.length - 1)) % tabs.length];
      select(next.id);
      next.focus();
    });
  });
  try { var saved = sessionStorage.getItem(KEY); if (saved) select(saved); } catch (e) { /* без сховища */ }

  return { select: select };
})();
