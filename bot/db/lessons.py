from openai import OpenAI
from .client import get_supabase

_openai: OpenAI | None = None


def _get_openai() -> OpenAI:
    global _openai
    if _openai is None:
        _openai = OpenAI()
    return _openai


def _embed(text: str) -> list[float]:
    response = _get_openai().embeddings.create(
        model="text-embedding-3-small",
        input=text,
    )
    return response.data[0].embedding


def get_relevant_lessons(user_message: str, threshold: float = 0.5, limit: int = 5) -> list[dict]:
    """Busca lecciones relevantes usando similitud vectorial."""
    sb = get_supabase()
    embedding = _embed(user_message)
    result = sb.rpc("match_lessons", {
        "query_embedding": embedding,
        "match_count": limit,
    }).execute()

    return [r for r in (result.data or []) if r.get("similarity", 0) >= threshold]


def save_lesson(trigger: str, rule: str, reason: str) -> dict:
    sb = get_supabase()
    embedding = _embed(f"{trigger} {rule}")
    result = sb.table("lessons").insert({
        "trigger_desc": trigger,
        "rule": rule,
        "reason": reason,
        "embedding": embedding,
        "active": True,
        "times_applied": 0,
    }).execute()
    return result.data[0]


def save_evaluation(message_id: str, quality: str, problem: str | None,
                    reasoning: str, lesson_id: str | None) -> None:
    sb = get_supabase()
    sb.table("evaluations").insert({
        "message_id": message_id,
        "quality": quality,
        "problem": problem,
        "reasoning": reasoning,
        "lesson_id": lesson_id,
    }).execute()


def increment_lesson_usage(lesson_ids: list[str]) -> None:
    if not lesson_ids:
        return
    sb = get_supabase()
    for lid in lesson_ids:
        sb.rpc("increment_lesson", {"lesson_id": lid}).execute()
