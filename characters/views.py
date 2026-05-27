"""Views for the characters app."""

import functools
import json
import logging
from collections import OrderedDict
from urllib.request import Request, urlopen

from django.conf import settings as django_settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from django.views.decorators.http import require_GET, require_POST

from . import rules
from .auth_emails import EmailSendError, send_confirmation_email
from .forms import FeedbackForm, RegistrationForm

logger = logging.getLogger(__name__)
from .models import (
    Character,
    Condition,
    HitDie,
    Item,
    Profile,
    SageStudyPoints,
    Spell,
)
from .units import D, u


def character_owner_required(view_func):
    """Reject requests where the logged-in user doesn't own the character.

    Works with views whose URL has a `pk` kwarg pointing to a Character,
    and with views whose URL has an `item_id`, `condition_id`, `hit_die_id`,
    or `spell_id` kwarg pointing to a related object.
    """

    @functools.wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if "pk" in kwargs:
            char = get_object_or_404(Character, pk=kwargs["pk"])
            owner = char.user
        elif "item_id" in kwargs:
            item = get_object_or_404(Item, pk=kwargs["item_id"])
            owner = item.owner.user
        elif "container_id" in kwargs:
            item = get_object_or_404(Item, pk=kwargs["container_id"])
            owner = item.owner.user
        elif "condition_id" in kwargs:
            cond = get_object_or_404(Condition, pk=kwargs["condition_id"])
            owner = cond.character.user
        elif "hit_die_id" in kwargs:
            hd = get_object_or_404(HitDie, pk=kwargs["hit_die_id"])
            owner = hd.character.user
        elif "spell_id" in kwargs:
            spell = get_object_or_404(Spell, pk=kwargs["spell_id"])
            owner = spell.character.user
        elif "study_pk" in kwargs:
            row = get_object_or_404(SageStudyPoints, pk=kwargs["study_pk"])
            owner = row.character.user
        else:
            return HttpResponseForbidden("Cannot determine character ownership.")
        if request.user != owner:
            return HttpResponseForbidden("You do not own this character.")
        return view_func(request, *args, **kwargs)

    return wrapper


# --- Helpers ---


def _build_char_data(character):
    """Build the char_data dict from a Character instance for rules.calculate_derived_stats."""
    data = {}
    for ability in Character.ABILITY_NAMES:
        data[ability] = character.current_ability_score(ability)
    # For strength, use effective_strength to handle the 18/percentile boundary
    eff_str, eff_pct = character.current_strength_and_percentile()
    data["strength"] = eff_str
    data["percentile_strength"] = eff_pct
    data["char_class"] = character.char_class
    data["level"] = character.level
    data["race"] = character.race
    data["sex"] = character.sex
    return data


def _build_ability_data(character, derived):
    """Build structured ability data for the template."""
    ability_data = []
    for ability in Character.ABILITY_NAMES:
        base_score = getattr(character, ability)
        current_score = character.current_ability_score(ability)
        derived_stats = []
        for stat_name, func in rules.abilities.get(ability, {}).items():
            value = derived.get(stat_name)
            is_mod = "modifier" in stat_name or stat_name == "bonus HP per level"
            is_pct = "%" in stat_name
            derived_stats.append(
                {
                    "label": stat_name,
                    "value": value,
                    "is_modifier": is_mod,
                    "is_pct": is_pct,
                }
            )
        entry = {
            "name": ability,
            "field_name": ability,
            "base_score": base_score,
            "current_score": current_score,
            "derived": derived_stats,
        }
        if ability == "strength":
            eff_str, eff_pct = character.current_strength_and_percentile()
            entry["current_score"] = eff_str
            entry["percentile_strength"] = character.percentile_strength
            entry["effective_percentile"] = eff_pct
        ability_data.append(entry)
    return ability_data


