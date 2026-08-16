// Reveal the "area of concentration" input in the Add Study picker, but only
// for the few studies that are taken by area (History and friends).
// Hooks, per the data-* convention:
//   select[data-concentration-select]        -> the study picker
//   option[data-concentration="<label>"]     -> what an area is for that study; empty = takes none
//   [data-concentration-input]               -> the text input to reveal, inside the same form
// The label doubles as the placeholder, so the picker says what to type
// ("region and era") rather than making the player guess. This is decoration
// only: the server validates the pair regardless, so the form still works
// with the input left visible and the script never loaded.
(function () {
  function sync(select) {
    var form = select.closest('form');
    if (!form) return;
    var input = form.querySelector('[data-concentration-input]');
    if (!input) return;
    var option = select.options[select.selectedIndex];
    var label = option ? option.dataset.concentration : '';
    input.hidden = !label;
    input.placeholder = label ? 'Area: ' + label : '';
    // A leftover area would otherwise be posted with a study that can't hold
    // one, which the server rejects.
    if (!label) input.value = '';
  }
  function init(root) {
    var selects = (root || document).querySelectorAll('[data-concentration-select]');
    Array.prototype.forEach.call(selects, function (select) { sync(select); });
  }
  document.addEventListener('change', function (event) {
    if (event.target.matches && event.target.matches('[data-concentration-select]')) {
      sync(event.target);
    }
  });
  // The sage section is re-rendered wholesale by htmx after every edit, so the
  // fresh picker has to be re-synced each time it lands.
  document.addEventListener('htmx:afterSwap', function (event) { init(event.target); });
  document.addEventListener('DOMContentLoaded', function () { init(document); });
})();
