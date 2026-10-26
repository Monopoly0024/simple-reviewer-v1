// Click every page-to-page route and its return path at desktop and mobile widths.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {pathToFileURL, fileURLToPath} = require('node:url');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
(async () => {
  const root = path.resolve(process.argv[2] || 'review-output');
  const guide = process.argv[3] ? path.resolve(process.argv[3]) : null;
  const pages = ['reviewer-overview.html', 'code-breakdown.html', 'report.html'].map(n => path.join(root, n));
  if (guide) pages.push(guide);
  const out = path.resolve(process.argv[4] || path.join(root, 'navigation-browser'));
  fs.mkdirSync(out, {recursive: true});
  const browser = await chromium.launch({headless: true,
    ...(process.env.BROWSER_EXECUTABLE ? {executablePath: process.env.BROWSER_EXECUTABLE} : {})});
  try {
    const page = await browser.newPage();
    const errors = [], external = [], checks = [];
    page.on('pageerror', e => errors.push(e.message));
    page.on('request', r => {if (/^https?:/.test(r.url())) external.push(r.url());});
    await page.emulateMedia({reducedMotion: 'reduce'});
    for (const width of [320, 390, 1440]) {
      await page.setViewportSize({width, height: 900});
      for (const source of pages) {
        await page.goto(pathToFileURL(source).href);
        const nav = page.getByRole('navigation', {name: '页面导航', exact: true});
        assert.equal(await nav.count(), 1, 'One page navigation per document');
        const links = await nav.locator('a').evaluateAll(nodes => nodes.map(n => n.href));
        assert.deepEqual(links.map(u => path.resolve(fileURLToPath(u))).sort(), [...pages].sort());
        const current = nav.locator('a[aria-current="page"]');
        assert.equal(await current.count(), 1);
        assert.equal(path.resolve(fileURLToPath(await current.evaluate(n => n.href))), source);
        for (const target of pages.filter(p => p !== source)) {
          const link = nav.locator('a');
          const targetURL = pathToFileURL(target).href;
          const targetIndex = links.indexOf(targetURL);
          assert.ok(targetIndex >= 0);
          await Promise.all([page.waitForURL(targetURL), link.nth(targetIndex).click()]);
          const returnNav = page.getByRole('navigation', {name: '页面导航', exact: true});
          const returnIndex = (await returnNav.locator('a').evaluateAll(as => as.map(a => a.href)))
            .indexOf(pathToFileURL(source).href);
          await Promise.all([page.waitForURL(pathToFileURL(source).href), returnNav.locator('a').nth(returnIndex).click()]);
          checks.push({width, from: path.basename(source), to: path.basename(target), returned: true});
        }
        const keyboardTarget = links.find(u => u !== pathToFileURL(source).href);
        await nav.locator('a').nth(links.indexOf(keyboardTarget)).focus();
        await Promise.all([page.waitForURL(keyboardTarget), page.keyboard.press('Enter')]);
        await page.goto(pathToFileURL(source).href);
        await page.evaluate(() => scrollTo(0, document.body.scrollHeight));
        const navBox = await nav.boundingBox();
        assert.ok(navBox && navBox.y >= 0 && navBox.y + navBox.height <= 901, 'Navigation stays in viewport');
        await nav.locator('a').first().focus();
        assert.ok(await nav.isVisible());
        assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false,
          'Overflow in ' + path.basename(source) + ' at width ' + width);
        await page.evaluate(() => scrollTo(0, 0));
        await page.screenshot({path: path.join(out, `${path.basename(source, '.html')}-${width}.png`)});
      }
    }
    assert.deepEqual(errors, []);
    assert.deepEqual(external, []);
    const result = {pages: pages.length, roundTrips: checks.length, widths: [320, 390, 1440],
      checks, pageErrors: errors, externalRequests: external};
    fs.writeFileSync(path.join(out, 'checks.json'), JSON.stringify(result, null, 2));
    console.log(JSON.stringify({pages: result.pages, roundTrips: result.roundTrips,
      widths: result.widths, keyboardLinks: true, fixedNavigation: true, pageErrors: errors, externalRequests: external}));
  } finally {await browser.close();}
})().catch(e => {console.error(e); process.exitCode = 1;});
