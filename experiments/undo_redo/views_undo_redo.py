"""Undo/redo view functions, extracted from characters/views.py."""

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST

from .models import Character


def _render_sheet_body(request, character):
    """Render just the sheet body partials (for HTMX swaps)."""
    # ctx = _sheet_context(character)
    # return render(request, "characters/partials/sheet_body.html", ctx)
    pass


@login_required
@require_POST
def undo(request, pk):
    character = get_object_or_404(Character, pk=pk, user=request.user)
    character.undo()
    character.refresh_from_db()
    return _render_sheet_body(request, character)


@login_required
@require_POST
def redo(request, pk):
    character = get_object_or_404(Character, pk=pk, user=request.user)
    character.redo()
    character.refresh_from_db()
    return _render_sheet_body(request, character)
