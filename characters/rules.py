"""Pure rules functions for D&D character mechanics.

No model imports — takes primitives, returns values. Easy to test and tweak.
Ported from dnd/characters.py.
"""

from .units import D, u

# --- Inclusive range helper ---


def ir(a, b):
    """Inclusive range for ability score lookups."""
    return range(a, b + 1)


# --- Coin weights ---

coin_exchange = {
    "gold": {"weight": D("0.4") * u.oz},
    "silver": {"weight": D("0.6") * u.oz},
    "copper": {"weight": D("0.8") * u.oz},
}


def weight_of_money(gp, sp, cp):
    """Calculate the weight of coins."""
    total = (
        gp.magnitude * coin_exchange["gold"]["weight"]
        + sp.magnitude * coin_exchange["silver"]["weight"]
        + cp.magnitude * coin_exchange["copper"]["weight"]
    )
    return total.to(u.lb)


# --- Ability score functions ---

martial_classes = {"assassin", "fighter", "paladin", "ranger"}


def effective_strength(base_str, base_pct, modifier_sum):
    """Compute effective (strength, percentile) after applying modifier sum.

    At the 18 boundary, each +1 becomes +10% percentile instead of +1 score.
    Once percentile exceeds 100 (18/00), further +1s increase the score to 19+.
    Negative modifiers reverse this: -1 from 18/10 → plain 18, -1 from plain 18 → 17.
    """
    if base_str is None:
        return None, None
    if modifier_sum == 0:
        return base_str, base_pct

    score = base_str
    pct = base_pct

    for _ in range(abs(modifier_sum)):
        if modifier_sum > 0:
            if score < 17:
                score += 1
            elif score == 17:
                score = 18
                # Just reached 18 — no percentile yet
            elif score == 18:
                current_pct = pct or 0
                current_pct += 10
                if current_pct > 100:
                    score = 19
                    pct = None
                else:
                    pct = current_pct
            else:  # > 18
                score += 1
        else:
            if score > 19:
                score -= 1
            elif score == 19:
                score = 18
                pct = 100
            elif score == 18 and pct is not None and pct > 0:
                pct -= 10
                if pct <= 0:
                    pct = None
            elif score == 18:
                score = 17
                pct = None
            else:
                score -= 1

    return score, pct


def str_attack_mod(s, pct=None):
    """Modifier on melee attack rolls.

    When s == 18 and pct is not None, use percentile strength breakpoints.
    The caller is responsible for only passing pct when the character class
    qualifies (fighters only).
    """
    if s < 0:
        raise ValueError(f"strength {s} less than 0")
    if s <= 2:
        return -3
    elif s == 3:
        return -3
    elif s == 4:
        return -2
    elif s == 5:
        return -1
    elif s in ir(6, 15):
        return 0
    elif s == 16:
        return 0
    elif s == 17:
        return 1
    elif s == 18:
        if pct is not None:
            if pct <= 50:
                return 1
            elif pct <= 90:
                return 2
            elif pct <= 99:
                return 2
            else:  # 100 (written as "00")
                return 3
        return 1
    elif s == 19:
        return 3
    elif s == 20:
        return 3
    elif s == 21:
        return 4
    elif s == 22:
        return 4
    elif s == 23:
        return 5
    elif s == 24:
        return 6
    elif s >= 25:
        return 7
    return 0


def str_damage_mod(s, pct=None):
    """Modifier on melee damage rolls.

    When s == 18 and pct is not None, use percentile strength breakpoints.
    The caller is responsible for only passing pct when the character class
    qualifies (fighters only).
    """
    if s < 0:
        raise ValueError(f"strength {s} less than 0")
    if s <= 2:
        return -2
    elif s == 3:
        return -2
    elif s == 4:
        return -1
    elif s == 5:
        return 0
    elif s in ir(6, 15):
        return 0
    elif s == 16:
        return 1
    elif s == 17:
        return 1
    elif s == 18:
        if pct is not None:
            if pct <= 50:
                return 3
            elif pct <= 75:
                return 3
            elif pct <= 90:
                return 4
            elif pct <= 99:
                return 5
            else:  # 100 (written as "00")
                return 6
        return 2
    elif s == 19:
        return 7
    elif s == 20:
        return 8
    elif s == 21:
        return 9
    elif s == 22:
        return 10
    elif s == 23:
        return 11
    elif s == 24:
        return 12
    elif s >= 25:
        return 14
    return 0


def dex_ac_mod(d):
    """Armor class modifier from dexterity."""
    if d < 0:
        raise ValueError(f"dexterity {d} less than 0")
    if d <= 3:
        return -4
    elif d == 4:
        return -3
    elif d == 5:
        return -2
    elif d == 6:
        return -1
    elif d in ir(7, 14):
        return 0
    elif d == 15:
        return 1
    elif d == 16:
        return 2
    elif d in ir(17, 19):
        return 3
    else:
        return 4


