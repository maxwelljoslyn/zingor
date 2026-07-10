"""Convert a Character instance to MediaWiki markup."""

from collections import OrderedDict

from .models import Character
from .sage import rank_for_points, sage_studies as SAGE_STUDIES


def character_to_wiki(character):
    """Return a MediaWiki-syntax string representing the full character sheet."""
    lines = []

    # --- Identity ---
    lines.append("== Identity ==")
    lines.append(f"* '''Name:''' {character.name or '?'}")
    lines.append(f"* '''Race:''' {character.race or '?'}")
    lines.append(f"* '''Sex:''' {character.sex or '?'}")
    lines.append(f"* '''Class:''' {character.char_class or '?'}")
    lines.append(
        f"* '''Level:''' {character.level if character.level is not None else '?'}"
    )
    lines.append(f"* '''XP:''' {character.xp if character.xp is not None else '?'}")
    lines.append(f"* '''Height:''' {character.height or '?'}")
    lines.append(f"* '''Weight (body):''' {character.weight or '?'}")
    lines.append(
        f"* '''Money:''' {character.gp or '0 gp'}, "
        f"{character.sp or '0 sp'}, {character.cp or '0 cp'}"
    )
    lines.append("")

    # --- Ability Scores ---
    lines.append("== Ability Scores ==")
    for ability in Character.ABILITY_NAMES:
        label = ability.capitalize()
        if ability == "strength":
            base = character.strength
            eff_str, eff_pct = character.current_strength_and_percentile()
            if base is None:
                lines.append(f"* '''{label}:''' ?")
            elif character.percentile_strength is not None:
                pct_base = character.percentile_strength
                if base != eff_str or pct_base != eff_pct:
                    lines.append(
                        f"* '''{label}:''' {base}/{pct_base} "
                        f"(effective: {eff_str}/{eff_pct})"
                    )
                else:
                    lines.append(f"* '''{label}:''' {base}/{pct_base}")
            else:
                if base != eff_str:
                    lines.append(f"* '''{label}:''' {base} (effective: {eff_str})")
                else:
                    lines.append(f"* '''{label}:''' {base}")
        else:
            base = getattr(character, ability)
            current = character.current_ability_score(ability)
            if base is None:
                lines.append(f"* '''{label}:''' ?")
            elif base != current:
                lines.append(f"* '''{label}:''' {base} (effective: {current})")
            else:
                lines.append(f"* '''{label}:''' {base}")
    lines.append("")

    # --- Hit Points ---
    lines.append("== Hit Points ==")
    lines.append(
        f"* '''Current HP:''' {character.current_hp if character.current_hp is not None else '?'}"
    )
    max_hp = character.maximum_hp
    lines.append(f"* '''Maximum HP:''' {max_hp if max_hp is not None else '?'}")
    bodymass = character.hit_dice.filter(is_bodymass=True).first()
    if bodymass:
        lines.append(f"* '''Bodymass die:''' {bodymass.die_type} → {bodymass.roll}")
    for hd in character.hit_dice.filter(is_bodymass=False):
        bonus = f" (+{hd.con_bonus} con)" if hd.con_bonus else ""
        lines.append(f"* Level {hd.level}: {hd.die_type} → {hd.roll}{bonus}")
    lines.append("")

    # --- Encumbrance ---
    lines.append("== Encumbrance ==")
    total_wt = character.current_encumbrance
    max_enc = character.max_encumbrance
    current_ap = character.current_action_points
    lines.append(f"* '''Total carried:''' {_fmt_weight(total_wt)}")
    lines.append(
        f"* '''Max encumbrance:''' {_fmt_weight(max_enc) if max_enc is not None else '?'}"
    )
    lines.append(f"* '''Current AP:''' {current_ap}")
    tiers = character.ap_tiers
    if tiers:
        lines.append("")
        lines.append("=== AP Loss Thresholds ===")
        lines.append('{| class="wikitable"')
        lines.append("! Weight (lb) !! AP")
        for weight_lb, ap in tiers:
            lines.append("|-")
            lines.append(f"| {weight_lb:.2f} || {ap}")
        lines.append("|}")
    lines.append("")

    # --- Inventory (wikitable) ---
    lines.append("== Inventory ==")
    items = list(character.inventory.filter(container__isnull=True))
    if items:
        lines.append('{| class="wikitable"')
        lines.append("! Name !! Weight !! Status")
        for item in items:
            lines.append("|-")
            lines.append(
                f"| {item.name} || {item.adjusted_weight} || {_item_status(item)}"
            )
            for content in item.contents.all():
                lines.append("|-")
                lines.append(
                    f"| ::{content.name} || {content.adjusted_weight} || {_item_status(content)}"
                )
        lines.append("|}")
    else:
        lines.append("No items.")
    lines.append("")

    # --- Conditions ---
    lines.append("== Conditions ==")
    active_conditions = list(character.conditions.filter(is_active=True))
    if active_conditions:
        for cond in active_conditions:
            scope = f"{cond.scope} only" if cond.scope else ""
            lines.append(f"* {cond} {scope}".rstrip())
    else:
        lines.append("No active conditions.")
    lines.append("")

    # --- Spells ---
    # is_memorized is too granular for the wiki export; omitted intentionally.
    lines.append("== Spells ==")
    spells = character.spells.all()
    if spells.exists():
        spells_by_level = OrderedDict()
        for spell in spells:
            spells_by_level.setdefault(spell.level, []).append(spell.name)
        for level, names in spells_by_level.items():
            lines.append(f"=== Level {level} ===")
            for name in names:
                lines.append(f"* {name}")
    else:
        lines.append("No spells known.")
    lines.append("")

    # --- Sage Knowledge ---
    lines.append("== Sage Knowledge ==")
    if character.chosen_field or character.chosen_study:
        lines.append(f"* '''Chosen Field:''' {character.chosen_field or '?'}")
        lines.append(f"* '''Chosen Study:''' {character.chosen_study or '?'}")
        lines.append("")
    sage_rows = list(character.sage_studies.order_by("study"))
    if sage_rows:
        # Group by field (first field listed for the study, preferring class fields)
        from .sage import CLASS_FIELDS

        char_class = (character.char_class or "").lower()
        class_fields = set(CLASS_FIELDS.get(char_class, []))
        field_map = {}
        for row in sage_rows:
            study_info = SAGE_STUDIES.get(row.study, {})
            study_fields = study_info.get("fields", [])
            matching = [f for f in study_fields if f in class_fields]
            field = (
                matching[0]
                if matching
                else (study_fields[0] if study_fields else "Other")
            )
            field_map.setdefault(field, []).append(row)
        for field in sorted(field_map):
            lines.append(f"=== {field} ===")
            lines.append('{| class="wikitable"')
            lines.append("! Study !! Points !! Rank")
            for row in sorted(field_map[field], key=lambda r: r.study):
                rank = rank_for_points(row.points)
                lines.append("|-")
                lines.append(f"| {row.study} || {row.points} || {rank}")
            lines.append("|}")
            lines.append("")
    else:
        lines.append("No sage studies.")
        lines.append("")

    # --- Notes ---
    lines.append("== Notes ==")
    if character.background:
        lines.append("=== Background ===")
        lines.append(character.background)
        lines.append("")
    if character.appearance:
        lines.append("=== Appearance ===")
        lines.append(character.appearance)
        lines.append("")
    if character.notes:
        lines.append("=== Notes ===")
        lines.append(character.notes)
        lines.append("")

    return "\n".join(lines)


def _fmt_weight(qty):
    """Format a Pint weight Quantity as a short string."""
    return f"{qty.magnitude:.2f} {qty.units}"


def _item_status(item):
    parts = []
    if item.is_worn:
        parts.append("worn")
    if not item.is_carried:
        parts.append("not carried")
    return ", ".join(parts) if parts else "carried"
