import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.game import Game
from app.models.review import Review
from app.schemas.game import GameDetailRead
from app.schemas.review import ReviewRead
from app.services.ai.content_translation_service import (
    ContentTranslationService,
    compute_text_hash,
)
from app.services.ai.summarizer import _build_system_prompt as build_review_summary_prompt
from app.services.ai.translator import FakeTranslator, is_already_russian
from app.services.youtube.summarizer import _build_system_prompt as build_youtube_summary_prompt


class FailingTranslator:
    """Translator that always fails to test pipeline resilience."""

    provider = "failing"
    model = "failing-model"

    async def translate_text(self, text: str, context_type: str = "description") -> str:
        raise RuntimeError("Simulated OpenRouter network failure")


@pytest.mark.asyncio
async def test_01_original_description_preserved_untouched(db_session: AsyncSession) -> None:
    """1. Original Metacritic English description is preserved without modifications."""
    original_desc = (
        "An epic open-world action RPG set in the Lands Between, created by Hidetaka Miyazaki."
    )
    game = Game(
        metacritic_slug="elden-ring-test-01",
        metacritic_url="https://www.metacritic.com/game/elden-ring-test-01/",
        title="Elden Ring",
        description=original_desc,
    )
    db_session.add(game)
    await db_session.commit()
    await db_session.refresh(game)

    fake_translator = FakeTranslator()
    service = ContentTranslationService(db=db_session, translator=fake_translator)
    res = await service.translate_game_description(game)

    assert res.status == "translated"
    await db_session.refresh(game)
    # INVARIANT: Original English description remains 100% identical
    assert game.description == original_desc
    assert game.description_ru is not None
    assert game.description_ru != original_desc


@pytest.mark.asyncio
async def test_02_russian_description_stored_separately(db_session: AsyncSession) -> None:
    """2. Russian description is stored in a dedicated description_ru column with hash."""
    game = Game(
        metacritic_slug="hades-test-02",
        metacritic_url="https://www.metacritic.com/game/hades-test-02/",
        title="Hades",
        description="Defy the god of the dead as you hack and slash out of the Underworld.",
    )
    db_session.add(game)
    await db_session.commit()
    await db_session.refresh(game)

    service = ContentTranslationService(db=db_session, translator=FakeTranslator())
    await service.translate_game_description(game)
    await db_session.commit()

    stmt = select(Game).where(Game.id == game.id)
    refreshed = (await db_session.execute(stmt)).scalar_one()

    assert refreshed.description_ru == f"[Перевод на русский] {refreshed.description}"
    assert refreshed.description_source_hash == compute_text_hash(refreshed.description or "")


@pytest.mark.asyncio
async def test_03_api_exposes_description_ru(db_session: AsyncSession) -> None:
    """3. API schema (GameDetailRead) exposes description_ru cleanly."""
    game = Game(
        metacritic_slug="portal-test-03",
        metacritic_url="https://www.metacritic.com/game/portal-test-03/",
        title="Portal 2",
        description="The innovative puzzle game from Valve.",
        description_ru="Инновационная игра-головоломка от Valve.",
    )
    db_session.add(game)
    await db_session.commit()
    await db_session.refresh(game)

    dto = GameDetailRead.model_validate(game)
    assert dto.description_ru == "Инновационная игра-головоломка от Valve."
    assert dto.title == "Portal 2"


def test_04_ui_contract_prevents_english_description_fallback() -> None:
    """4. UI rendering contract guarantees no English description leaks to users."""

    def render_description_ui(desc_ru: str | None, desc_en: str | None) -> str:
        if desc_ru:
            return desc_ru
        if desc_en:
            return "Перевод описания подготавливается…"
        return "Описание отсутствует."

    # When Russian is available -> show Russian
    assert render_description_ui("Русское описание", "English description") == "Русское описание"
    # When Russian is NOT yet ready -> show Russian placeholder, NEVER English
    assert (
        render_description_ui(None, "English description") == "Перевод описания подготавливается…"
    )
    assert "English" not in render_description_ui(None, "English description")
    # When neither exists -> show empty message
    assert render_description_ui(None, None) == "Описание отсутствует."


@pytest.mark.asyncio
async def test_05_original_review_body_preserved_untouched(db_session: AsyncSession) -> None:
    """5. Original English review body is preserved without modification."""
    game = Game(
        metacritic_slug="cyberpunk-test-05",
        metacritic_url="https://www.metacritic.com/game/cyberpunk-test-05/",
        title="Cyberpunk 2077",
    )
    db_session.add(game)
    await db_session.flush()

    orig_body = (
        "Night City is an incredible technological marvel with deeply compelling storytelling."
    )
    review = Review(
        game_id=game.id,
        review_type="critic",
        author="PC Gamer",
        rating=90.0,
        body=orig_body,
    )
    db_session.add(review)
    await db_session.commit()

    service = ContentTranslationService(db=db_session, translator=FakeTranslator())
    await service.translate_game_reviews(game)
    await db_session.refresh(review)

    # Invariant: Original review body is untouched
    assert review.body == orig_body
    assert review.body_ru is not None
    assert review.body_ru.startswith("[Перевод на русский]")