def dex_ranged_attacks_mod(d):
    """Modifier on ranged attack rolls (equals initiative modifier)."""
    return dex_initiative_mod(d)


def dex_initiative_mod(d):
    """Initiative modifier from dexterity."""
    if d < 0:
        raise ValueError(f"dexterity {d} less than 0")
    if d <= 3:
        return -3
    elif d == 4:
        return -2
    elif d == 5:
        return -1
    elif d in ir(6, 15):
        return 0
    elif d == 16:
        return 1
    elif d == 17:
        return 2
    elif d in ir(18, 19):
        return 3
    else:
        return 4


def con_max_hp_increase_adjustment(con, char_class=None):
    """Amount of HP to add to each Hit Die rolled upon level up."""
    if con < 0:
        raise ValueError(f"constitution {con} less than 0")
    if con <= 3:
        return -2
    elif con in ir(4, 6):
        return -1
    elif con in ir(7, 14):
        return 0
    elif con == 15:
        return 1
    elif con == 16:
        return 2
    elif con > 16 and char_class not in martial_classes:
        return 2
    else:
        if con == 17:
            return 3
        else:  # 18+
            return 4


_con_system_shock = {
    3: 35,
    4: 40,
    5: 45,
    6: 50,
    7: 55,
    8: 60,
    9: 65,
    10: 70,
    11: 75,
    12: 80,
    13: 85,
    14: 89,
    15: 93,
    16: 96,
    17: 98,
    18: 99,
}


def con_system_shock_survival_chance(con):
    """Base percentage chance of surviving a system shock roll."""
    if con < 0:
        raise ValueError(f"constitution {con} less than 0")
    if con < 3:
        return 35
    return _con_system_shock.get(con, 99)


_con_resurrection = {
    3: 39,
    4: 44,
    5: 50,
    6: 55,
    7: 61,
    8: 66,
    9: 72,
    10: 77,
    11: 79,
    12: 84,
    13: 87,
    14: 91,
    15: 94,
    16: 97,
    17: 99,
    18: 99.5,
}


def con_resurrection_survival_chance(con):
    """Percentage chance of surviving resurrection (Return from Dead)."""
    if con < 0:
        raise ValueError(f"constitution {con} less than 0")
    if con < 3:
        return 39
    return _con_resurrection.get(con, 99.5)


def int_max_mage_illusionist_spell_level(i):
    """Highest level of mage/illusionist spells that can be memorized."""
    if i < 0:
        raise ValueError(f"intelligence {i} less than 0")
    if i <= 8:
        return None
    if i == 9:
        return 4
    elif i in ir(10, 11):
        return 5
    elif i in ir(12, 13):
        return 6
    elif i in ir(14, 15):
        return 7
    elif i in ir(16, 17):
        return 8
    else:
        return 9


def int_spell_capability_chance(score):
    """Percentage chance of successfully learning a mage spell."""
    if score < 0:
        raise ValueError(f"intelligence {score} less than 0")
    elif score < 9:
        return None
    elif score == 9:
        return 35
    elif score in ir(10, 11):
        return 40
    elif score == 12:
        return 45
    elif score == 13:
        return 50
    elif score == 14:
        return 55
    elif score == 15:
        return 60
    elif score == 16:
        return 65
    elif score == 17:
        return 75
    elif score == 18:
        return 85
    elif score == 19:
        return 95
    elif score in ir(20, 21):
        return 98
    else:
        return 100


_int_min_capable_spells = {
    9: 8,
    10: 9,
    11: 9,
    12: 9,
    13: 10,
    14: 12,
    15: 13,
    16: 14,
    17: 16,
    18: 18,
    19: 19,
}


def int_min_capable_spells(score):
    """Minimum number of spells a mage can know per level."""
    if score < 0:
        raise ValueError(f"intelligence {score} less than 0")
    if score <= 8:
        return None
    return _int_min_capable_spells.get(score, min(20, score))


def wis_charm_illusion_save_mod(w):
    """Save modifier vs charm and illusion magic."""
    if w < 0:
        raise ValueError(f"wisdom {w} less than 0")
    if w <= 3:
        return -3
    elif w == 4:
        return -2
    elif w in ir(5, 7):
        return -1
    elif w in ir(8, 14):
        return 0
    elif w == 15:
        return 1
    elif w == 16:
        return 2
    elif w == 17:
        return 3
    elif w == 18:
        return 4
    elif w == 19:
        return 5
    else:
        return w - 14


def wis_max_cleric_spell_level(w):
    """Highest cleric spell level available."""
    if w < 0:
        raise ValueError(f"wisdom {w} less than 0")
    elif w < 9:
        return None
    elif w in ir(9, 12):
        return 4
    elif w in ir(13, 14):
        return 5
    elif w in ir(15, 16):
        return 6
    else:
        return 7


