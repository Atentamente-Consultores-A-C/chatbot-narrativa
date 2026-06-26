"""
Carga los documentos de comportamiento y ejemplos de conversación UNA SOLA VEZ
al arrancar el servidor y los cachea en memoria.

Se inyectan en el system prompt de TODAS las fases, sin costo de latencia por mensaje.
Los documentos de conocimiento (manuales, cursos) siguen usando RAG dinámico.
"""
from bot.db.client import get_supabase

_cache: str | None = None


def _fetch_style_docs() -> str:
    sb = get_supabase()

    result = sb.table("documents").select("content, metadata").in_(
        "metadata->>doc_type", ["behavior_example", "conversation_example"]
    ).execute()

    if not result.data:
        return ""

    behavior, examples = [], []
    for row in result.data:
        dtype = (row.get("metadata") or {}).get("doc_type", "")
        if dtype == "behavior_example":
            behavior.append(row["content"])
        elif dtype == "conversation_example":
            examples.append(row["content"])

    parts = []
    if behavior:
        parts.append(
            "INSTRUCCIONES DE COMPORTAMIENTO (síguelas en toda la conversación):\n"
            + "\n---\n".join(behavior)
        )
    if examples:
        parts.append(
            "EJEMPLOS DE CONVERSACIÓN (imita este estilo, tono y ritmo):\n"
            + "\n---\n".join(examples)
        )

    return "\n\n".join(parts)


def get_style_context() -> str:
    """Retorna el contexto de estilo cacheado. Llama a Supabase solo la primera vez."""
    global _cache
    if _cache is None:
        _cache = _fetch_style_docs()
    return _cache


def invalidate_cache() -> None:
    """Llama esto si actualizas los documentos de comportamiento en caliente."""
    global _cache
    _cache = None