def _sheet_context(character):
    """Build the full template context for a character sheet."""
    char_data = _build_char_data(character)
    derived = rules.calculate_derived_stats(char_data)
    ability_data = _build_ability_data(character, derived)
    bodymass_die = character.hit_dice.filter(is_bodymass=True).first()
    level_dice = character.hit_dice.filter(is_bodymass=False)
    items = character.inventory.filter(container__isnull=True)
    conditions = character.conditions.all()
    spells = character.spells.all()

    spells_by_level = OrderedDict()
    for spell in spells:
        spells_by_level.setdefault(spell.level, []).append(spell)

    ctx = {
        "character": character,
        "derived": derived,
        "ability_data": ability_data,
        "bodymass_die": bodymass_die,
        "level_dice": level_dice,
        "items": items,
        "conditions": conditions,
        "spells_by_level": spells_by_level,
    }
    ctx.update(_build_sage_context(character))
    return ctx


# --- Field type mapping ---

FIELD_TYPES = {
    "name": "text",
    "race": "select",
    "sex": "select",
    "char_class": "select",
    "level": "number",
    "xp": "number",
    "strength": "number",
    "percentile_strength": "number",
    "dexterity": "number",
    "constitution": "number",
    "intelligence": "number",
    "wisdom": "number",
    "charisma": "number",
    "current_hp": "number",
    "height": "text",
    "weight": "text",
    "gp": "text",
    "sp": "text",
    "cp": "text",
    "notes": "textarea",
    "background": "textarea",
    "appearance": "textarea",
    "encumbrance_multiplier": "text",
}

FIELD_CHOICES = {
    "race": list(rules.races.keys()),
    "sex": ["male", "female"],
    "char_class": list(rules.classes.keys()),
}

INTEGER_FIELDS = {
    "level",
    "xp",
    "strength",
    "percentile_strength",
    "dexterity",
    "constitution",
    "intelligence",
    "wisdom",
    "charisma",
    "current_hp",
}

PINT_FIELDS = {"height", "weight", "gp", "sp", "cp"}

# Short display labels for money pint units (canonical name -> short form)
PINT_UNIT_DISPLAY = {
    "gold_piece": "gp",
    "silver_piece": "sp",
    "copper_piece": "cp",
}

SECTION_FOR_FIELD = {
    "name": "identity",
    "race": "identity",
    "sex": "identity",
    "char_class": "identity",
    "level": "identity",
    "xp": "identity",
    "height": "identity",
    "weight": "identity",
    "gp": "identity",
    "sp": "identity",
    "cp": "identity",
    "strength": "abilities",
    "percentile_strength": "abilities",
    "dexterity": "abilities",
    "constitution": "abilities",
    "intelligence": "abilities",
    "wisdom": "abilities",
    "charisma": "abilities",
    "current_hp": "hp",
    "notes": "notes",
    "background": "notes",
    "appearance": "notes",
    "encumbrance_multiplier": "inventory",
}


# --- Auth views ---


def register(request):
    if request.method == "POST":
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            Profile.objects.create(user=user, email_confirmed=False)
            try:
                send_confirmation_email(user, request)
            except EmailSendError:
                login(request, user)
                messages.error(
                    request,
                    "Account created, but we couldn't send a confirmation email."
                    " You can resend it from your profile.",
                )
                return redirect("characters:email_confirmation_status")
            if not django_settings.EMAIL_CONFIRMATION_REQUIRED:
                login(request, user)
                messages.success(request, "Email auto-confirmed in dev.")
                return redirect("/")
            else:
                return redirect("characters:register_pending")
    else:
        form = RegistrationForm()
    return render(request, "registration/register.html", {"form": form})


def register_pending(request):
    return render(request, "registration/register_pending.html")


def register_confirm(request, uidb64, token):
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user is not None and default_token_generator.check_token(user, token):
        user.profile.email_confirmed = True
        user.profile.save(update_fields=["email_confirmed"])
        login(request, user)
        messages.success(request, "Your email has been confirmed.")
        return redirect("/")
    return render(request, "registration/register_confirm_invalid.html")


@login_required
@require_POST
def resend_confirmation(request):
    try:
        send_confirmation_email(request.user, request)
    except EmailSendError:
        messages.error(
            request, "Could not send confirmation email. Please try again later."
        )
        return redirect("characters:email_confirmation_status")
    if request.user.profile.email_confirmed:
        messages.success(request, "Email auto-confirmed in dev.")
    else:
        messages.success(request, "Confirmation email sent.")
    return redirect("characters:email_confirmation_status")


