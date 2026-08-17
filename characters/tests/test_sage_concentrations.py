"""Tests for sage concentrations: the named buckets a few studies split into.

Covers the catalogue's specs, the model, the sheet's views, the ZMF round trip,
and the grouping rule wiki_sync applies to a page that lists one study once per
bucket.
"""

from unittest import mock

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from characters import wiki_sync
from characters.microformats import parse_sheet
from characters.models import (
    Character,
    SageAbilityPoints,
    SageConcentration,
    SageStudyPoints,
)
from characters.sage import (
    Concentrations,
    canonical_concentration,
    concentration_choices,
    concentration_spec,
    sage_studies,
)
from characters.wiki_export import character_to_wiki


class ConcentrationCatalogueTests(TestCase):
    def test_an_ordinary_study_has_no_concentrations(self):
        self.assertIsNone(concentration_spec("Faith"))

    def test_history_buckets_are_period_by_sphere(self):
        choices = concentration_choices("History")
        self.assertEqual(len(choices), 12)
        self.assertIn("Ancient Asia", choices)
        self.assertIn("Modern New World", choices)

    def test_outer_planes_keeps_alternate_names_in_the_bucket_name(self):
        self.assertIn("Nine Hells (Baator)", concentration_choices("Outer Planes"))

    def test_geography_has_no_suggestions_because_loci_are_the_dms(self):
        self.assertFalse(concentration_spec("Geography").are_abilities)
        self.assertEqual(concentration_choices("Geography"), [])

    def test_athletics_buckets_are_standalone_abilities(self):
        self.assertTrue(concentration_spec("Athletics").are_abilities)
        self.assertIn("Swimming", concentration_choices("Athletics"))

    def test_spec_resolves_a_studys_spelling_variants(self):
        self.assertIsNotNone(concentration_spec("outer planes"))

    def test_every_spec_is_a_concentrations(self):
        for study, meta in sage_studies.items():
            spec = meta.get("concentrations")
            if spec is not None:
                with self.subTest(study=study):
                    self.assertIsInstance(spec, Concentrations)

    def test_heraldry_splits_by_mega_culture(self):
        self.assertEqual(
            concentration_choices("Heraldry, Signs & Sigils"),
            ["European", "Islamic", "Oriental", "Prehistoric"],
        )

    def test_beasts_and_artifacts_cost_ten_points_a_subject(self):
        for study in ("Beasts", "Artifacts"):
            with self.subTest(study=study):
                spec = concentration_spec(study)
                self.assertEqual(spec.block, 10)
                self.assertEqual(spec.choices, ())

    def test_law_and_policy_grants_one_and_allows_one(self):
        spec = concentration_spec("Law & Policy")
        self.assertTrue(spec.mirrored)
        self.assertEqual(spec.max_chosen, 1)
        self.assertIsNotNone(spec.granted_label)

    def test_politics_counts_the_character_at_half_elsewhere(self):
        spec = concentration_spec("Politics")
        self.assertTrue(spec.mirrored)
        self.assertEqual(spec.max_chosen, 1)
        self.assertEqual(spec.half_rate_label, "All other entities")


class ConcentrationsValidationTests(TestCase):
    """__post_init__ rejects specs describing a rule no study actually has."""

    def test_ability_buckets_cannot_be_priced(self):
        with self.assertRaises(ValueError):
            Concentrations(are_abilities=True, block=10)

    def test_ability_buckets_cannot_be_mirrored(self):
        with self.assertRaises(ValueError):
            Concentrations(are_abilities=True, mirrored=True)

    def test_a_mirrored_bucket_has_no_block_price(self):
        with self.assertRaises(ValueError):
            Concentrations(mirrored=True, block=10)

    def test_a_half_rate_row_needs_something_to_halve(self):
        with self.assertRaises(ValueError):
            Concentrations(half_rate_label="All other entities")

    def test_a_block_price_must_be_positive(self):
        with self.assertRaises(ValueError):
            Concentrations(block=0)

    def test_a_cap_must_be_positive(self):
        with self.assertRaises(ValueError):
            Concentrations(max_chosen=0)

    def test_a_closed_list_needs_names_in_it(self):
        with self.assertRaises(ValueError):
            Concentrations(closed=True)

    def test_the_plainest_spec_is_valid(self):
        self.assertEqual(Concentrations().choices, ())

    def test_a_spec_cannot_be_edited_in_passing(self):
        with self.assertRaises(Exception):
            Concentrations().block = 5


