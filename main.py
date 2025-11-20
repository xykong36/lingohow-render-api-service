"""
FastAPI Translation API
Provides endpoints for text translation, sentence enhancement, and expression generation.
"""

import logging
import hashlib
import os
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Optional
from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from concurrent.futures import ThreadPoolExecutor
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# Load environment variables from .env.local if exists (local development)
# In production (Render), environment variables come from Render dashboard
env_file = Path(__file__).parent / ".env.local"
if env_file.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(env_file)
        print("✅ Loaded environment variables from .env.local")
    except ImportError:
        print("⚠️ python-dotenv not installed, using system environment variables only")
from models import (
    ParagraphGenerateSentencesRequest,
    ParagraphGenerateSentencesResponse,
    SentenceEnhanceRequest,
    SentenceEnhanceResponse,
    ExpressionGenerateRequest,
    ExpressionGenerateResponse,
    VideoTranscriptRequest,
    VideoTranscriptResponse,
    SentenceAudioGenerateRequest,
    SentenceAudioGenerateResponse,
    SentenceAudioResult,
    PhraseAudioGenerateRequest,
    PhraseAudioGenerateResponse,
    EnhancedSentence,
    HighlightEntry,
    MongoDBEpisodeResponse,
    ErrorResponse,
)
from services.deepseek_client import DeepseekClient, DeepseekAPIError
from services.translation_service import TranslationService
from services.phonetic_service import PhoneticService
from services.highlight_service import HighlightService
from services.expression_service import ExpressionService
from services.transcript_service import (
    TranscriptService,
    TranscriptServiceError,
    TranscriptNotAvailableError,
    InvalidVideoIdError
)
from services.episode_service import (
    EpisodeService,
    EpisodeServiceError
)
from services.mongodb_service import (
    MongoDBService,
    MongoDBServiceError,
    MongoDBConnectionError,
    EpisodeNotFoundInDBError
)
from utils.text_splitter import split_into_sentences

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize rate limiter
limiter = Limiter(key_func=get_remote_address)

