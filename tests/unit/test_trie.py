import pytest
from util.trie import Trie


def test_insert_and_search():
    t = Trie()
    t.insert("hello", "id1")
    assert t.search("hello") == ["id1"]


def test_search_missing():
    t = Trie()
    assert t.search("nope") is None


def test_insert_multiple_terminators():
    t = Trie()
    t.insert("song", "id1")
    t.insert("song", "id2")
    assert t.search("song") == ["id1", "id2"]


def test_starts_with_match():
    t = Trie()
    t.insert("bohemian rhapsody", "id1")
    t.insert("bohemian like you", "id2")
    results = t.starts_with("bohem")
    assert results is not None
    assert "bohemian rhapsody" in results
    assert "bohemian like you" in results


def test_starts_with_no_match():
    t = Trie()
    t.insert("hello", "id1")
    assert t.starts_with("xyz") is None


def test_list_keys_empty():
    t = Trie()
    assert t.list_keys(t.root) == []


def test_list_keys_all():
    t = Trie()
    t.insert("abc", "id1")
    t.insert("def", "id2")
    keys = t.list_keys(t.root)
    assert set(keys) == {"abc", "def"}