@login_required
def email_confirmation_status(request):
    if request.method == "POST":
        new_email = request.POST.get("email", "").strip()
        if new_email:
            request.user.email = new_email
            request.user.save(update_fields=["email"])
            messages.success(request, "Email address updated.")
        return redirect("characters:email_confirmation_status")
    return render(request, "registration/email_confirmation_status.html")


# --- Character list ---


@login_required
def character_list(request):
    characters = Character.objects.select_related("user").order_by(
        "user__username", "name"
    )
    all_items = (
        Item.objects.select_related("owner", "owner__user")
        .filter(container__isnull=True)
        .order_by("owner__name", "name")
    )
    return render(
        request,
        "characters/character_list.html",
        {"characters": characters, "all_items": all_items},
    )


@login_required
@require_POST
def character_create(request):
    character = Character.objects.create(user=request.user)
    return redirect(f"/character/{character.pk}/")


# --- Character sheet ---


@login_required
def character_sheet(request, pk):
    character = get_object_or_404(Character, pk=pk)
    ctx = _sheet_context(character)
    ctx["is_owner"] = character.user == request.user
    return render(request, "characters/character_sheet.html", ctx)


# --- HTMX field editing ---


@login_required
@character_owner_required
def edit_field(request, pk):
    """Return an inline edit form for a single field."""
    character = get_object_or_404(Character, pk=pk)
    field_name = request.GET.get("field", "")
    field_type = FIELD_TYPES.get(field_name, "text")
    current_value = getattr(character, field_name, None)

    # For PintField, show just the string repr
    if field_name in PINT_FIELDS and current_value is not None:
        current_value = str(current_value)

    # For pint fields with a set value, split into magnitude and unit for the edit form.
    # For money fields with no value yet, default to 0 with the field's unit.
    is_pint_split = False
    pint_magnitude = None
    pint_unit = None
    pint_unit_display = None
    if field_name in PINT_FIELDS:
        if current_value is not None:
            parts = current_value.split(" ", 1)
            pint_magnitude = parts[0]
            pint_unit = parts[1] if len(parts) > 1 else field_name
            pint_unit_display = PINT_UNIT_DISPLAY.get(pint_unit, pint_unit)
            is_pint_split = True
        elif field_name in {"gp", "sp", "cp"}:
            pint_magnitude = "0"
            pint_unit = field_name
            pint_unit_display = field_name
            is_pint_split = True

    section = SECTION_FOR_FIELD.get(field_name, "identity")
    ctx = {
        "character_id": pk,
        "field_name": field_name,
        "field_type": field_type,
        "current_value": current_value,
        "choices": FIELD_CHOICES.get(field_name, []),
        "section": section,
        "is_pint_split": is_pint_split,
        "pint_magnitude": pint_magnitude,
        "pint_unit": pint_unit,
        "pint_unit_display": pint_unit_display,
    }
    return render(request, "characters/partials/edit_field.html", ctx)


@login_required
@character_owner_required
@require_POST
def update_field(request, pk):
    """Generic field updater."""
    character = get_object_or_404(Character, pk=pk)
    field_name = request.POST.get("field_name", "")
    raw_value = request.POST.get("value", "")

    if field_name not in FIELD_TYPES:
        return HttpResponse("Invalid field", status=400)

    old_value = getattr(character, field_name)

    # Type coercion
    if field_name in INTEGER_FIELDS:
        new_value = int(raw_value) if raw_value else None
    elif field_name in PINT_FIELDS:
        if raw_value:
            pint_unit = request.POST.get("pint_unit", "")
            if pint_unit:
                raw_value = f"{raw_value} {pint_unit}"
            q = u(raw_value)
            new_value = D(q.magnitude) * q.units
        else:
            new_value = None
    elif field_name == "encumbrance_multiplier":
        new_value = D(raw_value) if raw_value else D("1.0")
    else:
        new_value = raw_value if raw_value else None

    setattr(character, field_name, new_value)
    character.save(update_fields=[field_name, "updated_at"])

    # Return the updated section, with OOB updates for cross-section dependencies
    section = SECTION_FOR_FIELD.get(field_name, "identity")
    oob = []
    if field_name in {
        "strength",
        "percentile_strength",
        "weight",
        "encumbrance_multiplier",
        "gp",
        "sp",
        "cp",
    }:
        oob.append("inventory")
    if field_name in {"strength", "percentile_strength"}:
        oob.append("abilities")
    return _render_section(request, character, section, oob_sections=oob or None)


