// Holds a search box and the results beneath it at the top of the viewport, so
// results never arrive off-screen and the box never drifts under the reader.
//
// The drift this prevents: the results are the last thing on the page, so the
// page's height follows the result count. A search matching nothing shortens
// the page past the current scroll position, the browser clamps the scroll,
// and the box slides away on its own; the next, broader search then grows the
// page downward from wherever that left the viewport, putting every hit below
// the fold. Pinning fixes the box at a known position instead of chasing it.
//
// The companion CSS rule (.search-pin { min-height: 100vh }) is what makes the
// pin hold: it reserves one viewport for the region, which is exactly enough
// that "region at the top of the viewport" stays a reachable scroll position
// however few results come back. It reserves a viewport, not the unfiltered
// list's height — a full result set is far taller than 100vh and the rule then
// does nothing at all.
//
// Hooks, per the data-* convention:
//   [data-search-pin]       -> the region to hold at the top (box + results)
//   [data-search-pin-input] -> the search box inside it
(function () {
  function regionFor(element) {
    return element && element.closest ? element.closest('[data-search-pin]') : null;
  }
  function pin(element) {
    var region = regionFor(element);
    if (region) region.scrollIntoView({ block: 'start' });
  }
  // Pinning on focus rather than on the first result means the box reaches its
  // resting position before any results churn, so nothing moves once typing
  // starts. Every later pin is then a no-op unless the reader scrolled away.
  document.addEventListener('focusin', function (event) {
    if (event.target.closest('[data-search-pin-input]')) pin(event.target);
  });
  // Re-pin when results land, for the reader who scrolled down through a long
  // result set and then went back up to edit the query. Keyed off the element
  // that made the request, not the swapped-in one, so it stays correct however
  // the results are swapped.
  document.addEventListener('htmx:afterSwap', function (event) {
    var config = event.detail && event.detail.requestConfig;
    var source = config && config.elt;
    if (source && source.closest && source.closest('[data-search-pin-input]')) pin(source);
  });
})();
