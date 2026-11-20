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
  await page.getByRole('button', { name: 'Внести виконання', exact: true }).click();
  await page.getByRole('dialog').getByRole('textbox').fill('PW-ORDER-1');
  const submitted = page.waitForResponse(r => r.url().endsWith('/api/executions/submit') && r.request().method() === 'POST');
  await page.getByRole('button', { name: 'Надіслати на перевірку', exact: true }).click();
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
  await expect(page.getByRole('button', { name: 'Внести виконання', exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Уточнити виконання', exact: true })).toHaveCount(0);
});
