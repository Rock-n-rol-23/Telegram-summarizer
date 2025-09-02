"""
Trends analysis using YAKE keyword extraction
"""

import logging
from typing import List, Dict, Tuple, Optional
from collections import Counter, defaultdict
import yake
from datetime import datetime, timedelta
from .preprocess import detect_language, clean_text
from .db import get_digest_db

logger = logging.getLogger(__name__)

class TrendsAnalyzer:
    def __init__(self):
        self.db = get_digest_db()
    
    def analyze_period_trends(self, messages: List[Dict], period: str = 'daily') -> Dict:
        """
        Analyze trends for a period of messages
        Returns trend analysis with top keywords, channels, dynamics
        """
        try:
            if not messages:
                return self._empty_trends()
            
            # Combine all text for language detection
            all_text = ' '.join([msg.get('text', '') for msg in messages])
            lang = detect_language(all_text)
            
            # Extract keywords using YAKE
            top_keywords = self._extract_yake_keywords(all_text, lang)
            
            # Analyze channels activity
            channel_stats = self._analyze_channel_activity(messages)
            
            # Calculate basic dynamics (if we have historical data)
            dynamics = self._calculate_dynamics(messages, period)
            
            # Get trending topics
            topics = self._extract_trending_topics(messages, lang)
            
            result = {
                'period': period,
                'total_messages': len(messages),
                'top_keywords': top_keywords,
                'channel_stats': channel_stats,
                'dynamics': dynamics,
                'trending_topics': topics,
                'language': lang,
                'time_range': self._get_time_range(messages)
            }
            
            logger.info(f"Analyzed trends for {len(messages)} messages, "
                       f"found {len(top_keywords)} keywords")
            
            return result
            
        except Exception as e:
            logger.error(f"Error analyzing trends: {e}")
            return self._empty_trends()
    
    def _extract_yake_keywords(self, text: str, lang: str = 'ru', max_keywords: int = 10) -> List[Dict]:
        """Extract keywords using YAKE algorithm"""
        try:
            if not text.strip():
                return []
            
            # Configure YAKE parameters
            yake_lang = 'ru' if lang == 'ru' else 'en'
            
            kw_extractor = yake.KeywordExtractor(
                lan=yake_lang,
                n=3,  # Maximum number of words in keyphrase
                dedupLim=0.7,  # Deduplication threshold
                top=max_keywords * 2,  # Extract more to filter later
                features=None
            )
            
            # Clean text for better extraction
            cleaned_text = clean_text(text)
            
            # Extract keywords
            keywords = kw_extractor.extract_keywords(cleaned_text)
            
            # Format results (lower score = better in YAKE)
            formatted_keywords = []
            for score, keyword in keywords[:max_keywords]:
                formatted_keywords.append({
                    'keyword': keyword,
                    'score': score,
                    'relevance': 1 / (1 + score)  # Convert to relevance (higher = better)
                })
            
            return formatted_keywords
            
        except Exception as e:
            logger.warning(f"YAKE extraction failed: {e}")
            return self._fallback_keyword_extraction(text, max_keywords)
    
    def _fallback_keyword_extraction(self, text: str, max_keywords: int = 10) -> List[Dict]:
        """Fallback keyword extraction using simple frequency"""
        try:
            words = clean_text(text).lower().split()
            
            # Filter out short words and common words
            filtered_words = [w for w in words if len(w) > 3]
            
            # Count frequency
            word_counts = Counter(filtered_words)
            
            # Get top words
            top_words = word_counts.most_common(max_keywords)
            
            # Format as keywords
            keywords = []
            total_words = len(filtered_words)
            
            for word, count in top_words:
                keywords.append({
                    'keyword': word,
                    'score': count / total_words,
                    'relevance': count / total_words
                })
            
            return keywords
            
        except Exception as e:
            logger.error(f"Fallback keyword extraction failed: {e}")
            return []
    
    def _analyze_channel_activity(self, messages: List[Dict]) -> List[Dict]:
        """Analyze channel activity statistics"""
        try:
            channel_stats = defaultdict(lambda: {
                'message_count': 0,
                'total_length': 0,
                'avg_length': 0,
                'title': '',
                'username': ''
            })
            
            for msg in messages:
                channel_key = msg.get('username') or msg.get('title', 'Unknown')
                stats = channel_stats[channel_key]
                
                stats['message_count'] += 1
                text_length = len(msg.get('text', ''))
                stats['total_length'] += text_length
                stats['title'] = msg.get('title', '')
                stats['username'] = msg.get('username', '')
            
            # Calculate averages and sort by activity
            for stats in channel_stats.values():
                if stats['message_count'] > 0:
                    stats['avg_length'] = stats['total_length'] / stats['message_count']
            
            # Convert to sorted list
            sorted_channels = sorted(
                [
                    {
                        'channel': channel,
                        **stats
                    }
                    for channel, stats in channel_stats.items()
                ],
                key=lambda x: x['message_count'],
                reverse=True
            )
            
            return sorted_channels[:10]  # Top 10 channels
            
        except Exception as e:
            logger.error(f"Error analyzing channel activity: {e}")
            return []
    
    def _calculate_dynamics(self, messages: List[Dict], period: str) -> Dict:
        """Calculate dynamics compared to previous period (simplified)"""
        try:
            if not messages:
                return {}
            
            # For now, just return basic stats
            # In a full implementation, we'd compare with previous period data
            
            total_messages = len(messages)
            total_chars = sum(len(msg.get('text', '')) for msg in messages)
            avg_message_length = total_chars / total_messages if total_messages > 0 else 0
            
            # Time distribution
            time_distribution = self._analyze_time_distribution(messages)
            
            return {
                'total_messages': total_messages,
                'avg_message_length': avg_message_length,
                'time_distribution': time_distribution,
                'growth_rate': 0,  # Would calculate from historical data
                'activity_trend': 'stable'  # Would determine from comparison
            }
            
        except Exception as e:
            logger.error(f"Error calculating dynamics: {e}")
            return {}
    
    def _analyze_time_distribution(self, messages: List[Dict]) -> Dict:
        """Analyze message distribution over time"""
        try:
            hourly_distribution = defaultdict(int)
            
            for msg in messages:
                timestamp = msg.get('posted_at', 0)
                if timestamp > 0:
                    dt = datetime.fromtimestamp(timestamp)
                    hour = dt.hour
                    hourly_distribution[hour] += 1
            
            return dict(hourly_distribution)
            
        except Exception as e:
            logger.error(f"Error analyzing time distribution: {e}")
            return {}
    
    def _extract_trending_topics(self, messages: List[Dict], lang: str) -> List[Dict]:
        """Extract trending topics from messages"""
        try:
            # Group messages by similarity and extract topics
            topic_keywords = {}
            
            # Use clustering or similar approach to group related messages
            # For now, use a simplified approach
            
            all_keywords = []
            for msg in messages:
                text = msg.get('text', '')
                if text:
                    keywords = self._extract_yake_keywords(text, lang, max_keywords=5)
                    all_keywords.extend([kw['keyword'] for kw in keywords])
            
            # Count keyword frequency across all messages
            keyword_counts = Counter(all_keywords)
            
            # Create topics from top keywords
            topics = []
            for keyword, count in keyword_counts.most_common(5):
                topics.append({
                    'topic': keyword,
                    'frequency': count,
                    'relevance': count / len(messages) if messages else 0
                })
            
            return topics
            
        except Exception as e:
            logger.error(f"Error extracting trending topics: {e}")
            return []
    
    def _get_time_range(self, messages: List[Dict]) -> Dict:
        """Get time range of messages"""
        try:
            if not messages:
                return {}
            
            timestamps = [msg.get('posted_at', 0) for msg in messages if msg.get('posted_at', 0) > 0]
            
            if not timestamps:
                return {}
            
            min_time = min(timestamps)
            max_time = max(timestamps)
            
            return {
                'start': min_time,
                'end': max_time,
                'duration_hours': (max_time - min_time) / 3600
            }
            
        except Exception as e:
            logger.error(f"Error getting time range: {e}")
            return {}
    
    def _empty_trends(self) -> Dict:
        """Return empty trends structure"""
        return {
            'period': 'unknown',
            'total_messages': 0,
            'top_keywords': [],
            'channel_stats': [],
            'dynamics': {},
            'trending_topics': [],
            'language': 'ru',
            'time_range': {}
        }
    
    def get_weekly_trends(self, user_id: int) -> Dict:
        """Get trends for the past week"""
        try:
            # Calculate time range (last 7 days)
            end_time = int(datetime.now().timestamp())
            start_time = end_time - (7 * 24 * 3600)  # 7 days ago
            
            # Get messages from user's channels
            messages = self.db.get_messages_in_period(user_id, start_time, end_time)
            
            return self.analyze_period_trends(messages, 'weekly')
            
        except Exception as e:
            logger.error(f"Error getting weekly trends: {e}")
            return self._empty_trends()
    
    def get_monthly_trends(self, user_id: int) -> Dict:
        """Get trends for the past month"""
        try:
            # Calculate time range (last 30 days)
            end_time = int(datetime.now().timestamp())
            start_time = end_time - (30 * 24 * 3600)  # 30 days ago
            
            # Get messages from user's channels
            messages = self.db.get_messages_in_period(user_id, start_time, end_time)
            
            return self.analyze_period_trends(messages, 'monthly')
            
        except Exception as e:
            logger.error(f"Error getting monthly trends: {e}")
            return self._empty_trends()

# Global instance
_trends_analyzer = None

def get_trends_analyzer() -> TrendsAnalyzer:
    """Get global trends analyzer instance"""
    global _trends_analyzer
    if _trends_analyzer is None:
        _trends_analyzer = TrendsAnalyzer()
    return _trends_analyzer

def analyze_trends_for_period(messages: List[Dict], period: str = 'daily') -> Dict:
    """Convenient function to analyze trends"""
    analyzer = get_trends_analyzer()
    return analyzer.analyze_period_trends(messages, period)