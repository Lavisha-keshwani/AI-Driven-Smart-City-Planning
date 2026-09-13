/**
 * Browser end-to-end smoke test.
 *
 * Drives the real UI in Chrome against a running backend, and checks that every
 * page renders real data rather than merely mounting: the map draws actual grid
 * polygons, clicking a cell runs the full agent pipeline, the microplastic
 * screening agrees with the HMPD ground-truth label, and the building planner
 * produces recommendations from live NASA POWER data.
 *
 * Prerequisites — both servers running, and Chrome installed:
 *     backend:   uvicorn app.main:app --port 8000
 *     frontend:  npm run dev
 *
 * Run:
 *     npm run test:e2e
 *
 * Environment:
 *     UI_URL         frontend origin           (default http://localhost:5173)
 *     CHROME_PATH    Chrome executable         (default: the usual Windows path)
 *     SHOT_DIR       screenshot output folder  (default ./e2e/screenshots)
 *     HMPD_DIR       HMPD dataset root         (default: the repo's models/ copy)
 */

import { chromium } from 'playwright-core';
import { existsSync, mkdirSync, readdirSync, readFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO = resolve(HERE, '../..');

const UI = process.env.UI_URL || 'http://localhost:5173';
const SHOTS = process.env.SHOT_DIR || join(HERE, 'screenshots');
const CHROME =
  process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const HMPD =
  process.env.HMPD_DIR ||
  join(REPO, 'models/microplastic/Smart-city-microplastic/HMPD-Gen/HMPD-Gen');

mkdirSync(SHOTS, { recursive: true });

const results = [];
const consoleErrors = [];

function record(name, ok, detail = '') {
  results.push({ name, ok, detail });
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? `  — ${detail}` : ''}`);
}

function skip(name, why) {
  results.push({ name, ok: true, skipped: true, detail: why });
  console.log(`SKIP  ${name}  — ${why}`);
}

/** A real HMPD particle that has all three polarimetric channels, with its label. */
function findLabelledParticle() {
  const imageDir = join(HMPD, 'images');
  if (!existsSync(join(HMPD, 'gt.csv')) || !existsSync(imageDir)) return null;

  const available = new Set(readdirSync(imageDir));
  const rows = readFileSync(join(HMPD, 'gt.csv'), 'utf8').split('\n').slice(1);
  for (const row of rows) {
    const [id, cls] = row.trim().split(',');
    if (!id) continue;
    if (['R', 'A', 'P'].every((c) => available.has(`${id}_${c}.bmp`))) {
      return { id, label: cls, imageDir };
    }
  }
  return null;
}

async function main() {
  if (!existsSync(CHROME)) {
    console.error(`Chrome not found at ${CHROME}. Set CHROME_PATH.`);
    process.exit(2);
  }

  const browser = await chromium.launch({ executablePath: CHROME, headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });

  page.on('console', (msg) => {
    if (msg.type() === 'error') consoleErrors.push(msg.text());
  });
  page.on('pageerror', (err) => consoleErrors.push(`pageerror: ${err.message}`));

  try {
    // ── City Planner ───────────────────────────────────────────────────────
    await page.goto(UI, { waitUntil: 'networkidle' });
    await page.waitForTimeout(1500);

    record('app shell renders', (await page.locator('aside').count()) > 0);
    record(
      'backend status shows models loaded',
      await page
        .getByText(/models loaded/)
        .isVisible()
        .catch(() => false),
    );

    const title = await page.locator('h1').first().textContent();
    record('City Planner heading', title?.includes('City Planner'), title);

    await page.waitForSelector('.leaflet-container', { timeout: 30000 });
    await page.waitForFunction(
      () => document.querySelectorAll('.leaflet-overlay-pane path').length > 50,
      { timeout: 60000 },
    );
    const cellCount = await page.locator('.leaflet-overlay-pane path').count();
    record('map renders real grid cells', cellCount > 50, `${cellCount} polygons`);
    record('legend renders', (await page.getByText('Legend').count()) > 0);
    await page.screenshot({ path: join(SHOTS, '01-city-planner.png') });

    await page.getByRole('button', { name: /Where flooding is likely/ }).click();
    await page.waitForTimeout(1200);
    record(
      'layer switch to flood risk',
      (await page.locator('.leaflet-overlay-pane path').count()) > 50,
    );
    await page.screenshot({ path: join(SHOTS, '02-flood-layer.png') });

    // The city menu must paint above the map. Leaflet puts its panes at z-index
    // 400 and its controls at 1000, which previously painted over the dropdown.
    // Only a real browser can settle this, so it is checked here rather than in
    // the jsdom tests.
    await page.locator('button[aria-haspopup="listbox"]').click();
    await page.waitForTimeout(500);
    const menuStacking = await page.evaluate(() => {
      const menu = document.querySelector('[role="listbox"]')?.closest('div.absolute');
      const map = document.querySelector('.leaflet-container');
      if (!menu || !map) return { ok: false, why: 'menu or map not found' };

      const rect = menu.getBoundingClientRect();
      const mapRect = map.getBoundingClientRect();
      const covered = [];
      for (const fraction of [0.2, 0.5, 0.85]) {
        const x = rect.x + rect.width / 2;
        const y = rect.y + rect.height * fraction;
        if (y > mapRect.y && y < mapRect.bottom && x > mapRect.x && x < mapRect.right) {
          const onTop = document.elementFromPoint(x, y);
          if (onTop && onTop.closest('.leaflet-container')) covered.push(Math.round(y));
        }
      }
      return {
        ok: covered.length === 0 && rect.bottom <= window.innerHeight,
        coveredAt: covered,
        height: Math.round(rect.height),
        fitsOnScreen: rect.bottom <= window.innerHeight,
      };
    });
    record(
      'city menu renders above the map and fits on screen',
      menuStacking.ok,
      `height ${menuStacking.height}px, fits=${menuStacking.fitsOnScreen}` +
        (menuStacking.coveredAt?.length ? `, covered by map at y=${menuStacking.coveredAt}` : ''),
    );
    await page.keyboard.press('Escape');
    await page.waitForTimeout(300);

    // Click a cell -> the full five-agent pipeline.
    await page.locator('.leaflet-overlay-pane path').nth(20).click({ force: true });
    record(
      'cell selection starts the pipeline',
      await page
        .getByText(/Running the five agents|Overall recommendation/)
        .first()
        .isVisible({ timeout: 15000 })
        .catch(() => false),
    );

    await page.waitForSelector('text=Overall recommendation', { timeout: 240000 });
    const verdict = await page
      .locator('h3')
      .filter({ hasText: /Go ahead|Not recommended|Only with strong|Not enough/ })
      .first()
      .textContent();
    record('coordinator verdict rendered', Boolean(verdict), verdict?.trim());
    record('per-model cards rendered', (await page.getByText('What each model found').count()) > 0);
    record('agent reasoning rendered', (await page.getByText('Agent reasoning').count()) > 0);
    await page.screenshot({ path: join(SHOTS, '03-assessment.png'), fullPage: true });

    const shapToggle = page.getByRole('button', { name: /Why the model said this/ }).first();
    await shapToggle.click();
    await page.waitForTimeout(600);
    record(
      'SHAP attribution panel opens',
      (await page.getByText(/SHAP values for this single prediction/).count()) > 0,
    );

    const metricsToggle = page
      .getByRole('button', { name: /Model performance and limitations/ })
      .first();
    await metricsToggle.click();
    await page.waitForTimeout(800);
    record(
      'per-city performance table renders',
      (await page.getByText(/Performance by unseen city/).count()) > 0,
    );
    await page.screenshot({ path: join(SHOTS, '04-technical-details.png'), fullPage: true });

    // ── Water & Microplastics ──────────────────────────────────────────────
    await page.getByRole('link', { name: /Water & Microplastics/ }).click();
    await page.waitForTimeout(2500);
    record(
      'Water page heading',
      (await page.locator('h1').first().textContent())?.includes('Water & Microplastics'),
    );
    await page.waitForSelector('text=Water-body squares', { timeout: 60000 });
    record('surface water stats render', (await page.getByText(/Water-body squares/).count()) > 0);
    record(
      'multi-year monitoring renders',
      (await page.getByText(/Present all year round/).count()) > 0,
    );
    record(
      'microplastic disclaimer visible',
      (await page.getByText(/does not determine chemical composition/).count()) > 0,
    );

    const particle = findLabelledParticle();
    if (particle) {
      for (const channel of ['R', 'A', 'P']) {
        await page.setInputFiles(
          `#channel-${channel}`,
          join(particle.imageDir, `${particle.id}_${channel}.bmp`),
        );
      }
      await page.waitForTimeout(600);
      record(
        'three channels accepted',
        (await page.getByText(/All three channels ready/).count()) > 0,
      );

      await page.getByRole('button', { name: /Screen particle/ }).click();
      await page.waitForSelector('text=Screening result', { timeout: 120000 });
      const outcome = await page
        .locator('h3')
        .filter({ hasText: /Possible microplastic|No microplastic signature/ })
        .first()
        .textContent();
      const expected =
        particle.label === '1' ? /Possible microplastic/ : /No microplastic signature/;
      record(
        'microplastic screening matches HMPD label',
        expected.test(outcome || ''),
        `label=${particle.label} -> "${outcome?.trim()}"`,
      );
      await page.screenshot({ path: join(SHOTS, '05-microplastic.png'), fullPage: true });
    } else {
      skip('microplastic screening matches HMPD label', 'HMPD dataset not present');
    }

    // ── Building Planner ───────────────────────────────────────────────────
    await page.getByRole('link', { name: /Building Planner/ }).click();
    await page.waitForTimeout(1500);
    record(
      'Building page heading',
      (await page.locator('h1').first().textContent())?.includes('Sustainable Building Planner'),
    );

    await page.fill('#plot_size_sqm', '300');
    await page.fill('#occupants', '5');
    await page.getByRole('button', { name: /Get recommendations/ }).click();
    await page.waitForSelector('text=Recommendations for your plot', { timeout: 240000 });

    const recs = await page
      .locator('h3')
      .filter({ hasText: /Install|Design|Keep|Fit|Confirm|Expect|Build|Reconsider|Verify/ })
      .count();
    record('recommendations rendered', recs > 0, `${recs} recommendations`);
    record(
      'site conditions rendered',
      (await page.getByText(/Measured climate at this location/).count()) > 0,
    );
    record(
      'advisory disclaimer visible',
      (await page.getByText(/not a certified structural engineering design/).count()) > 0,
    );
    await page.screenshot({ path: join(SHOTS, '06-building-planner.png'), fullPage: true });

    await page.fill('#plot_size_sqm', '-5');
    await page.getByRole('button', { name: /Get recommendations/ }).click();
    await page.waitForTimeout(500);
    record(
      'form validation rejects bad input',
      (await page.getByText(/Must be greater than zero/).count()) > 0,
    );
  } finally {
    await browser.close();
  }

  // ── Report ───────────────────────────────────────────────────────────────
  const failed = results.filter((r) => !r.ok);
  const skipped = results.filter((r) => r.skipped);
  console.log(
    `\n${results.length - failed.length - skipped.length}/${results.length - skipped.length} ` +
      `checks passed${skipped.length ? ` (${skipped.length} skipped)` : ''}`,
  );

  // Tile-server and favicon noise is not an application fault.
  const appErrors = consoleErrors.filter(
    (e) => !/tile|openstreetmap|favicon|ERR_INTERNET|net::ERR/i.test(e),
  );
  if (appErrors.length) {
    console.log(`\n${appErrors.length} console error(s):`);
    for (const error of appErrors.slice(0, 10)) console.log(`  ${error}`);
  } else {
    console.log('No application console errors.');
  }
  console.log(`\nScreenshots in ${SHOTS}`);

  process.exit(failed.length || appErrors.length ? 1 : 0);
}

main().catch((error) => {
  console.error('Smoke test crashed:', error);
  process.exit(1);
});
