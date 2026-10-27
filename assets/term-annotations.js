/* Offline, authored explanations. Source excerpts and recorded evidence stay untouched. */
(() => {
  'use strict';
  const data = JSON.parse(document.getElementById('term-data').textContent);
  const main = document.querySelector('main');
  if (!main) return;
  const excluded = 'a,button,code,pre,script,style,svg,nav,h1,h2,h3,h4,summary,label,' +
    '.source,.source-path,.location,.evidence,.local-glossary,#glossary,.snapshot,' +
    '#snapshot,#meta,#all-evidence,#node-evidence,.scope-details,.page-hero,.document-stack,.term-card,.term-trigger,.term-help';
  const fallback = new Map(), ambiguous = new Set();
  const keys = item => [item.term, ...(item.aliases || [])].map(key => key.toLocaleLowerCase());
  for (const items of Object.values(data.blocks)) for (const item of items) for (const key of keys(item)) {
    if (fallback.has(key) && fallback.get(key).meaning !== item.meaning) ambiguous.add(key);
    fallback.set(key, item);
  }
  ambiguous.forEach(key => fallback.delete(key));
  for (const item of data.global) for (const key of keys(item)) fallback.set(key, item);
  const dictionaries = new Map();
  function dictionary(id) {
    if (dictionaries.has(id)) return dictionaries.get(id);
    const lookup = new Map(fallback);
    for (const item of data.blocks[id] || []) for (const key of keys(item)) lookup.set(key, item);
    const escaped = [...lookup.keys()].sort((a, b) => b.length - a.length)
      .map(key => key.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
    const result = {lookup, pattern: escaped.length ? new RegExp(escaped.join('|'), 'giu') : null};
    dictionaries.set(id, result);
    return result;
  }
  let active = null, serial = 0, frame = 0;
  const meanings = new WeakMap();
  function boardFor(button) {
    return button.closest('section.block') || button.closest('.context-section') || button.closest('.columns');
  }
  function annotate() {
    observer.disconnect();
    const walker = document.createTreeWalker(main, NodeFilter.SHOW_TEXT, {acceptNode(node) {
      const parent = node.parentElement;
      return parent && parent.closest('p,li,dd') && !parent.closest(excluded) && node.textContent.trim()
        ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
    }});
    const texts = [];
    while (walker.nextNode()) texts.push(walker.currentNode);
    for (const node of texts) {
      const scope = node.parentElement.closest('[data-term-scope],section.block');
      const id = scope?.dataset.termScope || scope?.id || '';
      const {lookup, pattern} = dictionary(id);
      if (!pattern) continue;
      pattern.lastIndex = 0;
      const text = node.textContent, fragment = document.createDocumentFragment();
      let cursor = 0;
      for (const match of text.matchAll(pattern)) {
        const start = match.index, end = start + match[0].length;
        // Do not mark an English word inside an identifier, file path, or larger word.
        if ((/^[a-z0-9_]/i.test(match[0]) && /[a-z0-9_./\\-]/i.test(text[start - 1] || '')) ||
            (/[a-z0-9_]$/i.test(match[0]) && /[a-z0-9_./\\-]/i.test(text[end] || ''))) continue;
        fragment.append(document.createTextNode(text.slice(cursor, start)));
        const button = document.createElement('button');
        button.type = 'button'; button.className = 'term-trigger'; button.textContent = match[0];
        button.setAttribute('aria-expanded', 'false');
        button.setAttribute('aria-label', match[0] + '：查看名词解释');
        meanings.set(button, lookup.get(match[0].toLocaleLowerCase()));
        fragment.append(button); cursor = end;
      }
      if (cursor) { fragment.append(document.createTextNode(text.slice(cursor))); node.replaceWith(fragment); }
    }
    observer.observe(main, {childList:true, subtree:true});
  }
  function close(restoreFocus = false) {
    if (!active) return;
    const {button, layer, resize} = active;
    active = null; resize.disconnect(); layer.remove();
    button.setAttribute('aria-expanded', 'false'); button.removeAttribute('aria-controls');
    button.removeAttribute('aria-describedby');
    if (restoreFocus && button.isConnected) button.focus({preventScroll:true});
  }
  function place() {
    if (!active) return;
    const {button, card, wire} = active;
    if (!button.isConnected || !button.getClientRects().length) { close(); return; }
    const source = button.getBoundingClientRect();
    const board = boardFor(button)?.getBoundingClientRect();
    const header = document.querySelector('.site-header')?.getBoundingClientRect();
    const navigation = document.querySelector('.page-navigation')?.getBoundingClientRect();
    const top = Math.max(16, header && header.bottom > 0 ? header.bottom + 12 : 16);
    const bottom = Math.min(innerHeight - 16, navigation && navigation.top > top ? navigation.top - 12 : innerHeight - 16);
    const width = Math.min(innerWidth < 700 ? 340 : 280, innerWidth - 32);
    const right = innerWidth - width - 16;
    const left = Math.max(16, Math.min(right, board ? board.right + 16 : right));
    card.style.width = width + 'px';
    card.style.maxHeight = Math.max(80, bottom - top) + 'px';
    let height = card.getBoundingClientRect().height;
    let y = Math.max(top, Math.min(source.top - 12, bottom - height));
    // Keep the current term visible when the viewport has no free side margin.
    if (source.right > left && source.left < left + width && source.bottom > y && source.top < y + height) {
      const below = bottom - source.bottom - 14, above = source.top - top - 14;
      if (Math.max(below, above) >= 80) {
        const useBelow = below >= height || (above < height && below >= above);
        card.style.maxHeight = Math.max(80, useBelow ? below : above) + 'px';
        height = card.getBoundingClientRect().height;
        y = useBelow ? source.bottom + 14 : source.top - height - 14;
      }
    }
    card.style.left = left + 'px'; card.style.top = Math.max(top, Math.min(y, bottom - height)) + 'px';
    const target = card.getBoundingClientRect();
    const x1 = source.right + 3, y1 = source.bottom;
    let route;
    if (source.right < target.left) {
      const bend = target.left - 12, y2 = target.top + 32;
      route = `M ${x1} ${y1} H ${bend} V ${y2} H ${target.left}`;
    } else if (source.left > target.right) {
      const bend = target.right + 12, y2 = target.top + 32;
      route = `M ${x1} ${y1} H ${bend} V ${y2} H ${target.right}`;
    } else {
      const x2 = Math.max(target.left + 16, Math.min(x1, target.right - 16));
      const y2 = source.bottom <= target.top ? target.top : target.bottom;
      route = `M ${x1} ${y1} H ${x2} V ${y2}`;
    }
    wire.style.visibility = source.bottom >= top && source.top <= bottom ? 'visible' : 'hidden';
    wire.setAttribute('viewBox', `0 0 ${innerWidth} ${innerHeight}`);
    wire.querySelector('path').setAttribute('d', route);
    const dot = wire.querySelector('circle'); dot.setAttribute('cx', x1); dot.setAttribute('cy', y1);
  }
  function schedule() { cancelAnimationFrame(frame); frame = requestAnimationFrame(place); }
  function open(button) {
    if (active?.button === button) { close(); return; }
    close();
    const item = meanings.get(button);
    if (!item) return;
    const layer = document.createElement('div'); layer.className = 'term-layer';
    const card = document.createElement('aside'); card.className = 'term-card';
    const id = 'term-note-' + (++serial); card.id = id; card.setAttribute('role', 'note');
    card.setAttribute('aria-labelledby', id + '-title');
    const label = document.createElement('div'); label.className = 'term-card-label'; label.textContent = '随文解释';
    const title = document.createElement('h3'); title.className = 'term-card-title'; title.id = id + '-title'; title.textContent = item.term;
    const meaning = document.createElement('p'); meaning.id = id + '-meaning'; meaning.className = 'term-card-meaning'; meaning.textContent = item.meaning;
    const dismiss = document.createElement('button'); dismiss.type = 'button'; dismiss.className = 'term-close';
    dismiss.textContent = '×'; dismiss.setAttribute('aria-label', '关闭名词解释');
    dismiss.addEventListener('click', () => close(true));
    card.append(label, title, meaning, dismiss);
    const ns = 'http://www.w3.org/2000/svg', wire = document.createElementNS(ns, 'svg');
    wire.classList.add('term-wire'); wire.setAttribute('aria-hidden', 'true');
    const path = document.createElementNS(ns, 'path'), dot = document.createElementNS(ns, 'circle'); dot.setAttribute('r', '3');
    wire.append(path, dot); layer.append(wire, card); document.body.append(layer);
    button.setAttribute('aria-expanded', 'true'); button.setAttribute('aria-controls', id);
    button.setAttribute('aria-describedby', meaning.id);
    const resize = new ResizeObserver(schedule);
    active = {button, layer, card, wire, resize};
    place(); resize.observe(main); resize.observe(card);
  }
  const observer = new MutationObserver(records => {
    if (active && (!active.button.isConnected || !active.button.getClientRects().length)) close();
    if (records.some(record => !record.target.closest?.('.term-card,.term-wire,.term-trigger'))) annotate();
    schedule();
  });
  main.addEventListener('click', event => {
    const button = event.target.closest('.term-trigger');
    if (button) open(button);
  });
  document.addEventListener('keydown', event => { if (event.key === 'Escape' && active) { event.preventDefault(); close(true); } });
  document.addEventListener('click', event => {
    if (active && !active.layer.contains(event.target) && !active.button.contains(event.target)) close();
  });
  window.addEventListener('resize', schedule); window.addEventListener('scroll', schedule, {passive:true, capture:true});
  document.addEventListener('toggle', schedule, true);
  window.addEventListener('beforeprint', () => close());
  annotate();
  if (main.querySelector('.term-trigger')) {
    const hint = document.createElement('p'); hint.className = 'term-help';
    hint.textContent = '带绿色下划线的词可以点击查看解释；按 Esc 关闭。解释配色不代表检查通过。';
    const guide = main.querySelector('.beginner-guide') || main.querySelector('section.block');
    if (guide) guide.before(hint);
  }
})();