class ConcentrationsPointsRuleTests(TestCase):
    def test_an_allocated_bucket_keeps_the_pages_number(self):
        self.assertEqual(Concentrations().stored_points(22), 22)

    def test_a_block_bucket_costs_its_block_whatever_the_page_says(self):
        self.assertEqual(Concentrations(block=10).stored_points(3), 10)

    def test_a_mirrored_bucket_stores_nothing_of_its_own(self):
        self.assertEqual(Concentrations(mirrored=True).stored_points(30), 0)

    def test_a_mirrored_bucket_displays_the_studys_total(self):
        self.assertEqual(Concentrations(mirrored=True).display_points(0, 30), 30)

    def test_an_allocated_bucket_displays_what_it_stores(self):
        self.assertEqual(Concentrations().display_points(22, 37), 22)

    def test_allocated_buckets_add_up_to_the_studys_total(self):
        self.assertEqual(Concentrations().total_from_buckets([22, 15]), 37)

    def test_mirrored_buckets_each_carry_the_whole_total(self):
        self.assertEqual(Concentrations(mirrored=True).total_from_buckets([30, 30]), 30)

    def test_block_buckets_total_their_block_price(self):
        self.assertEqual(Concentrations(block=10).total_from_buckets([1, 1]), 20)

    def test_no_buckets_means_no_points(self):
        self.assertEqual(Concentrations().total_from_buckets([]), 0)

    def test_a_mirrored_page_repeating_the_total_is_agreeing(self):
        # What the export itself writes, so a round trip must stay silent.
        self.assertFalse(Concentrations(mirrored=True).page_disagrees(30, 30))

    def test_a_mirrored_page_with_some_other_number_disagrees(self):
        self.assertTrue(Concentrations(mirrored=True).page_disagrees(11, 22))

    def test_a_block_page_at_the_block_price_is_agreeing(self):
        self.assertFalse(Concentrations(block=10).page_disagrees(10, 25))

    def test_a_block_page_at_any_other_price_disagrees(self):
        self.assertTrue(Concentrations(block=10).page_disagrees(3, 25))

    def test_an_allocated_page_can_never_disagree(self):
        # The page's number simply is the bucket's points; there is no rule for
        # it to contradict.
        self.assertFalse(Concentrations().page_disagrees(22, 37))

    def test_a_listed_name_is_canonicalized(self):
        self.assertEqual(
            canonical_concentration("History", "ancient asia"), "Ancient Asia"
        )

    def test_an_unlisted_name_passes_through(self):
        # Geography's loci can only ever arrive as freetext.
        self.assertEqual(
            canonical_concentration("Geography", "The Vale of Erech"),
            "The Vale of Erech",
        )


class ClosedChoiceTests(TestCase):
    """Studies whose list the rules define completely take nothing off it."""

    def setUp(self):
        self.user = User.objects.create_user(username="maud", password="pw")
        self.character = Character.objects.create(user=self.user, name="Maud")
        self.history = SageStudyPoints.objects.create(
            character=self.character, study="History", points=37
        )
        self.client.login(username="maud", password="pw")

    def _add(self, study, name):
        return self.client.post(
            reverse(
                "characters:sage_concentration_add", args=[self.character.pk, study.pk]
            ),
            {"name": name},
        )

    def test_the_rules_close_history_heraldry_and_the_planes(self):
        for study in ("History", "Heraldry, Signs & Sigils", "Outer Planes"):
            with self.subTest(study=study):
                self.assertTrue(concentration_spec(study).closed)

    def test_the_dms_lists_stay_open(self):
        # Geography's loci are invented; the beast and artifact lists are long
        # and still growing, so Zingor never holds all of either.
        for study in ("Geography", "Beasts", "Artifacts", "Politics"):
            with self.subTest(study=study):
                self.assertFalse(concentration_spec(study).closed)

    def test_permits_only_names_on_a_closed_list(self):
        spec = concentration_spec("History")
        self.assertTrue(spec.permits("Ancient Asia"))
        self.assertFalse(spec.permits("Ancient Antarctica"))

    def test_permits_anything_on_an_open_list(self):
        self.assertTrue(concentration_spec("Geography").permits("The Vale of Erech"))

    def test_a_name_off_a_closed_list_is_refused(self):
        response = self._add(self.history, "Ancient Antarctica")
        self.assertEqual(response.status_code, 400)
        self.assertIn("not one of History's concentrations", response.content.decode())
        self.assertEqual(self.history.concentrations.count(), 0)

    def test_a_name_on_the_list_is_still_accepted_in_any_casing(self):
        self.assertEqual(self._add(self.history, "ancient asia").status_code, 200)
        self.assertEqual(self.history.concentrations.first().name, "Ancient Asia")

    def test_the_form_is_a_picker_not_a_text_box(self):
        html = self.client.get(
            reverse("characters:character_sheet", args=[self.character.pk])
        ).content.decode()
        self.assertIn('<select name="name"', html)

    def test_the_picker_drops_subjects_already_held(self):
        self._add(self.history, "Ancient Asia")
        response = self.client.get(
            reverse("characters:character_sheet", args=[self.character.pk])
        )
        addable = _entry_for(response, "History")["concentration_addable"]
        self.assertNotIn("Ancient Asia", addable)
        self.assertEqual(len(addable), 11)

    def test_the_add_row_goes_away_once_the_list_is_exhausted(self):
        for choice in concentration_choices("History"):
            self._add(self.history, choice)
        response = self.client.get(
            reverse("characters:character_sheet", args=[self.character.pk])
        )
        self.assertFalse(_entry_for(response, "History")["concentration_can_add"])

    def test_an_open_study_keeps_its_text_box(self):
        geography = SageStudyPoints.objects.create(
            character=self.character, study="Geography", points=10
        )
        response = self.client.get(
            reverse("characters:character_sheet", args=[self.character.pk])
        )
        self.assertFalse(_entry_for(response, "Geography")["concentration_closed"])
        self.assertEqual(self._add(geography, "The Vale of Erech").status_code, 200)


