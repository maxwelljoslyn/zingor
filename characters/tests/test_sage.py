"""Tests for sage catalogue and rank logic."""

from django.test import TestCase

from characters.sage import rank_for_points, sort_sage_entries, CLASS_FIELDS, sage_fields


class RankForPointsTests(TestCase):
    def test_zero_is_unranked(self):
        self.assertEqual(rank_for_points(0), "unranked")

    def test_nine_is_unranked(self):
        self.assertEqual(rank_for_points(9), "unranked")

    def test_ten_is_amateur(self):
        self.assertEqual(rank_for_points(10), "amateur")

    def test_twenty_nine_is_amateur(self):
        self.assertEqual(rank_for_points(29), "amateur")

    def test_thirty_is_authority(self):
        self.assertEqual(rank_for_points(30), "authority")

    def test_fifty_nine_is_authority(self):
        self.assertEqual(rank_for_points(59), "authority")

    def test_sixty_is_expert(self):
        self.assertEqual(rank_for_points(60), "expert")

    def test_ninety_nine_is_expert(self):
        self.assertEqual(rank_for_points(99), "expert")

    def test_hundred_is_sage(self):
        self.assertEqual(rank_for_points(100), "sage")


class SortSageEntriesTests(TestCase):
    def test_empty_dict_returns_empty_list(self):
        self.assertEqual(sort_sage_entries({}), [])

    def test_entries_have_expected_keys(self):
        result = sort_sage_entries({"Horseback Riding": 15})
        self.assertEqual(len(result), 1)
        entry = result[0]
        self.assertEqual(entry["name"], "Horseback Riding")
        self.assertEqual(entry["points"], 15)
        self.assertEqual(entry["rank"], "amateur")
        self.assertIn("rank_order", entry)

    def test_default_sort_best_rank_first(self):
        entries = {"A Study": 0, "B Study": 100, "C Study": 30}
        result = sort_sage_entries(entries)
        self.assertEqual(result[0]["rank"], "sage")
        self.assertEqual(result[-1]["rank"], "unranked")


class ClassFieldsTests(TestCase):
    def test_fighter_fields_exist_in_sage_fields(self):
        for field_name in CLASS_FIELDS["fighter"]:
            self.assertIn(field_name, sage_fields, f"{field_name} missing from sage_fields")

    def test_all_class_fields_exist_in_sage_fields(self):
        for cls, fields in CLASS_FIELDS.items():
            for field_name in fields:
                self.assertIn(
                    field_name, sage_fields,
                    f"Class {cls!r}: field {field_name!r} missing from sage_fields"
                )


from django.db import IntegrityError
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User
from characters.models import Character, SageStudyPoints


class SageStudyPointsModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="sage_tester", password="pass")
        self.character = Character.objects.create(user=self.user, name="Rask")

    def test_duplicate_character_study_raises_integrity_error(self):
        SageStudyPoints.objects.create(character=self.character, study="Forgery", points=10)
        with self.assertRaises(IntegrityError):
            SageStudyPoints.objects.create(character=self.character, study="Forgery", points=5)

    def test_negative_points_raises_validation_error(self):
        row = SageStudyPoints(character=self.character, study="Forgery", points=-1)
        with self.assertRaises(ValidationError):
            row.full_clean()

    def test_zero_points_is_valid(self):
        row = SageStudyPoints(character=self.character, study="Forgery", points=0)
        row.full_clean()  # should not raise

    def test_chosen_field_defaults_none(self):
        char = Character.objects.create(user=self.user, name="Empty")
        self.assertIsNone(char.chosen_field)
        self.assertIsNone(char.chosen_study)
