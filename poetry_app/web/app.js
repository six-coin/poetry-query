(() => {
  'use strict';

  const MODES = ['original', 'translation', 'full'];
  const STORAGE_MODE = 'shijian.mode';
  const SEARCH_LIMIT = 60;

  const Settings = window.ShijianSettings;

  const state = {
    apiReady: false,
    query: '',
    items: [],
    total: 0,
    searchToken: 0,
    searchTimer: null,
    loadingSearch: false,
    searchFailed: false,
    isComposing: false,
    detail: null,
    detailId: null,
    detailToken: 0,
    mode: 'full',
    meta: null,
    homeScroll: 0,
    exporting: false,
    modalOpen: false,
    modalOnClose: null,
    settings: Settings ? Settings.load() : null,
    configPath: '',
    settingsSaveTimer: null,
    settingsSaveErrorShown: false
  };

  const els = {
    homeView: document.getElementById('home-view'),
    detailView: document.getElementById('detail-view'),
    homeButton: document.getElementById('home-button'),
    topbarTitle: document.getElementById('topbar-title'),
    settingsButton: document.getElementById('settings-button'),
    outputButton: document.getElementById('output-button'),
    homeOutputLink: document.getElementById('home-output-link'),

    searchShell: document.getElementById('search-shell'),
    searchInput: document.getElementById('search-input'),
    searchClear: document.getElementById('search-clear'),
    quickRow: document.querySelector('.quick-row'),

    resultsSection: document.getElementById('results-section'),
    resultsSummary: document.getElementById('results-summary'),
    resultsQuery: document.getElementById('results-query'),
    resultsList: document.getElementById('results-list'),
    resultsEmpty: document.getElementById('results-empty'),
    resultsLoading: document.getElementById('results-loading'),
    resultsMore: document.getElementById('results-more'),
    loadMore: document.getElementById('load-more'),
    metaCount: document.getElementById('meta-count'),

    backButton: document.getElementById('back-button'),
    exportTextButton: document.getElementById('export-text-button'),
    exportPdfButton: document.getElementById('export-pdf-button'),
    detailLoading: document.getElementById('detail-loading'),
    detailArticle: document.getElementById('detail-article'),

    poemTitle: document.getElementById('poem-title'),
    poemDynasty: document.getElementById('poem-dynasty'),
    poemAuthor: document.getElementById('poem-author'),
    poemNoteCount: document.getElementById('poem-note-count'),
    titleNotesBlock: document.getElementById('title-notes-block'),
    titleNotesList: document.getElementById('title-notes-list'),

    modeButtons: Array.from(document.querySelectorAll('.mode-button')),
    annotationPill: document.getElementById('annotation-pill'),

    reading: document.getElementById('reading'),
    appendixBlock: document.getElementById('appendix-block'),
    appendixList: document.getElementById('appendix-list'),

    toastRegion: document.getElementById('toast-region'),
    modalRoot: document.getElementById('modal-root')
  };

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  function clear(node) {
    while (node && node.firstChild) node.removeChild(node.firstChild);
  }

  function qsa(selector, root) {
    return Array.prototype.slice.call((root || document).querySelectorAll(selector));
  }

  function formatNumber(value) {
    return Number(value || 0).toLocaleString('zh-CN');
  }

  function basename(path) {
    return String(path || '').split(/[\\/]/).pop() || '';
  }

  const SUPERSCRIPT_DIGITS = {
    '0': '⁰', '1': '¹', '2': '²', '3': '³', '4': '⁴',
    '5': '⁵', '6': '⁶', '7': '⁷', '8': '⁸', '9': '⁹'
  };

  function superscriptNumber(number) {
    return String(number).split('').map((digit) => SUPERSCRIPT_DIGITS[digit] || digit).join('');
  }

  function setTopbarTitle(text, tooltip) {
    els.topbarTitle.textContent = text;
    els.topbarTitle.title = tooltip || text;
  }

  function updateTopbarTitle() {
    if (!els.detailView.hidden && state.detail) {
      setTopbarTitle(state.detail.poem.title);
      return;
    }
    if (!els.detailView.hidden) {
      setTopbarTitle('诗笺');
      return;
    }
    if (!state.query && els.resultsSection.hidden) {
      setTopbarTitle('诗笺');
      return;
    }
    if (state.loadingSearch) {
      setTopbarTitle('搜索——检索中');
      return;
    }
    if (state.searchFailed) {
      setTopbarTitle('搜索——检索失败');
      return;
    }
    setTopbarTitle('搜索——' + formatNumber(state.total) + '条结果');
  }

  function debounceSearch() {
    window.clearTimeout(state.searchTimer);
    state.searchTimer = window.setTimeout(() => {
      if (state.isComposing) return;
      const query = els.searchInput.value.trim();
      if (!query) {
        resetSearch();
        return;
      }
      runSearch(query, true);
    }, 180);
  }

  function apiBridge() {
    return window.pywebview && window.pywebview.api ? window.pywebview.api : null;
  }

  async function callApi(name) {
    const bridge = apiBridge();
    if (!bridge || typeof bridge[name] !== 'function') {
      throw new Error('应用接口尚未就绪');
    }
    const args = Array.prototype.slice.call(arguments, 1);
    return await bridge[name].apply(bridge, args);
  }

  // ---------- 检索 ----------

  function setSearchLoading(isLoading) {
    state.loadingSearch = isLoading;
    if (isLoading) {
      els.resultsSection.hidden = false;
      // 追加加载时保留已有结果，只显示按钮状态。
      els.resultsLoading.hidden = state.items.length > 0;
    } else {
      els.resultsLoading.hidden = true;
    }
    els.loadMore.disabled = isLoading;
    els.loadMore.textContent = isLoading ? '加载中…' : '加载更多';
    updateTopbarTitle();
  }

  function resetSearch() {
    els.homeView.classList.remove('has-results');
    if (!els.homeView.hidden) {
      window.scrollTo({ top: 0, behavior: 'smooth' });
    }
    state.searchToken += 1;
    state.query = '';
    state.items = [];
    state.total = 0;
    state.loadingSearch = false;
    state.searchFailed = false;
    els.resultsSection.hidden = true;
    els.resultsList.textContent = '';
    els.resultsEmpty.hidden = true;
    els.resultsLoading.hidden = true;
    els.resultsMore.hidden = true;
    els.searchClear.hidden = true;
    els.searchInput.value = '';
    updateTopbarTitle();
  }

  async function runSearch(query, reset) {
    const token = ++state.searchToken;
    state.query = query;
    state.searchFailed = false;
    els.homeView.classList.add('has-results');
    els.searchClear.hidden = false;
    els.resultsSection.hidden = false;
    updateTopbarTitle();

    if (reset) {
      state.items = [];
      state.total = 0;
      clear(els.resultsList);
      els.resultsEmpty.hidden = true;
      els.resultsSummary.textContent = '正在检索…';
      els.resultsQuery.textContent = '「' + query + '」';
      els.resultsMore.hidden = true;
      els.resultsLoading.innerHTML =
        '<div class="result-card skeleton-card">' +
          '<div class="skeleton skeleton-line" style="width:34%"></div>' +
          '<div class="skeleton skeleton-line" style="width:72%;margin-top:10px"></div>' +
        '</div>' +
        '<div class="result-card skeleton-card">' +
          '<div class="skeleton skeleton-line" style="width:27%"></div>' +
          '<div class="skeleton skeleton-line" style="width:64%;margin-top:10px"></div>' +
        '</div>';
    }

    setSearchLoading(true);

    try {
      const offset = reset ? 0 : state.items.length;
      const result = await callApi('search', query, offset, SEARCH_LIMIT);
      if (token !== state.searchToken) return;
      if (!result || !result.ok) {
        throw new Error(result && result.error ? result.error : '检索失败');
      }

      if (reset) state.items = result.items || [];
      else state.items = state.items.concat(result.items || []);
      state.total = result.total || 0;
      renderResults();
    } catch (error) {
      if (token !== state.searchToken) return;
      setSearchLoading(false);
      state.searchFailed = true;
      updateTopbarTitle();
      els.resultsSummary.textContent = '检索未完成';
      els.resultsEmpty.hidden = false;
      els.resultsEmpty.querySelector('h3').textContent = '检索没有完成';
      els.resultsEmpty.querySelector('p').textContent = error.message || '请稍后再试。';
      showToast(error.message || '检索失败', { type: 'error' });
    } finally {
      if (token === state.searchToken) setSearchLoading(false);
    }
  }

  function renderResults() {
    els.resultsSection.hidden = false;
    els.resultsLoading.hidden = true;
    els.resultsEmpty.hidden = state.items.length > 0;

    const shown = state.items.length;
    let summary = '共 ' + formatNumber(state.total) + ' 首';
    if (state.total > shown) summary += ' · 已显示 ' + formatNumber(shown);
    els.resultsSummary.textContent = summary;
    els.resultsQuery.textContent = '「' + state.query + '」';

    if (state.items.length === 0) {
      els.resultsEmpty.querySelector('h3').textContent = '没有找到相符的标题';
      els.resultsEmpty.querySelector('p').textContent =
        '没有匹配「' + state.query + '」的标题。换一个更短的词试试。';
    }

    clear(els.resultsList);
    const fragment = document.createDocumentFragment();
    state.items.forEach((item) => fragment.appendChild(createResultCard(item)));
    els.resultsList.appendChild(fragment);

    els.resultsMore.hidden = state.total <= shown;
    els.loadMore.disabled = false;
    els.loadMore.textContent = '加载更多';
    updateTopbarTitle();
  }

  function createResultCard(item) {
    const card = el('div', 'result-card');
    card.setAttribute('role', 'button');
    card.setAttribute('tabindex', '0');
    card.dataset.id = String(item.id);

    const main = el('div', 'result-main');
    const title = el('div', 'result-title');
    appendHighlighted(title, item.title || '', state.query);
    const meta = el('div', 'result-meta');
    meta.appendChild(el('span', '', item.dynasty || ''));
    if (item.dynasty && item.author) meta.appendChild(el('span', 'meta-dot', '·'));
    meta.appendChild(el('span', '', item.author || ''));
    main.appendChild(title);
    main.appendChild(meta);

    const excerpt = el('p', 'result-excerpt', item.excerpt || '');
    card.appendChild(main);
    card.appendChild(excerpt);
    return card;
  }

  function appendHighlighted(container, text, query) {
    if (!query || !text) {
      container.appendChild(document.createTextNode(text));
      return;
    }
    const lowerText = text.toLowerCase();
    const lowerQuery = query.toLowerCase();
    let cursor = 0;
    while (cursor < text.length) {
      const hit = lowerText.indexOf(lowerQuery, cursor);
      if (hit < 0) {
        container.appendChild(document.createTextNode(text.slice(cursor)));
        break;
      }
      if (hit > cursor) container.appendChild(document.createTextNode(text.slice(cursor, hit)));
      const mark = el('mark', '', text.slice(hit, hit + query.length));
      container.appendChild(mark);
      cursor = hit + query.length;
    }
  }

  // ---------- 阅读页 ----------

  function showDetailView() {
    state.homeScroll = window.scrollY || 0;
    els.homeView.hidden = true;
    els.detailView.hidden = false;
    els.detailLoading.hidden = false;
    els.detailArticle.hidden = true;
    els.exportTextButton.disabled = true;
    els.exportPdfButton.disabled = true;
    setTopbarTitle('诗笺');
    window.scrollTo(0, 0);
  }

  function showHomeView() {
    els.detailView.hidden = true;
    els.homeView.hidden = false;
    document.title = '诗笺 · 古诗文查询与笺注';
    updateTopbarTitle();
    window.requestAnimationFrame(() => {
      window.scrollTo({ top: state.homeScroll || 0, behavior: 'auto' });
      if (!els.searchInput.disabled) els.searchInput.focus({ preventScroll: true });
    });
  }

  async function openPoem(id) {
    if (!id) return;
    const token = ++state.detailToken;
    state.detailId = id;
    state.detail = null;
    showDetailView();

    try {
      const result = await callApi('get_detail', id);
      if (token !== state.detailToken) return;
      if (!result || !result.ok) {
        throw new Error(result && result.error ? result.error : '读取诗文失败');
      }
      state.detail = result.document;
      normalizeMode();
      renderDetail();
      els.exportTextButton.disabled = false;
      els.exportPdfButton.disabled = false;
    } catch (error) {
      if (token !== state.detailToken) return;
      showToast(error.message || '读取诗文失败', { type: 'error' });
      showHomeView();
    }
  }

  function normalizeMode() {
    if (!state.detail) return;
    if (state.mode !== 'full' && state.mode !== 'original' && state.mode !== 'translation') {
      state.mode = 'full';
    }
  }

  function renderDetail() {
    const documentData = state.detail;
    if (!documentData) return;

    document.title = documentData.poem.title + ' · 诗笺';
    setTopbarTitle(documentData.poem.title);
    els.poemDynasty.textContent = documentData.poem.dynasty || '';
    els.poemAuthor.textContent = documentData.poem.author || '';
    els.poemNoteCount.textContent = documentData.annotation.note_count > 0
      ? documentData.annotation.note_count + ' 条笺注'
      : '无笺注';

    renderTitle();
    renderTitleNotes();
    renderModeTabs();
    renderAnnotationStatus();
    renderReading();
    renderAppendix();

    els.detailLoading.hidden = true;
    els.detailArticle.hidden = false;
  }

  function renderTitle() {
    const documentData = state.detail;
    const full = state.mode === 'full';
    clear(els.poemTitle);
    if (full && documentData.title_notes && documentData.title_notes.length) {
      renderAnnotatedText(
        els.poemTitle,
        documentData.poem.title,
        documentData.title_references,
        'title',
        documentData.title_notes
      );
    } else {
      els.poemTitle.textContent = documentData.poem.title;
    }
  }

  function renderTitleNotes() {
    const documentData = state.detail;
    const full = state.mode === 'full';
    const notes = documentData.title_notes || [];
    if (!full || notes.length === 0) {
      els.titleNotesBlock.hidden = true;
      clear(els.titleNotesList);
      return;
    }
    els.titleNotesBlock.hidden = false;
    renderNoteList(els.titleNotesList, notes, 'title');
  }

  function renderModeTabs() {
    const documentData = state.detail;
    els.modeButtons.forEach((button) => {
      const mode = button.dataset.mode;
      const active = mode === state.mode;
      button.classList.toggle('is-active', active);
      button.setAttribute('aria-selected', active ? 'true' : 'false');
      button.classList.remove('is-disabled');
      button.removeAttribute('aria-disabled');
      button.title = '';
    });
  }

  function renderAnnotationStatus() {
    const annotation = state.detail.annotation;
    let label = '无笺注';
    let className = 'status-pill is-empty';

    if (annotation.state === 'ok') {
      if (annotation.note_count > 0) {
        label = '已笺注 · ' + annotation.note_count + ' 条';
        if (state.detail.appendix && state.detail.appendix.length) {
          label += ' · 附注 ' + state.detail.appendix.length + ' 条';
        }
      } else if (state.detail.appendix && state.detail.appendix.length) {
        label = '附注 · ' + state.detail.appendix.length + ' 条';
      }
      className = 'status-pill is-ok';
    }

    els.annotationPill.textContent = label;
    els.annotationPill.className = className;
  }

  function renderReading() {
    const documentData = state.detail;
    const full = state.mode === 'full';
    const includeTranslation = state.mode !== 'original';
    clear(els.reading);

    if (!documentData.sections || documentData.sections.length === 0) {
      els.reading.appendChild(el('div', 'empty-reading', '这篇诗文的正文为空。'));
      return;
    }

    let paragraphIndex = 0;
    documentData.sections.forEach((section) => {
      const sectionEl = el('div', 'reading-section');
      sectionEl.dataset.kind = section.kind;

      if (section.kind === 'paired' || section.kind === 'single') {
        section.paragraphs.forEach((paragraph) => {
          const key = 'p' + (paragraphIndex++);
          sectionEl.appendChild(renderParagraph(
            paragraph,
            key,
            includeTranslation,
            full,
            includeTranslation ? section.translations : []
          ));
        });
      } else {
        section.paragraphs.forEach((paragraph) => {
          const key = 'p' + (paragraphIndex++);
          sectionEl.appendChild(renderParagraph(paragraph, key, false, full, []));
        });

        if (includeTranslation && section.translations && section.translations.length) {
          const wrap = el('div', 'section-translation');
          const block = el('div', 'translation-block');
          section.translations.forEach((text) => {
            block.appendChild(el('p', 'translation-text', text));
          });
          wrap.appendChild(block);
          sectionEl.appendChild(wrap);
        }
      }

      els.reading.appendChild(sectionEl);
    });
  }

  function renderParagraph(paragraph, key, includeTranslation, includeNotes, translations) {
    const block = el('div', 'paragraph-block');
    block.dataset.para = key;

    const original = el('p', 'original-text');
    if (includeNotes) {
      renderAnnotatedText(original, paragraph.plain, paragraph.references, key, paragraph.notes);
    } else {
      original.textContent = paragraph.plain;
    }
    block.appendChild(original);

    if (includeTranslation && translations && translations.length) {
      const wrap = el('div', 'translation-block');
      translations.forEach((text) => wrap.appendChild(el('p', 'translation-text', text)));
      block.appendChild(wrap);
    }

    if (includeNotes && paragraph.notes && paragraph.notes.length) {
      const notesBlock = el('div', 'notes-block');
      const list = el('div', 'note-list');
      renderNoteList(list, paragraph.notes, key);
      notesBlock.appendChild(list);
      block.appendChild(notesBlock);
    }

    return block;
  }

  let noteTooltip = null;
  let noteTooltipHideTimer = null;

  function ensureNoteTooltip() {
    if (noteTooltip) return noteTooltip;
    noteTooltip = el('div', 'note-tooltip');
    noteTooltip.hidden = true;
    noteTooltip.setAttribute('role', 'tooltip');
    noteTooltip.addEventListener('mouseenter', cancelHideNoteTooltip);
    noteTooltip.addEventListener('mouseleave', () => scheduleHideNoteTooltip(120));
    document.body.appendChild(noteTooltip);
    return noteTooltip;
  }

  function cancelHideNoteTooltip() {
    if (noteTooltipHideTimer) {
      window.clearTimeout(noteTooltipHideTimer);
      noteTooltipHideTimer = null;
    }
  }

  function scheduleHideNoteTooltip(delay) {
    cancelHideNoteTooltip();
    noteTooltipHideTimer = window.setTimeout(() => {
      noteTooltipHideTimer = null;
      hideNoteTooltip();
    }, delay === undefined ? 280 : delay);
  }

  function hideNoteTooltip() {
    cancelHideNoteTooltip();
    if (noteTooltip) noteTooltip.hidden = true;
  }

  function showNoteTooltip(anchor, note) {
    if (!note) return;
    cancelHideNoteTooltip();
    const tooltip = ensureNoteTooltip();
    clear(tooltip);
    if (note.label) tooltip.appendChild(el('div', 'note-tooltip-label', note.label));
    tooltip.appendChild(el('div', 'note-tooltip-text', note.text || ''));
    tooltip.hidden = false;
    tooltip.style.visibility = 'hidden';
    tooltip.style.left = '0px';
    tooltip.style.top = '0px';

    const anchorRect = anchor.getBoundingClientRect();
    const tooltipRect = tooltip.getBoundingClientRect();
    let left = anchorRect.left + anchorRect.width / 2 - tooltipRect.width / 2;
    left = Math.max(12, Math.min(window.innerWidth - tooltipRect.width - 12, left));
    let top = anchorRect.bottom + 8;
    if (top + tooltipRect.height > window.innerHeight - 12) {
      top = Math.max(12, anchorRect.top - tooltipRect.height - 8);
    }
    tooltip.style.left = left + 'px';
    tooltip.style.top = top + 'px';
    tooltip.style.visibility = '';
  }

  function attachNoteInteractions(node, note, paragraphKey, number) {
    if (!note) return;
    node.addEventListener('mouseenter', () => showNoteTooltip(node, note));
    node.addEventListener('mouseleave', () => scheduleHideNoteTooltip(280));
    node.addEventListener('focus', () => showNoteTooltip(node, note));
    node.addEventListener('blur', () => scheduleHideNoteTooltip(180));
    node.addEventListener('click', (event) => {
      event.stopPropagation();
      hideNoteTooltip();
      focusNote(paragraphKey, number, true);
    });
    node.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        hideNoteTooltip();
        focusNote(paragraphKey, number, true);
      }
    });
  }

  function renderAnnotatedText(container, plain, references, paragraphKey, notes) {
    const noteMap = new Map();
    (notes || []).forEach((note) => {
      if (note.number > 0) noteMap.set(String(note.number), note);
    });

    const refs = (references || [])
      .map((item) => ({
        number: item.number,
        start: Math.max(0, Math.min(plain.length, item.start)),
        end: Math.max(0, Math.min(plain.length, item.end))
      }))
      .filter((item) => item.end > item.start)
      .sort((a, b) => (a.start - b.start) || (a.end - b.end) || (a.number - b.number));

    if (refs.length === 0) {
      container.textContent = plain;
      return;
    }

    const points = new Set([0, plain.length]);
    refs.forEach((item) => {
      points.add(item.start);
      points.add(item.end);
    });
    const ordered = Array.from(points).sort((a, b) => a - b);

    for (let index = 0; index < ordered.length - 1; index++) {
      const start = ordered[index];
      const end = ordered[index + 1];
      if (end > start) {
        const active = refs.filter((item) => item.start <= start && item.end >= end);
        const chunk = plain.slice(start, end);
        if (active.length) {
          const term = el('span', 'ref-term', chunk);
          const first = active[0];
          term.dataset.para = paragraphKey;
          term.dataset.note = String(first.number);
          term.setAttribute('role', 'button');
          term.setAttribute('tabindex', '0');
          attachNoteInteractions(term, noteMap.get(String(first.number)), paragraphKey, first.number);
          container.appendChild(term);
        } else {
          container.appendChild(document.createTextNode(chunk));
        }
      }

      const ending = refs.filter((item) => item.end === end).sort((a, b) => a.number - b.number);
      ending.forEach((item) => {
        const note = noteMap.get(String(item.number));
        // 用 word joiner 把上标与前面的汉字绑在一起，避免行首出现孤立上标。
        container.appendChild(document.createTextNode('\u2060'));
        const ref = el('span', 'ref', superscriptNumber(item.number));
        ref.dataset.note = String(item.number);
        ref.dataset.para = paragraphKey;
        ref.setAttribute('role', 'button');
        ref.setAttribute('tabindex', '0');
        attachNoteInteractions(ref, note, paragraphKey, item.number);
        container.appendChild(ref);
        container.appendChild(document.createTextNode('\u2060'));
      });
    }
  }

  function renderNoteList(container, notes, paragraphKey) {
    clear(container);
    notes.forEach((note) => {
      const item = el('div', 'note-item');
      item.dataset.para = paragraphKey;
      item.dataset.note = String(note.number || 0);
      item.setAttribute('role', 'button');
      item.setAttribute('tabindex', '0');

      const number = el('span', 'note-number', note.number > 0 ? String(note.number) : '');
      const body = el('span', 'note-body');
      if (note.label) {
        body.appendChild(el('span', 'note-label', note.label));
        if (note.text && !/[：:]$/.test(note.label)) {
          body.appendChild(document.createTextNode('：'));
        }
      }
      body.appendChild(el('span', 'note-text', note.text || ''));
      item.appendChild(number);
      item.appendChild(body);

      item.addEventListener('click', () => focusNote(paragraphKey, note.number, false));
      item.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          focusNote(paragraphKey, note.number, false);
        }
      });
      container.appendChild(item);
    });
  }

  function focusNote(paragraphKey, number, fromRef) {
    if (!number) return;
    hideNoteTooltip();
    const suffix = '[data-para="' + paragraphKey + '"][data-note="' + number + '"]';
    const refs = qsa('.ref' + suffix);
    const notes = qsa('.note-item' + suffix);

    refs.forEach((node) => node.classList.add('is-active'));
    notes.forEach((node) => node.classList.add('is-hit'));

    const target = fromRef ? notes[0] : refs[0];
    if (target && target.scrollIntoView) {
      target.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }

    window.setTimeout(() => {
      refs.forEach((node) => node.classList.remove('is-active'));
      notes.forEach((node) => node.classList.remove('is-hit'));
    }, 1700);
  }

  function renderAppendix() {
    const documentData = state.detail;
    const full = state.mode === 'full';
    const appendix = documentData.appendix || [];
    if (!full || appendix.length === 0) {
      els.appendixBlock.hidden = true;
      clear(els.appendixList);
      return;
    }
    els.appendixBlock.hidden = false;
    renderNoteList(els.appendixList, appendix, 'appendix');
  }

  function setMode(mode) {
    if (!state.detail) return;
    if (MODES.indexOf(mode) < 0 || state.mode === mode) return;
    state.mode = mode;
    try { localStorage.setItem(STORAGE_MODE, mode); } catch (error) { /* ignore */ }
    renderTitle();
    renderTitleNotes();
    renderModeTabs();
    renderReading();
    renderAppendix();
  }

  // ---------- 导出 ----------

  function setExportButtonsBusy(busy, label) {
    state.exporting = busy;
    els.exportTextButton.disabled = busy;
    els.exportPdfButton.disabled = busy;
    if (busy) {
      els.exportPdfButton.textContent = label || '生成中…';
    } else {
      els.exportPdfButton.textContent = '导出 PDF';
    }
  }

  async function runTextExport(style) {
    if (!state.detail || state.exporting) return;
    setExportButtonsBusy(true, '导出 PDF');
    try {
      const result = await callApi('export_text', state.detail.poem.id, style);
      if (!result || !result.ok) throw new Error(result && result.error ? result.error : '导出失败');
      showExportToast(result);
    } catch (error) {
      showToast(error.message || '导出文本失败', { type: 'error', duration: 7000 });
    } finally {
      setExportButtonsBusy(false);
    }
  }

  function showTextDialog() {
    if (!state.detail) return;
    const body = document.createDocumentFragment();
    body.appendChild(el('p', 'modal-copy', '阅读版按原文、译文、段末笺注的顺序排列，与阅读页一致；标准版是分节整理稿。'));

    const list = el('div', 'choice-list');
    const options = [
      {
        value: 'reading',
        title: '阅读版',
        desc: '原文带行内上标，译文随后，本段注释集中成一行。'
      },
      {
        value: 'standard',
        title: '标准版',
        desc: '标题、朝代、作者，以及【原文】【译文】【注释】分节。'
      }
    ];
    let selected = 'reading';
    options.forEach((option) => {
      const label = el('label', 'choice-card');
      if (option.value === selected) label.classList.add('is-selected');
      const input = document.createElement('input');
      input.type = 'radio';
      input.name = 'txt-style';
      input.value = option.value;
      input.checked = option.value === selected;
      const copy = el('span', 'choice-copy');
      copy.appendChild(el('strong', '', option.title));
      copy.appendChild(el('span', '', option.desc));
      label.appendChild(input);
      label.appendChild(copy);
      input.addEventListener('change', () => {
        qsa('.choice-card', list).forEach((card) => card.classList.remove('is-selected'));
        label.classList.add('is-selected');
      });
      list.appendChild(label);
    });
    body.appendChild(list);

    const getSelected = () => {
      const checked = list.querySelector('input[name="txt-style"]:checked');
      return checked ? checked.value : 'reading';
    };

    createModal({
      kicker: '导出',
      title: '导出为 TXT',
      body: body,
      actions: [
        { label: '取消' },
        {
          label: '开始导出',
          primary: true,
          onClick: () => runTextExport(getSelected())
        }
      ]
    });
  }

  async function runPdfExport(mode, noBackground) {
    if (!state.detail || state.exporting) return;
    setExportButtonsBusy(true, '生成中…');
    const progress = showToast('正在生成 PDF，请稍候…', { type: 'info', duration: 0 });
    try {
      const result = await callApi(
        'export_pdf',
        state.detail.poem.id,
        mode,
        state.settings,
        !noBackground
      );
      if (!result || !result.ok) throw new Error(result && result.error ? result.error : '导出失败');
      showExportToast(result);
    } catch (error) {
      showToast(error.message || '导出 PDF 失败', { type: 'error', duration: 8000 });
    } finally {
      if (progress) progress.remove();
      setExportButtonsBusy(false);
    }
  }

  function showExportToast(result) {
    const name = basename(result.path);
    const extra = result.overwritten ? '（已覆盖同名文件）' : '';
    showToast('已导出 ' + name + extra, {
      type: 'success',
      duration: 7000,
      actionLabel: '打开文件',
      onAction: () => openPath(result.path)
    });
  }

  function showPdfDialog() {
    if (!state.detail) return;
    const body = document.createDocumentFragment();
    body.appendChild(
      el(
        'p',
        'modal-copy',
        '选择 PDF 的呈现方式。版式会沿用阅读页的字体与主题色；打印时可勾选不铺背景，减少墨水消耗。'
      )
    );

    const list = el('div', 'choice-list');
    const options = [
      {
        value: 'original',
        title: '仅原文',
        desc: '只保留正文，适合校对与摘录。',
        disabled: false
      },
      {
        value: 'translation',
        title: '原文 · 译文',
        desc: '原文与译文分段对照，不含注释。',
        disabled: false
      },
      {
        value: 'full',
        title: '全文 · 笺注',
        desc: '原文、译文与行内笺注完整呈现。',
        disabled: false
      }
    ];

    let selected = state.mode;
    if (MODES.indexOf(selected) < 0) selected = 'full';

    options.forEach((option) => {
      const label = el('label', 'choice-card');
      if (option.value === selected) label.classList.add('is-selected');
      if (option.disabled) label.classList.add('is-disabled');

      const input = document.createElement('input');
      input.type = 'radio';
      input.name = 'pdf-mode';
      input.value = option.value;
      input.checked = option.value === selected;
      input.disabled = option.disabled;

      const copy = el('span', 'choice-copy');
      copy.appendChild(el('strong', '', option.title));
      copy.appendChild(el('span', '', option.desc));
      label.appendChild(input);
      label.appendChild(copy);

      input.addEventListener('change', () => {
        qsa('.choice-card', list).forEach((card) => card.classList.remove('is-selected'));
        label.classList.add('is-selected');
      });
      list.appendChild(label);
    });

    body.appendChild(list);

    const printToggle = el('label', 'print-toggle');
    const backgroundInput = document.createElement('input');
    backgroundInput.type = 'checkbox';
    backgroundInput.name = 'pdf-no-background';
    backgroundInput.checked = false;
    const toggleCopy = el('span', 'print-toggle-copy');
    toggleCopy.appendChild(el('strong', '', '不铺页面背景'));
    toggleCopy.appendChild(el('span', '', '省墨模式，适合打印；正文、译文和笺注保持不变。'));
    printToggle.appendChild(backgroundInput);
    printToggle.appendChild(toggleCopy);
    body.appendChild(printToggle);

    const getSelected = () => {
      const checked = list.querySelector('input[name="pdf-mode"]:checked');
      return checked ? checked.value : 'translation';
    };

    createModal({
      kicker: '导出',
      title: '导出为 PDF',
      body: body,
      actions: [
        { label: '取消' },
        {
          label: '开始导出',
          primary: true,
          onClick: () => runPdfExport(getSelected(), backgroundInput.checked)
        }
      ]
    });
  }

  function commitSettings(next) {
    state.settings = next;
    if (Settings) {
      Settings.save(next);
      Settings.apply(next);
    }
    scheduleSettingsSave();
  }

  function scheduleSettingsSave() {
    if (!apiBridge()) return;
    if (state.settingsSaveTimer) window.clearTimeout(state.settingsSaveTimer);
    state.settingsSaveTimer = window.setTimeout(() => {
      state.settingsSaveTimer = null;
      saveSettingsToDisk();
    }, 220);
  }

  function flushSettingsSave() {
    if (state.settingsSaveTimer) {
      window.clearTimeout(state.settingsSaveTimer);
      state.settingsSaveTimer = null;
    }
    saveSettingsToDisk();
  }

  function saveSettingsToDisk() {
    const bridge = apiBridge();
    if (!bridge || typeof bridge.save_settings !== 'function' || !state.settings) return;
    callApi('save_settings', state.settings)
      .then((result) => {
        if (!result || !result.ok) throw new Error(result && result.error ? result.error : '无法保存配置');
        state.settingsSaveErrorShown = false;
        if (result.path) state.configPath = result.path;
      })
      .catch((error) => {
        if (state.settingsSaveErrorShown) return;
        state.settingsSaveErrorShown = true;
        showToast(error.message || '配置保存失败，请检查 config 目录权限', { type: 'error' });
      });
  }

  async function loadUserSettings() {
    if (!Settings) return;
    let stored = null;
    try {
      const result = await callApi('get_settings');
      if (result && result.ok && result.settings) {
        stored = result.settings;
        if (result.path) state.configPath = result.path;
      }
    } catch (error) {
      // 预览页或旧接口没有 get_settings，退回本地缓存。
    }
    state.settings = Object.assign({}, Settings.load(), stored || {});
    Settings.apply(state.settings);
    Settings.save(state.settings);
  }

  function openSettingsPanel() {
    if (!Settings) {
      showToast('设置组件未加载。', { type: 'error' });
      return;
    }
    let settings = Object.assign({}, state.settings || Settings.load());

    const body = document.createDocumentFragment();

    const themeSection = el('section', 'settings-section');
    themeSection.appendChild(el('h3', 'settings-label', '主题'));
    const themeGrid = el('div', 'theme-grid');
    const themeButtons = [];
    Settings.PRESETS.forEach((preset) => {
      const button = el('button', 'theme-card');
      button.type = 'button';
      button.dataset.preset = preset.id;
      const swatches = el('span', 'theme-swatches');
      [preset.accent, preset.paper, preset.card, preset.ink].forEach((color) => {
        const dot = el('span', 'theme-dot');
        dot.style.background = color;
        swatches.appendChild(dot);
      });
      const copy = el('span', 'theme-copy');
      copy.appendChild(el('strong', '', preset.name));
      copy.appendChild(el('span', '', preset.description));
      button.appendChild(swatches);
      button.appendChild(copy);
      button.addEventListener('click', () => {
        commitSettings(Settings.applyPreset(settings, preset));
        Object.assign(settings, state.settings);
        refresh();
      });
      themeButtons.push(button);
      themeGrid.appendChild(button);
    });
    themeSection.appendChild(themeGrid);

    const colorGrid = el('div', 'settings-colors');
    const colorInputs = {};
    const colorTexts = {};
    [
      ['accent', '主色'],
      ['paper', '页面背景'],
      ['card', '卡片颜色'],
      ['ink', '正文颜色']
    ].forEach(([key, label]) => {
      const field = el('label', 'color-field');
      const input = document.createElement('input');
      input.type = 'color';
      input.value = settings[key];
      const text = el('span', 'color-hex', settings[key].toUpperCase());
      field.appendChild(input);
      field.appendChild(el('span', 'color-name', label));
      field.appendChild(text);
      input.addEventListener('input', () => {
        settings[key] = input.value;
        settings.preset = 'custom';
        text.textContent = input.value.toUpperCase();
        commitSettings(settings);
        refresh();
      });
      colorInputs[key] = input;
      colorTexts[key] = text;
      colorGrid.appendChild(field);
    });
    themeSection.appendChild(colorGrid);
    body.appendChild(themeSection);

    const layoutSection = el('section', 'settings-section');
    layoutSection.appendChild(el('h3', 'settings-label', '版式'));
    const widthRow = el('label', 'setting-row');
    widthRow.appendChild(el('span', 'setting-name', '内容宽度'));
    const widthInput = document.createElement('input');
    widthInput.type = 'range';
    widthInput.min = '50';
    widthInput.max = '96';
    widthInput.step = '1';
    widthInput.value = String(settings.contentPercent);
    const widthValue = el('span', 'setting-value', settings.contentPercent + '%');
    widthRow.appendChild(widthInput);
    widthRow.appendChild(widthValue);
    widthInput.addEventListener('input', () => {
      settings.contentPercent = Number(widthInput.value);
      widthValue.textContent = settings.contentPercent + '%';
      commitSettings(settings);
    });
    layoutSection.appendChild(widthRow);
    body.appendChild(layoutSection);

    const fontSection = el('section', 'settings-section');
    fontSection.appendChild(el('h3', 'settings-label', '字体与字号'));
    const selectMap = {};
    const sizeMap = {};
    const sizeTextMap = {};
    [
      ['原文', 'originalFont', 'originalSize', 14, 30],
      ['译文', 'translationFont', 'translationSize', 12, 26],
      ['注释', 'notesFont', 'notesSize', 11, 22]
    ].forEach(([label, fontKey, sizeKey, min, max]) => {
      const row = el('div', 'font-row');
      row.appendChild(el('span', 'setting-name', label));
      const select = document.createElement('select');
      select.className = 'font-select';
      Settings.FONT_OPTIONS.forEach((option) => {
        const item = document.createElement('option');
        item.value = option.id;
        item.textContent = option.name;
        select.appendChild(item);
      });
      select.value = settings[fontKey];
      const range = document.createElement('input');
      range.type = 'range';
      range.min = String(min);
      range.max = String(max);
      range.step = '0.5';
      range.value = String(settings[sizeKey]);
      const sizeText = el('span', 'setting-value', settings[sizeKey] + 'px');
      select.addEventListener('change', () => {
        settings[fontKey] = select.value;
        commitSettings(settings);
      });
      range.addEventListener('input', () => {
        settings[sizeKey] = Number(range.value);
        sizeText.textContent = settings[sizeKey] + 'px';
        commitSettings(settings);
      });
      row.appendChild(select);
      row.appendChild(range);
      row.appendChild(sizeText);
      fontSection.appendChild(row);
      selectMap[fontKey] = select;
      sizeMap[sizeKey] = range;
      sizeTextMap[sizeKey] = sizeText;
    });
    body.appendChild(fontSection);

    function refresh() {
      const activePreset = Settings.matchPreset(settings);
      themeButtons.forEach((button) => {
        button.classList.toggle('is-active', button.dataset.preset === activePreset);
      });
      ['accent', 'paper', 'card', 'ink'].forEach((key) => {
        if (colorInputs[key]) colorInputs[key].value = settings[key];
        if (colorTexts[key]) colorTexts[key].textContent = settings[key].toUpperCase();
      });
      widthInput.value = String(settings.contentPercent);
      widthValue.textContent = settings.contentPercent + '%';
      selectMap.originalFont.value = settings.originalFont;
      selectMap.translationFont.value = settings.translationFont;
      selectMap.notesFont.value = settings.notesFont;
      sizeMap.originalSize.value = String(settings.originalSize);
      sizeMap.translationSize.value = String(settings.translationSize);
      sizeMap.notesSize.value = String(settings.notesSize);
      sizeTextMap.originalSize.textContent = settings.originalSize + 'px';
      sizeTextMap.translationSize.textContent = settings.translationSize + 'px';
      sizeTextMap.notesSize.textContent = settings.notesSize + 'px';
    }

    refresh();

    const configNote = el('p', 'settings-path', '配置保存于 config/config.json');
    if (state.configPath) configNote.title = state.configPath;
    body.appendChild(configNote);

    createModal({
      kicker: '界面',
      title: '阅读与外观',
      cardClass: 'settings-card',
      body: body,
      onClose: flushSettingsSave,
      actions: [
        {
          label: '恢复默认',
          close: false,
          onClick: () => {
            settings = Settings.defaults();
            commitSettings(settings);
            refresh();
          }
        },
        { label: '完成', primary: true, onClick: flushSettingsSave }
      ]
    });
  }

  async function openPath(path) {
    try {
      const result = await callApi('open_path', path);
      if (!result || !result.ok) throw new Error(result && result.error ? result.error : '无法打开文件');
    } catch (error) {
      showToast(error.message || '无法打开文件', { type: 'error' });
    }
  }

  async function openOutputDir() {
    try {
      const result = await callApi('open_output_dir');
      if (!result || !result.ok) throw new Error(result && result.error ? result.error : '无法打开导出目录');
    } catch (error) {
      showToast(error.message || '无法打开导出目录', { type: 'error' });
    }
  }

  // ---------- Toast / 弹窗 ----------

  function showToast(message, options) {
    const opts = options || {};
    const toast = el('div', 'toast is-' + (opts.type || 'info'));
    const iconText = opts.type === 'success' ? '✓' : opts.type === 'error' ? '!' : 'i';
    toast.appendChild(el('span', 'toast-icon', iconText));
    toast.appendChild(el('span', 'toast-copy', message));

    if (opts.actionLabel && opts.onAction) {
      const action = el('button', 'toast-action', opts.actionLabel);
      action.type = 'button';
      action.addEventListener('click', () => {
        opts.onAction();
        toast.remove();
      });
      toast.appendChild(action);
    }

    while (els.toastRegion.children.length >= 4) {
      els.toastRegion.removeChild(els.toastRegion.firstChild);
    }
    els.toastRegion.appendChild(toast);

    if (opts.duration !== 0) {
      const duration = opts.duration || 5200;
      window.setTimeout(() => {
        toast.style.opacity = '0';
        window.setTimeout(() => toast.remove(), 220);
      }, duration);
    }
    return toast;
  }

  function closeModal() {
    if (!state.modalOpen) return;
    state.modalOpen = false;
    els.modalRoot.hidden = true;
    clear(els.modalRoot);
    document.body.style.overflow = '';
    const callback = state.modalOnClose;
    state.modalOnClose = null;
    if (callback) callback();
  }

  function createModal(options) {
    closeModal();
    const body = options.body || document.createDocumentFragment();

    const card = el('div', 'modal-card');
    if (options.cardClass) card.classList.add(options.cardClass);
    if (options.kicker) card.appendChild(el('p', 'modal-kicker', options.kicker));
    if (options.title) card.appendChild(el('h2', 'modal-title', options.title));
    card.appendChild(body);

    const actions = el('div', 'modal-actions');
    (options.actions || []).forEach((action) => {
      const button = el('button', action.primary ? 'primary-button' : 'soft-button', action.label);
      button.type = 'button';
      button.addEventListener('click', () => {
        const shouldClose = action.close !== false;
        if (shouldClose) closeModal();
        if (action.onClick) action.onClick();
      });
      actions.appendChild(button);
    });
    card.appendChild(actions);

    els.modalRoot.appendChild(card);
    els.modalRoot.hidden = false;
    state.modalOpen = true;
    state.modalOnClose = options.onClose || null;
    document.body.style.overflow = 'hidden';

    const focusTarget = card.querySelector('input:not([disabled]), button');
    if (focusTarget) window.setTimeout(() => focusTarget.focus(), 40);
  }

  // ---------- 事件 ----------

  function bindEvents() {
    els.searchInput.addEventListener('compositionstart', () => {
      state.isComposing = true;
      window.clearTimeout(state.searchTimer);
    });

    els.searchInput.addEventListener('compositionend', () => {
      state.isComposing = false;
      debounceSearch();
    });

    els.searchInput.addEventListener('input', (event) => {
      if (state.isComposing || event.isComposing) return;
      debounceSearch();
    });

    els.searchInput.addEventListener('keydown', (event) => {
      if (event.isComposing || state.isComposing) return;
      if (event.key === 'Enter') {
        event.preventDefault();
        if (state.items.length) {
          openPoem(state.items[0].id);
        } else {
          const query = els.searchInput.value.trim();
          if (query) runSearch(query, true);
        }
      } else if (event.key === 'ArrowDown' && state.items.length) {
        event.preventDefault();
        const first = els.resultsList.querySelector('.result-card');
        if (first) first.focus();
      } else if (event.key === 'Escape') {
        els.searchInput.value = '';
        resetSearch();
      }
    });

    els.searchClear.addEventListener('click', () => {
      resetSearch();
      els.searchInput.focus();
    });

    els.quickRow.addEventListener('click', (event) => {
      const chip = event.target.closest('.quick-chip');
      if (!chip) return;
      const query = chip.dataset.query || '';
      els.searchInput.value = query;
      els.searchClear.hidden = !query;
      runSearch(query, true);
      els.searchInput.focus();
    });

    els.resultsList.addEventListener('click', (event) => {
      const card = event.target.closest('.result-card');
      if (card) openPoem(Number(card.dataset.id));
    });

    els.resultsList.addEventListener('keydown', (event) => {
      const card = event.target.closest('.result-card');
      if (!card) return;
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        openPoem(Number(card.dataset.id));
        return;
      }
      if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
        event.preventDefault();
        const cards = qsa('.result-card', els.resultsList);
        const index = cards.indexOf(card);
        const next = event.key === 'ArrowDown'
          ? cards[Math.min(cards.length - 1, index + 1)]
          : cards[Math.max(0, index - 1)];
        if (next) next.focus();
      }
    });

    els.loadMore.addEventListener('click', () => {
      if (!state.query || state.loadingSearch) return;
      runSearch(state.query, false);
    });

    els.modeButtons.forEach((button) => {
      button.addEventListener('click', () => setMode(button.dataset.mode));
    });

    els.backButton.addEventListener('click', showHomeView);

    els.homeButton.addEventListener('click', () => {
      if (!els.detailView.hidden) showHomeView();
      resetSearch();
      window.scrollTo({ top: 0, behavior: 'smooth' });
      if (!els.searchInput.disabled) els.searchInput.focus({ preventScroll: true });
      updateTopbarTitle();
    });

    els.settingsButton.addEventListener('click', openSettingsPanel);
    els.exportTextButton.addEventListener('click', showTextDialog);
    els.exportPdfButton.addEventListener('click', showPdfDialog);
    els.outputButton.addEventListener('click', openOutputDir);
    els.homeOutputLink.addEventListener('click', openOutputDir);
    window.addEventListener('scroll', hideNoteTooltip, true);
    window.addEventListener('resize', hideNoteTooltip);

    els.modalRoot.addEventListener('click', (event) => {
      if (event.target === els.modalRoot) closeModal();
    });

    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') {
        if (state.modalOpen) {
          closeModal();
          return;
        }
        if (!els.detailView.hidden) {
          showHomeView();
          return;
        }
      }

      if (event.key === '/' && els.detailView.hidden) {
        const active = document.activeElement;
        const tag = active ? active.tagName : '';
        if (tag !== 'INPUT' && tag !== 'TEXTAREA') {
          event.preventDefault();
          els.searchInput.focus();
        }
      }
    });

    window.addEventListener('unhandledrejection', (event) => {
      const message = event.reason && event.reason.message ? event.reason.message : '操作失败';
      showToast(message, { type: 'error' });
    });
  }

  async function loadMeta() {
    try {
      const meta = await callApi('get_meta');
      if (!meta || !meta.ok) throw new Error(meta && meta.error ? meta.error : '无法读取数据库');
      state.meta = meta;
      els.metaCount.textContent = '库中 ' + formatNumber(meta.poemCount) + ' 篇诗文';
      els.outputButton.title = '打开导出目录 · ' + meta.outputDir;
      els.homeOutputLink.title = meta.outputDir;
    } catch (error) {
      els.metaCount.textContent = '数据库尚未就绪';
    }
  }

  async function init() {
    if (state.apiReady) return;
    if (!apiBridge()) return;
    state.apiReady = true;
    els.searchInput.disabled = false;
    await loadUserSettings();
    updateTopbarTitle();

    try {
      const stored = localStorage.getItem(STORAGE_MODE);
      if (MODES.indexOf(stored) >= 0) state.mode = stored;
    } catch (error) { /* ignore */ }

    bindEvents();
    await loadMeta();

    const preview = window.__PREVIEW__;
    if (preview) {
      if (preview.query) {
        els.searchInput.value = preview.query;
        els.searchClear.hidden = false;
        await runSearch(preview.query, true);
      }
      if (preview.view === 'detail' && preview.poemId) {
        await openPoem(preview.poemId);
      }
      return;
    }

    window.setTimeout(() => els.searchInput.focus({ preventScroll: true }), 280);
  }

  if (window.pywebview && window.pywebview.api) {
    init();
  } else {
    window.addEventListener('pywebviewready', init, { once: true });
  }

  window.setTimeout(() => {
    if (!state.apiReady) {
      els.metaCount.textContent = '未连接到应用接口';
      els.searchInput.disabled = true;
      showToast('请通过 python app.pyw 启动诗笺，浏览器直接打开时接口不可用。', {
        type: 'error',
        duration: 9000
      });
    }
  }, 6500);
})();
