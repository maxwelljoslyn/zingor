// In-page replacement for htmx's native confirm() prompt. Browsers offer to
// suppress repeated native dialogs ("Don't allow this site to prompt you
// again?"); once accepted, confirm() silently returns false and every
// hx-confirm'd action stops working. A <dialog> cannot be suppressed.
// Existing hx-confirm attributes work unchanged: htmx fires htmx:confirm with
// the question text, we show the dialog instead, and issue the request only
// if the user confirms.
(function () {
  var dialog = document.querySelector('[data-confirm-dialog]');
  if (!dialog || typeof dialog.showModal !== 'function') return;
  var questionEl = dialog.querySelector('[data-confirm-question]');
  var okButton = dialog.querySelector('[data-confirm-ok]');
  var pending = null;

  function ask(question) {
    return new Promise(function (resolve) {
      pending = resolve;
      questionEl.textContent = question;
      dialog.returnValue = '';
      dialog.showModal();
      // Focus Confirm so Enter accepts, matching native confirm().
      okButton.focus();
    });
  }

  // Both buttons submit the method="dialog" form, closing the dialog with
  // returnValue set to the clicked button's value. Escape also closes, with
  // the returnValue reset in ask() still in place, i.e. a cancel.
  dialog.addEventListener('close', function () {
    if (!pending) return;
    var resolve = pending;
    pending = null;
    resolve(dialog.returnValue === 'confirm');
  });

  // A click on the backdrop lands on the <dialog> itself, not its children.
  dialog.addEventListener('click', function (event) {
    if (event.target === dialog) dialog.close();
  });

  document.addEventListener('htmx:confirm', function (event) {
    // question is only set when the triggering element has hx-confirm.
    if (!event.detail.question) return;
    event.preventDefault();
    ask(event.detail.question).then(function (confirmed) {
      if (confirmed) event.detail.issueRequest(true);
    });
  });
})();
