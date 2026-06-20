"""Tests for the rules module."""

from django.test import TestCase

from characters.rules import (
    calculate_derived_stats,
    cha_max_henchmen,
    cha_morale_adj,
    character_saving_throw_target,
    con_max_hp_increase_adjustment,
    con_resurrection_survival_chance,
    con_system_shock_survival_chance,
    dex_ac_mod,
    dex_initiative_mod,
    dex_ranged_attacks_mod,
    effective_strength,
    int_max_mage_illusionist_spell_level,
    int_min_capable_spells,
    int_spell_capability_chance,
    maximum_encumbrance,
    maximum_hp,
    str_attack_mod,
    str_damage_mod,
    thac0,
    total_xp_for_next_level,
    wis_charm_illusion_save_mod,
    wis_cleric_spell_success_percent,
)
from characters.units import D


class StrengthModTests(TestCase):
    # --- Base table (no percentile) ---
    def test_str_3(self):
        self.assertEqual(str_attack_mod(3), -3)
        self.assertEqual(str_damage_mod(3), -2)

    def test_str_4(self):
        self.assertEqual(str_attack_mod(4), -2)
        self.assertEqual(str_damage_mod(4), -1)

    def test_str_5(self):
        self.assertEqual(str_attack_mod(5), -1)
        self.assertEqual(str_damage_mod(5), 0)

    def test_str_6_to_15(self):
        for s in range(6, 16):
            self.assertEqual(str_attack_mod(s), 0, f"attack for STR {s}")
            self.assertEqual(str_damage_mod(s), 0, f"damage for STR {s}")

    def test_str_16(self):
        self.assertEqual(str_attack_mod(16), 0)
        self.assertEqual(str_damage_mod(16), 1)

    def test_str_17(self):
        self.assertEqual(str_attack_mod(17), 1)
        self.assertEqual(str_damage_mod(17), 1)

    def test_str_18_no_pct(self):
        self.assertEqual(str_attack_mod(18), 1)
        self.assertEqual(str_damage_mod(18), 2)

    def test_str_19(self):
        self.assertEqual(str_attack_mod(19), 3)
        self.assertEqual(str_damage_mod(19), 7)

    def test_str_20(self):
        self.assertEqual(str_attack_mod(20), 3)
        self.assertEqual(str_damage_mod(20), 8)

    def test_str_25(self):
        self.assertEqual(str_attack_mod(25), 7)
        self.assertEqual(str_damage_mod(25), 14)

    # --- Percentile strength breakpoints ---
    def test_pct_01_to_50(self):
        for pct in (1, 25, 50):
            self.assertEqual(str_attack_mod(18, pct), 1, f"attack 18/{pct}")
            self.assertEqual(str_damage_mod(18, pct), 3, f"damage 18/{pct}")

    def test_pct_51_to_75(self):
        for pct in (51, 75):
            self.assertEqual(str_attack_mod(18, pct), 2, f"attack 18/{pct}")
            self.assertEqual(str_damage_mod(18, pct), 3, f"damage 18/{pct}")

    def test_pct_76_to_90(self):
        for pct in (76, 90):
            self.assertEqual(str_attack_mod(18, pct), 2, f"attack 18/{pct}")
            self.assertEqual(str_damage_mod(18, pct), 4, f"damage 18/{pct}")

    def test_pct_91_to_99(self):
        for pct in (91, 99):
            self.assertEqual(str_attack_mod(18, pct), 2, f"attack 18/{pct}")
            self.assertEqual(str_damage_mod(18, pct), 5, f"damage 18/{pct}")

    def test_pct_100(self):
        self.assertEqual(str_attack_mod(18, 100), 3)
        self.assertEqual(str_damage_mod(18, 100), 6)

    # --- Percentile ignored for non-18 ---
    def test_pct_ignored_for_non_18(self):
        self.assertEqual(str_attack_mod(17, 50), 1)
        self.assertEqual(str_damage_mod(17, 50), 1)

    def test_negative_raises(self):
        with self.assertRaises(ValueError):
            str_attack_mod(-1)


