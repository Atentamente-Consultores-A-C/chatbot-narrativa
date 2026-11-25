"""
Agente A — agente principal de conversación.

Maneja las 5 fases de la conversación. Detecta la señal [FIN_FASE] o
[FIN_CONVERSACION] en la respuesta del modelo para saber cuándo transitar.
"""
import asyncio
import json
import re
from datetime import date
from openai import AsyncOpenAI
from bot.prompts.phases import (
    get_phase_system_prompt,
    get_phase_opening_prompt,
    get_extraction_prompt,
    WELCOME_MESSAGE,
)
from bot.prompts.express import (
    EXPRESS_MAX_TURNS,
    TIME_CLASSIFIER_PROMPT,
    TIME_NORMAL,
    TIME_SHORT,
    TIME_UNKNOWN,
    get_express_system_prompt,
)
from bot.rag.retriever import retrieve_knowledge_context, get_known_courses
from bot.user_context import (
    DEFAULT_PROGRAM,
    PROGRAM_EPB,
    find_course_in_text,
    get_course_info,
    get_profile,
    program_from_name,
    resolve_course_name,
)
from bot.rag.style_context import get_style_context, get_behavior_context
from bot.db.lessons import get_relevant_lessons

MAIN_MODEL = "gpt-4.1-mini"
FIN_FASE = "[FIN_FASE]"
FIN_CONV = "[FIN_CONVERSACION]"
SURVEY_MESSAGE = (
    "Agradecería tu opinión sobre mi calidad de servicio en la siguiente encuesta: "
    "https://docs.google.com/forms/d/e/1FAIpQLSey7rEW9PxghC6wQE3b0rJo_PWBJaNwlZEqtASIp6nvLB8I0w/viewform"
)

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


_QUESTION_RE = re.compile(r"¿[^¿?]*\?")


def _drop_questions(text: str) -> str:
    """Quita todas las preguntas (¿...?). Se usa en el mensaje que cierra una fase cuando
    a continuación va la pregunta de apertura de la siguiente."""
    cleaned = _QUESTION_RE.sub("", text)
    return re.sub(r"[ \t]{2,}", " ", cleaned).strip()


def _keep_one_question(text: str) -> str:
    """Si el modelo hizo más de una pregunta, deja solo la primera (regla de una pregunta
    por mensaje)."""
    questions = list(_QUESTION_RE.finditer(text))
    if len(questions) <= 1:
        return text
    out, last = [], 0
    for i, m in enumerate(questions):
        out.append(text[last:m.start()])
        if i == 0:
            out.append(m.group(0))
        last = m.end()
    out.append(text[last:])
    return re.sub(r"[ \t]{2,}", " ", "".join(out)).strip()


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


async def _classify_time_mode(user_text: str) -> str:
    try:
        response = await _get_openai().chat.completions.create(
            model=MAIN_MODEL,
            messages=[
                {"role": "system", "content": TIME_CLASSIFIER_PROMPT},
                {"role": "user", "content": user_text},
            ],
            temperature=0,
            max_tokens=5,
        )
    except Exception as e:
        print(f"[Warning] No se pudo clasificar el tiempo disponible: {e}")
        return TIME_UNKNOWN
    answer = (response.choices[0].message.content or "").strip().lower()
    if answer.startswith(TIME_SHORT):
        return TIME_SHORT
    if answer.startswith(TIME_NORMAL):
        return TIME_NORMAL
    return TIME_UNKNOWN


async def _extract_phase_data(key, history: list[dict]) -> dict:
    """Resume en JSON lo que se obtuvo en la fase que acaba de terminar (ver
    _EXTRACTION_FIELDS en prompts/phases.py). {} si falla: la conversación sigue igual."""
    system = get_extraction_prompt(key)
    if not system:
        return {}
    transcript = "\n".join(
        f"{'Persona' if m['role'] == 'user' else 'Acompañante'}: {m['content']}"
        for m in history[-24:]
    )
    try:
        response = await _get_openai().chat.completions.create(
            model=MAIN_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": transcript},
            ],
            temperature=0,
            max_tokens=400,
            response_format={"type": "json_object"},
        )
        data = json.loads(response.choices[0].message.content or "{}")
    except Exception as e:
        print(f"[Warning] No se pudieron extraer los datos de la fase {key}: {e}")
        return {}
    return {k: str(v).strip() for k, v in data.items() if isinstance(v, (str, int, float)) and str(v).strip()}