class SageConcentrationModelTests(TestCase):
    def setUp(self):
        user = User.objects.create_user(username="maud", password="pw")
        self.character = Character.objects.create(user=user, name="Maud")
        self.study = SageStudyPoints.objects.create(
            character=self.character, study="History", points=37
        )

    def test_concentrations_hang_off_their_study(self):
        SageConcentration.objects.create(
            study=self.study, name="Ancient Asia", points=22
        )
        self.assertEqual(self.study.concentrations.count(), 1)

    def test_duplicate_name_under_one_study_is_rejected(self):
        SageConcentration.objects.create(study=self.study, name="Ancient Asia")
        with self.assertRaises(Exception):
            SageConcentration.objects.create(study=self.study, name="Ancient Asia")

    def test_deleting_the_study_takes_its_concentrations(self):
        SageConcentration.objects.create(study=self.study, name="Ancient Asia")
        self.study.delete()
        self.assertEqual(SageConcentration.objects.count(), 0)


class ConcentrationSheetTests(TestCase):
    """The sub-rows, the unallocated line, and the add form on the sheet."""

    def setUp(self):
        self.user = User.objects.create_user(username="maud", password="pw")
        self.character = Character.objects.create(
            user=self.user, name="Maud", char_class="cleric"
        )
        self.history = SageStudyPoints.objects.create(
            character=self.character, study="History", points=37
        )
        self.client.login(username="maud", password="pw")

    def _sheet(self):
        return self.client.get(
            reverse("characters:character_sheet", args=[self.character.pk])
        ).content.decode()

    def test_buckets_are_listed_under_their_study(self):
        SageConcentration.objects.create(
            study=self.history, name="Ancient Asia", points=22
        )
        self.assertIn("Ancient Asia", self._sheet())

    def test_unallocated_is_the_studys_total_less_its_buckets(self):
        SageConcentration.objects.create(
            study=self.history, name="Ancient Asia", points=22
        )
        SageConcentration.objects.create(
            study=self.history, name="Medieval Asia", points=15
        )
        response = self.client.post(
            reverse(
                "characters:sage_study_points",
                args=[self.character.pk, self.history.pk],
            ),
            {"points": 37},
        )
        entry = self._study_entry(response)
        self.assertEqual(entry["allocated"], 37)
        self.assertEqual(entry["unallocated"], 0)

    def test_unallocated_is_shown_even_with_no_buckets_at_all(self):
        # A study holding points it has not committed anywhere is ordinary, and
        # the row is the only place the sheet can say so.
        html = self._sheet()
        self.assertIn("unallocated", html)

    def test_over_allocation_is_reported_rather_than_clamped(self):
        SageConcentration.objects.create(
            study=self.history, name="Ancient Asia", points=99
        )
        html = self._sheet()
        self.assertIn("over-allocated", html)

    def test_an_ordinary_study_gets_no_concentration_rows(self):
        SageStudyPoints.objects.create(
            character=self.character, study="Faith", points=20
        )
        response = self.client.get(
            reverse("characters:character_sheet", args=[self.character.pk])
        )
        entries = self._entries(response)
        self.assertFalse(entries["Faith"]["has_concentrations"])
        self.assertTrue(entries["History"]["has_concentrations"])

    def _entries(self, response):
        return {
            entry["name"]: entry
            for group in response.context["sage_studies_by_field"]
            for entry in group["entries"]
        }

    def _study_entry(self, response):
        return self._entries(response)["History"]


class ConcentrationViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="maud", password="pw")
        self.character = Character.objects.create(user=self.user, name="Maud")
        self.history = SageStudyPoints.objects.create(
            character=self.character, study="History", points=37
        )
        self.athletics = SageStudyPoints.objects.create(
            character=self.character, study="Athletics", points=20
        )
        self.client.login(username="maud", password="pw")

    def _add(self, study, name):
        return self.client.post(
            reverse(
                "characters:sage_concentration_add", args=[self.character.pk, study.pk]
            ),
            {"name": name},
        )

    def test_adding_a_bucket_creates_a_concentration_row(self):
        self._add(self.history, "Ancient Asia")
        self.assertEqual(self.history.concentrations.count(), 1)

    def test_a_typed_name_is_snapped_to_the_catalogues_spelling(self):
        self._add(self.history, "ancient asia")
        self.assertEqual(self.history.concentrations.first().name, "Ancient Asia")

    def test_a_name_off_the_list_is_kept_as_typed(self):
        geography = SageStudyPoints.objects.create(
            character=self.character, study="Geography", points=10
        )
        self._add(geography, "The Vale of Erech")
        self.assertEqual(geography.concentrations.first().name, "The Vale of Erech")

    def test_an_ability_studys_bucket_becomes_a_sage_ability(self):
        self._add(self.athletics, "Swimming")
        self.assertEqual(self.athletics.concentrations.count(), 0)
        ability = SageAbilityPoints.objects.get(
            character=self.character, ability="Swimming"
        )
        self.assertEqual(ability.study, "Athletics")

    def test_an_existing_loose_ability_is_adopted_by_the_study(self):
        SageAbilityPoints.objects.create(
            character=self.character, ability="Swimming", points=14
        )
        self._add(self.athletics, "Swimming")
        ability = SageAbilityPoints.objects.get(
            character=self.character, ability="Swimming"
        )
        self.assertEqual(ability.study, "Athletics")
        self.assertEqual(ability.points, 14)

    def test_a_study_with_no_concentrations_refuses_one(self):
        faith = SageStudyPoints.objects.create(
            character=self.character, study="Faith", points=10
        )
        self.assertEqual(self._add(faith, "Whatever").status_code, 400)

    def test_a_blank_name_returns_400(self):
        self.assertEqual(self._add(self.history, "   ").status_code, 400)

    def test_points_are_updated(self):
        concentration = SageConcentration.objects.create(
            study=self.history, name="Ancient Asia"
        )
        self.client.post(
            reverse(
                "characters:sage_concentration_points",
                args=[self.character.pk, concentration.pk],
            ),
            {"points": 22},
        )
        concentration.refresh_from_db()
        self.assertEqual(concentration.points, 22)

    def test_negative_points_return_400(self):
        concentration = SageConcentration.objects.create(
            study=self.history, name="Ancient Asia"
        )
        response = self.client.post(
            reverse(
                "characters:sage_concentration_points",
                args=[self.character.pk, concentration.pk],
            ),
            {"points": -1},
        )
        self.assertEqual(response.status_code, 400)

    def test_hiding_keeps_the_points(self):
        concentration = SageConcentration.objects.create(
            study=self.history, name="Ancient Asia", points=22
        )
        self.client.post(
            reverse(
                "characters:sage_concentration_hide",
                args=[self.character.pk, concentration.pk],
            )
        )
        concentration.refresh_from_db()
        self.assertTrue(concentration.hidden)
        self.assertEqual(concentration.points, 22)

    def test_re_adding_a_hidden_bucket_restores_its_points(self):
        concentration = SageConcentration.objects.create(
            study=self.history, name="Ancient Asia", points=22, hidden=True
        )
        self._add(self.history, "Ancient Asia")
        concentration.refresh_from_db()
        self.assertFalse(concentration.hidden)
        self.assertEqual(concentration.points, 22)

    def test_another_characters_concentration_is_not_reachable(self):
        other = Character.objects.create(
            user=User.objects.create_user(username="rachel", password="pw"),
            name="Rachel",
        )
        their_study = SageStudyPoints.objects.create(
            character=other, study="History", points=10
        )
        theirs = SageConcentration.objects.create(
            study=their_study, name="Ancient Asia"
        )
        response = self.client.post(
            reverse(
                "characters:sage_concentration_points",
                args=[self.character.pk, theirs.pk],
            ),
            {"points": 99},
        )
        self.assertEqual(response.status_code, 404)


class BlockPricedConcentrationTests(TestCase):
    """Beasts and Artifacts: one studied subject per ten points."""

    def setUp(self):
        self.user = User.objects.create_user(username="maud", password="pw")
        self.character = Character.objects.create(user=self.user, name="Maud")
        self.beasts = SageStudyPoints.objects.create(
            character=self.character, study="Beasts", points=25
        )
        self.client.login(username="maud", password="pw")

    def _add(self, name):
        return self.client.post(
            reverse(
                "characters:sage_concentration_add",
                args=[self.character.pk, self.beasts.pk],
            ),
            {"name": name},
        )

    def test_a_subject_costs_its_block_not_what_the_player_types(self):
        self._add("Chimera")
        self.assertEqual(self.beasts.concentrations.first().points, 10)

    def test_twenty_five_points_buys_two_subjects(self):
        self.assertEqual(self._add("Chimera").status_code, 200)
        self.assertEqual(self._add("Wyvern").status_code, 200)
        self.assertEqual(self.beasts.concentrations.count(), 2)

    def test_a_third_subject_is_refused_with_what_is_still_needed(self):
        self._add("Chimera")
        self._add("Wyvern")
        response = self._add("Roc")
        self.assertEqual(response.status_code, 400)
        self.assertIn("you need 5 more", response.content.decode())

    def test_the_leftover_shows_as_unallocated(self):
        self._add("Chimera")
        self._add("Wyvern")
        response = self.client.get(
            reverse("characters:character_sheet", args=[self.character.pk])
        )
        entry = _entry_for(response, "Beasts")
        self.assertEqual(entry["allocated"], 20)
        self.assertEqual(entry["unallocated"], 5)

    def test_re_adding_an_existing_subject_is_not_refused_at_the_cap(self):
        self._add("Chimera")
        self._add("Wyvern")
        self.assertEqual(self._add("Chimera").status_code, 200)

    def test_a_subject_has_no_editable_points_input(self):
        self._add("Chimera")
        response = self.client.get(
            reverse("characters:character_sheet", args=[self.character.pk])
        )
        self.assertTrue(
            _entry_for(response, "Beasts")["concentrations"][0]["fixed_points"]
        )