class EffectiveStrengthTests(TestCase):
    def test_no_modifier(self):
        self.assertEqual(effective_strength(15, None, 0), (15, None))
        self.assertEqual(effective_strength(18, 50, 0), (18, 50))

    def test_none_base(self):
        self.assertEqual(effective_strength(None, None, 2), (None, None))

    def test_below_18_stays_below(self):
        self.assertEqual(effective_strength(14, None, 2), (16, None))

    def test_crosses_18_boundary(self):
        # 17 + 2: first +1 → 18, second +1 → 18/10
        self.assertEqual(effective_strength(17, None, 2), (18, 10))

    def test_at_18_no_pct_plus_one(self):
        # 18 (no pct) + 1 → 18/10
        self.assertEqual(effective_strength(18, None, 1), (18, 10))

    def test_at_18_with_pct_plus_two(self):
        # Zoltan: 18/10 + 2 → 18/30
        self.assertEqual(effective_strength(18, 10, 2), (18, 30))

    def test_overflow_past_100(self):
        # 18/90 + 2 → 18/100, then +1 → 19
        self.assertEqual(effective_strength(18, 90, 2), (19, None))

    def test_above_18_normal_addition(self):
        self.assertEqual(effective_strength(19, None, 2), (21, None))

    def test_negative_from_18_with_pct(self):
        # 18/30 - 1 → 18/20
        self.assertEqual(effective_strength(18, 30, -1), (18, 20))

    def test_negative_drains_pct_to_none(self):
        # 18/10 - 1 → plain 18
        self.assertEqual(effective_strength(18, 10, -1), (18, None))

    def test_negative_from_plain_18(self):
        # 18 (no pct) - 1 → 17
        self.assertEqual(effective_strength(18, None, -1), (17, None))

    def test_negative_from_19_to_18_100(self):
        # 19 - 1 → 18/100
        self.assertEqual(effective_strength(19, None, -1), (18, 100))

    def test_negative_from_above_19(self):
        self.assertEqual(effective_strength(21, None, -2), (19, None))


class DexterityModTests(TestCase):
    def test_ac_mod(self):
        self.assertEqual(dex_ac_mod(3), -4)
        self.assertEqual(dex_ac_mod(6), -1)
        self.assertEqual(dex_ac_mod(10), 0)
        self.assertEqual(dex_ac_mod(14), 0)
        self.assertEqual(dex_ac_mod(15), 1)
        self.assertEqual(dex_ac_mod(16), 2)
        self.assertEqual(dex_ac_mod(17), 3)
        self.assertEqual(dex_ac_mod(18), 3)

    def test_ranged_mod(self):
        self.assertEqual(dex_ranged_attacks_mod(10), 0)
        self.assertEqual(dex_ranged_attacks_mod(15), 0)
        self.assertEqual(dex_ranged_attacks_mod(16), 1)
        self.assertEqual(dex_ranged_attacks_mod(17), 2)
        self.assertEqual(dex_ranged_attacks_mod(18), 3)

    def test_initiative_mod(self):
        self.assertEqual(dex_initiative_mod(5), -1)
        self.assertEqual(dex_initiative_mod(6), 0)
        self.assertEqual(dex_initiative_mod(10), 0)
        self.assertEqual(dex_initiative_mod(15), 0)
        self.assertEqual(dex_initiative_mod(16), 1)
        self.assertEqual(dex_initiative_mod(17), 2)
        self.assertEqual(dex_initiative_mod(18), 3)


class ConstitutionTests(TestCase):
    def test_hp_increase_low(self):
        self.assertEqual(con_max_hp_increase_adjustment(3), -2)
        self.assertEqual(con_max_hp_increase_adjustment(4), -1)
        self.assertEqual(con_max_hp_increase_adjustment(6), -1)

    def test_hp_increase_average(self):
        self.assertEqual(con_max_hp_increase_adjustment(10), 0)
        self.assertEqual(con_max_hp_increase_adjustment(14), 0)

    def test_hp_increase_high_fighter(self):
        self.assertEqual(con_max_hp_increase_adjustment(17, "fighter"), 3)
        self.assertEqual(con_max_hp_increase_adjustment(18, "fighter"), 4)

    def test_hp_increase_high_mage(self):
        # Non-martial classes cap at +2
        self.assertEqual(con_max_hp_increase_adjustment(17, "mage"), 2)
        self.assertEqual(con_max_hp_increase_adjustment(18, "mage"), 2)

    def test_system_shock(self):
        self.assertEqual(con_system_shock_survival_chance(3), 35)
        self.assertEqual(con_system_shock_survival_chance(10), 70)
        self.assertEqual(con_system_shock_survival_chance(14), 89)
        self.assertEqual(con_system_shock_survival_chance(15), 93)
        self.assertEqual(con_system_shock_survival_chance(18), 99)

    def test_resurrection_survival(self):
        self.assertEqual(con_resurrection_survival_chance(3), 39)
        self.assertEqual(con_resurrection_survival_chance(10), 77)
        self.assertEqual(con_resurrection_survival_chance(18), 99.5)


