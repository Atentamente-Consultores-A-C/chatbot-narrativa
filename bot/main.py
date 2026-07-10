"""
FastAPI webhook para Turn.io.

Turn.io envia:
  POST /webhook
  { "message": "...", "whatsapp_id": "...", "contact_name": "..." }

Esperamos de vuelta:
  { "reply": "..." }
"""
import asyncio
import re
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from dotenv import load_dotenv

load_dotenv()

from bot.rag.style_context import get_style_context
from bot.db.sessions import get_or_create_session, update_session, advance_phase, update_collected_data
from bot.db.messages import save_message, get_history, delete_messages
from bot.agents.main_agent import process_message, WELCOME_MESSAGE
from bot.agents.supervisor import evaluate_response

@asynccontextmanager
async def lifespan(app):
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
        raise HTTPException(status_code=400, detail="JSON invalido")

    whatsapp_id = body.get("whatsapp_id", "").strip()
    contact_name = body.get("contact_name", "")
    user_message = (body.get("message") or "").strip()

    if not whatsapp_id or not user_message:
        raise HTTPException(status_code=400, detail="Faltan campos requeridos")

    reply = await handle_message(whatsapp_id, contact_name, user_message)
    if not reply:
        return JSONResponse({})
    return JSONResponse({"reply": reply})


# ---------------------------------------------------------------------------
# Detección de mensajes especiales
# ---------------------------------------------------------------------------

_GREETINGS = {
    "hola", "buenas", "buenos días", "buenos dias", "buenas tardes", "buenas noches",
    "hey", "hi", "hello", "qué tal", "que tal", "saludos", "buen día", "buen dia",
}

_FAREWELLS = {
    "adiós", "adios", "hasta luego", "hasta pronto", "nos vemos", "bye", "chao", "chau",
    "ok gracias", "ok, gracias", "gracias", "muchas gracias", "de nada", "entendido",
    "perfecto gracias", "listo gracias", "hasta la próxima", "hasta la proxima",
    "no gracias", "no, gracias", "ya gracias", "ya, gracias",
    # Turn.io envía "salir" cuando el usuario elige salir desde el flujo
    "salir",
}

# Mensajes inválidos de Turn.io con template sin resolver
_UNRESOLVED_TEMPLATE = re.compile(r"@event\.|@contact\.|{{.*?}}")

def _is_greeting(text: str) -> bool:
    normalized = text.lower().strip("!¡?¿., ")
    return any(normalized.startswith(g) for g in _GREETINGS)

def _is_farewell(text: str) -> bool:
    normalized = text.lower().strip("!¡?¿., ")
    return normalized in _FAREWELLS or any(normalized.startswith(f) for f in _FAREWELLS)

def _is_invalid_template(text: str) -> bool:
    return bool(_UNRESOLVED_TEMPLATE.search(text))

def _parse_debug_command(text: str) -> str | None:
    """Retorna el comando de debug si el mensaje es un comando, o None."""
    normalized = text.lower().strip()
    if normalized.startswith("debugg:"):
        return normalized.replace("debugg:", "").strip()
    return None


# ---------------------------------------------------------------------------
# Lógica central
# ---------------------------------------------------------------------------

async def handle_message(whatsapp_id: str, contact_name: str, user_message: str) -> str:
    session = get_or_create_session(whatsapp_id, contact_name)
    session_id = session["id"]
    phase = session["phase"]

    # Ignorar mensajes con templates sin resolver de Turn.io
    if _is_invalid_template(user_message):
        print(f"[Warning] Mensaje con template sin resolver ignorado: {user_message!r}")
        return ""

    # Comandos de debug — no se guardan en historial
    debug_cmd = _parse_debug_command(user_message)
    if debug_cmd is not None:
        if debug_cmd == "reset":
            update_session(session_id, {"phase": 1, "collected_data": {}})
            save_message(session_id, "assistant", WELCOME_MESSAGE, 1)
            print(f"[Debug] Sesión reseteada para {whatsapp_id}")
            return WELCOME_MESSAGE
        elif debug_cmd == "end":
            update_session(session_id, {"phase": 6, "collected_data": {}})
            print(f"[Debug] Conversación terminada para {whatsapp_id}")
            return ""
        elif debug_cmd == "clear":
            delete_messages(session_id)
            update_session(session_id, {"phase": 1, "collected_data": {}})
            save_message(session_id, "assistant", WELCOME_MESSAGE, 1)
            print(f"[Debug] Historial borrado para {whatsapp_id}")
            return WELCOME_MESSAGE
        else:
            return f"[Debug] Comando desconocido: {debug_cmd!r}. Comandos disponibles: reset, end, clear"

    # Despedidas durante la conversación activa — cerrar con mensaje breve
    if phase <= 5 and _is_farewell(user_message):
        update_session(session_id, {"phase": 6})
        print(f"[Info] Despedida detectada, sesión cerrada para {whatsapp_id}")
        return "Cuídate mucho. Aquí estaré cuando me necesites. 🙏"

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
            return ""

    history = get_history(session_id)

    # Primer contacto
    if user_message == "__init__":
        if not history:
            save_message(session_id, "assistant", WELCOME_MESSAGE, phase)
            return WELCOME_MESSAGE
        first_bot = next((m["content"] for m in history if m["role"] == "assistant"), WELCOME_MESSAGE)
        return first_bot

    # Primera vez que el usuario escribe (sin historial previo): devolver bienvenida.
    # Su mensaje se pierde intencionalmente — Turn.io arranca el flow con el primer mensaje
    # del usuario, y la bienvenida ya contiene la pregunta de apertura.
    if not history:
        save_message(session_id, "assistant", WELCOME_MESSAGE, phase)
        return WELCOME_MESSAGE

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

    # Disparar supervisor en background
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
