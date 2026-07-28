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

  // How far below the viewport top a section's start must be before it counts as
  // the one being read. Roughly one heading's worth of slack.
  var ACTIVE_OFFSET = 96;

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

  function currentKey() {
    var visible = sections();
    if (!visible.length) return null;
    // At the bottom of the page the last section can never reach the offset, so
    // claim it outright — otherwise the final entry is unreachable.
    var atBottom =
      window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 2;
    if (atBottom) return visible[visible.length - 1].dataset.section;
    var key = visible[0].dataset.section;
    visible.forEach(function (el) {
      if (el.getBoundingClientRect().top <= ACTIVE_OFFSET) key = el.dataset.section;
    });
    return key;
  }

  var pending = false;
  function update() {
    pending = false;
    setCurrent(currentKey());
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