def _map_extracted(phase, data: dict, known: list[str]) -> dict:
    """Convierte la extracción en las claves de collected_data que usan los prompts."""
    if phase == 4 or phase == "express":
        out = {}
        if data.get("difficulty"):
            out["difficulty"] = data["difficulty"]
        if data.get("practice"):
            rec = {k: data.get(k, "") for k in ("practice", "when", "observe")}
            out["recommendation"] = rec
            out["practices"] = "; ".join(
                part for part in (
                    rec["practice"],
                    f"cuándo: {rec['when']}" if rec["when"] else "",
                    f"observar: {rec['observe']}" if rec["observe"] else "",
                ) if part
            )
        course = resolve_course_name(data.get("course"), known)
        if course:
            out["course"] = course
        return out
    return data


def _build_last_recommendation(collected: dict) -> dict | None:
    """Lo que se guarda para el seguimiento de la próxima conversación."""
    rec = collected.get("recommendation")
    if not rec or not rec.get("practice"):
        return None
    return {
        **rec,
        "difficulty": collected.get("difficulty", ""),
        "date": date.today().isoformat(),
    }


async def _resolve_course_info(
    whatsapp_id: str | None,
    user_context: dict | None,
    collected: dict,
    history: list[dict],
    user_message: str,
    contact_name: str | None = None,
) -> dict:
    """Curso de la persona: context (course_name o, en edx, course_id) > lo que dijo en la
    fase 4 > nombre de curso mencionado en sus mensajes recientes.
    Agrega "flow" (programa cuyo flujo se usa, fijo durante la conversación) y "profile"."""
    try:
        known = await asyncio.to_thread(get_known_courses)
    except Exception as e:
        print(f"[Warning] No se pudieron cargar los cursos: {e}")
        known = []
    info = get_course_info(whatsapp_id, user_context, known)
    if not info["course"]:
        recent_user = [m["content"] for m in history[-12:] if m["role"] == "user"] + [user_message]
        info["course"] = (
            resolve_course_name(collected.get("course"), known)
            or find_course_in_text(recent_user, known)
        )
    info["known"] = known
    if info["course"] and not info["program"]:
        info["program"] = program_from_name(info["course"])
    # El flujo se decide al inicio y se guarda en collected_data["program"] para no cambiar
    # de rama a media conversación.
    info["flow"] = collected.get("program") or info["program"] or DEFAULT_PROGRAM
    info["profile"] = get_profile(user_context, contact_name)
    return info


async def _resolve_time_mode(collected: dict, phase: int, history: list[dict], user_message: str) -> str | None:
    """Modo ya guardado, o el detectado en los primeros mensajes. None = todavía no se sabe."""
    saved = collected.get("time_mode")
    if saved:
        return saved
    prior_user = [m["content"] for m in history if m["role"] == "user"]
    if phase != 1 or len(prior_user) > 1:
        return TIME_NORMAL
    detected = await _classify_time_mode(" ".join(prior_user + [user_message]))
    if detected == TIME_UNKNOWN:
        # Si no lo dijo en el primer mensaje, se le da una segunda oportunidad
        return TIME_NORMAL if prior_user else None
    return detected


