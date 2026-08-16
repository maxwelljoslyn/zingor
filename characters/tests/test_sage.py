"""Tests for sage catalogue and rank logic."""

import re

from django.test import TestCase

from characters.sage import (
    CLASS_FIELDS,
    CONCENTRATIONS,
    alexisify,
    concentration_label,
    format_study,
    linkify_field,
    linkify_study,
    rank_for_points,
    rank_studies,
    sage_fields,
    sage_studies,
    sort_sage_entries,
)


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

    def test_below_lowest_threshold_is_unranked(self):
        # Negative points fall through every threshold to the "unranked" default.
        self.assertEqual(rank_for_points(-5), "unranked")


class RankStudiesTests(TestCase):
    def test_studies_bucketed_by_rank(self):
        result = rank_studies({"Sage One": 100, "Amateur One": 15, "Nobody": 0})
        self.assertEqual(result["sage"], {"Sage One": 100})
        self.assertEqual(result["amateur"], {"Amateur One": 15})
        self.assertEqual(result["unranked"], {"Nobody": 0})
        self.assertEqual(result["expert"], {})

    def test_empty_input_yields_empty_buckets(self):
        result = rank_studies({})
        self.assertEqual(
            set(result), {"sage", "expert", "authority", "amateur", "unranked"}
        )
        self.assertTrue(all(bucket == {} for bucket in result.values()))


class AlexisifyTests(TestCase):
    def test_empty_string_raises(self):
        with self.assertRaises(ValueError):
            alexisify("")

    def test_plain_name_passes_through(self):
        self.assertEqual(alexisify("Forgery"), "Forgery")

    def test_and_becomes_ampersand(self):
        self.assertEqual(alexisify("Music and Design"), "Music & Design")

    def test_parenthetical_is_stripped(self):
        self.assertEqual(alexisify("Horseback Riding (mounted)"), "Horseback Riding")

    def test_alexis_name_alias_is_preferred(self):
        # "Double-Dealing" is stored under the wiki's spelling "Double-dealing".
        self.assertEqual(alexisify("Double-Dealing"), "Double-dealing")


class SageLinkifyTests(TestCase):
    def test_linkify_field_wraps_display_text_and_field_url(self):
        html = linkify_field("Forgery")
        self.assertIn(">Forgery</a>", html)
        self.assertIn("Forgery_(sage_field)", html)

    def test_linkify_study_uses_study_suffix(self):
        html = linkify_study("Forgery")
        self.assertIn("Forgery_(sage_study)", html)


class SortSageEntriesByPointsTests(TestCase):
    def test_ascending_points_sort(self):
        entries = {"Low": 10, "High": 100, "Mid": 30}
        result = sort_sage_entries(entries, sort_keys=["points"])
        self.assertEqual([e["name"] for e in result], ["Low", "Mid", "High"])

    def test_descending_points_sort(self):
        entries = {"Low": 10, "High": 100, "Mid": 30}
        result = sort_sage_entries(entries, sort_keys=["-points"])
        self.assertEqual([e["name"] for e in result], ["High", "Mid", "Low"])


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
            self.assertIn(
                field_name, sage_fields, f"{field_name} missing from sage_fields"
            )

    def test_all_class_fields_exist_in_sage_fields(self):
        for cls, fields in CLASS_FIELDS.items():
            for field_name in fields:
                self.assertIn(
                    field_name,
                    sage_fields,
                    f"Class {cls!r}: field {field_name!r} missing from sage_fields",
                )


class ConcentrationCatalogueTests(TestCase):
    def test_every_concentration_study_is_in_the_catalogue(self):
        for study in CONCENTRATIONS:
            self.assertIn(study, sage_studies, f"{study} missing from sage_studies")

    def test_label_names_what_an_area_is(self):
        self.assertEqual(concentration_label("History"), "region and era")

    def test_study_without_areas_has_no_label(self):
        self.assertIsNone(concentration_label("Forgery"))

    def test_athletics_takes_no_areas(self):
        # Its disciplines are sage abilities of their own, so they belong in
        # the standalone abilities table rather than under the study (#171).
        self.assertIsNone(concentration_label("Athletics"))


class FormatStudyTests(TestCase):
    def test_area_is_parenthesised_after_the_study(self):
        self.assertEqual(
            format_study("History", "Ancient European"), "History (Ancient European)"
        )

    def test_no_area_leaves_the_study_alone(self):
        self.assertEqual(format_study("Forgery", ""), "Forgery")

    def test_area_defaults_to_none(self):
        self.assertEqual(format_study("Forgery"), "Forgery")


from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from characters.models import Character, SageChosenField, SageStudyPoints


class SageStudyPointsModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="sage_tester", password="pass")
        self.character = Character.objects.create(user=self.user, name="Rask")

    def test_duplicate_character_study_raises_integrity_error(self):
        SageStudyPoints.objects.create(
            character=self.character, study="Forgery", points=10
        )
        with self.assertRaises(IntegrityError):
            SageStudyPoints.objects.create(
                character=self.character, study="Forgery", points=5
            )

    def test_negative_points_raises_validation_error(self):
        row = SageStudyPoints(character=self.character, study="Forgery", points=-1)
        with self.assertRaises(ValidationError):
            row.full_clean()

    def test_zero_points_is_valid(self):
        row = SageStudyPoints(character=self.character, study="Forgery", points=0)
        row.full_clean()  # should not raise

    def test_study_is_not_chosen_by_default(self):
        row = SageStudyPoints.objects.create(character=self.character, study="Forgery")
        self.assertFalse(row.chosen)

    def test_study_has_no_concentration_by_default(self):
        row = SageStudyPoints.objects.create(character=self.character, study="Forgery")
        self.assertEqual(row.concentration, "")
        self.assertEqual(row.display_name, "Forgery")

    def test_display_name_carries_the_area(self):
        row = SageStudyPoints.objects.create(
            character=self.character, study="History", concentration="Ancient European"
        )
        self.assertEqual(row.display_name, "History (Ancient European)")

    def test_two_areas_of_one_study_are_two_rows(self):
        SageStudyPoints.objects.create(
            character=self.character,
            study="History",
            concentration="Ancient European",
            points=20,
        )
        SageStudyPoints.objects.create(
            character=self.character,
            study="History",
            concentration="Ancient African",
            points=5,
        )
        self.assertEqual(self.character.sage_studies.filter(study="History").count(), 2)

    def test_the_whole_study_coexists_with_its_areas(self):
        # A blank area is its own row, not a placeholder for the others.
        SageStudyPoints.objects.create(character=self.character, study="History")
        SageStudyPoints.objects.create(
            character=self.character, study="History", concentration="Ancient European"
        )
        self.assertEqual(self.character.sage_studies.filter(study="History").count(), 2)

    def test_duplicate_area_of_one_study_raises_integrity_error(self):
        SageStudyPoints.objects.create(
            character=self.character, study="History", concentration="Ancient European"
        )
        with self.assertRaises(IntegrityError):
            SageStudyPoints.objects.create(
                character=self.character,
                study="History",
                concentration="Ancient European",
            )


class SageChosenFieldModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="field_tester", password="pass")
        self.character = Character.objects.create(user=self.user, name="Rask")

    def test_character_starts_with_no_chosen_fields(self):
        self.assertEqual(self.character.chosen_fields.count(), 0)

    def test_duplicate_character_field_raises_integrity_error(self):
        SageChosenField.objects.create(
            character=self.character, field="Animal Training"
        )
        with self.assertRaises(IntegrityError):
            SageChosenField.objects.create(
                character=self.character, field="Animal Training"
            )


from django.test import Client


class SageFieldChosenViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="view_tester", password="pass")
        self.client = Client()
        self.client.login(username="view_tester", password="pass")
        self.character = Character.objects.create(
            user=self.user, name="Olivia", char_class="fighter"
        )

    def _url(self, path):
        return f"/character/{self.character.pk}/sage/{path}"

    def _add(self, field):
        """Tick a field's Chosen box (what the Add Field picker posts too)."""
        return self.client.post(
            self._url("field/chosen/"), {"field": field, "chosen": "1"}
        )

    def _unchoose(self, field):
        """An unticked checkbox submits its name but no value."""
        return self.client.post(self._url("field/chosen/"), {"field": field})

    def test_valid_field_is_recorded(self):
        response = self._add("Animal Training")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            list(self.character.chosen_fields.values_list("field", flat=True)),
            ["Animal Training"],
        )

    def test_invalid_field_returns_400(self):
        response = self._add("Not A Real Field")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(self.character.chosen_fields.exists())

    def test_second_field_joins_the_first(self):
        self._add("Animal Training")
        self._add("Leadership")
        self.assertEqual(
            list(self.character.chosen_fields.values_list("field", flat=True)),
            ["Animal Training", "Leadership"],
        )

    def test_repeat_choice_is_idempotent(self):
        self._add("Animal Training")
        self._add("Animal Training")
        self.assertEqual(self.character.chosen_fields.count(), 1)

    def test_first_choice_bulk_creates_every_class_study(self):
        from characters.sage import CLASS_FIELDS, sage_fields

        expected = {
            s for f in CLASS_FIELDS["fighter"] for s in sage_fields[f]["studies"]
        }
        self._add("Animal Training")
        self.assertEqual(
            set(
                SageStudyPoints.objects.filter(character=self.character).values_list(
                    "study", flat=True
                )
            ),
            expected,
        )

    def test_later_choice_only_creates_its_own_fields_studies(self):
        from characters.sage import CLASS_FIELDS, sage_fields

        self._add("Animal Training")
        before = set(
            SageStudyPoints.objects.filter(character=self.character).values_list(
                "study", flat=True
            )
        )
        # Wilderland is a ranger field, not a fighter one: choosing it brings in
        # its own studies and nothing else.
        self.assertNotIn("Wilderland", CLASS_FIELDS["fighter"])
        self._add("Wilderland")
        after = set(
            SageStudyPoints.objects.filter(character=self.character).values_list(
                "study", flat=True
            )
        )
        self.assertEqual(after - before, set(sage_fields["Wilderland"]["studies"]))

    def test_shared_study_keeps_its_points_when_second_field_arrives(self):
        # Beasts belongs to both Reverence and Legends and Folklore, so choosing
        # the second of those must not reset the points earned under the first.
        self._add("Reverence")
        row = SageStudyPoints.objects.get(character=self.character, study="Beasts")
        row.points = 42
        row.save()
        self._add("Legends and Folklore")
        row.refresh_from_db()
        self.assertEqual(row.points, 42)
        self.assertEqual(
            SageStudyPoints.objects.filter(
                character=self.character, study="Beasts"
            ).count(),
            1,
        )

    def test_unticking_then_reticking_keeps_the_points(self):
        self._add("Animal Training")
        row = SageStudyPoints.objects.get(
            character=self.character, study="Horseback Riding"
        )
        row.points = 30
        row.save()
        self._unchoose("Animal Training")
        self._add("Animal Training")
        row.refresh_from_db()
        self.assertEqual(row.points, 30)
        self.assertEqual(self.character.chosen_fields.count(), 1)

    def test_unknown_class_creates_only_the_chosen_fields_studies(self):
        from characters.sage import sage_fields

        self.character.char_class = "wizard"
        self.character.save()
        self._add("Animal Training")
        self.assertEqual(
            set(
                SageStudyPoints.objects.filter(character=self.character).values_list(
                    "study", flat=True
                )
            ),
            set(sage_fields["Animal Training"]["studies"]),
        )


class SageFieldUnchooseViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="remove_tester", password="pass")
        self.client = Client()
        self.client.login(username="remove_tester", password="pass")
        self.character = Character.objects.create(
            user=self.user, name="Olivia", char_class="fighter"
        )
        self.row = SageChosenField.objects.create(
            character=self.character, field="Animal Training"
        )

    def _unchoose(self, field):
        return self.client.post(
            f"/character/{self.character.pk}/sage/field/chosen/", {"field": field}
        )

    def test_unticking_drops_the_choice_but_keeps_the_points(self):
        study = SageStudyPoints.objects.create(
            character=self.character, study="Falconry", points=17
        )
        response = self._unchoose("Animal Training")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(self.character.chosen_fields.exists())
        study.refresh_from_db()
        self.assertEqual(study.points, 17)

    def test_unticking_a_field_that_was_never_chosen_is_a_no_op(self):
        response = self._unchoose("Leadership")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.character.chosen_fields.count(), 1)

    def test_another_characters_choice_is_untouched(self):
        other_user = User.objects.create_user(username="other4", password="pass")
        other_char = Character.objects.create(user=other_user, name="Enemy")
        other_row = SageChosenField.objects.create(
            character=other_char, field="Animal Training"
        )
        self._unchoose("Animal Training")
        self.assertTrue(SageChosenField.objects.filter(pk=other_row.pk).exists())


class SageStudyChosenViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="chosen_tester", password="pass")
        self.client = Client()
        self.client.login(username="chosen_tester", password="pass")
        self.character = Character.objects.create(user=self.user, name="Rask")
        self.row = SageStudyPoints.objects.create(
            character=self.character, study="Forgery", points=10
        )

    def _url(self, study_pk=None):
        pk = self.row.pk if study_pk is None else study_pk
        return f"/character/{self.character.pk}/sage/study/{pk}/chosen/"

    def test_checked_box_marks_the_study_chosen(self):
        response = self.client.post(self._url(), {"chosen": "on"})
        self.assertEqual(response.status_code, 200)
        self.row.refresh_from_db()
        self.assertTrue(self.row.chosen)

    def test_unchecked_box_clears_the_mark(self):
        self.row.chosen = True
        self.row.save()
        # An unchecked checkbox submits nothing at all.
        self.client.post(self._url(), {})
        self.row.refresh_from_db()
        self.assertFalse(self.row.chosen)

    def test_wrong_character_returns_404(self):
        other_user = User.objects.create_user(username="other5", password="pass")
        other_char = Character.objects.create(user=other_user, name="Enemy")
        other_row = SageStudyPoints.objects.create(
            character=other_char, study="Forgery", points=5
        )
        response = self.client.post(self._url(other_row.pk), {"chosen": "on"})
        self.assertEqual(response.status_code, 404)


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


