"""
Persistent answer cache to avoid reprocessing identical questions.
Stores question-answer pairs with timestamps and metadata.

Matching strategy (hybrid):
  1. Exact hash match (fast path) — after normalization + stop word removal
  2. Similarity fallback — if no exact match, compare token overlap with
     all cached entries. If the best match exceeds a threshold, return it.
"""

import json
import hashlib
import logging
import re
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List, Tuple

logger = logging.getLogger(__name__)


def _tokenize(text: str) -> set:
    """Tokenize Chinese + English text into a set of meaningful tokens.

    Uses jieba for Chinese word segmentation (if available), falls back to
    character-level retrieval for pure CJK strings.
    """
    # Try jieba for proper Chinese word segmentation
    try:
        import jieba
        jieba.setLogLevel(jieba.logging.ERROR)
    except ImportError:
        jieba = None
    except AttributeError:
        jieba = None

    # Normalize
    text = text.lower().strip()
    text = re.sub(r'[^\w一-鿿]', ' ', text)  # keep letters, digits, CJK
    text = re.sub(r'\s+', ' ', text).strip()

    if not text:
        return set()

    # Extract CJK and Latin tokens separately
    cjk_part = ''.join(c for c in text if '一' <= c <= '鿿')
    latin_part = ' '.join(w for w in text.split() if not all('一' <= c <= '鿿' for c in w))

    tokens = set()

    # Latin tokens: split by whitespace
    if latin_part.strip():
        tokens.update(latin_part.split())

    # CJK tokens: use jieba, or fall back to bigrams
    if cjk_part:
        if jieba:
            tokens.update(w.strip() for w in jieba.cut(cjk_part) if w.strip())
        else:
            # Fallback: 2-4 character shingles
            for n in (2, 3, 4):
                for i in range(len(cjk_part) - n + 1):
                    tokens.add(cjk_part[i:i + n])
            # Also include the full string if short enough
            if len(cjk_part) <= 6:
                tokens.add(cjk_part)

    # Remove very short tokens (noise)
    tokens = {t for t in tokens if len(t) >= 2}
    return tokens


# Common Chinese question words and auxiliary words — safe to strip for matching
_CHINESE_STOP_WORDS = frozenset({
    '怎么样', '怎么', '什么', '如何', '哪些', '哪个', '谁', '哪里', '何时',
    '为什么', '是否', '有没有', '是不是', '能不能', '会不会', '要不要',
    '的', '了', '在', '是', '有', '和', '与', '或', '就', '都', '也',
    '很', '太', '非常', '比较', '可以', '需要', '能够', '应该', '必须',
    '吗', '呢', '啊', '吧', '呀', '哦',
    '请问', '请教', '回答', '解释', '说明', '给出',
    'what', 'which', 'who', 'where', 'when', 'why', 'how',
    'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been',
    'do', 'does', 'did', 'will', 'would', 'could', 'should',
    'in', 'on', 'at', 'to', 'for', 'of', 'by', 'with', 'from',
})


def _normalize_tokens(text: str) -> set:
    """Tokenize and remove stop words."""
    tokens = _tokenize(text)
    return tokens - _CHINESE_STOP_WORDS


def _similarity(query: str, cached: str) -> float:
    """Compute token overlap coefficient (Jaccard-like) between two questions.

    Returns 0.0–1.0. A score of >= 0.5 indicates the same question.
    """
    q_tokens = _normalize_tokens(query)
    c_tokens = _normalize_tokens(cached)

    if not q_tokens or not c_tokens:
        return 0.0

    intersection = q_tokens & c_tokens
    union = q_tokens | c_tokens

    # Jaccard similarity
    jaccard = len(intersection) / len(union) if union else 0.0

    # Query coverage: how much of the query tokens are in the cached tokens
    coverage = len(intersection) / len(q_tokens) if q_tokens else 0.0

    # Combined score (both must be good)
    return (jaccard * 0.5 + coverage * 0.5)


_SIMILARITY_THRESHOLD = 0.4  # minimum score to consider a match


class CachedAnswer:
    """Represents a single cached answer entry."""

    def __init__(self, question: str, answer: str, timestamp: str = None):
        self.question = question
        self.answer = answer
        self.timestamp = timestamp or datetime.now().isoformat()

    @staticmethod
    def _hash_question(question: str) -> str:
        """Create a normalized hash of the question for exact matching.

        Normalization:
        1. Lowercase + strip whitespace
        2. Remove punctuation (keep letters, digits, CJK chars)
        3. Collapse multiple spaces
        4. Remove English and Chinese stop words
        5. Sort unique tokens
        """
        tokens = _normalize_tokens(question)
        if not tokens:
            return hashlib.md5(question.lower().encode()).hexdigest()
        normalized = ' '.join(sorted(tokens))
        return hashlib.md5(normalized.encode()).hexdigest()

    def to_dict(self) -> Dict:
        """Serialize to dictionary."""
        return {
            "question": self.question,
            "answer": self.answer,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "CachedAnswer":
        """Deserialize from dictionary."""
        return cls(
            question=data.get("question", ""),
            answer=data.get("answer", ""),
            timestamp=data.get("timestamp")
        )


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

        Uses hybrid matching strategy:
        1. Fast path: exact hash match (normalized, stop words removed)
        2. Fallback: token similarity with all cached entries

        Args:
            question: User question to look up

        Returns:
            Cached answer string if found and valid, None otherwise
        """
        # ---- Step 1: Fast path — exact hash match ----
        question_hash = CachedAnswer._hash_question(question)

        for cached in self.cache:
            if CachedAnswer._hash_question(cached.question) == question_hash:
                if self._is_cache_valid(cached):
                    return cached.answer
                else:
                    self.cache.remove(cached)
                    self.save_cache()
                    return None

        # ---- Step 2: Fallback — token similarity ----
        # Only use the normalized tokens once
        best_match: Optional[Tuple[float, int]] = None  # (score, index)
        for idx, cached in enumerate(self.cache):
            if not self._is_cache_valid(cached):
                continue
            score = _similarity(question, cached.question)
            if score >= _SIMILARITY_THRESHOLD:
                if best_match is None or score > best_match[0]:
                    best_match = (score, idx)

        if best_match is not None:
            logger.info(
                "Fuzzy cache hit (score=%.2f): '%s' ≈ '%s'",
                best_match[0],
                question[:50],
                self.cache[best_match[1]].question[:50],
            )
            return self.cache[best_match[1]].answer

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
            if CachedAnswer._hash_question(cached.question) == question_hash:
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
        print(f"\n缓存统计：")
        print(f"  总条目：{stats['total_entries']}")
        print(f"  有效条目：{stats['valid_entries']}")
        print(f"  过期条目：{stats['expired_entries']}")
        
        if self.cache:
            print(f"\n📝 Recent cached questions:")
            for cached in self.cache[-5:]:  # Show last 5
                age = (datetime.now() - datetime.fromisoformat(cached.timestamp)).days
                status = "有效" if self._is_cache_valid(cached) else "⚠ 已过期"
                print(f"  [{status}, {age}天前] {cached.question[:70]}...")
    
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