def _render_section(request, character, section, oob_sections=None):
    """Render a single section partial, optionally with out-of-band updates.

    oob_sections: list of additional section names to include as hx-swap-oob.
    """
    ctx = _sheet_context(character)
    ctx["is_owner"] = character.user == request.user
    template_name = f"characters/partials/{section}.html"
    response = render(request, template_name, ctx)

    if oob_sections:
        primary_html = response.content.decode()
        oob_parts = []
        for oob_section in oob_sections:
            if oob_section == section:
                continue
            oob_template = f"characters/partials/{oob_section}.html"
            oob_html = render(request, oob_template, ctx).content.decode()
            # Inject hx-swap-oob into the outermost div
            oob_html = oob_html.replace(
                f'id="section-{oob_section}"',
                f'id="section-{oob_section}" hx-swap-oob="outerHTML"',
                1,
            )
            oob_parts.append(oob_html)
        full_html = primary_html + "\n".join(oob_parts)
        return HttpResponse(full_html)

    return response


# --- Section refresh endpoints ---


@login_required
def section_refresh(request, pk, section):
    character = get_object_or_404(Character, pk=pk)
    return _render_section(request, character, section)


# --- Item field editing ---


@login_required
@character_owner_required
def edit_item_field(request, item_id):
    """Return an inline edit form for a single item field."""
    item = get_object_or_404(Item, pk=item_id)
    field_name = request.GET.get("field", "")

    if field_name == "name":
        current_value = item.name
        is_pint_split = False
        pint_magnitude = None
        pint_unit = None
        pint_unit_display = None
    elif field_name == "weight":
        weight_str = str(item.weight) if item.weight is not None else "0 ounce"
        parts = weight_str.split(" ", 1)
        pint_magnitude = parts[0]
        pint_unit = parts[1] if len(parts) > 1 else "ounce"
        pint_unit_display = PINT_UNIT_DISPLAY.get(pint_unit, pint_unit)
        current_value = weight_str
        is_pint_split = True
    elif field_name == "capacity":
        cap = item.capacity
        current_value = str(cap) if cap is not None else ""
        is_pint_split = False
        pint_magnitude = None
        pint_unit = None
        pint_unit_display = None
    else:
        return HttpResponse("Invalid field", status=400)

    pint_unit_choices = None
    if field_name == "weight":
        pint_unit_choices = [("pound", "lb"), ("ounce", "oz")]

    ctx = {
        "item": item,
        "field_name": field_name,
        "current_value": current_value,
        "is_pint_split": is_pint_split,
        "pint_magnitude": pint_magnitude,
        "pint_unit": pint_unit,
        "pint_unit_display": pint_unit_display,
        "pint_unit_choices": pint_unit_choices,
    }
    return render(request, "characters/partials/item_edit_field.html", ctx)


@login_required
@character_owner_required
@require_POST
def update_item_field(request, item_id):
    """Update a single field on an item."""
    item = get_object_or_404(Item, pk=item_id)
    field_name = request.POST.get("field_name", "")
    raw_value = request.POST.get("value", "")

    if field_name == "name":
        item.name = raw_value
    elif field_name == "weight":
        pint_unit = request.POST.get("pint_unit", "")
        full = f"{raw_value} {pint_unit}" if pint_unit else raw_value
        q = u(full)
        item.weight = str(D(q.magnitude) * q.units)
    elif field_name == "is_worn":
        item.is_worn = raw_value == "on"
        item.is_carried = item.is_worn
    elif field_name == "is_container":
        item.is_container = raw_value == "on"
        if not item.is_container:
            item.contents.update(container=None)
    elif field_name == "capacity":
        if raw_value:
            q = u(raw_value)
            item.capacity = str(D(q.magnitude) * q.units)
        else:
            item.capacity = None
    else:
        return HttpResponse("Invalid field", status=400)

    save_fields = (
        [field_name, "is_carried"] if field_name == "is_worn" else [field_name]
    )
    item.save(update_fields=save_fields)
    return _render_section(request, item.owner, "inventory")