class MirroredConcentrationTests(TestCase):
    """Law & Policy and Politics: every bucket holds the study's whole total."""

    def setUp(self):
        self.user = User.objects.create_user(username="maud", password="pw")
        self.character = Character.objects.create(user=self.user, name="Maud")
        self.law = SageStudyPoints.objects.create(
            character=self.character, study="Law & Policy", points=30
        )
        self.politics = SageStudyPoints.objects.create(
            character=self.character, study="Politics", points=22
        )
        self.client.login(username="maud", password="pw")

    def _add(self, study, name, granted=False):
        data = {"name": name}
        if granted:
            data["granted"] = "1"
        return self.client.post(
            reverse(
                "characters:sage_concentration_add", args=[self.character.pk, study.pk]
            ),
            data,
        )

    def _entry(self, study_name):
        response = self.client.get(
            reverse("characters:character_sheet", args=[self.character.pk])
        )
        return _entry_for(response, study_name)

    def test_a_bucket_shows_the_studys_whole_total(self):
        self._add(self.law, "France")
        bucket = next(
            c
            for c in self._entry("Law & Policy")["concentrations"]
            if c["name"] == "France"
        )
        self.assertEqual(bucket["points"], 30)

    def test_a_mirrored_bucket_stores_no_points_of_its_own(self):
        self._add(self.law, "France")
        self.assertEqual(self.law.concentrations.get(name="France").points, 0)

    def test_there_is_no_unallocated_row(self):
        self._add(self.law, "France")
        entry = self._entry("Law & Policy")
        self.assertTrue(entry["concentration_mirrored"])
        self.assertIsNone(entry["unallocated"])

    def test_only_one_political_entity_may_be_chosen(self):
        self.assertEqual(self._add(self.politics, "France").status_code, 200)
        response = self._add(self.politics, "Aragon")
        self.assertEqual(response.status_code, 400)
        self.assertIn("only 1 chosen concentration", response.content.decode())

    def test_the_granted_slot_waits_to_be_named(self):
        placeholder = self._entry("Law & Policy")["concentrations"][0]
        self.assertTrue(placeholder["placeholder"])
        self.assertTrue(placeholder["granted"])
        self.assertIsNone(placeholder["pk"])

    def test_naming_the_granted_slot_creates_it(self):
        self._add(self.law, "Catholic canon law", granted=True)
        row = self.law.concentrations.get(name="Catholic canon law")
        self.assertTrue(row.granted)

    def test_the_granted_slot_does_not_use_up_the_players_one_choice(self):
        self._add(self.law, "Catholic canon law", granted=True)
        self.assertEqual(self._add(self.law, "France").status_code, 200)
        self.assertEqual(self.law.concentrations.count(), 2)

    def test_only_one_granted_slot_exists(self):
        self._add(self.law, "Catholic canon law", granted=True)
        response = self._add(self.law, "Something else", granted=True)
        self.assertEqual(response.status_code, 400)

    def test_politics_counts_the_character_at_half_everywhere_else(self):
        self._add(self.politics, "France")
        half = next(
            c for c in self._entry("Politics")["concentrations"] if c["derived"]
        )
        self.assertEqual(half["name"], "All other entities")
        self.assertEqual(half["points"], 11)

    def test_the_half_rate_row_is_not_a_row_of_its_own(self):
        self._add(self.politics, "France")
        self.assertEqual(self.politics.concentrations.count(), 1)

    def test_no_half_rate_row_before_an_entity_is_chosen(self):
        self.assertEqual(self._entry("Politics")["concentrations"], [])


def _entry_for(response, study_name):
    for group in response.context["sage_studies_by_field"]:
        for entry in group["entries"]:
            if entry["name"] == study_name:
                return entry
    raise AssertionError(f"{study_name} not on the sheet")


def _page(rows: str) -> str:
    return f"<html><body>{rows}</body></html>"


def _study_row(name: str, points: int) -> str:
    return "".join(
        [
            '<tr class="zingor-sage-study">',
            f'<td class="zingor-sage-study-name">{name}</td>',
            f'<td class="zingor-sage-study-points">{points}</td>',
            "</tr>",
        ]
    )


def _bucket_row(study: str, name: str, points: int | None = None) -> str:
    """One zingor-sage-concentration row, a sibling of its study's own row."""
    cell = "" if points is None else str(points)
    return "".join(
        [
            '<tr class="zingor-sage-concentration">',
            f'<td class="zingor-sage-concentration-study">{study}</td>',
            f'<td class="zingor-sage-concentration-name">{name}</td>',
            f'<td class="zingor-sage-concentration-points">{cell}</td>',
            "</tr>",
        ]
    )


class ConcentrationParsingTests(TestCase):
    def test_a_concentration_is_its_own_record(self):
        sheet = parse_sheet(_page(_bucket_row("History", "Ancient Asia", 22)))
        self.assertEqual(len(sheet.sage_studies), 0)
        record = sheet.concentrations[0]
        self.assertEqual(record.study_name, "History")
        self.assertEqual(record.name, "Ancient Asia")
        self.assertEqual(record.page_points, 22)

    def test_a_record_without_a_study_is_skipped(self):
        # Nothing can be done with a bucket that names no study: unlike nesting,
        # a flat record has no parent to fall back on.
        sheet = parse_sheet(
            _page(
                '<tr class="zingor-sage-concentration">'
                + '<td class="zingor-sage-concentration-name">Ancient Asia</td></tr>'
            )
        )
        self.assertEqual(sheet.concentrations, [])
        self.assertTrue(any("study" in w for w in sheet.warnings))

    def test_an_omitted_points_cell_is_none_not_zero(self):
        # A block-priced subject writes no number, and the sync has to tell that
        # apart from a page that really did say zero.
        record = parse_sheet(_page(_bucket_row("Beasts", "Chimera"))).concentrations[0]
        self.assertIsNone(record.page_points)

    def test_a_study_record_no_longer_carries_a_concentration(self):
        sheet = parse_sheet(_page(_study_row("History", 37)))
        self.assertEqual(sheet.sage_studies[0].points, 37)
        self.assertFalse(hasattr(sheet.sage_studies[0], "concentration"))

    def test_an_ability_record_names_the_study_it_comes_from(self):
        html = _page(
            "".join(
                [
                    '<tr class="zingor-sage-ability">',
                    '<td class="zingor-sage-ability-name">Swimming</td>',
                    '<td class="zingor-sage-ability-points">14</td>',
                    '<td class="zingor-sage-ability-from-study">Athletics</td>',
                    "</tr>",
                ]
            )
        )
        self.assertEqual(parse_sheet(html).sage_abilities[0].study, "Athletics")