def wis_cleric_spell_success_percent(w):
    """Percentage chance of successfully casting a cleric spell (100 - spell failure%)."""
    if w < 0:
        raise ValueError(f"wisdom {w} less than 0")
    if w < 9:
        return None
    elif w == 9:
        return 80
    elif w == 10:
        return 85
    elif w == 11:
        return 90
    elif w == 12:
        return 95
    else:
        return 100


def cha_max_henchmen(cha):
    """Maximum number of primary henchmen."""
    if cha < 0:
        raise ValueError(f"charisma {cha} less than 0")
    if cha == 0:
        return 0
    if cha in ir(1, 4):
        return 1
    elif cha in ir(5, 6):
        return 2
    elif cha in ir(7, 8):
        return 3
    elif cha in ir(9, 11):
        return 4
    elif cha in ir(12, 13):
        return 5
    elif cha == 14:
        return 6
    elif cha == 15:
        return 7
    elif cha == 16:
        return 8
    elif cha == 17:
        return 9
    elif cha == 18:
        return 10
    else:
        return cha_max_henchmen(18) + (cha - 18)


def cha_morale_adj(cha):
    """Morale adjustment: higher value means harder for henchfolk to maintain resolve."""
    if cha < 0:
        raise ValueError(f"charisma {cha} less than 0")
    if cha in ir(0, 5):
        return 3
    elif cha in ir(6, 7):
        return 2
    elif cha == 8:
        return 1
    elif cha in ir(9, 13):
        return 0
    elif cha == 14:
        return -1
    elif cha in ir(15, 16):
        return -2
    else:
        return -3


# --- Abilities dict: maps ability -> derived stat name -> function ---

abilities = {
    "strength": {
        "melee attack modifier": lambda s, pct=None: str_attack_mod(s, pct),
        "melee damage modifier": lambda s, pct=None: str_damage_mod(s, pct),
    },
    "dexterity": {
        "AC modifier": dex_ac_mod,
        "ranged attack modifier": dex_ranged_attacks_mod,
        "initiative modifier": dex_initiative_mod,
    },
    "constitution": {
        "bonus HP per level": con_max_hp_increase_adjustment,
        "system shock survival % chance": con_system_shock_survival_chance,
        "resurrection survival % chance": con_resurrection_survival_chance,
    },
    "intelligence": {
        "max mage spell level": int_max_mage_illusionist_spell_level,
        "mage spell capability % chance": int_spell_capability_chance,
        "min capable mage spells": int_min_capable_spells,
    },
    "wisdom": {
        "Charm & Illusion save modifier": wis_charm_illusion_save_mod,
        "max cleric spell level": wis_max_cleric_spell_level,
        "cleric spell success % chance": wis_cleric_spell_success_percent,
    },
    "charisma": {
        "max henchmen": cha_max_henchmen,
        "morale adjustment": cha_morale_adj,
    },
}


# --- Character classes ---

# Saving throw tables. Each list has 5 entries corresponding to the level
# brackets defined in _save_brackets for that group.
# Categories: poison, paralyse, polymorph, rod_staff_wand, breath, magic

_bard_fighter_ranger_saves = {
    "poison": [15, 14, 12, 11, 9],
    "paralyse": [15, 14, 13, 12, 10],
    "polymorph": [16, 15, 13, 11, 10],
    "rod_staff_wand": [15, 13, 12, 10, 9],
    "breath": [17, 16, 14, 13, 11],
    "magic": [15, 14, 12, 11, 9],
}
_bard_fighter_ranger_brackets = [3, 7, 10, 15]  # 1-3, 4-7, 8-10, 11-15, 16+

_assassin_thief_saves = {
    "poison": [13, 12, 11, 10, 9],
    "paralyse": [12, 11, 10, 9, 8],
    "polymorph": [14, 13, 12, 11, 10],
    "rod_staff_wand": [14, 12, 10, 8, 6],
    "breath": [16, 15, 14, 13, 12],
    "magic": [15, 13, 11, 9, 7],
}
_assassin_thief_brackets = [6, 11, 15, 19]  # 1-6, 7-11, 12-15, 16-19, 20+

_illusionist_mage_monk_saves = {
    "poison": [14, 13, 11, 10, 8],
    "paralyse": [12, 11, 10, 9, 8],
    "polymorph": [12, 10, 8, 6, 4],
    "rod_staff_wand": [11, 9, 7, 5, 3],
    "breath": [15, 13, 11, 9, 7],
    "magic": [12, 10, 8, 6, 4],
}
_illusionist_mage_monk_brackets = [4, 8, 12, 17]  # 1-4, 5-8, 9-12, 13-17, 18+

