"""Sage knowledge catalogue and rank logic.

Content adapted from dnd/dnd/sage.py, using the wiki's spelling of every
study and field. sage_studies is authoritative for field membership;
sage_fields is the reverse index, derived from it at import.
"""

import re

# ---------------------------------------------------------------------------
# Rank thresholds (descending). rank_for_points returns the first name
# where points >= threshold.
# ---------------------------------------------------------------------------

RANK_THRESHOLDS = [
    (100, "sage"),
    (60, "expert"),
    (30, "authority"),
    (10, "amateur"),
    (0, "unranked"),
]

RANK_ORDER = {name: i for i, (_, name) in enumerate(RANK_THRESHOLDS)}


def rank_for_points(points: int) -> str:
    """Return rank name for a point value (e.g. 61 -> 'expert')."""
    for threshold, name in RANK_THRESHOLDS:
        if points >= threshold:
            return name
    return "unranked"


# ---------------------------------------------------------------------------
# Static catalogue
# ---------------------------------------------------------------------------

sage_studies = {
    "Accompaniment": {"fields": ["Dance"]},
    "Acrobatics": {"fields": ["Circus"]},
    "Acting": {"fields": ["Drama"]},
    "Alchemy": {"fields": ["Earth & Sky", "Science"]},
    "Amphibians & Reptiles": {"fields": ["Animal Life"]},
    "Animal Performance": {"fields": ["Circus"]},
    "Animal Physiology": {"fields": ["Earth & Sky"]},
    "Animal Products": {"fields": ["Leather Work"]},
    "Architectural Aesthetics": {"fields": ["Architecture"]},
    "Artifacts": {"fields": ["Legends & Folklore"]},
    "Astronomy & Astrology": {"fields": ["Theology & Customs"]},
    "Athletics": {"fields": ["Training"]},
    "Auctionhouse": {"fields": ["Art World"]},
    "Backstabbing": {"fields": ["Skulduggery"]},
    "Baking": {"fields": ["Gastronomy"]},
    "Beachcomber": {"fields": ["Wilderland"]},
    "Beasts": {"fields": ["Legends & Folklore", "Reverence"]},
    "Birds": {"fields": ["Animal Life"]},
    "Blightlander": {"fields": ["Wilderland"]},
    "Black Market": {"fields": ["Art World"]},
    "Blood": {"fields": ["Way of the Heart"]},
    "Breath": {"fields": ["Way of the Heart"]},
    "Brewing & Distilling": {"fields": ["Gastronomy"]},
    "Bugs & Spiders": {"fields": ["Animal Life"]},
    "Burglary": {"fields": ["Theft"]},
    "Bushes & Shrubs": {"fields": ["Plant Life"]},
    "Calligraphy": {"fields": ["Way of the Spirit"]},
    "Camelback Riding": {"fields": ["Animal Training", "Animal Training (Assassin)"]},
    "Chicanery": {"fields": ["Fraud"]},
    "Claw": {"fields": ["Way of the Stick"]},
    "Clay Masonry": {"fields": ["Ceramics"]},
    "Clay Materials": {"fields": ["Ceramics"]},
    "Cloth & Materials": {"fields": ["Textiles"]},
    "Clothing": {"fields": ["Textiles"]},
    "Clowning": {"fields": ["Circus"]},
    "Coercion": {"fields": ["Streetwisdom"]},
    "College": {"fields": ["Salon"]},
    "Concealment": {"fields": ["Theft"]},
    "Construction": {"fields": ["Architecture", "Civitas (Mage)"]},
    "Cuisine": {"fields": ["Gastronomy"]},
    "Current Affairs": {"fields": ["Civitas (Mage)", "Civitas (Illusionist)"]},
    "Danse Noble": {"fields": ["Dance"]},
    "Daredevil": {"fields": ["Circus"]},
    "Delicate Metalwork": {"fields": ["Metalwork"]},
    "Demi-gods": {"fields": ["Legends & Folklore"]},
    "Direction": {"fields": ["Drama"]},
    "Divination": {"fields": ["Power", "Reverence"]},
    "Dog Training": {"fields": ["Animal Training", "Animal Training (Assassin)"]},
    "Double-dealing": {"fields": ["Fraud"]},
    "Dragon": {"fields": ["Way of the Heart"]},
    "Drawing": {"fields": ["Fine Art"]},
    "Dweomercraft": {"fields": ["Power", "Reverence"]},
    "Effigy": {"fields": ["Puppetry"]},
    "Embroidery & Print": {"fields": ["Textiles"]},
    "Empowerment": {"fields": ["Skulduggery", "Training"]},
    "Engineering": {"fields": ["Reality", "Science"]},
    "Engines": {"fields": ["Woodworking"]},
    "Faith": {"fields": ["Power"]},
    "Falconry": {"fields": ["Animal Training", "Animal Training (Assassin)"]},
    "Fist": {"fields": ["Way of the Stick"]},
    "Flowers & Sprigs": {"fields": ["Plant Life"]},
    "Flying Mounts": {"fields": ["Animal Training", "Animal Training (Assassin)"]},
    "Folk Dance": {"fields": ["Dance"]},
    "Folk Music": {"fields": ["Music"]},
    "Foot": {"fields": ["Way of the Stick"]},
    "Forester": {"fields": ["Wilderland"]},
    "Forgery": {"fields": ["Fraud"]},
    "Fortification": {"fields": ["Architecture"]},
    "Fungi": {"fields": ["Plant Life"]},
    "Geography": {"fields": ["Earth & Sky", "Humanities"]},
    "Geology": {"fields": ["Earth & Sky", "Science"]},
    "Glaze": {"fields": ["Ceramics"]},
    "Gods": {"fields": ["Theology & Customs"]},
    "Golems": {"fields": ["Animal Life", "Black Magic"]},
    "Grasses & Grains": {"fields": ["Plant Life"]},
    "Guilds": {"fields": ["Civitas (Mage)", "Civitas (Illusionist)"]},
    "Guile": {"fields": ["Grace", "Streetwisdom"]},
    "Hand": {"fields": ["Way of the Stick"]},
    "Heightened Senses": {"fields": ["Skulduggery"]},
    "Heraldry, Signs & Sigils": {"fields": ["The Church"]},
    "Heroism": {"fields": ["Legends & Folklore", "Leadership"]},
    "Hides & Skins": {"fields": ["Leather Work"]},
    "History": {"fields": ["The Church"]},
    "Horseback Riding": {"fields": ["Animal Training", "Animal Training (Assassin)"]},
    "Insight": {"fields": ["Way of the Spirit"]},
    "Instruction": {"fields": ["Salon", "Training"]},
    "Jack-of-all-Trades": {"fields": ["Grace", "Streetwisdom"]},
    "Joinery": {"fields": ["Woodworking"]},
    "Judgment": {"fields": ["Leadership"]},
    "Jungle Bushcraft": {"fields": ["Wilderland"]},
    "Language": {"fields": ["Humanities"]},
    "Law & Policy": {"fields": ["Humanities", "Theology & Customs"]},
    "Leather Armour": {"fields": ["Leather Work"]},
    "Leather Clothing": {"fields": ["Leather Work"]},
    "Leathercraft": {"fields": ["Leather Work"]},
    "Liberalism": {"fields": ["Civitas (Illusionist)"]},
    "Lockpicking": {"fields": ["Theft"]},
    "Logic & Ethics": {"fields": ["Humanities"]},
    "Logistics": {"fields": ["Leadership", "Reality"]},
    "Magic Fabrication": {"fields": ["Black Magic"]},
    "Mahout": {"fields": ["Animal Training"]},
    "Mammals": {"fields": ["Animal Life"]},
    "Martial Discipline": {"fields": ["Mastery at Arms"]},
    "Martial Music": {"fields": ["Music"]},
    "Medicine": {"fields": ["Power", "Reality", "Science"]},
    "Mercantilism": {"fields": ["Civitas (Illusionist)", "Civitas (Mage)"]},
    "Metal Armour": {"fields": ["Metalwork"]},
    "Metalsmithing": {"fields": ["Metalwork"]},
    "Military Engineering": {"fields": ["Training"]},
    "Mindfulness": {"fields": ["Way of the Spirit"]},
    "Moat": {"fields": ["Way of the Stone"]},
    "Modelling": {"fields": ["Ceramics"]},
    "Mosses & Ferns": {"fields": ["Plant Life"]},
    "Motivation": {"fields": ["Leadership"]},
    "Mountaineer": {"fields": ["Wilderland"]},
    "Murder": {"fields": ["Grace"]},
    "Mutations": {"fields": ["Unreality"]},
    "Natural Astronomy": {"fields": ["Earth & Sky"]},
    "Occultism": {"fields": ["Black Magic", "Unreality"]},
    "Oceanography": {"fields": ["Earth & Sky"]},
    "Opera": {"fields": ["Music"]},
    "Oral Tradition": {"fields": ["Literature"]},
    "Outer Planes": {"fields": ["Power"]},
    "Painting": {"fields": ["Fine Art"]},
    "Patronage": {"fields": ["Art World"]},
    "Pedestal": {"fields": ["Way of the Stone"]},
    "Physical Balance": {"fields": ["Mastery at Arms"]},
    "Physics": {"fields": ["Reality"]},
    "Pickpocketing": {"fields": ["Theft"]},
    "Piety": {"fields": ["Reverence"]},
    "Planar Travel & Gating": {"fields": ["Black Magic", "Unreality"]},
    "Playwriting": {"fields": ["Drama"]},
    "Poetry": {"fields": ["Literature"]},
    "Poisoning": {"fields": ["Grace"]},
    "Politics": {"fields": ["The Church"]},
    "Printmaking": {"fields": ["Fine Art"]},
    "Prose": {"fields": ["Literature"]},
    "Publishing": {"fields": ["Humanities"]},
    "Puissance": {"fields": ["Mastery at Arms"]},
    "Puppet-making": {"fields": ["Puppetry"]},
    "Puppeteering": {"fields": ["Puppetry"]},
    "Religious Art, Music & Design": {"fields": ["The Church"]},
    "Religious Music": {"fields": ["Music"]},
    "Research": {"fields": ["Salon"]},
    "Rhetoric": {"fields": ["Literature"]},
    "Ritual": {"fields": ["Theology & Customs"]},
    "Scouting": {"fields": ["Wilderland"]},
    "Sculpture": {"fields": ["Fine Art"]},
    "Sea Life": {"fields": ["Animal Life"]},
    "Setting Traps": {"fields": ["Skulduggery"]},
    "Shipbuilding": {"fields": ["Woodworking"]},
    "Slime Molds": {"fields": ["Animal Life"]},
    "Smoke": {"fields": ["Way of the Stone"]},
    "Social Dance": {"fields": ["Dance"]},
    "Stage Design": {"fields": ["Drama"]},
    "Steam & Gasgear": {"fields": ["Unreality"]},
    "Sure-footedness": {"fields": ["Skulduggery"]},
    "Theatrical Costuming": {"fields": ["Textiles"]},
    "Tranquility": {"fields": ["Way of the Spirit"]},
    "Trees": {"fields": ["Plant Life"]},
    "Turning": {"fields": ["Woodworking"]},
    "Unarmed Combat": {"fields": ["Mastery at Arms"]},
    "Underwater Mounts": {"fields": ["Animal Training"]},
    "Urban Sense": {"fields": ["Streetwisdom"]},
    "Use of Building Materials": {"fields": ["Architecture"]},
    "Wall": {"fields": ["Way of the Stone"]},
    "Weaponwright": {"fields": ["Metalwork"]},
    "Yin & Yang": {"fields": ["Way of the Heart"]},
}