# --- Container operations ---


def _would_create_cycle(container, item):
    current = container
    while current is not None:
        if current.pk == item.pk:
            return True
        current = current.container
    return False


@login_required
@character_owner_required
@require_POST
def put_in_container(request, container_id):
    container = get_object_or_404(Item, pk=container_id)
    if not container.is_container:
        return HttpResponse("Item is not a container", status=400)
    item_id = request.POST.get("item_id")
    item = get_object_or_404(Item, pk=item_id, owner=container.owner)
    if item.pk == container.pk:
        return HttpResponse("Cannot put item in itself", status=400)
    if _would_create_cycle(container, item):
        return HttpResponse("Cannot create container cycle", status=400)
    item.container = container
    item.save(update_fields=["container"])
    return _render_section(request, container.owner, "inventory")


@login_required
@character_owner_required
@require_POST
def remove_from_container(request, item_id):
    item = get_object_or_404(Item, pk=item_id)
    item.container = None
    item.save(update_fields=["container"])
    return _render_section(request, item.owner, "inventory")


# --- Item CRUD ---


@login_required
@character_owner_required
@require_POST
def add_item(request, pk):
    character = get_object_or_404(Character, pk=pk)
    name = request.POST.get("name", "")
    weight_str = request.POST.get("weight", "0 oz")
    is_worn = request.POST.get("is_worn") == "on"
    try:
        quantity = max(1, min(100, int(request.POST.get("quantity", 1))))
    except (TypeError, ValueError):
        quantity = 1

    if weight_str:
        try:
            q = u(weight_str)
            weight = D(q.magnitude) * q.units
        except Exception:
            weight = D(0) * u.oz
    else:
        weight = D(0) * u.oz

    for _ in range(quantity):
        Item.objects.create(
            owner=character,
            name=name,
            weight=str(weight),
            is_worn=is_worn,
        )

    return _render_section(request, character, "inventory")


@login_required
@character_owner_required
def delete_item(request, item_id):
    if request.method != "DELETE":
        return HttpResponse(status=405)
    item = get_object_or_404(Item, pk=item_id)
    character = item.owner
    item.delete()
    return _render_section(request, character, "inventory")


# --- Condition CRUD ---


@login_required
@character_owner_required
@require_POST
def add_condition(request, pk):
    character = get_object_or_404(Character, pk=pk)
    modifier_type = request.POST.get("modifier_type", "ability")
    target = request.POST.get("target", "") or None
    value = int(request.POST.get("value", 0))
    source = request.POST.get("source", "")
    scope = request.POST.get("scope", "") or None

    Condition.objects.create(
        character=character,
        modifier_type=modifier_type,
        target=target,
        value=value,
        source=source,
        scope=scope,
    )
    return _render_section(
        request,
        character,
        "conditions",
        oob_sections=["abilities", "inventory"],
    )


@login_required
@character_owner_required
def delete_condition(request, condition_id):
    if request.method != "DELETE":
        return HttpResponse(status=405)
    condition = get_object_or_404(Condition, pk=condition_id)
    character = condition.character
    condition.delete()
    return _render_section(
        request,
        character,
        "conditions",
        oob_sections=["abilities", "inventory"],
    )


# --- Hit Die CRUD ---


@login_required
@character_owner_required
@require_POST
def add_hit_die(request, pk):
    character = get_object_or_404(Character, pk=pk)
    is_bodymass = request.POST.get("is_bodymass") == "true"
    die_type = request.POST.get("die_type", "d10")
    roll = int(request.POST.get("roll", 1))

    if is_bodymass:
        level = None
        con_bonus = 0
    else:
        level = int(request.POST.get("level", 1))
        con_bonus = int(request.POST.get("con_bonus", 0))

    HitDie.objects.create(
        character=character,
        level=level,
        die_type=die_type,
        roll=roll,
        con_bonus=con_bonus,
        is_bodymass=is_bodymass,
    )
    return _render_section(request, character, "hp")