_cleric_druid_paladin_saves = {
    "poison": [12, 11, 9, 8, 7],
    "paralyse": [11, 10, 8, 7, 6],
    "polymorph": [13, 12, 10, 9, 8],
    "rod_staff_wand": [14, 13, 11, 10, 9],
    "breath": [15, 14, 12, 11, 10],
    "magic": [15, 14, 12, 11, 10],
}
_cleric_druid_paladin_brackets = [4, 8, 13, 18]  # 1-4, 5-8, 9-13, 14-18, 19+

SAVING_THROW_CATEGORIES = [
    "poison",
    "paralyse",
    "polymorph",
    "rod_staff_wand",
    "breath",
    "magic",
]

_save_groups = {
    "bard_fighter_ranger": (_bard_fighter_ranger_saves, _bard_fighter_ranger_brackets),
    "assassin_thief": (_assassin_thief_saves, _assassin_thief_brackets),
    "illusionist_mage_monk": (
        _illusionist_mage_monk_saves,
        _illusionist_mage_monk_brackets,
    ),
    "cleric_druid_paladin": (
        _cleric_druid_paladin_saves,
        _cleric_druid_paladin_brackets,
    ),
}

_class_to_save_group = {
    "bard": "bard_fighter_ranger",
    "fighter": "bard_fighter_ranger",
    "ranger": "bard_fighter_ranger",
    "assassin": "assassin_thief",
    "thief": "assassin_thief",
    "illusionist": "illusionist_mage_monk",
    "mage": "illusionist_mage_monk",
    "monk": "illusionist_mage_monk",
    "cleric": "cleric_druid_paladin",
    "druid": "cleric_druid_paladin",
    "paladin": "cleric_druid_paladin",
}

