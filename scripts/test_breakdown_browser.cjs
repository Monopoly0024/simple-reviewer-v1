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
    const themed = await page.locator('section.block').evaluateAll(blocks => blocks.map(block => {
      const heading = block.querySelector('.block-heading h2');
      const badge = block.querySelector('.badge');
      return {id: block.id,
        background: getComputedStyle(block).backgroundColor,
        headingBackground: getComputedStyle(block.querySelector('.block-heading')).backgroundColor,
        headingColor: getComputedStyle(heading).color,
        stages: [...block.querySelectorAll('.reading-flow > [data-stage]')].map(el =>
          ({role:el.dataset.stage, background:getComputedStyle(el).backgroundColor})),
        badgeClass: badge && badge.className};
    }));
    for (const block of themed) {
      assert.equal(block.background, 'rgb(255, 255, 255)', 'Parallel blocks share a white canvas');
      assert.equal(block.headingBackground, 'rgb(23, 32, 23)');
      assert.equal(block.headingColor, 'rgb(255, 255, 255)');
      assert.deepEqual(block.stages, [{role:'input',background:'rgb(255, 255, 255)'},
        {role:'process',background:'rgb(112, 242, 139)'}, {role:'output',background:'rgb(225, 241, 225)'}],
        'Contrast should express input/process/output on ' + block.id);
      assert.match(block.badgeClass || '', /badge (passed|failed|pending|unchecked)/,
        'Verification state should remain independently labeled on ' + block.id);
    }
    const catalogBackgrounds = await page.locator('.catalog-card').evaluateAll(cards =>
      cards.map(card => getComputedStyle(card).backgroundColor));
    assert.equal(catalogBackgrounds.length, total);
    assert.ok(catalogBackgrounds.every(bg=>bg==='rgb(255, 255, 255)'), 'Parallel catalog cards share one style');
    assert.equal(await page.locator('[data-theme]').count(), 0, 'No cycling colors by block ID');
    const clippedPreviews = await page.locator('.document-card').evaluateAll(cards => cards.filter(card=>
      card.clientHeight>0 && card.scrollHeight>card.clientHeight+1).map(card=>card.innerText));
    assert.deepEqual(clippedPreviews, [], 'Larger preview text should remain visible');
    const clippedTitles = await page.locator('.graph-scroll .node').evaluateAll(nodes => nodes.flatMap(node => {
      const rect = node.querySelector('rect').getBBox();
      return [...node.querySelectorAll('text')].filter(t=>{const b=t.getBBox();return b.x<rect.x ||
        b.x+b.width>rect.x+rect.width || b.y+b.height>rect.y+rect.height;}).map(t=>t.textContent);
    }));
    assert.deepEqual(clippedTitles, [], 'Graph text should fit inside nodes');
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
    const result = {blocks: total, sourceCount, semanticContrast: true, parallelCardsUniform: true,
      verificationLabelsPreserved: true, graphTextFits: true, widths, keyboardNavigation: true,
      filter: true, externalRequests: external, pageErrors: errors};
    if (artifacts) fs.writeFileSync(path.join(artifacts, 'browser-check.json'), JSON.stringify(result, null, 2));
    console.log(JSON.stringify(result));
  } finally {await browser.close();}
})().catch(error => {console.error(error);process.exit(1);});
