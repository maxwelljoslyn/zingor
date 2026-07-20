// Re-render server-emitted UTC timestamps into the viewer's local time zone.
// Each localizable timestamp is a <time data-localize-time datetime="<ISO 8601>">
// whose textContent is a UTC fallback for the no-JS case. On load (and after any
// htmx swap) we reparse the machine-readable datetime attribute and rewrite the
// text into the browser's local zone, including the zone's short name (e.g. EDT)
// so a viewer can tell at a glance which zone the times are shown in — catching
// bugs where times appear in an unexpected zone.
(function () {
  function formatLocal(iso) {
    var date = new Date(iso);
    if (isNaN(date.getTime())) return null;
    return date.toLocaleString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      timeZoneName: 'short',
    });
  }
  function localize(root) {
    var scope = root && root.querySelectorAll ? root : document;
    scope.querySelectorAll('time[data-localize-time]').forEach(function (el) {
      var iso = el.getAttribute('datetime');
      if (!iso) return;
      var text = formatLocal(iso);
      if (text !== null) el.textContent = text;
    });
  }
  document.addEventListener('DOMContentLoaded', function () { localize(document); });
  document.addEventListener('htmx:afterSwap', function (event) { localize(event.target); });
})();
