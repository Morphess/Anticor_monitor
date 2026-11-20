/* Risk reassessment UI: backend/app/api/risk_assessments.py contract.
   Does not modify Risk.score until backend approves an assessment. */
(function(root){
  'use strict';

  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const okScore = value => Number.isInteger(Number(value)) && Number(value) >= 1 && Number(value) <= 4 && value !== null && value !== '' && value !== undefined;
  const fmtDate = s => {
    if (!s) return '—';
    const d = new Date(s);
    return Number.isNaN(d.valueOf()) ? String(s) : d.toLocaleString('uk-UA');
  };
  const arrayOf = x => Array.isArray(x) ? x : (Array.isArray(x?.items) ? x.items : []);
  const score = a => okScore(a?.probability_score) && okScore(a?.impact_score)
    ? Number(a.probability_score) * Number(a.impact_score)
    : null;
  const dateOf = a => a?.assessed_on || a?.created_at || a?.decided_at || a?.date || '';
  const localDate = () => { const d = new Date(); const z = n => String(n).padStart(2, '0'); return d.getFullYear() + '-' + z(d.getMonth()+1) + '-' + z(d.getDate()); }; 
  const describeError = err => String(err?.message || err || 'Помилка сервера');

  function label(status){
    return ({draft:'Чернетка', pending:'На розгляді', approved:'Погоджено', rejected:'Відхилено', baseline:'Початкова оцінка'})[String(status || '').toLowerCase()] || status || '—';
  }

  function statusClass(status){
    const key = String(status || '').toLowerCase();
    return ['baseline','approved','rejected','draft','pending'].includes(key) ? key : 'draft';
  }

  function trendText(delta){
    if (!Number.isFinite(delta) || delta === 0) return 'Без змін';
    return delta < 0 ? 'Зменшення на ' + Math.abs(delta) : 'Збільшення на ' + delta;
  }

  function approvedItem(history){
    return history
      .filter(a => ['approved', 'baseline'].includes(String(a.status || '').toLowerCase()) && score(a) !== null)
      .sort((a,b) => (Date.parse(dateOf(b) || '') - Date.parse(dateOf(a) || '')) || (Number(b.id || 0) - Number(a.id || 0)))[0] || null;
  }

  function latestDraft(history){
    return history
      .filter(a => String(a.status || '').toLowerCase() === 'draft' && score(a) !== null)
      .sort((a,b) => (Date.parse(dateOf(b) || '') - Date.parse(dateOf(a) || '')) || (Number(b.id || 0) - Number(a.id || 0)))[0] || null;
  }

  function reasonOf(entry){
    return entry?.reason || entry?.justification || entry?.comment || '—';
  }

  function historyCard(entry){
    const total = entry?.score ?? score(entry);
    const status = String(entry?.status || '').toLowerCase();
    const actions = status === 'draft' && Number.isInteger(Number(entry?.id))
      ? `<div class="rra-row-actions">
          <button type="button" class="rra-btn rra-btn-primary" data-approve="${Number(entry.id)}">Погодити</button>
          <button type="button" class="rra-btn rra-btn-secondary" data-reject="${Number(entry.id)}">Відхилити</button>
        </div>`
      : '';
    return `<article class="rra-history-item">
      <div class="rra-history-top">
        <div class="rra-history-main">
          <div class="rra-history-meta">
            <span class="rra-badge ${statusClass(status)}">${esc(label(status))}</span>
            <span class="rra-history-date">${esc(fmtDate(dateOf(entry)))}</span>
          </div>
          <div class="rra-history-score">
            <strong>${esc(total ?? '—')}</strong>
            <span class="rra-history-values">${esc(entry?.probability_score ?? '—')} × ${esc(entry?.impact_score ?? '—')}</span>
          </div>
        </div>
        ${actions}
      </div>
      <p class="rra-history-reason">${esc(reasonOf(entry))}</p>${entry?.measurement_on ? `<p class="rra-history-measurement">Показник станом на ${esc(entry.measurement_on)}${entry.measurement_value != null ? ` · ${esc(entry.measurement_value)}` : ''}</p>` : ''}
    </article>`;
  }

  async function mountRiskReassessment(opts){
    const { container, riskId, api, onSaved } = opts || {};
    const host = typeof container === 'string' ? document.querySelector(container) : container;
    if (!host || !api || !riskId) throw new Error('Не передано контейнер, ризик або API');

    let busy = false;
    let risk = null;
    let history = [];
    let trend = null;

    host.innerHTML = `<section class="rra"><div class="rra-loading" role="status">Завантаження ризику та історії…</div></section>`;

    try {
      risk = await api.getRisk(riskId);
      history = arrayOf(await api.getHistory(riskId));
      try { trend = api.getTrend ? await api.getTrend(riskId) : null; } catch (_) { trend = null; }
    } catch (err) {
      host.innerHTML = `<section class="rra"><div class="rra-error-box" role="alert"><p class="rra-error">${esc(describeError(err))}</p><p class="rra-muted">Перевірте підключення роутера <code>/api/risk-assessments</code> у FastAPI та доступ до цього ризику.</p></div></section>`;
      return;
    }

    async function reload(){
      const [fresh, entries] = await Promise.all([
        api.getRisk(riskId),
        api.getHistory(riskId),
      ]);
      risk = fresh;
      history = arrayOf(entries);
      try { trend = api.getTrend ? await api.getTrend(riskId) : null; } catch (_) { trend = null; }
      render();
      if (typeof onSaved === 'function') await onSaved({ risk, history, trend });
    }

    function render(){
      const current = approvedItem(history) || risk;
      const draft = latestDraft(history);
      const currentProbability = Number(current?.probability_score);
      const currentImpact = Number(current?.impact_score);
      const currentScore = score(current);
      const initialProbability = Number((draft || current)?.probability_score || currentProbability || 1);
      const initialImpact = Number((draft || current)?.impact_score || currentImpact || 1);
      const draftScore = draft ? score(draft) : currentScore;
      const delta = Number.isFinite(draftScore) && Number.isFinite(currentScore) ? draftScore - currentScore : 0;
      const historyRows = history.slice().sort((a,b) => (Date.parse(dateOf(b)) || 0) - (Date.parse(dateOf(a)) || 0));
      const measurementDate = trend?.latest_measurement_on || draft?.measurement_on || '';
      const selectable = n => [1,2,3,4].map(v => `<option value="${v}" ${Number(n) === v ? 'selected' : ''}>${v}</option>`).join('');

      host.innerHTML = `
        <section class="rra" aria-label="Повторне оцінювання ризику">
          <div class="rra-stack">
            <header class="rra-hero">
              <div class="rra-hero-copy">
                <div class="rra-kicker">
                  <span class="rra-kicker-pill">Повторне оцінювання</span>
                </div>
                <h3>Повторне оцінювання ризику</h3>
                <p class="rra-lead">Оцініть оновлену ймовірність та наслідки, додайте коротке обґрунтування і, за потреби, погодьте чернетку через історію оцінювань.</p>
              </div>
              <span class="rra-code">${esc(risk?.id || riskId)}</span>
            </header>

            <section class="rra-grid rra-summary" aria-label="Порівняння оцінок">
              <article class="rra-card">
                <div class="rra-card-head">
                  <span class="rra-card-title">Чинна оцінка</span>
                  <span class="rra-badge ${history.length ? statusClass((approvedItem(history) || {}).status || 'baseline') : 'baseline'}">${esc(history.length ? label((approvedItem(history) || {}).status || 'baseline') : 'Поточна')}</span>
                </div>
                <div class="rra-score">${esc(currentScore ?? '—')}</div>
                <div class="rra-formula">${esc(currentProbability || '—')} × ${esc(currentImpact || '—')}</div>
                <div class="rra-meta">
                  <span class="rra-meta-item">Рівень: ${esc(risk?.level || '—')}</span>
                  ${trend?.trend_label ? `<span class="rra-meta-item">Динаміка: ${esc(trend.trend_label)}</span>` : ''}
                </div>
              </article>

              <article class="rra-card">
                <div class="rra-card-head">
                  <span class="rra-card-title">Проєкт нової оцінки</span>
                  <span class="rra-trend ${delta < 0 ? 'down' : delta > 0 ? 'up' : 'same'}" data-difference>${esc(trendText(delta))}</span>
                </div>
                <div class="rra-score" data-new-score>${esc(draftScore ?? currentScore ?? '—')}</div>
                <div class="rra-formula" data-new-formula>${esc((draft || current)?.probability_score ?? currentProbability ?? '—')} × ${esc((draft || current)?.impact_score ?? currentImpact ?? '—')}</div>
                <div class="rra-meta">
                  ${draft ? `<span class="rra-meta-item">Є незавершена чернетка</span>` : `<span class="rra-meta-item">Чернетку ще не створено</span>`}
                </div>
              </article>
            </section>

            <div class="rra-divider"></div>

            <section class="rra-form-wrap" aria-label="Форма повторного оцінювання">
              <div class="rra-section-head">
                <div>
                  <h4 class="rra-section-title">Створення чернетки оцінки</h4>
                  <p class="rra-section-subtitle">Заповни нові значення та коротко поясни, на підставі чого змінюється оцінка ризику.</p>
                </div>
              </div>

              <form class="rra-form" novalidate>
                <div class="rra-grid rra-fields">
                  <label class="rra-field">
                    <span class="rra-label">Імовірність (1–4)</span>
                    <select name="probability_score" class="rra-control">${selectable(initialProbability)}</select>
                    <span class="rra-help">Оціни, наскільки ймовірним залишається ризик після виконання заходів.</span>
                  </label>
                  <label class="rra-field">
                    <span class="rra-label">Наслідки (1–4)</span>
                    <select name="impact_score" class="rra-control">${selectable(initialImpact)}</select>
                    <span class="rra-help">Оціни масштаб можливих наслідків, якщо ризик реалізується.</span>
                  </label>
                </div>
                <div class="rra-grid rra-fields rra-date-fields">
                  <label class="rra-field">
                    <span class="rra-label">Дата оцінювання</span>
                    <input name="assessed_on" type="date" class="rra-control" value="${esc(localDate())}" required>
                    <span class="rra-help">Дата, на яку визначається новий рівень ризику.</span>
                  </label>
                  <label class="rra-field">
                    <span class="rra-label">Дата вимірювання індикатора</span>
                    <input name="measurement_on" type="date" class="rra-control" value="${esc(measurementDate)}" required>
                    <span class="rra-help">Дата фактично зареєстрованого показника. ${measurementDate ? 'Останній запис: ' + esc(measurementDate) : 'Показник ще не зареєстрований — додайте його нижче.'}</span>
                  </label>
                </div>
                <label class="rra-field">
                  <span class="rra-label">Обґрунтування оцінки</span>
                  <textarea name="justification" class="rra-control" rows="5" minlength="30" maxlength="10000" required placeholder="Фактичні результати заходів, підтвердні документи, зміни показника та підстави перегляду оцінки.">${esc(draft ? (draft.justification || '') : '')}</textarea>
                  <span class="rra-help">Обов’язково: від 30 до 10 000 символів. Конкретні факти та підтвердження.</span>
                </label>
                <div class="rra-actions">
                  <div class="rra-actions-left">
                    <button type="submit" class="rra-btn rra-btn-primary">Створити чернетку оцінки</button>
                    ${!history.length ? `<button type="button" class="rra-btn rra-btn-secondary" data-baseline>Зафіксувати початкову оцінку</button>` : ''}
                  </div>
                  <div class="rra-actions-right">
                    <span class="rra-status" role="status" aria-live="polite"></span>
                  </div>
                </div>
              </form>
            </section>

            <div class="rra-divider"></div>

            <section class="rra-measurement" aria-label="Реєстрація показника ризику">
              <div class="rra-section-head"><div>
                <h4 class="rra-section-title">Вимірювання індикатора ризику</h4>
                <p class="rra-section-subtitle">Для переоцінки використовується фактичний показник. Якщо його ще немає, зареєструйте вимірювання.</p>
              </div></div>
              <details class="rra-measurement-details" ${!measurementDate ? 'open' : ''}>
                <summary>+ Додати фактичне значення індикатора</summary>
                <form class="rra-measurement-form" novalidate>
                  <p class="rra-help">${esc(risk?.indicator_name || 'Індикатор ризику')} · ${esc(risk?.indicator_unit || '')}</p>
                  <div class="rra-grid rra-fields">
                    <label class="rra-field"><span class="rra-label">Дата вимірювання</span><input type="date" name="measured_on" class="rra-control" value="${esc(localDate())}"></label>
                    <label class="rra-field"><span class="rra-label">Фактичне значення</span><input type="number" name="value" class="rra-control" step="0.001" placeholder="Наприклад, 12.500"></label>
                  </div>
                  <label class="rra-field"><span class="rra-label">Джерело даних</span><textarea name="source" class="rra-control" rows="2" maxlength="4000" placeholder="Звіт, перевірка, документ або інше підтвердження (мінімум 10 символів)"></textarea></label>
                  <div class="rra-actions"><button class="rra-btn rra-btn-secondary" type="submit">Зареєструвати вимірювання</button><span class="rra-measurement-status" role="status" aria-live="polite"></span></div>
                </form>
              </details>
            </section>

            <div class="rra-divider"></div>

            <section class="rra-history" aria-label="Історія оцінювань">
              <div class="rra-section-head">
                <div>
                  <h4 class="rra-section-title">Історія оцінювань</h4>
                  <p class="rra-section-subtitle">У цьому списку відображаються початкова оцінка, чернетки та вже погоджені рішення.</p>
                </div>
              </div>
              ${historyRows.length
                ? `<div class="rra-history-list">${historyRows.map(historyCard).join('')}</div>`
                : `<div class="rra-empty-state"><p>Історія оцінювань поки порожня. Якщо початкову оцінку ще не зафіксовано, зроби це кнопкою вище — після цього можна створювати наступні чернетки переоцінки.</p></div>`}
            </section>
          </div>
        </section>`;

      const form = host.querySelector('.rra-form');
      const status = host.querySelector('.rra-status');
      const submitButton = form.querySelector('button[type="submit"]');

      function setStatus(message, kind){
        status.textContent = message || '';
        status.className = 'rra-status' + (kind ? ' ' + kind : '');
      }

      function recalc(){
        const p = Number(form.elements.probability_score.value);
        const i = Number(form.elements.impact_score.value);
        const result = p * i;
        const diff = Number.isFinite(currentScore) ? result - currentScore : 0;
        host.querySelector('[data-new-score]').textContent = String(result);
        host.querySelector('[data-new-formula]').textContent = p + ' × ' + i;
        const badge = host.querySelector('[data-difference]');
        badge.textContent = trendText(diff);
        badge.className = 'rra-trend ' + (diff < 0 ? 'down' : diff > 0 ? 'up' : 'same');
      }

      function validateForm(){
        const p = Number(form.elements.probability_score.value);
        const i = Number(form.elements.impact_score.value);
        const justification = form.elements.justification.value.trim();
        const assessed_on = form.elements.assessed_on.value;
        const measurement_on = form.elements.measurement_on.value;
        if (!okScore(p) || !okScore(i)) {
          setStatus('Оберіть значення імовірності та наслідків від 1 до 4.', 'error');
          return null;
        }
        if (!/^\d{4}-\d{2}-\d{2}$/.test(assessed_on) || !/^\d{4}-\d{2}-\d{2}$/.test(measurement_on)) {
          setStatus('Вкажіть дату оцінювання та дату фактичного вимірювання індикатора.', 'error');
          return null;
        }
        if (measurement_on > assessed_on) {
          setStatus('Дата вимірювання не може бути пізніше дати оцінювання.', 'error');
          return null;
        }
        if (justification.length < 30 || justification.length > 10000) {
          setStatus('Обґрунтування повинно містити від 30 до 10 000 символів.', 'error');
          form.elements.justification.focus();
          return null;
        }
        setStatus('');
        return { assessed_on, measurement_on, probability_score: p, impact_score: i, justification };
      }

      form.addEventListener('input', () => {
        if (status.textContent) setStatus('');
      });
      form.addEventListener('change', recalc);
      recalc();

      form.addEventListener('submit', async ev => {
        ev.preventDefault();
        if (busy) return;
        const payload = validateForm();
        if (!payload) return;
        busy = true;
        submitButton.disabled = true;
        setStatus('Створення чернетки…');
        try {
          await api.createAssessment(riskId, payload);
          setStatus('Чернетку оцінки створено.', 'ok');
          await reload();
        } catch (err) {
          submitButton.disabled = false;
          setStatus('Не вдалося створити чернетку: ' + describeError(err), 'error');
        } finally {
          busy = false;
        }
      });

      host.querySelectorAll('[data-approve],[data-reject]').forEach(button => {
        button.addEventListener('click', async () => {
          if (busy) return;
          const approve = button.hasAttribute('data-approve');
          const id = button.getAttribute(approve ? 'data-approve' : 'data-reject');
          const promptText = approve
            ? 'Вкажіть підставу погодження оцінки:'
            : 'Вкажіть причину відхилення оцінки:';
          const reason = window.prompt(promptText);
          if (reason === null) return;
          if (!reason.trim()) {
            window.alert('Вкажіть обґрунтування рішення.');
            return;
          }
          busy = true;
          button.disabled = true;
          try {
            await (approve ? api.approve(riskId, id, reason.trim()) : api.reject(riskId, id, reason.trim()));
            await reload();
          } catch (err) {
            window.alert('Не вдалося виконати дію: ' + describeError(err));
            button.disabled = false;
          } finally {
            busy = false;
          }
        });
      });

      const measurementForm = host.querySelector('.rra-measurement-form');
      measurementForm?.addEventListener('submit', async ev => {
        ev.preventDefault();
        if (busy) return;
        const mf = measurementForm.elements;
        const measured_on = mf.measured_on.value;
        const valueString = mf.value.value.trim();
        const source = mf.source.value.trim();
        const measurementStatus = host.querySelector('.rra-measurement-status');
        const btn = measurementForm.querySelector('button[type="submit"]');
        if (!measured_on || valueString === '' || !Number.isFinite(Number(valueString)) || source.length < 10) {
          measurementStatus.textContent = 'Заповніть дату, число і джерело (мінімум 10 символів).';
          return;
        }
        if (!api.registerMeasurement) {
          measurementStatus.textContent = 'API для вимірювання не підключений.';
          return;
        }
        busy = true;
        btn.disabled = true;
        measurementStatus.textContent = 'Реєстрація вимірювання…';
        try {
          await api.registerMeasurement(riskId, { measured_on, value: valueString, source });
          await reload();
        } catch (err) {
          measurementStatus.textContent = 'Не вдалося зберегти вимірювання: ' + describeError(err);
          btn.disabled = false;
        } finally { busy = false; }
      });

      const baselineButton = host.querySelector('[data-baseline]');
      baselineButton?.addEventListener('click', async () => {
        if (busy) return;
        if (!window.confirm('Зафіксувати поточну оцінку як початкову в історії ризику?')) return;
        busy = true;
        baselineButton.disabled = true;
        setStatus('Створення початкової оцінки…');
        try {
          await api.baseline(riskId);
          setStatus('Початкову оцінку зафіксовано.', 'ok');
          await reload();
        } catch (err) {
          baselineButton.disabled = false;
          setStatus('Не вдалося створити початкову оцінку: ' + describeError(err), 'error');
        } finally {
          busy = false;
        }
      });
    }

    render();
    return {
      reload,
      destroy: () => { host.replaceChildren(); },
    };
  }

  root.mountRiskReassessment = mountRiskReassessment;
})(window);
