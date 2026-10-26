// Optional browser smoke test: npm install --no-save playwright
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {pathToFileURL} = require('node:url');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

(async () => {
  const html = path.resolve(process.argv[2] || 'review-output/code-breakdown.html');
  const artifacts = process.argv[3] ? path.resolve(process.argv[3]) : null;
  if (artifacts) fs.mkdirSync(artifacts, {recursive: true});
  const browser = await chromium.launch({headless: true,
    ...(process.env.BROWSER_EXECUTABLE ? {executablePath: process.env.BROWSER_EXECUTABLE} : {})});
  try {
    const page = await browser.newPage({viewport: {width: 1440, height: 1000}});
    const errors = [], external = [];
    page.on('pageerror', e => errors.push(e.message));
    page.on('request', r => {if (/^https?:/.test(r.url())) external.push(r.url());});
    await page.emulateMedia({reducedMotion: 'reduce'});
    await page.goto(pathToFileURL(html).href);
    const total = await page.locator('section.block').count();
    assert.ok(total > 0);
    const palette = {violet: ['rgb(250, 248, 255)', 'rgb(73, 53, 138)'],
      cyan: ['rgb(244, 252, 254)', 'rgb(21, 93, 110)'],
      pink: ['rgb(255, 247, 252)', 'rgb(128, 55, 101)'],
      blue: ['rgb(247, 249, 255)', 'rgb(53, 78, 140)'],
      teal: ['rgb(244, 251, 249)', 'rgb(32, 93, 88)']};
    const themed = await page.locator('section.block[data-theme]').evaluateAll(blocks => blocks.map(block => {
      const heading = block.querySelector('.block-heading h2');
      const badge = block.querySelector('.badge');
      return {id: block.id, theme: block.dataset.theme,
        background: getComputedStyle(block).backgroundColor,
        headingColor: getComputedStyle(heading).color,
        badgeClass: badge && badge.className};
    }));
    assert.equal(themed.length, total, 'Every block should have a topic theme');
    for (const block of themed) {
      assert.ok(palette[block.theme], 'Unknown theme on ' + block.id);
      assert.equal(block.background, palette[block.theme][0], 'Block tint missing on ' + block.id);
      assert.equal(block.headingColor, palette[block.theme][1], 'Heading accent missing on ' + block.id);
      assert.match(block.badgeClass || '', /badge (passed|failed|pending|unchecked)/,
        'Verification state should remain independently labeled on ' + block.id);
    }
    const catalogThemes = await page.locator('.catalog-card[data-theme]').evaluateAll(cards =>
      cards.map(card => ({id: card.getAttribute('href').slice(1), theme: card.dataset.theme})));
    assert.equal(catalogThemes.length, total, 'Every block should have a themed catalog card');
    for (const card of catalogThemes) {
      assert.equal(card.theme, themed.find(block => block.id === card.id).theme,
        'Catalog and detail theme should match for ' + card.id);
    }
    assert.equal(await page.locator('.reading-flow').count(), total);
    const sourceCount = await page.locator('details.source').count();
    assert.ok(sourceCount > 0);
    await page.locator('#toggle-code').click();
    assert.equal(await page.locator('details.source[open]').count(), sourceCount);
    await page.locator('#toggle-code').click();
    assert.equal(await page.locator('details.source[open]').count(), 0);
    const firstTitle = await page.locator('section.block').first().locator('h2').innerText();
    await page.locator('#block-search').fill(firstTitle.slice(0, 5));
    assert.equal(await page.locator('.catalog-card:not([hidden])').count(), 1, 'Search should narrow the catalog');
    assert.equal(await page.locator('section.block:not([hidden])').count(), 1, 'Search should narrow the blocks');
    await page.locator('#block-search').fill('no-such-block');
    assert.equal(await page.locator('.catalog-card:not([hidden])').count(), 0, 'Search should show no match');
    await page.locator('#block-search').fill('');
    await page.locator('#filter').click();
    assert.equal(await page.locator('section.block.passed:not([hidden])').count(), 0);
    const graphNode = page.locator('.graph-scroll .node').first();
    const target = await graphNode.getAttribute('data-node');
    await graphNode.focus();
    await page.keyboard.press('Enter');
    assert.equal(await page.evaluate(() => location.hash), '#' + target);
    assert.equal(await page.locator('section.block[hidden]').count(), 0);
    await page.locator('.sidebar a[href="#B1"]').click();
    assert.equal(await page.evaluate(() => location.hash), '#B1');
    if (artifacts) {
      await page.evaluate(() => scrollTo(0, 0));
      await page.screenshot({path: path.join(artifacts, 'desktop.png')});
      await page.locator('#B2').evaluate(block => scrollTo(0, block.getBoundingClientRect().top + scrollY - 80));
      await page.screenshot({path: path.join(artifacts, 'desktop-block.png')});
    }
    const widths = [320, 390, 700, 1024];
    for (const width of widths) {
      await page.setViewportSize({width, height: 844});
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false,
        'Page overflow at width ' + width);
    }
    if (artifacts) {
      await page.setViewportSize({width: 390, height: 844});
      await page.locator('#B2').evaluate(block => scrollTo(0, block.getBoundingClientRect().top + scrollY - 80));
      await page.screenshot({path: path.join(artifacts, 'mobile-block.png')});
      await page.evaluate(() => scrollTo(0, 0));
      await page.screenshot({path: path.join(artifacts, 'mobile.png')});
    }
    assert.deepEqual(errors, []);
    assert.deepEqual(external, []);
    const result = {blocks: total, sourceCount, themeAssignments: themed, catalogThemes,
      topicAndVerificationColorsIndependent: true, widths, keyboardNavigation: true,
      filter: true, externalRequests: external, pageErrors: errors};
    if (artifacts) fs.writeFileSync(path.join(artifacts, 'browser-check.json'), JSON.stringify(result, null, 2));
    console.log(JSON.stringify(result));
  } finally {await browser.close();}
})().catch(error => {console.error(error);process.exit(1);});
