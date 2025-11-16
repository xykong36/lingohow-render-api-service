"""
Pydantic models for request and response validation.

Defines all data structures used in the Translation API endpoints.
"""

from typing import Optional, Any, Union
from pydantic import BaseModel, Field, field_validator


# ===== Shared Models =====

class HighlightEntry(BaseModel):
    """Model for a single highlight entry."""
    slug: str = Field(..., description="Kebab-case slug identifier")
    display_text: str = Field(..., description="Original word/phrase")
    translation_zh: str = Field(..., description="Chinese translation")


# ===== Use Case 1: Paragraph Translation + Highlights =====

class ParagraphTranslateRequest(BaseModel):
    """Request model for paragraph translation with highlights."""
    text: str = Field(..., description="English paragraph text to translate")
    extract_highlights: bool = Field(True, description="Whether to extract highlight entries")


class ParagraphTranslateResponse(BaseModel):
    """Response model for paragraph translation."""
    original_text: str = Field(..., description="Original English text")
    translation: str = Field(..., description="Chinese translation")
    highlights: list[HighlightEntry] = Field(default_factory=list, description="Extracted highlight entries")


# ===== Use Case 2: Paragraph to Sentences Generation =====

class ParagraphGenerateSentencesRequest(BaseModel):
    """Request model for generating sentences from paragraph."""
    text: str = Field(..., description="English paragraph text")
    episode_id: Optional[int] = Field(None, description="Episode ID for sentences")
    split_by: str = Field("period", description="Sentence splitting method: period | newline | auto")


class EnhancedSentence(BaseModel):
    """Model for an enhanced sentence with all metadata."""
    sentence_id: Optional[Union[str, int]] = None
    episode_id: Optional[int] = None
    episode_sequence: Optional[int] = None
    en: str
    zh: str
    phonetic_us: str
    highlight_entries: list[HighlightEntry] = Field(default_factory=list)
    start_ts: Optional[float] = None
    end_ts: Optional[float] = None
    duration: Optional[float] = None
    sentence_hash: Optional[str] = None

    @field_validator('sentence_id')
    @classmethod
    def convert_sentence_id_to_str(cls, v):
        """Convert sentence_id to string if it's an integer."""
        if v is not None and isinstance(v, int):
            return str(v)
        return v


class ParagraphGenerateSentencesResponse(BaseModel):
    """Response model for paragraph sentence generation."""
    sentences: list[EnhancedSentence]


# ===== Use Case 3: Single Sentence Enhancement =====

class SentenceEnhanceRequest(BaseModel):
    """Request model for single sentence enhancement."""
    en: str = Field(..., description="English sentence text")
    sentence_id: Optional[str] = Field(None, description="Sentence ID")
    episode_id: Optional[int] = Field(None, description="Episode ID")
    episode_sequence: Optional[int] = Field(None, description="Episode sequence number")
    start_ts: Optional[float] = Field(None, description="Start timestamp")
    end_ts: Optional[float] = Field(None, description="End timestamp")
    duration: Optional[float] = Field(None, description="Duration")
    sentence_hash: Optional[str] = Field(None, description="Sentence hash")


class SentenceEnhanceResponse(BaseModel):
    """Response model for single sentence enhancement."""
    sentence: EnhancedSentence


# ===== Use Case 4: Expression Generation =====

class ExpressionGenerateRequest(BaseModel):
    """Request model for expression generation from sentences."""
    sentences: list[dict[str, Any]] = Field(..., description="List of sentence dictionaries with 'en', 'zh', etc.")
    episode_id: int = Field(1, description="Episode ID for the expressions")
    max_input_tokens: int = Field(2500, description="Maximum input tokens per batch")
    max_workers: int = Field(4, description="Maximum parallel workers")


class ExpressionTranslations(BaseModel):
    """Translations for an expression meaning."""
    zh: str
    en: str


class ExpressionExample(BaseModel):
    """Example usage of an expression."""
    zh: str
    en: str


class ExpressionMeaning(BaseModel):
    """Meaning definition for an expression."""
    translations: ExpressionTranslations
    examples: list[ExpressionExample] = Field(default_factory=list)


class PhraseTranslation(BaseModel):
    """A phrase with translation."""
    phrase: str
    translation: str


class WordRelations(BaseModel):
    """Word relations for an expression."""
    synonyms: list[PhraseTranslation] = Field(default_factory=list)
    antonyms: list[PhraseTranslation] = Field(default_factory=list)
    similar: list[PhraseTranslation] = Field(default_factory=list)


class RelatedExpression(BaseModel):
    """Related expression model."""
    type: str
    phrase: str
    translation: str
    examples: list[ExpressionExample] = Field(default_factory=list)


class Analysis(BaseModel):
    """Analysis item for an expression."""
    type: str
    content: str


class MatchedSentence(BaseModel):
    """A sentence that matches an expression."""
    sentence_id: Optional[Union[str, int]] = None
    episode_id: Optional[int] = None
    episode_sequence: Optional[int] = None
    en: str
    zh: str
    phonetic_us: str
    start_ts: Optional[float] = None
    end_ts: Optional[float] = None
    duration: Optional[float] = None
    sentence_hash: Optional[str] = None
    highlight_entries: list[HighlightEntry] = Field(default_factory=list)
    matched_highlight: Optional[str] = None

    @field_validator('sentence_id')
    @classmethod
    def convert_sentence_id_to_str(cls, v):
        """Convert sentence_id to string if it's an integer."""
        if v is not None and isinstance(v, int):
            return str(v)
        return v


