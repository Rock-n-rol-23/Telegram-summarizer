"""
Deduplication using RapidFuzz for fast similarity detection
"""

import logging
from typing import List, Dict, Set, Tuple
from rapidfuzz import fuzz
import os

logger = logging.getLogger(__name__)

# Get threshold from environment
DUP_THRESHOLD = int(os.getenv('DIGEST_DUP_SIM_THRESHOLD', '85'))

def calculate_similarity(text1: str, text2: str) -> float:
    """Calculate similarity between two texts using RapidFuzz"""
    if not text1 or not text2:
        return 0.0
    
    # Use token_set_ratio for better handling of word order differences
    return fuzz.token_set_ratio(text1, text2)

def find_duplicates(messages: List[Dict], threshold: float = DUP_THRESHOLD) -> List[Set[int]]:
    """
    Find duplicate messages using RapidFuzz similarity
    Returns list of sets, each set contains indices of duplicate messages
    """
    if not messages:
        return []
    
    duplicate_groups = []
    used_indices = set()
    
    for i, msg1 in enumerate(messages):
        if i in used_indices:
            continue
            
        text1 = msg1.get('text', '').strip()
        if not text1 or len(text1) < 10:  # Skip very short texts
            continue
        
        current_group = {i}
        
        # Compare with remaining messages
        for j, msg2 in enumerate(messages[i+1:], i+1):
            if j in used_indices:
                continue
                
            text2 = msg2.get('text', '').strip()
            if not text2:
                continue
            
            similarity = calculate_similarity(text1, text2)
            
            if similarity >= threshold:
                current_group.add(j)
                used_indices.add(j)
        
        if len(current_group) > 1:
            duplicate_groups.append(current_group)
            used_indices.update(current_group)
    
    return duplicate_groups

def deduplicate_messages(messages: List[Dict]) -> Tuple[List[Dict], List[List[Dict]]]:
    """
    Remove duplicates from messages, return unique messages and duplicate groups
    """
    if not messages:
        return [], []
    
    logger.info(f"Deduplicating {len(messages)} messages with threshold {DUP_THRESHOLD}")
    
    # Find duplicate groups
    duplicate_groups = find_duplicates(messages, DUP_THRESHOLD)
    
    unique_messages = []
    merged_groups = []
    used_indices = set()
    
    # Process duplicate groups
    for group_indices in duplicate_groups:
        group_messages = [messages[i] for i in group_indices]
        
        # Choose the best representative (longest text, earliest timestamp)
        best_msg = max(group_messages, 
                      key=lambda m: (len(m.get('text', '')), -m.get('posted_at', 0)))
        
        unique_messages.append(best_msg)
        merged_groups.append(group_messages)
        used_indices.update(group_indices)
    
    # Add non-duplicate messages
    for i, msg in enumerate(messages):
        if i not in used_indices:
            unique_messages.append(msg)
    
    logger.info(f"After deduplication: {len(unique_messages)} unique messages, "
               f"{len(duplicate_groups)} merged groups")
    
    return unique_messages, merged_groups

def merge_similar_texts(texts: List[str], threshold: float = DUP_THRESHOLD) -> List[Tuple[str, List[int]]]:
    """
    Merge similar texts, return representative text and indices of merged texts
    """
    if not texts:
        return []
    
    groups = []
    used_indices = set()
    
    for i, text1 in enumerate(texts):
        if i in used_indices or not text1.strip():
            continue
            
        current_indices = [i]
        
        for j, text2 in enumerate(texts[i+1:], i+1):
            if j in used_indices or not text2.strip():
                continue
                
            similarity = calculate_similarity(text1, text2)
            if similarity >= threshold:
                current_indices.append(j)
                used_indices.add(j)
        
        if current_indices:
            # Choose longest text as representative
            best_idx = max(current_indices, key=lambda idx: len(texts[idx]))
            groups.append((texts[best_idx], current_indices))
            used_indices.update(current_indices)
    
    # Add remaining texts
    for i, text in enumerate(texts):
        if i not in used_indices and text.strip():
            groups.append((text, [i]))
    
    return groups

def quick_duplicate_check(new_text: str, existing_texts: List[str], threshold: float = DUP_THRESHOLD) -> bool:
    """
    Quick check if new text is duplicate of any existing text
    """
    if not new_text.strip():
        return False
    
    for existing in existing_texts:
        if not existing.strip():
            continue
            
        similarity = calculate_similarity(new_text, existing)
        if similarity >= threshold:
            return True
    
    return False