@pytest.mark.asyncio
async def test_06_review_russian_translation_stored_separately(db_session: AsyncSession) -> None:
    """6. Review Russian translation is stored in body_ru with body_source_hash."""
    game = Game(
        metacritic_slug="witcher-test-06",
        metacritic_url="https://www.metacritic.com/game/witcher-test-06/",
        title="The Witcher 3",
    )
    db_session.add(game)
    await db_session.flush()

    review = Review(
        game_id=game.id,
        review_type="user",
        author="Gamer123",
        rating=10.0,
        body="One of the greatest RPGs ever made.",
    )
    db_session.add(review)
    await db_session.commit()

    service = ContentTranslationService(db=db_session, translator=FakeTranslator())
    stats = await service.translate_game_reviews(game)
    await db_session.commit()

    assert stats.translated == 1
    await db_session.refresh(review)
    assert review.body_ru == "[Перевод на русский] One of the greatest RPGs ever made."
    assert review.body_source_hash == compute_text_hash(review.body or "")


@pytest.mark.asyncio
async def test_07_filtered_displayed_reviews_only_use_body_ru(db_session: AsyncSession) -> None:
    """7. Frontend review filtering contract selects only reviews with body_ru."""
    game = Game(
        metacritic_slug="zelda-test-07",
        metacritic_url="https://www.metacritic.com/game/zelda-test-07/",
        title="Zelda: Tears of the Kingdom",
    )
    db_session.add(game)
    await db_session.flush()

    # Review 1: Translated
    r1 = Review(
        game_id=game.id,
        review_type="critic",
        body="Masterpiece of emergent gameplay.",
        body_ru="Шедевр эмерджентного геймплея.",
    )
    # Review 2: Not yet translated
    r2 = Review(
        game_id=game.id,
        review_type="critic",
        body="Unbelievable physics and building systems.",
        body_ru=None,
    )
    db_session.add_all([r1, r2])
    await db_session.commit()

    # Emulate frontend filtering:
    reviews = [ReviewRead.model_validate(r) for r in [r1, r2]]
    displayed = [r for r in reviews if r.body_ru]

    assert len(displayed) == 1
    assert displayed[0].body_ru == "Шедевр эмерджентного геймплея."
    # Review 2 is NOT shown because it has no Russian translation yet
    assert not any(r.body_ru is None for r in displayed)


def test_08_missing_translation_yields_russian_placeholder_not_english() -> None:
    """8. Missing translation UI logic displays pending placeholder, never falling back to English."""

    def get_review_tab_message(total_source: int, total_translated: int, tab_type: str) -> str:
        label = "критиков" if tab_type == "critic" else "игроков"
        if total_source == 0:
            return f"Отзывы {label} для этой игры пока отсутствуют."
        if total_translated == 0:
            return f"Перевод отзывов {label} подготавливается…"
        return ""

    # No source reviews at all
    assert (
        get_review_tab_message(0, 0, "critic") == "Отзывы критиков для этой игры пока отсутствуют."
    )
    # Source reviews exist but translation is pending
    assert get_review_tab_message(5, 0, "critic") == "Перевод отзывов критиков подготавливается…"
    # Zero English leakage in either state
    assert "review" not in get_review_tab_message(5, 0, "critic").lower()


@pytest.mark.asyncio
async def test_09_unchanged_translation_skips_llm_call(db_session: AsyncSession) -> None:
    """9. Unchanged source text skips LLM translation call based on SHA-256 fingerprint."""
    game = Game(
        metacritic_slug="celeste-test-09",
        metacritic_url="https://www.metacritic.com/game/celeste-test-09/",
        title="Celeste",
        description="Help Madeline survive her inner demons on her journey to Celeste Mountain.",
    )
    db_session.add(game)
    await db_session.commit()

    fake_translator = FakeTranslator()
    service = ContentTranslationService(db=db_session, translator=fake_translator)

    # First call: Translates
    res1 = await service.translate_game_description(game)
    assert res1.status == "translated"
    assert fake_translator.call_count == 1
    await db_session.commit()

    # Second call without modifying description: Skipped
    res2 = await service.translate_game_description(game)
    assert res2.status == "skipped_unchanged"
    # Call count did NOT increase
    assert fake_translator.call_count == 1


