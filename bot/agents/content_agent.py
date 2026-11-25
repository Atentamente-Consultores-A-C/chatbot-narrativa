"""
Agente de dudas sobre el contenido de los cursos.

Responde solo con materiales recuperados por RAG (citando curso/módulo). Si no sabe
en qué curso está la persona (ni por `context.course_name`, ni por `context.course_id` si
viene de la plataforma edx, ni por lo que ya dijo),
se lo pregunta una vez; si el curso no se reconoce, responde con todo el material
disponible en lugar de dejar la duda sin responder.
"""
import asyncio
import re
import unicodedata
from openai import AsyncOpenAI
from bot.prompts.content import get_content_system_prompt
from bot.rag.retriever import retrieve_knowledge_context, get_known_courses
from bot.user_context import get_course_info, get_profile

CONTENT_MODEL = "gpt-4.1-mini"
_COURSE_SIGNAL = re.compile(r"\[CURSO:\s*(.+?)\]")

_openai: AsyncOpenAI | None = None


def _get_openai() -> AsyncOpenAI:
    global _openai
    if _openai is None:
        _openai = AsyncOpenAI()
    return _openai


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return " ".join(text.lower().split())


def _resolve_course(name: str | None, known: list[str]) -> str | None:
    if not name:
        return None
    target = _norm(str(name))
    return next((c for c in known if _norm(c) == target), None)


def _find_course(
    session: dict, user_context: dict, known: list[str], whatsapp_id: str | None = None
) -> tuple[str | None, bool]:
    """(curso con contenido o None, enrolled). enrolled=True si viene de la plataforma con
    course_id: sabemos que está en un curso aunque no se pueda mapear a uno con contenido."""
    info = get_course_info(whatsapp_id, user_context, known)
    course = info["course"] or _resolve_course(
        session.get("collected_data", {}).get("course"), known
    )
    return course, info["enrolled"]


def _build_rag_query(history: list[dict], user_message: str) -> str:
    # Incluye el mensaje de usuario anterior para que los seguimientos ("¿y cómo se
    # practica?") o la respuesta con el curso no pierdan la pregunta original.
    previous_user = [m["content"] for m in history if m["role"] == "user"][-1:]
    return " ".join(previous_user + [user_message])


async def _call_llm(system: str, history: list[dict], user_message: str) -> str:
    messages = [{"role": "system", "content": system}] + history
    messages.append({"role": "user", "content": user_message})
    response = await _get_openai().chat.completions.create(
        model=CONTENT_MODEL,
        messages=messages,
        temperature=0.2,
        max_tokens=600,
    )
    return response.choices[0].message.content or ""


async def process_message(
    session: dict,
    history: list[dict],
    user_message: str,
    user_context: dict,
    whatsapp_id: str | None = None,
) -> dict:
    """Retorna {"reply", "course", "general"}; "course"/"general" solo si se acaban de descubrir
    (general=True: el curso no se reconoció y se responde con todo el material).
    `user_context` es el context completo del contacto; al modelo solo llega el perfil."""
    profile = get_profile(user_context, user_context.get("contact_name"))
    known = await asyncio.to_thread(get_known_courses)
    course, enrolled = _find_course(
        session, user_context, known, whatsapp_id or session.get("whatsapp_id")
    )
    # Desde la plataforma no se le pregunta el curso: si su course_id no se reconoce,
    # se responde con el material de todos los cursos.
    general = bool(session.get("collected_data", {}).get("course_general")) or (enrolled and not course)
    new_course, new_general = None, False

    if known and not course and not general:
        system = get_content_system_prompt(profile, known, None)
        raw = await _call_llm(system, history, user_message)
        signal = _COURSE_SIGNAL.search(raw)
        if not signal:
            reply = raw.strip() or (
                "¿De qué curso es tu duda? Tengo contenido de: " + ", ".join(known) + "."
            )
            return {"reply": reply, "course": None, "general": False}
        course = new_course = _resolve_course(signal.group(1), known)
        if not course:
            general = new_general = True

    rag_ctx = await asyncio.to_thread(
        retrieve_knowledge_context, _build_rag_query(history, user_message), course
    )
    system = get_content_system_prompt(profile, known, course, rag_ctx, general)
    raw = await _call_llm(system, history, user_message)
    reply = _COURSE_SIGNAL.sub("", raw).strip()
    if not reply:
        reply = "Lo siento, tuve un problema procesando tu mensaje. ¿Puedes intentarlo de nuevo?"
    return {"reply": reply, "course": new_course, "general": new_general}
