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
    ParagraphTranslateRequest,
    ParagraphTranslateResponse,
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
    EnhancedSentence,
    HighlightEntry,
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown events."""
    global translation_service, phonetic_service, highlight_service, expression_service, transcript_service

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

        logger.info("✅ All services initialized successfully")
    except Exception as e:
        logger.error(f"❌ Failed to initialize services: {e}")
        raise

    yield

    # Shutdown
    logger.info("Shutting down Translation API")


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


# ===== Endpoints =====

@app.get("/")
async def root():
    """API information endpoint."""
    return {
        "name": "Translation API",
        "version": "1.0.0",
        "status": "running",
        "endpoints": {
            "paragraph_translate": "POST /api/paragraph/translate",
            "paragraph_generate_sentences": "POST /api/paragraph/generate-sentences",
            "sentence_enhance": "POST /api/sentence/enhance",
            "sentence_audio_generate": "POST /api/sentence/generate-audio",
            "expression_generate": "POST /api/expression/generate",
            "video_transcript": "POST /api/video/transcript",
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
        }
    }


@app.post(
    "/api/paragraph/translate",
    response_model=ParagraphTranslateResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}}
)
async def translate_paragraph(
    request: ParagraphTranslateRequest,
    trans_svc: TranslationService = Depends(get_translation_service),
    highlight_svc: HighlightService = Depends(get_highlight_service)
):
    """
    Use Case 1: Translate a paragraph and optionally extract highlight entries.

    - Translates entire paragraph to Chinese
    - Extracts important words/phrases as highlight entries
    """
    try:
        logger.info(f"Translating paragraph: {request.text[:50]}...")

        # Get Chinese translation
        translation = trans_svc.translate(request.text)

        # Extract highlights if requested
        highlights = []
        if request.extract_highlights:
            logger.info("Extracting highlights from paragraph...")
            highlight_data = highlight_svc.extract_highlights(request.text, translation)
            highlights = [HighlightEntry(**h) for h in highlight_data]

        return ParagraphTranslateResponse(
            original_text=request.text,
            translation=translation,
            highlights=highlights
        )

    except DeepseekAPIError as e:
        logger.error(f"Translation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@app.post(
    "/api/paragraph/generate-sentences",
    response_model=ParagraphGenerateSentencesResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}}
)
async def generate_sentences_from_paragraph(
    request: ParagraphGenerateSentencesRequest,
    trans_svc: TranslationService = Depends(get_translation_service),
    phonetic_svc: PhoneticService = Depends(get_phonetic_service),
    highlight_svc: HighlightService = Depends(get_highlight_service)
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

    - Generates MP3 audio files for each sentence using Edge TTS
    - Uploads all audio files to both COS and R2 storage
    - Returns comprehensive upload statistics and results
    """
    try:
        from pathlib import Path
        from concurrent.futures import ThreadPoolExecutor, as_completed
        from utils.text_helpers import hash_text
        from utils.audio_helpers import generate_audio_with_edge_tts, check_edge_tts_available

        logger.info(f"Generating audio for {len(request.sentences)} sentences...")

        # Check if Edge TTS is available
        if not check_edge_tts_available():
            raise HTTPException(
                status_code=500,
                detail="Edge TTS is not available. Please install edge-tts command line tool."
            )

        # Create output directory
        audio_dir = Path("audio/sentences")
        audio_dir.mkdir(parents=True, exist_ok=True)

        # Process sentences to generate audio files
        def process_single_sentence(sentence_text: str, idx: int) -> dict:
            """Process a single sentence: generate hash and audio file."""
            sentence_text = sentence_text.strip()

            if not sentence_text:
                logger.warning(f"Sentence {idx}: Empty text, skipping")
                return {
                    'en': '',
                    'sentence_hash': '',
                    'audio_path': None,
                    'audio_generated': False,
                    'error': 'Empty sentence text'
                }

            # Generate hash
            sentence_hash = hash_text(sentence_text, length=8)

            # Create audio file path
            audio_filename = f"{sentence_hash}.mp3"
            audio_path = audio_dir / audio_filename

            # Check if audio file already exists
            if audio_path.exists():
                logger.info(f"Sentence {idx}: Audio already exists - {audio_filename}")
                return {
                    'en': sentence_text,
                    'sentence_hash': sentence_hash,
                    'audio_path': str(audio_path),
                    'audio_generated': True,
                    'existed': True
                }

            # Generate new audio file
            logger.info(f"Sentence {idx}: Generating audio for: {sentence_text[:50]}...")
            success = generate_audio_with_edge_tts(sentence_text, audio_path, request.voice)

            if success:
                logger.info(f"Sentence {idx}: ✅ Generated - {audio_filename}")
                return {
                    'en': sentence_text,
                    'sentence_hash': sentence_hash,
                    'audio_path': str(audio_path),
                    'audio_generated': True,
                    'existed': False
                }
            else:
                logger.warning(f"Sentence {idx}: ❌ Failed to generate audio")
                return {
                    'en': sentence_text,
                    'sentence_hash': sentence_hash,
                    'audio_path': None,
                    'audio_generated': False,
                    'error': 'Audio generation failed'
                }

        # Generate audio files in parallel
        processed_sentences = []
        with ThreadPoolExecutor(max_workers=request.max_workers) as executor:
            futures = {
                executor.submit(process_single_sentence, sentence, idx): idx
                for idx, sentence in enumerate(request.sentences)
            }

            for future in as_completed(futures):
                idx = futures[future]
                try:
                    result = future.result()
                    processed_sentences.append((idx, result))
                except Exception as e:
                    logger.error(f"Error processing sentence {idx}: {e}")
                    processed_sentences.append((idx, {
                        'en': request.sentences[idx],
                        'sentence_hash': '',
                        'audio_generated': False,
                        'error': str(e)
                    }))

        # Sort by original index
        processed_sentences.sort(key=lambda x: x[0])
        processed_sentences = [result for _, result in processed_sentences]

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

        # Upload to COS
        cos_upload_results = []
        cos_stats = {'total_uploads': 0, 'successful_uploads': 0, 'failed_uploads': 0, 'success_rate': 0.0}
        try:
            # Load COS configuration directly (without Prefect task wrapper)
            import os
            cos_config = {
                'COS_SECRET_ID': os.getenv('COS_SECRET_ID'),
                'COS_SECRET_KEY': os.getenv('COS_SECRET_KEY'),
                'COS_BUCKET': os.getenv('COS_BUCKET'),
                'COS_REGION': os.getenv('COS_REGION')
            }

            # Check if COS is configured
            if not all(cos_config.values()):
                raise Exception("COS configuration incomplete - missing environment variables")

            logger.info("🔑 COS configuration loaded, starting upload...")

            # Create COS client and upload files
            def upload_to_cos_simple(file_path: str, object_key: str) -> dict:
                """Upload file to COS without Prefect wrapper."""
                try:
                    from qcloud_cos import CosConfig, CosS3Client

                    cos_cfg = CosConfig(
                        Region=cos_config['COS_REGION'],
                        SecretId=cos_config['COS_SECRET_ID'],
                        SecretKey=cos_config['COS_SECRET_KEY']
                    )
                    client = CosS3Client(cos_cfg)

                    file_obj = Path(file_path)
                    if not file_obj.exists():
                        return {'success': False, 'object_key': object_key, 'error': 'File not found'}

                    response = client.upload_file(
                        Bucket=cos_config['COS_BUCKET'],
                        Key=object_key,
                        LocalFilePath=str(file_obj),
                        EnableMD5=True
                    )

                    return {
                        'success': True,
                        'object_key': object_key,
                        'file_name': file_obj.name,
                        'file_size': file_obj.stat().st_size,
                        'etag': response.get('ETag', '').strip('"')
                    }
                except Exception as e:
                    return {'success': False, 'object_key': object_key, 'error': str(e)}

            # Upload files in parallel
            with ThreadPoolExecutor(max_workers=request.max_workers) as executor:
                futures = [
                    executor.submit(upload_to_cos_simple, file_info['file_path'], file_info['object_key'])
                    for file_info in upload_files
                ]
                cos_upload_results = [future.result() for future in as_completed(futures)]

            # Calculate COS statistics
            total_cos = len(cos_upload_results)
            successful_cos = sum(1 for r in cos_upload_results if r.get('success', False))
            cos_stats = {
                'total_uploads': total_cos,
                'successful_uploads': successful_cos,
                'failed_uploads': total_cos - successful_cos,
                'success_rate': successful_cos / total_cos if total_cos > 0 else 0.0
            }
            logger.info(f"📊 COS upload: {successful_cos}/{total_cos} successful")
        except Exception as e:
            logger.warning(f"⚠️ COS upload skipped: {e}")
            cos_stats = {'error': str(e)}

        # Upload to R2
        r2_upload_results = []
        r2_stats = {'total_uploads': 0, 'successful_uploads': 0, 'failed_uploads': 0, 'success_rate': 0.0}
        try:
            # Load R2 configuration directly (without Prefect task wrapper)
            r2_config = {
                'R2_BUCKET_NAME': os.getenv('R2_BUCKET_NAME'),
                'R2_ACCESS_KEY_ID': os.getenv('R2_ACCESS_KEY_ID'),
                'R2_SECRET_ACCESS_KEY': os.getenv('R2_SECRET_ACCESS_KEY'),
                'R2_ACCOUNT_ID': os.getenv('R2_ACCOUNT_ID'),
                'R2_ENDPOINT_URL': os.getenv('R2_ENDPOINT_URL')
            }

            # Check if R2 is configured
            if not all(r2_config.values()):
                raise Exception("R2 configuration incomplete - missing environment variables")

            logger.info("🔑 R2 configuration loaded, starting upload...")

            # Create R2 client and upload files
            def upload_to_r2_simple(file_path: str, object_key: str) -> dict:
                """Upload file to R2 without Prefect wrapper."""
                try:
                    import boto3

                    s3_client = boto3.client(
                        service_name='s3',
                        endpoint_url=r2_config['R2_ENDPOINT_URL'],
                        aws_access_key_id=r2_config['R2_ACCESS_KEY_ID'],
                        aws_secret_access_key=r2_config['R2_SECRET_ACCESS_KEY'],
                        region_name='auto'
                    )

                    file_obj = Path(file_path)
                    if not file_obj.exists():
                        return {'success': False, 'object_key': object_key, 'error': 'File not found'}

                    extra_args = {'ContentType': 'audio/mpeg'}
                    s3_client.upload_file(
                        Filename=str(file_obj),
                        Bucket=r2_config['R2_BUCKET_NAME'],
                        Key=object_key,
                        ExtraArgs=extra_args
                    )

                    return {
                        'success': True,
                        'object_key': object_key,
                        'file_name': file_obj.name,
                        'file_size': file_obj.stat().st_size,
                        'content_type': 'audio/mpeg'
                    }
                except Exception as e:
                    return {'success': False, 'object_key': object_key, 'error': str(e)}

            # Upload files in parallel
            with ThreadPoolExecutor(max_workers=request.max_workers) as executor:
                futures = [
                    executor.submit(upload_to_r2_simple, file_info['file_path'], file_info['object_key'])
                    for file_info in upload_files
                ]
                r2_upload_results = [future.result() for future in as_completed(futures)]

            # Calculate R2 statistics
            total_r2 = len(r2_upload_results)
            successful_r2 = sum(1 for r in r2_upload_results if r.get('success', False))
            r2_stats = {
                'total_uploads': total_r2,
                'successful_uploads': successful_r2,
                'failed_uploads': total_r2 - successful_r2,
                'success_rate': successful_r2 / total_r2 if total_r2 > 0 else 0.0
            }
            logger.info(f"📊 R2 upload: {successful_r2}/{total_r2} successful")
        except Exception as e:
            logger.warning(f"⚠️ R2 upload skipped: {e}")
            r2_stats = {'error': str(e)}

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
        statistics = {
            'total_sentences': total_sentences,
            'audio_generated': audio_generated,
            'audio_failed': total_sentences - audio_generated,
            'audio_success_rate': audio_generated / total_sentences if total_sentences > 0 else 0.0,
            'files_collected_for_upload': len(upload_files)
        }

        logger.info(f"✅ Audio generation completed: {audio_generated}/{total_sentences} successful")

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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
