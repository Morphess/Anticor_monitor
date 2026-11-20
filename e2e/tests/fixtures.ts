import { test as base, expect, Page, BrowserContext } from '@playwright/test';
export { expect };
export const PASSWORD = 'synthetic-playwright-only-2026';
export const PERIOD = `${new Date().getUTCFullYear()}-H${new Date().getUTCMonth() < 6 ? 1 : 2}`;

// These endpoints are required by the initial workflows. Optional modules are
// deliberately not classified as failures here; assertions still verify UI data.
const requiredAPI = /\/api\/(auth\/me|program-routing\/|measures\/|executions(?:\/|\?)|departments(?:\/|\?|$)|users(?:\/|\?|$))/;
export function monitorContext(context: BrowserContext) {
  const errors: string[] = [];
  context.on('page', page => {
    page.on('pageerror', error => errors.push(error.message));
    page.on('requestfailed', req => {
      if (requiredAPI.test(req.url()) && req.failure()?.errorText !== 'net::ERR_ABORTED') {
        errors.push(`Request failed: ${req.method()} ${new URL(req.url()).pathname}`);
      }
    });
    page.on('response', response => {
      const path = new URL(response.url()).pathname;
      if (requiredAPI.test(response.url()) && response.status() >= 400) {
        errors.push(`HTTP ${response.status()}: ${response.request().method()} ${path}`);
      }
      // With HTTPS termination this unnecessary redirect can downgrade to HTTP.
      if (path === '/api/departments/' && [307, 308].includes(response.status())) {
        errors.push('Unexpected departments collection redirect');
      }
    });
  });
  return errors;
}
export const test = base.extend<{ browserErrors: void }>({
  browserErrors: [async ({ context }, use) => {
    const errors = monitorContext(context);
    await use();
    expect(errors, 'No browser exceptions or failed mandatory API calls').toEqual([]);
  }, { auto: true }],
});

export async function login(page: Page, user: string, target: string) {
  await page.goto('/login');
  await page.getByLabel('Логін', { exact: true }).fill(user);
  await page.getByLabel('Пароль', { exact: true }).fill(PASSWORD);
  await page.getByRole('button', { name: 'Увійти', exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`${target}$`));
}
