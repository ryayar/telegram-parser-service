"""Tests for userbot/matcher.py — pattern matching and deduplication."""
from __future__ import annotations

from shared.models import Pattern, PatternType
from userbot.matcher import (
    normalize_text,
    compute_text_hash,
    match_exact,
    match_smart,
    check_pattern,
    find_matching_patterns,
)


class TestNormalization:
    def test_lowercase(self):
        assert normalize_text("HELLO World") == "hello world"

    def test_collapse_whitespace(self):
        assert normalize_text("hello   world") == "hello world"

    def test_strip(self):
        assert normalize_text("  hello  ") == "hello"

    def test_unicode_normalization(self):
        # NFKC normalization
        assert normalize_text("\uff28ello") == "hello"


class TestTextHash:
    def test_same_text_same_hash(self):
        h1 = compute_text_hash("Продам iPhone 15")
        h2 = compute_text_hash("Продам iPhone 15")
        assert h1 == h2

    def test_different_case_same_hash(self):
        h1 = compute_text_hash("Продам iPhone")
        h2 = compute_text_hash("продам iphone")
        assert h1 == h2

    def test_extra_spaces_same_hash(self):
        h1 = compute_text_hash("Продам  iPhone")
        h2 = compute_text_hash("Продам iPhone")
        assert h1 == h2

    def test_different_text_different_hash(self):
        h1 = compute_text_hash("Продам iPhone")
        h2 = compute_text_hash("Продам MacBook")
        assert h1 != h2


class TestMatchExact:
    def test_simple_match(self):
        assert match_exact("Продам iPhone 15 Pro", "iphone") is True

    def test_case_insensitive(self):
        assert match_exact("IPHONE", "iphone") is True

    def test_no_match(self):
        assert match_exact("Продам MacBook", "iphone") is False

    def test_substring(self):
        assert match_exact("Продам iPhone15Pro", "iphone") is True

    def test_phrase_match(self):
        assert match_exact("Продам iPhone 15 Pro 256gb", "iphone 15") is True


class TestMatchSmart:
    def test_direct_match(self):
        assert match_smart("Продам iPhone 15", "iphone") is True

    def test_leet_speak(self):
        assert match_smart("Продам 1ph0ne 15", "iphone") is True

    def test_cyrillic_substitution(self):
        # 'о' cyrillic in 'iрhоne'
        assert match_smart("Продам i\u0440h\u043ene", "iphone") is True

    def test_with_separators(self):
        assert match_smart("Продам i-phone 15", "iphone") is True
        assert match_smart("Продам i phone 15", "iphone") is True
        assert match_smart("Продам i.phone 15", "iphone") is True

    def test_no_match(self):
        assert match_smart("Продам MacBook Air", "iphone") is False

    def test_fuzzy_match_long_pattern(self):
        # Fuzzy should work for longer patterns
        assert match_smart("iPhone 15 Pro Max 256gb titanium", "iphone 15 pro") is True

    def test_mixed_obfuscation(self):
        # 1Ph0ne with separator
        assert match_smart("Продам 1-Ph0ne 15", "iphone") is True


class TestCheckPattern:
    def test_exact_pattern(self):
        p = Pattern(id=1, user_id=1, pattern_type=PatternType.EXACT, value="iphone")
        assert check_pattern("Продам iPhone 15", p) is True

    def test_smart_pattern(self):
        p = Pattern(id=1, user_id=1, pattern_type=PatternType.SMART, value="iphone")
        assert check_pattern("Продам 1ph0ne 15", p) is True


class TestFindMatchingPatterns:
    def test_finds_matching(self):
        patterns = [
            Pattern(id=1, user_id=1, pattern_type=PatternType.EXACT, value="iphone"),
            Pattern(id=2, user_id=1, pattern_type=PatternType.EXACT, value="macbook"),
            Pattern(id=3, user_id=1, pattern_type=PatternType.SMART, value="airpods"),
        ]
        matched = find_matching_patterns("Продам iPhone 15 Pro", patterns)
        assert len(matched) == 1
        assert matched[0].value == "iphone"

    def test_multiple_matches(self):
        patterns = [
            Pattern(id=1, user_id=1, pattern_type=PatternType.EXACT, value="iphone"),
            Pattern(id=2, user_id=1, pattern_type=PatternType.EXACT, value="15 pro"),
        ]
        matched = find_matching_patterns("Продам iPhone 15 Pro", patterns)
        assert len(matched) == 2

    def test_no_matches(self):
        patterns = [
            Pattern(id=1, user_id=1, pattern_type=PatternType.EXACT, value="macbook"),
        ]
        matched = find_matching_patterns("Продам iPhone 15", patterns)
        assert len(matched) == 0
