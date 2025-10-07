"""
LLM Provider Router - Manages multiple LLM providers with fallback support
Supports Google Gemini (primary), OpenRouter (secondary) and optional Groq fallback
"""

import logging
import time
from typing import Optional, Tuple, Dict, Any
import openai
from groq import Groq
from config import config

# Google Gemini support
try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    genai = None

logger = logging.getLogger(__name__)

class LLMProviderRouter:
    """Routes LLM requests through multiple providers with fallback support"""

    def __init__(self):
        self.gemini_client = None
        self.openrouter_client = None
        self.groq_client = None
        self.current_model = None
        self.current_provider = None  # 'gemini', 'openrouter', 'groq'
        self.retry_count = 0
        self.max_retries = 2

        self._initialize_clients()
    
    def _initialize_clients(self):
        """Initialize available LLM clients"""
        # Google Gemini client setup (primary)
        if GEMINI_AVAILABLE and config.GEMINI_API_KEY:
            try:
                genai.configure(api_key=config.GEMINI_API_KEY)
                self.gemini_client = genai.GenerativeModel(config.GEMINI_MODEL)
                logger.info(f"✅ Gemini client initialized: {config.GEMINI_MODEL}")
            except Exception as e:
                logger.warning(f"⚠️ Gemini initialization failed: {e}")
                self.gemini_client = None

        # OpenRouter client setup (secondary)
        if config.OPENROUTER_API_KEY:
            self.openrouter_client = openai.OpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=config.OPENROUTER_API_KEY,
                default_headers={
                    "HTTP-Referer": "https://telegram-summarizer.com",
                    "X-Title": "Telegram Summarizer Bot"
                }
            )
            logger.info("✅ OpenRouter client initialized")

        # Optional Groq fallback
        if config.ENABLE_GROQ_FALLBACK and config.GROQ_API_KEY:
            self.groq_client = Groq(api_key=config.GROQ_API_KEY)
            logger.info("✅ Groq fallback client initialized")
    
    def get_llm_client_and_model(self) -> Tuple[Any, str]:
        """
        Get the appropriate LLM client and model
        Returns: (client, model_name, provider)
        """
        # Primary: Google Gemini (free and fast)
        if config.USE_GEMINI_PRIMARY and self.gemini_client:
            self.current_provider = 'gemini'
            return self.gemini_client, config.GEMINI_MODEL, 'gemini'

        # Secondary: OpenRouter with free models
        if config.USE_OPENROUTER_PRIMARY and self.openrouter_client and config.OPENROUTER_PRIMARY_MODEL:
            self.current_provider = 'openrouter'
            return self.openrouter_client, config.OPENROUTER_PRIMARY_MODEL, 'openrouter'

        if self.openrouter_client and config.OPENROUTER_SECONDARY_MODEL:
            self.current_provider = 'openrouter'
            return self.openrouter_client, config.OPENROUTER_SECONDARY_MODEL, 'openrouter'

        # Tertiary fallback: Groq
        if config.ENABLE_GROQ_FALLBACK and self.groq_client and config.GROQ_LLM_MODEL:
            self.current_provider = 'groq'
            return self.groq_client, config.GROQ_LLM_MODEL, 'groq'

        raise ValueError("Нет доступных LLM провайдеров. Проверьте конфигурацию.")
    
    def _handle_rate_limit(self, error) -> bool:
        """Handle rate limiting with retry logic"""
        if "429" in str(error) or "rate" in str(error).lower():
            self.retry_count += 1
            if self.retry_count < self.max_retries:
                wait_time = min(2 ** self.retry_count, 60)  # Exponential backoff, max 60s
                logger.warning(f"Rate limited. Retrying in {wait_time}s (attempt {self.retry_count})")
                time.sleep(wait_time)
                return True
        return False
    
    def _switch_to_fallback(self) -> Tuple[Any, str, str]:
        """Switch to fallback provider"""
        logger.info("🔄 Switching to fallback provider")

        # If Gemini failed, try OpenRouter
        if self.current_provider == 'gemini':
            if self.openrouter_client and config.OPENROUTER_PRIMARY_MODEL:
                self.current_provider = 'openrouter'
                return self.openrouter_client, config.OPENROUTER_PRIMARY_MODEL, 'openrouter'

        # If primary OpenRouter failed, try secondary
        if self.current_provider == 'openrouter' and self.current_model == config.OPENROUTER_PRIMARY_MODEL:
            if self.openrouter_client and config.OPENROUTER_SECONDARY_MODEL:
                return self.openrouter_client, config.OPENROUTER_SECONDARY_MODEL, 'openrouter'

        # If OpenRouter failed, try Groq
        if self.current_provider in ['gemini', 'openrouter']:
            if config.ENABLE_GROQ_FALLBACK and self.groq_client and config.GROQ_LLM_MODEL:
                self.current_provider = 'groq'
                return self.groq_client, config.GROQ_LLM_MODEL, 'groq'

        raise ValueError("Все провайдеры недоступны")
    
    def generate_completion(self,
                          prompt: str,
                          system: Optional[str] = None,
                          temperature: float = 0.2,
                          max_tokens: int = 2000) -> str:
        """
        Generate completion using available providers with fallback

        Args:
            prompt: User prompt
            system: System message (optional)
            temperature: Temperature for generation
            max_tokens: Maximum tokens to generate

        Returns:
            Generated text completion
        """
        self.retry_count = 0

        while self.retry_count < self.max_retries:
            try:
                client, model, provider = self.get_llm_client_and_model()
                self.current_model = model

                logger.info(f"🤖 Using {provider}: {model} (attempt {self.retry_count + 1})")

                # Generate completion based on provider
                if provider == 'gemini':
                    # Gemini API format
                    full_prompt = prompt
                    if system:
                        full_prompt = f"{system}\n\n{prompt}"

                    generation_config = {
                        "temperature": temperature,
                        "max_output_tokens": max_tokens,
                    }

                    response = client.generate_content(
                        full_prompt,
                        generation_config=generation_config
                    )
                    result = response.text

                else:
                    # OpenAI-compatible API (OpenRouter, Groq)
                    messages = []
                    if system:
                        messages.append({"role": "system", "content": system})
                    messages.append({"role": "user", "content": prompt})

                    response = client.chat.completions.create(
                        model=model,
                        messages=messages,
                        temperature=temperature,
                        max_tokens=max_tokens
                    )
                    result = response.choices[0].message.content

                logger.info(f"✅ Successfully generated completion using {provider}/{model}")
                return result

            except Exception as e:
                error_str = str(e)
                logger.error(f"❌ Error with {self.current_provider}/{self.current_model}: {error_str}")

                # Handle rate limiting
                if self._handle_rate_limit(e):
                    continue

                # Try fallback provider
                try:
                    client, model, provider = self._switch_to_fallback()
                    self.current_model = model

                    logger.info(f"🔄 Trying fallback: {provider}/{model}")

                    # Generate with fallback
                    if provider == 'gemini':
                        full_prompt = prompt
                        if system:
                            full_prompt = f"{system}\n\n{prompt}"

                        generation_config = {
                            "temperature": temperature,
                            "max_output_tokens": max_tokens,
                        }

                        response = client.generate_content(
                            full_prompt,
                            generation_config=generation_config
                        )
                        result = response.text
                    else:
                        messages = []
                        if system:
                            messages.append({"role": "system", "content": system})
                        messages.append({"role": "user", "content": prompt})

                        response = client.chat.completions.create(
                            model=model,
                            messages=messages,
                            temperature=temperature,
                            max_tokens=max_tokens
                        )
                        result = response.choices[0].message.content

                    logger.info(f"✅ Successfully generated completion using fallback {provider}/{model}")
                    return result

                except Exception as fallback_error:
                    logger.error(f"❌ Fallback also failed: {fallback_error}")
                    break

        raise Exception(f"Все провайдеры недоступны после {self.max_retries} попыток. Попробуйте позже.")


    def analyze_image(self,
                     image_data: bytes,
                     prompt: str,
                     temperature: float = 0.3,
                     max_tokens: int = 2000) -> str:
        """
        Analyze image using Gemini Vision or fallback to OCR + text analysis

        Args:
            image_data: Binary image data
            prompt: Analysis prompt
            temperature: Temperature for generation
            max_tokens: Maximum tokens to generate

        Returns:
            Analysis result text
        """
        # Try Gemini Vision first
        if GEMINI_AVAILABLE and self.gemini_client:
            try:
                logger.info("🖼️ Analyzing image with Gemini Vision")

                # Gemini Vision requires PIL Image
                from PIL import Image
                import io

                image = Image.open(io.BytesIO(image_data))

                generation_config = {
                    "temperature": temperature,
                    "max_output_tokens": max_tokens,
                }

                response = self.gemini_client.generate_content(
                    [prompt, image],
                    generation_config=generation_config
                )

                result = response.text
                logger.info("✅ Successfully analyzed image with Gemini Vision")
                return result

            except Exception as e:
                logger.warning(f"⚠️ Gemini Vision failed: {e}, falling back to OCR")

        # Fallback: Use OCR + text analysis
        raise NotImplementedError("OCR fallback should be handled by the caller")


# Global instance
llm_router = LLMProviderRouter()

def generate_completion(prompt: str,
                       system: Optional[str] = None,
                       temperature: float = 0.2,
                       max_tokens: int = 2000) -> str:
    """Convenience function for generating completions"""
    return llm_router.generate_completion(prompt, system, temperature, max_tokens)


def analyze_image(image_data: bytes,
                 prompt: str,
                 temperature: float = 0.3,
                 max_tokens: int = 2000) -> str:
    """Convenience function for analyzing images"""
    return llm_router.analyze_image(image_data, prompt, temperature, max_tokens)