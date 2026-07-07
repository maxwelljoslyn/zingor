// Click-to-sort for any table marked data-sort-table. Sortable headers carry
// class "sortable" plus data-col (cell index) and data-type ("text" | "number");
// cells may provide data-sort-value to override textContent as the key (unit-
// normalized weights; item names whose cell also holds a collapse caret).
// data-sort-table="rows" sorts the rows of the table's first <tbody>;
// data-sort-table="groups" sorts whole <tbody> groups by each group's first row,
// so container contents travel with their container (character inventory).
// Listeners are delegated from document so tables re-rendered by htmx swaps
// stay sortable; sort state lives on the table's dataset and resets with it.
(function () {
  function cellKey(row, col, type) {
    var cell = row.children[col];
    if (!cell) return type === 'number' ? 0 : '';
    var raw = cell.dataset.sortValue !== undefined ? cell.dataset.sortValue : cell.textContent;
    if (type === 'number') {
      var val = parseFloat(raw);
      return isNaN(val) ? 0 : val;
    }
    return raw.trim().toLowerCase();
  }
  document.addEventListener('click', function (event) {
    var th = event.target.closest('th.sortable');
    if (!th) return;
    var table = th.closest('table[data-sort-table]');
    if (!table) return;
    var col = parseInt(th.dataset.col, 10);
    var type = th.dataset.type;
    var ascending = table.dataset.sortCol === String(col) ? table.dataset.sortAsc !== 'true' : true;
    table.dataset.sortCol = col;
    table.dataset.sortAsc = ascending;
    var units, keyRow, parent;
    if (table.getAttribute('data-sort-table') === 'groups') {
      units = Array.prototype.slice.call(table.tBodies);
      keyRow = function (tbody) { return tbody.rows[0]; };
      parent = table;
    } else {
      parent = table.tBodies[0];
      if (!parent) return;
      units = Array.prototype.slice.call(parent.rows);
      keyRow = function (row) { return row; };
    }
    units.sort(function (a, b) {
      var aVal = cellKey(keyRow(a), col, type);
      var bVal = cellKey(keyRow(b), col, type);
      if (aVal < bVal) return ascending ? -1 : 1;
      if (aVal > bVal) return ascending ? 1 : -1;
      return 0;
    });
    units.forEach(function (unit) { parent.appendChild(unit); });
    table.querySelectorAll('th.sortable .sort-arrow').forEach(function (arrow) {
      arrow.textContent = '';
    });
    th.querySelector('.sort-arrow').textContent = ascending ? ' ▲' : ' ▼';
  });
})();
