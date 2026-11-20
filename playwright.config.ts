import { defineConfig, devices } from '@playwright/test';

// Deliberately do not accept an arbitrary URL or the Tailscale production host.
if (process.env.BORDERGROUP_E2E !== '1' || process.env.E2E_BASE_URL !== 'http://api:8000') {
  throw new Error('Run npm run test:e2e; only the isolated Compose API is allowed.');
}

export default defineConfig({
  testDir: './e2e/tests',
  outputDir: '/artifacts/test-results',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 30_000,
  globalTimeout: 5 * 60_000,
  expect: { timeout: 8_000 },
  forbidOnly: !!process.env.CI,
  reporter: [['list'], ['html', { open: 'never', outputFolder: '/artifacts/playwright-report' }]],
  use: {
    baseURL: 'http://api:8000',
    timezoneId: 'UTC',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'off',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'], channel: 'chromium' } }],
});
