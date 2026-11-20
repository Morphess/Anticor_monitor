import type { Page, APIRequestContext } from '@playwright/test';
import { test, expect, login, PASSWORD, PERIOD, monitorContext } from './fixtures';

test('incorrect credentials are rejected visibly', async ({ page }) => {
  await page.goto('/login');
  await page.getByLabel('Логін', { exact: true }).fill('pw_admin');
  await page.getByLabel('Пароль', { exact: true }).fill('incorrect-password');
  const response = page.waitForResponse(r => r.url().endsWith('/api/auth/token'));
  await page.getByRole('button', { name: 'Увійти', exact: true }).click();
  expect((await response).status()).toBe(401);
  await expect(page.locator('#login-error')).toBeVisible();
  await expect(page).toHaveURL(/\/login$/);
});

test('administrator can load users and departments', async ({ page }) => {
  await login(page, 'pw_admin', '/admin');
  await expect(page.getByText('pw_executor', { exact: true })).toBeVisible();
  await page.getByRole('tab', { name: 'Підрозділи', exact: true }).click();
  await expect(page.getByText('Synthetic PW-TEAM', { exact: true })).toBeVisible();
});

test('main coordinator can see own program and planned measure', async ({ page }) => {
  await login(page, 'pw_main', '/main-coordinator');
  await expect(page.getByText('Playwright synthetic program', { exact: true })).toBeVisible();
  await expect(page.locator('#mc-count-measures')).toHaveText('1');
});

test('coordinator sees only the dispatched workflow', async ({ page }) => {
  await login(page, 'pw_coord', '/coordinator');
  await expect(page.getByRole('button', { name: /PW-PROGRAM Playwright synthetic program/ })).toBeVisible();
  await expect(page.locator('#coord-total')).toHaveText('1');
});

