// Виконавець вводить номер наказу й натискає Enter — сервер перевіряє наказ у базі.
function el(tag, cls, text) {
  var e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}

function rowNode(r) {
  var tr = el("tr");
  tr.appendChild(el("td", "name", r.order_title));
  tr.appendChild(el("td", "", r.organ));
  tr.appendChild(el("td", "nowrap", r.start));
  tr.appendChild(el("td", "nowrap", r.end));

  var td = el("td");
  var label = el("label", "sr", "Номер наказу для заходу " + r.id);
  label.htmlFor = "order-" + r.id;
  var input = el("input", "order-input" + (r.entered ? " is-ok" : ""));
  input.id = "order-" + r.id;
  input.value = r.entered;
  input.placeholder = "№ і Enter";
  input.autocomplete = "off";
  input.setAttribute("aria-describedby", "msg-" + r.id);
  var msg = el("div", "order-msg" + (r.entered ? " ok" : ""), r.entered ? "Успіх" : "");
  msg.id = "msg-" + r.id;
  msg.setAttribute("role", "status");
  td.appendChild(label);
  td.appendChild(input);
  td.appendChild(msg);
  tr.appendChild(td);

  var stTd = el("td");
  var status = el("span", "st st-" + r.st, r.status);
  stTd.appendChild(status);
  tr.appendChild(stTd);

  var goal = el("td");
  goal.appendChild(el("div", "goal", r.goal));
  goal.appendChild(el("div", "muted", r.indicator));
  tr.appendChild(goal);
  tr.appendChild(el("td", "", r.note));

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
    Api.post("/api/executor/check-order", { measure_id: r.id, number: input.value })
      .then(function (res) {
        show(res.ok, res.message);
        if (res.ok) {
          status.textContent = res.status;
          status.className = "st st-" + res.st;
        }
      })
      .catch(function (ex) { show(false, ex.message); });
  });
  return tr;
}

Api.get("/api/executor/rows")
  .then(function (data) {
    document.getElementById("unit").textContent = data.unit;
    var body = document.getElementById("rows");
    body.textContent = "";
    if (!data.rows.length) {
      var tr = el("tr"), td = el("td", "muted", "Вашому підрозділу ще не призначено заходів.");
      td.colSpan = 8;
      tr.appendChild(td);
      body.appendChild(tr);
    }
    data.rows.forEach(function (r) { body.appendChild(rowNode(r)); });
  })
  .catch(function (ex) {
    document.getElementById("rows").textContent = "";
    document.getElementById("page-error").textContent = ex.message;
  });
