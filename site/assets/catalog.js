(() => {
  'use strict';
  const root = document.querySelector('[data-catalog]');
  if (!root) return;
  const form = document.querySelector('#tool-search');
  const input = form.querySelector('input');
  const cards = [...root.querySelectorAll('[data-tool]')];
  const categories = [...document.querySelectorAll('[data-filter]')];
  const count = document.querySelector('#result-count');
  const empty = document.querySelector('#no-results');
  const reset = document.querySelector('#reset-search');
  const clear = document.querySelector('#clear-query');
  const sort = document.querySelector('#sort-tools');
  const heading = document.querySelector('#catalog-title');
  const normalize = value => value.normalize('NFKC').toLocaleLowerCase('ja').replace(/[\u30a1-\u30f6]/g, c => String.fromCharCode(c.charCodeAt(0) - 0x60));
  let selected = root.dataset.category || 'all';
  let timer;
  const known = new Set(categories.map(link => link.dataset.filter));
  const params = new URLSearchParams(location.search);
  if (known.has(params.get('category'))) selected = params.get('category');
  input.value = (params.get('q') || '').slice(0, 160);
  if (params.get('sort') === 'name') sort.value = 'name';
  const categoryURL = id => {
    const url = new URL(id === 'all' ? '/' : `/categories/${id}/`, location.origin);
    if (input.value.trim()) url.searchParams.set('q', input.value.trim());
    if (sort.value === 'name') url.searchParams.set('sort', 'name');
    url.hash = 'software';
    return url;
  };
  if (root.dataset.category !== 'all' && selected !== root.dataset.category) {
    location.replace(categoryURL(selected));
    return;
  }
  const update = (save = true) => {
    const terms = normalize(input.value).trim().split(/\s+/u).filter(Boolean);
    let found = 0;
    for (const card of cards) {
      const text = normalize(card.dataset.search);
      const matches = (selected === 'all' || card.dataset.category === selected) && terms.every(term => text.includes(term));
      card.hidden = !matches;
      if (matches) found++;
    }
    const list = [...cards].sort(sort.value === 'name'
      ? (a, b) => a.dataset.name.localeCompare(b.dataset.name, 'ja')
      : (a, b) => Number(a.dataset.order) - Number(b.dataset.order));
    for (const card of list) root.append(card);
    const current = categories.find(link => link.dataset.filter === selected);
    const label = current?.dataset.label || 'すべて';
    heading.textContent = selected === 'all' ? '公開中のソフト' : label;
    count.textContent = `${cards.length}本中 ${found}本を表示`;
    empty.hidden = found !== 0;
    reset.hidden = !input.value && selected === 'all' && sort.value === 'recommended';
    clear.hidden = !input.value;
    for (const link of categories) {
      if (link.dataset.filter === selected) link.setAttribute('aria-current', 'true');
      else link.removeAttribute('aria-current');
    }
    if (save) {
      const url = new URL(location.href);
      const baseCategory = root.dataset.category || 'all';
      if (input.value.trim()) url.searchParams.set('q', input.value.trim()); else url.searchParams.delete('q');
      if (selected !== baseCategory) url.searchParams.set('category', selected); else url.searchParams.delete('category');
      if (sort.value === 'name') url.searchParams.set('sort', 'name'); else url.searchParams.delete('sort');
      history.replaceState(null, '', url);
    }
  };
  form.addEventListener('submit', event => { event.preventDefault(); update(); document.querySelector('#software').scrollIntoView({block: 'start'}); });
  input.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(update, 100); });
  clear.addEventListener('click', () => { input.value = ''; update(); input.focus(); });
  reset.addEventListener('click', () => {
    input.value = ''; selected = 'all'; sort.value = 'recommended';
    if (root.dataset.category !== 'all') { location.assign(categoryURL('all')); return; }
    update(); input.focus();
  });
  sort.addEventListener('change', () => update());
  categories.forEach(link => link.addEventListener('click', event => {
    if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey || event.button !== 0) return;
    event.preventDefault(); selected = link.dataset.filter;
    if (root.dataset.category !== 'all' && selected !== root.dataset.category) { location.assign(categoryURL(selected)); return; }
    update();
    document.querySelector('#software').scrollIntoView({block: 'start'});
  }));
  document.querySelectorAll('[data-search-example]').forEach(link => link.addEventListener('click', event => {
    if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey || event.button !== 0) return;
    event.preventDefault(); selected = 'all'; input.value = link.dataset.searchExample; update();
    document.querySelector('#software').scrollIntoView({block: 'start'}); input.focus({preventScroll: true});
  }));
  document.addEventListener('keydown', event => {
    if (event.key === '/' && !event.ctrlKey && !event.metaKey && !event.altKey && !event.target.closest('input,textarea,select,[contenteditable]')) {
      event.preventDefault(); input.focus();
    }
    if (event.key === 'Escape' && event.target === input) { input.value = ''; update(); }
  });
  document.querySelectorAll('[data-js-only]').forEach(element => { element.hidden = false; });
  input.disabled = false;
  form.querySelector('[type="submit"]').disabled = false;
  update(false);
})();
