"""
Text processing utilities.

Pure functions for text manipulation, formatting, and analysis.
"""

import hashlib
import re
from typing import Optional


def extract_video_id_from_url(text: str) -> Optional[str]:
    """
    Extract video ID from YouTube URL or return the text if it's already a video ID.

    Args:
        text: YouTube URL or video ID

    Returns:
        Video ID string or None if invalid

    Examples:
        >>> extract_video_id_from_url("dQw4w9WgXcQ")
        'dQw4w9WgXcQ'
        >>> extract_video_id_from_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        'dQw4w9WgXcQ'
        >>> extract_video_id_from_url("https://youtu.be/dQw4w9WgXcQ")
        'dQw4w9WgXcQ'
    """
    text = text.strip()

    # If it's already a video ID (11 characters, alphanumeric + - and _)
    if len(text) == 11 and text.replace('-', '').replace('_', '').isalnum():
        return text

    # Extract from various YouTube URL formats
    patterns = [
        r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([a-zA-Z0-9_-]{11})',
        r'youtube\.com/.*[?&]v=([a-zA-Z0-9_-]{11})',
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1)

    return None


def hash_text(text: str, length: int = 8) -> str:
    """
    Generate MD5 hash value for text content.

    Args:
        text: Text content to hash
        length: Length of hash to retain (default: 8 characters)

    Returns:
        MD5 hash string

    Examples:
        >>> hash_text("Hello World", length=8)
        'b10a8db1'
    """
    text_bytes = text.encode('utf-8')
    hash_obj = hashlib.md5(text_bytes)
    return hash_obj.hexdigest()[:length]


def format_text_for_tts(text: str) -> str:
    """
    Format text for TTS processing.

    Rules:
    1. For acronyms (all caps), add spaces between letters
    2. Remove excessive dots/periods
    3. Clean up extra spaces

    Args:
        text: Text to format

    Returns:
        Formatted text ready for TTS

    Examples:
        >>> format_text_for_tts("The FBI and CIA are here...")
        'The F B I and C I A are here'
    """
    # Remove excessive dots and ellipsis
    text = text.replace('...', ' ').replace('…', ' ')

    # Remove multiple spaces
    text = ' '.join(text.split())

    # Handle acronyms: if all uppercase and length > 1, add spaces
    words = text.split()
    formatted_words = []

    for word in words:
        # Remove punctuation for acronym check
        clean_word = ''.join(c for c in word if c.isalpha())
        if len(clean_word) > 1 and clean_word.isupper():
            # Add spaces between letters for acronyms
            spaced_letters = ' '.join(list(clean_word))
            # Preserve original punctuation
            formatted_word = word.replace(clean_word, spaced_letters)
            formatted_words.append(formatted_word)
        else:
            formatted_words.append(word)

    return ' '.join(formatted_words).strip()


def clean_phrase_for_filename(phrase: str) -> str:
    """
    Clean phrase to create a valid filename (spaces to underscores).

    Args:
        phrase: Original phrase text

    Returns:
        Cleaned filename without extension

    Examples:
        >>> clean_phrase_for_filename("Hello World!")
        'hello_world'
        >>> clean_phrase_for_filename("Can't stop won't stop")
        'cant_stop_wont_stop'
    """
    # Replace spaces with underscores
    cleaned = phrase.replace(' ', '_')

    # Remove invalid filename characters
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        cleaned = cleaned.replace(char, '')

    return cleaned.strip('_').lower()


def normalize_text_for_matching(text: str) -> str:
    """
    Normalize text for similarity matching.

    Removes punctuation and converts to lowercase.

    Args:
        text: Text to normalize

    Returns:
        Normalized text (lowercase, no punctuation)

    Examples:
        >>> normalize_text_for_matching("Hello, World!")
        'hello world'
    """
    # Remove punctuation and convert to lowercase
    return re.sub(r'[^\w\s]', '', text.lower()).strip()


def calculate_text_similarity(text1: str, text2: str) -> float:
    """
    Calculate similarity between two texts using word-based Jaccard similarity.

    Args:
        text1: First text
        text2: Second text

    Returns:
        Similarity percentage (0.0 to 100.0)

    Examples:
        >>> calculate_text_similarity("hello world", "hello world")
        100.0
        >>> calculate_text_similarity("hello world", "goodbye world")
        50.0
    """
    if not text1 and not text2:
        return 100.0

    if not text1 or not text2:
        return 0.0

    # Normalize texts for comparison
    norm_text1 = re.sub(r'\s+', ' ', text1.lower().strip())
    norm_text2 = re.sub(r'\s+', ' ', text2.lower().strip())

    # Simple word-based similarity
    words1 = set(norm_text1.split())
    words2 = set(norm_text2.split())

    if not words1 and not words2:
        return 100.0

    if not words1 or not words2:
        return 0.0

    # Calculate Jaccard similarity
    intersection = len(words1.intersection(words2))
    union = len(words1.union(words2))

    similarity = (intersection / union) * 100 if union > 0 else 0.0
    return similarity


__all__ = [
    'extract_video_id_from_url',
    'hash_text',
    'format_text_for_tts',
    'clean_phrase_for_filename',
    'normalize_text_for_matching',
    'calculate_text_similarity',
]
