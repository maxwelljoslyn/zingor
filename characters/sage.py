"""Sage knowledge catalogue and rank logic.

Content adapted from dnd/dnd/sage.py. sage_fields is authoritative for
validation; sage_studies provides reverse lookups.
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
    "Alchemy": {"fields": ["Earth and Sky", "Science"]},
    "Amphibians and Reptiles": {"fields": ["Animal Life"]},
    "Animal Performance": {"fields": ["Circus"]},
    "Animal Physiology": {
        "alexis_fields": ["Earth and Sky"],
        "fields": ["Animal Life"],
    },
    "Animal Products": {"fields": ["Leatherwork"]},
    "Architectural Aesthetics": {"fields": ["Architecture"]},
    "Artifacts": {"fields": ["Legends and Folklore"]},
    "Astronomy and Astrology": {"fields": ["Theology and Customs"]},
    "Athletics": {"fields": ["Training"]},
    "Auctionhouse": {"fields": ["Art World"]},
    "Backstabbing": {"fields": ["Skulduggery"]},
    "Baking": {"fields": ["Gastronomy"]},
    "Beachcomber": {"fields": ["Wilderland"]},
    "Beasts": {"fields": ["Legends and Folklore", "Reverence"]},
    "Birds": {"fields": ["Animal Life"]},
    "Blightlander": {"fields": ["Wilderland"]},
    "Black Market": {"fields": ["Art World"]},
    "Blood": {"fields": ["Way of the Heart"]},
    "Breath": {"fields": ["Way of the Heart"]},
    "Brewing and Distilling": {"fields": ["Gastronomy"]},
    "Bugs and Spiders": {"fields": ["Animal Life"]},
    "Burglary": {"fields": ["Theft"]},
    "Bushes and Shrubs": {"fields": ["Plant Life"]},
    "Calligraphy": {"fields": ["Way of the Spirit"]},
    "Camelback Riding": {"fields": ["Animal Training", "Animal Training (Assassin)"]},
    "Chicanery": {"fields": ["Fraud"]},
    "Claw": {"fields": ["Way of the Stick"]},
    "Clay Masonry": {"fields": ["Ceramics"]},
    "Clay Materials": {"fields": ["Ceramics"]},
    "Cloth and Materials": {"fields": ["Textiles"]},
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
    "Demi-Gods": {"fields": ["Legends and Folklore"]},
    "Direction": {"fields": ["Drama"]},
    "Divination": {"fields": ["Power", "Reverence"]},
    "Dog Training": {"fields": ["Animal Training", "Animal Training (Assassin)"]},
    "Double-Dealing": {"alexis_name": "Double-dealing", "fields": ["Fraud"]},
    "Dragon": {"fields": ["Way of the Heart"]},
    "Drawing": {"fields": ["Fine Art"]},
    "Dweomercraft": {"fields": ["Power", "Reverence"]},
    "Effigy": {"fields": ["Puppetry"]},
    "Embroidery and Print": {"fields": ["Textiles"]},
    "Empowerment": {"fields": ["Skulduggery", "Training"]},
    "Engineering": {"fields": ["Reality", "Science"]},
    "Engines": {"fields": ["Woodworking"]},
    "Faith": {"fields": ["Power"]},
    "Falconry": {"fields": ["Animal Training", "Animal Training (Assassin)"]},
    "Fist": {"fields": ["Way of the Stick"]},
    "Flowers and Sprigs": {"fields": ["Plant Life"]},
    "Flying Mounts": {"fields": ["Animal Training", "Animal Training (Assassin)"]},
    "Folk Dance": {"fields": ["Dance"]},
    "Folk Music": {"fields": ["Music"]},
    "Foot": {"fields": ["Way of the Stick"]},
    "Forester": {"fields": ["Wilderland"]},
    "Forgery": {"fields": ["Fraud"]},
    "Fortification": {"fields": ["Architecture"]},
    "Fungi": {"fields": ["Plant Life"]},
    "Geography": {"fields": ["Earth and Sky", "Humanities"]},
    "Geology": {"fields": ["Earth and Sky", "Science"]},
    "Glaze": {"fields": ["Ceramics"]},
    "Gods": {"fields": ["Theology and Customs"]},
    "Golems": {"fields": ["Animal Life", "Black Magic"]},
    "Grasses and Grains": {"fields": ["Plant Life"]},
    "Guilds": {"fields": ["Civitas (Mage)", "Civitas (Illusionist)"]},
    "Guile": {"fields": ["Grace", "Streetwisdom"]},
    "Hand": {"fields": ["Way of the Stick"]},
    "Heightened Senses": {"fields": ["Skulduggery"]},
    "Heraldry, Signs, and Sigils": {
        "alexis_name": "Heraldry, Signs & Sigils",
        "fields": ["The Church"],
    },
    "Heroism": {"fields": ["Legends and Folklore", "Leadership"]},
    "Hides and Skins": {"fields": ["Leatherwork"]},
    "History": {"fields": ["The Church"]},
    "Horseback Riding": {"fields": ["Animal Training", "Animal Training (Assassin)"]},
    "Insight": {"fields": ["Way of the Spirit"]},
    "Instruction": {"fields": ["Salon", "Training"]},
    "Jack-of-All-Trades": {
        "alexis_name": "Jack-of-all-Trades",
        "fields": ["Grace", "Streetwisdom"],
    },
    "Joinery": {"fields": ["Woodworking"]},
    "Judgment": {"fields": ["Leadership"]},
    "Jungle Bushcraft": {"fields": ["Wilderland"]},
    "Language": {"fields": ["Humanities"]},
    "Law and Policy": {"fields": ["Humanities", "Theology and Customs"]},
    "Leather Armor": {"fields": ["Leatherwork"]},
    "Leather Clothing": {"fields": ["Leatherwork"]},
    "Leathercraft": {"fields": ["Leatherwork"]},
    "Liberalism": {"fields": ["Civitas (Illusionist)"]},
    "Lockpicking": {"fields": ["Theft"]},
    "Logic and Ethics": {"fields": ["Humanities"]},
    "Logistics": {"fields": ["Leadership", "Reality"]},
    "Magic Fabrication": {"fields": ["Black Magic"]},
    "Mahout": {"fields": ["Animal Training"]},
    "Mammals": {"fields": ["Animal Life"]},
    "Martial Discipline": {"fields": ["Mastery at Arms"]},
    "Martial Music": {"fields": ["Music"]},
    "Medicine": {"fields": ["Power", "Reality", "Science"]},
    "Mercantilism": {"fields": ["Civitas (Illusionist)", "Civitas (Mage)"]},
    "Metal Armor": {"fields": ["Metalwork"]},
    "Metalsmithing": {"fields": ["Metalwork"]},
    "Military Engineering": {"fields": ["Training"]},
    "Mindfulness": {"fields": ["Way of the Spirit"]},
    "Moat": {"fields": ["Way of the Stone"]},
    "Modelling": {"fields": ["Ceramics"]},
    "Mosses and Ferns": {"fields": ["Plant Life"]},
    "Motivation": {"fields": ["Leadership"]},
    "Mountaineer": {"fields": ["Wilderland"]},
    "Murder": {"fields": ["Grace"]},
    "Mutations": {"fields": ["Unreality"]},
    "Natural Astronomy": {"fields": ["Earth and Sky"]},
    "Occultism": {"fields": ["Black Magic", "Unreality"]},
    "Oceanography": {"fields": ["Earth and Sky"]},
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
    "Planar Travel and Gating": {"fields": ["Black Magic", "Unreality"]},
    "Playwriting": {"fields": ["Drama"]},
    "Poetry": {"fields": ["Literature"]},
    "Poisoning": {"fields": ["Grace"]},
    "Politics": {"fields": ["The Church"]},
    "Printmaking": {"fields": ["Fine Art"]},
    "Prose": {"fields": ["Literature"]},
    "Publishing": {"fields": ["Humanities"]},
    "Puissance": {"fields": ["Mastery at Arms"]},
    "Puppet-Making": {"alexis_name": "Puppet-making", "fields": ["Puppetry"]},
    "Puppeteering": {"fields": ["Puppetry"]},
    "Religious Art, Music, and Design": {
        "alexis_name": "Religious Art, Music and Design",
        "fields": ["The Church"],
    },
    "Religious Music": {"fields": ["Music"]},
    "Research": {"fields": ["Salon"]},
    "Rhetoric": {"fields": ["Literature"]},
    "Ritual": {"fields": ["Theology and Customs"]},
    "Scouting": {"fields": ["Wilderland"]},
    "Sculpture": {"fields": ["Fine Art"]},
    "Sea Life": {"fields": ["Animal Life"]},
    "Setting Traps": {"fields": ["Skulduggery"]},
    "Shipbuilding": {"fields": ["Woodworking"]},
    "Slime Molds": {"fields": ["Animal Life"]},
    "Smoke": {"fields": ["Way of the Stone"]},
    "Social Dance": {"fields": ["Dance"]},
    "Stage Design": {"fields": ["Drama"]},
    "Steam and Gasgear": {"fields": ["Unreality"]},
    "Sure-Footedness": {"alexis_name": "Sure-footedness", "fields": ["Skulduggery"]},
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
    "Yin and Yang": {"fields": ["Way of the Heart"]},
}


sage_fields = {
    "Animal Life": {
        "studies": [
            "Amphibians and Reptiles",
            "Animal Physiology",
            "Birds",
            "Bugs and Spiders",
            "Golems",
            "Mammals",
            "Sea Life",
            "Slime Molds",
        ]
    },
    "Animal Training": {
        "studies": [
            "Camelback Riding",
            "Dog Training",
            "Falconry",
            "Flying Mounts",
            "Horseback Riding",
            "Mahout",
            "Underwater Mounts",
        ]
    },
    "Animal Training (Assassin)": {
        "studies": [
            "Camelback Riding",
            "Dog Training",
            "Falconry",
            "Flying Mounts",
            "Horseback Riding",
        ],
    },
    "Architecture": {
        "studies": [
            "Architectural Aesthetics",
            "Construction",
            "Fortification",
            "Use of Building Materials",
        ]
    },
    "Art World": {"studies": ["Auctionhouse", "Black Market", "Patronage"]},
    "Black Magic": {
        "studies": [
            "Golems",
            "Magic Fabrication",
            "Occultism",
            "Planar Travel and Gating",
        ]
    },
    "Ceramics": {"studies": ["Clay Masonry", "Clay Materials", "Glaze", "Modelling"]},
    "Circus": {
        "studies": ["Acrobatics", "Animal Performance", "Clowning", "Daredevil"]
    },
    "Civitas (Illusionist)": {
        "studies": ["Current Affairs", "Guilds", "Liberalism", "Mercantilism"],
    },
    "Civitas (Mage)": {
        "studies": ["Construction", "Current Affairs", "Guilds", "Mercantilism"],
    },
    "Dance": {
        "studies": ["Accompaniment", "Danse Noble", "Folk Dance", "Social Dance"]
    },
    "Drama": {"studies": ["Acting", "Direction", "Playwriting", "Stage Design"]},
    "Earth and Sky": {
        "studies": [
            "Alchemy",
            "Geography",
            "Geology",
            "Natural Astronomy",
            "Oceanography",
        ],
    },
    "Fine Art": {"studies": ["Drawing", "Painting", "Printmaking", "Sculpture"]},
    "Fraud": {"studies": ["Chicanery", "Double-Dealing", "Forgery"]},
    "Gastronomy": {"studies": ["Baking", "Brewing and Distilling", "Cuisine"]},
    "Grace": {"studies": ["Guile", "Jack-of-All-Trades", "Murder", "Poisoning"]},
    "Humanities": {
        "studies": [
            "Geography",
            "Language",
            "Law and Policy",
            "Logic and Ethics",
            "Publishing",
        ]
    },
    "Leadership": {"studies": ["Heroism", "Judgment", "Logistics", "Motivation"]},
    "Leatherwork": {
        "alexis_name": "Leather Work",
        "studies": [
            "Animal Products",
            "Hides and Skins",
            "Leather Armor",
            "Leather Clothing",
            "Leathercraft",
        ],
    },
    "Legends and Folklore": {
        "studies": ["Artifacts", "Beasts", "Demi-Gods", "Heroism"],
    },
    "Literature": {"studies": ["Oral Tradition", "Poetry", "Prose", "Rhetoric"]},
    "Mastery at Arms": {
        "studies": [
            "Martial Discipline",
            "Physical Balance",
            "Puissance",
            "Unarmed Combat",
        ]
    },
    "Metalwork": {
        "studies": [
            "Delicate Metalwork",
            "Metal Armor",
            "Metalsmithing",
            "Weaponwright",
        ]
    },
    "Music": {"studies": ["Folk Music", "Martial Music", "Opera", "Religious Music"]},
    "Plant Life": {
        "studies": [
            "Bushes and Shrubs",
            "Flowers and Sprigs",
            "Fungi",
            "Grasses and Grains",
            "Mosses and Ferns",
            "Trees",
        ]
    },
    "Power": {
        "studies": ["Divination", "Dweomercraft", "Faith", "Medicine", "Outer Planes"]
    },
    "Puppetry": {"studies": ["Effigy", "Puppet-Making", "Puppeteering"]},
    "Reality": {"studies": ["Engineering", "Logistics", "Medicine", "Physics"]},
    "Reverence": {"studies": ["Beasts", "Divination", "Dweomercraft", "Piety"]},
    "Salon": {"studies": ["College", "Instruction", "Research"]},
    "Science": {"studies": ["Alchemy", "Engineering", "Geology", "Medicine"]},
    "Skulduggery": {
        "studies": [
            "Backstabbing",
            "Empowerment",
            "Heightened Senses",
            "Setting Traps",
            "Sure-Footedness",
        ]
    },
    "Streetwisdom": {
        "studies": ["Coercion", "Guile", "Jack-of-All-Trades", "Urban Sense"]
    },
    "Textiles": {
        "studies": [
            "Cloth and Materials",
            "Clothing",
            "Embroidery and Print",
            "Theatrical Costuming",
        ]
    },
    "The Church": {
        "studies": [
            "Heraldry, Signs, and Sigils",
            "History",
            "Politics",
            "Religious Art, Music, and Design",
        ]
    },
    "Theft": {"studies": ["Burglary", "Concealment", "Lockpicking", "Pickpocketing"]},
    "Theology and Customs": {
        "studies": ["Astronomy and Astrology", "Gods", "Law and Policy", "Ritual"],
    },
    "Training": {
        "studies": ["Athletics", "Empowerment", "Instruction", "Military Engineering"]
    },
    "Unreality": {
        "studies": [
            "Mutations",
            "Occultism",
            "Planar Travel and Gating",
            "Steam and Gasgear",
        ]
    },
    "Way of the Heart": {"studies": ["Blood", "Breath", "Dragon", "Yin and Yang"]},
    "Way of the Spirit": {
        "studies": ["Calligraphy", "Insight", "Mindfulness", "Tranquility"]
    },
    "Way of the Stick": {"studies": ["Claw", "Fist", "Foot", "Hand"]},
    "Way of the Stone": {"studies": ["Moat", "Pedestal", "Smoke", "Wall"]},
    "Wilderland": {
        "studies": [
            "Beachcomber",
            "Blightlander",
            "Forester",
            "Jungle Bushcraft",
            "Mountaineer",
            "Scouting",
        ]
    },
    "Woodworking": {"studies": ["Engines", "Joinery", "Shipbuilding", "Turning"]},
}


# ---------------------------------------------------------------------------
# Class -> fields mapping
# ---------------------------------------------------------------------------

CLASS_FIELDS = {
    "assassin": ["Animal Training (Assassin)", "Grace", "Mastery at Arms", "Skulduggery"],
    "bard": [
        "Architecture", "Art World", "Ceramics", "Circus", "Dance", "Drama",
        "Fine Art", "Gastronomy", "Leatherwork", "Literature", "Metalwork",
        "Music", "Puppetry", "Salon", "Textiles", "Woodworking",
    ],
    "cleric": ["Legends and Folklore", "Power", "The Church", "Theology and Customs"],
    "druid": ["Animal Life", "Earth and Sky", "Plant Life"],
    "fighter": ["Animal Training", "Leadership", "Mastery at Arms", "Training"],
    "illusionist": ["Civitas (Illusionist)", "Humanities", "Reality", "Unreality"],
    "mage": ["Civitas (Mage)", "Humanities", "Black Magic", "Science"],
    "monk": [
        "Way of the Heart", "Way of the Spirit", "Way of the Stick", "Way of the Stone"
    ],
    "paladin": ["Animal Training", "Mastery at Arms", "Leadership", "Reverence"],
    "ranger": ["Animal Training", "Mastery at Arms", "Training", "Wilderland"],
    "thief": ["Fraud", "Skulduggery", "Streetwisdom", "Theft"],
}


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def alexisify(text: str) -> str:
    """Return the wiki's canonical spelling for a study/field name."""
    if not text:
        raise ValueError("String cannot be empty")
    alternative = (
        sage_fields.get(text, {}).get("alexis_name")
        or sage_studies.get(text, {}).get("alexis_name")
        or None
    )
    if alternative:
        text = alternative
    text = re.sub(re.compile(r"([,\s])and(\s)"), r"\1&\2", text)
    text = re.sub(re.compile(r"\s+\(.*\)"), "", text)
    return text


def linkify_field(x: str) -> str:
    return f"<a href='https://wiki.alexissmolensk.com/index.php/{alexisify(x)}_(sage_field)'>{x}</a>"


def linkify_study(x: str) -> str:
    return f"<a href='https://wiki.alexissmolensk.com/index.php/{alexisify(x)}_(sage_study)'>{x}</a>"


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