class Expression(BaseModel):
    """Complete expression data model."""
    expression_id: str
    phrase: str
    phonetic: str
    type: str
    meanings: list[ExpressionMeaning]
    wordRelations: WordRelations
    relatedExpressions: list[RelatedExpression] = Field(default_factory=list)
    analysis: list[Analysis] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    episodes: list[str]
    matched_sentences: list[MatchedSentence]
    slug: str
    forms: list[str]


class ExpressionGenerateResponse(BaseModel):
    """Response model for expression generation."""
    expressions: list[Expression]


# ===== Error Response Model =====

# ===== Use Case 5: Video Transcript Generation =====

class VideoTranscriptRequest(BaseModel):
    """Request model for video transcript generation."""
    video_id: Optional[str] = Field(None, description="YouTube video ID (11 characters)")
    video_url: Optional[str] = Field(None, description="Full YouTube video URL")

    def model_post_init(self, __context) -> None:
        """Validate that at least one of video_id or video_url is provided."""
        if not self.video_id and not self.video_url:
            raise ValueError("Either video_id or video_url must be provided")


class TranscriptSegment(BaseModel):
    """Model for a single transcript segment with timestamp."""
    text: str = Field(..., description="Transcript text for this segment")
    start: float = Field(..., description="Start time in seconds")
    duration: float = Field(..., description="Duration in seconds")


class VideoTranscriptMetadata(BaseModel):
    """Metadata for video transcript."""
    total_segments: int
    language: str
    language_code: str
    is_generated: bool
    character_count: int
    word_count: int
    total_duration_seconds: Optional[float] = None
    total_duration_formatted: Optional[str] = None
    fetch_timestamp: str
    api_version: str = "1.2.2"
    r2_object_key: Optional[str] = Field(None, description="R2 object storage key for the transcript file")


class VideoTranscriptResponse(BaseModel):
    """Response model for video transcript."""
    video_id: str = Field(..., description="YouTube video ID")
    title: str = Field(..., description="Video title")
    video_url: str = Field(..., description="YouTube video URL")
    transcript: list[TranscriptSegment] = Field(..., description="Timestamped transcript segments")
    full_transcript: str = Field(..., description="Complete transcript text without timestamps")
    metadata: VideoTranscriptMetadata = Field(..., description="Transcript metadata")
    r2_url: Optional[str] = Field(None, description="R2 public URL for the stored transcript JSON file")


# ===== Use Case 6: Sentence Audio Generation =====

class SentenceAudioGenerateRequest(BaseModel):
    """Request model for generating audio files for sentences."""
    sentences: list[str] = Field(..., description="List of sentence texts to generate audio for")
    voice: str = Field("en-US-AvaMultilingualNeural", description="Edge TTS voice model to use")
    max_workers: int = Field(4, description="Maximum parallel workers for audio generation")


class SentenceAudioResult(BaseModel):
    """Result for a single sentence audio generation and upload."""
    sentence_hash: str = Field(..., description="MD5 hash of the sentence text")
    en: str = Field(..., description="Original English sentence text")
    audio_generated: bool = Field(..., description="Whether audio file was generated successfully")
    uploaded_cos: bool = Field(False, description="Whether uploaded to COS successfully")
    uploaded_r2: bool = Field(False, description="Whether uploaded to R2 successfully")
    cos_object_key: Optional[str] = Field(None, description="COS object key")
    r2_object_key: Optional[str] = Field(None, description="R2 object key")
    error: Optional[str] = Field(None, description="Error message if any step failed")


class SentenceAudioGenerateResponse(BaseModel):
    """Response model for sentence audio generation."""
    results: list[SentenceAudioResult] = Field(..., description="Results for each sentence")
    statistics: dict[str, Any] = Field(..., description="Overall statistics")
    cos_upload_stats: dict[str, Any] = Field(..., description="COS upload statistics")
    r2_upload_stats: dict[str, Any] = Field(..., description="R2 upload statistics")


# ===== Use Case 7: Episode Management =====

class EpisodeReadResponse(BaseModel):
    """Response model for reading episode data."""
    episode_id: int = Field(..., description="Episode ID")
    sentences: list[EnhancedSentence] = Field(..., description="List of enhanced sentences")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Episode metadata")
    created_at: str = Field(..., description="ISO timestamp when episode was created")
    updated_at: str = Field(..., description="ISO timestamp when episode was last updated")
    version: int = Field(..., description="Episode version number")


class EpisodeUpdateRequest(BaseModel):
    """Request model for updating entire episode."""
    sentences: list[dict[str, Any]] = Field(..., description="Complete list of sentences")
    metadata: Optional[dict[str, Any]] = Field(None, description="Optional metadata")


class EpisodeUpdateResponse(BaseModel):
    """Response model for episode update."""
    episode_id: int
    sentence_count: int
    version: int
    updated_at: str


class SentenceUpdateRequest(BaseModel):
    """Request model for updating a single sentence."""
    sentence: dict[str, Any] = Field(..., description="Updated sentence data")


class SentenceUpdateResponse(BaseModel):
    """Response model for sentence update."""
    episode_id: int
    sentence_index: int
    version: int
    updated_at: str


class EpisodeListItem(BaseModel):
    """Model for episode list item."""
    episode_id: int
    file_name: str
    sentence_count: Optional[int] = None
    version: Optional[int] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    file_size_bytes: int
    error: Optional[str] = None


class EpisodeListResponse(BaseModel):
    """Response model for episode list."""
    episodes: list[EpisodeListItem]
    total_count: int


# ===== Error Response Model =====

class ErrorResponse(BaseModel):
    """Standard error response."""
    error: str = Field(..., description="Error message")
    detail: Optional[str] = Field(None, description="Additional error details")
