"""Sage knowledge catalogue and rank logic.

Content adapted from dnd/dnd/sage.py, using the wiki's spelling of every
study and field. sage_studies is authoritative for field membership;
sage_fields is the reverse index, derived from it at import.
"""

import re
from dataclasses import dataclass

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
# Concentrations
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Concentrations:
    """How one study splits its points into named buckets.

    A handful of studies do not hold their points as a single pool. The points
    are committed to named subjects within the study, and knowledge aimed at one
    does nothing for any other: thirty points of History never makes an
    authority on history, only on some period and sphere of it.

    Every field has a default, so a catalogue entry states only what makes that
    study unusual — ``Concentrations()`` on its own describes Geography, the
    plainest case. Frozen because the instances are catalogue data shared by
    every request; nothing may edit one in passing.
    """

    # The buckets are standalone sage abilities in their own right, so they are
    # stored as SageAbilityPoints carrying the study's name instead of as rows
    # of their own. Athletics alone: the wiki calls each of its disciplines a
    # sage ability outright, so inventing a second kind of record for them would
    # be Zingor disagreeing with the rules for no reason.
    are_abilities: bool = False
    # Every bucket holds the study's whole total rather than a portion of it,
    # because the buckets are not divisions of the knowledge but subjects it
    # applies to in full (Law & Policy, Politics). Nothing is ever left over,
    # and a bucket has no number of its own to store.
    mirrored: bool = False
    # The names the catalogue knows. Geography's is empty because the loci are
    # the DM's invention and there are thousands of them, so a player naming one
    # is the only way it can ever be known.
    choices: tuple[str, ...] = ()
    # Whether `choices` is the complete set of legal names or merely a set of
    # suggestions. Closed where the rules define the whole list and nothing else
    # is a legal allocation — History's twelve period-and-sphere pairs, or
    # Heraldry's four mega-cultures. Open where a list exists but Zingor does not
    # hold all of it: the wiki catalogues beasts and artifacts, but those lists
    # are long and still growing, so a name Zingor has not heard of is the
    # player's to make up rather than a mistake.
    closed: bool = False
    # A bucket costs exactly this many points, so how many the study can hold is
    # arithmetic (Beasts, Artifacts: ten points per studied subject).
    block: int | None = None
    # Cap on the buckets the player may choose. A granted one is the study's
    # own and does not count against it.
    max_chosen: int | None = None
    # Names a bucket the study confers rather than the player choosing it. The
    # player still says what it is — Zingor does not know their religion.
    granted_label: str | None = None
    # Politics counts the character at half strength outside their chosen
    # entity; this labels the row the sheet works that out into.
    half_rate_label: str | None = None

    def __post_init__(self):
        """Reject combinations that describe no rule any study actually has.

        The fields are close to independent but not entirely, and a spec that
        contradicts itself would fail far from here — as a bucket priced in
        points it can never spend, or a half-rate row computed off a total no
        bucket holds. Catching it at import means a bad catalogue entry cannot
        start the app at all.
        """
        if self.are_abilities and (
            self.mirrored
            or self.block is not None
            or self.granted_label is not None
            or self.half_rate_label is not None
        ):
            raise ValueError(
                "are_abilities buckets are standalone sage abilities: they are "
                + "not priced, mirrored, granted, or halved"
            )
        if self.mirrored and self.block is not None:
            raise ValueError(
                "a mirrored bucket holds the study's whole total, so it has no "
                + "per-bucket cost to pay out of it"
            )
        if self.half_rate_label is not None and not self.mirrored:
            raise ValueError(
                "a half-rate row restates the total a mirrored bucket holds; it "
                + "means nothing where buckets divide the total instead"
            )
        if self.closed and not self.choices:
            raise ValueError(
                "a closed set of names needs names in it; leave closed False "
                + "where the player invents their own"
            )
        if self.block is not None and self.block <= 0:
            raise ValueError("a bucket's block price must be positive")
        if self.max_chosen is not None and self.max_chosen <= 0:
            raise ValueError("max_chosen must be positive, or None for no cap")

    def permits(self, name: str) -> bool:
        """Whether this study may hold a bucket by that name.

        Everything is permitted unless the catalogue holds the complete list.
        Callers should canonicalize first, so a difference of case or
        punctuation is not mistaken for a different subject.
        """
        return not self.closed or name in self.choices

    def stored_points(self, page_points: int) -> int:
        """What to persist for one bucket, given the number a page put on it.

        A mirrored bucket has no number of its own and a block-priced one costs
        a fixed amount however the page has it written, so only an allocated
        study reads the figure off the page at all.
        """
        if self.mirrored:
            return 0
        if self.block is not None:
            return self.block
        return page_points

    def display_points(self, stored: int, study_points: int) -> int:
        """What one bucket is worth, given what is stored and the study's total."""
        return study_points if self.mirrored else stored

    def page_disagrees(self, page_points: int, study_points: int) -> bool:
        """Whether a number a page put on a bucket contradicts this study's rule.

        Only a contradiction is worth reporting. A mirrored bucket is worth the
        study's whole total, which is exactly what ``display_points`` writes into
        an exported page — so a page repeating that figure is agreeing, and
        round-tripping Zingor's own export must stay silent.
        """
        if self.mirrored:
            return page_points != study_points
        if self.block is not None:
            return page_points != self.block
        return False

    def total_from_buckets(self, page_points: list[int]) -> int:
        """The study's total, inferred from its buckets alone.

        Used when a page lists where the points went but never states the total.
        Allocated buckets are portions of it, so they add up to it; mirrored ones
        each carry the whole of it, so the largest is it.
        """
        if not page_points:
            return 0
        if self.mirrored:
            return max(page_points)
        return sum(self.stored_points(points) for points in page_points)