classes = {
    "assassin": {
        "save_group": "assassin_thief",
        "hit_die": "d8",
        "ability_minimums": {
            "strength": 12,
            "intelligence": 11,
            "dexterity": 12,
            "wisdom": 6,
            "constitution": 8,
        },
        "bonus_xp_minimums": {},
        "levels": {
            1: {"min XP": 0, "proficiencies": 3},
            2: {"min XP": 1_751},
            3: {"min XP": 3_501},
            4: {"min XP": 7_501},
            5: {"min XP": 15_001, "proficiencies": 4},
            6: {"min XP": 30_001},
            7: {"min XP": 60_001},
            8: {"min XP": 115_001},
            9: {"min XP": 230_001, "proficiencies": 5},
            10: {"min XP": 425_001},
            11: {"min XP": 650_001},
            12: {"min XP": 850_001},
            13: {"min XP": 1_050_001, "proficiencies": 6},
            14: {"min XP": 1_275_001},
            15: {"min XP": 1_750_001},
        },
    },
    "bard": {
        "save_group": "bard_fighter_ranger",
        "hit_die": "d6",
        "ability_minimums": {
            "strength": 6,
            "intelligence": 10,
            "wisdom": 13,
            "constitution": 6,
            "dexterity": 6,
            "charisma": 15,
        },
        "bonus_xp_minimums": {},
        "levels": {
            1: {"min XP": 0, "proficiencies": 2},
            2: {"min XP": 2_001},
            3: {"min XP": 4_001},
            4: {"min XP": 8_001},
            5: {"min XP": 16_001},
            6: {"min XP": 30_001, "proficiencies": 3},
            7: {"min XP": 55_001},
            8: {"min XP": 100_001},
            9: {"min XP": 180_001},
            10: {"min XP": 300_001},
            11: {"min XP": 480_001, "proficiencies": 4},
            12: {"min XP": 660_001},
            13: {"min XP": 840_001},
            14: {"min XP": 1_020_001},
            15: {"min XP": 1_200_001},
            16: {"min XP": 1_380_001, "proficiencies": 5},
            17: {"min XP": 1_560_001},
            18: {"min XP": 1_740_001},
            19: {"min XP": 1_920_001},
            20: {"min XP": 2_100_001},
            21: {"min XP": 2_280_001},
            22: {"min XP": 2_460_001},
            23: {"min XP": 2_640_001},
        },
    },
    "cleric": {
        "save_group": "cleric_druid_paladin",
        "hit_die": "d8",
        "ability_minimums": {
            "strength": 6,
            "intelligence": 6,
            "wisdom": 9,
            "constitution": 6,
            "charisma": 6,
        },
        "bonus_xp_minimums": {"wisdom": 16},
        "levels": {
            1: {"min XP": 0, "proficiencies": 2},
            2: {"min XP": 1_501},
            3: {"min XP": 3_001},
            4: {"min XP": 6_001},
            5: {"min XP": 13_001, "proficiencies": 3},
            6: {"min XP": 27_501},
            7: {"min XP": 55_001},
            8: {"min XP": 110_001},
            9: {"min XP": 225_001, "proficiencies": 4},
            10: {"min XP": 450_001},
            11: {"min XP": 675_001},
            12: {"min XP": 900_001},
            13: {"min XP": 1_125_001, "proficiencies": 5},
            14: {"min XP": 1_350_001},
            15: {"min XP": 1_575_001},
            16: {"min XP": 1_800_001},
            17: {"min XP": 2_025_001, "proficiencies": 6},
            18: {"min XP": 2_250_001},
            19: {"min XP": 2_475_001},
            20: {"min XP": 2_700_001},
        },
    },
    "druid": {
        "save_group": "cleric_druid_paladin",
        "hit_die": "d8",
        "ability_minimums": {
            "strength": 6,
            "intelligence": 6,
            "wisdom": 12,
            "constitution": 6,
            "dexterity": 6,
            "charisma": 15,
        },
        "bonus_xp_minimums": {"wisdom": 16, "charisma": 16},
        "levels": {
            1: {"min XP": 0, "proficiencies": 2},
            2: {"min XP": 2_401},
            3: {"min XP": 4_751},
            4: {"min XP": 9_001},
            5: {"min XP": 15_001},
            6: {"min XP": 24_001, "proficiencies": 3},
            7: {"min XP": 42_001},
            8: {"min XP": 72_001},
            9: {"min XP": 110_001},
            10: {"min XP": 150_001},
            11: {"min XP": 240_001, "proficiencies": 4},
            12: {"min XP": 360_001},
            13: {"min XP": 750_001},
            14: {"min XP": 1_500_001},
            15: {"min XP": 2_250_001},
            16: {"min XP": 3_000_001, "proficiencies": 5},
            17: {"min XP": 3_500_001},
            18: {"min XP": 3_900_001},
            19: {"min XP": 4_300_001},
            20: {"min XP": 4_700_001},
            21: {"min XP": 5_100_001},
            22: {"min XP": 5_500_001},
            23: {"min XP": 6_500_001},
        },
    },
    "fighter": {
        "save_group": "bard_fighter_ranger",
        "hit_die": "d10",
        "ability_minimums": {
            "strength": 9,
            "dexterity": 6,
            "constitution": 7,
            "wisdom": 6,
            "charisma": 6,
        },
        "bonus_xp_minimums": {"strength": 16},
        "levels": {
            1: {"min XP": 0, "proficiencies": 4},
            2: {"min XP": 2_001},
            3: {"min XP": 4_001},
            4: {"min XP": 8_001, "proficiencies": 5},
            5: {"min XP": 18_001},
            6: {"min XP": 35_001},
            7: {"min XP": 70_001, "proficiencies": 6},
            8: {"min XP": 125_001},
            9: {"min XP": 250_001},
            10: {"min XP": 500_001, "proficiencies": 7},
            11: {"min XP": 750_001},
            12: {"min XP": 1_000_001},
            13: {"min XP": 1_250_001, "proficiencies": 8},
            14: {"min XP": 1_500_001},
            15: {"min XP": 1_750_001},
            16: {"min XP": 2_000_001, "proficiencies": 9},
            17: {"min XP": 2_250_001},
            18: {"min XP": 2_500_001},
            19: {"min XP": 2_750_001, "proficiencies": 10},
            20: {"min XP": 3_000_001},
        },
    },
    "illusionist": {
        "save_group": "illusionist_mage_monk",
        "hit_die": "d4",
        "ability_minimums": {
            "strength": 6,
            "intelligence": 12,
            "dexterity": 16,
            "wisdom": 6,
            "charisma": 6,
        },
        "bonus_xp_minimums": {},
        "levels": {
            1: {"min XP": 0, "proficiencies": 1},
            2: {"min XP": 2_251},
            3: {"min XP": 4_501},
            4: {"min XP": 9_001},
            5: {"min XP": 18_001},
            6: {"min XP": 35_001},
            7: {"min XP": 60_001, "proficiencies": 2},
            8: {"min XP": 96_001},
            9: {"min XP": 145_001},
            10: {"min XP": 220_001},
            11: {"min XP": 440_001},
            12: {"min XP": 660_001},
            13: {"min XP": 880_001, "proficiencies": 3},
            14: {"min XP": 1_100_001},
            15: {"min XP": 1_320_001},
            16: {"min XP": 1_540_001},
            17: {"min XP": 1_760_001},
            18: {"min XP": 1_980_001},
            19: {"min XP": 2_200_001, "proficiencies": 4},
            20: {"min XP": 2_420_001},
        },
    },
    "mage": {
        "save_group": "illusionist_mage_monk",
        "hit_die": "d4",
        "ability_minimums": {
            "intelligence": 9,
            "dexterity": 7,
            "constitution": 6,
            "wisdom": 6,
            "charisma": 6,
        },
        "bonus_xp_minimums": {"intelligence": 16},
        "levels": {
            1: {"min XP": 0, "proficiencies": 1},
            2: {"min XP": 2_501},
            3: {"min XP": 5_001},
            4: {"min XP": 10_001},
            5: {"min XP": 22_501},
            6: {"min XP": 40_001},
            7: {"min XP": 60_001, "proficiencies": 2},
            8: {"min XP": 90_001},
            9: {"min XP": 135_001},
            10: {"min XP": 250_001},
            11: {"min XP": 375_001},
            12: {"min XP": 750_001},
            13: {"min XP": 1_125_001, "proficiencies": 3},
            14: {"min XP": 1_500_001},
            15: {"min XP": 1_875_001},
            16: {"min XP": 2_250_001},
            17: {"min XP": 2_625_001},
            18: {"min XP": 3_000_001},
            19: {"min XP": 3_375_001, "proficiencies": 4},
            20: {"min XP": 3_750_001},
        },
    },
    "monk": {
        "save_group": "illusionist_mage_monk",
        "hit_die": "d6",
        "ability_minimums": {
            "strength": 15,
            "intelligence": 9,
            "wisdom": 15,
            "constitution": 11,
            "dexterity": 15,
            "charisma": 6,
        },
        "bonus_xp_minimums": {},
        "levels": {
            1: {"min XP": 0, "proficiencies": 2},
            2: {"min XP": 2_251},
            3: {"min XP": 4_751, "proficiencies": 3},
            4: {"min XP": 10_001},
            5: {"min XP": 22_501, "proficiencies": 4},
            6: {"min XP": 47_501},
            7: {"min XP": 98_001, "proficiencies": 5},
            8: {"min XP": 200_001},
            9: {"min XP": 350_001, "proficiencies": 6},
            10: {"min XP": 500_001},
            11: {"min XP": 700_001, "proficiencies": 7},
            12: {"min XP": 950_001},
            13: {"min XP": 1_250_001, "proficiencies": 8},
            14: {"min XP": 1_750_001},
            15: {"min XP": 2_250_001, "proficiencies": 9},
            16: {"min XP": 2_750_001},
            17: {"min XP": 3_250_001, "proficiencies": 10},
        },
    },
    "paladin": {
        "save_group": "cleric_druid_paladin",
        "hit_die": "d10",
        "ability_minimums": {
            "strength": 12,
            "intelligence": 9,
            "wisdom": 13,
            "constitution": 9,
            "dexterity": 7,
            "charisma": 17,
        },
        "bonus_xp_minimums": {"strength": 16, "wisdom": 16},
        "levels": {
            1: {"min XP": 0, "proficiencies": 3},
            2: {"min XP": 2_751},
            3: {"min XP": 5_501},
            4: {"min XP": 12_001, "proficiencies": 4},
            5: {"min XP": 24_001},
            6: {"min XP": 45_001},
            7: {"min XP": 95_001, "proficiencies": 5},
            8: {"min XP": 175_001},
            9: {"min XP": 350_001},
            10: {"min XP": 700_001, "proficiencies": 6},
            11: {"min XP": 1_050_001},
            12: {"min XP": 1_400_001},
            13: {"min XP": 1_750_001, "proficiencies": 7},
            14: {"min XP": 2_100_001},
            15: {"min XP": 2_450_001},
            16: {"min XP": 2_800_001, "proficiencies": 8},
            17: {"min XP": 3_150_001},
            18: {"min XP": 3_500_001},
            19: {"min XP": 3_850_001, "proficiencies": 9},
            20: {"min XP": 4_200_001},
        },
    },
    "ranger": {
        "save_group": "bard_fighter_ranger",
        "hit_die": "d10",
        "ability_minimums": {
            "strength": 13,
            "intelligence": 13,
            "wisdom": 14,
            "constitution": 14,
            "dexterity": 7,
            "charisma": 6,
        },
        "bonus_xp_minimums": {"strength": 16, "intelligence": 16},
        "levels": {
            1: {"min XP": 0, "proficiencies": 3},
            2: {"min XP": 2_251},
            3: {"min XP": 4_501},
            4: {"min XP": 10_001, "proficiencies": 4},
            5: {"min XP": 20_001},
            6: {"min XP": 40_001},
            7: {"min XP": 90_001, "proficiencies": 5},
            8: {"min XP": 150_001},
            9: {"min XP": 225_001},
            10: {"min XP": 325_001, "proficiencies": 6},
            11: {"min XP": 650_001},
            12: {"min XP": 975_001},
            13: {"min XP": 1_300_001, "proficiencies": 7},
            14: {"min XP": 1_625_001},
            15: {"min XP": 1_950_001},
            16: {"min XP": 2_275_001, "proficiencies": 8},
            17: {"min XP": 2_600_001},
            18: {"min XP": 2_925_001},
            19: {"min XP": 3_250_001, "proficiencies": 9},
            20: {"min XP": 3_575_001},
        },
    },
    "thief": {
        "save_group": "assassin_thief",
        "hit_die": "d6",
        "ability_minimums": {
            "strength": 6,
            "intelligence": 7,
            "dexterity": 9,
            "constitution": 6,
            "charisma": 6,
        },
        "bonus_xp_minimums": {"dexterity": 16},
        "levels": {
            1: {"min XP": 0, "proficiencies": 2},
            2: {"min XP": 1_251},
            3: {"min XP": 2_501},
            4: {"min XP": 5_001},
            5: {"min XP": 10_001, "proficiencies": 3},
            6: {"min XP": 20_001},
            7: {"min XP": 42_501},
            8: {"min XP": 70_001},
            9: {"min XP": 110_001, "proficiencies": 4},
            10: {"min XP": 160_001},
            11: {"min XP": 220_001},
            12: {"min XP": 440_001},
            13: {"min XP": 660_001, "proficiencies": 5},
            14: {"min XP": 880_001},
            15: {"min XP": 1_100_001},
            16: {"min XP": 1_320_001},
            17: {"min XP": 1_540_001, "proficiencies": 6},
            18: {"min XP": 1_760_001},
            19: {"min XP": 1_980_001},
            20: {"min XP": 2_200_001},
        },
    },
}