class SageStudyAddConcentrationTests(TestCase):
    """Adding a study that is taken by area of concentration (#171)."""

    def setUp(self):
        self.user = User.objects.create_user(username="area_tester", password="pass")
        self.client = Client()
        self.client.login(username="area_tester", password="pass")
        self.character = Character.objects.create(user=self.user, name="Lexent")

    def _add(self, study, concentration=""):
        return self.client.post(
            f"/character/{self.character.pk}/sage/study/add/",
            {"study": study, "concentration": concentration},
        )

    def test_area_is_recorded_on_the_row(self):
        response = self._add("History", "Ancient European")
        self.assertEqual(response.status_code, 200)
        row = SageStudyPoints.objects.get(character=self.character, study="History")
        self.assertEqual(row.concentration, "Ancient European")
        self.assertEqual(row.points, 0)

    def test_second_area_of_the_same_study_is_its_own_row(self):
        self._add("History", "Ancient European")
        self._add("History", "Ancient African")
        self.assertEqual(
            sorted(
                self.character.sage_studies.filter(study="History").values_list(
                    "concentration", flat=True
                )
            ),
            ["Ancient African", "Ancient European"],
        )

    def test_repeating_an_area_is_idempotent(self):
        self._add("Outer Planes", "Nirvana")
        self._add("Outer Planes", "Nirvana")
        self.assertEqual(self.character.sage_studies.count(), 1)

    def test_surrounding_whitespace_is_trimmed(self):
        self._add("History", "  Ancient European  ")
        row = SageStudyPoints.objects.get(character=self.character, study="History")
        self.assertEqual(row.concentration, "Ancient European")

    def test_the_study_taken_whole_is_still_addable(self):
        self._add("History", "Ancient European")
        self._add("History")
        self.assertEqual(
            sorted(
                self.character.sage_studies.filter(study="History").values_list(
                    "concentration", flat=True
                )
            ),
            ["", "Ancient European"],
        )

    def test_area_on_a_study_that_takes_none_returns_400(self):
        response = self._add("Forgery", "Seals")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(self.character.sage_studies.exists())

    def test_an_area_may_contain_parentheses(self):
        # Nothing reads the joined display name apart, so an area is free text.
        self._add("Outer Planes", "Nirvana (upper)")
        row = SageStudyPoints.objects.get(character=self.character)
        self.assertEqual(row.concentration, "Nirvana (upper)")
        self.assertEqual(row.display_name, "Outer Planes (Nirvana (upper))")

    def test_restoring_a_hidden_area_names_it_in_full(self):
        self._add("History", "Ancient European")
        row = SageStudyPoints.objects.get(character=self.character, study="History")
        row.points = 22
        row.hidden = True
        row.save()
        response = self._add("History", "Ancient European")
        self.assertIn(
            "Restored History (Ancient European) with 22 points",
            response.content.decode(),
        )
        row.refresh_from_db()
        self.assertFalse(row.hidden)
        self.assertEqual(row.points, 22)


class SageSectionRenderingTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="render_tester", password="pass")
        self.client = Client()
        self.client.login(username="render_tester", password="pass")
        self.character = Character.objects.create(
            user=self.user, name="Thorn", char_class="paladin"
        )

    def _sheet(self):
        return self.client.get(f"/character/{self.character.pk}/").content.decode()

    def test_chosen_field_heading_is_starred_and_its_box_ticked(self):
        SageChosenField.objects.create(
            character=self.character, field="Animal Training"
        )
        html = self._sheet()
        self.assertIn('<span class="chosen-mark" title="Chosen field">', html)
        self.assertIn('<input type="checkbox" name="chosen" checked>', html)

    def test_unchosen_field_heading_still_offers_its_box(self):
        """A field the character only has studies in gets a heading and an
        unticked box, which is how it gets chosen."""
        SageStudyPoints.objects.create(character=self.character, study="Piety")
        html = self._sheet()
        self.assertIn('<input type="hidden" name="field" value="Reverence">', html)
        self.assertNotIn('title="Chosen field"', html)

    def test_add_field_picker_only_offers_fields_with_no_heading(self):
        self.assertIn('<option value="Wilderland">', self._sheet())
        SageChosenField.objects.create(character=self.character, field="Wilderland")
        self.assertNotIn('<option value="Wilderland">', self._sheet())

    def test_chosen_field_with_no_studies_still_gets_a_heading(self):
        SageChosenField.objects.create(character=self.character, field="Wilderland")
        self.assertIn("No studies tracked in this field yet.", self._sheet())

    def test_shared_study_is_listed_under_every_field_holding_it(self):
        # Beasts reaches a paladin through Reverence (a class field) and through
        # Legends and Folklore (chosen from outside the class); one row, two
        # listings.
        SageChosenField.objects.create(
            character=self.character, field="Legends and Folklore"
        )
        SageStudyPoints.objects.create(character=self.character, study="Beasts")
        html = self._sheet()
        self.assertEqual(html.count(">Beasts</a>"), 2)

    def test_a_chosen_study_is_starred_in_both_of_its_fields(self):
        SageChosenField.objects.create(
            character=self.character, field="Legends and Folklore"
        )
        SageStudyPoints.objects.create(
            character=self.character, study="Beasts", chosen=True
        )
        html = self._sheet()
        self.assertEqual(html.count('title="Chosen study"'), 2)
        # One row behind both listings, so both boxes are ticked.
        self.assertEqual(
            html.count(
                '<input type="checkbox" name="chosen" aria-label="Chosen study" checked>'
            ),
            2,
        )

    def test_an_area_is_shown_after_its_study(self):
        SageStudyPoints.objects.create(
            character=self.character,
            study="Outer Planes",
            concentration="Nirvana",
            points=14,
        )
        self.assertIn(">Outer Planes (Nirvana)</a>", self._sheet())

    def test_an_area_links_to_its_study_page(self):
        # An area has no wiki page of its own, so the link drops it.
        SageStudyPoints.objects.create(
            character=self.character, study="Outer Planes", concentration="Nirvana"
        )
        html = self._sheet()
        self.assertIn("Outer_Planes_(sage_study)", html)
        self.assertNotIn("Nirvana_(sage_study)", html)

    def test_areas_of_one_study_are_filed_under_its_field(self):
        # Both rows are Outer Planes, so both sit under Power — a paladin's
        # Reverence doesn't hold it, so it falls back to the study's own field.
        for area in ["Nirvana", "Elysium"]:
            SageStudyPoints.objects.create(
                character=self.character, study="Outer Planes", concentration=area
            )
        html = self._sheet()
        self.assertEqual(html.count(">Power</a>"), 1)
        self.assertEqual(html.count("Outer_Planes_(sage_study)"), 2)

    def test_the_add_study_picker_labels_studies_taken_by_area(self):
        html = self._sheet()
        self.assertIn(
            '<option value="History" data-concentration="region and era">', html
        )
        self.assertIn('<option value="Forgery" data-concentration="">', html)

    def test_the_area_input_starts_hidden(self):
        # The picker opens on Accompaniment, which takes no area, so there is
        # nothing to fill in until a study that does is chosen.
        tag = re.search(r"<input[^>]*data-concentration-input[^>]*>", self._sheet())
        self.assertIsNotNone(tag)
        self.assertIn("hidden", tag.group(0))

    def test_the_star_sits_after_the_study_name(self):
        SageStudyPoints.objects.create(
            character=self.character, study="Piety", chosen=True
        )
        self.assertIn(
            '>Piety</a> <span class="chosen-mark" title="Chosen study">',
            self._sheet(),
        )


class SageStudyTableLayoutTests(TestCase):
    """Each field gets its own studies table, so the widths must be pinned (#45)."""

    def setUp(self):
        self.user = User.objects.create_user(username="layout_tester", password="pass")
        self.client = Client()
        self.client.login(username="layout_tester", password="pass")
        self.character = Character.objects.create(user=self.user, name="Thorn")
        # Two studies belonging to different fields: two tables get rendered.
        SageStudyPoints.objects.create(
            character=self.character, study="Forgery", points=10
        )
        SageStudyPoints.objects.create(
            character=self.character, study="Fortification", points=4
        )

    def test_every_study_table_pins_its_column_widths(self):
        response = self.client.get(f"/character/{self.character.pk}/")
        html = response.content.decode()
        self.assertEqual(html.count('<table class="data-table fixed-cols">'), 2)
        for column in ["col-study", "col-points", "col-status", "col-chosen"]:
            self.assertEqual(html.count(f'class="{column}"'), 2)
