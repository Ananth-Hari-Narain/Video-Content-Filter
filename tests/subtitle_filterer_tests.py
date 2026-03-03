import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import content_filter.video.subtitle_filtering as subtitle_filtering
from content_filter.video.subtitle_filtering import SubtitleFilterer, Trie, find_profanity_span_per_word


class DummyReader:
    def __init__(self):
        self.result = []
        self.calls = []

    def readtext(self, image):
        self.calls.append(image)
        return self.result


def build_filterer(monkeypatch, profanity_set):
    reader = DummyReader()

    def _factory(_languages):
        return reader

    monkeypatch.setattr(subtitle_filtering.easyocr, "Reader", _factory)
    return SubtitleFilterer(profanity_set=profanity_set), reader


class TestSubtitleFilterer:
    def test_build_profanity_trie_single_word(self, monkeypatch):
        filterer, _ = build_filterer(monkeypatch, {"apple"})
        trie = Trie({"apple"})

        assert isinstance(trie, Trie)
        assert trie.root["a"]["p"]["p"]["l"]["e"][Trie.END] is True

    def test_build_profanity_trie_multiple_words(self, monkeypatch: pytest.MonkeyPatch):
        # monkeypatch is a pytest fixture (type: pytest.MonkeyPatch) used here
        # to replace easyocr.Reader with DummyReader during this unit test.
        words = {"apple", "appler", "chocolate", "xchoco"}
        filterer, _ = build_filterer(monkeypatch, words)
        trie = Trie(words=words)
        expected_trie = {
            "a": {
                "p": {
                    "p": {
                        "l": {
                            "e": {
                                Trie.END: True,
                                "r": {Trie.END: True},
                            }
                        }
                    }
                }
            },
            "c": {
                "h": {
                    "o": {
                        "c": {
                            "o": {
                                "l": {
                                    "a": {
                                        "t": {
                                            "e": {Trie.END: True}
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            },
            "x": {
                "c": {
                    "h": {
                        "o": {
                            "c": {
                                "o": {Trie.END: True}
                            }
                        }
                    }
                }
            },
        }
        assert trie.root == expected_trie

    def test_normalize_text_with_map_remove_punctuation(self, monkeypatch):
        filterer, _ = build_filterer(monkeypatch, set())
        result, _ = filterer._normalize_text_with_map("hello!")
        assert result == "hello"

    def test_normalize_text_with_map_lower_case(self, monkeypatch):
        filterer, _ = build_filterer(monkeypatch, set())
        result, _ = filterer._normalize_text_with_map("Hell0")
        assert result == "hell"

    def test_normalize_text_with_map_remove_spaces_and_punctuation(self, monkeypatch):
        filterer, _ = build_filterer(monkeypatch, set())
        result, _ = filterer._normalize_text_with_map("Stup*d pers0n")
        assert result == "stup*dpersn"

    def test_find_profanity_spans_multiple_examples(self, monkeypatch):
        profanity_set = {"apple", "bread", "toast", "table"}
        filterer, _ = build_filterer(monkeypatch, profanity_set)
        trie = Trie(profanity_set)

        test_cases = [
            ("I love apple pie", [(7, 12)]),
            ("bread and butter", [(0, 5)]),
            ("toast table near", [(0, 5), (6, 11)]),
            ("The quick brown fox", []),
        ]

        for text, expected_spans in test_cases:
            spans = filterer._find_profanity_spans(text, trie)
            assert spans == expected_spans


def test_find_profanity_span_per_word_required_behavior():
    profanity_set = {"hot", "hello", "apple", "appler", "bad-word"}
    text_words = [
        "xxapplerxx",
        "h*t!",
        "h*llo??",
        "xxbadwordyy",
        "clean",
        "h*t!",
    ]

    spans = find_profanity_span_per_word(profanity_set, text_words)

    assert spans == [
        (2, 8),
        (0, 3),
        (0, 5),
        (2, 9),
        None,
        (0, 3),
    ]
