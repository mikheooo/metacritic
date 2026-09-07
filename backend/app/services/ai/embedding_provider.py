import asyncio
import hashlib
import logging
import math
import struct
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from openai import AsyncOpenAI, InternalServerError, RateLimitError

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class EmbeddingResult:
    vector: list[float]
    provider: str
    model: str
    dimensions: int
    input_tokens: int | None = None


@runtime_checkable
class EmbeddingProvider(Protocol):
    provider: str
    model: str
    dimensions: int

    async def embed(self, text: str) -> EmbeddingResult:
        ...


class OpenRouterEmbeddingProvider:
    """Production embedding provider querying OpenRouter via OpenAI-compatible API."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://openrouter.ai/api/v1",
        model: str | None = None,
        dimensions: int | None = None,
        max_retries: int = 3,
    ) -> None:
        if not api_key or not api_key.strip():
            raise ValueError("OPENROUTER_API_KEY is missing or empty. Cannot initialize OpenRouterEmbeddingProvider.")

        self.api_key = api_key.strip()
        self.base_url = base_url.rstrip("/")
        self.provider = "openrouter"
        self.model = model or settings.EMBEDDING_MODEL
        self.dimensions = dimensions or settings.EMBEDDING_DIMENSIONS
        self.max_retries = max_retries

        self.client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
        )

    async def embed(self, text: str) -> EmbeddingResult:
        if not text or not text.strip():
            raise ValueError("Text input for embedding cannot be empty.")

        delay = 1.0
        last_exc: Exception | None = None

        for attempt in range(1, self.max_retries + 1):
            try:
                response = await self.client.embeddings.create(
                    input=text,
                    model=self.model,
                )
                if not response.data or len(response.data) == 0:
                    raise ValueError(f"Empty embedding data returned by {self.provider} ({self.model})")

                raw_vector = response.data[0].embedding
                input_tokens = getattr(response.usage, "prompt_tokens", None) or getattr(response.usage, "total_tokens", None)

                return EmbeddingResult(
                    vector=raw_vector,
                    provider=self.provider,
                    model=self.model,
                    dimensions=len(raw_vector),
                    input_tokens=input_tokens,
                )
            except (RateLimitError, InternalServerError) as exc:
                last_exc = exc
                logger.warning(
                    "Transient error calling %s embeddings (attempt %d/%d): %s. Backoff %0.1fs",
                    self.provider,
                    attempt,
                    self.max_retries,
                    exc,
                    delay,
                )
                if attempt < self.max_retries:
                    await asyncio.sleep(delay)
                    delay *= 2
            except Exception as exc:
                logger.error("Non-transient error from embedding provider %s: %s", self.provider, exc)
                raise

        raise RuntimeError(
            f"Failed to generate embedding from {self.provider} after {self.max_retries} attempts"
        ) from last_exc


class FakeEmbeddingProvider:
    """Hermetic deterministic embedding provider for testing and offline execution."""

    def __init__(
        self,
        dimensions: int = 1536,
        model: str = "fake-embedding",
        custom_vectors: dict[str, list[float]] | None = None,
    ) -> None:
        self.provider = "fake"
        self.model = model
        self.dimensions = dimensions
        self.call_count = 0
        self.custom_vectors = custom_vectors or {}

    async def embed(self, text: str) -> EmbeddingResult:
        self.call_count += 1

        # Check if caller provided explicit vector mapping for this text
        if text in self.custom_vectors:
            vec = self.custom_vectors[text]
            return EmbeddingResult(
                vector=vec,
                provider=self.provider,
                model=self.model,
                dimensions=len(vec),
                input_tokens=len(text.split()),
            )

        # Generate deterministic normalized pseudo-embedding from SHA-256 hash of text
        h = hashlib.sha256(text.encode("utf-8")).digest()
        # Seed pseudo-random stream with hash
        raw_vals: list[float] = []
        seed = struct.unpack(">Q", h[:8])[0]
        state = seed
        for _ in range(self.dimensions):
            state = (state * 6364136223846793005 + 1442695040888963407) & 0xFFFFFFFFFFFFFFFF
            # Map to float between -1.0 and 1.0
            val = (state / 0xFFFFFFFFFFFFFFFF) * 2.0 - 1.0
            raw_vals.append(val)

        # Normalize vector to unit length
        norm = math.sqrt(sum(x * x for x in raw_vals)) or 1.0
        norm_vector = [x / norm for x in raw_vals]

        return EmbeddingResult(
            vector=norm_vector,
            provider=self.provider,
            model=self.model,
            dimensions=self.dimensions,
            input_tokens=len(text.split()),
        )


def get_embedding_provider() -> EmbeddingProvider:
    """
    Factory creating the configured EmbeddingProvider based on application settings.
    Strictly forbids silent fallback to FakeEmbeddingProvider if production credentials are missing.
    """
    provider_name = settings.EMBEDDING_PROVIDER.lower().strip()

    if provider_name == "openrouter":
        if not settings.OPENROUTER_API_KEY or not settings.OPENROUTER_API_KEY.strip():
            raise ValueError(
                "EMBEDDING_PROVIDER is set to 'openrouter', but OPENROUTER_API_KEY is missing or empty. "
                "Explicit credentials are required in production mode (silent fake fallback is prohibited)."
            )
        return OpenRouterEmbeddingProvider(
            api_key=settings.OPENROUTER_API_KEY,
            base_url=settings.OPENROUTER_BASE_URL,
            model=settings.EMBEDDING_MODEL,
            dimensions=settings.EMBEDDING_DIMENSIONS,
        )

    if provider_name == "fake":
        return FakeEmbeddingProvider(
            dimensions=settings.EMBEDDING_DIMENSIONS,
            model=settings.EMBEDDING_MODEL,
        )

    raise ValueError(
        f"Unsupported EMBEDDING_PROVIDER '{settings.EMBEDDING_PROVIDER}'. "
        "Supported providers: 'openrouter', 'fake'."
    )