class ConcentrationSyncTests(TestCase):
    """The grouping rule: one study, listed once per bucket."""

    def setUp(self):
        self.user = User.objects.create_user(username="maud", password="pw")
        self.character = Character.objects.create(
            user=self.user, name="Maud", wiki_url="https://example.test/Maud"
        )

    def _sync(self, html):
        with mock.patch.object(wiki_sync, "fetch_page", return_value=html):
            return wiki_sync.sync_character_from_wiki(self.character)

    def _history(self):
        return self.character.sage_studies.get(study="History")

    def test_the_study_carries_its_total_and_the_buckets_their_share(self):
        self._sync(
            _page(
                _study_row("History", 37)
                + _bucket_row("History", "Ancient Asia", 22)
                + _bucket_row("History", "Medieval Asia", 15)
            )
        )
        history = self._history()
        self.assertEqual(history.points, 37)
        self.assertEqual(
            {(c.name, c.points) for c in history.concentrations.all()},
            {("Ancient Asia", 22), ("Medieval Asia", 15)},
        )

    def test_a_studys_total_may_exceed_the_sum_of_its_buckets(self):
        # Rachel's example on the wiki: 37 points with only 30 committed leaves
        # 7 the character has yet to aim anywhere.
        self._sync(
            _page(
                _study_row("History", 37) + _bucket_row("History", "Ancient Asia", 30)
            )
        )
        self.assertEqual(self._history().points, 37)

    def test_buckets_for_an_unlisted_study_still_make_the_study(self):
        warnings = self._sync(
            _page(
                _bucket_row("History", "Ancient Asia", 22)
                + _bucket_row("History", "Medieval Asia", 15)
            )
        )
        self.assertEqual(self._history().points, 37)
        self.assertTrue(any("not listed" in w for w in warnings))

    def test_bucket_names_are_canonicalized(self):
        self._sync(
            _page(
                _study_row("History", 22) + _bucket_row("History", "ancient asia", 22)
            )
        )
        self.assertEqual(self._history().concentrations.first().name, "Ancient Asia")

    def test_a_buckets_study_name_is_canonicalized_too(self):
        self._sync(
            _page(
                _study_row("History", 22) + _bucket_row("history", "Ancient Asia", 22)
            )
        )
        self.assertEqual(self._history().concentrations.count(), 1)

    def test_the_study_row_survives_a_resync_so_its_buckets_do(self):
        html = _page(
            _study_row("History", 37) + _bucket_row("History", "Ancient Asia", 22)
        )
        self._sync(html)
        pk = self._history().pk
        self._sync(html)
        self.assertEqual(self._history().pk, pk)
        self.assertEqual(self._history().concentrations.count(), 1)

    def test_a_bucket_the_page_drops_is_removed(self):
        self._sync(
            _page(
                _study_row("History", 37)
                + _bucket_row("History", "Ancient Asia", 22)
                + _bucket_row("History", "Medieval Asia", 15)
            )
        )
        self._sync(
            _page(
                _study_row("History", 37) + _bucket_row("History", "Ancient Asia", 22)
            )
        )
        self.assertEqual(
            list(self._history().concentrations.values_list("name", flat=True)),
            ["Ancient Asia"],
        )

    def test_a_hidden_bucket_is_not_resurrected(self):
        self._sync(
            _page(
                _study_row("History", 22) + _bucket_row("History", "Ancient Asia", 22)
            )
        )
        concentration = self._history().concentrations.get(name="Ancient Asia")
        concentration.hidden = True
        concentration.points = 22
        concentration.save()
        self._sync(
            _page(
                _study_row("History", 99) + _bucket_row("History", "Ancient Asia", 99)
            )
        )
        concentration.refresh_from_db()
        self.assertTrue(concentration.hidden)
        self.assertEqual(concentration.points, 22)

    def test_a_page_with_no_study_table_does_not_wipe_the_studies(self):
        # The mirror image of the test below: a page carrying only
        # concentrations says nothing about which studies the character has, and
        # must not be read as saying they have none.
        self._sync(_page(_study_row("History", 37) + _study_row("Faith", 12)))
        self._sync(_page(_bucket_row("History", "Ancient Asia", 22)))
        self.assertEqual(self.character.sage_studies.count(), 2)

    def test_a_concentration_only_page_keeps_the_studys_own_points(self):
        # 22 is where the points went inside History, not what History is worth.
        self._sync(_page(_study_row("History", 37)))
        self._sync(_page(_bucket_row("History", "Ancient Asia", 22)))
        self.assertEqual(self._history().points, 37)
        self.assertEqual(self._history().concentrations.count(), 1)

    def test_a_study_table_that_omits_a_concentrated_study_warns(self):
        # Here the page does have a study table and left History out of it while
        # still naming History on a concentration, which is a contradiction
        # worth reporting. The study survives on the points Zingor already held.
        self._sync(_page(_study_row("History", 37)))
        warnings = self._sync(
            _page(_study_row("Faith", 12) + _bucket_row("History", "Ancient Asia", 22))
        )
        self.assertEqual(self._history().points, 37)
        self.assertTrue(any("existing points were kept" in w for w in warnings))

    def test_a_page_with_no_concentration_markup_leaves_them_alone(self):
        # Concentrations are their own ZMF section, so a page that carries a
        # study table and no concentration table is saying nothing about them.
        # Wiping them here would destroy the player's allocations the first time
        # they reorganised their page.
        self._sync(
            _page(
                _study_row("History", 37) + _bucket_row("History", "Ancient Asia", 22)
            )
        )
        self._sync(_page(_study_row("History", 37)))
        self.assertEqual(self._history().concentrations.count(), 1)

    def test_a_page_that_drops_one_bucket_still_drops_it(self):
        # The section being present is what makes it authoritative; this is the
        # case the test above must not break.
        self._sync(
            _page(
                _study_row("History", 37)
                + _bucket_row("History", "Ancient Asia", 22)
                + _bucket_row("History", "Medieval Asia", 15)
            )
        )
        self._sync(
            _page(_study_row("History", 37) + _bucket_row("Geography", "The Vale", 5))
        )
        self.assertEqual(self._history().concentrations.count(), 0)

    def test_granted_is_local_state_a_sync_leaves_alone(self):
        # Like `hidden`: the page says nothing about it, so a sync must not
        # clear what the player set on the sheet.
        law = _page(
            _study_row("Law & Policy", 30)
            + _bucket_row("Law & Policy", "Catholic canon law", 30)
        )
        self._sync(law)
        row = self.character.sage_studies.get(study="Law & Policy")
        row.concentrations.filter(name="Catholic canon law").update(granted=True)
        self._sync(law)
        self.assertTrue(row.concentrations.get(name="Catholic canon law").granted)

    def test_a_study_the_page_drops_is_removed(self):
        self._sync(_page(_study_row("History", 10) + _study_row("Faith", 5)))
        self._sync(_page(_study_row("History", 10)))
        self.assertEqual(
            list(self.character.sage_studies.values_list("study", flat=True)),
            ["History"],
        )

    def test_a_hidden_study_is_still_not_resurrected(self):
        self._sync(_page(_study_row("History", 10)))
        history = self._history()
        history.hidden = True
        history.save()
        self._sync(_page(_study_row("History", 99)))
        history.refresh_from_db()
        self.assertTrue(history.hidden)
        self.assertEqual(history.points, 10)

    def test_a_bucket_under_a_study_that_has_none_is_warned_about(self):
        warnings = self._sync(
            _page(_study_row("Faith", 12) + _bucket_row("Faith", "Somewhere", 5))
        )
        self.assertTrue(any("no concentrations" in w for w in warnings))
        self.assertEqual(self.character.sage_studies.get(study="Faith").points, 12)
        self.assertEqual(SageConcentration.objects.count(), 0)

    def test_a_bucket_off_a_closed_list_is_ignored_with_a_warning(self):
        warnings = self._sync(
            _page(
                _study_row("History", 37)
                + _bucket_row("History", "Ancient Antarctica", 22)
            )
        )
        self.assertEqual(self._history().concentrations.count(), 0)
        self.assertTrue(any("not one of" in w for w in warnings))

    def test_a_bucket_on_a_closed_list_syncs_normally(self):
        self._sync(
            _page(
                _study_row("History", 37) + _bucket_row("History", "Ancient Asia", 22)
            )
        )
        self.assertEqual(self._history().concentrations.count(), 1)

    def test_an_athletics_bucket_belongs_in_an_ability_record(self):
        warnings = self._sync(
            _page(
                _study_row("Athletics", 20) + _bucket_row("Athletics", "Swimming", 14)
            )
        )
        self.assertTrue(any("zingor-sage-ability" in w for w in warnings))
        self.assertEqual(SageConcentration.objects.count(), 0)

    def test_a_study_listed_twice_keeps_the_first_listings_points(self):
        warnings = self._sync(
            _page(_study_row("History", 37) + _study_row("History", 5))
        )
        self.assertEqual(self._history().points, 37)
        self.assertTrue(any("listed twice" in w for w in warnings))

    def test_a_bucket_listed_twice_keeps_the_first_listing(self):
        warnings = self._sync(
            _page(
                _study_row("History", 37)
                + _bucket_row("History", "Ancient Asia", 22)
                + _bucket_row("History", "Ancient Asia", 5)
            )
        )
        self.assertEqual(
            self._history().concentrations.get(name="Ancient Asia").points, 22
        )
        self.assertTrue(any("listed twice" in w for w in warnings))

    def test_a_block_bucket_costs_its_block_however_the_page_writes_it(self):
        self._sync(_page(_study_row("Beasts", 25) + _bucket_row("Beasts", "Chimera")))
        beasts = self.character.sage_studies.get(study="Beasts")
        self.assertEqual(beasts.points, 25)
        self.assertEqual(beasts.concentrations.get(name="Chimera").points, 10)

    def test_a_block_bucket_with_a_contradicting_number_warns(self):
        warnings = self._sync(
            _page(_study_row("Beasts", 25) + _bucket_row("Beasts", "Chimera", 3))
        )
        beasts = self.character.sage_studies.get(study="Beasts")
        self.assertEqual(beasts.concentrations.get(name="Chimera").points, 10)
        self.assertTrue(any("one subject per 10 points" in w for w in warnings))

    def test_a_block_bucket_that_agrees_with_the_rule_is_silent(self):
        warnings = self._sync(
            _page(_study_row("Beasts", 25) + _bucket_row("Beasts", "Chimera", 10))
        )
        self.assertFalse(any("per 10 points" in w for w in warnings))

    def test_a_mirrored_bucket_stores_no_points(self):
        self._sync(
            _page(_study_row("Politics", 22) + _bucket_row("Politics", "France", 22))
        )
        politics = self.character.sage_studies.get(study="Politics")
        self.assertEqual(politics.points, 22)
        self.assertEqual(politics.concentrations.get(name="France").points, 0)

    def test_a_mirrored_bucket_with_a_number_of_its_own_warns(self):
        warnings = self._sync(
            _page(_study_row("Politics", 22) + _bucket_row("Politics", "France", 11))
        )
        self.assertTrue(any("whole total" in w for w in warnings))

    def test_a_mirrored_studys_total_is_the_largest_bucket_not_their_sum(self):
        # Each mirrored bucket carries the whole total, so two of them at 30
        # describe a 30-point study, not a 60-point one.
        self._sync(
            _page(
                _bucket_row("Law & Policy", "Catholic canon law", 30)
                + _bucket_row("Law & Policy", "France", 30)
            )
        )
        self.assertEqual(
            self.character.sage_studies.get(study="Law & Policy").points, 30
        )

    def test_an_abilitys_study_is_stored(self):
        html = _page(
            "".join(
                [
                    '<tr class="zingor-sage-ability">',
                    '<td class="zingor-sage-ability-name">Swimming</td>',
                    '<td class="zingor-sage-ability-points">14</td>',
                    '<td class="zingor-sage-ability-from-study">athletics</td>',
                    "</tr>",
                ]
            )
        )
        self._sync(html)
        ability = self.character.sage_abilities.get(ability="Swimming")
        self.assertEqual(ability.study, "Athletics")


