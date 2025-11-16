"""
Custom types, exceptions, and constants for transcript processing.

Provides:
- Custom exceptions
- JSON encoders for MongoDB types
- Feature availability flags
"""

import json
from typing import Any

# Check optional dependencies
try:
    from bson import ObjectId
    BSON_AVAILABLE = True
except ImportError:
    BSON_AVAILABLE = False
    ObjectId = None  # type: ignore

try:
    from dotenv import load_dotenv
    load_dotenv()
    DOTENV_AVAILABLE = True
except ImportError:
    DOTENV_AVAILABLE = False

try:
    from translation_api import DeepseekClient, TranslationAPIError, create_deepseek_client
    TRANSLATION_API_AVAILABLE = True
except ImportError:
    TRANSLATION_API_AVAILABLE = False

try:
    from youtube_transcript_api import YouTubeTranscriptApi
    from youtube_transcript_api._errors import (
        TranscriptsDisabled,
        NoTranscriptFound,
        VideoUnavailable
    )
    from youtube_transcript_api.formatters import WebVTTFormatter, JSONFormatter
    TRANSCRIPT_API_AVAILABLE = True
except ImportError:
    TRANSCRIPT_API_AVAILABLE = False

try:
    import spacy
    SPACY_AVAILABLE = True
    # Try to load the English model
    try:
        spacy.load("en_core_web_sm")
        SPACY_MODEL_AVAILABLE = True
    except OSError:
        SPACY_MODEL_AVAILABLE = False
except ImportError:
    SPACY_AVAILABLE = False
    SPACY_MODEL_AVAILABLE = False


class TranscriptProcessingError(Exception):
    """Custom exception for transcript processing errors."""
    pass


class MongoJSONEncoder(json.JSONEncoder):
    """Custom JSON encoder to handle MongoDB ObjectId."""

    def default(self, obj: Any) -> Any:
        if BSON_AVAILABLE and ObjectId and isinstance(obj, ObjectId):
            return str(obj)
        return super().default(obj)


__all__ = [
    'TranscriptProcessingError',
    'MongoJSONEncoder',
    'BSON_AVAILABLE',
    'DOTENV_AVAILABLE',
    'TRANSLATION_API_AVAILABLE',
    'TRANSCRIPT_API_AVAILABLE',
    'SPACY_AVAILABLE',
    'SPACY_MODEL_AVAILABLE',
]
