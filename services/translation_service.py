"""
Translation Service - Handles Chinese translation logic.

Business logic layer for translation operations.
"""

import logging
from typing import Optional
from .deepseek_client import DeepseekClient, DeepseekAPIError
from .prompts import TRANSLATION_SYSTEM_PROMPT, get_translation_user_prompt


logger = logging.getLogger(__name__)


class TranslationService:
    """
    Service for handling Chinese translation operations.

    Responsibilities:
    - Validate input text
    - Call Deepseek API for translation
    - Validate translation output
    - Handle errors gracefully
    """

    def __init__(self, client: DeepseekClient):
        """
        Initialize translation service.

        Args:
            client: DeepseekClient instance for API calls
        """
        self.client = client
        self.logger = logger

    def translate(self, text: str) -> str:
        """
        Translate English text to Chinese.

        Args:
            text: English text to translate

        Returns:
            Chinese translation string

        Raises:
            DeepseekAPIError: If translation fails
        """
        # Input validation
        if not text or not text.strip():
            self.logger.warning("Empty text provided for translation")
            return ""

        text = text.strip()

        try:
            self.logger.debug(f"Translating text: {text[:50]}...")

            # Call API
            translation = self.client.simple_completion(
                system_prompt=TRANSLATION_SYSTEM_PROMPT,
                user_prompt=get_translation_user_prompt(text),
                temperature=0.1,
                max_tokens=2000
            )

            # Validate output - ensure we got Chinese characters
            if not translation or not self._contains_chinese(translation):
                self.logger.warning(f"Translation may be invalid for text: {text[:30]}...")
                return ""

            self.logger.info(f"✅ Translation successful: '{text[:30]}...' -> '{translation[:30]}...'")
            return translation

        except DeepseekAPIError as e:
            self.logger.error(f"Translation failed for text '{text[:30]}...': {e}")
            raise
        except Exception as e:
            self.logger.error(f"Unexpected error during translation: {e}")
            raise DeepseekAPIError(f"Translation failed: {e}")

    def _contains_chinese(self, text: str) -> bool:
        """
        Check if text contains Chinese characters.

        Args:
            text: Text to check

        Returns:
            True if text contains at least one Chinese character
        """
        return any('\u4e00' <= char <= '\u9fff' for char in text)