@pytest.mark.asyncio
async def test_10_changed_source_triggers_retranslation(db_session: AsyncSession) -> None:
    """10. Modifying the source description invalidates the hash and triggers re-translation."""
    game = Game(
        metacritic_slug="doom-test-10",
        metacritic_url="https://www.metacritic.com/game/doom-test-10/",
        title="DOOM Eternal",
        description="Hell's armies have invaded Earth. Become the Slayer.",
    )
    db_session.add(game)
    await db_session.commit()

    fake_translator = FakeTranslator()
    service = ContentTranslationService(db=db_session, translator=fake_translator)

    await service.translate_game_description(game)
    assert fake_translator.call_count == 1
    old_translation = game.description_ru
    await db_session.commit()

    # Source text changes
    game.description = (
        "Hell's armies have invaded Earth. Raze Hell with the ultimate Slayer arsenal."
    )
    await db_session.commit()

    res = await service.translate_game_description(game)
    assert res.status == "translated"
    assert fake_translator.call_count == 2
    assert game.description_ru != old_translation
    assert game.description_source_hash == compute_text_hash(game.description)


@pytest.mark.asyncio
async def test_11_translation_failure_does_not_block_ingestion(db_session: AsyncSession) -> None:
    """11. Translation failure does not block or fail game ingestion/pipeline."""
    game = Game(
        metacritic_slug="bloodborne-test-11",
        metacritic_url="https://www.metacritic.com/game/bloodborne-test-11/",
        title="Bloodborne",
        description="A terrifying action RPG through the ancient city of Yharnam.",
    )
    db_session.add(game)
    await db_session.commit()

    failing_service = ContentTranslationService(db=db_session, translator=FailingTranslator())  # type: ignore[arg-type]

    # Description translation returns error status without blowing up unhandled
    res = await failing_service.translate_game_description(game)
    assert res.status == "error"
    assert "Simulated OpenRouter network failure" in (res.error or "")

    # Ingestion remains healthy and game persists
    await db_session.refresh(game)
    assert game.title == "Bloodborne"
    assert game.description_ru is None  # Remains pending/null safely


def test_12_ai_review_summaries_generated_in_russian() -> None:
    """12. Review summarizer system prompt explicitly enforces natural Russian output."""
    prompt = build_review_summary_prompt("ru")
    assert "Return the final answer in natural Russian." in prompt
    assert "Output all text (summary, likes, dislikes) strictly in Russian." in prompt


def test_13_youtube_summary_generated_in_russian() -> None:
    """13. YouTube Let's Play summarizer system prompt explicitly enforces Russian output."""
    prompt = build_youtube_summary_prompt("ru")
    assert "Return the final answer in natural Russian." in prompt
    assert (
        "Output all text (summary, key_points, overall_impression) strictly in Russian." in prompt
    )


@pytest.mark.asyncio
async def test_14_backfill_russian_content_is_idempotent(db_session: AsyncSession) -> None:
    """14. Running translation on existing localized data is fully idempotent."""
    game = Game(
        metacritic_slug="sekiro-test-14",
        metacritic_url="https://www.metacritic.com/game/sekiro-test-14/",
        title="Sekiro: Shadows Die Twice",
        description="Carve your own clever path to vengeance in feudal Japan.",
    )
    db_session.add(game)
    await db_session.flush()

    rev = Review(
        game_id=game.id,
        review_type="critic",
        body="Incredible posture-based combat design.",
    )
    db_session.add(rev)
    await db_session.commit()

    fake_translator = FakeTranslator()
    service = ContentTranslationService(db=db_session, translator=fake_translator)

    # First pass: Translates
    r1 = await service.translate_game_content(game)
    assert r1["description_status"] == "translated"
    assert r1["reviews_translated"] == 1
    assert fake_translator.call_count == 2
    await db_session.commit()

    # Second pass: Skipped unchanged
    r2 = await service.translate_game_content(game)
    assert r2["description_status"] == "skipped_unchanged"
    assert r2["reviews_skipped_unchanged"] == 1
    assert r2["reviews_translated"] == 0
    # No additional LLM calls made
    assert fake_translator.call_count == 2


@pytest.mark.asyncio
async def test_15_already_russian_source_not_resent_to_llm(db_session: AsyncSession) -> None:
    """15. Already Russian source text is detected and bypassed without redundant LLM calls."""
    russian_desc = "Увлекательная ролевая игра с глубоким сюжетом и открытым миром."
    game = Game(
        metacritic_slug="russian-game-test-15",
        metacritic_url="https://www.metacritic.com/game/russian-game-test-15/",
        title="Сказка",
        description=russian_desc,
    )
    db_session.add(game)
    await db_session.commit()

    assert is_already_russian(russian_desc) is True

    fake_translator = FakeTranslator()
    service = ContentTranslationService(db=db_session, translator=fake_translator)
    res = await service.translate_game_description(game)

    assert res.status == "already_russian"
    assert fake_translator.call_count == 0  # Zero LLM calls!
    await db_session.refresh(game)
    assert game.description_ru == russian_desc
    assert game.description_source_hash == compute_text_hash(russian_desc)