class IntelligenceTests(TestCase):
    def test_no_spells_below_9(self):
        self.assertIsNone(int_max_mage_illusionist_spell_level(8))

    def test_spell_levels(self):
        self.assertEqual(int_max_mage_illusionist_spell_level(9), 4)
        self.assertEqual(int_max_mage_illusionist_spell_level(10), 5)
        self.assertEqual(int_max_mage_illusionist_spell_level(11), 5)
        self.assertEqual(int_max_mage_illusionist_spell_level(12), 6)
        self.assertEqual(int_max_mage_illusionist_spell_level(13), 6)
        self.assertEqual(int_max_mage_illusionist_spell_level(14), 7)
        self.assertEqual(int_max_mage_illusionist_spell_level(15), 7)
        self.assertEqual(int_max_mage_illusionist_spell_level(16), 8)
        self.assertEqual(int_max_mage_illusionist_spell_level(17), 8)
        self.assertEqual(int_max_mage_illusionist_spell_level(18), 9)
        self.assertEqual(int_max_mage_illusionist_spell_level(19), 9)

    def test_min_capable_spells(self):
        self.assertIsNone(int_min_capable_spells(8))
        self.assertEqual(int_min_capable_spells(9), 8)
        self.assertEqual(int_min_capable_spells(10), 9)
        self.assertEqual(int_min_capable_spells(11), 9)
        self.assertEqual(int_min_capable_spells(12), 9)
        self.assertEqual(int_min_capable_spells(13), 10)
        self.assertEqual(int_min_capable_spells(14), 12)
        self.assertEqual(int_min_capable_spells(16), 14)
        self.assertEqual(int_min_capable_spells(17), 16)
        self.assertEqual(int_min_capable_spells(18), 18)
        self.assertEqual(int_min_capable_spells(19), 19)

    def test_capability_chance(self):
        self.assertIsNone(int_spell_capability_chance(8))
        self.assertEqual(int_spell_capability_chance(9), 35)
        self.assertEqual(int_spell_capability_chance(18), 85)


class WisdomTests(TestCase):
    def test_charm_save_mod(self):
        self.assertEqual(wis_charm_illusion_save_mod(3), -3)
        self.assertEqual(wis_charm_illusion_save_mod(4), -2)
        self.assertEqual(wis_charm_illusion_save_mod(5), -1)
        self.assertEqual(wis_charm_illusion_save_mod(7), -1)
        self.assertEqual(wis_charm_illusion_save_mod(8), 0)
        self.assertEqual(wis_charm_illusion_save_mod(10), 0)
        self.assertEqual(wis_charm_illusion_save_mod(14), 0)
        self.assertEqual(wis_charm_illusion_save_mod(15), 1)
        self.assertEqual(wis_charm_illusion_save_mod(16), 2)
        self.assertEqual(wis_charm_illusion_save_mod(17), 3)
        self.assertEqual(wis_charm_illusion_save_mod(18), 4)
        self.assertEqual(wis_charm_illusion_save_mod(19), 5)
        self.assertEqual(wis_charm_illusion_save_mod(20), 6)

    def test_cleric_spell_success(self):
        self.assertIsNone(wis_cleric_spell_success_percent(8))
        self.assertEqual(wis_cleric_spell_success_percent(9), 80)
        self.assertEqual(wis_cleric_spell_success_percent(10), 85)
        self.assertEqual(wis_cleric_spell_success_percent(11), 90)
        self.assertEqual(wis_cleric_spell_success_percent(12), 95)
        self.assertEqual(wis_cleric_spell_success_percent(13), 100)


