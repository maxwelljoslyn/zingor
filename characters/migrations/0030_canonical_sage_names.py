"""Store existing sage studies and fields under the wiki's spelling.

The catalogue was ported from a private campaign that renamed some of the
wiki's studies and fields, so rows written before the correction carry names
the catalogue no longer contains; on the sheet they group under "Other".

The canonical names and the matching rule are frozen copies of
characters/sage.py as it stood at this migration, deliberately not imported:
a migration is replayed against old databases, so a later rename must not
change what this one does.
"""

import re

from django.db import migrations

CANONICAL_STUDIES = [
    "Accompaniment",
    "Acrobatics",
    "Acting",
    "Alchemy",
    "Amphibians & Reptiles",
    "Animal Performance",
    "Animal Physiology",
    "Animal Products",
    "Architectural Aesthetics",
    "Artifacts",
    "Astronomy & Astrology",
    "Athletics",
    "Auctionhouse",
    "Backstabbing",
    "Baking",
    "Beachcomber",
    "Beasts",
    "Birds",
    "Black Market",
    "Blightlander",
    "Blood",
    "Breath",
    "Brewing & Distilling",
    "Bugs & Spiders",
    "Burglary",
    "Bushes & Shrubs",
    "Calligraphy",
    "Camelback Riding",
    "Chicanery",
    "Claw",
    "Clay Masonry",
    "Clay Materials",
    "Cloth & Materials",
    "Clothing",
    "Clowning",
    "Coercion",
    "College",
    "Concealment",
    "Construction",
    "Cuisine",
    "Current Affairs",
    "Danse Noble",
    "Daredevil",
    "Delicate Metalwork",
    "Demi-gods",
    "Direction",
    "Divination",
    "Dog Training",
    "Double-dealing",
    "Dragon",
    "Drawing",
    "Dweomercraft",
    "Effigy",
    "Embroidery & Print",
    "Empowerment",
    "Engineering",
    "Engines",
    "Faith",
    "Falconry",
    "Fist",
    "Flowers & Sprigs",
    "Flying Mounts",
    "Folk Dance",
    "Folk Music",
    "Foot",
    "Forester",
    "Forgery",
    "Fortification",
    "Fungi",
    "Geography",
    "Geology",
    "Glaze",
    "Gods",
    "Golems",
    "Grasses & Grains",
    "Guilds",
    "Guile",
    "Hand",
    "Heightened Senses",
    "Heraldry, Signs & Sigils",
    "Heroism",
    "Hides & Skins",
    "History",
    "Horseback Riding",
    "Insight",
    "Instruction",
    "Jack-of-all-Trades",
    "Joinery",
    "Judgment",
    "Jungle Bushcraft",
    "Language",
    "Law & Policy",
    "Leather Armour",
    "Leather Clothing",
    "Leathercraft",
    "Liberalism",
    "Lockpicking",
    "Logic & Ethics",
    "Logistics",
    "Magic Fabrication",
    "Mahout",
    "Mammals",
    "Martial Discipline",
    "Martial Music",
    "Medicine",
    "Mercantilism",
    "Metal Armour",
    "Metalsmithing",
    "Military Engineering",
    "Mindfulness",
    "Moat",
    "Modelling",
    "Mosses & Ferns",
    "Motivation",
    "Mountaineer",
    "Murder",
    "Mutations",
    "Natural Astronomy",
    "Occultism",
    "Oceanography",
    "Opera",
    "Oral Tradition",
    "Outer Planes",
    "Painting",
    "Patronage",
    "Pedestal",
    "Physical Balance",
    "Physics",
    "Pickpocketing",
    "Piety",
    "Planar Travel & Gating",
    "Playwriting",
    "Poetry",
    "Poisoning",
    "Politics",
    "Printmaking",
    "Prose",
    "Publishing",
    "Puissance",
    "Puppet-making",
    "Puppeteering",
    "Religious Art, Music & Design",
    "Religious Music",
    "Research",
    "Rhetoric",
    "Ritual",
    "Scouting",
    "Sculpture",
    "Sea Life",
    "Setting Traps",
    "Shipbuilding",
    "Slime Molds",
    "Smoke",
    "Social Dance",
    "Stage Design",
    "Steam & Gasgear",
    "Sure-footedness",
    "Theatrical Costuming",
    "Tranquility",
    "Trees",
    "Turning",
    "Unarmed Combat",
    "Underwater Mounts",
    "Urban Sense",
    "Use of Building Materials",
    "Wall",
    "Weaponwright",
    "Yin & Yang",
]

