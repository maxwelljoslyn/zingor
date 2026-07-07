// Collapse/expand a container's contents in the inventory table. Collapse
// state is a per-viewer UI preference, so it lives in localStorage (keyed by
// the table's data-collapse-scope, the character pk) rather than on Item —
// two viewers of the same sheet each keep their own state.
// Hooks, per the data-* convention:
//   table[data-collapse-scope="<key>"]  -> opts a table in; the storage key suffix
//   tr[data-item-id] / [data-parent-id] -> row identity and containment chain
//   [data-collapse-toggle]              -> the caret button on a container row
// The inventory section is re-rendered wholesale by htmx after most edits, so
// state is re-applied to every opted-in table on each htmx:afterSwap.
(function () {
  function storageKey(scope) { return 'zingor-collapsed-' + scope; }
  function loadCollapsed(scope) {
    try {
      var ids = JSON.parse(localStorage.getItem(storageKey(scope)) || '[]');
      return Array.isArray(ids) ? ids : [];
    } catch (e) { return []; }
  }
  function saveCollapsed(scope, ids) {
    try { localStorage.setItem(storageKey(scope), JSON.stringify(ids)); } catch (e) {}
  }
  function apply(table) {
    var collapsed = loadCollapsed(table.dataset.collapseScope);
    var rows = Array.prototype.slice.call(table.querySelectorAll('tr[data-item-id]'));
    var parentOf = {};
    rows.forEach(function (row) {
      if (row.dataset.parentId) parentOf[row.dataset.itemId] = row.dataset.parentId;
    });
    rows.forEach(function (row) {
      // A row is hidden when any ancestor container is collapsed, so expanding
      // an outer container keeps a collapsed inner container's contents hidden.
      var hidden = false;
      var seen = {};
      var ancestor = row.dataset.parentId;
      while (ancestor && !seen[ancestor]) {
        seen[ancestor] = true;
        if (collapsed.indexOf(ancestor) !== -1) { hidden = true; break; }
        ancestor = parentOf[ancestor];
      }
      row.classList.toggle('collapse-hidden', hidden);
      var toggle = row.querySelector('[data-collapse-toggle]');
      if (toggle) {
        var isCollapsed = collapsed.indexOf(row.dataset.itemId) !== -1;
        toggle.textContent = isCollapsed ? '▸' : '▾';
        toggle.setAttribute('aria-expanded', String(!isCollapsed));
      }
    });
  }
  function applyAll() {
    document.querySelectorAll('table[data-collapse-scope]').forEach(apply);
  }
  // Called by the drag-drop handler in base.html so that dropping an item into
  // a collapsed container expands it — otherwise the item would land unseen.
  window.zingorExpandRow = function (row) {
    var table = row.closest('table[data-collapse-scope]');
    if (!table) return;
    var scope = table.dataset.collapseScope;
    saveCollapsed(scope, loadCollapsed(scope).filter(function (id) {
      return id !== row.dataset.itemId;
    }));
  };
  // Delegated from document so toggles in htmx-swapped markup keep working.
  document.addEventListener('click', function (event) {
    var toggle = event.target.closest('[data-collapse-toggle]');
    if (!toggle) return;
    var row = toggle.closest('tr[data-item-id]');
    var table = toggle.closest('table[data-collapse-scope]');
    if (!row || !table) return;
    var scope = table.dataset.collapseScope;
    var ids = loadCollapsed(scope);
    var index = ids.indexOf(row.dataset.itemId);
    if (index === -1) ids.push(row.dataset.itemId); else ids.splice(index, 1);
    // Prune ids whose rows are gone (deleted items) so the list can't grow forever.
    var present = {};
    table.querySelectorAll('tr[data-item-id]').forEach(function (r) {
      present[r.dataset.itemId] = true;
    });
    saveCollapsed(scope, ids.filter(function (id) { return present[id]; }));
    apply(table);
  });
  document.addEventListener('htmx:afterSwap', applyAll);
  applyAll(); // loaded with defer, so the DOM is already parsed
})();