class CharismaTests(TestCase):
    def test_max_henchmen(self):
        self.assertEqual(cha_max_henchmen(1), 1)
        self.assertEqual(cha_max_henchmen(4), 1)
        self.assertEqual(cha_max_henchmen(9), 4)
        self.assertEqual(cha_max_henchmen(10), 4)
        self.assertEqual(cha_max_henchmen(11), 4)
        self.assertEqual(cha_max_henchmen(12), 5)
        self.assertEqual(cha_max_henchmen(13), 5)
        self.assertEqual(cha_max_henchmen(14), 6)
        self.assertEqual(cha_max_henchmen(15), 7)
        self.assertEqual(cha_max_henchmen(16), 8)
        self.assertEqual(cha_max_henchmen(17), 9)
        self.assertEqual(cha_max_henchmen(18), 10)

    def test_morale_adj(self):
        self.assertEqual(cha_morale_adj(3), 3)
        self.assertEqual(cha_morale_adj(5), 3)
        self.assertEqual(cha_morale_adj(6), 2)
        self.assertEqual(cha_morale_adj(7), 2)
        self.assertEqual(cha_morale_adj(8), 1)
        self.assertEqual(cha_morale_adj(9), 0)
        self.assertEqual(cha_morale_adj(13), 0)
        self.assertEqual(cha_morale_adj(14), -1)
        self.assertEqual(cha_morale_adj(15), -2)
        self.assertEqual(cha_morale_adj(16), -2)
        self.assertEqual(cha_morale_adj(17), -3)
        self.assertEqual(cha_morale_adj(18), -3)


class THAC0Tests(TestCase):
    def test_fighter_thac0(self):
        self.assertEqual(thac0("fighter", 1), 20)
        self.assertEqual(thac0("fighter", 5), 16)
        self.assertEqual(thac0("fighter", 10), 12)

    def test_mage_thac0(self):
        self.assertEqual(thac0("mage", 1), 21)
        self.assertEqual(thac0("mage", 5), 20)

    def test_none_class(self):
        self.assertEqual(thac0(None, 1), 21)


class MaximumHPTests(TestCase):
    def test_basic_hp(self):
        hit_dice = [
            {"level": 1, "die_type": "d10", "roll": 8, "con_bonus": 1},
            {"level": 2, "die_type": "d10", "roll": 6, "con_bonus": 1},
        ]
        self.assertEqual(maximum_hp(hit_dice, "fighter"), 16)

    def test_minimum_hp(self):
        hit_dice = [{"level": 1, "die_type": "d4", "roll": 1, "con_bonus": -2}]
        self.assertEqual(maximum_hp(hit_dice, "mage"), 1)

    def test_bonus_hp_added(self):
        hit_dice = [{"level": 1, "die_type": "d10", "roll": 8, "con_bonus": 1}]
        self.assertEqual(maximum_hp(hit_dice, "fighter", bonus_hp=4), 13)

    def test_bonus_hp_only(self):
        self.assertEqual(maximum_hp([], "fighter", bonus_hp=5), 5)


class XPTests(TestCase):
    def test_fighter_xp(self):
        self.assertEqual(total_xp_for_next_level("fighter", 1), 2001)
        self.assertEqual(total_xp_for_next_level("fighter", 5), 35001)

    def test_none_class(self):
        self.assertEqual(total_xp_for_next_level(None, 0), 1500)

    def test_max_level(self):
        self.assertIsNone(total_xp_for_next_level("fighter", 20))


class EncumbranceTests(TestCase):
    def test_basic_encumbrance(self):
        # STR 15, 175 lb body weight: lookup=170, 170*175/175 = 170 lb
        result = maximum_encumbrance(15, None, D(175), D(1))
        self.assertAlmostEqual(float(result.magnitude), 170.0, places=1)

    def test_light_character(self):
        # STR 15, 100 lb: 170 * 100/175 ≈ 97.14 → rounds to 97
        result = maximum_encumbrance(15, None, D(100), D(1))
        self.assertEqual(result.magnitude, D(97))

    def test_percentile_strength(self):
        # STR 18/50, 175 lb: lookup for 18.1 = 200, 200*175/175 = 200
        result = maximum_encumbrance(18, 50, D(175), D(1))
        self.assertAlmostEqual(float(result.magnitude), 200.0, places=1)

    def test_percentile_100(self):
        # STR 18/00, 175 lb: lookup for 18.5 = 240
        result = maximum_encumbrance(18, 100, D(175), D(1))
        self.assertAlmostEqual(float(result.magnitude), 240.0, places=1)

    def test_rounding(self):
        # STR 18/30, 194 lb: 200 * 194/175 = 221.71 → rounds to 222
        result = maximum_encumbrance(18, 30, D(194), D(1))
        self.assertEqual(result.magnitude, D(222))

    def test_encumbrance_multiplier(self):
        # STR 15, 175 lb, mult 1.5: 170 * 1.5 = 255
        result = maximum_encumbrance(15, None, D(175), D("1.5"))
        self.assertEqual(result.magnitude, D(255))


