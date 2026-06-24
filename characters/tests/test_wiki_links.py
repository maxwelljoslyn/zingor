import pytest
import requests

from characters.wiki_links import linkify_field, linkify_spell, linkify_study

WIKI_BASE = "https://wiki.alexissmolensk.com/index.php"


def _wiki_reachable() -> bool:
    try:
        resp = requests.head(WIKI_BASE, timeout=5)
        return resp.status_code < 500
    except requests.RequestException:
        return False


def test_linkify_spell_url_format():
    assert linkify_spell("Fireball", 3) == f"{WIKI_BASE}/Fireball_(spell)"
    assert linkify_spell("Hairy", 0) == f"{WIKI_BASE}/Hairy_(cantrip)"


def test_linkify_study_url_format():
    assert (
        linkify_study("Animal Training") == f"{WIKI_BASE}/Animal_Training_(sage_study)"
    )


def test_linkify_field_url_format():
    assert (
        linkify_field("Animal Training") == f"{WIKI_BASE}/Animal_Training_(sage_field)"
    )


@pytest.mark.skipif(not _wiki_reachable(), reason="Wiki site unreachable")
class TestWikiLinksLive:
    def test_spell_fireball(self):
        url = linkify_spell("Fireball", 3)
        resp = requests.get(url, timeout=10)
        assert resp.status_code == 200

    def test_field_animal_training(self):
        url = linkify_field("Animal Training")
        resp = requests.get(url, timeout=10)
        assert resp.status_code == 200

    def test_study_alchemy(self):
        url = linkify_study("Alchemy")
        resp = requests.get(url, timeout=10)
        assert resp.status_code == 200
