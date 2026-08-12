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
from bot.db.sessions import get_or_create_session, update_session
from bot.db.messages import save_message, get_history, delete_messages
from bot.agents.main_agent import process_message, WELCOME_MESSAGE
from bot.prompts.phases import get_welcome_message
from bot.agents.supervisor import evaluate_response

# Lock por usuario — evita procesar dos mensajes simultáneos del mismo número
_user_locks: dict[str, asyncio.Lock] = {}

def _get_user_lock(whatsapp_id: str) -> asyncio.Lock:
    if whatsapp_id not in _user_locks:
        _user_locks[whatsapp_id] = asyncio.Lock()
    return _user_locks[whatsapp_id]


@asynccontextmanager
async def lifespan(app):
    style = await asyncio.to_thread(get_style_context)
    print(f"[Startup] Style context cargado ({len(style)} chars).")
    yield

app = FastAPI(title="AtentaMente Bot", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/webhook")
async def webhook(request: Request):
    raw = await request.body()

    try:
        body = await request.json()
    except Exception:
        # JSON inválido — el mensaje probablemente contiene comillas dobles u otros
        # caracteres especiales que Turn.io no escapó al construir el body.
        # Intentamos extraer los campos con regex para no perder el mensaje.
        raw_str = raw.decode("utf-8", errors="replace")
        print(f"[Warning] JSON inválido, intentando extracción por regex: {raw_str[:300]}")
        wid = re.search(r'"whatsapp_id"\s*:\s*"([^"]+)"', raw_str)
        name = re.search(r'"contact_name"\s*:\s*"([^"]*)"', raw_str)
        # Intentamos dos formatos: message antes o después de whatsapp_id
        msg_match = re.search(
            r'"message"\s*:\s*"(.*?)",\s*"whatsapp_id"', raw_str, re.DOTALL
        ) or re.search(
            r'"message"\s*:\s*"(.*?)"\s*\}', raw_str, re.DOTALL
        )
        if not wid:
            return JSONResponse({"reply": "Lo siento, hubo un error procesando tu mensaje. ¿Puedes intentarlo de nuevo?"})
        body = {
            "whatsapp_id": wid.group(1),
            "contact_name": name.group(1) if name else "",
            "message": msg_match.group(1).replace('\\"', '"') if msg_match else "",
        }

    whatsapp_id = (body.get("whatsapp_id") or "").strip()
    contact_name = body.get("contact_name", "")
    user_message = (body.get("message") or "").strip()

    if not whatsapp_id or not user_message:
        raise HTTPException(status_code=400, detail="Faltan campos requeridos")

    async with _get_user_lock(whatsapp_id):
        reply = await handle_message(whatsapp_id, contact_name, user_message)

    # None o "" = no hay respuesta que mostrar.
    # Devolver {} sin clave "reply" — Turn.io no renderiza nada si el campo está ausente
    # (si se devuelve {"reply": ""} Turn.io puede mostrar "@api_response.body.reply" literal).
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
    "salir",
}

_UNRESOLVED_TEMPLATE = re.compile(r"@event\.|@contact\.|{{.*?}}|Starting preview\.\.\.")

def _is_greeting(text: str) -> bool:
    normalized = text.lower().strip("!¡?¿., ")
    return any(normalized.startswith(g) for g in _GREETINGS)

def _is_farewell(text: str) -> bool:
    normalized = text.lower().strip("!¡?¿., ")
    return normalized in _FAREWELLS or any(normalized.startswith(f) for f in _FAREWELLS)

def _is_invalid_template(text: str) -> bool:
    return bool(_UNRESOLVED_TEMPLATE.search(text))

def _parse_debug_command(text: str) -> str | None:
    normalized = text.lower().strip()
    if normalized.startswith("debugg:"):
        return normalized.replace("debugg:", "").strip()
    return None


# ---------------------------------------------------------------------------
# Lógica central
# ---------------------------------------------------------------------------

