# Wiki Export Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a "Export to Wiki" button on the character sheet that calls a backend route, generates MediaWiki-syntax markup for the full character, and displays it in a modal with a clipboard-copy button.

**Architecture:** New `wiki_export.py` module holds the pure formatting function. A new GET view calls it and returns an HTML partial (modal fragment) via HTMX. The character sheet gets a button + empty swap-target div; the modal includes a `<textarea>` and a plain-JS copy button.

**Tech Stack:** Django, HTMX 2.x, vanilla JS (`navigator.clipboard`), MediaWiki wikitext syntax.

---

### Task 1: `wiki_export.py` — pure formatting function

**Files:**
- Create: `characters/wiki_export.py`
- Test: `characters/tests/test_wiki_export.py`

**Step 1: Write the failing test**

```python
# characters/tests/test_wiki_export.py
from django.test import TestCase
from django.contrib.auth import get_user_model
from characters.models import Character, Item, Spell, Condition, HitDie
from characters.wiki_export import character_to_wiki

User = get_user_model()


class WikiExportTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("tester", password="x")
        self.char = Character.objects.create(
            user=self.user,
            name="Aldric",
            race="human",
            sex="male",
            char_class="fighter",
            level=3,
            xp=6000,
            strength=17,
            dexterity=14,
            constitution=15,
            intelligence=10,
            wisdom=12,
            charisma=8,
            current_hp=22,
        )

    def test_identity_section_present(self):
        wiki = character_to_wiki(self.char)
        assert "== Identity ==" in wiki
        assert "Aldric" in wiki
        assert "fighter" in wiki

    def test_ability_scores_section(self):
        wiki = character_to_wiki(self.char)
        assert "== Ability Scores ==" in wiki
        assert "Strength" in wiki
        assert "17" in wiki

    def test_inventory_wikitable(self):
        Item.objects.create(owner=self.char, name="Longsword", weight="4 lb")
        wiki = character_to_wiki(self.char)
        assert "== Inventory ==" in wiki
        assert '{| class="wikitable"' in wiki
        assert "Longsword" in wiki

    def test_spells_section(self):
        Spell.objects.create(character=self.char, name="Magic Missile", level=1)
        wiki = character_to_wiki(self.char)
        assert "== Spells ==" in wiki
        assert "Magic Missile" in wiki

    def test_empty_inventory_no_table(self):
        wiki = character_to_wiki(self.char)
        assert "No items." in wiki
        assert '{| class="wikitable"' not in wiki

    def test_notes_section(self):
        self.char.background = "Born in a village."
        self.char.save()
        wiki = character_to_wiki(self.char)
        assert "== Notes ==" in wiki
        assert "Born in a village." in wiki
```

**Step 2: Run test to verify it fails**

```bash
cd /Users/maxwelljoslyn/Desktop/projects/alexis-campaign/zingor
uv run python manage.py test characters.tests.test_wiki_export --verbosity=2
```

Expected: `ImportError: cannot import name 'character_to_wiki'`

**Step 3: Write implementation**

```python
# characters/wiki_export.py
"""Convert a Character instance to MediaWiki markup."""

from collections import OrderedDict

from .models import Character


def character_to_wiki(character):
    """Return a MediaWiki-syntax string representing the full character sheet."""
    lines = []

    # --- Identity ---
    lines.append("== Identity ==")
    lines.append(f"* '''Name:''' {character.name or '?'}")
    lines.append(f"* '''Race:''' {character.race or '?'}")
    lines.append(f"* '''Sex:''' {character.sex or '?'}")
    lines.append(f"* '''Class:''' {character.char_class or '?'}")
    lines.append(f"* '''Level:''' {character.level if character.level is not None else '?'}")
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

    # --- Inventory (wikitable) ---
    lines.append("== Inventory ==")
    items = list(character.inventory.filter(container__isnull=True))
    if items:
        lines.append('{| class="wikitable"')
        lines.append("! Name !! Weight !! Status")
        for item in items:
            lines.append("|-")
            lines.append(f"| {item.name} || {item.adjusted_weight} || {_item_status(item)}")
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
            lines.append(f"* {cond}")
    else:
        lines.append("No active conditions.")
    lines.append("")

    # --- Spells ---
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


def _item_status(item):
    parts = []
    if item.is_worn:
        parts.append("worn")
    if not item.is_carried:
        parts.append("not carried")
    return ", ".join(parts) if parts else "carried"
```

**Step 4: Run test to verify it passes**

```bash
uv run python manage.py test characters.tests.test_wiki_export --verbosity=2
```

Expected: all 6 tests PASS

**Step 5: Commit**

```bash
git add characters/wiki_export.py characters/tests/test_wiki_export.py
git commit -m "feat: add character_to_wiki export function"
```

---

### Task 2: Backend view and URL