test('executor submits a pinned order, coordinator views and approves it', async ({ page, browser, request }) => {
  await login(page, 'pw_executor', '/executor');
  await expect(page.locator('#executor-total')).toHaveText('1');
  await page.getByLabel('Звітний період', { exact: true }).selectOption(PERIOD);
  await page.getByRole('button', { name: 'Підтвердити виконання', exact: true }).click();
  await page.getByRole('dialog').getByRole('textbox').fill('PW-ORDER-1');
  const submitted = page.waitForResponse(r => r.url().endsWith('/api/executions/submit') && r.request().method() === 'POST');
  await page.getByRole('dialog').getByRole('button', { name: 'Підтвердити виконання', exact: true }).click();
  const response = await submitted;
  expect(response.status()).toBe(201);
  expect(response.request().postDataJSON()).toEqual({ measure_id: 'PW000001', period: PERIOD, order_number: 'PW-ORDER-1' });
  const execution = await response.json();
  expect(execution.status).toBe('pending');
  expect(execution.order_version_id).toBeGreaterThan(0);
  expect(execution.submitted_sha256).toMatch(/^[0-9a-f]{64}$/);
  await expect(page.locator('#executor-review')).toHaveText('1');

  // Real JWT and real API: the executor cannot approve, no dependency overrides.
  const tokenResponse = await request.post('/api/auth/token', { form: { username: 'pw_executor', password: PASSWORD } });
  expect(tokenResponse.status()).toBe(200);
  const { access_token } = await tokenResponse.json();
  const forbidden = await request.post(`/api/executions/${execution.id}/approve`, { headers: { Authorization: `Bearer ${access_token}` }, data: {} });
  expect(forbidden.status()).toBe(403);
  const forbiddenAnalysis = await request.post(`/api/executions/${execution.id}/analyze`, { headers: { Authorization: `Bearer ${access_token}` } });
  expect(forbiddenAnalysis.status()).toBe(403);
  const forbiddenSaved = await request.get(`/api/executions/${execution.id}/analysis`, { headers: { Authorization: `Bearer ${access_token}` } });
  expect(forbiddenSaved.status()).toBe(403);

  const coordinatorContext = await browser.newContext({ baseURL: 'http://api:8000', timezoneId: 'UTC' });
  try {
    const pageErrors = monitorContext(coordinatorContext);
    const coord = await coordinatorContext.newPage();
    await login(coord, 'pw_coord', '/coordinator');
    await coord.locator('#period').selectOption(PERIOD);
    await expect(coord.locator('#coord-review-count')).toHaveText('1');
    await coord.getByRole('button', { name: /Playwright synthetic program/ }).click();
    await coord.getByRole('button', { name: /Synthetic training/ }).click();
    await coord.getByRole('button', { name: /Conduct one synthetic integrity training/ }).click();
    await expect(coord.getByRole('button', { name: /^(Проаналізувати наказ|Повторити аналіз)$/ })).toBeVisible();
    const documentResponse = coord.waitForResponse(r => new URL(r.url()).pathname === `/api/executions/${execution.id}/document`);
    const popup = coord.waitForEvent('popup');
    await coord.getByRole('button', { name: 'Переглянути наказ', exact: true }).click();
    const pdf = await documentResponse;
    expect(pdf.status()).toBe(200);
    expect(pdf.headers()['content-type']).toContain('application/pdf');
    expect((await pdf.body()).subarray(0, 5).toString()).toBe('%PDF-');
    const documentPage = await popup;
    await expect(documentPage).toHaveURL(/^blob:/);
    await documentPage.close();
    await coord.getByRole('button', { name: 'Погодити', exact: true }).click();
    const approved = coord.waitForResponse(r => r.url().endsWith(`/api/executions/${execution.id}/approve`));
    await coord.locator('#coord-review-submit').click();
    expect((await approved).status()).toBe(200);
    await expect(coord.locator('#coord-approved')).toHaveText('1');
    expect(pageErrors).toEqual([]);
  } finally {
    await coordinatorContext.close();
  }
  await page.reload();
  await expect(page.locator('#executor-approved')).toHaveText('1');
  await expect(page.getByRole('button', { name: 'Підтвердити виконання', exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Уточнити виконання', exact: true })).toHaveCount(0);
});

async function openAnalysisCard(page: Page, request: APIRequestContext) {
  const token = await request.post('/api/auth/token', { form: { username: 'pw_executor', password: PASSWORD } });
  const { access_token } = await token.json();
  const headers = { Authorization: `Bearer ${access_token}` };
  const rows = await request.get(`/api/executions/?period=${PERIOD}`, { headers });
  expect(rows.status()).toBe(200);
  if (!(await rows.json()).some((row: { measure_id: string }) => row.measure_id === 'PW000001')) {
    const submitted = await request.post('/api/executions/submit', { headers, data: {
      measure_id: 'PW000001', period: PERIOD, order_number: 'PW-ORDER-1',
    } });
    expect(submitted.status()).toBe(201);
  }
  await page.clock.install();
  await login(page, 'pw_coord', '/coordinator');
  await page.locator('#period').selectOption(PERIOD);
  return expandAnalysisCard(page);
}

async function expandAnalysisCard(page: Page) {
  await expect(page.locator('#coord-total')).toHaveText('1');
  await page.getByRole('button', { name: /Playwright synthetic program/ }).click();
  await page.getByRole('button', { name: /Synthetic training/ }).click();
  await page.getByRole('button', { name: /Conduct one synthetic integrity training/ }).click();
  const button = page.getByRole('button', { name: /^(Проаналізувати наказ|Повторити аналіз)$/ });
  const result = page.locator('.analysis-result');
  return { button, result };
}

test('analysis survives polling during the request and after completion', async ({ page, request }) => {
  expect((await request.post('http://model-stub:11434/hold')).ok()).toBeTruthy();
  const { button, result } = await openAnalysisCard(page, request);
  const response = page.waitForResponse(r => new URL(r.url()).pathname.endsWith('/analyze'));
  try {
    await button.click();
    await expect.poll(async () => (await (await request.get('http://model-stub:11434/state')).json()).started).toBe(true);
    await expect(button).toBeDisabled();
    await expect(result).toContainText('Порівнюємо наказ');
    const poll = page.waitForResponse(r => r.request().method() === 'GET' && new URL(r.url()).pathname === '/api/executions/');
    await page.clock.fastForward(46000);
    await poll;
    // The active request remains disabled and visible in the recreated card.
    await expect(button).toBeDisabled();
    await expect(result).toContainText('Порівнюємо наказ');
    expect((await request.post('http://model-stub:11434/release')).ok()).toBeTruthy();
    expect((await response).status()).toBe(200);
    await expect(result).toContainText('SYNTHETIC ANALYSIS: training matches the measure');
    await expect(button).toBeEnabled();
    const afterCompletionPoll = page.waitForResponse(r => r.request().method() === 'GET' && new URL(r.url()).pathname === '/api/executions/');
    await page.clock.fastForward(46000);
    await afterCompletionPoll;
    await expect(result).toContainText('SYNTHETIC ANALYSIS: training matches the measure');
    await page.locator('#search').fill('Conduct');
    await expect(result).toContainText('SYNTHETIC ANALYSIS: training matches the measure');
  } finally {
    await request.post('http://model-stub:11434/release');
  }
});

// This negative case asserts the one expected HTTP failure explicitly; every
// other API failure and browser exception still fails the test.
const errorTest = test.extend({
  browserErrors: [async ({ context }, use) => {
    const errors = monitorContext(context);
    await use();
    expect(errors).toHaveLength(1);
    expect(errors[0]).toMatch(/^HTTP 502: POST \/api\/executions\/\d+\/analyze$/);
  }, { auto: true }],
});

errorTest('analysis error remains visible after polling', async ({ page, request }) => {
  expect((await request.post('http://model-stub:11434/fail')).ok()).toBeTruthy();
  const { button, result } = await openAnalysisCard(page, request);
  const response = page.waitForResponse(r => new URL(r.url()).pathname.endsWith('/analyze'));
  await button.click();
  expect((await response).status()).toBe(502);
  await expect(result).toContainText('Помилка аналізу:');
  await expect(button).toBeEnabled();
  const poll = page.waitForResponse(r => r.request().method() === 'GET' && new URL(r.url()).pathname === '/api/executions/');
  await page.clock.fastForward(46000);
  await poll;
  await expect(result).toContainText('Помилка аналізу:');
});


test('analysis warns when the model reaches its output limit', async ({ page, request }) => {
  expect((await request.post('http://model-stub:11434/limit')).ok()).toBeTruthy();
  const { button, result } = await openAnalysisCard(page, request);
  const response = page.waitForResponse(r => new URL(r.url()).pathname.endsWith('/analyze'));
  await button.click();
  const reply = await response;
  expect(reply.status()).toBe(200);
  expect((await reply.json()).output_truncated).toBe(true);
  await expect(result).toContainText('Досягнуто ліміту відповіді моделі');
  await expect(result).toContainText('Висновок може бути неповним');
});


test('saved analysis survives reload without generating a new report', async ({ page, request }) => {
  expect((await request.post('http://model-stub:11434/release')).ok()).toBeTruthy();
  const { button, result } = await openAnalysisCard(page, request);
  await expect(button).toBeEnabled();
  if (await button.textContent() === 'Проаналізувати наказ') {
    const response = page.waitForResponse(r => new URL(r.url()).pathname.endsWith('/analyze'));
    await button.click();
    expect((await response).status()).toBe(200);
  }
  await expect(result).toContainText('SYNTHETIC ANALYSIS');
  await expect(result).toContainText('Збережено:');
  const before = (await (await request.get('http://model-stub:11434/state')).json()).calls;
  await page.reload();
  await page.locator('#period').selectOption(PERIOD);
  const savedResponse = page.waitForResponse(r => new URL(r.url()).pathname.endsWith('/analysis'));
  const reloaded = await expandAnalysisCard(page);
  const saved = await savedResponse;
  expect(saved.status()).toBe(200);
  const record = await saved.json();
  expect(record.analysis_id).toBeGreaterThan(0);
  await expect(reloaded.result).toContainText('SYNTHETIC ANALYSIS');
  await expect(reloaded.button).toHaveText('Повторити аналіз');
  expect((await (await request.get('http://model-stub:11434/state')).json()).calls).toBe(before);

  const token = await request.post('/api/auth/token', { form: { username: 'pw_coord', password: PASSWORD } });
  const { access_token } = await token.json();
  const reused = await request.post(`/api/executions/${record.execution_id}/analyze`, {
    headers: { Authorization: `Bearer ${access_token}` },
  });
  expect(reused.status()).toBe(200);
  expect((await reused.json()).analysis_id).toBe(record.analysis_id);
  const outsideToken = await request.post('/api/auth/token', { form: { username: 'pw_unrelated_coord', password: PASSWORD } });
  const outsider = (await outsideToken.json()).access_token;
  const denied = await request.get(`/api/executions/${record.execution_id}/analysis`, {
    headers: { Authorization: `Bearer ${outsider}` },
  });
  expect(denied.status()).toBe(403);
  expect((await (await request.get('http://model-stub:11434/state')).json()).calls).toBe(before);
});
