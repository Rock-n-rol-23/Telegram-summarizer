"""
LLM Provider Router - Manages multiple LLM providers with fallback support
Supports OpenRouter (primary/secondary free routes) and optional Groq fallback
"""

import logging
import time
from typing import Optional, Tuple, Dict, Any
import openai
from groq import Groq
from config import config

logger = logging.getLogger(__name__)

class LLMProviderRouter:
    """Routes LLM requests through multiple providers with fallback support"""
    
    def __init__(self):
        self.openrouter_client = None
        self.groq_client = None
        self.current_model = None
        self.retry_count = 0
        self.max_retries = 2
        
        self._initialize_clients()
    
    def _initialize_clients(self):
        """Initialize available LLM clients"""
        # OpenRouter client setup
        if config.OPENROUTER_API_KEY:
            self.openrouter_client = openai.OpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=config.OPENROUTER_API_KEY,
                default_headers={
                    "HTTP-Referer": "https://telegram-summarizer.com",
                    "X-Title": "Telegram Summarizer Bot"
                }
            )
            logger.info("OpenRouter client initialized")
        
        # Optional Groq fallback
        if config.ENABLE_GROQ_FALLBACK and config.GROQ_API_KEY:
            self.groq_client = Groq(api_key=config.GROQ_API_KEY)
            logger.info("Groq fallback client initialized")
    
    def get_llm_client_and_model(self) -> Tuple[Any, str]:
        """
        Get the appropriate LLM client and model
        Returns: (client, model_name)
        """
        # Primary: OpenRouter with primary free model
        if (config.USE_OPENROUTER_PRIMARY and 
            self.openrouter_client and 
            config.OPENROUTER_PRIMARY_MODEL):
            return self.openrouter_client, config.OPENROUTER_PRIMARY_MODEL
        
        # Secondary: OpenRouter with secondary free model
        if (self.openrouter_client and 
            config.OPENROUTER_SECONDARY_MODEL):
            return self.openrouter_client, config.OPENROUTER_SECONDARY_MODEL
        
        # Optional fallback: Groq
        if (config.ENABLE_GROQ_FALLBACK and 
            self.groq_client and 
            config.GROQ_LLM_MODEL):
            return self.groq_client, config.GROQ_LLM_MODEL
        
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
    
    def _switch_to_fallback(self) -> Tuple[Any, str]:
        """Switch to fallback provider"""
        logger.info("Switching to fallback provider")
        
        # If we were using primary OpenRouter, try secondary
        if self.current_model == config.OPENROUTER_PRIMARY_MODEL:
            if self.openrouter_client and config.OPENROUTER_SECONDARY_MODEL:
                return self.openrouter_client, config.OPENROUTER_SECONDARY_MODEL
        
        # If secondary OpenRouter failed or we were using it, try Groq
        if (config.ENABLE_GROQ_FALLBACK and 
            self.groq_client and 
            config.GROQ_LLM_MODEL):
            return self.groq_client, config.GROQ_LLM_MODEL
        
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
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        
        self.retry_count = 0
        
        while self.retry_count < self.max_retries:
            try:
                client, model = self.get_llm_client_and_model()
                self.current_model = model
                
                logger.info(f"Using model: {model} (attempt {self.retry_count + 1})")
                
                # Generate completion
                response = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens
                )
                
                result = response.choices[0].message.content
                logger.info(f"Successfully generated completion using {model}")
                return result
                
            except Exception as e:
                error_str = str(e)
                logger.error(f"Error with {self.current_model}: {error_str}")
                
                # Handle rate limiting
                if self._handle_rate_limit(e):
                    continue
                
                # Try fallback provider
                try:
                    client, model = self._switch_to_fallback()
                    self.current_model = model
                    
                    logger.info(f"Trying fallback: {model}")
                    
                    response = client.chat.completions.create(
                        model=model,
                        messages=messages,
                        temperature=temperature,
                        max_tokens=max_tokens
                    )
                    
                    result = response.choices[0].message.content
                    logger.info(f"Successfully generated completion using fallback {model}")
                    return result
                    
                except Exception as fallback_error:
                    logger.error(f"Fallback also failed: {fallback_error}")
                    break
        
        raise Exception(f"Все провайдеры недоступны после {self.max_retries} попыток. Попробуйте позже.")


# Global instance
llm_router = LLMProviderRouter()

def generate_completion(prompt: str, 
                       system: Optional[str] = None,
                       temperature: float = 0.2,
                       max_tokens: int = 2000) -> str:
    """Convenience function for generating completions"""
    return llm_router.generate_completion(prompt, system, temperature, max_tokens)