class ConcentrationExportTests(TestCase):
    """An exported page must parse back to the same buckets."""

    def setUp(self):
        user = User.objects.create_user(username="maud", password="pw")
        self.character = Character.objects.create(
            user=user, name="Maud", char_class="cleric"
        )
        self.history = SageStudyPoints.objects.create(
            character=self.character, study="History", points=37
        )
        SageConcentration.objects.create(
            study=self.history, name="Ancient Asia", points=22
        )
        SageConcentration.objects.create(
            study=self.history, name="Medieval Asia", points=15
        )

    def test_buckets_get_their_own_table_of_their_own_records(self):
        markup = character_to_wiki(self.character)
        self.assertIn("=== Concentrations ===", markup)
        self.assertIn('|- class="zingor-sage-concentration"', markup)
        self.assertIn("Ancient Asia", markup)

    def test_every_bucket_row_names_its_study_visibly(self):
        # A flat record carries its own study name; nothing is hidden in a span
        # for the parser's benefit. See adr/0001-zmf-stays-flat.md.
        markup = character_to_wiki(self.character)
        self.assertIn('class="zingor-sage-concentration-study" | History', markup)
        self.assertNotIn("display:none", markup.split("=== Concentrations ===")[1])

    def test_the_study_row_still_carries_the_overall_total(self):
        markup = character_to_wiki(self.character)
        self.assertIn('class="zingor-sage-study-points" | 37', markup)

    def test_a_hidden_bucket_is_not_exported(self):
        self.history.concentrations.filter(name="Ancient Asia").update(hidden=True)
        self.assertNotIn("Ancient Asia", character_to_wiki(self.character))

    def test_no_concentrations_table_when_no_study_has_one(self):
        self.history.concentrations.all().delete()
        self.assertNotIn("=== Concentrations ===", character_to_wiki(self.character))

    def test_a_block_priced_subject_is_exported_without_a_number(self):
        # Ten points a subject is the catalogue's rule, not a fact about this
        # character, so the page states no figure that could drift out of step.
        beasts = SageStudyPoints.objects.create(
            character=self.character, study="Beasts", points=25
        )
        SageConcentration.objects.create(study=beasts, name="Chimera", points=10)
        row = next(
            line
            for line in character_to_wiki(self.character).splitlines()
            if "Chimera" in line
        )
        self.assertTrue(row.rstrip().endswith("|"), row)

    def test_a_mirrored_subject_is_exported_at_the_studys_total(self):
        politics = SageStudyPoints.objects.create(
            character=self.character, study="Politics", points=22
        )
        SageConcentration.objects.create(study=politics, name="France", points=0)
        row = next(
            line
            for line in character_to_wiki(self.character).splitlines()
            if "France" in line
        )
        self.assertIn("22", row)

    def test_an_abilitys_study_is_exported(self):
        SageAbilityPoints.objects.create(
            character=self.character, ability="Swimming", points=14, study="Athletics"
        )
        markup = character_to_wiki(self.character)
        self.assertIn("zingor-sage-ability-from-study", markup)
