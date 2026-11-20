/* pka-skills walkthrough: one screen at a time, addressed by the URL hash.
   Without this script the page is a single long document and every link still works. */
(function () {
  'use strict';

  var doc = document;
  var root = doc.documentElement;
  var screens = Array.prototype.slice.call(doc.querySelectorAll('section.screen'));
  if (!screens.length) { return; }

  var ids = screens.map(function (s) { return s.id; });
  var toc = doc.getElementById('toc');
  var tocToggle = doc.getElementById('toc-toggle');
  var tocClose = doc.getElementById('toc-close');
  var tocLinks = Array.prototype.slice.call(toc.querySelectorAll('a[href^="#"]'));
  var back = doc.getElementById('nav-back');
  var next = doc.getElementById('nav-next');
  var whereText = doc.getElementById('where-text');
  var meter = doc.getElementById('meter');
  var meterFill = doc.getElementById('meter-fill');
  var baseTitle = doc.title;
  var wide = window.matchMedia('(min-width: 66rem)');
  var current = -1;

  root.classList.add('js');
  meter.setAttribute('aria-valuemax', String(screens.length));

  function titleOf(i) {
    return screens[i].getAttribute('data-title') || screens[i].id;
  }

  /* The screen a hash points at: a screen id, or any element inside a screen. */
  function indexFromHash(hash) {
    var id = hash.replace(/^#/, '');
    try { id = decodeURIComponent(id); } catch (e) { /* keep as typed */ }
    if (!id) { return 0; }
    var i = ids.indexOf(id);
    if (i !== -1) { return i; }
    var el = doc.getElementById(id);
    var parent = el && el.closest ? el.closest('section.screen') : null;
    return parent ? ids.indexOf(parent.id) : 0;
  }

  function setLink(a, i, labelPrefix) {
    var label = a.querySelector('span');
    if (i < 0 || i >= screens.length) {
      a.setAttribute('aria-disabled', 'true');
      a.setAttribute('tabindex', '-1');
      a.removeAttribute('href');
      a.setAttribute('aria-label', labelPrefix + ': none');
      label.textContent = labelPrefix;
      return;
    }
    a.removeAttribute('aria-disabled');
    a.removeAttribute('tabindex');
    a.setAttribute('href', '#' + ids[i]);
    a.setAttribute('aria-label', labelPrefix + ': ' + titleOf(i));
    label.textContent = labelPrefix === 'Next' ? titleOf(i) : 'Back';
  }

  /* Wide blocks scroll inside themselves; make the ones that do reachable by keyboard. */
  function markScrollers(scope) {
    Array.prototype.forEach.call(scope.querySelectorAll('pre, .scroller'), function (el) {
      if (el.scrollWidth > el.clientWidth + 1) {
        el.setAttribute('tabindex', '0');
        el.setAttribute('role', 'region');
        if (!el.getAttribute('aria-label')) {
          el.setAttribute('aria-label', 'Example, scrolls sideways');
        }
        el.setAttribute('data-scrolls', '');
      } else if (el.hasAttribute('data-scrolls')) {
        el.removeAttribute('tabindex');
        el.removeAttribute('role');
        el.removeAttribute('data-scrolls');
      }
    });
  }

  function show(i, moveFocus) {
    if (i < 0 || i >= screens.length) { i = 0; }
    var changed = i !== current;
    current = i;

    screens.forEach(function (s, n) { s.hidden = n !== i; });

    var n = i + 1;
    var total = screens.length;
    whereText.innerHTML = '';
    whereText.appendChild(doc.createTextNode(n + ' of ' + total + ' · '));
    var b = doc.createElement('b');
    b.textContent = titleOf(i);
    whereText.appendChild(b);
    meter.setAttribute('aria-valuenow', String(n));
    meter.setAttribute('aria-valuetext', 'Screen ' + n + ' of ' + total + ': ' + titleOf(i));
    meterFill.style.width = (n / total * 100) + '%';

    setLink(back, i - 1, 'Back');
    setLink(next, i + 1, 'Next');

    tocLinks.forEach(function (a) {
      if (a.getAttribute('href') === '#' + ids[i]) {
        a.setAttribute('aria-current', 'page');
      } else {
        a.removeAttribute('aria-current');
      }
    });

    doc.title = i === 0 ? baseTitle : titleOf(i) + ' · ' + baseTitle;
    markScrollers(screens[i]);

    if (changed && moveFocus) {
      window.scrollTo(0, 0);
      var h = screens[i].querySelector('h2');
      if (h) {
        try { h.focus({ preventScroll: true }); } catch (e) { h.focus(); }
      }
    }
  }

  function go(i) {
    if (i < 0 || i >= screens.length || i === current) { return; }
    /* Setting the hash adds a history entry, so the browser's Back button returns here. */
    window.location.hash = ids[i];
  }

  /* ----- contents drawer (narrow windows) ----- */

  function tocOpen() { return toc.classList.contains('open'); }

  function setToc(open, returnFocus) {
    toc.classList.toggle('open', open);
    tocToggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    if (open) {
      var cur = toc.querySelector('a[aria-current="page"]') || tocLinks[0];
      if (cur) { cur.focus(); }
    } else if (returnFocus) {
      tocToggle.focus();
    }
  }

  tocToggle.addEventListener('click', function () { setToc(!tocOpen(), true); });
  tocClose.addEventListener('click', function () { setToc(false, true); });

  toc.addEventListener('click', function (e) {
    var a = e.target.closest ? e.target.closest('a[href^="#"]') : null;
    if (!a) { return; }
    if (tocOpen()) { setToc(false, false); }
    /* Choosing the screen already shown fires no hashchange: still move to its heading. */
    if (a.getAttribute('href') === '#' + ids[current]) {
      var h = screens[current].querySelector('h2');
      if (h) { h.focus(); }
    }
  });

  doc.addEventListener('click', function (e) {
    if (tocOpen() && !toc.contains(e.target) && !tocToggle.contains(e.target)) {
      setToc(false, false);
    }
  });

  function onWide() { if (wide.matches && tocOpen()) { setToc(false, false); } }
  if (wide.addEventListener) { wide.addEventListener('change', onWide); }
  else if (wide.addListener) { wide.addListener(onWide); }

  /* ----- keys ----- */

  doc.addEventListener('keydown', function (e) {
    if (e.defaultPrevented || e.altKey || e.ctrlKey || e.metaKey || e.shiftKey) { return; }
    if (e.key === 'Escape' && tocOpen()) {
      setToc(false, true);
      return;
    }
    if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') { return; }
    var t = e.target;
    if (t && t.closest) {
      /* Leave the arrows alone where they already mean something. */
      if (t.closest('input, textarea, select, [contenteditable="true"], [data-scrolls]')) { return; }
      if (tocOpen()) { return; }
    }
    e.preventDefault();
    go(current + (e.key === 'ArrowRight' ? 1 : -1));
  });

  window.addEventListener('hashchange', function () {
    show(indexFromHash(window.location.hash), true);
  });

  var resizeTimer = null;
  window.addEventListener('resize', function () {
    window.clearTimeout(resizeTimer);
    resizeTimer = window.setTimeout(function () {
      if (current >= 0) { markScrollers(screens[current]); }
    }, 150);
  });

  show(indexFromHash(window.location.hash), false);
  /* A link straight to something inside a screen: bring it into view once the screen is shown. */
  if (window.location.hash && ids.indexOf(window.location.hash.slice(1)) === -1) {
    var target = doc.getElementById(window.location.hash.slice(1));
    if (target && target.scrollIntoView) { target.scrollIntoView(); }
  }
})();
