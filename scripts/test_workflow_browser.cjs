// Verify vector text bounds and the same responsive picture rule used by README.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {pathToFileURL} = require('node:url');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
(async () => {
  const root = path.resolve(__dirname, '..');
  const out = path.resolve(process.argv[2] || 'review-output/workflow-browser');
  fs.mkdirSync(out, {recursive: true});
  const browser = await chromium.launch({headless: true,
    ...(process.env.BROWSER_EXECUTABLE ? {executablePath: process.env.BROWSER_EXECUTABLE} : {})});
  try {
    const page = await browser.newPage();
    const checks = [];
    for (const name of ['workflow-mobile-en', 'workflow-mobile', 'workflow-overview-en', 'workflow-overview']) {
      await page.goto(pathToFileURL(path.join(root, 'assets', name + '.svg')).href);
      await page.evaluate(() => document.fonts.ready);
      const result = await page.evaluate(() => {
        const svg = document.querySelector('svg'), box = svg.viewBox.baseVal;
        return {width: box.width, height: box.height, overflow: [...svg.querySelectorAll('text')]
          .filter(t => {const b = t.getBBox(); return b.x < 0 || b.y < 0 ||
            b.x + b.width > box.width || b.y + b.height > box.height;}).map(t => t.textContent)};
      });
      assert.deepEqual(result.overflow, [], name);
      await page.setViewportSize({width: result.width, height: result.height});
      await page.screenshot({path: path.join(out, name + '.png')});
      checks.push({name, ...result});
    }
    const readme = fs.readFileSync(path.join(root, 'README.md'), 'utf8');
    const picture = readme.match(/<picture>[\s\S]*?<\/picture>/);
    assert.ok(picture, 'README must contain a responsive workflow picture');
    const fixture = path.join(out, 'readme-picture.html');
    fs.writeFileSync(fixture, '<!doctype html><meta charset="utf-8">' +
      '<style>body{margin:0}img{max-width:100%;height:auto}</style>' +
      picture[0].replace(/(src|srcset)="(assets\/[^"]+)"/g,
        (_, attr, file) => attr + '="' + pathToFileURL(path.join(root, file)).href + '"'));
    for (const width of [320, 390, 640, 641, 1440]) {
      await page.setViewportSize({width, height: 1000});
      await page.goto(pathToFileURL(fixture).href);
      await page.locator('img').evaluate(i => i.decode());
      const result = await page.locator('img').evaluate(i => ({source: i.currentSrc.split('/').pop(),
        overflow: document.documentElement.scrollWidth > innerWidth}));
      assert.equal(result.overflow, false);
      assert.equal(result.source, width <= 640 ? 'workflow-mobile-en.svg' : 'workflow-overview-en.svg');
      checks.push({width, ...result});
    }
    fs.writeFileSync(path.join(out, 'checks.json'), JSON.stringify(checks, null, 2));
    console.log(JSON.stringify(checks));
  } finally {await browser.close();}
})().catch(e => {console.error(e); process.exitCode = 1;});
