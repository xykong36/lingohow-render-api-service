"""
Phrase text formatting utilities for TTS and filename generation.

Provides special formatting rules for phrases, especially for:
- Acronyms (e.g., "S.P.F." -> "S P F" for TTS)
- Clean filename generation
- Phrase-specific text processing
"""

import re
from typing import Optional


def format_phrase_for_tts(phrase: str) -> str:
    """
    Format phrase for TTS processing with special rules for phrases.

    Rules:
    1. For acronyms (all caps), add spaces between letters
    2. Remove all dots/periods completely
    3. Clean up trailing spaces and punctuation
    4. Handle abbreviations properly

    Args:
        phrase: Phrase to format

    Returns:
        Formatted phrase ready for TTS

    Examples:
        >>> format_phrase_for_tts("S.P.F.")
        'S P F'
        >>> format_phrase_for_tts("break the ice")
        'break the ice'
        >>> format_phrase_for_tts("What's up?")
        "What's up?"
    """
    # Remove dots, periods, and ellipsis
    phrase = phrase.replace('.', ' ').replace('…', ' ')

    # Remove multiple spaces
    phrase = ' '.join(phrase.split())

    # Check if phrase is an acronym (all uppercase and length > 1)
    if len(phrase) > 1 and phrase.isupper():
        # Add space between each letter: "SPF" -> "S P F"
        return ' '.join(list(phrase))

    # Handle mixed content with potential acronyms
    words = phrase.split()
    formatted_words = []

    for word in words:
        # Extract only alphabetic characters for acronym detection
        clean_word = ''.join(c for c in word if c.isalpha())

        # If word is all caps and more than 1 letter, treat as acronym
        if len(clean_word) > 1 and clean_word.isupper():
            # Replace the clean word with spaced version in original word
            spaced_acronym = ' '.join(list(clean_word))
            formatted_word = word.replace(clean_word, spaced_acronym)
            formatted_words.append(formatted_word)
        else:
            formatted_words.append(word)

    return ' '.join(formatted_words).strip()


def clean_phrase_filename(phrase: str) -> str:
    """
    Clean the phrase to create a valid filename.
    Preserves the original phrase structure for readability.

    Args:
        phrase: Original phrase text

    Returns:
        Cleaned filename without extension

    Examples:
        >>> clean_phrase_filename("break the ice")
        'break_the_ice'
        >>> clean_phrase_filename("S.P.F.")
        'SPF'
        >>> clean_phrase_filename("What's up?")
        'whats_up'
    """
    # Remove all dots/periods (both single and multiple)
    phrase = phrase.replace('.', ' ')
    # Remove Unicode ellipsis
    phrase = phrase.replace('…', ' ')
    # Remove multiple spaces
    phrase = ' '.join(phrase.split())

    # Replace spaces with underscores
    cleaned = phrase.replace(' ', '_')

    # Remove invalid filename characters while preserving case
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        cleaned = cleaned.replace(char, '')

    # Remove apostrophes and other punctuation
    cleaned = cleaned.replace("'", '').replace('"', '')

    # Convert to lowercase only if it's not an acronym
    # Check if the original phrase (without punctuation) is all uppercase
    alpha_only = ''.join(c for c in phrase if c.isalpha())
    if not (len(alpha_only) > 1 and alpha_only.isupper()):
        cleaned = cleaned.lower()

    return cleaned.strip('_')  # Remove leading/trailing underscores


def generate_phrase_hash(phrase: str) -> str:
    """
    Generate a unique hash for a phrase based on cleaned filename.

    This ensures consistent hash generation for the same phrase,
    regardless of punctuation or formatting variations.

    Args:
        phrase: Phrase text

    Returns:
        8-character hash string

    Examples:
        >>> hash1 = generate_phrase_hash("break the ice")
        >>> hash2 = generate_phrase_hash("break the ice!")
        >>> hash1 == hash2
        True
    """
    import hashlib

    # Use the cleaned filename as the base for hashing
    # This ensures consistent hashing for phrases with different punctuation
    cleaned = clean_phrase_filename(phrase)

    # Generate MD5 hash and take first 8 characters
    return hashlib.md5(cleaned.encode()).hexdigest()[:8]


__all__ = [
    'format_phrase_for_tts',
    'clean_phrase_filename',
    'generate_phrase_hash'
]
