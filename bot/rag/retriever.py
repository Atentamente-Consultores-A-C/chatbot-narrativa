import os
from openai import OpenAI
from bot.db.client import get_supabase

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


def _search(embedding: list[float], filter_param: dict, k: int) -> list[dict]:
    sb = get_supabase()
    return sb.rpc("match_documents", {
        "query_embedding": embedding,
        "match_count": k,
        "filter": filter_param,
    }).execute().data or []


def retrieve_context(
    query: str,
    metadata_filter: dict | None = None,
    doc_types: list[str] | None = None,
    k_specific: int = 4,
    k_general: int = 2,
) -> str:
    """
    Recupera fragmentos relevantes de la base de conocimiento.

    doc_types filtra por tipo de documento:
      "knowledge"            — contenido de cursos (PDFs de manuales)
      "behavior_example"     — instrucciones y reglas de comportamiento
      "conversation_example" — ejemplos de conversaciones socráticas

    Si doc_types es None, busca en todos los tipos.
    Combina resultados filtrados + resultados generales (sin filtro de curso/módulo).
    """
    embedding = _embed(query)

    base_filter = metadata_filter or {}

    # Si hay filtro de doc_type, hacer búsqueda separada por cada tipo y combinar
    if doc_types:
        all_results = []
        for dt in doc_types:
            f = {**base_filter, "doc_type": dt}
            all_results += _search(embedding, f, k_specific)
        # Además buscar sin filtro de doc_type para no perder contexto general
        all_results += _search(embedding, base_filter, k_general)
    else:
        all_results = _search(embedding, base_filter, k_specific)
        if base_filter:
            all_results += _search(embedding, {}, k_general)

    seen, merged = set(), []
    for doc in all_results:
        key = doc["content"][:80]
        if key not in seen:
            seen.add(key)
            merged.append(doc)

    if not merged:
        return "(No se encontraron materiales relevantes para esta consulta.)"

    parts = []
    for i, doc in enumerate(merged, 1):
        meta = doc.get("metadata", {})
        source = meta.get("source_file", "desconocido")
        course = meta.get("course", "")
        module = meta.get("module", "")
        dtype = meta.get("doc_type", "")
        parts.append(
            f"[{i}] [{dtype}] {course} · módulo {module} · {source}\n{doc['content']}"
        )
    return "\n\n".join(parts)


def retrieve_behavior_context(query: str) -> str:
    """Recupera instrucciones de comportamiento y ejemplos de conversación."""
    return retrieve_context(
        query,
        doc_types=["behavior_example", "conversation_example"],
        k_specific=3,
        k_general=0,
    )


def retrieve_knowledge_context(query: str, course: str | None = None,
                                module: int | None = None) -> str:
    """Recupera contenido de cursos (manuales, prácticas)."""
    f = {}
    if course:
        f["course"] = course
    if module is not None:
        f["module"] = module
    return retrieve_context(
        query,
        metadata_filter=f,
        doc_types=["knowledge"],
        k_specific=4,
        k_general=2,
    )
