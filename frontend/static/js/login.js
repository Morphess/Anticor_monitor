// Демо-вхід: роль лише визначає сторінку, автентифікація не виконується.
var form = document.getElementById("login-form");
form.addEventListener("submit", function (event) {
  event.preventDefault();
  var role = document.getElementById("role").value;
  var path = role === "executor" ? "/executor" : "/coordinator";
  window.location.assign(path);
});