CANONICAL_FIELDS = [
    "Animal Life",
    "Animal Training",
    "Animal Training (Assassin)",
    "Architecture",
    "Art World",
    "Black Magic",
    "Ceramics",
    "Circus",
    "Civitas (Illusionist)",
    "Civitas (Mage)",
    "Dance",
    "Drama",
    "Earth & Sky",
    "Fine Art",
    "Fraud",
    "Gastronomy",
    "Grace",
    "Humanities",
    "Leadership",
    "Leather Work",
    "Legends & Folklore",
    "Literature",
    "Mastery at Arms",
    "Metalwork",
    "Music",
    "Plant Life",
    "Power",
    "Puppetry",
    "Reality",
    "Reverence",
    "Salon",
    "Science",
    "Skulduggery",
    "Streetwisdom",
    "Textiles",
    "The Church",
    "Theft",
    "Theology & Customs",
    "Training",
    "Unreality",
    "Way of the Heart",
    "Way of the Spirit",
    "Way of the Stick",
    "Way of the Stone",
    "Wilderland",
    "Woodworking",
]

_SPELLING_VARIANTS = {"armour": "armor"}


def _normalize(name):
    """Reduce a name to the form used to match catalogue entries."""
    name = name.lower().replace("&", "and")
    for variant, canonical in _SPELLING_VARIANTS.items():
        name = name.replace(variant, canonical)
    return re.sub(r"[^a-z0-9]", "", name)


def _rename(model, attr, canonical_names, merge):
    """Rewrite one model's names in place, merging rows that collide.

    Both models carry a per-character unique key on the name, so a character
    holding a study under two spellings — a hidden row from before the
    correction alongside the one the wiki resurrected, say — cannot simply
    have the stale row renamed. The rows are merged instead, and the merge
    keeps whichever value loses least: see the callers.
    """
    lookup = {_normalize(name): name for name in canonical_names}
    for character_id in (
        model.objects.values_list("character_id", flat=True).distinct().order_by()
    ):
        rows = list(model.objects.filter(character_id=character_id))
        survivors = {}
        merged = set()
        for row in rows:
            name = getattr(row, attr)
            canonical = lookup.get(_normalize(name), name)
            kept = survivors.get(canonical)
            if kept is None:
                survivors[canonical] = row
                continue
            # Prefer a row already carrying the canonical name as the survivor,
            # so the row that stays is the one other data most likely refers to.
            if getattr(kept, attr) != canonical and name == canonical:
                survivors[canonical], row = row, kept
                kept = survivors[canonical]
            merge(kept, row)
            merged.add(canonical)
            row.delete()
        # Renaming only after every duplicate for this character is gone, so a
        # rename can never land on a name the unique key still holds.
        for canonical, row in survivors.items():
            renamed = getattr(row, attr) != canonical
            if renamed:
                setattr(row, attr, canonical)
            if canonical in merged:
                row.save()
            elif renamed:
                row.save(update_fields=[attr])


def _merge_studies(kept, dropped):
    """Fold a duplicate study row into the one being kept.

    Points take the higher of the two rather than the sum: both rows describe
    the same study, so adding them would invent knowledge. A study stays
    visible if either row was visible — an unwanted study can be hidden again
    in one click, whereas one hidden by this migration would never be noticed.
    """
    kept.points = max(kept.points, dropped.points)
    kept.chosen = kept.chosen or dropped.chosen
    kept.hidden = kept.hidden and dropped.hidden


def _merge_fields(kept, dropped):
    """Chosen fields carry no state beyond existing, so there is nothing to
    fold in; the duplicate is simply dropped."""


def forwards(apps, schema_editor):
    _rename(
        apps.get_model("characters", "SageStudyPoints"),
        "study",
        CANONICAL_STUDIES,
        _merge_studies,
    )
    _rename(
        apps.get_model("characters", "SageChosenField"),
        "field",
        CANONICAL_FIELDS,
        _merge_fields,
    )


class Migration(migrations.Migration):
    dependencies = [
        ("characters", "0029_multiple_chosen_sage_fields"),
    ]

    # Irreversible in substance rather than in principle: merged rows cannot be
    # split back apart, and the old spellings are not recorded anywhere.
    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
