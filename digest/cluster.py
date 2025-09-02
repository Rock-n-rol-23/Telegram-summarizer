"""
Clustering messages using TF-IDF and cosine similarity
"""

import logging
import os
from typing import List, Dict, Tuple, Optional
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.cluster import DBSCAN
from .preprocess import prepare_for_clustering, detect_language

logger = logging.getLogger(__name__)

# Get clustering threshold from environment
CLUSTER_THRESHOLD = float(os.getenv('DIGEST_MIN_CLUSTER_SIM', '0.62'))

class MessageClusterer:
    def __init__(self, similarity_threshold: float = CLUSTER_THRESHOLD):
        self.similarity_threshold = similarity_threshold
        self.vectorizer = None
        
    def _create_vectorizer(self, lang: str = 'ru') -> TfidfVectorizer:
        """Create TF-IDF vectorizer for given language"""
        # Language-specific stop words will be handled in preprocessing
        return TfidfVectorizer(
            max_features=1000,
            ngram_range=(1, 2),  # unigrams and bigrams
            min_df=1,  # minimum document frequency
            max_df=0.8,  # maximum document frequency
            sublinear_tf=True,  # apply sublinear tf scaling
            norm='l2'  # l2 normalization
        )
    
    def cluster_messages(self, messages: List[Dict]) -> List[List[Dict]]:
        """
        Cluster messages by content similarity
        Returns list of clusters, each cluster is a list of messages
        """
        if not messages:
            return []
        
        if len(messages) == 1:
            return [messages]
        
        logger.info(f"Clustering {len(messages)} messages with threshold {self.similarity_threshold}")
        
        # Detect primary language
        all_text = ' '.join([msg.get('text', '') for msg in messages])
        lang = detect_language(all_text)
        
        # Prepare texts for vectorization
        prepared_texts = prepare_for_clustering(messages, lang)
        
        # Filter out empty texts and their corresponding messages
        valid_pairs = [(text, msg) for text, msg in zip(prepared_texts, messages) if text.strip()]
        
        if not valid_pairs:
            return [messages]  # Return all as one cluster if no valid text
        
        valid_texts, valid_messages = zip(*valid_pairs)
        
        # Create TF-IDF vectors
        self.vectorizer = self._create_vectorizer(lang)
        
        try:
            tfidf_matrix = self.vectorizer.fit_transform(valid_texts)
            
            if tfidf_matrix.shape[0] == 1:
                return [list(valid_messages)]
            
            # Use DBSCAN clustering with cosine distance
            # Convert similarity threshold to distance threshold
            eps = 1 - self.similarity_threshold
            
            # Calculate pairwise cosine similarities
            similarity_matrix = cosine_similarity(tfidf_matrix)
            
            # Convert to distance matrix
            distance_matrix = 1 - similarity_matrix
            
            # Apply DBSCAN clustering
            dbscan = DBSCAN(
                eps=eps,
                min_samples=1,  # Allow single-message clusters
                metric='precomputed'
            )
            
            cluster_labels = dbscan.fit_predict(distance_matrix)
            
            # Group messages by cluster labels
            clusters = {}
            for i, label in enumerate(cluster_labels):
                if label not in clusters:
                    clusters[label] = []
                clusters[label].append(valid_messages[i])
            
            # Convert to list and sort by cluster size (descending)
            result_clusters = sorted(clusters.values(), key=len, reverse=True)
            
            logger.info(f"Created {len(result_clusters)} clusters")
            return result_clusters
            
        except Exception as e:
            logger.warning(f"Clustering failed: {e}, returning all messages as single cluster")
            return [messages]
    
    def find_cluster_representatives(self, cluster: List[Dict]) -> Dict:
        """Find the best representative message for a cluster"""
        if not cluster:
            return {}
        
        if len(cluster) == 1:
            return cluster[0]
        
        # Score messages by length and recency
        scored_messages = []
        for msg in cluster:
            text_length = len(msg.get('text', ''))
            posted_at = msg.get('posted_at', 0)
            
            # Combined score: text length + recency bonus
            score = text_length + (posted_at / 1000000)  # Small recency bonus
            scored_messages.append((score, msg))
        
        # Return message with highest score
        return max(scored_messages, key=lambda x: x[0])[1]
    
    def cluster_and_summarize(self, messages: List[Dict]) -> List[Dict]:
        """
        Cluster messages and return cluster representatives with metadata
        """
        clusters = self.cluster_messages(messages)
        
        cluster_summaries = []
        for i, cluster in enumerate(clusters):
            representative = self.find_cluster_representatives(cluster)
            
            # Add cluster metadata
            representative['cluster_id'] = i
            representative['cluster_size'] = len(cluster)
            representative['cluster_messages'] = cluster
            
            # Collect all channels in cluster
            channels = set()
            for msg in cluster:
                if 'username' in msg:
                    channels.add(msg['username'])
                elif 'title' in msg:
                    channels.add(msg['title'])
            
            representative['cluster_channels'] = list(channels)
            
            cluster_summaries.append(representative)
        
        return cluster_summaries

def simple_clustering(messages: List[Dict], max_clusters: int = 10) -> List[List[Dict]]:
    """
    Simple clustering fallback using basic similarity
    """
    if not messages or len(messages) <= max_clusters:
        return [[msg] for msg in messages]
    
    clusterer = MessageClusterer()
    clusters = clusterer.cluster_messages(messages)
    
    # If too many clusters, merge smallest ones
    while len(clusters) > max_clusters:
        # Find two smallest clusters
        clusters.sort(key=len)
        merged = clusters[0] + clusters[1]
        clusters = [merged] + clusters[2:]
    
    return clusters

def calculate_cluster_similarity(cluster1: List[Dict], cluster2: List[Dict]) -> float:
    """Calculate similarity between two clusters"""
    if not cluster1 or not cluster2:
        return 0.0
    
    # Use representative messages for comparison
    clusterer = MessageClusterer()
    rep1 = clusterer.find_cluster_representatives(cluster1)
    rep2 = clusterer.find_cluster_representatives(cluster2)
    
    text1 = rep1.get('text', '')
    text2 = rep2.get('text', '')
    
    if not text1 or not text2:
        return 0.0
    
    # Use TF-IDF similarity
    try:
        vectorizer = TfidfVectorizer(max_features=500, ngram_range=(1, 2))
        tfidf_matrix = vectorizer.fit_transform([text1, text2])
        similarity = cosine_similarity(tfidf_matrix)[0][1]
        return similarity
    except:
        return 0.0