class SavingThrowTests(TestCase):
    def test_fighter_saves_level_1(self):
        # Bard/Fighter/Ranger group, level 1 (bracket 1-3)
        self.assertEqual(character_saving_throw_target("fighter", 1, "poison"), 15)
        self.assertEqual(character_saving_throw_target("fighter", 1, "paralyse"), 15)
        self.assertEqual(character_saving_throw_target("fighter", 1, "polymorph"), 16)
        self.assertEqual(
            character_saving_throw_target("fighter", 1, "rod_staff_wand"), 15
        )
        self.assertEqual(character_saving_throw_target("fighter", 1, "breath"), 17)
        self.assertEqual(character_saving_throw_target("fighter", 1, "magic"), 15)

    def test_fighter_saves_level_5(self):
        # Bracket 4-7
        self.assertEqual(character_saving_throw_target("fighter", 5, "poison"), 14)
        self.assertEqual(character_saving_throw_target("fighter", 5, "breath"), 16)

    def test_fighter_saves_level_16(self):
        # Bracket 16+
        self.assertEqual(character_saving_throw_target("fighter", 16, "poison"), 9)
        self.assertEqual(character_saving_throw_target("fighter", 16, "magic"), 9)

    def test_thief_saves(self):
        # Assassin/Thief group, level 1 (bracket 1-6)
        self.assertEqual(character_saving_throw_target("thief", 1, "poison"), 13)
        self.assertEqual(
            character_saving_throw_target("thief", 1, "rod_staff_wand"), 14
        )

    def test_mage_saves(self):
        # Illusionist/Mage/Monk group, level 1 (bracket 1-4)
        self.assertEqual(character_saving_throw_target("mage", 1, "poison"), 14)
        self.assertEqual(character_saving_throw_target("mage", 1, "rod_staff_wand"), 11)

    def test_cleric_saves(self):
        # Cleric/Druid/Paladin group, level 1 (bracket 1-4)
        self.assertEqual(character_saving_throw_target("cleric", 1, "poison"), 12)
        self.assertEqual(character_saving_throw_target("cleric", 1, "magic"), 15)

    def test_bard_uses_fighter_group(self):
        self.assertEqual(character_saving_throw_target("bard", 1, "poison"), 15)

    def test_monk_uses_mage_group(self):
        self.assertEqual(character_saving_throw_target("monk", 1, "poison"), 14)

    def test_no_class_saves(self):
        # No class gets penalized fighter group saves
        self.assertEqual(character_saving_throw_target(None, 0, "poison"), 17)


class DerivedStatsTests(TestCase):
    def test_partial_data(self):
        """Some fields None should produce None for those derived stats."""
        stats = calculate_derived_stats({"strength": 15})
        self.assertEqual(stats["melee attack modifier"], 0)
        self.assertIsNone(stats["AC modifier"])
        self.assertIsNone(stats["thac0"])

    def test_full_data(self):
        stats = calculate_derived_stats(
            {
                "strength": 15,
                "dexterity": 14,
                "constitution": 12,
                "intelligence": 10,
                "wisdom": 13,
                "charisma": 11,
                "char_class": "fighter",
                "level": 3,
            }
        )
        self.assertEqual(stats["melee attack modifier"], 0)
        self.assertEqual(stats["thac0"], 18)
        self.assertEqual(stats["xp_for_next_level"], 8001)
        self.assertEqual(stats["save_poison"], 15)

    def test_fighter_percentile_strength(self):
        """Fighter with 18/75 should get percentile bonuses."""
        stats = calculate_derived_stats(
            {
                "strength": 18,
                "char_class": "fighter",
                "level": 1,
                "percentile_strength": 75,
            }
        )
        self.assertEqual(stats["melee attack modifier"], 2)
        self.assertEqual(stats["melee damage modifier"], 3)

    def test_non_fighter_percentile_ignored(self):
        """Non-fighter with 18/75 should use flat 18 row."""
        stats = calculate_derived_stats(
            {
                "strength": 18,
                "char_class": "mage",
                "level": 1,
                "percentile_strength": 75,
            }
        )
        self.assertEqual(stats["melee attack modifier"], 1)
        self.assertEqual(stats["melee damage modifier"], 2)

    def test_empty_data(self):
        stats = calculate_derived_stats({})
        for value in stats.values():
            self.assertIsNone(value)