def _invert_studies(studies: dict) -> dict:
    """Build the field -> studies index by inverting sage_studies.

    sage_studies is the single source of truth for field membership, so the
    reverse index is derived rather than maintained by hand; the two cannot
    drift apart. Fields and their study lists are both alphabetical.
    """
    index: dict[str, dict] = {}
    for study, meta in sorted(studies.items()):
        for field in meta["fields"]:
            index.setdefault(field, {"studies": []})["studies"].append(study)
    return {field: index[field] for field in sorted(index)}


sage_fields = _invert_studies(sage_studies)


# ---------------------------------------------------------------------------
# Class -> fields mapping
# ---------------------------------------------------------------------------

CLASS_FIELDS = {
    "assassin": [
        "Animal Training (Assassin)",
        "Grace",
        "Mastery at Arms",
        "Skulduggery",
    ],
    "bard": [
        "Architecture",
        "Art World",
        "Ceramics",
        "Circus",
        "Dance",
        "Drama",
        "Fine Art",
        "Gastronomy",
        "Leather Work",
        "Literature",
        "Metalwork",
        "Music",
        "Puppetry",
        "Salon",
        "Textiles",
        "Woodworking",
    ],
    "cleric": ["Legends & Folklore", "Power", "The Church", "Theology & Customs"],
    "druid": ["Animal Life", "Earth & Sky", "Plant Life"],
    "fighter": ["Animal Training", "Leadership", "Mastery at Arms", "Training"],
    "illusionist": ["Civitas (Illusionist)", "Humanities", "Reality", "Unreality"],
    "mage": ["Civitas (Mage)", "Humanities", "Black Magic", "Science"],
    "monk": [
        "Way of the Heart",
        "Way of the Spirit",
        "Way of the Stick",
        "Way of the Stone",
    ],
    "paladin": ["Animal Training", "Mastery at Arms", "Leadership", "Reverence"],
    "ranger": ["Animal Training", "Mastery at Arms", "Training", "Wilderland"],
    "thief": ["Fraud", "Skulduggery", "Streetwisdom", "Theft"],
}