**Files:**
- Modify: `characters/views.py` (add `wiki_export` view at the bottom)
- Modify: `characters/urls.py` (add URL pattern)

**Step 1: Add view to `views.py`**

Add this at the end of `characters/views.py`:

```python
# --- Wiki export ---


@login_required
def wiki_export(request, pk):
    character = get_object_or_404(Character, pk=pk, user=request.user)
    from .wiki_export import character_to_wiki
    wiki_text = character_to_wiki(character)
    return render(request, "characters/partials/wiki_modal.html", {"wiki_text": wiki_text})
```

**Step 2: Add URL to `urls.py`**

Inside `urlpatterns`, after the section-refresh path, add:

```python
path(
    "character/<int:pk>/wiki-export/",
    views.wiki_export,
    name="wiki_export",
),
```

**Step 3: Verify with Django check**

```bash
uv run python manage.py check
```

Expected: `System check identified no issues.`

**Step 4: Commit**

```bash
git add characters/views.py characters/urls.py
git commit -m "feat: add wiki_export view and URL"
```

---

### Task 3: Modal template

**Files:**
- Create: `characters/templates/characters/partials/wiki_modal.html`

**Step 1: Write the template**

```html
<!-- characters/templates/characters/partials/wiki_modal.html -->
<div id="wiki-modal"
     style="position:fixed;inset:0;background:rgba(0,0,0,0.7);
            display:flex;align-items:center;justify-content:center;z-index:1000;">
  <div style="background:var(--surface);border:1px solid var(--border);
              border-radius:6px;padding:1.5rem;max-width:700px;width:90%;
              max-height:80vh;display:flex;flex-direction:column;gap:0.75rem;">
    <div style="display:flex;justify-content:space-between;align-items:center;">
      <h2 style="color:var(--accent);margin:0;">Wiki Export</h2>
      <button class="btn btn-secondary btn-small"
              onclick="document.getElementById('wiki-modal').remove()">Close</button>
    </div>
    <textarea id="wiki-export-text"
              readonly
              style="flex:1;min-height:400px;font-family:monospace;
                     font-size:0.85rem;resize:vertical;
                     background:var(--bg);color:var(--text);
                     border:1px solid var(--border);border-radius:4px;padding:0.5rem;">{{ wiki_text }}</textarea>
    <button class="btn"
            onclick="
              navigator.clipboard.writeText(
                document.getElementById('wiki-export-text').value
              ).then(function() {
                var btn = event.target;
                var orig = btn.textContent;
                btn.textContent = 'Copied!';
                btn.disabled = true;
                setTimeout(function(){ btn.textContent = orig; btn.disabled = false; }, 1500);
              });
            ">Copy to Clipboard</button>
  </div>
</div>
```

**Step 2: Verify Django can find the template**

```bash
uv run python manage.py check
```

Expected: no errors.

**Step 3: Commit**

```bash
git add characters/templates/characters/partials/wiki_modal.html
git commit -m "feat: add wiki_modal partial template"
```

---

### Task 4: Wire up the button in character_sheet.html

**Files:**
- Modify: `characters/templates/characters/character_sheet.html`

**Step 1: Add button to toolbar and modal container div**

In `character_sheet.html`, add the "Export to Wiki" button inside the existing `.toolbar` div (alongside Undo/Redo/Back), and add the modal swap-target div after `</div>` (closing `#sheet-body`).

Replace the toolbar `<div class="toolbar">` block so it reads:

```html
  <div class="toolbar">
    <button hx-post="/character/{{ character.pk }}/undo/"
            hx-target="#sheet-body"
            hx-swap="innerHTML"
            hx-headers='{"X-CSRFToken": "{{ csrf_token }}"}'
            class="btn btn-secondary btn-small">Undo</button>
    <button hx-post="/character/{{ character.pk }}/redo/"
            hx-target="#sheet-body"
            hx-swap="innerHTML"
            hx-headers='{"X-CSRFToken": "{{ csrf_token }}"}'
            class="btn btn-secondary btn-small">Redo</button>
    <button hx-get="/character/{{ character.pk }}/wiki-export/"
            hx-target="#wiki-modal"
            hx-swap="innerHTML"
            class="btn btn-secondary btn-small">Export to Wiki</button>
    <a href="/" class="btn btn-secondary btn-small">Back to List</a>
  </div>
```

And after the closing `</div>` of `#sheet-body`, add:

```html
<div id="wiki-modal"></div>
```

**Step 2: Manual smoke test**

Start the dev server and navigate to a character sheet. Click "Export to Wiki". The modal should appear with wikitext. Click "Copy to Clipboard" — the button text should briefly change to "Copied!". Click "Close" — the modal should disappear.

```bash
uv run python manage.py runserver
```

**Step 3: Commit**

```bash
git add characters/templates/characters/character_sheet.html
git commit -m "feat: wire Export to Wiki button to modal on character sheet"
```
