// Character sheet table of contents: highlights the section you're currently
// looking at, and keeps its order in step with a drag-reorder of the sections.
//
// The links are plain in-page anchors (href="#section-<key>"), so jumping works
// with JS off; everything here is enhancement. Section elements are found by
// their [data-section] key rather than by their htmx id, and positions are read
// fresh on every update, so htmx swapping a section out changes nothing.
(function () {
  var list = document.querySelector('[data-toc="sections"]');
  if (!list) return;

  // How far below the top of the reading area (see readingTop) a section's start
  // must be before it counts as the one being read. Roughly one heading's worth
  // of slack.
  var ACTIVE_OFFSET = 96;
  var header = document.querySelector('header');
  // The key last brought into view in the narrow-screen bar (see revealCurrent).
  var revealedKey = null;

  function entries() {
    return Array.prototype.slice.call(list.querySelectorAll('[data-toc-key]'));
  }

  function sections() {
    return Array.prototype.slice.call(document.querySelectorAll('[data-section]'));
  }

  function setCurrent(key) {
    entries().forEach(function (entry) {
      var link = entry.querySelector('a');
      if (!link) return;
      if (entry.dataset.tocKey === key) {
        link.setAttribute('aria-current', 'true');
      } else {
        link.removeAttribute('aria-current');
      }
    });
  }

  // Where the reading area starts: below the sticky site header, and below the
  // contents too when they are a bar across the top of the sheet (narrow screens)
  // rather than a rail beside it, told apart by whether they overlap the sections
  // horizontally.
  function readingTop(firstSection) {
    var top = header ? header.getBoundingClientRect().bottom : 0;
    var contents = list.getBoundingClientRect();
    if (contents.right > firstSection.getBoundingClientRect().left) {
      top = Math.max(top, contents.bottom);
    }
    return top;
  }

  // In the narrow-screen bar the list scrolls sideways, so keep the current entry
  // in view, centred. Only on a change of section, so it never fights a reader
  // scrolling the bar by hand; a no-op while the list fits, as in the rail.
  function revealCurrent(key) {
    if (key === revealedKey) return;
    revealedKey = key;
    var link = list.querySelector('a[aria-current]');
    if (!link || list.scrollWidth <= list.clientWidth) return;
    var box = list.getBoundingClientRect();
    var linkBox = link.getBoundingClientRect();
    if (linkBox.left >= box.left && linkBox.right <= box.right) return;
    list.scrollLeft += linkBox.left - box.left - (box.width - linkBox.width) / 2;
  }

  function currentKey() {
    var visible = sections();
    if (!visible.length) return null;
    // At the bottom of the page the last section can never reach the offset, so
    // claim it outright — otherwise the final entry is unreachable.
    var atBottom =
      window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 2;
    if (atBottom) return visible[visible.length - 1].dataset.section;
    var readingLine = readingTop(visible[0]) + ACTIVE_OFFSET;
    var key = visible[0].dataset.section;
    visible.forEach(function (el) {
      if (el.getBoundingClientRect().top <= readingLine) key = el.dataset.section;
    });
    return key;
  }

  var pending = false;
  function update() {
    pending = false;
    var key = currentKey();
    setCurrent(key);
    revealCurrent(key);
  }
  function schedule() {
    if (pending) return;
    pending = true;
    window.requestAnimationFrame(update);
  }

  window.addEventListener('scroll', schedule, { passive: true });
  window.addEventListener('resize', schedule);
  // A swap can change a section's height, moving every section below it.
  document.body.addEventListener('htmx:afterSwap', schedule);
  document.body.addEventListener('zingor:reorder', function (event) {
    if (!event.detail || event.detail.scope !== 'sections') return;
    var entryFor = {};
    entries().forEach(function (entry) {
      entryFor[entry.dataset.tocKey] = entry;
    });
    event.detail.order.forEach(function (key) {
      if (entryFor[key]) list.appendChild(entryFor[key]);
    });
    schedule();
  });
  update();
})();