# ---------------------------------------------------------------------------
# Canonical spelling
# ---------------------------------------------------------------------------

# Spellings Zingor and the Adventure wiki have historically disagreed on, in
# whichever direction. Folded away before matching so either form resolves.
_SPELLING_VARIANTS = {"armour": "armor"}


def _normalize(name: str) -> str:
    """Reduce a name to the form used to match catalogue entries.

    Case, punctuation, and "and" versus "&" are all noise: an Adventure wiki
    page is hand-written, so the same study appears as "Bugs & Spiders",
    "Bugs and Spiders", or "bugs and spiders" depending on who typed it.
    """
    name = name.lower().replace("&", "and")
    for variant, canonical in _SPELLING_VARIANTS.items():
        name = name.replace(variant, canonical)
    return re.sub(r"[^a-z0-9]", "", name)


_STUDIES_BY_NORMALIZED = {_normalize(name): name for name in sage_studies}
_FIELDS_BY_NORMALIZED = {_normalize(name): name for name in sage_fields}


def canonical_study(name: str) -> str:
    """Return the catalogue's spelling of a study, or the name unchanged.

    A name with no catalogue entry is passed through rather than rejected:
    studies arrive as freetext from the wiki, and an unrecognised one is
    displayed under the sheet's "Other" heading instead of being dropped.
    """
    return _STUDIES_BY_NORMALIZED.get(_normalize(name), name)