async def _process_express(
    history: list[dict],
    user_message: str,
    collected: dict,
    updates: dict,
    course_info: dict,
) -> dict:
    """Modo express: algo concreto en máximo EXPRESS_MAX_TURNS mensajes, sin fases.
    No usa lecciones del supervisor (son del flujo de 5 fases) ni se evalúa con él."""
    turn = collected.get("express_turns", 0) + 1
    previous_user = [m["content"] for m in history if m["role"] == "user"][-1:]
    rag_ctx = await asyncio.to_thread(
        retrieve_knowledge_context,
        " ".join(previous_user + [user_message]),
        course_info.get("course"),
    )
    system = get_express_system_prompt(
        turn, rag_ctx, course_info, collected.get("follow_up"),
        program=course_info.get("flow"), profile=course_info.get("profile"),
    )
    raw_reply = await _call_llm(system, history, user_message)
    reply, _, conv_done = _strip_signals(raw_reply)
    if not conv_done:
        reply = _keep_one_question(reply)

    if not reply:
        return {
            "reply": "Lo siento, tuve un problema procesando tu mensaje. ¿Puedes intentarlo de nuevo?",
            "phase_advanced": False,
            "conversation_ended": False,
            "lessons_used": [],
            "raw_reply_for_evaluation": raw_reply,
            "collected_updates": updates,
            "skip_supervisor": True,
        }

    conv_done = conv_done or turn >= EXPRESS_MAX_TURNS
    updates = {**updates, "express_turns": turn}
    if conv_done:
        full_history = history + [
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": reply},
        ]
        extracted = _map_extracted(
            "express",
            await _extract_phase_data("express", full_history),
            course_info.get("known", []),
        )
        updates.update(extracted)
        last_rec = _build_last_recommendation({**collected, **updates})
        if last_rec:
            updates["last_recommendation"] = last_rec
        reply = reply + "\n\n" + SURVEY_MESSAGE
    return {
        "reply": reply,
        "phase_advanced": conv_done,
        "conversation_ended": conv_done,
        "lessons_used": [],
        "raw_reply_for_evaluation": raw_reply,
        "collected_updates": updates,
        "skip_supervisor": True,
    }


def _phase4_rag_query(collected: dict, extra: str = "") -> str:
    parts = [
        collected.get("main_imbalance", ""),
        collected.get("trigger_response", ""),
        collected.get("difficulty", ""),
        "práctica",
        extra,
    ]
    return " ".join(p for p in parts if p).strip() or "desequilibrio mental práctica meditativa"


async def _generate_phase_opener(
    next_phase: int,
    collected: dict,
    history: list[dict],
    course_info: dict,
) -> tuple[str, bool]:
    """Primer mensaje de la fase siguiente. Retorna (texto, conversación_terminada)."""
    rag_ctx = ""
    if next_phase == 4:
        rag_ctx = await asyncio.to_thread(
            retrieve_knowledge_context, _phase4_rag_query(collected), course_info.get("course")
        )

    style = await asyncio.to_thread(get_style_context)
    if next_phase == 4:
        behavior = await asyncio.to_thread(get_behavior_context)
        style = (style + "\n\n" + behavior).strip()

    flow = course_info.get("flow")
    system = get_phase_system_prompt(
        next_phase, collected, rag_ctx, style, course_info, flow, course_info.get("profile")
    )
    opening_instruction = get_phase_opening_prompt(next_phase, collected, course_info, flow)

    opener = await _call_llm(system, history, opening_instruction)
    clean, _, conv_done = _strip_signals(opener)
    if next_phase != 5:
        clean = _keep_one_question(clean)
    # El cierre (fase 5) siempre termina la conversación, aunque el modelo olvide la señal.
    return clean, conv_done or next_phase == 5


