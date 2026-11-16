// Локальний прототип: введене значення та статус зберігаються лише в браузері.
document.querySelectorAll(".order-input").forEach(function (input) {
  var id = input.dataset.measure;
  var msg = document.getElementById("msg-" + id);
  var status = document.getElementById("status-" + id);

  function show(ok, text) {
    input.classList.toggle("is-ok", ok);
    input.classList.toggle("is-err", !ok);
    msg.className = "order-msg " + (ok ? "ok" : "err");
    msg.textContent = text;
  }

  input.addEventListener("input", function () {
    input.classList.remove("is-ok", "is-err");
    msg.textContent = "";
  });

  input.addEventListener("keydown", function (e) {
    if (e.key !== "Enter") return;
    e.preventDefault();
    if (!input.value.trim()) { show(false, "Введіть номер наказу"); return; }
    show(true, "Збережено локально (демо)");
    status.textContent = "виконано (демо)";
    status.className = "st st-done";
    try { localStorage.setItem("monitor-preview-order-" + id, input.value.trim()); } catch (_) {}
  });

  try {
    var saved = localStorage.getItem("monitor-preview-order-" + id);
    if (saved) { input.value = saved; show(true, "Збережено локально (демо)"); }
  } catch (_) {}
});
