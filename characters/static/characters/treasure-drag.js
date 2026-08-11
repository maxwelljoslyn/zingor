// Dragging an item out of one person's take of a hoard and into another's.
//
// The splitter's division is never stored anywhere: the rendered page is the
// only record of it, and the form around it carries every item's name, value
// and holder as hidden fields. So a drop does not move anything on its own —
// it writes which item went where into two hidden fields and hands the whole
// division back to the server, which re-reads it with that one holder changed
// and returns the re-totalled markup. That is why the XP and the over/under
// against a fair share are right after a move without this file knowing how
// either is worked out.
//
// Listeners are delegated from the document rather than bound to the rows,
// because htmx replaces the entire division on every move: anything bound to a
// row would be thrown away with the first swap and never rebound.
//
// Hooks, per the data-* convention:
//   [data-treasure-form]      -> the form holding the whole division
//   [data-treasure-holder]    -> one recipient's take; a drop target, keyed by pk
//   [data-treasure-item]      -> a draggable item row, keyed by its name
//   [data-treasure-move-item] -> hidden field taking the dragged item's name
//   [data-treasure-move-to]   -> hidden field taking the holder it was dropped on
(function () {
  var dragging = null;

  function takeUnder(event) {
    var target = event.target;
    if (!target || !target.closest) return null;
    return target.closest('[data-treasure-holder]');
  }

  function clearTargets() {
    var lit = document.querySelectorAll('[data-treasure-holder].drop-target');
    Array.prototype.forEach.call(lit, function (take) {
      take.classList.remove('drop-target');
    });
  }

  document.addEventListener('dragstart', function (event) {
    var item = event.target.closest && event.target.closest('[data-treasure-item]');
    if (!item) return;
    dragging = item;
    event.dataTransfer.effectAllowed = 'move';
    // Firefox refuses to start a drag until some data is attached to it.
    event.dataTransfer.setData('text/plain', item.dataset.treasureItem);
    item.classList.add('treasure-dragging');
  });

  document.addEventListener('dragend', function () {
    if (dragging) dragging.classList.remove('treasure-dragging');
    dragging = null;
    clearTargets();
  });

  document.addEventListener('dragover', function (event) {
    if (!dragging) return;
    var take = takeUnder(event);
    if (!take) return;
    // Only a preventDefault here makes the element a valid drop target.
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
    if (take.classList.contains('drop-target')) return;
    clearTargets();
    take.classList.add('drop-target');
  });

  document.addEventListener('drop', function (event) {
    if (!dragging) return;
    var take = takeUnder(event);
    var item = dragging;
    var from = item.closest('[data-treasure-holder]');
    item.classList.remove('treasure-dragging');
    dragging = null;
    clearTargets();
    if (!take) return;
    event.preventDefault();
    // Dropping an item back where it came from changes nothing, so don't make
    // the server re-render an identical division.
    if (from === take) return;
    var form = take.closest('[data-treasure-form]');
    if (!form) return;
    var moved = form.querySelector('[data-treasure-move-item]');
    var onto = form.querySelector('[data-treasure-move-to]');
    if (!moved || !onto) return;
    moved.value = item.dataset.treasureItem;
    onto.value = take.dataset.treasureHolder;
    // The form listens for this via hx-trigger; htmx serialises it from there.
    form.dispatchEvent(new CustomEvent('treasure-move'));
  });
})();