# --- Races ---

races = {
    "human": {"ability_modifiers": {}},
    "elf": {"ability_modifiers": {"intelligence": 1, "constitution": -1}},
    "halfelf": {"ability_modifiers": {"dexterity": 1, "constitution": -1}},
    "halforc": {"ability_modifiers": {"strength": 1, "charisma": -1}},
    "halfling": {"ability_modifiers": {"dexterity": 1, "strength": -1}},
    "gnome": {"ability_modifiers": {"wisdom": 1, "strength": -1}},
    "dwarf": {"ability_modifiers": {"constitution": 1, "dexterity": -1}},
}


# --- Core game functions ---


_THAC0_TABLE = {
    "assassin": (20, 19, 19, 18, 17, 16, 15, 15, 14, 13, 12, 11, 11, 10, 10),
    "bard": (21, 20, 20, 20, 19, 18, 18, 17, 17, 16, 16, 15, 15, 14, 14, 13),
    "cleric": (20, 20, 19, 18, 18, 17, 16, 16, 15, 14, 14, 13, 12, 12, 11, 11),
    "druid": (20, 20, 19, 19, 18, 18, 17, 16, 16, 15, 14, 14, 13, 13, 12, 12),
    "fighter": (20, 19, 18, 17, 16, 15, 14, 13, 12, 12, 11, 10, 10, 9, 8, 8),
    "paladin": (20, 19, 18, 17, 16, 15, 14, 13, 12, 12, 11, 10, 10, 9, 8, 8),
    "ranger": (20, 19, 18, 17, 16, 15, 14, 13, 12, 12, 11, 10, 10, 9, 8, 8),
    "illusionist": (21, 21, 20, 20, 20, 19, 19, 18, 18, 17, 17, 16, 16, 15, 15, 14),
    "mage": (21, 21, 20, 20, 20, 19, 19, 18, 18, 17, 17, 16, 16, 15, 15, 14),
    "monk": (20, 19, 19, 18, 17, 17, 16, 15, 14, 13, 12, 12, 11, 10, 10, 9),
    "thief": (21, 21, 20, 20, 19, 19, 18, 18, 17, 16, 16, 15, 14, 14, 13, 13),
}

