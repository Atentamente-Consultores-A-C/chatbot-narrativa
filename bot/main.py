"""
FastAPI webhook para Turn.io.

Turn.io envía:
  POST /webhook
  { "message": "...", "whatsapp_id": "...", "contact_name": "..." }

Esperamos de vuelta:
  { "reply": "..." }
"""
import asyncio
import os
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from dotenv import load_dotenv

load_dotenv()

from bot.rag.style_context import get_style_context
from bot.db.sessions import get_or_create_session, update_session, advance_phase, update_collected_data
from bot.db.messages import save_message, get_history
from bot.agents.main_agent import process_message, WELCOME_MESSAGE
from bot.agents.supervisor import evaluate_response

@asynccontextmanager
async def lifespan(app):
    # Precalentar el cache de documentos de comportamiento al arrancar
    style = get_style_context()
    print(f"[Startup] Style context cargado ({len(style)} chars).")
    yield

app = FastAPI(title="AtentaMente Bot", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/webhook")
async def webhook(request: Request):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="JSON inválido")

    whatsapp_id = body.get("whatsapp_id", "").strip()
    contact_name = body.get("contact_name", "")
    user_message = (body.get("message") or "").strip()

    if not whatsapp_id or not user_message:
        raise HTTPException(status_code=400, detail="Faltan campos requeridos")

    reply = await handle_message(whatsapp_id, contact_name, user_message)
    if not reply:
        return JSONResponse({})  # Turn.io no envía nada si no hay "reply"
    return JSONResponse({"reply": reply})


_GREETINGS = {
    "hola", "buenas", "buenos días", "buenos dias", "buenas tardes", "buenas noches",
    "hey", "hi", "hello", "qué tal", "que tal", "saludos", "buen día", "buen dia",
}

def _is_greeting(text: str) -> bool:
    normalized = text.lower().strip("!¡?¿.,")
    return any(normalized.startswith(g) for g in _GREETINGS)


async def handle_message(whatsapp_id: str, contact_name: str, user_message: str) -> str:
    """Lógica central: obtiene sesión, procesa mensaje, guarda en DB, dispara supervisor."""
    session = get_or_create_session(whatsapp_id, contact_name)
    session_id = session["id"]
    phase = session["phase"]

    # Conversación terminada — solo reactivar si el usuario saluda
    if phase > 5:
        if _is_greeting(user_message):
            update_session(session_id, {"phase": 1, "collected_data": {}})
            session["phase"] = 1
            session["collected_data"] = {}
            phase = 1
            save_message(session_id, "assistant", WELCOME_MESSAGE, 1)
            return WELCOME_MESSAGE
        else:
            return ""  # no responder a despedidas o agradecimientos post-cierre

    history = get_history(session_id)

    # Primer contacto (historial vacío o señal de inicio): enviar bienvenida
    is_init = user_message == "__init__" or not history
    if is_init and not history:
        save_message(session_id, "assistant", WELCOME_MESSAGE, phase)
        return WELCOME_MESSAGE
    if is_init:
        # Ya existe historial (sesión recuperada), reenviar el primer mensaje del bot
        first_bot = next((m["content"] for m in history if m["role"] == "assistant"), WELCOME_MESSAGE)
        return first_bot

    # Guardar mensaje del usuario
    user_msg_row = save_message(session_id, "user", user_message, phase)

    # Procesar con el agente principal
    result = await process_message(session, history, user_message)

    reply = result["reply"]
    phase_advanced = result["phase_advanced"]
    conv_ended = result["conversation_ended"]

    # Guardar respuesta del agente
    agent_msg_row = save_message(session_id, "assistant", reply, phase)

    # Actualizar fase si corresponde
    if phase_advanced:
        new_phase = 6 if conv_ended else phase + 1
        update_session(session_id, {"phase": new_phase})

    # Disparar supervisor en background (no bloquea la respuesta)
    asyncio.create_task(
        evaluate_response(
            message_id=agent_msg_row["id"],
            user_message=user_message,
            agent_response=result["raw_reply_for_evaluation"],
            phase=phase,
            conversation_history=history,
        )
    )

    return reply
