"""
Persistent answer cache to avoid reprocessing identical questions.
Stores question-answer pairs with timestamps and metadata.
"""

import json
import hashlib
import logging
import re
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List

logger = logging.getLogger(__name__)


class CachedAnswer:
    """Represents a single cached answer entry."""
    
    def __init__(self, question: str, answer: str, timestamp: str = None):
        self.question = question
        self.answer = answer
        self.timestamp = timestamp or datetime.now().isoformat()
        self.question_hash = self._hash_question(question)
    
    # English stop words commonly used in questions — safe to strip for matching
    _STOP_WORDS = frozenset({
        'a', 'an', 'the', 'is', 'are', 'was', 'were', 'be', 'been',
        'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might',
        'what', 'which', 'who', 'whom', 'whose', 'why', 'how',
        'where', 'when', 'in', 'on', 'at', 'to', 'for', 'of', 'by', 'with',
        'from', 'about', 'into', 'through', 'during', 'before', 'after',
        'and', 'or', 'but', 'not', 'no', 'if', 'so',
    })

    @staticmethod
    def _hash_question(question: str) -> str:
        """Create a normalized hash of the question for matching.

        Normalization pipeline:
        1. Lowercase + strip whitespace
        2. Remove punctuation (keep letters, digits, spaces)
        3. Collapse multiple spaces → single space
        4. Remove common English stop words
        5. Strip & rejoin sorted unique words (so word order doesn't matter)
        """
        normalized = question.lower().strip()
        # Remove punctuation: keep a-z, 0-9, whitespace
        normalized = re.sub(r'[^\w\s]', ' ', normalized)
        # Collapse whitespace
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        # Tokenize and remove stop words
        tokens = [w for w in normalized.split() if w not in CachedAnswer._STOP_WORDS]
        # If after removing stop words we have nothing, fall back to raw tokens
        if not tokens:
            tokens = normalized.split()
        # Sort uniquely — "what is BERT" ≡ "BERT what is"
        normalized = ' '.join(sorted(set(tokens)))
        return hashlib.md5(normalized.encode()).hexdigest()
    
    def to_dict(self) -> Dict:
        """Serialize to dictionary."""
        return {
            "question": self.question,
            "answer": self.answer,
            "timestamp": self.timestamp,
            "question_hash": self.question_hash
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "CachedAnswer":
        """Deserialize from dictionary."""
        obj = cls(
            question=data.get("question", ""),
            answer=data.get("answer", ""),
            timestamp=data.get("timestamp")
        )
        return obj


class AnswerCache:
    """
    Manages persistent caching of LLM answers.
    
    Features:
    - Auto-loads existing cache on initialization
    - Auto-saves after adding new answers
    - Efficient question matching using hashing
    - Timestamp tracking for cache invalidation
    - Cache statistics
    """
    
    def __init__(self, cache_file: str = "cache/answer_cache.json", ttl_days: int = 30):
        """
        Initialize the answer cache.
        
        Args:
            cache_file: Path to JSON file storing cached answers
            ttl_days: Time-to-live for cached answers in days (0 = no expiry)
        """
        self.cache_file = Path(cache_file)
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        self.ttl_days = ttl_days
        self.cache: List[CachedAnswer] = []
        self.load_cache()
    
    def load_cache(self) -> None:
        """Load cache from JSON file."""
        if not self.cache_file.exists():
            self.cache = []
            return
        
        try:
            with open(self.cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.cache = [CachedAnswer.from_dict(item) for item in data.get("answers", [])]
            logger.info("Loaded %d cached answers from %s", len(self.cache), self.cache_file)
        except Exception as e:
            logger.warning("Failed to load cache: %s. Starting with empty cache.", e)
            self.cache = []
    
    def save_cache(self) -> None:
        """Save cache to JSON file."""
        try:
            data = {"answers": [item.to_dict() for item in self.cache]}
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error("Failed to save cache: %s", e)
    
    def _is_cache_valid(self, cached_answer: CachedAnswer) -> bool:
        """Check if a cached answer is still valid (not expired)."""
        if self.ttl_days == 0:
            return True  # No expiry
        
        try:
            cached_time = datetime.fromisoformat(cached_answer.timestamp)
            age_days = (datetime.now() - cached_time).days
            return age_days < self.ttl_days
        except Exception:
            return True  # If timestamp parsing fails, assume valid
    
    def get_answer(self, question: str) -> Optional[str]:
        """
        Retrieve a cached answer for the given question.
        
        Args:
            question: User question to look up
            
        Returns:
            Cached answer string if found and valid, None otherwise
        """
        question_hash = CachedAnswer._hash_question(question)
        
        for cached in self.cache:
            if cached.question_hash == question_hash:
                if self._is_cache_valid(cached):
                    return cached.answer
                else:
                    # Remove expired cache entry
                    self.cache.remove(cached)
                    self.save_cache()
                    return None
        
        return None
    
    def save_answer(self, question: str, answer: str) -> None:
        """
        Save an answer to the cache.
        
        Args:
            question: User question
            answer: LLM answer
        """
        # Check if this question already exists
        question_hash = CachedAnswer._hash_question(question)
        for i, cached in enumerate(self.cache):
            if cached.question_hash == question_hash:
                # Update existing entry
                self.cache[i] = CachedAnswer(question, answer)
                self.save_cache()
                logger.info("Updated cached answer for: %s...", question[:60])
                return
        
        # Add new entry
        self.cache.append(CachedAnswer(question, answer))
        self.save_cache()
        logger.info("Cached answer for: %s...", question[:60])
    
    def clear_cache(self) -> None:
        """Clear all cached answers."""
        self.cache = []
        if self.cache_file.exists():
            self.cache_file.unlink()
        logger.info("Cache cleared.")
    
    def get_stats(self) -> Dict:
        """Get cache statistics."""
        valid_count = sum(1 for c in self.cache if self._is_cache_valid(c))
        expired_count = len(self.cache) - valid_count
        
        return {
            "total_entries": len(self.cache),
            "valid_entries": valid_count,
            "expired_entries": expired_count,
            "cache_file": str(self.cache_file)
        }
    
    def display_cache(self) -> None:
        """Display cache statistics and recent entries."""
        stats = self.get_stats()
        print(f"\nCache Statistics:")
        print(f"  Total entries: {stats['total_entries']}")
        print(f"  Valid entries: {stats['valid_entries']}")
        print(f"  Expired entries: {stats['expired_entries']}")
        
        if self.cache:
            print(f"\n📝 Recent cached questions:")
            for cached in self.cache[-5:]:  # Show last 5
                age = (datetime.now() - datetime.fromisoformat(cached.timestamp)).days
                status = "Valid" if self._is_cache_valid(cached) else "⚠ Expired"
                print(f"  [{status}, {age} days ago] {cached.question[:70]}...")
    
    def __len__(self) -> int:
        """Return number of valid cached entries."""
        return sum(1 for c in self.cache if self._is_cache_valid(c))
    
    def cleanup_expired(self) -> None:
        """Remove all expired entries from cache."""
        original_count = len(self.cache)
        self.cache = [c for c in self.cache if self._is_cache_valid(c)]
        removed = original_count - len(self.cache)
        if removed > 0:
            self.save_cache()
            logger.info("Cleaned up %d expired cache entries.", removed)
        else:
            logger.info("No expired cache entries to clean up.")
