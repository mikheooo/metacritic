import hashlib
import re


def normalize_transcript_text(text: str) -> str:
    """
    Deterministic transcript normalization:
    1. Normalize whitespace (tabs, newlines, multiple spaces).
    2. Remove obvious subtitle repetition artifacts.
    3. Retain exact casing and punctuation.
    """
    if not text:
        return ""

    # Replace newlines and tabs with single spaces
    normalized = re.sub(r"[\r\n\t]+", " ", text)
    # Collapse multiple spaces
    normalized = re.sub(r"\s{2,}", " ", normalized).strip()

    # Remove immediate duplicate word blocks common in auto-captions
    # e.g. "hello world hello world" -> "hello world"
    words = normalized.split(" ")
    deduped_words: list[str] = []
    i = 0
    while i < len(words):
        # Look for 3-5 word repeating phrases
        found_repeat = False
        for phrase_len in (5, 4, 3):
            if i + 2 * phrase_len <= len(words):
                chunk1 = words[i : i + phrase_len]
                chunk2 = words[i + phrase_len : i + 2 * phrase_len]
                if [w.lower() for w in chunk1] == [w.lower() for w in chunk2]:
                    deduped_words.extend(chunk1)
                    i += 2 * phrase_len
                    found_repeat = True
                    break
        if not found_repeat:
            deduped_words.append(words[i])
            i += 1

    return " ".join(deduped_words)


def compute_transcript_hash(normalized_text: str) -> str:
    """Compute SHA-256 hash of normalized transcript text."""
    return hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()


def compute_youtube_summary_fingerprint(
    transcript_hash: str,
    provider: str,
    model: str,
    prompt_version: str,
    summary_language: str,
) -> str:
    """
    Compute deterministic SHA-256 fingerprint for AI video summary generation.
    Any change in transcript, LLM provider, model, prompt version, or language
    invalidates the fingerprint and requires regeneration.
    """
    payload = ":".join(
        [
            transcript_hash,
            provider.strip().lower(),
            model.strip().lower(),
            prompt_version.strip(),
            summary_language.strip().lower(),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
