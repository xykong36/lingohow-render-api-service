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
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from concurrent.futures import ThreadPoolExecutor

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
    EnhancedSentence,
    HighlightEntry,
    ErrorResponse,
)
from services.deepseek_client import DeepseekClient, DeepseekAPIError
from services.translation_service import TranslationService
from services.phonetic_service import PhoneticService
from services.highlight_service import HighlightService
from services.expression_service import ExpressionService
from utils.text_splitter import split_into_sentences

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global service instances
translation_service: Optional[TranslationService] = None
phonetic_service: Optional[PhoneticService] = None
highlight_service: Optional[HighlightService] = None
expression_service: Optional[ExpressionService] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown events."""
    global translation_service, phonetic_service, highlight_service, expression_service

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
            "expression_generate": "POST /api/expression/generate",
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
            return ParagraphGenerateSentencesResponse(sentences=[], total_count=0)

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
            total_count=len(enhanced_sentences)
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
            expressions=expressions,
            total_count=len(expressions)
        )

    except DeepseekAPIError as e:
        logger.error(f"Expression generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