# ---------------------------------------------------------------------------
# Inventions
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Invention:
    """One buildable device of a study, and what its daily upkeep costs.

    Steam & Gasgear does not commit its points to named subjects the way the
    concentrated studies do. Its knowledge points double as a daily pool of
    maintenance points, spent keeping built devices operational — and each
    device is a physical item the character had to build in play, so the
    things the points are aimed at are inventory items, not buckets. This
    class is only the catalogue's price list; which devices a character has
    built is read off her items. Frozen for the same reason Concentrations
    is: catalogue data shared by every request.

    rank is the status the wiki lists the device under (amateur, authority,
    expert, sage). It gates nothing in Zingor — building is governed by the
    DM in play — but the sheet's picker groups by it so the list reads the
    way the wiki writes it.
    """

    name: str
    cost: int
    rank: str

    def __post_init__(self):
        if self.cost <= 0:
            raise ValueError("a device's daily maintenance cost must be positive")


# Every device on the wiki's Steam & Gasgear page, priced by its daily
# maintenance cost. Mechanical Repair I and II are left out deliberately:
# they are skills of the practitioner, not devices, so there is nothing to
# build or maintain. The Rotating Ballista's per-volley cost and the
# Hydraulic Exosuit's refill cost are operational expenses beyond the daily
# upkeep tracked here.
steam_gasgear_inventions = (
    Invention("Armoured Weave", 2, "amateur"),
    Invention("Gas Pistol", 3, "amateur"),
    Invention("Infravision Goggles", 1, "amateur"),
    Invention("Pocket Timepiece", 1, "amateur"),
    Invention("Brass-fired Velocipede", 7, "authority"),
    Invention("Clockwork Typograph", 3, "authority"),
    Invention("Little Clank", 1, "authority"),
    Invention("Underwater Goggles", 2, "authority"),
    Invention("Articulated Maniple", 10, "expert"),
    Invention("Gyro-stabilised Steam Glider", 20, "expert"),
    Invention("Piston-driven Carriage", 30, "expert"),
    Invention("Rotating Ballista", 15, "expert"),
    Invention("Collapsible Cart", 3, "expert"),
    Invention("Folding Spyglass", 3, "expert"),
    Invention("Hand-crank Fan", 3, "expert"),
    Invention("Pressure-sealed Storage", 3, "expert"),
    Invention("Spring-loaded Stylus", 3, "expert"),
    Invention("Steam-heated Canteen", 3, "expert"),
    Invention("Airship", 62, "sage"),
    Invention("Hydraulic Exosuit", 30, "sage"),
    Invention("Steam-driven Subterranean Drill", 25, "sage"),
)


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
    "Artifacts": {
        "fields": ["Legends & Folklore"],
        # One studied artifact per ten points. The wiki does keep a list of
        # them, but it is long and still growing, so the player names theirs.
        "concentrations": Concentrations(block=10),
    },
    "Astronomy & Astrology": {"fields": ["Theology & Customs"]},
    "Athletics": {
        "fields": ["Training"],
        "concentrations": Concentrations(
            are_abilities=True,
            choices=(
                "Cliff Diving",
                "Free-diving",
                "Hurling",
                "Ice Sailing",
                "Kayaking",
                "Martial Arts",
                "Running",
                "Sailing",
                "Scrambling",
                "Skating",
                "Skiing",
                "Surfing",
                "Swimming",
            ),
        ),
    },
    "Auctionhouse": {"fields": ["Art World"]},
    "Backstabbing": {"fields": ["Skulduggery"]},
    "Baking": {"fields": ["Gastronomy"]},
    "Beachcomber": {"fields": ["Wilderland"]},
    "Beasts": {
        "fields": ["Legends & Folklore", "Reverence"],
        # One studied beast per ten points, named by the player for the same
        # reason as Artifacts.
        "concentrations": Concentrations(block=10),
    },
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
    "Geography": {
        "fields": ["Earth & Sky", "Humanities"],
        # Loci are the DM's, not the wiki's: there is no list to pick from, so
        # the player names one and the empty choices tuple makes the input
        # freetext. The plainest concentrated study there is.
        "concentrations": Concentrations(),
    },
    "Geology": {"fields": ["Earth & Sky", "Science"]},
    "Glaze": {"fields": ["Ceramics"]},
    "Gods": {"fields": ["Theology & Customs"]},
    "Golems": {"fields": ["Animal Life", "Black Magic"]},
    "Grasses & Grains": {"fields": ["Plant Life"]},
    "Guilds": {"fields": ["Civitas (Mage)", "Civitas (Illusionist)"]},
    "Guile": {"fields": ["Grace", "Streetwisdom"]},
    "Hand": {"fields": ["Way of the Stick"]},
    "Heightened Senses": {"fields": ["Skulduggery"]},
    "Heraldry, Signs & Sigils": {
        "fields": ["The Church"],
        # Each level's points go wholly to one mega-culture, but which one is
        # free to change from level to level, so this is ordinary allocation.
        "concentrations": Concentrations(
            choices=("European", "Islamic", "Oriental", "Prehistoric"),
            closed=True,
        ),
    },
    "Heroism": {"fields": ["Legends & Folklore", "Leadership"]},
    "Hides & Skins": {"fields": ["Leather Work"]},
    "History": {
        "fields": ["The Church"],
        # Points are assigned to a combination of one of the wiki's three
        # periods and one of its four geographic spheres.
        "concentrations": Concentrations(
            choices=(
                "Ancient Africa",
                "Ancient Asia",
                "Ancient Europe",
                "Ancient New World",
                "Medieval Africa",
                "Medieval Asia",
                "Medieval Europe",
                "Medieval New World",
                "Modern Africa",
                "Modern Asia",
                "Modern Europe",
                "Modern New World",
            ),
            closed=True,
        ),
    },
    "Horseback Riding": {"fields": ["Animal Training", "Animal Training (Assassin)"]},
    "Insight": {"fields": ["Way of the Spirit"]},
    "Instruction": {"fields": ["Salon", "Training"]},
    "Jack-of-all-Trades": {"fields": ["Grace", "Streetwisdom"]},
    "Joinery": {"fields": ["Woodworking"]},
    "Judgment": {"fields": ["Leadership"]},
    "Jungle Bushcraft": {"fields": ["Wilderland"]},
    "Language": {"fields": ["Humanities"]},
    "Law & Policy": {
        "fields": ["Humanities", "Theology & Customs"],
        # The character knows their religion's theological law, "supplemented by
        # an equal amount of knowledge in a single political entity of the
        # character's choice" — so neither bucket divides the study's points;
        # both hold all of them.
        "concentrations": Concentrations(
            mirrored=True,
            max_chosen=1,
            granted_label="Your religion's theological law",
        ),
    },
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
    "Outer Planes": {
        "fields": ["Power"],
        # Alternate names are part of the bucket's name rather than aliases for
        # it: the campaign uses both, and folding them away would make the
        # sheet name a plane the player did not.
        "concentrations": Concentrations(
            choices=(
                "Abyss",
                "Acheron",
                "Arborea (Olympus)",
                "Arcadia",
                "Astral Plane",
                "Beastlands (Happy Hunting Grounds)",
                "Bytopia (Twin Paradises)",
                "Elysium",
                "Ethereal Plane",
                "Gehenna",
                "Grey Waste",
                "Hades",
                "Heaven",
                "Limbo",
                "Mechanus",
                "Mount Celestia (Purgatory)",
                "Nine Hells (Baator)",
                "Nirvana",
                "Outlands",
                "Pandemonium",
                "Tartarus (Carceri)",
                "Ysgard (Gladsheim)",
            ),
            closed=True,
        ),
    },
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
    "Politics": {
        "fields": ["The Church"],
        # All the points go to one entity; the character is still counted at
        # half that everywhere else, which the sheet works out rather than
        # storing.
        "concentrations": Concentrations(
            mirrored=True,
            max_chosen=1,
            half_rate_label="All other entities",
        ),
    },
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
    "Steam & Gasgear": {
        "fields": ["Unreality"],
        "inventions": steam_gasgear_inventions,
    },
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


