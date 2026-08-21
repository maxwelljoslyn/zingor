// Publishes the sticky header's height as --header-height on the document root.
//
// Anything that positions itself against the top of the viewport has to know how
// much of it the header covers: the sheet's sticky table of contents, and the
// scroll-padding that keeps in-page jumps from landing under the header. The
// height is content-driven (it grows when the nav wraps, or with the user's font
// size), so it's measured rather than guessed; the stylesheet's own value is the
// fallback for JS off.
(function () {
  var header = document.querySelector('header');
  if (!header) return;

  function publish() {
    document.documentElement.style.setProperty(
      '--header-height', header.offsetHeight + 'px'
    );
  }

  publish();
  if (window.ResizeObserver) {
    new ResizeObserver(publish).observe(header);
  } else {
    window.addEventListener('resize', publish);
  }
})();
