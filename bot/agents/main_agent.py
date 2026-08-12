"""
Agente A — agente principal de conversación.

Maneja las 5 fases de la conversación. Detecta la señal [FIN_FASE] o
[FIN_CONVERSACION] en la respuesta del modelo para saber cuándo transitar.
"""
import asyncio
from openai import AsyncOpenAI
from bot.prompts.phases import (
    get_phase_system_prompt,
    PHASE_OPENING_PROMPTS,
    WELCOME_MESSAGE,
)
from bot.rag.retriever import retrieve_knowledge_context
from bot.rag.style_context import get_style_context, get_behavior_context
from bot.db.lessons import get_relevant_lessons

MAIN_MODEL = "gpt-4.1-mini"
FIN_FASE = "[FIN_FASE]"
FIN_CONV = "[FIN_CONVERSACION]"

_openai: AsyncOpenAI | None = None


def _get_openai() -> AsyncOpenAI:
    global _openai
    if _openai is None:
        _openai = AsyncOpenAI()
    return _openai


def _strip_signals(text: str) -> tuple[str, bool, bool]:
    fin_conv = FIN_CONV in text
    fin_fase = FIN_FASE in text or fin_conv
    clean = text.replace(FIN_FASE, "").replace(FIN_CONV, "").strip()
    return clean, fin_fase, fin_conv


async def _call_llm(system: str, history: list[dict], user_message: str | None = None) -> str:
    messages = [{"role": "system", "content": system}] + history
    if user_message:
        messages.append({"role": "user", "content": user_message})

    response = await _get_openai().chat.completions.create(
        model=MAIN_MODEL,
        messages=messages,
        temperature=0.4,
        max_tokens=800,
    )
    return response.choices[0].message.content or ""


async def _generate_phase_opener(
    next_phase: int,
    session: dict,
    history: list[dict],
) -> str:
    rag_ctx = ""
    if next_phase == 4:
        imbalance = session.get("collected_data", {}).get("main_imbalance", "")
        rag_ctx = await asyncio.to_thread(
            retrieve_knowledge_context,
            imbalance or "desequilibrio mental práctica meditativa",
        )

    style = await asyncio.to_thread(get_style_context)
    if next_phase == 4:
        behavior = await asyncio.to_thread(get_behavior_context)
        style = (style + "\n\n" + behavior).strip()

    system = get_phase_system_prompt(
        next_phase, session.get("collected_data", {}), rag_ctx, style
    )
    opening_instruction = PHASE_OPENING_PROMPTS.get(next_phase, "Continúa fluidamente.")

    opener = await _call_llm(system, history, opening_instruction)
    clean, _, _ = _strip_signals(opener)
    return clean


async def process_message(
    session: dict,
    history: list[dict],
    user_message: str,
) -> dict:
    """
    Procesa un mensaje del usuario y retorna:
    {
      "reply": str,
      "phase_advanced": bool,
      "conversation_ended": bool,
      "lessons_used": list,
      "raw_reply_for_evaluation": str,
    }
    """
    phase = session.get("phase", 1)
    collected = session.get("collected_data", {})

    # Recuperar lecciones, RAG y style en paralelo para reducir latencia
    lessons_task = asyncio.to_thread(get_relevant_lessons, user_message)
    style_task = asyncio.to_thread(get_style_context)

    if phase == 4:
        imbalance = collected.get("main_imbalance", "")
        query = f"{imbalance} práctica meditativa {user_message}"
        rag_task = asyncio.to_thread(retrieve_knowledge_context, query)
        lessons, rag_ctx, style_ctx = await asyncio.gather(lessons_task, rag_task, style_task)
        behavior = await asyncio.to_thread(get_behavior_context)
        style_ctx = (style_ctx + "\n\n" + behavior).strip()
    else:
        lessons, style_ctx = await asyncio.gather(lessons_task, style_task)
        rag_ctx = ""

    lessons_block = ""
    if lessons:
        lines = [
            f"{i+1}. CUANDO: {l['trigger_desc']}\n   REGLA: {l['rule']}\n   RAZÓN: {l['reason']}"
            for i, l in enumerate(lessons)
        ]
        lessons_block = (
            "\n\nLECCIONES APRENDIDAS DE INTERACCIONES PREVIAS (síguelas):\n"
            + "\n\n".join(lines)
        )

    system = get_phase_system_prompt(phase, collected, rag_ctx, style_ctx) + lessons_block

    raw_reply = await _call_llm(system, history, user_message)
    reply, phase_done, conv_done = _strip_signals(raw_reply)

    next_phase_opener = ""
    if phase_done and not conv_done:
        next_phase = phase + 1
        if next_phase <= 4:
            next_history = history + [
                {"role": "user", "content": user_message},
                {"role": "assistant", "content": reply},
            ]
            opener = await _generate_phase_opener(next_phase, session, next_history)
            next_phase_opener = opener

    full_reply = reply
    if next_phase_opener:
        full_reply = (reply + "\n\n" + next_phase_opener).strip() if reply else next_phase_opener

    # Si el modelo emitió solo [FIN_FASE] sin texto (full_reply vacío) y no hay opener,
    # no avanzamos la fase y pedimos al usuario que reintente.
    if not full_reply:
        return {
            "reply": "Lo siento, tuve un problema procesando tu mensaje. ¿Puedes intentarlo de nuevo?",
            "phase_advanced": False,
            "conversation_ended": False,
            "lessons_used": lessons,
            "raw_reply_for_evaluation": raw_reply,
        }

    return {
        "reply": full_reply,
        "phase_advanced": phase_done,
        "conversation_ended": conv_done,
        "lessons_used": lessons,
        "raw_reply_for_evaluation": raw_reply,
    }
