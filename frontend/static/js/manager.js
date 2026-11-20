/* Read-only KER dashboard. All figures and recommendations come from /api/management/*.
   Do not call coordinator assignment, review, orders or reporting endpoints here. */
(function () {
  'use strict';
  const $ = id => document.getElementById(id);
  const app = $('manager-dashboard');
  if (!app) return;

  const state = { dashboard: null, departmentProgress: null, programs: [], measures: [], risks: [], recs: [], deadlines: [] };
  let departmentProgressRequest = 0;
  const LEVEL = {critical: 'Критичний', high: 'Високий', medium: 'Середній', low: 'Низький'};
  const TREND = {improved: 'Покращується', worsened: 'Погіршується', unchanged: 'Без змін', no_data: 'Немає вимірювань'};
  const STATUS = {completed: 'Виконано', partial: 'Частково виконано', in_progress: 'У процесі', not_completed: 'Не виконано', not_started: 'Не подано'};

  function node(tag, cls, text) {
    const element = document.createElement(tag);
    if (cls) element.className = cls;
    if (text !== undefined && text !== null) element.textContent = String(text);
    return element;
  }
  function add(parent, ...children) { children.forEach(child => {if (child) parent.appendChild(child);}); return parent; }
  function clear(el) { el.replaceChildren(); return el; }
  function muted(text) { return node('span', 'mgr-muted', text); }
  function info(id, text) { $(id).textContent = text; }
  function humanDate(date) { return date ? Api.fmtDate(date) : '—'; }
  function textValue(value) { return value === null || value === undefined ? '—' : String(value); }
  function matches(query, ...fields) { return !query || fields.some(field => String(field ?? '').toLocaleLowerCase('uk').includes(query)); }
  function message(text) { const box = $('mgr-message'); box.textContent = text || ''; box.hidden = !text; }
  function empty(host, label) { add(clear(host), node('p', 'mgr-empty', label)); }

  function measuresWord(n) {
    const last = n % 10, lastTwo = n % 100;
    return n + ' ' + ((lastTwo >= 11 && lastTwo <= 14) ? 'заходів'
      : last === 1 ? 'захід' : last >= 2 && last <= 4 ? 'заходи' : 'заходів');
  }

  // A complete routed programme is visible, while management statistics are
  // restricted to the executor assignments in the KER's department branch.
  function measureTotals(measureId) {
    const totals = {assigned: 0, approved: 0, pending: 0, rejected: 0, not_submitted: 0};
    for (const department of state.departmentProgress?.departments || []) {
      const row = (department.measures || []).find(m => m.measure_id === measureId);
      if (!row) continue;
      Object.keys(totals).forEach(key => { totals[key] += Number(row[key] || 0); });
    }
    return totals;
  }
  function completeInScope(measure) {
    if (!measure.in_scope) return false;
    const t = measureTotals(measure.measure_id);
    return t.assigned > 0 && t.approved === t.assigned;
  }

  function setTab(name) {
    app.querySelectorAll('[data-mgr-tab]').forEach(btn => {
      const on = btn.dataset.mgrTab === name;
      btn.setAttribute('aria-selected', on ? 'true' : 'false');
    });
    app.querySelectorAll('[data-mgr-panel]').forEach(panel => {
      panel.hidden = panel.dataset.mgrPanel !== name;
    });
  }

  // Management statistics use today's server-side snapshot. A reporting period
  // that has not started cannot be queried (backend rejects as_of < start).
  // Keep future periods visible in the dropdown but not selectable.
  function guardReportingPeriod() {
    const select = $('mgr-period');
    const current = Api.currentPeriod();
    for (const option of select.options) {
      const future = /^\d{4}-H[12]$/.test(option.value) && option.value > current;
      option.disabled = future;
      if (future) option.title = 'Період ще не почався';
    }
    if (!select.value || select.value > current) {
      let fallback = [...select.options].find(opt => opt.value === current);
      if (!fallback) {
        fallback = new Option(Api.periodLabel(current), current);
        select.add(fallback);
      }
      select.value = fallback.value;
      // Keep the shared saved preference consistent across reloads.
      if (typeof Api.pref === 'function') Api.pref('period', fallback.value);
    }
    return select.value;
  }

  function kpis() {
    const d = state.dashboard || {};
    // Total = entire authorised programme passports, NOT only managed measures.
    info('mgr-kpi-total', state.measures.length);
    const loaded = Boolean(state.departmentProgress && state.departmentProgress.period === $('mgr-period').value);
    info('mgr-kpi-completed', loaded ? state.measures.filter(completeInScope).length : Number(d.approved_completed || 0));
    // Pending submissions in the managed branch, one entry per executor.
    info('mgr-kpi-pending', loaded
      ? state.departmentProgress.departments.reduce((n, dep) => n + Number(dep.pending || 0), 0)
      : Number(d.awaiting_approval || 0));
    info('mgr-kpi-overdue', Number(d.overdue || 0));
    info('mgr-position', Api.me && Api.me.position ? Api.me.position : 'Керівник');
    info('mgr-department', d.department_name || 'Підрозділ керівника');
  }

  function progress() {
    const host = clear($('mgr-department-progress'));
    const result = state.departmentProgress;
    const rows = result?.departments || [];
    const search = $('mgr-department-search').value.trim().toLocaleLowerCase('uk');
    const found = rows.filter(r => matches(search, r.department_id, r.department_name));
    if (!result) return empty(host, 'Дані про прогрес за підрозділами завантажуються…');
    if (!found.length) return empty(host, 'Підрозділів за цим пошуком не знайдено.');
    found.forEach(dept => {
      const box = node('article', 'mgr-department-card');
      const heading = node('div', 'mgr-department-head');
      const departmentName = dept.department_name + (dept.is_own_department ? ' · Ваш підрозділ' : '');
      add(heading, node('strong', '', departmentName),
        node('span', 'mgr-count', 'Погоджено ' + dept.approved + ' із ' + dept.assigned));
      const track = node('div', 'mgr-progress-track');
      const bar = node('div', 'mgr-progress-bar');
      const ratio = dept.assigned > 0 ? (100 * dept.approved / dept.assigned) : 0;
      bar.style.width = Math.max(0, Math.min(100, ratio)) + '%';
      track.setAttribute('role', 'progressbar');
      track.setAttribute('aria-valuenow', String(dept.approved));
      track.setAttribute('aria-valuemin', '0');
      track.setAttribute('aria-valuemax', String(dept.assigned));
      track.setAttribute('aria-label', 'Погоджено виконавців — ' + dept.department_name);
      add(track, bar);
      add(box, heading, track,
        node('p', 'mgr-muted', 'Очікують: ' + dept.pending +
          ' · Відхилено: ' + dept.rejected +
          ' · Не подано: ' + dept.not_submitted));
      host.appendChild(box);
    });
  }

  // The KER API supplies one progress record per (department, measure).
  // Do not infer scope client-side: only render departments returned by the KER-only API.
  function measureDepartmentProgress(measure, host) {
    clear(host);
    // This measure is in the *programme passport*, not the branch work plan.
    if (measure.in_scope === false) {
      host.appendChild(node('p', 'mgr-muted', 'У вашому підрозділі та його підпорядкованих підрозділах виконання цього заходу не передбачене.'));
      return;
    }
    const result = state.departmentProgress;
    if (!result || result.period !== $('mgr-period').value) {
      host.appendChild(node('p', 'mgr-muted', 'Завантажуємо прогрес за підрозділами…'));
      return;
    }
    const departments = result.departments || [];
    if (!departments.length) {
      host.appendChild(node('p', 'mgr-muted', 'Немає доступних підрозділів.'));
      return;
    }
    departments.forEach(dept => {
      const item = (dept.measures || []).find(row => row.measure_id === measure.measure_id);
      const assigned = Number(item?.assigned || 0);
      const approved = Number(item?.approved || 0);
      const pending = Number(item?.pending || 0);
      const rejected = Number(item?.rejected || 0);
      const notSubmitted = Number(item?.not_submitted || 0);
      const card = node('div', 'mgr-measure-dept');
      const heading = node('div', 'mgr-measure-dept-head');
      add(heading,
        node('strong', '', dept.department_name + (dept.is_own_department ? ' · Ваш підрозділ' : '')),
        node('span', 'mgr-count', 'Погоджено ' + approved + ' із ' + assigned));
      card.appendChild(heading);
      if (assigned) {
        const track = node('div', 'mgr-progress-track mgr-measure-progress-track');
        const bar = node('div', 'mgr-progress-bar');
        bar.style.width = Math.max(0, Math.min(100, 100 * approved / assigned)) + '%';
        track.setAttribute('role', 'progressbar');
        track.setAttribute('aria-label', 'Погоджено призначень: ' + dept.department_name);
        track.setAttribute('aria-valuemin', '0');
        track.setAttribute('aria-valuemax', String(assigned));
        track.setAttribute('aria-valuenow', String(approved));
        track.appendChild(bar);
        add(card, track, node('p', 'mgr-muted',
          'Очікують: ' + pending + ' · Відхилено: ' + rejected +
          ' · Не подано: ' + notSubmitted));
      } else {
        card.appendChild(node('p', 'mgr-muted', 'Виконавців на цей захід не призначено.'));
      }
      host.appendChild(card);
    });
  }

  function updateMeasureProgress() {
    app.querySelectorAll('[data-mgr-measure-progress]').forEach(host => {
      const measure = state.measures.find(m => m.measure_id === host.dataset.mgrMeasureProgress);
      if (measure) measureDepartmentProgress(measure, host);
    });
  }

  function status(measure) {
    if (measure.in_scope === false) return ['Поза сферою виконання', 'outside'];
    if (!state.departmentProgress) return ['Дані завантажуються', 'none'];
    const t = measureTotals(measure.measure_id);
    if (t.assigned === 0) return ['Не призначено', 'none'];
    if (t.approved === t.assigned) return ['Виконано', 'approved'];
    if (t.pending > 0) return ['Очікує погодження', 'pending'];
    if (t.rejected > 0) return ['Відхилено', 'rejected'];
    if (t.approved > 0) return ['Погоджено ' + t.approved + ' із ' + t.assigned, 'in_progress'];
    return ['Не подано', 'none'];
  }

  function buildMeasure(measure) {
    const details = node('details', 'mgr-measure');
    const header = node('summary');
    const title = node('span', 'mgr-title', measure.description);
    const prefix = measure.sequence_number !== null && measure.sequence_number !== undefined ? measure.sequence_number + '. ' : '';
    title.prepend(document.createTextNode(prefix));
    const [label, current] = status(measure);
    const badge = node('span', 'mgr-status', label);
    badge.dataset.state = current;
    add(header, title, node('span', 'mgr-meta', measure.deadline_on ? humanDate(measure.deadline_on) : (measure.deadline_description || '—')), badge);
    const body = node('div', 'mgr-measure-body');
    // Details contain only the department-scoped progress; heading has deadline and status.
    const progressSection = node('section', 'mgr-measure-progress');
    progressSection.setAttribute('aria-label', 'Прогрес виконання заходу за підрозділами');
    progressSection.appendChild(node('h4', '', 'Прогрес за підрозділами · ' + Api.periodLabel($('mgr-period').value)));
    const deptList = node('div', 'mgr-measure-dept-grid');
    deptList.dataset.mgrMeasureProgress = measure.measure_id;
    measureDepartmentProgress(measure, deptList);
    progressSection.appendChild(deptList);
    body.appendChild(progressSection);
    add(details, header, body);
    return details;
  }

  function drawTree() {
    const host = clear($('mgr-program-tree'));
    const search = $('mgr-program-search').value.trim().toLocaleLowerCase('uk');
    const only = $('mgr-program').value;
    const visiblePrograms = state.programs.filter(program => {
      if (only && program.id !== only) return false;
      const matchesProgram = matches(search, program.id, program.title);
      const programMeasures = state.measures.filter(m => m.program_id === program.id);
      return matchesProgram || programMeasures.some(m => matches(search, m.measure_id, m.description, m.section_title, m.responsible_department_name));
    });
    info('mgr-program-count', 'Програм: ' + visiblePrograms.length);
    if (!visiblePrograms.length) return empty(host, 'Програм за вибраними умовами не знайдено.');

    visiblePrograms.forEach((program, i) => {
      const matchesProgram = matches(search, program.id, program.title);
      let measures = state.measures.filter(m => m.program_id === program.id);
      if (search && !matchesProgram) measures = measures.filter(m =>
        matches(search, m.measure_id, m.description, m.section_title, m.responsible_department_name));
      const total = measures.length;
      const scoped = measures.filter(m => m.in_scope !== false);
      const count = scoped.filter(completeInScope).length;
      const item = node('details', 'mgr-program');
      // Native details/summary keep program → section → measure navigable without edit actions.
      if (i === 0 || search) item.open = true;
      const header = node('summary');
      const title = node('span', 'mgr-title');
      add(title, node('span', 'mgr-code', program.id), document.createTextNode(program.title));
      add(header, title,
        node('span', 'mgr-meta', humanDate(program.start_date) + ' – ' + humanDate(program.end_date)),
        node('span', 'mgr-count', measuresWord(total)));
      const body = node('div', 'mgr-program-body');
      add(body, node('div', 'mgr-program-meta',
        'У вашій сфері відповідальності: ' + measuresWord(scoped.length) +
        ' · Повністю погоджено: ' + count));
      const dispatch = (program.dispatched_to || []).map(d => d.department_name).filter(Boolean);
      if (dispatch.length) add(body, node('div', 'mgr-program-meta', 'Направлено: ' + dispatch.join(', ')));
      if (!measures.length) add(body, node('p', 'mgr-muted', 'Доступних заходів немає.'));
      const sections = new Map();
      measures.forEach(m => {
        const key = m.section_id || 'unknown';
        if (!sections.has(key)) sections.set(key, {number: m.section_number, title: m.section_title || 'Розділ', rows: []});
        sections.get(key).rows.push(m);
      });
      [...sections.values()].sort((a, b) => (a.number ?? 999) - (b.number ?? 999)).forEach((section, n) => {
        const group = node('details', 'mgr-section-tree');
        if (n === 0 || search) group.open = true;
        const heading = node('summary');
        add(heading, node('span', 'mgr-title', (section.number ? section.number + '. ' : '') + section.title),
          node('span', 'mgr-count', section.rows.length + ' заходів'));
        const inner = node('div', 'mgr-section-body');
        section.rows.sort((a,b) => (a.sequence_number ?? 9999) - (b.sequence_number ?? 9999))
          .forEach(m => inner.appendChild(buildMeasure(m)));
        add(group, heading, inner); body.appendChild(group);
      });
      add(item, header, body); host.appendChild(item);
    });
  }

  function recCard(rec, showFlag) {
    const card = node('article', 'mgr-card');
    const level = node('span', 'mgr-tag', LEVEL[rec.priority] || rec.priority || 'Інформація');
    level.dataset.priority = rec.priority || '';
    add(card, level, node('h3', '', (showFlag ? rec.code + ' · ' : '') + rec.title),
      node('p', 'mgr-muted', 'Програма ' + rec.program_id + ' · ' + (rec.object_type || 'об’єкт') + ' ' + (rec.object_id || '')),
      node('p', '', rec.reason), node('p', '', 'Рекомендація: ' + rec.suggestion));
    return card;
  }
  function renderRecommendations() {
    const host = clear($('mgr-recommendations'));
    const search = $('mgr-rec-search').value.trim().toLocaleLowerCase('uk');
    const priority = $('mgr-rec-priority').value;
    const rows = state.recs.filter(r => (!priority || r.priority === priority) &&
      matches(search, r.title, r.reason, r.suggestion, r.code, r.object_id, r.program_id));
    if (!rows.length) return empty(host, 'Рекомендацій за вибраними умовами немає.');
    rows.forEach(r => host.appendChild(recCard(r, false)));
  }
  function renderFlags() {
    const flags = state.recs.filter(r => r.source === 'risk_flag' || /^RF\d/i.test(r.code || ''));
    info('mgr-flags-count', flags.length ? '(' + flags.length + ')' : '');
    const host = clear($('mgr-flags'));
    if (!flags.length) return empty(host, 'Сигналів Risk Flags за вибраний період немає.');
    flags.forEach(r => host.appendChild(recCard(r, true)));
  }
  function renderRisks() {
    const host = clear($('mgr-risks'));
    const search = $('mgr-risk-search').value.trim().toLocaleLowerCase('uk');
    const rows = state.risks.filter(r => matches(search, r.risk_id, r.title, r.program_id, r.indicator_name));
    if (!rows.length) return empty(host, 'Ризиків за вибраними умовами немає.');
    rows.forEach(r => {
      const card = node('article', 'mgr-card');
      const level = node('span', 'mgr-tag', LEVEL[r.level] || r.level);
      level.dataset.priority = r.level || '';
      add(card, level, node('h3', '', r.risk_id + ' · ' + r.title),
        node('p', 'mgr-muted', 'Програма ' + r.program_id + ' · ' + (r.indicator_name || 'Індикатор')),
        node('p', '', 'Базове: ' + textValue(r.baseline) + ' · Ціль: ' + textValue(r.target) + ' · Факт: ' + textValue(r.actual)),
        node('p', '', 'Динаміка: ' + (TREND[r.trend] || 'Немає даних')));
      host.appendChild(card);
    });
  }
  function render() {
    kpis(); progress(); drawTree(); renderRecommendations(); renderFlags(); renderRisks();
    info('mgr-rec-count', state.recs.length ? '(' + state.recs.length + ')' : '');
  }
  async function loadDepartmentProgress() {
    const period = $('mgr-period').value;
    if (!period) return;
    // Department tab always summarises all programmes in the KER's server-authorized branch.
    // The programme selector filters only the programme tree, not this management summary.
    const url = '/api/management/department-progress?period=' + encodeURIComponent(period);
    const request = ++departmentProgressRequest;
    state.departmentProgress = null;
    progress();
    updateMeasureProgress();
    try {
      const result = await Api.get(url);
      if (request !== departmentProgressRequest) return;
      state.departmentProgress = result;
      progress();
      drawTree();
      kpis();
    } catch (error) {
      if (request !== departmentProgressRequest) return;
      state.departmentProgress = null;
      const text = 'Не вдалося завантажити прогрес: ' + (error.message || 'помилка сервера');
      empty($('mgr-department-progress'), text);
      app.querySelectorAll('[data-mgr-measure-progress]').forEach(host => empty(host, text));
      kpis();
    }
  }

  async function load() {
    const period = guardReportingPeriod();
    if (!period) return;
    message('');
    $('mgr-refresh').disabled = true;
    const qs = '?period=' + encodeURIComponent(period);
    try {
      const [dashboard, programs, measures, recommendations, risks] = await Promise.all([
        Api.get('/api/management/dashboard' + qs),
        Api.get('/api/management/programs' + qs),
        Api.get('/api/management/measures' + qs),
        Api.get('/api/management/recommendations' + qs + '&limit=500'),
        Api.get('/api/management/risks' + qs)
      ]);
      state.dashboard = dashboard;
      state.programs = programs || [];
      state.measures = measures || [];
      state.recs = recommendations.recommendations || [];
      state.risks = risks || [];
      // This filter only changes the view; backend decides the user's scope.
      const select = $('mgr-program'), current = select.value;
      clear(select);
      add(select, new Option('Усі програми', ''));
      state.programs.forEach(p => add(select, new Option(p.title || p.id, p.id)));
      select.value = state.programs.some(p => p.id === current) ? current : '';
      render();
      await loadDepartmentProgress();
    } catch (error) {
      message('Не вдалося отримати дані керівника: ' + (error.message || 'помилка сервера'));
      if (window.Api?.showError) Api.showError(error);
    } finally {
      $('mgr-refresh').disabled = false;
    }
  }
  async function init() {
    if (!window.Api || !await Api.requireRole('KER')) return;
    app.querySelectorAll('[data-mgr-tab]').forEach(btn => btn.addEventListener('click', () => setTab(btn.dataset.mgrTab)));
    $('mgr-refresh').addEventListener('click', load);
    $('mgr-program-search').addEventListener('input', drawTree);
    $('mgr-program').addEventListener('change', drawTree);
    $('mgr-department-search').addEventListener('input', progress);
    $('mgr-rec-search').addEventListener('input', renderRecommendations);
    $('mgr-rec-priority').addEventListener('change', renderRecommendations);
    $('mgr-risk-search').addEventListener('input', renderRisks);
    $('mgr-period').addEventListener('change', load);
    try {
      const period = Api.currentPeriod();
      const programs = await Api.get('/api/management/programs?period=' + encodeURIComponent(period));
      const now = new Date().getFullYear();
      Api.fillPeriods($('mgr-period'), programs.length ? programs : [{start_date:(now-2)+'-01-01',end_date:(now+1)+'-12-31'}]);
      guardReportingPeriod();
      await load();
    } catch(error) {
      message('Не вдалося завантажити кабінет: ' + (error.message || 'помилка сервера'));
    }
  }
  init();
})();
