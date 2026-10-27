// Optional browser verification for the full beginner-facing overview.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {pathToFileURL, fileURLToPath} = require('node:url');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

(async () => {
  const html = path.resolve(process.argv[2] || 'review-output/reviewer-overview.html');
  const artifacts = path.resolve(process.argv[3] || 'review-output/overview-browser');
  fs.mkdirSync(artifacts, {recursive: true});
  const browser = await chromium.launch({headless: true,
    ...(process.env.BROWSER_EXECUTABLE ? {executablePath: process.env.BROWSER_EXECUTABLE} : {})});
  try {
    const page = await browser.newPage({viewport: {width: 1440, height: 1000}});
    const errors = [], requests = [];
    page.on('pageerror', e => errors.push(e.message));
    page.on('request', r => {if (/^https?:/.test(r.url())) requests.push(r.url());});
    await page.emulateMedia({reducedMotion: 'reduce'});
    await page.goto(pathToFileURL(html).href);
    const record = JSON.parse(fs.readFileSync(path.join(path.dirname(html), 'review.effective.json'), 'utf8'));
    const projectTitle = record.presentation?.project_title || record.title;
    assert.ok((await page.locator('h1').innerText()).includes(projectTitle));
    assert.equal(await page.locator('.document-card').count(), Math.min(record.blocks.length, 6));
    assert.equal(await page.locator('.metric .verdict').getAttribute('class'), 'verdict ' + record.overall);
    for (const req of record.requirements) {
      const card = page.locator('.acceptance').filter({has: page.locator('h3', {hasText: req.id + ' · '})});
      assert.equal(await card.count(), 1, 'Missing acceptance ' + req.id);
      assert.equal(await card.getAttribute('class'), 'acceptance ' + req.status);
    }
    for (const id of ['goal', 'changes', 'acceptance', 'risks', 'next-actions']) {
      assert.equal(await page.locator('#' + id).count(), 1, 'Missing or duplicate section ' + id);
    }
    await page.locator('.topnav a[href="#acceptance"]').click();
    assert.equal(await page.evaluate(() => location.hash), '#acceptance');
    const details = page.locator('#acceptance details').first();
    if (await details.count()) {
      await details.locator('summary').focus();
      await page.keyboard.press('Enter');
      assert.equal(await details.evaluate(d => d.open), true);
      await details.locator('summary').click();
    }
    for (const anchor of await page.locator('a[href]:not([href^="#"])').evaluateAll(as => as.map(a => a.getAttribute('href')))) {
      const target = new URL(anchor, pathToFileURL(html));
      assert.ok(fs.existsSync(fileURLToPath(target)), 'Broken local link ' + anchor);
    }
    const readingLinks = await page.locator('.beginner-route a').evaluateAll(as => as.map(a => a.href));
    assert.equal(readingLinks.length, record.blocks.length);
    for (const link of readingLinks) {
      const anchor = page.locator('.beginner-route a').filter({hasText: new URL(link).hash.slice(1) + ' ·'});
      await anchor.click();
      const id = new URL(link).hash;
      assert.equal(await page.evaluate(() => location.hash), id);
      assert.ok(await page.locator(id).isVisible());
      await page.goBack();
    }
    await page.evaluate(() => scrollTo(0, 0));
    await page.screenshot({path: path.join(artifacts, 'desktop.png')});
    for (const width of [320, 390, 700, 1024, 1800]) {
      await page.setViewportSize({width, height: 900});
      assert.equal(await page.locator('.document-card:visible').count(), Math.min(record.blocks.length, 6));
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false, 'Overflow ' + width);
    }
    await page.setViewportSize({width: 390, height: 844});
    await page.evaluate(() => scrollTo(0, 0));
    await page.screenshot({path: path.join(artifacts, 'mobile.png')});
    await page.emulateMedia({media: 'print'});
    await page.pdf({path: path.join(artifacts, 'print.pdf'), format: 'A4', printBackground: true});
    assert.deepEqual(errors, []);
    assert.deepEqual(requests, []);
    await page.emulateMedia({media: 'screen'});
    await page.goto(pathToFileURL(path.join(path.dirname(html), 'report.html')).href);
    assert.equal(await page.locator('#title').innerText(), record.title);
    const node = page.locator('.node').first();
    await node.focus();
    await page.keyboard.press('Enter');
    assert.ok((await page.locator('#node-title').innerText()).includes(record.nodes[0].id));
    for (const width of [320, 390, 1440]) {
      await page.setViewportSize({width, height: 900});
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false, 'Report overflow ' + width);
    }
    assert.deepEqual(errors, []);
    assert.deepEqual(requests, []);
    const result = {sections: 5, keyboardDetails: true, navigation: true, links: true,
      effectiveStatuses: true, fullReport: true, widths: [320, 390, 700, 1024, 1800],
      print: true, pageErrors: errors, externalRequests: requests};
    fs.writeFileSync(path.join(artifacts, 'browser-check.json'), JSON.stringify(result, null, 2));
    console.log(JSON.stringify(result));
  } finally { await browser.close(); }
})().catch(e => {console.error(e); process.exit(1);});
