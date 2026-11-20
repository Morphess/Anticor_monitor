/* UI-елементи адміністратора: короткочасні Toast та компактні списки з пошуком.
   Без CDN: працює з CSS проєкту. Якщо вже підключений Bootstrap 5,
   використовується його Toast; для списків використовується автономний dropdown. */
(function () {
  "use strict";

  const toastRoot = document.getElementById("admin-toast-stack");
  const widgets = new WeakMap();
  const allWidgets = [];
  let toastCount = 0;
  let dropdownCount = 0;

  function toast(message, kind, duration) {
    if (!toastRoot) return;
    kind = ["success", "danger", "warning", "info"].includes(kind) ? kind : "info";
    duration = typeof duration === "number" ? duration : (kind === "danger" ? 6500 : 4000);
    const item = document.createElement("div");
    item.className = "toast admin-toast show admin-toast-" + kind;
    item.setAttribute("role", kind === "danger" ? "alert" : "status");
    item.setAttribute("aria-live", kind === "danger" ? "assertive" : "polite");
    item.setAttribute("aria-atomic", "true");
    item.setAttribute("data-bs-delay", String(duration));
    item.id = "admin-toast-" + ++toastCount;

    const header = document.createElement("div");
    header.className = "toast-header";
    const title = document.createElement("strong");
    title.className = "me-auto";
    title.textContent = ({ success: "Успішно", danger: "Помилка", warning: "Увага", info: "Повідомлення" })[kind];
    const close = document.createElement("button");
    close.type = "button";
    close.className = "btn-close admin-toast-close";
    close.setAttribute("aria-label", "Закрити повідомлення");
    close.textContent = "×";
    const body = document.createElement("div");
    body.className = "toast-body";
    body.textContent = String(message);
    header.append(title, close);
    item.append(header, body);
    toastRoot.appendChild(item);

    let timer;
    function remove() {
      clearTimeout(timer);
      item.remove();
    }
    close.addEventListener("click", remove);
    // Одночасно тримаємо на екрані не більше 4 сповіщень.
    while (toastRoot.children.length > 4) toastRoot.firstElementChild.remove();
    timer = setTimeout(remove, duration);
    return item;
  }

  // Компонент з пошуком: меню піднімаємо до top layer через Popover API.
  // Це вирішує обрізання dropdown прокруткою <dialog> і появу 2 scrollbars.
  function searchableSelect(select) {
    if (!select || widgets.has(select)) return;
    dropdownCount += 1;
    const nativeId = select.id || select.getAttribute("name") || "select";
    const listId = "admin-search-list-" + dropdownCount;
    select.classList.add("admin-native-select");
    select.tabIndex = -1;

    const wrapper = document.createElement("div");
    wrapper.className = "dropdown admin-search-select";
    const trigger = document.createElement("button");
    trigger.type = "button";
    trigger.className = "admin-search-trigger dropdown-toggle";
    trigger.setAttribute("aria-haspopup", "listbox");
    trigger.setAttribute("aria-expanded", "false");
    trigger.setAttribute("aria-controls", listId);
    trigger.setAttribute("aria-label", "Вибір: " + nativeId);
    const chosen = document.createElement("span");
    chosen.className = "admin-search-chosen";
    trigger.appendChild(chosen);

    const menu = document.createElement("div");
    menu.className = "dropdown-menu admin-search-menu";
    menu.id = listId;
    menu.setAttribute("popover", "manual");
    const search = document.createElement("input");
    search.type = "search";
    search.className = "admin-search-input";
    search.autocomplete = "off";
    search.placeholder = "Пошук за назвою або кодом…";
    search.setAttribute("aria-label", "Пошук у списку");
    const list = document.createElement("div");
    list.className = "admin-search-options";
    list.setAttribute("role", "listbox");
    list.setAttribute("aria-label", "Варіанти вибору");
    const empty = document.createElement("p");
    empty.className = "admin-search-empty hidden";
    empty.textContent = "Нічого не знайдено";
    menu.append(search, list, empty);

    wrapper.append(trigger);
    select.insertAdjacentElement("afterend", wrapper);
    // Внутрішньо модального вікна меню лишається його нащадком для фокуса.
    // Поза модалкою прикріплюємо його до body; ні в якому разі не в поле label.
    const host = select.closest("dialog") || document.body;
    host.appendChild(menu);

    let open = false;
    let buttons = [];
    let positionTick = 0;
    function updateLabel() {
      const current = select.selectedOptions[0];
      chosen.textContent = current ? current.textContent.trim() : "— Оберіть значення —";
      trigger.title = chosen.textContent;
      trigger.disabled = select.disabled;
    }
    function positionMenu() {
      if (!open) return;
      const rect = trigger.getBoundingClientRect();
      const margin = 10;
      const gap = 5;
      const viewportWidth = document.documentElement.clientWidth;
      const viewportHeight = window.innerHeight;
      const below = Math.max(0, viewportHeight - rect.bottom - margin - gap);
      const above = Math.max(0, rect.top - margin - gap);
      const upward = below < 285 && above > below;
      const space = upward ? above : below;
      const maxHeight = Math.max(48, Math.min(300, space));
      const width = Math.min(Math.max(rect.width, 260), viewportWidth - margin * 2);
      const left = Math.max(margin, Math.min(rect.left, viewportWidth - width - margin));
      menu.style.position = "fixed";
      menu.style.width = width + "px";
      menu.style.maxHeight = maxHeight + "px";
      menu.style.left = left + "px";
      menu.style.right = "auto";
      menu.style.bottom = "auto";
      menu.style.transform = "none";
      // Після відображення меню його фактична висота враховує результати пошуку.
      const height = menu.getBoundingClientRect().height;
      menu.style.top = (upward
        ? Math.max(margin, rect.top - gap - height)
        : Math.max(margin, Math.min(rect.bottom + gap, viewportHeight - height - margin))) + "px";
    }
    function queuePosition() {
      if (positionTick) cancelAnimationFrame(positionTick);
      positionTick = requestAnimationFrame(function () {
        positionTick = 0;
        positionMenu();
      });
    }
    function render() {
      updateLabel();
      list.replaceChildren();
      buttons = [];
      const term = search.value.trim().toLocaleLowerCase("uk");
      Array.from(select.options).forEach(function (option) {
        if (option.hidden || option.disabled) return;
        const label = option.textContent.trim();
        if (term && !String(label + " " + option.value).toLocaleLowerCase("uk").includes(term)) return;
        const button = document.createElement("button");
        button.type = "button";
        button.className = "dropdown-item admin-search-option";
        button.textContent = label;
        button.setAttribute("role", "option");
        button.setAttribute("aria-selected", String(option.value === select.value));
        if (option.value === select.value) button.classList.add("selected");
        button.addEventListener("click", function (event) {
          event.preventDefault();
          select.value = option.value;
          select.dispatchEvent(new Event("input", { bubbles: true }));
          select.dispatchEvent(new Event("change", { bubbles: true }));
          updateLabel();
          closeMenu(true);
        });
        list.appendChild(button);
        buttons.push(button);
      });
      empty.classList.toggle("hidden", Boolean(buttons.length));
      if (open) queuePosition();
    }
    function closeMenu(restoreFocus) {
      if (!open) return;
      open = false;
      if (positionTick) cancelAnimationFrame(positionTick);
      positionTick = 0;
      wrapper.classList.remove("show");
      menu.classList.remove("show");
      trigger.setAttribute("aria-expanded", "false");
      if (typeof menu.hidePopover === "function" && menu.matches(":popover-open")) {
        menu.hidePopover();
      }
      if (restoreFocus) trigger.focus({ preventScroll: true });
    }
    function openMenu() {
      if (select.disabled) return;
      allWidgets.forEach(function (widget) { widget.close(false); });
      open = true;
      search.value = "";
      render();
      wrapper.classList.add("show");
      menu.classList.add("show");
      trigger.setAttribute("aria-expanded", "true");
      if (typeof menu.showPopover === "function") {
        menu.showPopover();
      }
      positionMenu();
      search.focus({ preventScroll: true });
    }
    trigger.addEventListener("click", function (event) {
      event.preventDefault();
      event.stopPropagation();
      open ? closeMenu(false) : openMenu();
    });
    trigger.addEventListener("keydown", function (event) {
      if (["ArrowDown", "ArrowUp", "Enter", " "].includes(event.key)) {
        event.preventDefault();
        if (!open) openMenu();
        if (event.key === "ArrowDown" && buttons[0]) buttons[0].focus();
      }
    });
    search.addEventListener("input", render);
    search.addEventListener("keydown", function (event) {
      if (event.key === "Escape") { event.preventDefault(); closeMenu(true); }
      if (event.key === "ArrowDown" && buttons.length) { event.preventDefault(); buttons[0].focus(); }
      if (event.key === "ArrowUp" && buttons.length) { event.preventDefault(); buttons[buttons.length - 1].focus(); }
      if (event.key === "Enter" && buttons.length === 1) { event.preventDefault(); buttons[0].click(); }
    });
    list.addEventListener("keydown", function (event) {
      const i = buttons.indexOf(document.activeElement);
      if (event.key === "Escape") { event.preventDefault(); closeMenu(true); }
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        const next = Math.max(0, Math.min(buttons.length - 1, i + (event.key === "ArrowDown" ? 1 : -1)));
        if (buttons[next]) buttons[next].focus();
      }
    });
    menu.addEventListener("toggle", function (event) {
      if (event.newState === "closed" && open) closeMenu(false);
    });
    select.addEventListener("change", function () { if (open) render(); else updateLabel(); });
    const widget = {
      refresh: function () { if (open) render(); else updateLabel(); },
      close: closeMenu,
      menu: menu,
      wrapper: wrapper,
      position: positionMenu,
    };
    widgets.set(select, widget);
    allWidgets.push(widget);
    updateLabel();
  }

  document.addEventListener("pointerdown", function (event) {
    if (!allWidgets.some(function (widget) {
      return widget.wrapper.contains(event.target) || widget.menu.contains(event.target);
    })) allWidgets.forEach(function (widget) { widget.close(false); });
  });
  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") allWidgets.forEach(function (widget) { widget.close(false); });
  });
  // Попап позиціонується за полем, навіть якщо dialog або сторінку прокрутили.
  document.addEventListener("scroll", function (event) {
    if (event.target.closest && event.target.closest(".admin-search-options")) return;
    allWidgets.forEach(function (widget) { widget.position(); });
  }, true);
  window.addEventListener("resize", function () {
    allWidgets.forEach(function (widget) { widget.position(); });
  });

  window.AdminUI = {
    toast: toast,
    initSelects: function (container) {
      (container || document).querySelectorAll("select").forEach(searchableSelect);
    },
    refreshSelect: function (select) {
      const widget = widgets.get(select);
      if (widget) widget.refresh();
    },
    refreshAll: function () {
      allWidgets.forEach(function (widget) { widget.refresh(); });
    },
    closeAll: function () {
      allWidgets.forEach(function (widget) { widget.close(false); });
    },
  };
})();
