"""News sentiment analysis for trading signals."""

import asyncio
import feedparser
import aiohttp
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from textblob import TextBlob
import re

from ..core.logger import setup_logger


class NewsSentimentAnalyzer:
    """Analyze news sentiment for trading signals."""
    
    def __init__(
        self,
        news_feeds: Optional[List[str]] = None,
        lookback_hours: int = 24
    ):
        """
        Initialize news sentiment analyzer.
        
        Args:
            news_feeds: List of RSS feed URLs
            lookback_hours: Hours to look back for news
        """
        self.news_feeds = news_feeds or [
            "https://cointelegraph.com/rss",
            "https://www.coindesk.com/arc/outboundfeeds/rss/",
            "https://bitcoinmagazine.com/.rss/full/",
        ]
        self.lookback_hours = lookback_hours
        self.logger = setup_logger("NewsSentimentAnalyzer")
        self._cache: Dict[str, List[Dict]] = {}
        self._cache_time: Dict[str, datetime] = {}
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """
        Get or create aiohttp session for connection pooling.
        
        Returns:
            aiohttp.ClientSession instance
        """
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=30)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session
    
    async def close(self) -> None:
        """Close HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
    
    async def analyze_symbol_sentiment(self, symbol: str) -> Dict[str, float]:
        """
        Analyze sentiment for a symbol.
        
        Args:
            symbol: Trading pair symbol (e.g., BTCUSDT)
        
        Returns:
            Dict with sentiment scores
        """
        try:
            # Extract base asset (e.g., BTC from BTCUSDT)
            base_asset = symbol.replace("USDT", "").replace("USD", "")
            
            # Check cache
            cache_key = f"{base_asset}_{datetime.now().hour}"
            if cache_key in self._cache:
                cache_age = datetime.now() - self._cache_time.get(cache_key, datetime.now())
                if cache_age < timedelta(minutes=30):
                    return self._cache[cache_key]
            
            # Fetch and analyze news
            articles = await self._fetch_recent_news(base_asset)
            sentiment_scores = []
            
            for article in articles:
                text = f"{article.get('title', '')} {article.get('summary', '')}"
                sentiment = self._analyze_text_sentiment(text, base_asset)
                if sentiment is not None:
                    sentiment_scores.append(sentiment)
            
            if not sentiment_scores:
                return {
                    'sentiment': 0.0,
                    'confidence': 0.0,
                    'article_count': 0
                }
            
            # Calculate average sentiment
            avg_sentiment = sum(sentiment_scores) / len(sentiment_scores)
            confidence = min(1.0, len(sentiment_scores) / 10.0)  # More articles = higher confidence
            
            result = {
                'sentiment': avg_sentiment,
                'confidence': confidence,
                'article_count': len(sentiment_scores)
            }
            
            # Cache result
            self._cache[cache_key] = result
            self._cache_time[cache_key] = datetime.now()
            
            return result
        
        except Exception as e:
            self.logger.error(f"Error analyzing sentiment for {symbol}: {e}")
            return {
                'sentiment': 0.0,
                'confidence': 0.0,
                'article_count': 0
            }
    
    async def _fetch_recent_news(self, asset: str) -> List[Dict]:
        """Fetch recent news articles."""
        articles = []
        cutoff_time = datetime.now() - timedelta(hours=self.lookback_hours)
        
        for feed_url in self.news_feeds:
            try:
                feed = feedparser.parse(feed_url)
                
                for entry in feed.entries[:20]:  # Limit to recent 20 entries
                    published = self._parse_date(entry.get('published', ''))
                    if published and published >= cutoff_time:
                        # Check if article mentions the asset
                        text = f"{entry.get('title', '')} {entry.get('summary', '')}"
                        if asset.lower() in text.lower():
                            articles.append({
                                'title': entry.get('title', ''),
                                'summary': entry.get('summary', ''),
                                'published': published,
                                'link': entry.get('link', '')
                            })
            except Exception as e:
                self.logger.debug(f"Error fetching feed {feed_url}: {e}")
        
        return articles
    
    def _analyze_text_sentiment(self, text: str, asset: str) -> Optional[float]:
        """Analyze sentiment of text using TextBlob."""
        try:
            # Simple keyword-based sentiment (can be enhanced with ML)
            positive_keywords = ['bullish', 'surge', 'rally', 'gain', 'up', 'rise', 'breakout', 'moon']
            negative_keywords = ['bearish', 'crash', 'drop', 'fall', 'down', 'decline', 'dump', 'bear']
            
            text_lower = text.lower()
            positive_count = sum(1 for kw in positive_keywords if kw in text_lower)
            negative_count = sum(1 for kw in negative_keywords if kw in text_lower)
            
            # Use TextBlob for more nuanced sentiment
            blob = TextBlob(text)
            polarity = blob.sentiment.polarity
            
            # Combine keyword and TextBlob sentiment
            keyword_sentiment = (positive_count - negative_count) / max(positive_count + negative_count, 1)
            combined_sentiment = (polarity + keyword_sentiment) / 2
            
            return combined_sentiment
        
        except Exception as e:
            self.logger.debug(f"Error analyzing sentiment: {e}")
            return None
    
    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse date string to datetime."""
        try:
            # Try common date formats
            from email.utils import parsedate_to_datetime
            return parsedate_to_datetime(date_str)
        except:
            try:
                return datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
            except:
                return None