# Global service instances
translation_service: Optional[TranslationService] = None
phonetic_service: Optional[PhoneticService] = None
highlight_service: Optional[HighlightService] = None
expression_service: Optional[ExpressionService] = None
transcript_service: Optional[TranscriptService] = None
episode_service: Optional[EpisodeService] = None
mongodb_service: Optional[MongoDBService] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown events."""
    global translation_service, phonetic_service, highlight_service, expression_service, transcript_service, episode_service, mongodb_service

    # Startup
    logger.info("Starting Translation API v1.0.0")
    try:
        # Get environment variables
        api_key = os.getenv("DEEPSEEK_API_KEY")
        base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")

        if not api_key:
            raise ValueError("DEEPSEEK_API_KEY environment variable not set")

        # Create Deepseek client
        deepseek_client = DeepseekClient(
            api_key=api_key,
            base_url=base_url
        )
        logger.info("✅ DeepseekClient initialized")

        # Initialize services
        translation_service = TranslationService(deepseek_client)
        phonetic_service = PhoneticService(deepseek_client)
        highlight_service = HighlightService(deepseek_client)
        expression_service = ExpressionService(deepseek_client)
        transcript_service = TranscriptService()
        episode_service = EpisodeService()

        # Initialize MongoDB service
        try:
            mongodb_service = MongoDBService()
            mongodb_service.connect()
            logger.info("✅ MongoDBService initialized")
        except MongoDBConnectionError as e:
            logger.warning(f"⚠️  MongoDB service initialization failed: {e}")
            mongodb_service = None

        logger.info("✅ All services initialized successfully")
    except Exception as e:
        logger.error(f"❌ Failed to initialize services: {e}")
        raise

    yield

    # Shutdown
    logger.info("Shutting down Translation API")
    if mongodb_service:
        mongodb_service.close()


# Initialize FastAPI app
app = FastAPI(
    title="Translation API",
    version="1.0.0",
    description="API for Chinese translation, phonetic transcription, and expression generation",
    lifespan=lifespan
)

# Add rate limiter to app state
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Configure CORS

# 生产环境里面用环境变量控制
# allowed_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")

# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=allowed_origins,
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,    # 注意：改为 False
    allow_methods=["*"],
    allow_headers=["*"],
)
# ===== Dependency Injection =====

def get_translation_service() -> TranslationService:
    """Get translation service instance."""
    if translation_service is None:
        raise HTTPException(status_code=503, detail="Translation service not initialized")
    return translation_service


def get_phonetic_service() -> PhoneticService:
    """Get phonetic service instance."""
    if phonetic_service is None:
        raise HTTPException(status_code=503, detail="Phonetic service not initialized")
    return phonetic_service


def get_highlight_service() -> HighlightService:
    """Get highlight service instance."""
    if highlight_service is None:
        raise HTTPException(status_code=503, detail="Highlight service not initialized")
    return highlight_service


def get_expression_service() -> ExpressionService:
    """Get expression service instance."""
    if expression_service is None:
        raise HTTPException(status_code=503, detail="Expression service not initialized")
    return expression_service


def get_transcript_service() -> TranscriptService:
    """Get transcript service instance."""
    if transcript_service is None:
        raise HTTPException(status_code=503, detail="Transcript service not initialized")
    return transcript_service


def get_episode_service() -> EpisodeService:
    """Get episode service instance."""
    if episode_service is None:
        raise HTTPException(status_code=503, detail="Episode service not initialized")
    return episode_service


def get_mongodb_service() -> MongoDBService:
    """Get MongoDB service instance."""
    if mongodb_service is None:
        raise HTTPException(status_code=503, detail="MongoDB service not initialized")
    return mongodb_service


# ===== Endpoints =====

@app.get("/")
async def root():
    """API information endpoint."""
    return {
        "name": "Translation API",
        "version": "1.0.0",
        "status": "running",
        "endpoints": {
            "paragraph_generate_sentences": "POST /api/paragraph/generate-sentences",
            "sentence_enhance": "POST /api/sentence/enhance",
            "sentence_audio_generate": "POST /api/sentence/generate-audio",
            "phrase_audio_generate": "POST /api/phrase/generate-audio",
            "expression_generate": "POST /api/expression/generate",
            "video_transcript": "POST /api/video/transcript",
            "episode_read_from_db": "GET /api/episode/db/{episode_id}",
        }
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "services": {
            "translation": "initialized" if translation_service else "not initialized",
            "phonetic": "initialized" if phonetic_service else "not initialized",
            "highlight": "initialized" if highlight_service else "not initialized",
            "expression": "initialized" if expression_service else "not initialized",
            "transcript": "initialized" if transcript_service else "not initialized",
            "episode": "initialized" if episode_service else "not initialized",
            "mongodb": "initialized" if mongodb_service else "not initialized",
        }
    }


@app.post(
    "/api/paragraph/generate-sentences",
    response_model=ParagraphGenerateSentencesResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}}
)
async def generate_sentences_from_paragraph(
    request: ParagraphGenerateSentencesRequest,
    trans_svc: TranslationService = Depends(get_translation_service),
    phonetic_svc: PhoneticService = Depends(get_phonetic_service),
    highlight_svc: HighlightService = Depends(get_highlight_service),
    episode_svc: EpisodeService = Depends(get_episode_service)
):
    """
    Use Case 2: Split paragraph into sentences and enhance each sentence.

    - Splits paragraph into individual sentences
    - For each sentence: generates translation, phonetic, and highlights
    - Processes in parallel for better performance
    """
    try:
        logger.info(f"Generating sentences from paragraph: {request.text[:50]}...")

        # Split paragraph into sentences
        sentences = split_into_sentences(request.text, request.split_by)
        logger.info(f"Split into {len(sentences)} sentences")

        if not sentences:
            return ParagraphGenerateSentencesResponse(sentences=[])

        # Process sentences in parallel
        def process_sentence(idx: int, sentence_text: str) -> EnhancedSentence:
            """Process a single sentence."""
            try:
                # Get translation
                zh = trans_svc.translate(sentence_text)

                # Get phonetic
                phonetic_us = phonetic_svc.get_phonetic(sentence_text)

                # Get highlights
                highlight_data = highlight_svc.extract_highlights(sentence_text, zh)
                highlights = [HighlightEntry(**h) for h in highlight_data]

                # Generate sentence hash
                sentence_hash = hashlib.md5(sentence_text.encode()).hexdigest()[:16]

                return EnhancedSentence(
                    sentence_id=None,
                    episode_id=request.episode_id,
                    episode_sequence=idx + 1,
                    en=sentence_text,
                    zh=zh,
                    phonetic_us=phonetic_us,
                    highlight_entries=highlights,
                    start_ts=None,
                    end_ts=None,
                    duration=None,
                    sentence_hash=sentence_hash
                )
            except Exception as e:
                logger.error(f"Failed to process sentence {idx + 1}: {e}")
                return EnhancedSentence(
                    episode_sequence=idx + 1,
                    en=sentence_text,
                    zh="",
                    phonetic_us="",
                    highlight_entries=[]
                )

        # Parallel processing
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [
                executor.submit(process_sentence, idx, sent)
                for idx, sent in enumerate(sentences)
            ]
            enhanced_sentences = [future.result() for future in futures]

        logger.info(f"✅ Generated {len(enhanced_sentences)} enhanced sentences")

        # Save to episode file if episode_id is provided
        if request.episode_id is not None:
            try:
                # Convert EnhancedSentence objects to dictionaries
                sentences_data = [s.model_dump() for s in enhanced_sentences]

                # Save to episode file
                save_result = episode_svc.save_episode(
                    episode_id=request.episode_id,
                    sentences=sentences_data,
                    metadata={
                        "source": "paragraph_generation",
                        "original_text": request.text[:100] + "..." if len(request.text) > 100 else request.text,
                        "split_by": request.split_by
                    }
                )
                logger.info(f"💾 Saved episode {request.episode_id} to {save_result['file_path']}")
            except Exception as e:
                # Don't fail the request if episode save fails, just log it
                logger.error(f"Failed to save episode {request.episode_id}: {e}")

        return ParagraphGenerateSentencesResponse(
            sentences=enhanced_sentences,
        )

    except Exception as e:
        logger.error(f"Sentence generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@app.post(
    "/api/sentence/enhance",
    response_model=SentenceEnhanceResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}}
)
async def enhance_sentence(
    request: SentenceEnhanceRequest,
    trans_svc: TranslationService = Depends(get_translation_service),
    phonetic_svc: PhoneticService = Depends(get_phonetic_service),
    highlight_svc: HighlightService = Depends(get_highlight_service)
):
    """
    Use Case 3: Enhance a single sentence with translation, phonetic, and highlights.

    - Translates sentence to Chinese
    - Generates US phonetic transcription
    - Extracts highlight entries
    """
    try:
        logger.info(f"Enhancing sentence: {request.en[:50]}...")

        # Get translation
        zh = trans_svc.translate(request.en)

        # Get phonetic
        phonetic_us = phonetic_svc.get_phonetic(request.en)

        # Get highlights
        highlight_data = highlight_svc.extract_highlights(request.en, zh)
        highlights = [HighlightEntry(**h) for h in highlight_data]

        # Generate sentence hash if not provided
        sentence_hash = request.sentence_hash
        if not sentence_hash:
            sentence_hash = hashlib.md5(request.en.encode()).hexdigest()[:16]

        # Calculate duration if not provided
        duration = request.duration
        if duration is None and request.start_ts is not None and request.end_ts is not None:
            duration = request.end_ts - request.start_ts

        enhanced = EnhancedSentence(
            sentence_id=request.sentence_id,
            episode_id=request.episode_id,
            episode_sequence=request.episode_sequence,
            en=request.en,
            zh=zh,
            phonetic_us=phonetic_us,
            highlight_entries=highlights,
            start_ts=request.start_ts,
            end_ts=request.end_ts,
            duration=duration,
            sentence_hash=sentence_hash
        )

        logger.info(f"✅ Sentence enhanced successfully")

        return SentenceEnhanceResponse(sentence=enhanced)

    except DeepseekAPIError as e:
        logger.error(f"Sentence enhancement failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@app.post(
    "/api/expression/generate",
    response_model=ExpressionGenerateResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}}
)
async def generate_expressions(
    request: ExpressionGenerateRequest,
    expr_svc: ExpressionService = Depends(get_expression_service)
):
    """
    Use Case 4: Generate expressions from a list of sentences.

    - Analyzes sentences to extract valuable expressions
    - Returns phrasal verbs, idioms, collocations, etc.
    - Includes meanings, examples, and word relations
    """
    try:
        logger.info(f"Generating expressions from {len(request.sentences)} sentences...")

        # Call expression service
        expressions = expr_svc.generate_expressions(
            sentences=request.sentences,
            episode_id=request.episode_id,
            max_input_tokens=request.max_input_tokens,
            max_workers=request.max_workers
        )

        logger.info(f"✅ Generated {len(expressions)} expressions")

        return ExpressionGenerateResponse(
            expressions=expressions
        )

    except DeepseekAPIError as e:
        logger.error(f"Expression generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@app.post(
    "/api/video/transcript",
    response_model=VideoTranscriptResponse,
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}, 429: {"model": ErrorResponse}, 500: {"model": ErrorResponse}}
)
@limiter.limit("1/5seconds")
async def get_video_transcript(
    request: Request,
    body: VideoTranscriptRequest,
    trans_svc: TranscriptService = Depends(get_transcript_service)
):
    """
    Use Case 5: Get YouTube video transcript with timestamps.

    - Accepts video_id or video_url
    - Returns timestamped transcript segments
    - Includes full transcript text and metadata
    - Provides language information and auto-generation status
    - Rate limited: 1 request per 5 seconds per IP address
    """
    try:
        # Extract video ID from URL if provided
        video_id = body.video_id
        if not video_id and body.video_url:
            video_id = trans_svc.extract_video_id(body.video_url)
            if not video_id:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid YouTube URL. Could not extract video ID."
                )

        if not video_id:
            raise HTTPException(
                status_code=400,
                detail="Either video_id or video_url must be provided"
            )

        logger.info(f"Fetching transcript for video: {video_id}")

        # Get transcript
        transcript_data = trans_svc.get_transcript(video_id)

        logger.info(f"✅ Transcript fetched successfully for video {video_id}")

        return VideoTranscriptResponse(**transcript_data)

    except InvalidVideoIdError as e:
        logger.error(f"Invalid video ID: {e}")
        raise HTTPException(status_code=400, detail=str(e))

    except TranscriptNotAvailableError as e:
        logger.error(f"Transcript not available: {e}")
        raise HTTPException(status_code=404, detail=str(e))

    except TranscriptServiceError as e:
        logger.error(f"Transcript service error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    except ValueError as e:
        logger.error(f"Validation error: {e}")
        raise HTTPException(status_code=400, detail=str(e))

    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@app.post(
    "/api/sentence/generate-audio",
    response_model=SentenceAudioGenerateResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}}
)
async def generate_sentence_audio(
    request: SentenceAudioGenerateRequest
):
    """
    Use Case 6: Generate audio files for sentences and upload to COS/R2.

    - Generates MP3 audio files for each sentence using Edge TTS (async)
    - Uploads all audio files to both COS and R2 storage (async)
    - Returns comprehensive upload statistics and results

    This endpoint uses async/await throughout for better performance and
    proper resource management. Audio generation uses edge-tts Python API
    directly (not CLI) with timeout, retry, and concurrency control.
    """
    try:
        from pathlib import Path
        from utils.audio_generator import generate_batch_audio, check_edge_tts_available, AudioGenerationError
        from services.storage_service import upload_audio_files

        logger.info(f"Generating audio for {len(request.sentences)} sentences...")

        # Check if Edge TTS library is available
        if not check_edge_tts_available():
            raise HTTPException(
                status_code=500,
                detail="Edge TTS library is not installed. Please install edge-tts Python package."
            )

        # Create output directory
        audio_dir = Path("audio/sentences")
        audio_dir.mkdir(parents=True, exist_ok=True)

        # Generate audio files asynchronously with concurrency control
        # This uses asyncio.gather internally for parallel processing
        try:
            processed_sentences = await generate_batch_audio(
                sentences=request.sentences,
                audio_dir=audio_dir,
                voice=request.voice,
                max_concurrent=min(request.max_workers, 5),  # Limit to max 5 concurrent
                timeout_per_sentence=30
            )
        except AudioGenerationError as e:
            logger.error(f"Audio generation error: {e}")
            raise HTTPException(status_code=500, detail=str(e))

        # Collect audio files for upload
        upload_files = []
        for sentence in processed_sentences:
            if sentence.get('audio_generated') and sentence.get('audio_path'):
                audio_path = sentence['audio_path']
                sentence_hash = sentence['sentence_hash']
                if Path(audio_path).exists():
                    object_key = f"audio/sentences/{sentence_hash}.mp3"
                    upload_files.append({
                        'file_path': audio_path,
                        'object_key': object_key,
                        'sentence_hash': sentence_hash
                    })

        logger.info(f"📁 Collected {len(upload_files)} audio files for upload")

        # Upload to both COS and R2 concurrently (async)
        cos_upload_results, r2_upload_results, cos_stats, r2_stats = await upload_audio_files(
            upload_files=upload_files,
            upload_to_cos=True,
            upload_to_r2=True,
            max_concurrent_r2=10,
            max_workers_cos=request.max_workers
        )

        # Build upload results map
        cos_upload_map = {r.get('object_key'): r for r in cos_upload_results}
        r2_upload_map = {r.get('object_key'): r for r in r2_upload_results}

        # Build final results
        results = []
        for sentence in processed_sentences:
            sentence_hash = sentence.get('sentence_hash', '')
            object_key = f"audio/sentences/{sentence_hash}.mp3" if sentence_hash else None

            cos_result = cos_upload_map.get(object_key, {}) if object_key else {}
            r2_result = r2_upload_map.get(object_key, {}) if object_key else {}

            results.append(SentenceAudioResult(
                sentence_hash=sentence_hash,
                en=sentence.get('en', ''),
                audio_generated=sentence.get('audio_generated', False),
                uploaded_cos=cos_result.get('success', False),
                uploaded_r2=r2_result.get('success', False),
                cos_object_key=object_key if cos_result.get('success') else None,
                r2_object_key=object_key if r2_result.get('success') else None,
                error=sentence.get('error')
            ))

        # Overall statistics
        total_sentences = len(processed_sentences)
        audio_generated = sum(1 for s in processed_sentences if s.get('audio_generated', False))
        newly_generated = sum(1 for s in processed_sentences if s.get('audio_generated', False) and not s.get('existed', False))
        already_existed = sum(1 for s in processed_sentences if s.get('existed', False))

        statistics = {
            'total_sentences': total_sentences,
            'audio_generated': audio_generated,
            'audio_failed': total_sentences - audio_generated,
            'audio_success_rate': audio_generated / total_sentences if total_sentences > 0 else 0.0,
            'files_collected_for_upload': len(upload_files),
            'newly_generated': newly_generated,
            'already_existed': already_existed
        }

        logger.info(
            f"✅ Audio generation completed: {audio_generated}/{total_sentences} successful "
            f"({newly_generated} new, {already_existed} existed)"
        )

        return SentenceAudioGenerateResponse(
            results=results,
            statistics=statistics,
            cos_upload_stats=cos_stats,
            r2_upload_stats=r2_stats
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Sentence audio generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@app.post(
    "/api/phrase/generate-audio",
    response_model=PhraseAudioGenerateResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}}
)
async def generate_phrase_audio(
    request: PhraseAudioGenerateRequest
):
    """
    Generate audio file for a single phrase and upload to COS/R2.

    This endpoint:
    - Accepts a phrase text (e.g., "break the ice", "S.P.F.")
    - Applies phrase-specific formatting rules for TTS (e.g., spacing acronyms)
    - Optionally checks if audio already exists in R2 and COS
    - Generates MP3 audio file using Edge TTS if needed
    - Uploads to both COS and R2 storage
    - Returns comprehensive status and metadata

    Special formatting rules:
    - Acronyms like "S.P.F." are automatically spaced: "S P F" for better pronunciation
    - Dots and periods are removed for cleaner TTS output
    - Original phrase structure is preserved in filenames

    Example requests:
    ```json
    {
        "phrase": "break the ice",
        "voice": "en-US-AvaMultilingualNeural",
        "check_existing": true
    }
    ```

    ```json
    {
        "phrase": "S.P.F.",
        "voice": "en-US-JennyNeural"
    }
    ```
    """
    try:
        from utils.phrase_audio_generator import generate_and_upload_phrase_audio, check_edge_tts_available

        logger.info(f"Generating phrase audio: {request.phrase}")

        # Check if Edge TTS library is available
        if not check_edge_tts_available():
            raise HTTPException(
                status_code=500,
                detail="Edge TTS library is not installed. Please install edge-tts Python package."
            )

        # Validate phrase
        if not request.phrase or not request.phrase.strip():
            raise HTTPException(
                status_code=400,
                detail="Phrase text is required and cannot be empty"
            )

        # Generate and upload phrase audio
        result = await generate_and_upload_phrase_audio(
            phrase=request.phrase,
            voice=request.voice,
            check_existing=request.check_existing
        )

        # Check if there was an error
        if result.get('error'):
            logger.error(f"Phrase audio generation error: {result['error']}")
            # Still return the result with error info
            return PhraseAudioGenerateResponse(**result)

        # Log success
        if result.get('audio_generated'):
            logger.info(
                f"✅ Phrase audio generated successfully: {result['clean_filename']}.mp3 "
                f"(R2: {result.get('uploaded_r2', False)}, COS: {result.get('uploaded_cos', False)})"
            )
        elif result.get('audio_existed'):
            logger.info(
                f"✅ Phrase audio already exists: {result['clean_filename']}.mp3 "
                f"(R2: {result.get('r2_existed', False)}, COS: {result.get('cos_existed', False)})"
            )

        return PhraseAudioGenerateResponse(**result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Phrase audio generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


# ===== Episode Management Endpoints (MongoDB) =====

@app.get(
    "/api/episode/db/{episode_id}",
    response_model=MongoDBEpisodeResponse,
    responses={404: {"model": ErrorResponse}, 503: {"model": ErrorResponse}, 500: {"model": ErrorResponse}}
)
async def read_episode_from_mongodb(
    episode_id: int,
    mongo_svc: MongoDBService = Depends(get_mongodb_service)
):
    """
    Read episode data from MongoDB by episode_id.

    Queries the episodes collection in MongoDB and returns the complete episode document.
    This endpoint directly accesses the MongoDB database to retrieve the latest episode data.

    Args:
        episode_id: The episode ID to query

    Returns:
        Complete episode data from MongoDB including all fields

    Raises:
        404: Episode not found in database
        503: MongoDB service not available
        500: Internal server error
    """
    try:
        logger.info(f"Reading episode {episode_id} from MongoDB...")

        # Get episode from MongoDB
        episode_data = mongo_svc.get_episode_by_id(episode_id)

        return MongoDBEpisodeResponse(
            episode_id=episode_id,
            data=episode_data
        )

    except EpisodeNotFoundInDBError as e:
        logger.error(f"Episode not found in MongoDB: {e}")
        raise HTTPException(status_code=404, detail=str(e))

    except MongoDBConnectionError as e:
        logger.error(f"MongoDB connection error: {e}")
        raise HTTPException(status_code=503, detail=f"Database connection error: {str(e)}")

    except MongoDBServiceError as e:
        logger.error(f"MongoDB service error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    except Exception as e:
        logger.error(f"Unexpected error reading episode from MongoDB: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
