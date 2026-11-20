/* VYK — one independent order submission per executor/measure/period.
   Backend: POST /api/executions/submit (measure_id, period, order_number).
   Pending orders may be replaced via POST /api/executions/{id}/change-order. */
(function () {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const make = Api.el;
  const root = $('programs');
  const search = $('search');
  const filter = $('filter');
  const programFilter = $('executor-program');
  const period = $('period');
  const dialog = $('execution-dialog');
  const form = $('execution-form');
  const saveButton = $('execution-save');
  const message = $('execution-message');
  const expanded = new Set();
  const state = {
    programs: [], byProgram: {}, measures: [], sections: {},
    executions: {}, reminders: {}, edit: null, loading: false,
  };
  const list = (v) => Array.isArray(v) ? v : [];
  const groupBy = (rows, key) => rows.reduce((result, row) => {
    (result[row[key]] ||= []).push(row);
    return result;
  }, {});
  const submission = (m) => state.executions[m.id] || null;
  const approved = (ex) => !!(ex && ex.status === 'approved' && !ex.document_changed);
  const pending = (ex) => !!(ex && ex.status === 'pending' && !ex.document_changed);
  const rework = (ex) => !!(ex && (ex.status === 'rejected' || ex.document_changed));
  const statusOf = (ex) => Api.statusOf(ex);
  const canSubmit = (ex) => !ex || rework(ex);
  const canChange = (ex) => pending(ex);
  const actionLabel = (ex) => canChange(ex) ? 'Підтвердити зміну наказу' :
    ex ? 'Повторно підтвердити виконання' : 'Підтвердити виконання';

  function daysLeft(m) {
    if (m.deadline_type && m.deadline_type !== 'date') return null;
    const reminder = state.reminders[m.id];
    if (reminder && Number.isFinite(Number(reminder.days_left))) return Number(reminder.days_left);
    if (window.Notify && typeof Notify.daysLeft === 'function') return Notify.daysLeft(m);
    if (!m.deadline_on) return null;
    const due = new Date(m.deadline_on + 'T12:00:00');
    const now = new Date();
    now.setHours(12, 0, 0, 0);
    return Math.round((due - now) / 86400000);
  }
  const attention = (m) => {
    const days = daysLeft(m);
    return !approved(submission(m)) && days !== null && days <= 7;
  };

  function toast(text, kind) {
    const host = $('executor-toasts');
    if (!host) return;
    const node = make('div', { class: 'executor-toast', 'data-kind': kind || 'success', role: kind === 'error' ? 'alert' : 'status' });
    node.appendChild(make('span', { text: text }));
    const close = make('button', { type: 'button', text: '×', 'aria-label': 'Закрити сповіщення' });
    close.addEventListener('click', () => node.remove());
    node.appendChild(close);
    host.appendChild(node);
    setTimeout(() => node.remove(), kind === 'error' ? 7000 : 4200);
  }
  function showError(err) {
    const text = err && err.message || 'Не вдалося завантажити дані';
    root.replaceChildren(make('div', { class: 'executor-inline-error', text }));
    const retry = make('button', { type: 'button', class: 'btn', text: 'Повторити' });
    retry.addEventListener('click', () => refresh(true));
    root.appendChild(retry);
    toast(text, 'error');
  }
  function errorInForm(text) {
    message.className = 'msg err';
    message.textContent = text;
  }
  function clearFormError() {
    message.className = 'msg';
    message.textContent = '';
  }
  function spanText(label, value, cls) {
    return make('div', { class: cls || '' }, [
      make('span', { class: 'm-label', text: label + ': ' }),
      make('span', { text: String(value == null ? '—' : value) }),
    ]);
  }
  function deadlineText(m) {
    if (m.deadline_on) return Api.fmtDate(m.deadline_on);
    if (m.deadline_type === 'ongoing') return 'Постійно';
    return m.deadline_description || 'Не вказано';
  }
  function deadlineChip(m) {
    if (approved(submission(m))) return null;
    const days = daysLeft(m);
    if (days === null) return null;
    if (days < 0) return make('span', { class: 'chip late', text: 'Прострочено на ' + (-days) + ' дн.' });
    if (days === 0) return make('span', { class: 'chip soon', text: 'Строк сьогодні' });
    if (days <= 7) return make('span', { class: 'chip soon', text: 'Залишилося ' + days + ' дн.' });
    return null;
  }

  async function loadMeasures() {
    // Routing API restricts VYK to personal, active assignments.
    const [mine, available] = await Promise.all([
      Api.get('/api/program-routing/my/measures'),
      Api.get('/api/program-routing/my/programs'),
    ]);
    const allowed = new Set(list(available).map((p) => p.id));
    const short = list(mine).filter((m) => allowed.has(m.program_id));
    const full = [];
    for (let i = 0; i < short.length; i += 6) {
      const batch = await Promise.all(short.slice(i, i + 6).map(async (m) => {
        try {
          const detail = await Api.get('/api/measures/' + encodeURIComponent(m.id), { noRedirect: true });
          return Object.assign({}, m, detail && detail.id === m.id ? detail : {});
        } catch (err) {
          if (err.status === 401) throw err;
          return m; // Some roles may see only MeasureBriefRead.
        }
      }));
      full.push(...batch);
    }
    const programs = list(available).filter((p) => full.some((m) => m.program_id === p.id));
    const meta = await Promise.all(programs.map(async (p) => {
      let detail = {}, sections = [];
      try { detail = await Api.get('/api/program-routing/programs/' + encodeURIComponent(p.id), { noRedirect: true }); }
      catch (err) { if (err.status === 401) throw err; }
      try { sections = await Api.get('/api/program-routing/programs/' + encodeURIComponent(p.id) + '/sections', { noRedirect: true }); }
      catch (err) { if (err.status === 401) throw err; }
      return { program: Object.assign({}, p, detail || {}), sections: list(sections) };
    }));
    state.programs = meta.map((x) => x.program).sort((a, b) => String(a.title || a.id).localeCompare(String(b.title || b.id), 'uk'));
    state.measures = full.sort(Api.byMeasureOrder);
    state.sections = Object.fromEntries(meta.flatMap((x) => x.sections.map((s) => [s.id, s])));
    state.byProgram = groupBy(state.measures, 'program_id');
    const selectedProgram = programFilter.value;
    programFilter.replaceChildren(make('option', { value: '', text: 'Усі мої програми' }));
    state.programs.forEach((p) => programFilter.appendChild(make('option', { value: p.id, text: p.title || p.id })));
    programFilter.value = state.programs.some((p) => p.id === selectedProgram) ? selectedProgram : '';
    const oldPeriod = period.value;
    Api.fillPeriods(period, state.programs);
    if (Array.from(period.options).some((o) => o.value === oldPeriod)) period.value = oldPeriod;
    if (state.programs.length === 1) expanded.add('p:' + state.programs[0].id);
    if (state.measures.length === 1) expanded.add('s:' + state.measures[0].program_id + ':' + state.measures[0].section_id);
  }

  async function loadSubmissions() {
    const [rows, reminderResult] = await Promise.all([
      Api.executions(period.value),
      Api.optional(Api.get('/api/deadline-reminders/?limit=100&offset=0', { noRedirect: true })),
    ]);
    const assignedIds = new Set(state.measures.map((m) => m.id));
    const actorId = Number(Api.userId());
    state.executions = {};
    // Defense in depth; the server already filters submissions by JWT user.
    list(rows).forEach((row) => {
      if (assignedIds.has(row.measure_id) && Number(row.submitted_by_user_id) === actorId) {
        state.executions[row.measure_id] = row;
      }
    });
    state.reminders = {};
    if (reminderResult.ok) {
      list(reminderResult.data && reminderResult.data.reminders).forEach((r) => {
        if (assignedIds.has(r.measure_id)) state.reminders[r.measure_id] = r;
      });
    }
  }

  async function refresh(full) {
    if (state.loading) return;
    state.loading = true;
    const button = $('executor-refresh');
    button.disabled = true;
    button.textContent = 'Оновлення…';
    root.setAttribute('aria-busy', 'true');
    try {
      if (full || !state.programs.length) await loadMeasures();
      await loadSubmissions();
      render();
      if (full) toast('Дані кабінету оновлено');
    } catch (err) {
      showError(err);
    } finally {
      state.loading = false;
      root.setAttribute('aria-busy', 'false');
      button.disabled = false;
      button.textContent = 'Оновити дані';
    }
  }

  function matches(m, p, q) {
    const section = state.sections[m.section_id];
    const ex = submission(m);
    return [p.id, p.title, m.id, m.description, m.sequence_number,
      section && section.title, ex && ex.order_number].some((v) => String(v || '').toLocaleLowerCase('uk').includes(q));
  }
  function matchesFilter(m, f) {
    const ex = submission(m);
    if (!f) return true;
    if (f === 'todo') return !ex;
    if (f === 'deadline') return attention(m);
    if (f === 'review') return pending(ex);
    if (f === 'rejected') return !!ex && ex.status === 'rejected' && !ex.document_changed;
    if (f === 'document-changed') return !!ex && ex.document_changed;
    if (f === 'done') return approved(ex);
    return true;
  }
  function updateCounters() {
    const rows = state.measures;
    const numbers = {
      'executor-total': rows.length,
      'executor-attention': rows.filter(attention).length,
      'executor-review': rows.filter((m) => pending(submission(m))).length,
      'executor-approved': rows.filter((m) => approved(submission(m))).length,
    };
    Object.entries(numbers).forEach(([id, n]) => { const node = $(id); if (node) node.textContent = String(n); });
    document.querySelectorAll('.executor-stat[data-stat-filter]').forEach((button) => {
      button.setAttribute('aria-pressed', String(button.dataset.statFilter === filter.value));
    });
  }
  function empty(title, desc, reset) {
    const node = make('div', { class: 'executor-empty' }, [
      make('h3', { text: title }), make('p', { text: desc }),
    ]);
    if (reset) {
      const btn = make('button', { type: 'button', class: 'btn', text: 'Скинути фільтри' });
      btn.addEventListener('click', () => {
        search.value = ''; filter.value = ''; programFilter.value = ''; render();
      });
      node.appendChild(btn);
    }
    return node;
  }
  function render() {
    updateCounters();
    root.replaceChildren();
    const q = search.value.trim().toLocaleLowerCase('uk');
    const f = filter.value;
    const pId = programFilter.value;
    const forced = !!(q || f || pId);
    if (!state.measures.length) {
      root.appendChild(empty('Поки немає призначених заходів', 'Зверніться до координатора підрозділу для призначення.', false));
      if (window.Notify) Notify.render([], 'Немає термінових повідомлень');
      return;
    }
    let count = 0;
    state.programs.forEach((p) => {
      if (pId && p.id !== pId) return;
      const all = state.byProgram[p.id] || [];
      const shown = all.filter((m) => matchesFilter(m, f) && (!q || matches(m, p, q)));
      if (!shown.length) return;
      count += shown.length;
      root.appendChild(programNode(p, all, shown, forced));
    });
    if (!count) root.appendChild(empty('Заходів не знайдено', 'Змініть пошук або фільтр.', true));
    notifications();
  }
  function toggle(key) {
    expanded.has(key) ? expanded.delete(key) : expanded.add(key);
    render();
  }
  function counter(rows) {
    return make('span', { class: 'count', text: 'Погоджено ' + rows.filter((m) => approved(submission(m))).length + ' / ' + rows.length });
  }
  function programNode(p, all, shown, forced) {
    const key = 'p:' + p.id;
    const visible = forced || expanded.has(key);
    const node = make('article', { class: 'prog' }, [
      make('button', { type: 'button', class: 'row-head', 'aria-expanded': String(visible), onclick: () => toggle(key) }, [
        make('span', { class: 'title' }, [make('span', { class: 'code', text: p.id }), p.title || p.id,
          p.organization_name ? make('span', { class: 'sub', text: p.organization_name }) : null]),
        counter(all),
      ]),
    ]);
    if (!visible) return node;
    const body = make('div', { class: 'prog-body' });
    const bySection = groupBy(shown, 'section_id');
    Object.keys(bySection).sort(Api.compareSections).forEach((sid) => {
      body.appendChild(sectionNode(p, sid, all.filter((m) => m.section_id === sid), bySection[sid], forced));
    });
    node.appendChild(body);
    return node;
  }
  function sectionNode(p, sid, all, shown, forced) {
    const key = 's:' + p.id + ':' + sid;
    const visible = forced || expanded.has(key);
    const node = make('section', { class: 'sec' }, [
      make('button', { type: 'button', class: 'row-head', 'aria-expanded': String(visible), onclick: () => toggle(key) }, [
        make('span', { class: 'title', text: Api.sectionTitle(state.sections, sid) }), counter(all),
      ]),
    ]);
    if (!visible) return node;
    node.appendChild(make('div', { class: 'mrow head', 'aria-hidden': 'true' }, [
      make('span', { text: 'Захід' }), make('span', { text: 'Контрольний строк' }),
      make('span', { text: 'Наказ' }), make('span', { text: 'Погодження' }),
    ]));
    shown.forEach((m) => node.appendChild(measureRow(m)));
    return node;
  }

  function measureRow(m) {
    const ex = submission(m);
    const status = statusOf(ex);
    const stateText = !ex ? 'Підтвердження ще не подано.' :
      ex.document_changed ? 'Версія наказу змінилася. Подайте підтвердження повторно.' :
      ex.status === 'pending' ? 'Очікує погодження координатора.' :
      ex.status === 'approved' ? 'Координатор погодив саме ваше подання.' :
      'Координатор відхилив подання; перегляньте причину та виправте номер наказу.';
    const name = make('div', {}, [
      make('div', { class: 'executor-measure-name' }, [
        make('span', { class: 'num', text: Api.measureNo(m) }),
        document.createTextNode(m.description || m.id),
      ]),
      make('div', { class: 'executor-measure-meta' }, [
        make('span', { text: 'Код: ' + m.id }),
        m.completion_indicator ? make('span', { text: 'Індикатор: ' + m.completion_indicator }) : null,
      ]),
    ]);
    const deadline = make('div', {}, [spanText('Строк', deadlineText(m), 'executor-deadline-label'), deadlineChip(m)]);
    const order = make('div', {}, [
      make('span', { class: 'm-label', text: 'Наказ: ' }),
      make('span', { class: 'executor-evidence-label', text: ex && ex.order_number ? '№ ' + ex.order_number : 'Не подано' }),
      ex && ex.order_version_id ? make('span', { class: 'executor-order-meta', text: 'Версія документа #' + ex.order_version_id }) : null,
      ex && ex.document_changed ? make('span', { class: 'chip soon', text: 'Наказ оновлено' }) : null,
    ]);
    const controls = make('div', {}, [
      Api.statusBadge(status),
      make('span', { class: 'executor-status-hint', text: stateText }),
    ]);
    if (ex && ex.rejection_reason && ex.status === 'rejected') {
      controls.appendChild(make('div', { class: 'executor-rejection', text: 'Причина відхилення: ' + ex.rejection_reason }));
    }
    const actions = make('div', { class: 'executor-order-actions' });
    if (ex && ex.document_api_path) {
      const download = make('button', { class: 'btn', type: 'button', text: 'Переглянути наказ' });
      download.addEventListener('click', async () => {
        download.disabled = true;
        try { await downloadOrder(ex); }
        catch (err) { toast(err.message || 'Не вдалося завантажити наказ', 'error'); }
        finally { download.disabled = false; }
      });
      actions.appendChild(download);
    }
    if (canSubmit(ex) || canChange(ex)) {
      const submit = make('button', { class: 'btn btn-dark', type: 'button', text: canChange(ex) ? 'Змінити наказ' : (ex ? 'Подати повторно' : 'Підтвердити виконання') });
      submit.addEventListener('click', () => openForm(m));
      actions.appendChild(submit);
    }
    if (actions.childNodes.length) controls.appendChild(actions);
    return make('div', { class: 'mrow', id: 'executor-measure-' + m.id }, [name, deadline, order, controls]);
  }

  // Download the original file using Bearer JWT, without opening a new tab.
  // The backend FileResponse carries the original name in Content-Disposition.
  async function downloadOrder(ex) {
    const path = ex && ex.document_api_path;
    if (!path || !path.startsWith('/api/')) throw new Error('Некоректний маршрут наказу');
    const token = Api.token();
    if (!token) throw new Error('Сесію завершено. Увійдіть повторно.');

    const response = await fetch(path, {
      credentials: 'same-origin',
      headers: { Authorization: 'Bearer ' + token },
    });
    if (!response.ok) {
      let reason = 'Не вдалося завантажити наказ (HTTP ' + response.status + ')';
      try {
        const body = await response.json();
        if (typeof body.detail === 'string') reason = body.detail;
      } catch (_) { /* Keep HTTP fallback. */ }
      throw new Error(reason);
    }

    const disposition = response.headers.get('Content-Disposition') || '';
    const utfName = disposition.match(/filename\*\s*=\s*(?:UTF-8'')?([^;]+)/i);
    const plainName = disposition.match(/filename\s*=\s*(?:"([^"]+)"|([^;]+))/i);
    let original = utfName ? utfName[1].trim() : (plainName ? (plainName[1] || plainName[2]).trim() : '');
    if (utfName) {
      try { original = decodeURIComponent(original); } catch (_) { /* Keep encoded name. */ }
    }
    original = original.replace(/^["']|["']$/g, '').replace(/[\\/:*?"<>|\u0000-\u001f]/g, '_').trim();
    const mime = (response.headers.get('Content-Type') || '').toLowerCase();
    const ext = mime.includes('pdf') ? '.pdf' :
      mime.includes('wordprocessingml') ? '.docx' :
      mime.includes('msword') ? '.doc' :
      mime.includes('image/png') ? '.png' :
      mime.includes('image/jpeg') ? '.jpg' : '';
    const number = String(ex.order_number || ex.id || 'document')
      .replace(/[\\/:*?"<>|\u0000-\u001f]/g, '_');
    const filename = original && original !== '.' && original !== '..'
      ? original : ('nakaz-' + number + ext);

    const blobUrl = URL.createObjectURL(await response.blob());
    try {
      const link = document.createElement('a');
      link.href = blobUrl;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
    } finally {
      setTimeout(() => URL.revokeObjectURL(blobUrl), 60000);
    }
  }

  function notifications() {
    if (!window.Notify) return;
    const rows = [];
    state.measures.forEach((m) => {
      const ex = submission(m);
      if (approved(ex)) return;
      const p = state.programs.find((x) => x.id === m.program_id);
      const which = (p ? p.title : m.program_id) + ' · ' + m.id;
      const go = () => {
        search.value = ''; filter.value = ''; programFilter.value = '';
        expanded.add('p:' + m.program_id);
        expanded.add('s:' + m.program_id + ':' + m.section_id);
        render();
        const row = $('executor-measure-' + m.id);
        if (row && Notify.flash) Notify.flash(row);
      };
      if (rework(ex)) rows.push({ lvl: 'rework', rank: 1, what: ex.document_changed ? 'Документ змінено' : 'Потрібне доопрацювання', which, go });
      if (pending(ex)) return;
      const days = daysLeft(m);
      if (days === null) return;
      if (days < 0) rows.push({ lvl: 'late', rank: 0, what: 'Строк прострочено на ' + (-days) + ' дн.', which, go });
      else if (days <= 7) rows.push({ lvl: 'soon', rank: 2, what: days === 0 ? 'Строк спливає сьогодні' : 'До строку: ' + days + ' дн.', which, go });
    });
    rows.sort((a, b) => a.rank - b.rank);
    Notify.render(rows, 'Немає заходів із терміновими нагадуваннями.');
  }

  function openForm(m) {
    const ex = submission(m);
    if (!(canSubmit(ex) || canChange(ex))) return;
    state.edit = m;
    form.reset();
    clearFormError();
    $('execution-title').textContent = canChange(ex) ? 'Змінити номер наказу' : 'Підтвердження виконання';
    form.elements.order_number.value = ex && ex.order_number || '';
    // Поля звіту НАЗК. Під час заміни наказу (change-order) змінюється лише номер.
    const today = new Date().toISOString().slice(0, 10);
    const reportFields = $('executor-report-fields');
    const changing = canChange(ex);
    reportFields.hidden = changing;
    ['outcome_status', 'completed_on', 'result_description', 'indicator_actual'].forEach((name) => {
      form.elements[name].disabled = changing;
    });
    form.elements.outcome_status.value = ex && ex.outcome_status === 'partial' ? 'partial' : 'completed';
    form.elements.completed_on.max = today;
    form.elements.completed_on.value = ex && ex.completed_on || today;
    form.elements.result_description.value = ex && ex.result_description || '';
    form.elements.indicator_actual.value = ex && ex.indicator_actual != null ? ex.indicator_actual : '';
    const section = state.sections[m.section_id];
    const isTraining = section ? Number(section.number) === 3 : String(m.section_id) === 'R3';
    $('executor-indicator-label').textContent = isTraining
      ? 'Кількість осіб, які взяли участь у навчанні'
      : 'Фактичне значення індикатора' + (m.indicator_unit ? ' (' + m.indicator_unit + ')' : '');
    form.elements.indicator_actual.required = isTraining;
    // This status describes what is awaiting action. The definitive state is
    // always loaded from the backend, never inferred from clicking the button.
    const status = $('executor-approval-status');
    if (canChange(ex)) {
      status.textContent = 'Очікує погодження координатора. До його рішення можна змінити номер наказу.';
    } else if (ex && ex.document_changed) {
      status.textContent = 'Файл наказу змінено. Очікується повторне підтвердження.';
    } else if (ex && ex.status === 'rejected') {
      status.textContent = 'Координатор відхилив подання.' + (ex.rejection_reason ? ' Причина: ' + ex.rejection_reason : '') + ' Очікується повторне підтвердження.';
    } else {
      status.textContent = 'Після подання наказ очікуватиме погодження координатора.';
    }
    saveButton.textContent = actionLabel(ex);
    dialog.showModal();
    form.elements.order_number.focus();
  }

  async function submit(event) {
    event.preventDefault();
    const m = state.edit;
    if (!m) return;
    const ex = submission(m);
    if (!(canSubmit(ex) || canChange(ex))) {
      errorInForm('Це виконання вже погоджено. Оновіть дані.');
      return;
    }
    if (!form.reportValidity()) return;
    const number = String(form.elements.order_number.value || '').trim();
    if (!number) { errorInForm('Вкажіть номер зареєстрованого наказу.'); return; }
    if (canChange(ex) && number === ex.order_number) {
      errorInForm('Ви вже подали цей номер. Для зміни введіть інший наказ.');
      return;
    }
    const body = { measure_id: m.id, period: period.value, order_number: number };
    const isChange = canChange(ex);
    if (!isChange) {
      const description = String(form.elements.result_description.value || '').trim();
      if (description.length < 10) { errorInForm('Опишіть результат виконання (щонайменше 10 символів).'); return; }
      body.result_description = description;
      body.outcome_status = form.elements.outcome_status.value;
      body.completed_on = form.elements.completed_on.value || null;
      const indicator = String(form.elements.indicator_actual.value || '').trim();
      if (indicator !== '') body.indicator_actual = indicator;
    }
    saveButton.disabled = true;
    saveButton.textContent = 'Надсилання…';
    clearFormError();
    try {
      // The backend pins the current immutable order_version and verifies its SHA-256.
      if (isChange) {
        await Api.post('/api/executions/' + encodeURIComponent(ex.id) + '/change-order', { order_number: number });
      } else {
        await Api.post('/api/executions/submit', body);
      }
      dialog.close();
      toast(isChange
        ? 'Номер наказу змінено. Координатору надіслано повідомлення, очікується погодження.'
        : 'Номер наказу подано. Очікує погодження координатора.');
      await refresh(false);
    } catch (err) {
      const detail = err && err.message || 'Не вдалося подати наказ';
      errorInForm(detail);
      // A duplicate or changed submission may need reloading current server state.
      if (err && err.status === 409) toast('Подання не прийнято. Перевірте повідомлення у формі.', 'error');
    } finally {
      saveButton.disabled = false;
      saveButton.textContent = actionLabel(ex);
    }
  }

  async function init() {
    if (!await Api.requireRole('VYK')) return;
    const me = Api.me || {};
    const id = $('ident');
    if (id) { id.textContent = 'Виконавець'; id.title = 'Роль: Виконавець'; }
    $('executor-title').textContent = String(me.position || 'Мої призначені заходи').trim();
    await refresh(false);
  }
  search.addEventListener('input', render);
  filter.addEventListener('change', render);
  programFilter.addEventListener('change', render);
  period.addEventListener('change', () => refresh(false));
  $('executor-refresh').addEventListener('click', () => refresh(true));
  document.querySelectorAll('.executor-stat[data-stat-filter]').forEach((b) => {
    b.addEventListener('click', () => {
      filter.value = b.dataset.statFilter;
      render();
      document.querySelector('.executor-toolbar')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  });
  form.addEventListener('submit', submit);
  $('execution-close').addEventListener('click', () => dialog.close());
  $('execution-cancel').addEventListener('click', () => dialog.close());
  dialog.addEventListener('close', () => { state.edit = null; });
  init();
})();
