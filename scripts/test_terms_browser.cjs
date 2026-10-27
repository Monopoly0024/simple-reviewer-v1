/* Exercise actual offline term notes, including adversarial text and responsive geometry. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {pathToFileURL} = require('node:url');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

(async () => {
  const args = process.argv.slice(2);
  const htmls = args.length ? args.map(p => path.resolve(p)) :
    ['reviewer-overview.html', 'code-breakdown.html', 'report.html'].map(p => path.resolve('outputs/reviewer-example', p));
  const browser = await chromium.launch({headless:true, ...(process.env.BROWSER_EXECUTABLE ? {executablePath:process.env.BROWSER_EXECUTABLE} : {})});
  const page = await browser.newPage({viewport:{width:1440,height:1000}});
  const errors = [], requests = [];
  page.on('pageerror', e => errors.push(e.message));
  page.on('request', r => { if (/^https?:/i.test(r.url())) requests.push(r.url()); });
  await page.emulateMedia({reducedMotion:'reduce'});
  const settle = () => page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  const layout = () => page.evaluate(() => ({
    height:document.documentElement.scrollHeight, width:document.documentElement.scrollWidth,
    elements:[...document.querySelectorAll('main section,main article,main p,main li,main dd,main h2,main h3,main .acceptance-list')]
      .filter(node => !node.closest('details:not([open]),[hidden]') && node.getClientRects().length).map(node => {
      const rect = node.getBoundingClientRect();
      return [node.tagName, node.id, rect.left + scrollX, rect.top + scrollY, rect.width, rect.height];
    })
  }));
  function sameLayout(before, after, label) {
    assert.equal(after.height, before.height, label + ': page height changed');
    assert.equal(after.width, before.width, label + ': page width changed');
    assert.equal(after.elements.length, before.elements.length, label + ': original content structure changed');
    before.elements.forEach((expected, index) => expected.forEach((value, field) => {
      const actual = after.elements[index][field];
      if (typeof value === 'number') assert.ok(Math.abs(value - actual) < 0.5, label + ': moved/resized ' + expected.slice(0,2).join('/') + ' field ' + field + ': ' + value + ' -> ' + actual);
      else assert.equal(actual, value, label + ': original node changed');
    }));
  }
  try {
    for (const html of htmls) {
      await page.setViewportSize({width:1440,height:1000});
      await page.goto(pathToFileURL(html).href);
      await page.evaluate(() => document.fonts.ready);
      const before = await page.locator('pre').allTextContents();
      const acceptance = page.locator('#acceptance .term-trigger:visible').first();
      const trigger = await acceptance.count() ? acceptance : page.locator('section.block .plain-intro .term-trigger:visible').first();
      const term = await trigger.count() ? trigger : page.locator('.term-trigger:visible').first();
      assert.ok(await term.count(), 'No visible annotated terms in ' + html);
      await term.scrollIntoViewIfNeeded();
      const baseline = await layout();
      await term.click();
      await settle();
      sameLayout(baseline, await layout(), path.basename(html) + ' open');
      await page.locator('.term-card').waitFor();
      assert.ok((await page.locator('.term-card-meaning').innerText()).trim().length);
      const controls = await term.getAttribute('aria-controls');
      assert.equal(await page.locator('#' + controls).count(), 1);
      assert.equal(await term.getAttribute('aria-expanded'), 'true');
      assert.equal(await page.locator('.term-card').evaluate(n => getComputedStyle(n).position), 'fixed');
      assert.equal(await page.locator('main .term-card, .term-reading-copy, .term-board-shell').count(), 0);
      for (const width of [320,390,700,1024,1440,1800]) {
        await page.keyboard.press('Escape');
        await page.setViewportSize({width,height:1000});
        await term.scrollIntoViewIfNeeded(); await settle();
        const beforeOpen = await layout();
        await term.click(); await settle();
        sameLayout(beforeOpen, await layout(), path.basename(html) + ' at ' + width);
        assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false, 'Overflow at ' + width + ': ' + html);
        const geometry = await page.locator('.term-layer').evaluate(layer => {
          const card = layer.querySelector('.term-card').getBoundingClientRect();
          const source = document.querySelector('.term-trigger[aria-expanded="true"]').getBoundingClientRect();
          const dot = layer.querySelector('.term-wire circle');
          return {left:card.left,right:card.right,top:card.top,bottom:card.bottom,
            dx:Math.abs(Number(dot.getAttribute('cx')) - (source.right + 3)),
            dy:Math.abs(Number(dot.getAttribute('cy')) - source.bottom),
            coversTerm:card.left < source.right && card.right > source.left && card.top < source.bottom && card.bottom > source.top,
            line:layer.querySelector('.term-wire path').getAttribute('d')};
        });
        assert.ok(geometry.left >= 0 && geometry.right <= width && geometry.top >= 0 && geometry.bottom <= 1000, 'Card exceeds viewport');
        assert.ok(geometry.dx < 2 && geometry.dy < 2, 'Connector is detached from the source term');
        assert.ok(geometry.line.startsWith('M '), 'Missing connector');
        assert.equal(geometry.coversTerm, false, 'Card covers the current term');
        await page.keyboard.press('Escape'); await settle();
        sameLayout(beforeOpen, await layout(), path.basename(html) + ' close at ' + width);
      }
      await term.click();
      await page.keyboard.press('Escape');
      assert.equal(await page.locator('.term-card').count(), 0);
      assert.equal(await term.getAttribute('aria-expanded'), 'false');
      assert.ok(await term.evaluate(n => n === document.activeElement));
      await page.keyboard.press('Enter');
      await page.locator('.term-card').waitFor();
      await page.locator('.term-close').click();
      await page.keyboard.press('Space');
      await page.locator('.term-card').waitFor();
      await page.keyboard.press('Escape');
      assert.equal(await page.locator('.term-layer').count(), 0);
      assert.deepEqual(await page.locator('pre').allTextContents(), before, 'Source/evidence text changed');
      assert.equal(await page.locator('pre .term-trigger, code .term-trigger, a .term-trigger, .local-glossary .term-trigger, #glossary .term-trigger').count(), 0);
      if (await acceptance.count()) {
        await page.setViewportSize({width:1440,height:1000});
        const terms = page.locator('#acceptance .term-trigger:visible');
        for (let index = 0; index < await terms.count(); index++) {
          await terms.nth(index).scrollIntoViewIfNeeded(); await settle();
          const beforeOpen = await layout();
          await terms.nth(index).click(); await settle();
          sameLayout(beforeOpen, await layout(), 'acceptance term ' + index);
          await page.keyboard.press('Escape');
        }
      }
      console.log('Term interaction and zero layout shift passed: ' + path.basename(path.dirname(html)) + '/' + path.basename(html));
    }
    const assets = path.resolve(__dirname, '../assets');
    const data = {
      global:[{term:'CSV',meaning:'Table text'}, {term:'CSV conversion',aliases:['CSV转换'],meaning:'Change table format'},
        {term:'checkpoint',meaning:'Model save'}, {term:'literal',meaning:'<img src=x onerror=alert(1)> & text'},
        {term:'a+b',meaning:'Literal plus'}],
      blocks:{B1:[{term:'token',meaning:'First meaning'}], B2:[{term:'token',meaning:'Second meaning'}]}
    };
    await page.setViewportSize({width:1440,height:1000});
    await page.setContent('<style>main{width:1100px;margin:auto}p{font:18px/1.6 sans-serif}</style><style>' +
      fs.readFileSync(path.join(assets,'term-annotations.css'),'utf8') + '</style><main>' +
      '<p id="outer">token CSV转换 CheckPoint checkpointed folder/checkpoint.pth a+b literal</p>' +
      '<section class="block" id="B1"><p>token</p><pre><code>checkpoint CSV转换</code></pre></section>' +
      '<section class="block" id="B2"><p>token</p></section><div id="dynamic"></div></main>' +
      '<script id="term-data" type="application/json">' + JSON.stringify(data).replaceAll('<','\\u003c') + '</script>' +
      '<script>' + fs.readFileSync(path.join(assets,'term-annotations.js'),'utf8') + '</script>');
    assert.deepEqual(await page.locator('#outer .term-trigger').allTextContents(), ['CSV转换','CheckPoint','a+b','literal']);
    for (const [id, meaning] of [['B1','First meaning'],['B2','Second meaning']]) {
      await page.locator('#'+id+' .term-trigger').click();
      assert.equal(await page.locator('.term-card-meaning').innerText(), meaning);
    }
    assert.equal(await page.locator('.term-card').count(), 1, 'Only one explanation should be open');
    await page.locator('#outer .term-trigger').filter({hasText:'literal'}).click();
    assert.equal(await page.locator('.term-card img').count(), 0);
    assert.equal(await page.locator('.term-card-meaning').textContent(), data.global[3].meaning);
    await page.keyboard.press('Escape');
    await page.evaluate(() => {
      const paragraph = document.createElement('p'); paragraph.textContent = 'checkpoint';
      document.querySelector('#dynamic').append(paragraph);
    });
    await page.locator('#dynamic .term-trigger').waitFor();
    await page.locator('#dynamic .term-trigger').click();
    await page.evaluate(() => document.querySelector('#dynamic').replaceChildren());
    await page.waitForFunction(() => !document.querySelector('.term-card'));
    assert.equal(await page.locator('pre .term-trigger').count(), 0);
    assert.deepEqual(errors, []); assert.deepEqual(requests, []);
    console.log('Aliases, longest match, identifier boundaries, local definitions, literal text, dynamic updates and offline checks passed.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
