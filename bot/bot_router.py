"""
Clasificación del bot activo a partir del mensaje del usuario.

El usuario elige uno de 3 bots enviando su etiqueta exacta (normalmente vía un menú
de botones que Turn.io presenta antes de llamar a nuestro webhook):

  APOYO EMOCIONAL          -> flujo completo de acompañamiento (bot/agents/main_agent.py)
  DUDAS SOBRE EL CURSO     -> todavía no implementado (bot/agents/stub_agent.py)
  DUDAS SOBRE EL CONTENIDO -> todavía no implementado (bot/agents/stub_agent.py)
"""
import unicodedata

APOYO_EMOCIONAL = "apoyo_emocional"
DUDAS_CURSO = "dudas_curso"
DUDAS_CONTENIDO = "dudas_contenido"

STUB_BOT_TYPES = {DUDAS_CURSO, DUDAS_CONTENIDO}

_LABELS = {
    APOYO_EMOCIONAL: "APOYO EMOCIONAL",
    DUDAS_CURSO: "DUDAS SOBRE EL CURSO",
    DUDAS_CONTENIDO: "DUDAS SOBRE EL CONTENIDO",
}


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return " ".join(text.upper().split())


_NORMALIZED_LABELS = {_normalize(label): bot_type for bot_type, label in _LABELS.items()}


def detect_bot_type(message: str) -> str | None:
    """Retorna el bot_type si el mensaje coincide exactamente (sin importar
    acentos/mayúsculas/espacios extra) con alguna de las 3 etiquetas. None si no."""
    return _NORMALIZED_LABELS.get(_normalize(message))
