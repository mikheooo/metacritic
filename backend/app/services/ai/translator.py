import asyncio
import logging
import re
from typing import Protocol

from openai import AsyncOpenAI

from app.core.config import settings

logger = logging.getLogger(__name__)


def is_already_russian(text: str) -> bool:
    """
    Check if text is predominantly Russian (Cyrillic).
    Prevents redundant LLM translation calls if content is already localized.
    """
    if not text:
        return False
    # Find all alphabetic characters (both Latin and Cyrillic)
    letters = re.findall(r"[a-zA-Z\u0400-\u04FF]", text)
    if not letters:
        return False
    cyrillic = re.findall(r"[\u0400-\u04FF]", text)
    return (len(cyrillic) / len(letters)) >= 0.5


def _build_system_prompt(context_type: str = "description") -> str:
    item_label = (
        "game descriptions" if context_type == "description" else "player and critic reviews"
    )
    return f"""You are an expert video game localization specialist and professional translator.
Your mission is to translate video game text ({item_label}) from English into natural, fluent Russian.

TRANSLATION GUIDELINES AND INTEGRITY RULES:
1. Translate accurately into natural, contemporary Russian with proper gaming terminology.
2. Do NOT shorten, summarize, truncate, or omit any details from the original text.
3. Do NOT add fabricated facts, extra commentary, or personal opinions.
4. STRICTLY PRESERVE proper names, game titles, developer and publisher names, platform names (e.g. 'Elden Ring', 'PlayStation 5', 'FromSoftware', 'Valve', 'Xbox Series X/S'), Metascores, Userscores, URLs, and technical identifiers.
5. If the source text is already in Russian, return it unchanged.
6. Output ONLY the Russian translation. Do NOT output code fences, markdown blocks, notes, or explanatory prefixes."""


class ContentTranslator(Protocol):
    """Protocol for video game content translation services."""

    provider: str
    model: str

    async def translate_text(
        self,
        text: str,
        context_type: str = "description",
    ) -> str: ...


class OpenRouterTranslator:
    """Production translator leveraging OpenRouter / OpenAI endpoint with gpt-4o-mini."""

    def __init__(
        self,
        provider: str = "openrouter",
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = 45.0,
    ) -> None:
        self.provider = provider
        self.api_key = api_key or settings.OPENROUTER_API_KEY
        if not self.api_key or not self.api_key.strip():
            raise ValueError(
                f"API key must be provided and non-empty for {self.__class__.__name__}."
            )
        self.base_url = base_url or settings.OPENROUTER_BASE_URL
        self.model = model or settings.LLM_MODEL
        self.timeout = timeout
        self.client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=self.timeout,
        )

    async def translate_text(
        self,
        text: str,
        context_type: str = "description",
    ) -> str:
        if not text or not text.strip():
            return ""

        if is_already_russian(text):
            logger.info("Source text is already predominantly Russian, skipping LLM translation.")
            return text.strip()

        system_prompt = _build_system_prompt(context_type)
        user_prompt = f"Please translate the following gaming {context_type} into natural Russian:\n\n{text.strip()}"

        max_retries = 3
        backoff = 2.0
        last_error: Exception | None = None

        for attempt in range(1, max_retries + 1):
            try:
                completion = await self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.3,
                )
                raw_text = completion.choices[0].message.content or ""
                cleaned = raw_text.strip()
                if cleaned.startswith("```") and cleaned.endswith("```"):
                    lines = cleaned.split("\n")
                    if len(lines) >= 3:
                        cleaned = "\n".join(lines[1:-1]).strip()
                return cleaned

            except Exception as exc:
                last_error = exc
                logger.warning(
                    "Translation call failed (attempt %d/%d): %s",
                    attempt,
                    max_retries,
                    exc,
                )
                if attempt < max_retries:
                    await asyncio.sleep(backoff * attempt)

        raise RuntimeError(
            f"Translation failed after {max_retries} attempts: {last_error}"
        ) from last_error


class OpenAITranslator(OpenRouterTranslator):
    """Direct OpenAI API translator implementation."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = 45.0,
    ) -> None:
        super().__init__(
            provider="openai",
            api_key=api_key or settings.OPENAI_API_KEY,
            base_url=base_url or settings.OPENAI_BASE_URL,
            model=model or settings.LLM_MODEL,
            timeout=timeout,
        )


class FakeTranslator:
    """Mock translator for automated tests and deterministic local development."""

    def __init__(self, provider: str = "fake", model: str = "fake-model") -> None:
        self.provider = provider
        self.model = model
        self.call_count = 0
        self.last_text: str | None = None
        self.last_context_type: str | None = None

    async def translate_text(
        self,
        text: str,
        context_type: str = "description",
    ) -> str:
        self.call_count += 1
        self.last_text = text
        self.last_context_type = context_type

        if not text or not text.strip():
            return ""

        if is_already_russian(text):
            return text.strip()

        # Deterministic Russian mock translation
        return f"[Перевод на русский] {text.strip()}"


def get_translator() -> ContentTranslator:
    """Factory to retrieve configured content translator."""
    provider = (settings.LLM_PROVIDER or "openrouter").strip().lower()
    if provider == "openrouter":
        if not settings.OPENROUTER_API_KEY or not settings.OPENROUTER_API_KEY.strip():
            raise ValueError(
                "LLM_PROVIDER is configured as 'openrouter', but OPENROUTER_API_KEY is missing or empty."
            )
        return OpenRouterTranslator()
    elif provider == "openai":
        if not settings.OPENAI_API_KEY or not settings.OPENAI_API_KEY.strip():
            raise ValueError(
                "LLM_PROVIDER is configured as 'openai', but OPENAI_API_KEY is missing or empty."
            )
        return OpenAITranslator()
    elif provider == "fake":
        return FakeTranslator()
    else:
        raise ValueError(
            f"Unsupported LLM_PROVIDER '{settings.LLM_PROVIDER}'. Supported: 'openrouter', 'openai', 'fake'."
        )
