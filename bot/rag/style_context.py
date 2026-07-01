"""
Carga documentos de estilo UNA SOLA VEZ al arrancar el servidor y los cachea en memoria.

- conversation_example → se inyecta en TODAS las fases (tono y ritmo general)
- behavior_example     → solo se inyecta en FASE 4 (lineamientos del diálogo socrático)
"""
from bot.db.client import get_supabase

_conversation_cache: str | None = None
_behavior_cache: str | None = None


def _fetch_docs(doc_types: list[str]) -> str:
    sb = get_supabase()
    result = sb.table("documents").select("content, metadata").in_(
        "metadata->>doc_type", doc_types
    ).execute()

    if not result.data:
        return ""

    parts = [row["content"] for row in result.data if row.get("content")]
    return "\n---\n".join(parts)


def get_conversation_style() -> str:
    """Ejemplos de conversación — tono y ritmo. Se inyecta en todas las fases."""
    global _conversation_cache
    if _conversation_cache is None:
        raw = _fetch_docs(["conversation_example"])
        _conversation_cache = (
            "EJEMPLOS DE CONVERSACIÓN (imita este estilo, tono y ritmo):\n" + raw
            if raw else ""
        )
    return _conversation_cache


def get_behavior_context() -> str:
    """Lineamientos de comportamiento fase 4. Solo se inyecta en fase 4."""
    global _behavior_cache
    if _behavior_cache is None:
        raw = _fetch_docs(["behavior_example"])
        _behavior_cache = (
            "INSTRUCCIONES DE COMPORTAMIENTO PARA ESTA FASE (síguelas estrictamente):\n" + raw
            if raw else ""
        )
    return _behavior_cache


def get_style_context() -> str:
    """Compatibilidad: retorna solo conversation_example (para todas las fases)."""
    return get_conversation_style()


def invalidate_cache() -> None:
    global _conversation_cache, _behavior_cache
    _conversation_cache = None
    _behavior_cache = None
