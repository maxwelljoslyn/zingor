"""Tests for the DM-only treasure splitter pages."""

from django.contrib.auth.models import User
from django.test import TestCase

from characters.models import Character

# Two lumps and two trinkets: the only even division puts one lump on each side.
HOARD = "gem: 4000\ncrown: 4000\nlamp: 100\nring: 100\n"


class TreasureBase(TestCase):
    """A DM, a player, and two equally-experienced characters to divide among."""

    def setUp(self):
        self.dm = User.objects.create_user(
            username="dm", password="pass1234!", is_staff=True
        )
        self.player = User.objects.create_user(username="player", password="pass1234!")
        # Equal XP so an even hoard divides evenly; FEL is derived from it.
        self.alix = Character.objects.create(user=self.player, name="Alix", xp=4000)
        self.bront = Character.objects.create(user=self.player, name="Bront", xp=4000)

    def split(self, **overrides):
        """Post one division, defaulting to both characters on a single share."""
        data = {
            "hoard": HOARD,
            "recipient": [str(self.alix.pk), str(self.bront.pk)],
            f"shares-{self.alix.pk}": "1",
            f"shares-{self.bront.pk}": "1",
        }
        data.update(overrides)
        return self.client.post("/treasure/split/", data)

    def move(self, item, to, division=None, **overrides):
        """Post a division back with one item dragged onto somebody else.

        `division` is the state the page is showing, as item name -> (XP, holder);
        it defaults to an even one so a move is visibly what unbalances it.
        """
        if division is None:
            division = {
                "gem": (4000, self.alix),
                "lamp": (100, self.alix),
                "crown": (4000, self.bront),
                "ring": (100, self.bront),
            }
        drawn = list(dict.fromkeys(char for _, char in division.values()))
        data = {
            "recipient": [str(char.pk) for char in drawn],
            "item-name": list(division),
            "item-xp": [str(xp) for xp, _ in division.values()],
            "item-holder": [str(char.pk) for _, char in division.values()],
            "move-item": item,
            "move-to": str(to.pk) if hasattr(to, "pk") else str(to),
        }
        for char in drawn:
            data[f"shares-{char.pk}"] = "1"
        data.update(overrides)
        return self.client.post("/treasure/move/", data)

    def holders(self, response):
        return {str(char): char for char in response.context["share_holders"]}

    def rows(self, response):
        return {str(row["character"]): row for row in response.context["rows"]}

    def held(self, response):
        """Who holds what, as item name -> holder name."""
        return {
            item["name"]: str(row["character"])
            for row in response.context["rows"]
            for item in row["items"]
        }