def canonical_field(name: str) -> str:
    """Return the catalogue's spelling of a field, or the name unchanged."""
    return _FIELDS_BY_NORMALIZED.get(_normalize(name), name)


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def sort_sage_entries(
    entries: dict,
    sort_keys: list | None = None,
) -> list:
    """Flatten {name: points} into sorted list of {name, points, rank, rank_order} dicts.

    sort_keys: list of 'name', 'points', 'rank' (prefix '-' for descending).
    Defaults to ['rank', 'name'] (best rank first, then alphabetical).
    rank_order: {sage:0, expert:1, authority:2, amateur:3, unranked:4} — lower = better.
    """
    if sort_keys is None:
        sort_keys = ["rank", "name"]
    result = []
    for name, points in entries.items():
        rank = rank_for_points(points)
        result.append(
            {
                "name": name,
                "points": points,
                "rank": rank,
                "rank_order": RANK_ORDER[rank],
            }
        )
    for key in reversed(sort_keys):
        descending = key.startswith("-")
        field = key.lstrip("-")
        if field == "rank":
            result.sort(key=lambda e: e["rank_order"], reverse=descending)
        elif field == "name":
            result.sort(key=lambda e: e["name"].lower(), reverse=descending)
        elif field == "points":
            result.sort(key=lambda e: e["points"], reverse=descending)
    return result


def rank_studies(study_dict: dict) -> dict:
    """Categorize studies based on their values into the four sage ranks."""
    result = {"sage": {}, "expert": {}, "authority": {}, "amateur": {}, "unranked": {}}
    for study, value in study_dict.items():
        rank = rank_for_points(value)
        result[rank][study] = value
    return result
