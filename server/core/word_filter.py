import re
from pathlib import Path
import logging

logger = logging.getLogger("WordFilter")

class WordFilter:
    def __init__(self, blocked_words_file="blocked_words.txt"):
        self.blocked_words = set()
        self.file_path = Path(blocked_words_file)
        if not self.file_path.is_absolute():
            # Assume it's relative to the project root or server dir
            # For simplicity, let's look in the same dir as this file if it's not found
            self.file_path = Path(__file__).parent.parent / blocked_words_file
            
        self.load_words()

    def load_words(self):
        """Loads blocked words from the text file."""
        if not self.file_path.exists():
            logger.warning(f"Blocked words file not found at {self.file_path}. Filter will be empty.")
            return

        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                for line in f:
                    word = line.strip().lower()
                    if word:
                        self.blocked_words.add(word)
            logger.info(f"Loaded {len(self.blocked_words)} blocked words.")
        except Exception as e:
            logger.error(f"Error loading blocked words: {e}")

    def contains_profanity(self, text: str) -> bool:
        """Returns True if text contains any of the blocked words."""
        if not text:
            return False
        
        lowered = text.lower()
        for word in self.blocked_words:
            # Use regex for whole-word matching to avoid false positives (e.g. "lan" in "alan")
            pattern = rf"\b{re.escape(word)}\b"
            if re.search(pattern, lowered, flags=re.IGNORECASE):
                return True
        return False

    def censor_text(self, text: str, placeholder="***") -> str:
        """Replaces blocked words in the text with a placeholder."""
        if not text:
            return text
            
        censored = text
        # Sort words by length descending to avoid partial replacement of longer words first
        sorted_words = sorted(list(self.blocked_words), key=len, reverse=True)
        
        for word in sorted_words:
            pattern = rf"\b{re.escape(word)}\b"
            censored = re.sub(pattern, placeholder, censored, flags=re.IGNORECASE)
            
        return censored