async def handle_message(whatsapp_id: str, contact_name: str, user_message: str) -> str:
    session = await asyncio.to_thread(get_or_create_session, whatsapp_id, contact_name)
    session_id = session["id"]
    phase = session["phase"]

    if _is_invalid_template(user_message):
        print(f"[Warning] Mensaje con template sin resolver ignorado: {user_message!r}")
        return None

    # Comandos de debug — no se guardan en historial
    debug_cmd = _parse_debug_command(user_message)
    if debug_cmd is not None:
        if debug_cmd == "reset":
            await asyncio.to_thread(update_session, session_id, {"phase": 1, "collected_data": {}})
            await asyncio.to_thread(save_message, session_id, "assistant", WELCOME_MESSAGE, 1)
            print(f"[Debug] Sesión reseteada para {whatsapp_id}")
            return WELCOME_MESSAGE
        elif debug_cmd == "end":
            await asyncio.to_thread(update_session, session_id, {"phase": 6, "collected_data": {}})
            print(f"[Debug] Conversación terminada para {whatsapp_id}")
            return None
        elif debug_cmd == "clear":
            await asyncio.to_thread(delete_messages, session_id)
            await asyncio.to_thread(update_session, session_id, {"phase": 1, "collected_data": {}})
            await asyncio.to_thread(save_message, session_id, "assistant", WELCOME_MESSAGE, 1)
            print(f"[Debug] Historial borrado para {whatsapp_id}")
            return WELCOME_MESSAGE
        else:
            return f"[Debug] Comando desconocido: {debug_cmd!r}. Comandos disponibles: reset, end, clear"

    # Despedidas durante la conversación activa
    if phase <= 5 and _is_farewell(user_message):
        await asyncio.to_thread(update_session, session_id, {"phase": 6})
        print(f"[Info] Despedida detectada, sesión cerrada para {whatsapp_id}")
        return "Cuídate mucho. Aquí estaré cuando me necesites. 🙏"

    # Conversación terminada — solo reactivar si el usuario saluda
    if phase > 5:
        if _is_greeting(user_message):
            await asyncio.to_thread(update_session, session_id, {"phase": 1, "collected_data": {}})
            session["phase"] = 1
            session["collected_data"] = {}
            phase = 1
            welcome = get_welcome_message(session.get("contact_name"))
            await asyncio.to_thread(save_message, session_id, "assistant", welcome, 1)
            return welcome
        else:
            return "Esta conversación ya terminó. Si quieres iniciar una nueva, escríbeme 'Hola'."

    history = await asyncio.to_thread(get_history, session_id)

    # Primer contacto vía CLI
    if user_message == "__init__":
        if not history:
            await asyncio.to_thread(save_message, session_id, "assistant", WELCOME_MESSAGE, phase)
            return WELCOME_MESSAGE
        first_bot = next((m["content"] for m in history if m["role"] == "assistant"), WELCOME_MESSAGE)
        return first_bot

    # Primera vez que el usuario escribe (sin historial previo): mostrar bienvenida.
    # El trigger de Turn.io puede ser cualquier mensaje; la bienvenida ya tiene la
    # pregunta de apertura, así que el usuario responderá a ella naturalmente.
    if not history:
        await asyncio.to_thread(save_message, session_id, "assistant", WELCOME_MESSAGE, phase)
        return WELCOME_MESSAGE

    # Guardar mensaje del usuario
    await asyncio.to_thread(save_message, session_id, "user", user_message, phase)

    # Procesar con el agente principal
    try:
        result = await process_message(session, history, user_message)
    except Exception as e:
        print(f"[Error] process_message falló para {whatsapp_id}: {e}")
        return (
            "Tuve un problema técnico procesando tu mensaje. "
            "¿Puedes intentar enviarlo de nuevo?"
        )

    reply = result["reply"]
    phase_advanced = result["phase_advanced"]
    conv_ended = result["conversation_ended"]

    agent_msg_row = await asyncio.to_thread(save_message, session_id, "assistant", reply, phase)

    if phase_advanced:
        new_phase = 6 if conv_ended else phase + 1
        await asyncio.to_thread(update_session, session_id, {"phase": new_phase})

    def _log_supervisor_error(task):
        if not task.cancelled() and task.exception():
            print(f"[Supervisor] Error no capturado: {task.exception()}")

    task = asyncio.create_task(
        evaluate_response(
            message_id=agent_msg_row["id"],
            user_message=user_message,
            agent_response=result["raw_reply_for_evaluation"],
            phase=phase,
            conversation_history=history,
        )
    )
    task.add_done_callback(_log_supervisor_error)

    return reply