_DEFAULT_THAC0 = 21  # Commoner / no class


def thac0(klass, level):
    """THAC0 (to-hit armor class 0) for a character of class klass at level."""
    row = _THAC0_TABLE.get(klass)
    if row is None:
        return _DEFAULT_THAC0
    idx = min(level, len(row)) - 1
    return row[idx]


def maximum_hp(hit_dice_list, char_class=None):
    """Calculate max HP from a list of hit die dicts.

    Each dict has: level, die_type, roll, con_bonus.
    """
    total = 0
    for die in hit_dice_list:
        total += die["roll"] + die["con_bonus"]
    return max(1, total)


def total_xp_for_next_level(klass, current_level):
    """Total XP required to reach the next level."""
    if klass is None or klass not in classes:
        return 1500
    max_lvl = max(classes[klass]["levels"].keys())
    if current_level >= max_lvl:
        return None
    return classes[klass]["levels"][current_level + 1]["min XP"]


# Strength-to-encumbrance base factor lookup.
# Percentile strength is represented as a fractional value:
# 18/01-50 → 18.1, 18/51-75 → 18.2, 18/76-90 → 18.3, 18/91-99 → 18.4, 18/00 → 18.5
_enc_str_lookup = {
    3: 115,
    4: 125,
    5: 130,
    6: 135,
    7: 140,
    8: 150,
    9: 150,
    10: 150,
    11: 150,
    12: 155,
    13: 160,
    14: 165,
    15: 170,
    16: 175,
    17: 185,
    18: 190,
    18.1: 200,
    18.2: 210,
    18.3: 220,
    18.4: 230,
    18.5: 240,
    19: 255,
    20: 270,
    21: 285,
    22: 300,
    23: 315,
    24: 330,
    25: 350,
}