@login_required
@character_owner_required
def delete_hit_die(request, hit_die_id):
    if request.method != "DELETE":
        return HttpResponse(status=405)
    hd = get_object_or_404(HitDie, pk=hit_die_id)
    character = hd.character
    hd.delete()
    return _render_section(request, character, "hp")


# --- Spell CRUD ---


@login_required
@character_owner_required
@require_POST
def add_spell(request, pk):
    character = get_object_or_404(Character, pk=pk)
    name = request.POST.get("name", "")
    level = int(request.POST.get("level", 1))

    Spell.objects.create(character=character, name=name, level=level)
    return _render_section(request, character, "spells")


@login_required
@character_owner_required
def delete_spell(request, spell_id):
    if request.method != "DELETE":
        return HttpResponse(status=405)
    spell = get_object_or_404(Spell, pk=spell_id)
    character = spell.character
    spell.delete()
    return _render_section(request, character, "spells")


@login_required
@character_owner_required
def toggle_spell_memorized(request, spell_id: int) -> HttpResponse:
    if request.method != "POST":
        return HttpResponse(status=405)
    spell = get_object_or_404(Spell, pk=spell_id)
    spell.is_memorized = "value" in request.POST
    spell.save(update_fields=["is_memorized"])
    return _render_section(request, spell.character, "spells")


# --- Sage knowledge ---


def _build_sage_context(character):
    """Build template context for the sage.html partial."""
    from .sage import CLASS_FIELDS, sage_fields, sage_studies, sort_sage_entries

    rows = {r.study: r for r in character.sage_studies.all()}
    sorted_entries = sort_sage_entries(
        {study: row.points for study, row in rows.items()},
        sort_keys=["name"],
    )
    for entry in sorted_entries:
        entry["pk"] = rows[entry["name"]].pk

    # Group entries by field using the character's class fields.
    char_class = (character.char_class or "").lower()
    class_fields = set(CLASS_FIELDS.get(char_class, []))
    field_map = {}
    for entry in sorted_entries:
        study_info = sage_studies.get(entry["name"], {})
        study_fields = study_info.get("fields", [])
        # Use whichever of this study's fields are in the character's class fields.
        matching = [f for f in study_fields if f in class_fields]
        field = (
            matching[0] if matching else (study_fields[0] if study_fields else "Other")
        )
        field_map.setdefault(field, []).append(entry)
    sage_studies_by_field = [
        {"field": f, "entries": field_map[f]} for f in sorted(field_map)
    ]

    return {
        "character": character,
        "sage_studies_by_field": sage_studies_by_field,
        "sage_fields": sage_fields,
        "sage_fields_json": json.dumps(sage_fields),
        "all_study_names": sorted(sage_studies.keys()),
    }


@login_required
@character_owner_required
@require_GET
def sage_chosen_field_form(request, pk):
    """Return the inline form snippet for editing chosen field/study."""
    from .sage import sage_fields

    character = get_object_or_404(Character, pk=pk)
    initial_field = character.chosen_field or next(iter(sage_fields))
    initial_studies = (
        sage_fields[initial_field]["studies"] if initial_field in sage_fields else []
    )
    return render(
        request,
        "characters/partials/sage_field_form.html",
        {
            "character": character,
            "sage_fields": sage_fields,
            "sage_fields_json": json.dumps(sage_fields),
            "initial_field": initial_field,
            "initial_studies": initial_studies,
        },
    )


@login_required
@character_owner_required
@require_GET
def sage_study_options(request, pk):
    """Return <option> tags for the studies in the given field (used by HTMX field-select)."""
    from .sage import sage_fields

    get_object_or_404(Character, pk=pk)
    field_name = request.GET.get("chosen_field", "")
    studies = sage_fields.get(field_name, {}).get("studies", [])
    return render(
        request,
        "characters/partials/sage_study_options.html",
        {"studies": studies},
    )