def concentration_spec(study: str) -> Concentrations | None:
    """Return a study's Concentrations, or None if it has no buckets.

    Takes the catalogue's spelling or any variant of it, so a stored study name
    predating a spelling correction still resolves.
    """
    return sage_studies.get(canonical_study(study), {}).get("concentrations")


def concentration_choices(study: str) -> list[str]:
    """Return the names the catalogue suggests for a study's buckets."""
    spec = concentration_spec(study)
    return list(spec.choices) if spec else []


def canonical_concentration(study: str, name: str) -> str:
    """Return the catalogue's spelling of one of a study's buckets.

    Unrecognised names pass through for the same reason unrecognised studies
    do: the list is a suggestion, and Geography has none at all.
    """
    wanted = _normalize(name)
    for choice in concentration_choices(study):
        if _normalize(choice) == wanted:
            return choice
    return name


def invention_catalogue(study: str) -> tuple[Invention, ...] | None:
    """Return a study's buildable devices, or None if it has none.

    Takes the catalogue's spelling or any variant of it, like
    ``concentration_spec``.
    """
    return sage_studies.get(canonical_study(study), {}).get("inventions")


def canonical_invention(study: str, name: str) -> Invention | None:
    """Return the catalogue entry for one of a study's devices, or None.

    Unlike concentration names, an unrecognised device does not pass
    through: the catalogue is the price list, and a device it has never
    heard of has no maintenance cost to look up.
    """
    wanted = _normalize(name)
    for invention in invention_catalogue(study) or ():
        if _normalize(invention.name) == wanted:
            return invention
    return None


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