# Map percentile breakpoints to fractional strength values for encumbrance lookup
_pct_to_fraction = [
    (50, 0.1),
    (75, 0.2),
    (90, 0.3),
    (99, 0.4),
    (100, 0.5),
]


def _enc_str_key(strength, percentile):
    """Convert strength + percentile into a lookup key for _enc_str_lookup."""
    if strength != 18 or percentile is None:
        return strength
    for threshold, fraction in _pct_to_fraction:
        if percentile <= threshold:
            return 18 + fraction
    return 18.5


def maximum_encumbrance(strength, percentile, body_weight, enc_mult):
    """Maximum weight a character can carry.

    Uses the encumbrance lookup table: base_factor * body_weight / 175.

    Args:
        strength: Current strength score (integer)
        percentile: Percentile strength (1-100) or None
        body_weight: Character weight as Decimal (magnitude only)
        enc_mult: Encumbrance multiplier (Decimal)
    """
    enc_mult = D(enc_mult)
    key = _enc_str_key(strength, percentile)
    base_factor = _enc_str_lookup.get(key)
    if base_factor is None:
        # Clamp to nearest known value
        if key < 3:
            base_factor = _enc_str_lookup[3]
        else:
            base_factor = _enc_str_lookup[25]
    max_weight = D(base_factor) * body_weight / D(175) * enc_mult
    if max_weight == 0:
        return D("1") * u.lb
    rounded = int(max_weight.quantize(D("1"), rounding="ROUND_HALF_UP"))
    return D(rounded) * u.lb


def action_points(current_enc, max_enc, max_ap):
    """Calculate current action points based on encumbrance.

    Max encumbrance is divided into max_ap equal tiers. Each tier crossed costs 1 AP.
    """
    if max_enc is None or max_enc.magnitude == 0:
        return 0
    num_tiers = max_ap
    tier_size = max_enc / num_tiers
    penalty = 0
    for i in range(1, num_tiers):
        if current_enc > tier_size * i:
            penalty = i
    return max(0, max_ap - penalty)


def character_saving_throw_target(charclass, level, save_type):
    """Get saving throw target number."""
    if level < 0:
        raise ValueError("Level can't be below 0")
    if charclass is None:
        # No class: use fighter group values at worst bracket, +2 penalty
        saves, brackets = _save_groups["bard_fighter_ranger"]
        return saves[save_type][0] + 2
    group_name = _class_to_save_group.get(charclass)
    if group_name is None:
        group_name = "bard_fighter_ranger"
    saves, brackets = _save_groups[group_name]
    # Find the bracket index: brackets define the upper bound of each tier
    idx = len(brackets)  # default to last tier (highest levels)
    for i, upper in enumerate(brackets):
        if level <= upper:
            idx = i
            break
    return saves[save_type][idx]


def calculate_derived_stats(char_data):
    """Given whatever fields are non-None, compute all derivable stats.

    char_data keys mirror Character model fields plus related data.
    Returns a dict of derived stat values (None for anything that can't be computed).
    """
    result = {}

    # Ability-derived stats
    char_class = char_data.get("char_class")
    pct = char_data.get("percentile_strength")
    # Only fighters get percentile strength bonuses on attack/damage
    str_pct = pct if char_class == "fighter" else None
    for ability_name, derived_stats in abilities.items():
        score = char_data.get(ability_name)
        if score is not None:
            for stat_name, func in derived_stats.items():
                if stat_name == "bonus HP per level":
                    result[stat_name] = func(score, char_data.get("char_class"))
                elif ability_name == "strength":
                    result[stat_name] = func(score, str_pct)
                else:
                    result[stat_name] = func(score)
        else:
            for stat_name in derived_stats:
                result[stat_name] = None

    # THAC0
    level = char_data.get("level")
    if char_class and level:
        result["thac0"] = thac0(char_class, level)
    else:
        result["thac0"] = None

    # XP for next level
    if char_class and level is not None:
        result["xp_for_next_level"] = total_xp_for_next_level(char_class, level)
    else:
        result["xp_for_next_level"] = None

    # Saving throws
    if level is not None:
        for cat in SAVING_THROW_CATEGORIES:
            result[f"save_{cat}"] = character_saving_throw_target(
                char_class, level or 0, cat
            )
    else:
        for cat in SAVING_THROW_CATEGORIES:
            result[f"save_{cat}"] = None

    return result
