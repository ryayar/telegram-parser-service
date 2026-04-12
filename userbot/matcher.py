"""Pattern matching and deduplication logic.

Provides functions to:
- Normalize text for hashing
- Compute text hash (MD5)
- Check exact keyword match (case-insensitive)
- Check smart pattern match (transliteration, character substitution, fuzzy)
"""
from __future__ import annotations

import hashlib
import re
import unicodedata

from rapidfuzz import fuzz

from shared.models import Pattern, PatternType


# ─── Character Substitution Maps ─────────────────────────────────────

# Common leet-speak / obfuscation + Cyrillic→Latin substitutions
CHAR_SUBSTITUTIONS = {
    # Leet-speak
    "0": "o", "1": "i", "3": "e", "4": "a", "5": "s",
    "7": "t", "8": "b", "@": "a", "$": "s",
    # Cyrillic → Latin lookalikes
    "\u0430": "a", "\u0435": "e", "\u043e": "o", "\u0440": "p",
    "\u0441": "c", "\u0445": "x", "\u0443": "y", "\u043a": "k",
    "\u043c": "m", "\u0442": "t", "\u043d": "h", "\u0432": "b",
    "\u0438": "i", "\u043b": "l", "\u0434": "d", "\u0433": "g",
}


# ─── Text Normalization ──────────────────────────────────────────────


def normalize_text(text: str) -> str:
    """Normalize text for hashing: lowercase, collapse whitespace, strip."""
    text = text.lower()
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def compute_text_hash(text: str) -> str:
    """Compute MD5 hash of normalized text."""
    normalized = normalize_text(text)
    return hashlib.md5(normalized.encode("utf-8")).hexdigest()


# ─── Pattern Matching ────────────────────────────────────────────────


def _transliterate(text: str) -> str:
    """Replace lookalike characters with their Latin base form."""
    result = []
    for ch in text.lower():
        result.append(CHAR_SUBSTITUTIONS.get(ch, ch))
    return "".join(result)


def _remove_separators(text: str) -> str:
    """Remove common separators between characters."""
    return re.sub(r"[\s\-_.]+", "", text)


def match_exact(text: str, pattern_value: str) -> bool:
    """Case-insensitive whole-word match."""
    pattern = re.escape(pattern_value)
    return bool(re.search(r"\b" + pattern + r"\b", text, re.IGNORECASE))


def match_smart(text: str, pattern_value: str) -> bool:
    """Smart matching: transliteration, separator removal, fuzzy.

    Strategies in order:
    1. Direct case-insensitive match
    2. Transliterated match (latin/cyrillic/leet substitutions)
    3. Match with separators removed
    4. Fuzzy token match (for longer patterns, threshold 85%)
    """
    text_lower = text.lower()
    pattern_lower = pattern_value.lower()

    def _word_match(t: str, p: str) -> bool:
        return bool(re.search(r"\b" + re.escape(p) + r"\b", t, re.IGNORECASE))

    # 1. Direct match
    if _word_match(text_lower, pattern_lower):
        return True

    # 2. Transliterated match
    text_trans = _transliterate(text_lower)
    pattern_trans = _transliterate(pattern_lower)
    if _word_match(text_trans, pattern_trans):
        return True

    # 3. Match with separators removed — only if the pattern itself contains separators
    # (e.g. "i-phone" → "iphone"). Skipped for plain words to avoid cross-word false positives
    # where end of one word + start of next accidentally form the pattern after space removal.
    if any(c in pattern_value for c in " -_."):
        text_no_sep = _remove_separators(text_trans)
        pattern_no_sep = _remove_separators(pattern_trans)
        if pattern_no_sep in text_no_sep:
            return True

    # 4. Fuzzy match for patterns with 2+ words or longer strings
    if " " in pattern_value or len(pattern_value) >= 5:
        ratio = fuzz.token_set_ratio(text_trans, pattern_trans)
        if ratio >= 85:
            return True

    return False


def check_pattern(text: str, pattern: Pattern) -> bool:
    """Check if text matches a pattern based on its type."""
    if pattern.pattern_type == PatternType.EXACT:
        return match_exact(text, pattern.value)
    elif pattern.pattern_type == PatternType.SMART:
        return match_smart(text, pattern.value)
    return False


def find_matching_patterns(text: str, patterns: list[Pattern]) -> list[Pattern]:
    """Return all patterns that match the given text."""
    return [p for p in patterns if check_pattern(text, p)]
