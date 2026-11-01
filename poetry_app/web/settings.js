(() => {
  'use strict';

  const STORAGE_KEY = 'shijian.settings.v1';

  const PRESETS = [
    {
      id: 'paper',
      name: '宣纸',
      description: '朱砂 · 暖白',
      accent: '#A4422F',
      paper: '#F7F3EA',
      card: '#FFFDF8',
      ink: '#26231E'
    },
    {
      id: 'blue',
      name: '靛蓝',
      description: '现代 · 清爽',
      accent: '#2F6BD8',
      paper: '#F3F6FB',
      card: '#FFFFFF',
      ink: '#1D2733'
    },
    {
      id: 'celadon',
      name: '青瓷',
      description: '青绿 · 温润',
      accent: '#3D7A6A',
      paper: '#F3F6F1',
      card: '#FFFEFA',
      ink: '#25302C'
    },
    {
      id: 'sand',
      name: '暖沙',
      description: '赭石 · 柔和',
      accent: '#B06A3B',
      paper: '#F8F3EA',
      card: '#FFFDF7',
      ink: '#2C261F'
    }
  ];

  const FONT_OPTIONS = [
    {
      id: 'song',
      name: '宋体 / 思源宋体',
      stack: '"Source Han Serif SC", "Noto Serif SC", "Songti SC", "STSong", "SimSun", serif'
    },
    {
      id: 'kai',
      name: '楷体',
      stack: '"STKaiti", "KaiTi", "Kaiti SC", "STSong", serif'
    },
    {
      id: 'fangsong',
      name: '仿宋',
      stack: '"FangSong", "STFangsong", "SimFang", "STSong", serif'
    },
    {
      id: 'hei',
      name: '黑体 / 微软雅黑',
      stack: '"Microsoft YaHei UI", "Microsoft YaHei", "PingFang SC", "Noto Sans SC", sans-serif'
    },
    {
      id: 'deng',
      name: '等线',
      stack: '"DengXian", "Microsoft YaHei UI", sans-serif'
    }
  ];

  const DEFAULT_SETTINGS = {
    preset: 'paper',
    accent: '#A4422F',
    paper: '#F7F3EA',
    card: '#FFFDF8',
    ink: '#26231E',
    contentPercent: 72,
    originalFont: 'song',
    translationFont: 'song',
    notesFont: 'song',
    originalSize: 19.5,
    translationSize: 16.5,
    notesSize: 14.5
  };

  function normalizeHex(value, fallback) {
    const text = String(value || '').trim();
    if (/^#[0-9a-fA-F]{6}$/.test(text)) return text.toLowerCase();
    if (/^#[0-9a-fA-F]{3}$/.test(text)) {
      return '#' + text.slice(1).split('').map((char) => char + char).join('').toLowerCase();
    }
    return fallback;
  }

  function hexToRgb(hex) {
    const value = normalizeHex(hex, '#000000').slice(1);
    return {
      r: parseInt(value.slice(0, 2), 16),
      g: parseInt(value.slice(2, 4), 16),
      b: parseInt(value.slice(4, 6), 16)
    };
  }

  function mix(hexA, hexB, amountB) {
    const a = hexToRgb(hexA);
    const b = hexToRgb(hexB);
    const weight = Math.max(0, Math.min(1, Number(amountB) || 0));
    const channel = (left, right) => Math.round(left * (1 - weight) + right * weight);
    return '#' + [channel(a.r, b.r), channel(a.g, b.g), channel(a.b, b.b)]
      .map((value) => value.toString(16).padStart(2, '0'))
      .join('');
  }

  function rgbText(hex) {
    const value = hexToRgb(hex);
    return value.r + ', ' + value.g + ', ' + value.b;
  }

  function numberInRange(value, fallback, min, max) {
    const number = Number(value);
    if (!Number.isFinite(number)) return fallback;
    return Math.min(max, Math.max(min, number));
  }

  function fontStack(id) {
    const option = FONT_OPTIONS.find((item) => item.id === id);
    return option ? option.stack : FONT_OPTIONS[0].stack;
  }

  function defaults() {
    return Object.assign({}, DEFAULT_SETTINGS);
  }

  function load() {
    let stored = null;
    try {
      stored = JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null');
    } catch (error) {
      stored = null;
    }
    const settings = Object.assign({}, DEFAULT_SETTINGS, stored || {});
    settings.preset = String(settings.preset || 'custom');
    settings.accent = normalizeHex(settings.accent, DEFAULT_SETTINGS.accent);
    settings.paper = normalizeHex(settings.paper, DEFAULT_SETTINGS.paper);
    settings.card = normalizeHex(settings.card, DEFAULT_SETTINGS.card);
    settings.ink = normalizeHex(settings.ink, DEFAULT_SETTINGS.ink);
    settings.contentPercent = numberInRange(settings.contentPercent, DEFAULT_SETTINGS.contentPercent, 50, 96);
    settings.originalFont = FONT_OPTIONS.some((item) => item.id === settings.originalFont)
      ? settings.originalFont : DEFAULT_SETTINGS.originalFont;
    settings.translationFont = FONT_OPTIONS.some((item) => item.id === settings.translationFont)
      ? settings.translationFont : DEFAULT_SETTINGS.translationFont;
    settings.notesFont = FONT_OPTIONS.some((item) => item.id === settings.notesFont)
      ? settings.notesFont : DEFAULT_SETTINGS.notesFont;
    settings.originalSize = numberInRange(settings.originalSize, DEFAULT_SETTINGS.originalSize, 14, 30);
    settings.translationSize = numberInRange(settings.translationSize, DEFAULT_SETTINGS.translationSize, 12, 26);
    settings.notesSize = numberInRange(settings.notesSize, DEFAULT_SETTINGS.notesSize, 11, 22);
    return settings;
  }

  function save(settings) {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
    } catch (error) {
      // 隐私模式或磁盘受限时，设置只在本次运行生效。
    }
  }

  function apply(settings) {
    const root = document.documentElement;
    const accent = normalizeHex(settings.accent, DEFAULT_SETTINGS.accent);
    const paper = normalizeHex(settings.paper, DEFAULT_SETTINGS.paper);
    const card = normalizeHex(settings.card, DEFAULT_SETTINGS.card);
    const ink = normalizeHex(settings.ink, DEFAULT_SETTINGS.ink);
    const accentRgb = rgbText(accent);
    const paperRgb = rgbText(paper);
    const cardRgb = rgbText(card);
    const inkRgb = rgbText(ink);

    root.style.setProperty('--accent', accent);
    root.style.setProperty('--accent-rgb', accentRgb);
    root.style.setProperty('--accent-deep', mix(accent, '#000000', 0.24));
    root.style.setProperty('--accent-soft', mix(accent, '#FFFFFF', 0.84));
    root.style.setProperty('--accent-faint', mix(accent, '#FFFFFF', 0.94));
    root.style.setProperty('--paper', paper);
    root.style.setProperty('--paper-rgb', paperRgb);
    root.style.setProperty('--paper-deep', mix(paper, ink, 0.055));
    root.style.setProperty('--card', card);
    root.style.setProperty('--card-rgb', cardRgb);
    root.style.setProperty('--card-soft', 'rgba(' + cardRgb + ', 0.72)');
    root.style.setProperty('--ink', ink);
    root.style.setProperty('--ink-rgb', inkRgb);
    root.style.setProperty('--ink-soft', mix(ink, paper, 0.18));
    root.style.setProperty('--muted', mix(ink, paper, 0.48));
    root.style.setProperty('--muted-light', mix(ink, paper, 0.64));
    root.style.setProperty('--line', mix(ink, paper, 0.86));
    root.style.setProperty('--line-strong', mix(ink, paper, 0.72));
    root.style.setProperty('--content-percent', String(settings.contentPercent));
    root.style.setProperty('--content-width', settings.contentPercent + 'vw');
    root.style.setProperty('--font-original', fontStack(settings.originalFont));
    root.style.setProperty('--font-translation', fontStack(settings.translationFont));
    root.style.setProperty('--font-notes', fontStack(settings.notesFont));
    root.style.setProperty('--size-original', settings.originalSize + 'px');
    root.style.setProperty('--size-translation', settings.translationSize + 'px');
    root.style.setProperty('--size-notes', settings.notesSize + 'px');
  }

  function presetById(id) {
    return PRESETS.find((item) => item.id === id) || null;
  }

  function applyPreset(settings, preset) {
    const next = Object.assign({}, settings, {
      preset: preset.id,
      accent: preset.accent,
      paper: preset.paper,
      card: preset.card,
      ink: preset.ink
    });
    return next;
  }

  function matchPreset(settings) {
    const found = PRESETS.find((preset) => (
      preset.accent.toLowerCase() === String(settings.accent).toLowerCase()
      && preset.paper.toLowerCase() === String(settings.paper).toLowerCase()
      && preset.card.toLowerCase() === String(settings.card).toLowerCase()
      && preset.ink.toLowerCase() === String(settings.ink).toLowerCase()
    ));
    return found ? found.id : 'custom';
  }

  const api = {
    PRESETS,
    FONT_OPTIONS,
    DEFAULT_SETTINGS,
    defaults,
    load,
    save,
    apply,
    presetById,
    applyPreset,
    matchPreset,
    fontStack,
    normalizeHex,
    mix
  };

  window.ShijianSettings = api;

  try {
    apply(load());
  } catch (error) {
    // 极端情况下仍使用 CSS 默认值。
  }
})();
