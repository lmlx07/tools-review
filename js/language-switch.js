/**
 * Language Switch — Custom Google Translate integration
 * Uses translate.googleapis.com directly (no widget, no branding)
 * Free, client-side, no API key required
 */
(function () {
  'use strict';

  const STORE_KEY = 'lng_cache';

  let currentLang = localStorage.getItem('lng_current') || 'zh-CN';
  let busy = false;

  // ---------- cache ----------
  function loadCache() {
    try {
      return JSON.parse(localStorage.getItem(STORE_KEY) || '{}');
    } catch { return {}; }
  }
  function saveCache(c) {
    try { localStorage.setItem(STORE_KEY, JSON.stringify(c)); } catch {}
  }
  let cache = loadCache();

  // ---------- DOM helpers ----------
  function getContentRoot() {
    return document.querySelector('#article-container')
        || document.querySelector('.post-content')
        || document.querySelector('article')
        || document.querySelector('#content')
        || document.body;
  }

  /** Paragraph-level elements that hold translatable text */
  const SELECTOR = 'p, h1, h2, h3, h4, h5, h6, li, blockquote, td, th, figcaption, .post-title, .page-title';

  function getTargets(root) {
    const els = root.querySelectorAll(SELECTOR);
    return Array.from(els).filter(el => {
      if (el.closest('pre, code, .highlight, .code-block, .gist, script, style')) return false;
      const raw = el.textContent.replace(/\s+/g, '').trim();
      return raw.length >= 2;
    });
  }

  /** Walk direct child text nodes of an element */
  function getTextNodes(el) {
    const nodes = [];
    for (let i = 0; i < el.childNodes.length; i++) {
      if (el.childNodes[i].nodeType === Node.TEXT_NODE) {
        const t = el.childNodes[i].textContent.trim();
        if (t.length > 0) nodes.push(el.childNodes[i]);
      }
    }
    return nodes;
  }

  // ---------- translate API ----------
  async function translate(text, from = 'zh-CN', to = 'en') {
    const key = `${from}_${to}_${text}`;
    if (cache[key]) return cache[key];

    const url = 'https://translate.googleapis.com/translate_a/single'
      + `?client=gtx&sl=${from}&tl=${to}&dt=t`
      + '&q=' + encodeURIComponent(text);

    const res = await fetch(url);
    const data = await res.json();

    // data[0] = [[translated, original, ...], ...]
    const result = data[0].map(p => p[0]).join('');
    cache[key] = result;
    saveCache(cache);
    return result;
  }

  // ---------- apply translations ----------
  function applyEn(elements, translations) {
    elements.forEach((el, i) => {
      const translated = translations[i];
      if (!translated) return;

      // Store original HTML (only once)
      if (!el.hasAttribute('data-lng-orig')) {
        el.setAttribute('data-lng-orig', el.innerHTML);
      }

      const textNodes = getTextNodes(el);
      if (textNodes.length > 0) {
        // Put all translated text into the first text node, clear the rest
        textNodes[0].textContent = translated;
        for (let j = 1; j < textNodes.length; j++) {
          textNodes[j].textContent = '';
        }
      } else if (el.children.length > 0) {
        // No direct text nodes — all text is in child elements
        // Replace the innermost text of deepest child
        let deepest = el;
        while (deepest.children.length > 0) {
          // Find a child that has text content
          let found = false;
          for (let k = 0; k < deepest.children.length; k++) {
            const c = deepest.children[k];
            if (c.textContent.trim().length > 0) {
              deepest = c;
              found = true;
              break;
            }
          }
          if (!found) break;
        }
        const subNodes = getTextNodes(deepest);
        if (subNodes.length > 0) {
          subNodes[0].textContent = translated;
          for (let j = 1; j < subNodes.length; j++) {
            subNodes[j].textContent = '';
          }
        } else {
          deepest.textContent = translated;
        }
      } else {
        el.textContent = translated;
      }
    });
  }

  function restoreCn() {
    const root = getContentRoot();
    root.querySelectorAll('[data-lng-orig]').forEach(el => {
      el.innerHTML = el.getAttribute('data-lng-orig');
      el.removeAttribute('data-lng-orig');
    });
  }

  // ---------- switch ----------
  async function switchTo(lang) {
    if (busy || lang === currentLang) return;
    busy = true;
    document.body.classList.add('lng-busy');

    try {
      if (lang === 'en') {
        const root = getContentRoot();
        const targets = getTargets(root);
        if (targets.length === 0) return;

        // Translate all targets in parallel
        const texts = targets.map(el => el.textContent.trim());
        const translations = await Promise.all(
          texts.map(t => translate(t, 'zh-CN', 'en'))
        );
        applyEn(targets, translations);
      } else {
        restoreCn();
      }

      currentLang = lang;
      localStorage.setItem('lng_current', lang);
      updateUI(lang);
    } catch (err) {
      console.error('[lang-switch]', err);
    } finally {
      busy = false;
      document.body.classList.remove('lng-busy');
    }
  }

  // ---------- UI ----------
  function updateUI(lang) {
    document.querySelectorAll('#lang-switch .lo').forEach(el => {
      el.classList.toggle('on', el.dataset.lang === lang);
    });
    document.documentElement.lang = lang === 'en' ? 'en' : 'zh-CN';
  }

  /** Inject lang-switch into the nav (handles PJAX re-insertion) */
  function injectNav() {
    const menu = document.querySelector('#nav .menus_items');
    const sw = document.getElementById('lang-switch');
    if (!menu || !sw) return;
    if (menu.contains(sw)) return;
    sw.style.display = 'inline-flex';
    const li = document.createElement('li');
    li.className = 'menus_item';
    li.appendChild(sw);
    menu.appendChild(li);
  }

  // ---------- init ----------
  function init() {
    // Click handler (delegated)
    document.addEventListener('click', function (e) {
      const lo = e.target.closest('#lang-switch .lo');
      if (!lo) return;
      e.stopPropagation();
      switchTo(lo.dataset.lang);
    });

    // Restore last language on page load
    if (currentLang === 'en') {
      // Delayed to let page render first, then translate
      setTimeout(() => switchTo('en'), 800);
    }

    // Nav injection on load
    setTimeout(injectNav, 500);

    // PJAX: re-inject after page transition
    document.addEventListener('pjax:complete', function () {
      setTimeout(injectNav, 500);
      if (currentLang === 'en') {
        // Re-translate new content
        setTimeout(() => switchTo('en'), 1000);
      }
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