@login_required
@character_owner_required
@require_POST
def sage_chosen_field(request, pk):
    """Save chosen field/study and bulk-create class study rows."""
    from .sage import CLASS_FIELDS, sage_fields

    character = get_object_or_404(Character, pk=pk)
    chosen_field = request.POST.get("chosen_field", "")
    chosen_study = request.POST.get("chosen_study", "")

    if chosen_field not in sage_fields:
        return HttpResponse("Invalid field", status=400)
    if chosen_study not in sage_fields[chosen_field]["studies"]:
        return HttpResponse("Invalid study for field", status=400)

    character.chosen_field = chosen_field
    character.chosen_study = chosen_study
    character.save(update_fields=["chosen_field", "chosen_study", "updated_at"])

    char_class = character.char_class
    if char_class in CLASS_FIELDS:
        all_studies = list(
            dict.fromkeys(
                s
                for field_name in CLASS_FIELDS[char_class]
                for s in sage_fields[field_name]["studies"]
            )
        )
        SageStudyPoints.objects.bulk_create(
            [
                SageStudyPoints(character=character, study=s, points=0)
                for s in all_studies
            ],
            ignore_conflicts=True,
        )

    sage_ctx = _build_sage_context(character)
    sage_ctx["is_owner"] = True
    return render(request, "characters/partials/sage.html", sage_ctx)


@login_required
@character_owner_required
@require_POST
def sage_study_points(request, pk, study_pk):
    """Update points for a single study row."""
    character = get_object_or_404(Character, pk=pk)
    row = get_object_or_404(SageStudyPoints, pk=study_pk, character=character)

    raw = request.POST.get("points")
    try:
        points = int(raw)
        if points < 0:
            raise ValueError
    except (TypeError, ValueError):
        return HttpResponse("Points must be a non-negative integer", status=400)

    row.points = points
    row.save(update_fields=["points"])
    sage_ctx = _build_sage_context(character)
    sage_ctx["is_owner"] = True
    return render(request, "characters/partials/sage.html", sage_ctx)


@login_required
@character_owner_required
@require_POST
def sage_study_add(request, pk):
    """Add a new study row to the character's sage table."""
    from .sage import sage_studies

    character = get_object_or_404(Character, pk=pk)
    study = request.POST.get("study", "")

    if study not in sage_studies:
        return HttpResponse("Unknown study", status=400)

    SageStudyPoints.objects.get_or_create(
        character=character, study=study, defaults={"points": 0}
    )
    sage_ctx = _build_sage_context(character)
    sage_ctx["is_owner"] = True
    return render(request, "characters/partials/sage.html", sage_ctx)


# --- Wiki export ---


@login_required
def wiki_export(request, pk):
    character = get_object_or_404(Character, pk=pk)
    from .wiki_export import character_to_wiki as _character_to_wiki

    wiki_text = _character_to_wiki(character)
    return render(
        request, "characters/partials/wiki_modal.html", {"wiki_text": wiki_text}
    )


# --- Feedback ---


@login_required
def feedback(request):
    if request.method == "POST":
        form = FeedbackForm(request.POST)
        if form.is_valid():
            user = request.user
            body = (
                f"{form.cleaned_data['description']}"
                f"\n\n---\n*Submitted by {user.username} ({user.email})*"
            )

            repo = django_settings.GITHUB_FEEDBACK_REPO
            token = django_settings.GITHUB_FEEDBACK_TOKEN
            if not repo or not token:
                logger.error("GITHUB_FEEDBACK_REPO or GITHUB_FEEDBACK_TOKEN not set")
                messages.error(
                    request,
                    "Feedback system is not configured. Please contact the developer.",
                )
                return redirect("characters:feedback")

            payload = json.dumps(
                {
                    "title": form.cleaned_data["title"],
                    "body": body,
                    "labels": ["user-feedback"],
                }
            ).encode()
            req = Request(
                f"https://api.github.com/repos/{repo}/issues",
                data=payload,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            try:
                urlopen(req)
                messages.success(request, "Thanks! Your feedback has been submitted.")
            except Exception:
                logger.exception("Failed to create GitHub issue")
                messages.error(
                    request,
                    "Something went wrong submitting your feedback. Please try again.",
                )
            return redirect("characters:feedback")
    else:
        form = FeedbackForm()
    return render(request, "characters/feedback.html", {"form": form})
