#!/usr/bin/env python3
"""
Enhanced message handling with async support and chunking
"""

import asyncio
import logging
from typing import List, Dict, Any, Optional
from utils.telegram import split_message, format_summary_message, format_error_message
from utils.network import RateLimitError, SSRFError

logger = logging.getLogger(__name__)

class MessageHandler:
    """Handles message processing with rate limiting and chunking"""
    
    def __init__(self, bot_instance):
        self.bot = bot_instance
    
    async def send_long_message(self, chat_id: int, text: str, parse_mode: str = None) -> List[int]:
        """
        Send long message split into chunks
        
        Args:
            chat_id: Telegram chat ID
            text: Message text to send
            parse_mode: Telegram parse mode (HTML, Markdown, etc.)
            
        Returns:
            List of sent message IDs
        """
        chunks = split_message(text)
        message_ids = []
        
        for i, chunk in enumerate(chunks):
            try:
                if i > 0:
                    # Add delay between chunks to avoid rate limiting
                    await asyncio.sleep(0.5)
                
                # Add chunk indicator for multi-part messages
                if len(chunks) > 1:
                    chunk_info = f"\n\n📄 Часть {i+1}/{len(chunks)}"
                    chunk += chunk_info
                
                message_id = await self.bot.send_message(chat_id, chunk, parse_mode=parse_mode)
                if message_id:
                    message_ids.append(message_id)
                    
            except Exception as e:
                logger.error(f"Error sending message chunk {i+1}: {e}")
                break
                
        return message_ids
    
    async def handle_url_processing(self, chat_id: int, user_id: int, urls: List[str], 
                                  compression_level: float = 0.3) -> bool:
        """
        Process URLs with error handling and user feedback
        
        Args:
            chat_id: Telegram chat ID
            user_id: User ID for rate limiting
            urls: List of URLs to process
            compression_level: Summary compression level
            
        Returns:
            True if processing successful, False otherwise
        """
        processing_message_id = None
        
        try:
            # Send processing message
            processing_message_id = await self.bot.send_message(
                chat_id, 
                f"🔄 Обрабатываю {len(urls)} ссылок...\nЭто может занять некоторое время."
            )
            
            summaries = []
            
            for i, url in enumerate(urls):
                try:
                    # Update progress
                    if len(urls) > 1:
                        await self.bot.edit_message_text(
                            chat_id, 
                            processing_message_id,
                            f"🔄 Обрабатываю ссылку {i+1}/{len(urls)}...\n{url[:50]}..."
                        )
                    
                    # Check if URL is allowed
                    if not self.bot.is_url_allowed(url):
                        summaries.append({
                            'url': url,
                            'error': 'Данный тип сайта не поддерживается'
                        })
                        continue
                    
                    # Extract content
                    result = await self.bot.extract_webpage_content(url, user_id=user_id)
                    
                    if result.get('success'):
                        # Summarize content
                        content = result['content']
                        title = result['title']
                        
                        summary_result = self.bot.summarize_text(
                            content, 
                            compression_level=compression_level
                        )
                        
                        if summary_result.get('success'):
                            summaries.append({
                                'url': url,
                                'title': title,
                                'summary': summary_result['summary'],
                                'compression': summary_result.get('compression_ratio', 0)
                            })
                        else:
                            summaries.append({
                                'url': url,
                                'title': title,
                                'error': 'Ошибка суммаризации'
                            })
                    else:
                        # Handle specific error types
                        error_msg = result.get('error', 'Неизвестная ошибка')
                        if result.get('ssrf_blocked'):
                            error_msg = "🛡️ Безопасность: URL заблокирован"
                        elif result.get('rate_limited'):
                            error_msg = "⏰ Превышен лимит запросов"
                        elif result.get('blocked'):
                            error_msg = f"🚫 {error_msg}"
                        
                        summaries.append({
                            'url': url,
                            'error': error_msg
                        })
                        
                except Exception as e:
                    logger.error(f"Error processing URL {url}: {e}")
                    summaries.append({
                        'url': url,
                        'error': f'Ошибка обработки: {str(e)[:100]}'
                    })
            
            # Delete processing message
            if processing_message_id:
                await self.bot.delete_message(chat_id, processing_message_id)
            
            # Format and send results
            await self._send_url_results(chat_id, summaries)
            return True
            
        except RateLimitError:
            if processing_message_id:
                await self.bot.delete_message(chat_id, processing_message_id)
            await self.bot.send_message(
                chat_id,
                format_error_message("rate_limit", "Превышен лимит запросов. Попробуйте позже.")
            )
            return False
            
        except Exception as e:
            logger.error(f"Error in URL processing: {e}")
            if processing_message_id:
                await self.bot.delete_message(chat_id, processing_message_id)
            await self.bot.send_message(
                chat_id,
                format_error_message("processing", f"Ошибка обработки: {str(e)[:100]}")
            )
            return False
    
    async def _send_url_results(self, chat_id: int, summaries: List[Dict[str, Any]]) -> None:
        """Send formatted URL processing results"""
        result_text = "📄 **Результаты обработки ссылок:**\n\n"
        
        for i, item in enumerate(summaries, 1):
            result_text += f"**{i}. {item.get('title', 'Без названия')}**\n"
            result_text += f"🔗 {item['url'][:50]}...\n"
            
            if 'error' in item:
                result_text += f"❌ {item['error']}\n\n"
            else:
                summary = item['summary']
                compression = item.get('compression', 0)
                
                result_text += f"📝 {summary}\n"
                result_text += f"📊 Сжатие: {compression:.1%}\n\n"
        
        await self.send_long_message(chat_id, result_text)
    
    async def handle_text_processing(self, chat_id: int, user_id: int, text: str,
                                   compression_level: float = 0.3) -> bool:
        """
        Process text with progress feedback
        
        Args:
            chat_id: Telegram chat ID
            user_id: User ID for rate limiting
            text: Text to process
            compression_level: Summary compression level
            
        Returns:
            True if processing successful, False otherwise
        """
        processing_message_id = None
        
        try:
            # Send processing message
            processing_message_id = await self.bot.send_message(
                chat_id, 
                "🔄 Анализирую текст и создаю резюме..."
            )
            
            # Process text
            result = self.bot.summarize_text(text, compression_level=compression_level)
            
            # Delete processing message
            if processing_message_id:
                await self.bot.delete_message(chat_id, processing_message_id)
            
            if result.get('success'):
                # Format response with statistics
                summary = result['summary']
                compression = result.get('compression_ratio', 0)
                processing_time = result.get('processing_time', 0)
                
                response_text = format_summary_message(
                    summary, compression, processing_time, "текста"
                )
                
                await self.send_long_message(chat_id, response_text)
                return True
            else:
                error_msg = result.get('error', 'Неизвестная ошибка')
                await self.bot.send_message(
                    chat_id,
                    format_error_message("processing", error_msg)
                )
                return False
                
        except Exception as e:
            logger.error(f"Error in text processing: {e}")
            if processing_message_id:
                await self.bot.delete_message(chat_id, processing_message_id)
            await self.bot.send_message(
                chat_id,
                format_error_message("processing", f"Ошибка обработки: {str(e)[:100]}")
            )
            return False