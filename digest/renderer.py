"""
Digest rendering in HTML/MarkdownV2 format
"""

import logging
import os
from typing import List, Dict, Optional, Tuple
from datetime import datetime
import html

logger = logging.getLogger(__name__)

# Get limits from environment
MAX_ITEMS = int(os.getenv('DIGEST_MAX_ITEMS', '15'))
HOURLY_MAX_ITEMS = int(os.getenv('DIGEST_HOURLY_MAX_ITEMS', '8'))

class DigestRenderer:
    def __init__(self):
        self.max_items = MAX_ITEMS
        self.hourly_max_items = HOURLY_MAX_ITEMS
    
    def render_digest(self, 
                     clusters: List[Dict], 
                     trends: Optional[Dict] = None,
                     period: str = 'daily',
                     from_ts: int = 0,
                     to_ts: int = 0) -> Tuple[str, bool]:
        """
        Render complete digest
        Returns (rendered_text, has_more_items)
        """
        try:
            # Determine item limit
            max_items = self.hourly_max_items if period == 'hourly' else self.max_items
            
            # Build digest sections
            sections = []
            
            # Header
            header = self._render_header(period, from_ts, to_ts, len(clusters))
            sections.append(header)
            
            # Main content
            if clusters:
                main_section = self._render_main_content(clusters[:max_items])
                sections.append(main_section)
                
                # Channel breakdown (only for non-hourly)
                if period != 'hourly' and len(clusters) > 3:
                    channel_section = self._render_channels_section(clusters[:max_items])
                    if channel_section:
                        sections.append(channel_section)
            else:
                sections.append("📭 <b>No new messages in this period</b>")
            
            # Key numbers section
            if clusters:
                numbers_section = self._render_key_numbers(clusters[:max_items])
                if numbers_section:
                    sections.append(numbers_section)
            
            # Trends section (only for daily/weekly/monthly)
            if trends and period != 'hourly':
                trends_section = self._render_trends_section(trends)
                if trends_section:
                    sections.append(trends_section)
            
            # Footer with pagination info
            has_more = len(clusters) > max_items
            if has_more:
                footer = f"\n<i>... and {len(clusters) - max_items} more items</i>"
                sections.append(footer)
            
            rendered = '\n\n'.join(sections)
            
            # Ensure message doesn't exceed Telegram limits
            if len(rendered) > 4000:
                rendered = self._truncate_message(rendered)
            
            return rendered, has_more
            
        except Exception as e:
            logger.error(f"Error rendering digest: {e}")
            return f"❌ Error generating digest: {e}", False
    
    def _render_header(self, period: str, from_ts: int, to_ts: int, total_items: int) -> str:
        """Render digest header"""
        try:
            # Period emoji mapping
            period_emojis = {
                'hourly': '⏰',
                'daily': '📅',
                'weekly': '📈',
                'monthly': '📊',
                'custom': '🔍'
            }
            
            emoji = period_emojis.get(period, '📋')
            period_name = period.title()
            
            # Format time range
            if from_ts and to_ts:
                from_dt = datetime.fromtimestamp(from_ts)
                to_dt = datetime.fromtimestamp(to_ts)
                
                if period == 'hourly':
                    time_str = from_dt.strftime('%H:%M') + ' - ' + to_dt.strftime('%H:%M')
                elif period == 'daily':
                    time_str = from_dt.strftime('%d.%m.%Y')
                else:
                    time_str = from_dt.strftime('%d.%m') + ' - ' + to_dt.strftime('%d.%m.%Y')
            else:
                time_str = datetime.now().strftime('%d.%m.%Y %H:%M')
            
            header = f"{emoji} <b>{period_name} Digest</b>"
            
            if time_str:
                header += f"\n🕐 <i>{time_str}</i>"
            
            if total_items > 0:
                header += f"\n📊 <i>{total_items} items total</i>"
            
            return header
            
        except Exception as e:
            logger.error(f"Error rendering header: {e}")
            return f"{period.title()} Digest"
    
    def _render_main_content(self, clusters: List[Dict]) -> str:
        """Render main content section"""
        try:
            if not clusters:
                return ""
            
            content_lines = ["🔥 <b>Main Topics</b>"]
            
            for i, cluster in enumerate(clusters, 1):
                item = self._render_cluster_item(cluster, i)
                content_lines.append(item)
            
            return '\n\n'.join(content_lines)
            
        except Exception as e:
            logger.error(f"Error rendering main content: {e}")
            return "❌ Error rendering content"
    
    def _render_cluster_item(self, cluster: Dict, index: int) -> str:
        """Render individual cluster item"""
        try:
            text = cluster.get('text', '')
            cluster_size = cluster.get('cluster_size', 1)
            channels = cluster.get('cluster_channels', [])
            message_url = cluster.get('message_url', '')
            
            # Create summary (first 200 chars or use existing summary)
            summary = self._create_item_summary(text)
            
            # Build item
            item_lines = [f"<b>{index}.</b> {summary}"]
            
            # Add source info
            source_info = []
            if channels:
                channel_names = [self._format_channel_name(ch) for ch in channels[:2]]
                source_info.append(f"📢 {', '.join(channel_names)}")
                
                if len(channels) > 2:
                    source_info.append(f"and {len(channels) - 2} more")
            
            if cluster_size > 1:
                source_info.append(f"📊 {cluster_size} messages")
            
            if source_info:
                item_lines.append(f"<i>{' • '.join(source_info)}</i>")
            
            # Add link if available
            if message_url:
                item_lines.append(f"🔗 <a href='{message_url}'>Read more</a>")
            
            return '\n'.join(item_lines)
            
        except Exception as e:
            logger.error(f"Error rendering cluster item: {e}")
            return f"{index}. Error rendering item"
    
    def _render_channels_section(self, clusters: List[Dict]) -> str:
        """Render channels activity section"""
        try:
            # Count activity by channel
            channel_activity = {}
            
            for cluster in clusters:
                channels = cluster.get('cluster_channels', [])
                for channel in channels:
                    if channel not in channel_activity:
                        channel_activity[channel] = 0
                    channel_activity[channel] += 1
            
            if not channel_activity:
                return ""
            
            # Sort by activity
            sorted_channels = sorted(
                channel_activity.items(), 
                key=lambda x: x[1], 
                reverse=True
            )[:5]  # Top 5 channels
            
            lines = ["📢 <b>Most Active Channels</b>"]
            
            for channel, count in sorted_channels:
                channel_name = self._format_channel_name(channel)
                lines.append(f"• {channel_name} — {count} items")
            
            return '\n'.join(lines)
            
        except Exception as e:
            logger.error(f"Error rendering channels section: {e}")
            return ""
    
    def _render_key_numbers(self, clusters: List[Dict]) -> str:
        """Render key numbers section"""
        try:
            numbers = []
            
            # Extract numbers from cluster texts
            for cluster in clusters:
                text = cluster.get('text', '')
                extracted = self._extract_important_numbers(text)
                numbers.extend(extracted)
            
            if not numbers:
                return ""
            
            # Take top numbers
            unique_numbers = list(set(numbers))[:5]
            
            lines = ["💎 <b>Key Numbers</b>"]
            
            for number in unique_numbers:
                lines.append(f"• {number}")
            
            return '\n'.join(lines)
            
        except Exception as e:
            logger.error(f"Error rendering key numbers: {e}")
            return ""
    
    def _render_trends_section(self, trends: Dict) -> str:
        """Render trends section"""
        try:
            if not trends or not trends.get('top_keywords'):
                return ""
            
            lines = ["📈 <b>Trending Topics</b>"]
            
            keywords = trends.get('top_keywords', [])[:5]
            for keyword in keywords:
                kw_text = keyword.get('keyword', '')
                relevance = keyword.get('relevance', 0)
                
                # Simple relevance indicator
                stars = '⭐' * min(3, int(relevance * 3))
                lines.append(f"• {kw_text} {stars}")
            
            return '\n'.join(lines)
            
        except Exception as e:
            logger.error(f"Error rendering trends: {e}")
            return ""
    
    def _create_item_summary(self, text: str, max_length: int = 150) -> str:
        """Create summary for digest item"""
        try:
            if not text:
                return "No content"
            
            # Clean text
            text = text.strip()
            
            # If short enough, return as is
            if len(text) <= max_length:
                return html.escape(text)
            
            # Try to cut at sentence boundary
            sentences = text.split('.')
            if len(sentences) > 1 and len(sentences[0]) <= max_length:
                return html.escape(sentences[0].strip()) + '.'
            
            # Cut at word boundary
            words = text.split()
            summary = []
            length = 0
            
            for word in words:
                if length + len(word) + 1 > max_length:
                    break
                summary.append(word)
                length += len(word) + 1
            
            if summary:
                return html.escape(' '.join(summary)) + '...'
            else:
                return html.escape(text[:max_length]) + '...'
            
        except Exception as e:
            logger.error(f"Error creating summary: {e}")
            return "Error creating summary"
    
    def _format_channel_name(self, channel: str) -> str:
        """Format channel name for display"""
        try:
            if not channel:
                return "Unknown"
            
            # If it's a username, keep @
            if channel.startswith('@'):
                return channel
            
            # If it's a username without @, add it
            if len(channel) < 50 and ' ' not in channel:
                return f"@{channel}"
            
            # Otherwise, it's probably a title - truncate if needed
            if len(channel) > 30:
                return channel[:27] + '...'
            
            return channel
            
        except Exception as e:
            logger.error(f"Error formatting channel name: {e}")
            return "Unknown"
    
    def _extract_important_numbers(self, text: str) -> List[str]:
        """Extract important numbers from text"""
        try:
            import re
            
            numbers = []
            
            # Money amounts
            money_patterns = [
                r'\d+[.,]?\d*\s*(?:руб|рубл|доллар|евро|₽|\$|€)',
                r'[\$€₽]\s*\d+[.,]?\d*'
            ]
            
            for pattern in money_patterns:
                matches = re.findall(pattern, text, re.IGNORECASE)
                numbers.extend(matches)
            
            # Percentages
            percentages = re.findall(r'\d+[.,]?\d*%', text)
            numbers.extend(percentages)
            
            # Large numbers
            large_numbers = re.findall(r'\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?(?:\s*(?:млн|млрд|тыс|тысяч|миллион|миллиард))', text, re.IGNORECASE)
            numbers.extend(large_numbers)
            
            return numbers[:3]  # Return top 3
            
        except Exception as e:
            logger.error(f"Error extracting numbers: {e}")
            return []
    
    def _truncate_message(self, message: str, max_length: int = 4000) -> str:
        """Truncate message to fit Telegram limits"""
        try:
            if len(message) <= max_length:
                return message
            
            # Try to cut at last complete section
            sections = message.split('\n\n')
            truncated_sections = []
            current_length = 0
            
            for section in sections:
                if current_length + len(section) + 2 > max_length - 100:  # Leave room for footer
                    break
                truncated_sections.append(section)
                current_length += len(section) + 2
            
            if truncated_sections:
                result = '\n\n'.join(truncated_sections)
                result += '\n\n<i>... (truncated due to length)</i>'
                return result
            else:
                # Fallback: just cut the string
                return message[:max_length-50] + '\n\n<i>... (truncated)</i>'
            
        except Exception as e:
            logger.error(f"Error truncating message: {e}")
            return message[:max_length]

# Global instance
_digest_renderer = None

def get_digest_renderer() -> DigestRenderer:
    """Get global digest renderer instance"""
    global _digest_renderer
    if _digest_renderer is None:
        _digest_renderer = DigestRenderer()
    return _digest_renderer

def render_digest(clusters: List[Dict], trends: Optional[Dict] = None, 
                 period: str = 'daily', from_ts: int = 0, to_ts: int = 0) -> Tuple[str, bool]:
    """Convenient function to render digest"""
    renderer = get_digest_renderer()
    return renderer.render_digest(clusters, trends, period, from_ts, to_ts)