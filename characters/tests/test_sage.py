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


from django.test import Client


class SageChosenFieldViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="view_tester", password="pass")
        self.client = Client()
        self.client.login(username="view_tester", password="pass")
        self.character = Character.objects.create(
            user=self.user, name="Olivia", char_class="fighter"
        )

    def _url(self, path):
        return f"/character/{self.character.pk}/sage/{path}"

    def test_chosen_field_saves_valid(self):
        response = self.client.post(
            self._url("chosen-field/"),
            {"chosen_field": "Animal Training", "chosen_study": "Horseback Riding"},
        )
        self.assertEqual(response.status_code, 200)
        self.character.refresh_from_db()
        self.assertEqual(self.character.chosen_field, "Animal Training")
        self.assertEqual(self.character.chosen_study, "Horseback Riding")

    def test_chosen_field_invalid_field_returns_400(self):
        response = self.client.post(
            self._url("chosen-field/"),
            {"chosen_field": "Not A Real Field", "chosen_study": "Whatever"},
        )
        self.assertEqual(response.status_code, 400)

    def test_chosen_field_invalid_study_returns_400(self):
        response = self.client.post(
            self._url("chosen-field/"),
            {"chosen_field": "Animal Training", "chosen_study": "Not A Study"},
        )
        self.assertEqual(response.status_code, 400)

    def test_chosen_field_bulk_creates_fighter_studies(self):
        from characters.sage import CLASS_FIELDS, sage_fields
        expected_count = len(
            dict.fromkeys(
                s
                for f in CLASS_FIELDS["fighter"]
                for s in sage_fields[f]["studies"]
            )
        )
        self.client.post(
            self._url("chosen-field/"),
            {"chosen_field": "Animal Training", "chosen_study": "Horseback Riding"},
        )
        self.assertEqual(
            SageStudyPoints.objects.filter(character=self.character).count(),
            expected_count,
        )

    def test_chosen_field_repost_preserves_points(self):
        SageStudyPoints.objects.create(
            character=self.character, study="Horseback Riding", points=42
        )
        self.client.post(
            self._url("chosen-field/"),
            {"chosen_field": "Animal Training", "chosen_study": "Horseback Riding"},
        )
        row = SageStudyPoints.objects.get(
            character=self.character, study="Horseback Riding"
        )
        self.assertEqual(row.points, 42)

    def test_chosen_field_unknown_class_no_rows_created(self):
        self.character.char_class = "wizard"
        self.character.save()
        self.client.post(
            self._url("chosen-field/"),
            {"chosen_field": "Animal Training", "chosen_study": "Horseback Riding"},
        )
        self.assertEqual(
            SageStudyPoints.objects.filter(character=self.character).count(), 0
        )


class SageStudyPointsViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="pts_tester", password="pass")
        self.client = Client()
        self.client.login(username="pts_tester", password="pass")
        self.character = Character.objects.create(user=self.user, name="Rask")
        self.row = SageStudyPoints.objects.create(
            character=self.character, study="Forgery", points=10
        )

    def _url(self):
        return f"/character/{self.character.pk}/sage/study/{self.row.pk}/points/"

    def test_valid_update(self):
        response = self.client.post(self._url(), {"points": "25"})
        self.assertEqual(response.status_code, 200)
        self.row.refresh_from_db()
        self.assertEqual(self.row.points, 25)

    def test_wrong_character_returns_404(self):
        other_user = User.objects.create_user(username="other2", password="pass")
        other_char = Character.objects.create(user=other_user, name="Enemy")
        other_row = SageStudyPoints.objects.create(
            character=other_char, study="Forgery", points=5
        )
        url = f"/character/{self.character.pk}/sage/study/{other_row.pk}/points/"
        response = self.client.post(url, {"points": "10"})
        self.assertEqual(response.status_code, 404)

    def test_negative_points_returns_400(self):
        response = self.client.post(self._url(), {"points": "-1"})
        self.assertEqual(response.status_code, 400)

    def test_non_integer_points_returns_400(self):
        response = self.client.post(self._url(), {"points": "abc"})
        self.assertEqual(response.status_code, 400)

    def test_missing_points_returns_400(self):
        response = self.client.post(self._url(), {})
        self.assertEqual(response.status_code, 400)


class SageStudyAddViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="add_tester", password="pass")
        self.client = Client()
        self.client.login(username="add_tester", password="pass")
        self.character = Character.objects.create(user=self.user, name="Jared")

    def _url(self):
        return f"/character/{self.character.pk}/sage/study/add/"

    def test_valid_study_creates_row(self):
        response = self.client.post(self._url(), {"study": "Forgery"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            SageStudyPoints.objects.filter(
                character=self.character, study="Forgery", points=0
            ).exists()
        )

    def test_duplicate_study_is_idempotent(self):
        self.client.post(self._url(), {"study": "Forgery"})
        self.client.post(self._url(), {"study": "Forgery"})
        self.assertEqual(
            SageStudyPoints.objects.filter(
                character=self.character, study="Forgery"
            ).count(),
            1,
        )

    def test_unknown_study_returns_400(self):
        response = self.client.post(self._url(), {"study": "Not Real"})
        self.assertEqual(response.status_code, 400)


class SageChosenFieldFormViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="form_tester", password="pass")
        self.other_user = User.objects.create_user(username="other3", password="pass")
        self.client = Client()
        self.client.login(username="form_tester", password="pass")
        self.character = Character.objects.create(
            user=self.user, name="Thorn", chosen_field="Animal Training"
        )

    def test_unauthenticated_redirects(self):
        self.client.logout()
        url = f"/character/{self.character.pk}/sage/chosen-field/form/"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)

    def test_valid_returns_200_with_select(self):
        url = f"/character/{self.character.pk}/sage/chosen-field/form/"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Animal Training")
        self.assertContains(response, "<select")

    def test_wrong_user_returns_404(self):
        other_char = Character.objects.create(user=self.other_user, name="Enemy")
        url = f"/character/{other_char.pk}/sage/chosen-field/form/"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)
