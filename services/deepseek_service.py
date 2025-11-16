"""
Deepseek Service module for integrating with Deepseek API.
Provides Chinese translation and US phonetic transcription functionality.

This module encapsulates all external API interactions for the translation workflow,
following clean architecture principles and separation of concerns.

Migrated from translation_api.py to services layer for FastAPI architecture.
"""

import json
import re
import time
import logging
from typing import Dict, Any, Optional, List
from concurrent.futures import ThreadPoolExecutor, as_completed
from openai import OpenAI
from bson import ObjectId


class TranslationAPIError(Exception):
    """Custom exception for translation API errors"""
    pass


class DeepseekClient:
    """
    Client for interacting with Deepseek API for translation and phonetic generation.

    This class handles all external API calls and implements rate limiting,
    error handling, and response parsing.
    """

    def __init__(self, api_key: str, base_url: str = "https://api.deepseek.com"):
        """
        Initialize the Deepseek client.

        Args:
            api_key: Deepseek API key
            base_url: API base URL (default: https://api.deepseek.com)

        Raises:
            TranslationAPIError: If API key is invalid or missing
        """
        if not api_key or not api_key.strip():
            raise TranslationAPIError("API key is required and cannot be empty")

        self.api_key = api_key
        self.base_url = base_url
        self.client = self._create_client()
        self.logger = logging.getLogger(__name__)

    def _create_client(self) -> OpenAI:
        """Create and configure the OpenAI client for Deepseek."""
        try:
            return OpenAI(
                api_key=self.api_key,
                base_url=self.base_url
            )
        except Exception as e:
            raise TranslationAPIError(f"Failed to create API client: {e}")

    def get_chinese_translation(self, text: str) -> str:
        """
        Get Chinese translation for English text.

        Args:
            text: English text to translate

        Returns:
            Chinese translation string

        Raises:
            TranslationAPIError: If translation fails
        """
        if not text or not text.strip():
            return ""

        try:
            response = self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are an expert Chinese translator specializing in translating "
                            "English to Chinese. Provide accurate, natural, and fluent Chinese "
                            "translations that follow the principles of faithfulness (信), "
                            "expressiveness (达), and elegance (雅). The translation should be "
                            "concise and smooth, suitable for language learning contexts. "
                            "Return only the Chinese translation without any explanations "
                            "or additional text."
                        )
                    },
                    {
                        "role": "user",
                        "content": f"Translate the following English text to Chinese: {text}"
                    }
                ],
                temperature=0.1,  # Low temperature for consistent translations
                max_tokens=2000,
                stream=False
            )

            translation = response.choices[0].message.content.strip()

            # Basic validation - ensure we got some Chinese characters
            if not translation or not any('\u4e00' <= char <= '\u9fff' for char in translation):
                self.logger.warning(f"Translation may be invalid for text: {text[:30]}...")
                return ""

            return translation

        except Exception as e:
            self.logger.error(f"Chinese translation failed for text '{text[:30]}...': {e}")
            raise TranslationAPIError(f"Translation failed: {e}")

    def get_us_phonetic(self, text: str) -> str:
        """
        Get US phonetic transcription for English text.

        Args:
            text: English text to transcribe

        Returns:
            US phonetic transcription in IPA notation with slashes

        Raises:
            TranslationAPIError: If phonetic generation fails
        """
        if not text or not text.strip():
            return ""

        try:
            response = self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a pronunciation assistant specialized in American English. "
                            "Your task is to provide the US phonetic transcription for the given "
                            "English text using IPA (International Phonetic Alphabet) notation. "
                            "Return only the phonetic transcription enclosed in slashes like this: "
                            "/transcription/. Do not include any explanations or additional text. "
                            "Focus on American English pronunciation patterns."
                        )
                    },
                    {
                        "role": "user",
                        "content": f"Provide US phonetic transcription for: {text}"
                    }
                ],
                temperature=0.1,  # Low temperature for consistent phonetics
                max_tokens=500,
                stream=False
            )

            result = response.choices[0].message.content.strip()

            # Clean up and validate the response
            phonetic = self._parse_phonetic_response(result)

            return phonetic

        except Exception as e:
            self.logger.error(f"Phonetic generation failed for text '{text[:30]}...': {e}")
            raise TranslationAPIError(f"Phonetic generation failed: {e}")

    def _parse_phonetic_response(self, response: str) -> str:
        """
        Parse and clean phonetic response from API.

        Args:
            response: Raw API response

        Returns:
            Cleaned phonetic transcription with slashes
        """
        if not response:
            return ""

        # If it's already properly formatted with slashes
        if response.startswith('/') and response.endswith('/'):
            return response

        # Extract phonetic transcription from response
        # Look for text enclosed in slashes
        phonetic_match = re.search(r'(/[^/]+/)', response)
        if phonetic_match:
            return phonetic_match.group(1)

        # If no slashes found, wrap the response in slashes
        # Remove any extra formatting or explanations
        cleaned_response = response.strip()

        # Remove common prefixes/suffixes that might be added
        prefixes_to_remove = [
            "Phonetic transcription:",
            "IPA:",
            "US pronunciation:",
            "Transcription:"
        ]

        for prefix in prefixes_to_remove:
            if cleaned_response.lower().startswith(prefix.lower()):
                cleaned_response = cleaned_response[len(prefix):].strip()

        # If it doesn't start with /, add slashes
        if not cleaned_response.startswith('/'):
            cleaned_response = f"/{cleaned_response}/"
        elif not cleaned_response.endswith('/'):
            cleaned_response = f"{cleaned_response}/"

        return cleaned_response

    def get_highlight_entries(self, text: str, chinese_translation: str = "") -> list:
        """
        Get highlight entries for important expressions in the text.

        Args:
            text: English text to analyze
            chinese_translation: Chinese translation of the full sentence (optional)

        Returns:
            List of highlight entry dictionaries with 'slug', 'display_text', and 'translation_zh'

        Raises:
            TranslationAPIError: If highlight generation fails
        """
        if not text or not text.strip():
            return []

        # Build the system prompt based on whether we have Chinese translation
        if chinese_translation and chinese_translation.strip():
            system_content = (
                "You are an English language learning assistant. Analyze the given English sentence "
                "and identify important or interesting learning points that would be valuable "
                "for American middle school students (with basic/intermediate vocabulary) to learn. "
                "Focus on:\n"
                "1. Important individual words that are advanced or context-specific (e.g., 'enthusiasts', 'ceremony')\n"
                "2. Phrasal verbs (e.g., 'moved to', 'got pulled in', 'figure out')\n"
                "3. Common collocations and expressions (e.g., 'thanks to', 'at the very last minute')\n"
                "4. Idioms and figurative language (e.g., 'hit the nail on the head')\n"
                "5. Useful sentence patterns and structures (e.g., 'not only... but also', 'used to')\n\n"
                "Guidelines:\n"
                "- Every sentence needs at least one highlight\n"
                "- Prioritize words/phrases that are useful and frequently used\n"
                "- Avoid basic vocabulary that middle schoolers already know\n"
                "- For single words, focus on those that are important for the context\n\n"
                "IMPORTANT: For translation_zh, you MUST extract the matching substring from the provided Chinese translation. "
                "Do NOT create a new translation. Find the exact words/phrase in the Chinese sentence that corresponds to the English highlight.\n\n"
                "Return ONLY a valid JSON array of objects with this exact format:\n"
                "[{\"slug\": \"kebab-case-slug\", \"display_text\": \"original word/phrase\", \"translation_zh\": \"从中文句子中提取的对应片段\"}]\n\n"
                "If there are NO highlights, return an empty array: []\n"
                "Do NOT include any explanations, just the JSON array."
            )
            user_content = f"English sentence: {text}\nChinese translation: {chinese_translation}\n\nAnalyze this sentence for highlight entries."
        else:
            # Fallback to old behavior if no Chinese translation provided
            system_content = (
                "You are an English language learning assistant. Analyze the given sentence "
                "and identify important or interesting learning points that would be valuable "
                "for American middle school students (with basic/intermediate vocabulary) to learn. "
                "Focus on:\n"
                "1. Important individual words that are advanced or context-specific (e.g., 'enthusiasts', 'ceremony')\n"
                "2. Phrasal verbs (e.g., 'moved to', 'got pulled in', 'figure out')\n"
                "3. Common collocations and expressions (e.g., 'thanks to', 'at the very last minute')\n"
                "4. Idioms and figurative language (e.g., 'hit the nail on the head')\n"
                "5. Useful sentence patterns and structures (e.g., 'not only... but also', 'used to')\n\n"
                "Guidelines:\n"
                "- every sentence needs at least one highlight\n"
                "- Prioritize words/phrases that are useful and frequently used\n"
                "- Avoid basic vocabulary that middle schoolers already know\n"
                "- For single words, focus on those that are important for the context\n\n"
                "Return ONLY a valid JSON array of objects with this exact format:\n"
                "[{\"slug\": \"kebab-case-slug\", \"display_text\": \"original word/phrase\", \"translation_zh\": \"中文翻译\"}]\n\n"
                "If there are NO highlights, return an empty array: []\n"
                "Do NOT include any explanations, just the JSON array."
            )
            user_content = f"Analyze this sentence for highlight entries: {text}"

        try:
            response = self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {
                        "role": "system",
                        "content": system_content
                    },
                    {
                        "role": "user",
                        "content": user_content
                    }
                ],
                temperature=0.3,
                max_tokens=500,
                stream=False
            )

            result = response.choices[0].message.content.strip()

            # Parse JSON response
            try:
                highlights = json.loads(result)
                if not isinstance(highlights, list):
                    self.logger.warning(f"Invalid highlight format (not a list): {result[:100]}")
                    return []

                # Validate each entry has required fields
                validated_highlights = []
                for entry in highlights:
                    if not isinstance(entry, dict) or not all(k in entry for k in ['slug', 'display_text', 'translation_zh']):
                        self.logger.warning(f"Skipping invalid highlight entry: {entry}")
                        continue

                    # Additional validation: if we have Chinese translation, verify translation_zh is a substring
                    if chinese_translation and chinese_translation.strip():
                        translation_zh = entry.get('translation_zh', '').strip()
                        if translation_zh and translation_zh not in chinese_translation:
                            self.logger.warning(
                                f"⚠️ translation_zh '{translation_zh}' not found in sentence '{chinese_translation}'. "
                                f"Skipping highlight entry: {entry}"
                            )
                            continue

                    validated_highlights.append(entry)

                return validated_highlights

            except json.JSONDecodeError as e:
                self.logger.warning(f"Failed to parse highlight JSON for '{text[:30]}...': {e}")
                return []

        except Exception as e:
            self.logger.error(f"Highlight generation failed for text '{text[:30]}...': {e}")
            raise TranslationAPIError(f"Highlight generation failed: {e}")

    def enhance_sentence(self, sentence_data: Dict[str, Any], delay: float = 0.2) -> Dict[str, Any]:
        """
        Enhance a sentence with Chinese translation and US phonetic transcription.

        This is the main method that combines both translation and phonetic generation
        for a single sentence, with built-in rate limiting.

        Args:
            sentence_data: Dictionary containing sentence data with 'en' key
            delay: Delay in seconds after API calls (for rate limiting)

        Returns:
            Enhanced sentence dictionary with 'zh' and 'phonetic_us' fields

        Raises:
            TranslationAPIError: If enhancement fails critically
        """
        if not isinstance(sentence_data, dict):
            raise TranslationAPIError("sentence_data must be a dictionary")

        english_text = sentence_data.get('en', '').strip()
        if not english_text:
            self.logger.warning("Empty English text in sentence data")
            return {
                **sentence_data,
                'zh': '',
                'phonetic_us': ''
            }

        enhanced_sentence = sentence_data.copy()

        try:
            # Get Chinese translation
            self.logger.debug(f"Getting Chinese translation for: {english_text[:50]}...")
            chinese_translation = self.get_chinese_translation(english_text)
            enhanced_sentence['zh'] = chinese_translation

            # Small delay between calls to avoid overwhelming the API
            time.sleep(delay / 2)

            # Get US phonetic transcription
            self.logger.debug(f"Getting phonetic transcription for: {english_text[:50]}...")
            phonetic_transcription = self.get_us_phonetic(english_text)
            enhanced_sentence['phonetic_us'] = phonetic_transcription

            # Final delay for rate limiting
            time.sleep(delay / 2)

            self.logger.info(f"Enhanced sentence: '{english_text[:30]}...' -> '{chinese_translation[:30]}...'")

            return enhanced_sentence

        except TranslationAPIError:
            # Re-raise translation API errors
            raise
        except Exception as e:
            # Handle unexpected errors gracefully
            self.logger.error(f"Unexpected error enhancing sentence '{english_text[:30]}...': {e}")
            # Return original sentence with empty translation fields
            return {
                **sentence_data,
                'zh': '',
                'phonetic_us': ''
            }

    def _robust_json_parse(self, json_str: str, max_retries: int = 3) -> List[Dict[str, Any]]:
        """
        Robustly parse JSON with error recovery and fixing common issues.

        Args:
            json_str: JSON string to parse
            max_retries: Maximum number of fixing attempts

        Returns:
            Parsed list of dictionaries, or empty list if parsing fails

        Attempts to fix:
        - Missing trailing commas in arrays
        - Missing closing brackets
        - Truncated JSON responses
        - Markdown code blocks
        """
        # First, try to extract JSON from markdown code blocks
        json_match = re.search(r'```json\s*(\[.*?\])\s*```', json_str, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        elif not json_str.strip().startswith('['):
            # Try to find JSON array in the response
            array_match = re.search(r'\[.*\]', json_str, re.DOTALL)
            if array_match:
                json_str = array_match.group(0)

        for attempt in range(max_retries):
            try:
                # Try standard parsing first
                result = json.loads(json_str)
                if isinstance(result, list):
                    return result
                else:
                    self.logger.warning(f"JSON result is not a list: {type(result)}")
                    return []
            except json.JSONDecodeError as e:
                self.logger.warning(f"JSON parse attempt {attempt + 1} failed: {e}")

                # Try to fix common issues
                if attempt < max_retries - 1:
                    json_str = self._fix_json_errors(json_str, str(e))
                else:
                    # Last attempt: try to extract partial valid JSON
                    partial_result = self._extract_partial_json(json_str)
                    if partial_result:
                        self.logger.info(f"Extracted {len(partial_result)} expressions from partial JSON")
                        return partial_result
                    else:
                        self.logger.error(f"All JSON parsing attempts failed")
                        return []

        return []

    def _fix_json_errors(self, json_str: str, error_msg: str) -> str:
        """
        Attempt to fix common JSON formatting errors.

        Args:
            json_str: JSON string with errors
            error_msg: Error message from JSONDecodeError

        Returns:
            Fixed JSON string
        """
        # Handle truncated JSON (missing closing brackets)
        if "Unterminated string" in error_msg or "Expecting" in error_msg:
            # Count opening and closing brackets
            open_braces = json_str.count('{')
            close_braces = json_str.count('}')
            open_brackets = json_str.count('[')
            close_brackets = json_str.count(']')

            # Add missing closing brackets
            if close_braces < open_braces:
                json_str += '}' * (open_braces - close_braces)
            if close_brackets < open_brackets:
                json_str += ']' * (open_brackets - close_brackets)

        # Fix missing commas between objects (common LLM error)
        # Pattern: }{ -> },{
        json_str = re.sub(r'\}\s*\{', '},{', json_str)

        # Fix trailing commas before closing brackets (valid in some parsers but not standard JSON)
        json_str = re.sub(r',\s*\]', ']', json_str)
        json_str = re.sub(r',\s*\}', '}', json_str)

        return json_str

    def _extract_partial_json(self, json_str: str) -> List[Dict[str, Any]]:
        """
        Extract valid expression objects from malformed JSON.

        Uses regex to find individual complete expression objects even if
        the overall JSON array is malformed.

        Args:
            json_str: Malformed JSON string

        Returns:
            List of successfully extracted expression dictionaries
        """
        expressions = []

        # Find all potential expression objects using regex
        # Pattern: {"phrase": ...} with balanced braces
        pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'

        matches = re.finditer(pattern, json_str, re.DOTALL)

        for match in matches:
            obj_str = match.group(0)
            try:
                obj = json.loads(obj_str)
                # Validate it looks like an expression
                if isinstance(obj, dict) and 'phrase' in obj:
                    expressions.append(obj)
            except json.JSONDecodeError:
                # This object is also malformed, skip it
                continue

        return expressions

    def _process_batch_with_retry(self, sentences: list, episode_id: int, batch_idx: int, max_retries: int = 3) -> List[Dict[str, Any]]:
        """
        Process a batch with retry logic and error handling.

        Args:
            sentences: List of sentences in this batch
            episode_id: Episode ID
            batch_idx: Batch index for logging
            max_retries: Maximum retry attempts

        Returns:
            List of expression dictionaries

        Raises:
            Exception: If all retries fail
        """
        last_error = None

        for attempt in range(max_retries):
            try:
                self.logger.info(f"Processing batch {batch_idx} (attempt {attempt + 1}/{max_retries})")

                # Add delay between retries
                if attempt > 0:
                    delay = 2 ** attempt  # Exponential backoff: 2s, 4s, 8s
                    self.logger.info(f"Retrying after {delay}s delay...")
                    time.sleep(delay)

                # Call the actual batch processing
                expressions = self._generate_expressions_from_batch(
                    sentences,
                    episode_id,
                    start_expr_id=1  # Will be reassigned later
                )

                if expressions:
                    return expressions
                else:
                    self.logger.warning(f"Batch {batch_idx} returned no expressions (attempt {attempt + 1})")
                    # Continue to retry

            except Exception as e:
                last_error = e
                self.logger.warning(f"Batch {batch_idx} attempt {attempt + 1} failed: {e}")

        # All retries failed
        if last_error:
            raise last_error
        else:
            self.logger.error(f"Batch {batch_idx} failed after {max_retries} attempts with no expressions")
            return []

    def _normalize_expression_data(self, expr: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize and validate expression data from API response.
        Transforms legacy format to match TypeScript ExpressionData interface.

        Args:
            expr: Raw expression dictionary from API

        Returns:
            Normalized expression dictionary with correct structure
        """
        normalized = {}

        # Copy simple fields
        normalized['phrase'] = expr.get('phrase', '')
        normalized['phonetic'] = expr.get('phonetic', '')
        normalized['type'] = expr.get('type', 'expression')
        normalized['tags'] = expr.get('tags', [])
        normalized['forms'] = expr.get('forms', [normalized['phrase']])
        normalized['matched_sentence_indices'] = expr.get('matched_sentence_indices', [])

        # Normalize meanings array
        meanings = expr.get('meanings', [])
        normalized_meanings = []
        for meaning in meanings:
            if isinstance(meaning, dict):
                # New format: {translations: {zh, en}, examples: [{zh, en}]}
                if 'translations' in meaning:
                    normalized_meanings.append({
                        'translations': meaning.get('translations', {'zh': '', 'en': ''}),
                        'examples': meaning.get('examples', [])
                    })
                # Legacy format: {language: 'zh', translation: '...', example: '...'}
                elif 'language' in meaning or 'translation' in meaning:
                    # Skip, will be handled after loop
                    continue

        # If no normalized meanings, create from legacy format
        if not normalized_meanings and meanings:
            # Try to find zh and en translations
            zh_meaning = next((m for m in meanings if m.get('language') == 'zh'), None)
            en_meaning = next((m for m in meanings if m.get('language') == 'en'), None)

            if zh_meaning or en_meaning:
                normalized_meanings.append({
                    'translations': {
                        'zh': zh_meaning.get('translation', '') if zh_meaning else '',
                        'en': en_meaning.get('translation', '') if en_meaning else ''
                    },
                    'examples': [
                        {
                            'zh': zh_meaning.get('example', '') if zh_meaning else '',
                            'en': en_meaning.get('example', '') if en_meaning else ''
                        }
                    ] if (zh_meaning and zh_meaning.get('example')) or (en_meaning and en_meaning.get('example')) else []
                })

        normalized['meanings'] = normalized_meanings if normalized_meanings else []

        # Normalize wordRelations
        word_relations = expr.get('wordRelations', {})
        normalized['wordRelations'] = {
            'synonyms': self._normalize_phrase_list(word_relations.get('synonyms', [])),
            'antonyms': self._normalize_phrase_list(word_relations.get('antonyms', [])),
            'similar': self._normalize_phrase_list(word_relations.get('similar', []))
        }

        # Normalize relatedExpressions
        related = expr.get('relatedExpressions', [])
        normalized_related = []
        for item in related:
            if isinstance(item, dict):
                # Already correct format
                if 'type' in item and 'phrase' in item:
                    normalized_related.append({
                        'type': item.get('type', 'related'),
                        'phrase': item.get('phrase', ''),
                        'translation': item.get('translation', ''),
                        'examples': item.get('examples', [])
                    })
            elif isinstance(item, str):
                # Legacy format: just string
                normalized_related.append({
                    'type': 'related',
                    'phrase': item,
                    'translation': '',
                    'examples': []
                })

        normalized['relatedExpressions'] = normalized_related

        # Normalize analysis
        analysis = expr.get('analysis', [])
        normalized_analysis = []
        for item in analysis:
            if isinstance(item, dict) and 'type' in item and 'content' in item:
                normalized_analysis.append(item)

        normalized['analysis'] = normalized_analysis

        return normalized

    def _normalize_phrase_list(self, items: list) -> list:
        """
        Normalize a list of phrases to {phrase, translation} format.

        Args:
            items: List of phrases (strings or dicts)

        Returns:
            List of {phrase, translation} objects
        """
        normalized = []
        for item in items:
            if isinstance(item, dict):
                # Already correct format
                if 'phrase' in item:
                    normalized.append({
                        'phrase': item.get('phrase', ''),
                        'translation': item.get('translation', '')
                    })
            elif isinstance(item, str):
                # Legacy format: just string
                normalized.append({
                    'phrase': item,
                    'translation': ''
                })

        return normalized

    def _estimate_token_count(self, text: str) -> int:
        """
        Estimate token count for text (rough approximation: 1 token ≈ 4 characters for English).

        Args:
            text: Text to estimate

        Returns:
            Estimated token count
        """
        # Simple estimation: ~4 chars per token for English, ~2 for Chinese
        return len(text) // 3

    def _split_sentences_by_token_limit(self, sentences: list, max_input_tokens: int = 2500) -> list:
        """
        Split sentences into smaller batches that fit within token limits.

        Reduced batch size to 2500 tokens (from 6000) to:
        - Reduce DeepSeek response complexity and JSON formatting errors
        - Process 10-20 sentences per batch instead of hundreds
        - Enable parallel processing with better granularity

        Args:
            sentences: List of sentence dictionaries
            max_input_tokens: Maximum input tokens per batch (default: 2500 for better JSON reliability)

        Returns:
            List of sentence batches (each with 10-20 sentences typically)
        """
        batches = []
        current_batch = []
        current_tokens = 0

        for sentence in sentences:
            en_text = sentence.get('en', '')
            sentence_tokens = self._estimate_token_count(en_text)

            # If adding this sentence exceeds limit, start new batch
            if current_tokens + sentence_tokens > max_input_tokens and current_batch:
                batches.append(current_batch)
                current_batch = [sentence]
                current_tokens = sentence_tokens
            else:
                current_batch.append(sentence)
                current_tokens += sentence_tokens

        # Add remaining batch
        if current_batch:
            batches.append(current_batch)

        return batches

    def generate_expressions_from_sentences(self, sentences: list, episode_id: int = 1, max_input_tokens: int = 2500, max_workers: int = 4) -> list:
        """
        Generate expression data from a list of sentences with parallel batch processing.

        This method automatically splits large sentence lists into smaller batches and
        processes them in parallel using ThreadPoolExecutor for improved performance.

        Args:
            sentences: List of sentence dictionaries with 'en', 'zh', 'sentence_id', 'episode_sequence'
            episode_id: Episode ID for the expressions
            max_input_tokens: Maximum input tokens per API call (default: 2500 for better JSON reliability)
            max_workers: Maximum number of parallel workers (default: 4, limited to avoid rate limiting)

        Returns:
            List of expression dictionaries with complete expression data structure

        Raises:
            TranslationAPIError: If expression generation fails
        """
        if not sentences:
            self.logger.warning("No sentences provided for expression generation")
            return []

        # Split sentences into smaller batches
        batches = self._split_sentences_by_token_limit(sentences, max_input_tokens)

        if len(batches) > 1:
            self.logger.info(f"Split {len(sentences)} sentences into {len(batches)} batches for parallel processing")

        all_expressions = []

        # Process batches in parallel
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all batch processing tasks
            future_to_batch = {}
            for batch_idx, batch_sentences in enumerate(batches, 1):
                future = executor.submit(
                    self._process_batch_with_retry,
                    batch_sentences,
                    episode_id,
                    batch_idx
                )
                future_to_batch[future] = batch_idx

            # Collect results as they complete
            for future in as_completed(future_to_batch):
                batch_idx = future_to_batch[future]
                try:
                    batch_expressions = future.result()
                    all_expressions.extend(batch_expressions)
                    self.logger.info(f"✅ Batch {batch_idx}/{len(batches)} completed: {len(batch_expressions)} expressions")
                except Exception as e:
                    self.logger.error(f"❌ Batch {batch_idx}/{len(batches)} failed: {e}")
                    # Continue processing other batches

        # Deduplicate and merge expressions
        deduplicated_expressions = self._deduplicate_expressions(all_expressions)

        # Reassign expression IDs using ObjectId
        for expr in deduplicated_expressions:
            expr['expression_id'] = str(ObjectId())

        self.logger.info(f"Generated total of {len(deduplicated_expressions)} unique expressions from {len(sentences)} sentences ({len(all_expressions)} before deduplication)")
        return deduplicated_expressions

    def _generate_expressions_from_batch(self, sentences: list, episode_id: int, start_expr_id: int = 1) -> list:
        """
        Generate expressions from a single batch of sentences.

        Args:
            sentences: List of sentence dictionaries (one batch)
            episode_id: Episode ID for the expressions
            start_expr_id: Starting expression ID for this batch

        Returns:
            List of expression dictionaries

        Raises:
            TranslationAPIError: If expression generation fails
        """
        try:
            # Combine all sentences for context
            sentences_text = "\n".join([
                f"{i+1}. {s.get('en', '')}"
                for i, s in enumerate(sentences)
                if s.get('en', '').strip()
            ])

            response = self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are an expert English language learning content creator. "
                            "Analyze the given sentences and identify important expressions, phrasal verbs, "
                            "idioms, and collocations that would be valuable for learners.\n\n"
                            "For each expression, provide a JSON object with this EXACT structure:\n"
                            "{\n"
                            "  \"phrase\": \"base form of expression\",\n"
                            "  \"phonetic\": \"/IPA notation/\",\n"
                            "  \"type\": \"phrasal verb|idiom|collocation|expression\",\n"
                            "  \"meanings\": [\n"
                            "    {\n"
                            "      \"translations\": {\"zh\": \"中文翻译\", \"en\": \"English definition\"},\n"
                            "      \"examples\": [{\"zh\": \"中文例句\", \"en\": \"English example\"}]\n"
                            "    }\n"
                            "  ],\n"
                            "  \"wordRelations\": {\n"
                            "    \"synonyms\": [{\"phrase\": \"synonym\", \"translation\": \"同义词翻译\"}],\n"
                            "    \"antonyms\": [{\"phrase\": \"antonym\", \"translation\": \"反义词翻译\"}],\n"
                            "    \"similar\": [{\"phrase\": \"similar phrase\", \"translation\": \"相似短语翻译\"}]\n"
                            "  },\n"
                            "  \"relatedExpressions\": [\n"
                            "    {\n"
                            "      \"type\": \"collocation|variation|idiom\",\n"
                            "      \"phrase\": \"related phrase\",\n"
                            "      \"translation\": \"相关短语翻译\",\n"
                            "      \"examples\": [{\"zh\": \"例句\", \"en\": \"example\"}]\n"
                            "    }\n"
                            "  ],\n"
                            "  \"analysis\": [{\"type\": \"grammar|usage\", \"content\": \"分析内容\"}],\n"
                            "  \"tags\": [\"tag1\", \"tag2\"],\n"
                            "  \"forms\": [\"form1\", \"form2\"],\n"
                            "  \"matched_sentence_indices\": [1, 3, 5]\n"
                            "}\n\n"
                            "IMPORTANT: Return ONLY a valid JSON array of expression objects. "
                            "Extract ALL valuable expressions, phrasal verbs, idioms, and collocations from the content. "
                            "Include as many expressions as you can find (typically 20-50 per batch). "
                            "Do NOT limit yourself to only the most important ones. "
                            "Do NOT include basic vocabulary that beginners already know (like 'have', 'go', 'make'). "
                            "Focus on: phrasal verbs, idioms, collocations, useful expressions, and intermediate/advanced vocabulary."
                        )
                    },
                    {
                        "role": "user",
                        "content": f"Extract ALL important expressions from these sentences:\n\n{sentences_text}"
                    }
                ],
                temperature=0.3,
                max_tokens=6000,
                stream=False
            )

            result = response.choices[0].message.content.strip()

            # Parse JSON response with robust error handling
            expressions = self._robust_json_parse(result)
            if not expressions:
                self.logger.warning("No valid expressions parsed from API response")
                return []

            # Process and enhance each expression
            from bson import ObjectId
            processed_expressions = []

            for idx, expr in enumerate(expressions):
                if not isinstance(expr, dict):
                    continue

                # Normalize expression data to match TypeScript interface
                normalized_expr = self._normalize_expression_data(expr)

                # Get phrase from normalized data
                phrase = normalized_expr.get('phrase', '')
                if not phrase:
                    continue

                # Generate slug from phrase
                slug = phrase.lower().replace(' ', '-').replace("'", '')

                # Match sentences containing this expression
                matched_sentences = []
                matched_indices = normalized_expr.get('matched_sentence_indices', [])

                for sent_idx in matched_indices:
                    if 1 <= sent_idx <= len(sentences):
                        sentence = sentences[sent_idx - 1]
                        en_text = sentence.get('en', '')

                        # Find the matched text in the sentence
                        matched_highlight = self._find_phrase_in_sentence(
                            phrase, en_text, normalized_expr.get('forms', [])
                        )

                        # Build EnhancedSentenceData with all fields
                        matched_sentences.append({
                            'sentence_id': sentence.get('sentence_id'),
                            'episode_id': sentence.get('episode_id', episode_id),
                            'episode_sequence': sentence.get('episode_sequence', sent_idx),
                            'en': en_text,
                            'zh': sentence.get('zh', ''),
                            'phonetic_us': sentence.get('phonetic_us', ''),
                            'start_ts': sentence.get('start_ts', 0),
                            'end_ts': sentence.get('end_ts', 0),
                            'duration': sentence.get('duration', 0),
                            'sentence_hash': sentence.get('sentence_hash', ''),
                            'highlight_entries': sentence.get('highlight_entries', []),
                            'matched_highlight': matched_highlight
                        })

                # Build complete expression object matching TypeScript ExpressionData interface
                processed_expr = {
                    'expression_id': str(ObjectId()),  # Use ObjectId instead of sequential ID
                    'phrase': phrase,
                    'phonetic': normalized_expr.get('phonetic', ''),
                    'type': normalized_expr.get('type', 'expression'),
                    'meanings': normalized_expr.get('meanings', []),
                    'wordRelations': normalized_expr.get('wordRelations', {
                        'synonyms': [],
                        'antonyms': [],
                        'similar': []
                    }),
                    'relatedExpressions': normalized_expr.get('relatedExpressions', []),
                    'analysis': normalized_expr.get('analysis', []),
                    'tags': normalized_expr.get('tags', []),
                    'episodes': [str(episode_id)],
                    'matched_sentences': matched_sentences,
                    'slug': slug,
                    'forms': normalized_expr.get('forms', [phrase])
                }

                processed_expressions.append(processed_expr)

            self.logger.info(f"Generated {len(processed_expressions)} expressions from {len(sentences)} sentences")
            return processed_expressions

        except Exception as e:
            self.logger.error(f"Expression generation failed: {e}")
            raise TranslationAPIError(f"Expression generation failed: {e}")

    def _deduplicate_expressions(self, expressions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Deduplicate expressions based on phrase, merging matched_sentences.

        Args:
            expressions: List of expression dictionaries (may contain duplicates)

        Returns:
            Deduplicated list of expressions with merged matched_sentences
        """
        if not expressions:
            return []

        # Group expressions by phrase (case-insensitive)
        phrase_to_expressions = {}

        for expr in expressions:
            phrase = expr.get('phrase', '').lower().strip()
            if not phrase:
                continue

            if phrase not in phrase_to_expressions:
                phrase_to_expressions[phrase] = []

            phrase_to_expressions[phrase].append(expr)

        # Merge duplicates
        deduplicated = []

        for phrase, expr_list in phrase_to_expressions.items():
            if len(expr_list) == 1:
                # No duplicates, use as-is
                deduplicated.append(expr_list[0])
            else:
                # Merge multiple expressions with same phrase
                merged_expr = self._merge_expressions(expr_list)
                deduplicated.append(merged_expr)

        self.logger.info(f"Deduplicated {len(expressions)} -> {len(deduplicated)} expressions")
        return deduplicated

    def _merge_expressions(self, expr_list: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Merge multiple expressions with the same phrase into one.

        Combines matched_sentences and keeps the richest metadata.

        Args:
            expr_list: List of expression dictionaries with same phrase

        Returns:
            Merged expression dictionary
        """
        if not expr_list:
            return {}

        # Start with the first expression as base
        merged = expr_list[0].copy()

        # Collect all matched sentences from all expressions
        all_matched_sentences = []
        seen_sentence_ids = set()

        for expr in expr_list:
            matched_sentences = expr.get('matched_sentences', [])
            for sent in matched_sentences:
                sent_id = sent.get('sentence_id')
                if sent_id and sent_id not in seen_sentence_ids:
                    all_matched_sentences.append(sent)
                    seen_sentence_ids.add(sent_id)

        merged['matched_sentences'] = all_matched_sentences

        # Merge meanings (keep unique translations)
        all_meanings = []
        seen_translations = set()

        for expr in expr_list:
            meanings = expr.get('meanings', [])
            for meaning in meanings:
                zh_trans = meaning.get('translations', {}).get('zh', '')
                if zh_trans and zh_trans not in seen_translations:
                    all_meanings.append(meaning)
                    seen_translations.add(zh_trans)

        if all_meanings:
            merged['meanings'] = all_meanings

        # Merge tags (unique)
        all_tags = set()
        for expr in expr_list:
            all_tags.update(expr.get('tags', []))
        merged['tags'] = list(all_tags)

        # Merge forms (unique)
        all_forms = set()
        for expr in expr_list:
            all_forms.update(expr.get('forms', []))
        merged['forms'] = list(all_forms)

        # Keep the richest word relations (most items)
        best_word_relations = merged.get('wordRelations', {'synonyms': [], 'antonyms': [], 'similar': []})
        for expr in expr_list[1:]:
            wr = expr.get('wordRelations', {})
            if len(wr.get('synonyms', [])) > len(best_word_relations.get('synonyms', [])):
                best_word_relations['synonyms'] = wr.get('synonyms', [])
            if len(wr.get('antonyms', [])) > len(best_word_relations.get('antonyms', [])):
                best_word_relations['antonyms'] = wr.get('antonyms', [])
            if len(wr.get('similar', [])) > len(best_word_relations.get('similar', [])):
                best_word_relations['similar'] = wr.get('similar', [])

        merged['wordRelations'] = best_word_relations

        # Merge related expressions (unique by phrase)
        all_related = {}
        for expr in expr_list:
            for related in expr.get('relatedExpressions', []):
                related_phrase = related.get('phrase', '')
                if related_phrase and related_phrase not in all_related:
                    all_related[related_phrase] = related

        merged['relatedExpressions'] = list(all_related.values())

        # Merge analysis (unique by type)
        all_analysis = {}
        for expr in expr_list:
            for analysis_item in expr.get('analysis', []):
                analysis_type = analysis_item.get('type', '')
                if analysis_type and analysis_type not in all_analysis:
                    all_analysis[analysis_type] = analysis_item

        merged['analysis'] = list(all_analysis.values())

        return merged

    def _find_phrase_in_sentence(self, phrase: str, sentence: str, forms: list) -> str:
        """
        Find the best matching form of a phrase in a sentence.

        Args:
            phrase: Base phrase to find
            sentence: Sentence text to search in
            forms: List of phrase forms/variations

        Returns:
            The matched text from the sentence, or the base phrase if not found
        """
        sentence_lower = sentence.lower()

        # Try each form
        for form in forms:
            if form.lower() in sentence_lower:
                # Find the actual cased version in the sentence
                start_idx = sentence_lower.index(form.lower())
                return sentence[start_idx:start_idx + len(form)]

        # Try the base phrase
        if phrase.lower() in sentence_lower:
            start_idx = sentence_lower.index(phrase.lower())
            return sentence[start_idx:start_idx + len(phrase)]

        # Return base phrase as fallback
        return phrase


def create_deepseek_client(api_key: str) -> DeepseekClient:
    """
    Factory function to create a DeepseekClient instance.

    Args:
        api_key: Deepseek API key

    Returns:
        Configured DeepseekClient instance

    Raises:
        TranslationAPIError: If client creation fails
    """
    return DeepseekClient(api_key)


def test_client_connection(api_key: str) -> bool:
    """
    Test if the API client can connect successfully.

    Args:
        api_key: Deepseek API key to test

    Returns:
        True if connection is successful, False otherwise
    """
    try:
        client = create_deepseek_client(api_key)
        # Test with a simple phrase
        test_result = client.get_chinese_translation("Hello world")
        return bool(test_result and any('\u4e00' <= char <= '\u9fff' for char in test_result))
    except Exception:
        return False


if __name__ == "__main__":
    # Simple test when run directly
    import os

    api_key = os.getenv('DEEPSEEK_API_KEY')
    if not api_key:
        print("Please set DEEPSEEK_API_KEY environment variable for testing")
        exit(1)

    # Test the client
    try:
        client = create_deepseek_client(api_key)

        test_sentence = {
            'en': 'Hello, this is a test sentence.',
            'start_ts': 0.0,
            'end_ts': 2.5
        }

        print("Testing sentence enhancement...")
        enhanced = client.enhance_sentence(test_sentence)

        print("Original:", test_sentence)
        print("Enhanced:", enhanced)

    except Exception as e:
        print(f"Test failed: {e}")