class TreasureAccessTests(TreasureBase):
    def test_pages_require_login(self):
        response = self.client.get("/treasure/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response["Location"])

    def test_pages_are_staff_only(self):
        self.client.login(username="player", password="pass1234!")
        self.assertEqual(self.client.get("/treasure/").status_code, 403)
        self.assertEqual(self.split().status_code, 403)

    def test_nav_link_shows_only_for_staff(self):
        self.client.login(username="player", password="pass1234!")
        self.assertNotContains(self.client.get("/"), 'href="/treasure/"')
        self.client.login(username="dm", password="pass1234!")
        self.assertContains(self.client.get("/"), 'href="/treasure/"')

    def test_the_split_route_is_post_only(self):
        self.client.login(username="dm", password="pass1234!")
        self.assertEqual(self.client.get("/treasure/split/").status_code, 405)


class TreasureFormTests(TreasureBase):
    def setUp(self):
        super().setUp()
        self.client.login(username="dm", password="pass1234!")

    def test_shares_default_to_each_character_s_fel(self):
        response = self.client.get("/treasure/")
        self.assertEqual(response.status_code, 200)
        alix = self.holders(response)["Alix"]
        self.assertEqual(alix.drawn, alix.fel)
        self.assertContains(
            response, f'name="shares-{self.alix.pk}" value="{alix.fel}"'
        )

    def test_inactive_characters_are_not_offered(self):
        self.bront.is_active = False
        self.bront.save()
        self.assertEqual(list(self.holders(self.client.get("/treasure/"))), ["Alix"])

    def test_hirelings_are_offered_but_start_unchecked(self):
        hireling = Character.objects.create(
            user=self.player, name="Cwen", kind="hireling", xp=1000
        )
        response = self.client.get("/treasure/")
        holders = self.holders(response)
        self.assertFalse(holders["Cwen"].in_party)
        self.assertTrue(holders["Alix"].in_party)
        self.assertContains(response, f'value="{hireling.pk}"')

    def test_a_character_with_no_xp_defaults_to_one_share(self):
        newcomer = Character.objects.create(user=self.player, name="Dai")
        response = self.client.get("/treasure/")
        self.assertIsNone(self.holders(response)["Dai"].fel)
        self.assertContains(response, f'name="shares-{newcomer.pk}" value="1"')


class TreasureSplitTests(TreasureBase):
    def setUp(self):
        super().setUp()
        self.client.login(username="dm", password="pass1234!")

    def test_equal_shares_divide_the_hoard_evenly(self):
        rows = self.rows(self.split())
        self.assertEqual(sorted(rows), ["Alix", "Bront"])
        self.assertEqual([row["xp"] for row in rows.values()], [4100, 4100])
        self.assertEqual(rows["Alix"]["vs_fair"], 0)

    def test_every_item_lands_in_exactly_one_share(self):
        rows = self.rows(self.split())
        dealt = [item["name"] for row in rows.values() for item in row["items"]]
        self.assertEqual(sorted(dealt), ["crown", "gem", "lamp", "ring"])

    def test_unchecked_characters_draw_nothing(self):
        rows = self.rows(self.split(recipient=[str(self.alix.pk)]))
        self.assertEqual(list(rows), ["Alix"])
        self.assertEqual(rows["Alix"]["xp"], 8200)

    def test_edited_shares_override_the_fel_default(self):
        """The party may divide on the FEL agreed before the fight, not today's."""
        response = self.split(**{f"shares-{self.alix.pk}": "3"})
        rows = self.rows(response)
        self.assertEqual(rows["Alix"]["shares"], 3)
        self.assertEqual(rows["Bront"]["shares"], 1)
        self.assertGreater(rows["Alix"]["xp"], rows["Bront"]["xp"])
        self.assertEqual(response.context["shares_drawn"], 4)

    def test_two_characters_with_one_name_both_draw(self):
        """Shares are keyed by pk, so a shared name can't collapse two recipients."""
        twin = Character.objects.create(user=self.player, name="Alix", xp=4000)
        response = self.split(
            recipient=[str(self.alix.pk), str(twin.pk)],
            **{f"shares-{twin.pk}": "1"},
        )
        self.assertEqual(len(response.context["rows"]), 2)

    def test_summary_reports_totals_and_spread(self):
        response = self.split()
        self.assertEqual(response.context["total_xp"], 8200)
        self.assertEqual(response.context["item_count"], 4)
        self.assertEqual(response.context["fair_share"], 4100)
        self.assertEqual(response.context["spread"], 0)

    def test_the_division_is_rendered_for_reading(self):
        response = self.split()
        self.assertContains(response, "Alix")
        self.assertContains(response, "gem")
        self.assertContains(response, "8,200 XP")

    def test_an_unreadable_hoard_is_reported_not_divided(self):
        response = self.split(hoard="gem: lots\n")
        self.assertNotIn("rows", response.context)
        self.assertIn("non-numeric", response.context["errors"][0])

    def test_an_empty_hoard_is_reported(self):
        errors = self.split(hoard="  ").context["errors"]
        self.assertIn("is empty", errors[0])

    def test_choosing_nobody_is_reported(self):
        errors = self.split(recipient=[]).context["errors"]
        self.assertTrue(any("at least one character" in error for error in errors))

    def test_a_non_numeric_share_count_is_reported(self):
        errors = self.split(**{f"shares-{self.alix.pk}": "two"}).context["errors"]
        self.assertIn("not a whole number", errors[0])
        self.assertIn("Alix", errors[0])

    def test_a_share_count_below_one_is_reported(self):
        errors = self.split(**{f"shares-{self.bront.pk}": "0"}).context["errors"]
        self.assertIn("at least 1", errors[0])

    def test_the_division_round_trips_every_item_through_the_form(self):
        """A move has only the rendered page to work from, so it must all be there."""
        response = self.split()
        for name in ["gem", "crown", "lamp", "ring"]:
            self.assertContains(response, f'name="item-name" value="{name}"')
        self.assertContains(response, 'name="item-holder"', count=4)
        self.assertContains(response, f'name="recipient" value="{self.alix.pk}"')
        self.assertContains(response, f'name="shares-{self.alix.pk}" value="1"')


class TreasureMoveTests(TreasureBase):
    def setUp(self):
        super().setUp()
        self.client.login(username="dm", password="pass1234!")

    def test_moving_an_item_changes_who_holds_it(self):
        held = self.held(self.move("gem", self.bront))
        self.assertEqual(held["gem"], "Bront")
        # Nothing else budges: a move is a move, not a re-division.
        self.assertEqual(held["lamp"], "Alix")
        self.assertEqual(held["crown"], "Bront")

    def test_the_totals_rework_themselves_around_the_move(self):
        rows = self.rows(self.move("gem", self.bront))
        self.assertEqual(rows["Alix"]["xp"], 100)
        self.assertEqual(rows["Bront"]["xp"], 8100)
        self.assertEqual(rows["Alix"]["vs_fair"], -4000)
        self.assertEqual(rows["Bront"]["vs_fair"], 4000)

    def test_the_spread_reworks_itself_around_the_move(self):
        self.assertEqual(self.split().context["spread"], 0)
        self.assertEqual(self.move("gem", self.bront).context["spread"], 8000)

    def test_the_hoard_total_is_unchanged_by_a_move(self):
        response = self.move("gem", self.bront)
        self.assertEqual(response.context["total_xp"], 8200)
        self.assertEqual(response.context["item_count"], 4)

    def test_a_moved_division_says_it_was_adjusted_by_hand(self):
        response = self.move("gem", self.bront)
        self.assertTrue(response.context["hand_edited"])
        self.assertContains(response, "adjusted by hand")
        # In a notice box rather than in the prose, since re-dividing discards it.
        self.assertContains(response, "flash flash--danger")

    def test_a_recipient_emptied_by_a_move_still_appears(self):
        """They keep a row, so an item can be dragged back onto them."""
        division = {"gem": (4000, self.alix), "crown": (4000, self.bront)}
        rows = self.rows(self.move("gem", self.bront, division=division))
        self.assertEqual(sorted(rows), ["Alix", "Bront"])
        self.assertEqual(rows["Alix"]["items"], [])
        self.assertEqual(rows["Alix"]["xp"], 0)

    def test_a_move_can_be_stacked_on_a_previous_move(self):
        """The page posts its current state, so moves accumulate."""
        after_one = {
            "gem": (4000, self.bront),
            "lamp": (100, self.alix),
            "crown": (4000, self.bront),
            "ring": (100, self.bront),
        }
        held = self.held(self.move("crown", self.alix, division=after_one))
        self.assertEqual(held["gem"], "Bront")
        self.assertEqual(held["crown"], "Alix")

    def test_uneven_shares_are_respected_by_a_move(self):
        response = self.move("gem", self.bront, **{f"shares-{self.alix.pk}": "3"})
        rows = self.rows(response)
        self.assertEqual(rows["Alix"]["shares"], 3)
        self.assertEqual(response.context["shares_drawn"], 4)
        # Alix holds only the 100 XP lamp against 3 of the 4 shares drawn.
        self.assertEqual(rows["Alix"]["per_share"], 33)

    def test_an_item_lands_in_value_order_in_its_new_take(self):
        rows = self.rows(self.move("gem", self.bront))
        names = [item["name"] for item in rows["Bront"]["items"]]
        self.assertEqual(names, ["crown", "gem", "ring"])

    def test_moving_to_a_non_recipient_is_rejected(self):
        outsider = Character.objects.create(user=self.player, name="Cwen", xp=4000)
        errors = self.move("gem", outsider).context["errors"]
        self.assertIn("not drawing a share", errors[0])

    def test_moving_an_unknown_item_is_rejected(self):
        errors = self.move("sceptre", self.bront).context["errors"]
        self.assertIn("not in this division", errors[0])

    def test_a_division_naming_an_unchosen_holder_is_rejected(self):
        """Stale markup must not be silently reinterpreted into a real division."""
        errors = self.move("gem", self.bront, **{"item-holder": ["999"] * 4}).context[
            "errors"
        ]
        self.assertIn("out of date", errors[0])

    def test_a_ragged_division_is_rejected(self):
        errors = self.move("gem", self.bront, **{"item-xp": ["4000"]}).context["errors"]
        self.assertIn("out of date", errors[0])

    def test_a_move_is_staff_only(self):
        self.client.login(username="player", password="pass1234!")
        self.assertEqual(self.move("gem", self.bront).status_code, 403)

    def test_the_move_route_is_post_only(self):
        self.assertEqual(self.client.get("/treasure/move/").status_code, 405)