async def process_message(
    session: dict,
    history: list[dict],
    user_message: str,
    user_context: dict | None = None,
    whatsapp_id: str | None = None,
) -> dict:
    """
    Procesa un mensaje del usuario y retorna:
    {
      "reply": str,
      "phase_advanced": bool,
      "conversation_ended": bool,
      "lessons_used": list,
      "raw_reply_for_evaluation": str,
      "collected_updates": dict,   # claves a mezclar en session.collected_data
      "skip_supervisor": bool,     # solo en modo express
    }
    """
    phase = session.get("phase", 1)
    collected = session.get("collected_data", {})

    # En paralelo: clasificar el tiempo disponible y resolver curso/programa/perfil
    time_mode, course_info = await asyncio.gather(
        _resolve_time_mode(collected, phase, history, user_message),
        _resolve_course_info(
            whatsapp_id or session.get("whatsapp_id"),
            user_context,
            collected,
            history,
            user_message,
            session.get("contact_name"),
        ),
    )
    updates: dict = {}
    if time_mode and "time_mode" not in collected:
        updates["time_mode"] = time_mode
    if "program" not in collected:
        updates["program"] = course_info["flow"]
    if time_mode == TIME_SHORT:
        return await _process_express(history, user_message, collected, updates, course_info)

    # Recuperar lecciones, RAG y style en paralelo para reducir latencia
    lessons_task = asyncio.to_thread(get_relevant_lessons, user_message)
    style_task = asyncio.to_thread(get_style_context)

    if phase == 4:
        query = _phase4_rag_query(collected, user_message)
        rag_task = asyncio.to_thread(retrieve_knowledge_context, query, course_info.get("course"))
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

    system = get_phase_system_prompt(
        phase, collected, rag_ctx, style_ctx, course_info,
        course_info.get("flow"), course_info.get("profile"),
    ) + lessons_block

    raw_reply = await _call_llm(system, history, user_message)
    reply, phase_done, conv_done = _strip_signals(raw_reply)
    if phase_done and not conv_done and phase <= 4:
        # La pregunta la pone la apertura de la siguiente fase: aquí no debe ir ninguna
        reply = _drop_questions(reply)
    elif not conv_done:
        reply = _keep_one_question(reply)

    next_phase_opener = ""
    if phase_done and not conv_done and phase <= 4:
        next_history = history + [
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": reply},
        ]
        # Guardar lo que dejó la fase que termina, para que los prompts siguientes lo usen
        extract_key = phase
        if course_info.get("flow") == PROGRAM_EPB and phase in (2, 3):
            extract_key = f"epb_{phase}"
        extracted = _map_extracted(
            phase,
            await _extract_phase_data(extract_key, next_history),
            course_info.get("known", []),
        )
        updates.update(extracted)
        if extracted.get("course") and not course_info.get("course"):
            course_info["course"] = extracted["course"]
        next_collected = {**collected, **updates}
        # Tras la fase 4 se genera el cierre de inmediato (fase 5) con la recomendación ya extraída
        next_phase_opener, opener_ended = await _generate_phase_opener(
            phase + 1, next_collected, next_history, course_info
        )
        conv_done = conv_done or opener_ended

    if conv_done:
        last_rec = _build_last_recommendation({**collected, **updates})
        if last_rec:
            updates["last_recommendation"] = last_rec

    full_reply = reply
    if next_phase_opener:
        full_reply = (reply + "\n\n" + next_phase_opener).strip() if reply else next_phase_opener

    # El último mensaje de la conversación siempre lleva la encuesta después de la despedida
    if conv_done and full_reply:
        full_reply = full_reply + "\n\n" + SURVEY_MESSAGE

    # Si el modelo emitió solo [FIN_FASE] sin texto (full_reply vacío) y no hay opener,
    # no avanzamos la fase y pedimos al usuario que reintente.
    if not full_reply:
        return {
            "reply": "Lo siento, tuve un problema procesando tu mensaje. ¿Puedes intentarlo de nuevo?",
            "phase_advanced": False,
            "conversation_ended": False,
            "lessons_used": lessons,
            "raw_reply_for_evaluation": raw_reply,
            "collected_updates": updates,
        }

    return {
        "reply": full_reply,
        "phase_advanced": phase_done,
        "conversation_ended": conv_done,
        "lessons_used": lessons,
        "raw_reply_for_evaluation": raw_reply,
        "collected_updates": updates,
    }
