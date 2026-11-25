# -*- coding: utf-8 -*-
"""
Canal, curso, programa y perfil de la persona, deducidos del whatsapp_id y del `context`
que manda el cliente.

Canal (por prefijo del whatsapp_id):
  "app:<id>"  -> app de AtentaMente
  "edx:<id>"  -> plataforma de cursos (eduNEXT / Open edX)
  otro        -> WhatsApp (número de teléfono)

Curso:
  - `context.course_name` (cualquier canal): nombre legible del curso.
  - `context.course_id` (solo canal edx): id del curso en Open edX, ej.
    "course-v1:Atentamente+CC204+2026_PIBSE_Estudiantes_Chiapas". Se toma el código "CCnnn".
  - `context.course_stage` (lo manda la app): curso + última sesión, ej. "CC101-S2".
    También se acepta el formato "M101-S2".
  Con cualquiera de los dos sabemos que la persona SÍ está en un curso y no se le pregunta.

Programa: decide el flujo de la conversación.
  - PIBSE -> flujo ABCD (4 desequilibrios).
  - EPB   -> flujo de competencias socioemocionales (emoción, botón, herramientas del curso).
"""
import re
import unicodedata

CHANNEL_WHATSAPP = "whatsapp"
CHANNEL_APP = "app"
CHANNEL_EDX = "edx"

PROGRAM_EPB = "EPB"
PROGRAM_PIBSE = "PIBSE"
# Flujo para quien no sabemos en qué programa está (incluye CC104-CC107).
DEFAULT_PROGRAM = PROGRAM_EPB

# Códigos de curso de Open edX. "rag" = nombre EXACTO del curso en la base de conocimiento
# (metadata.course); None si ese curso todavía no tiene contenido cargado.
COURSE_CODES: dict[str, dict] = {
    "CC100": {"name": "EPB Taller Introductorio", "program": PROGRAM_EPB, "module": 0, "rag": "Educar para el Bienestar"},
    "CC101": {"name": "Educar para el Bienestar, Módulo 1", "program": PROGRAM_EPB, "module": 1, "rag": "Educar para el Bienestar"},
    "CC102": {"name": "Educar para el Bienestar, Módulo 2", "program": PROGRAM_EPB, "module": 2, "rag": "Educar para el Bienestar"},
    "CC103": {"name": "Educar para el Bienestar, Módulo 3", "program": PROGRAM_EPB, "module": 3, "rag": "Educar para el Bienestar"},
    "CC104": {"name": "Formación de Liderazgo Sistémico", "program": None, "module": None, "rag": None},
    "CC105": {"name": "Acompañamiento", "program": None, "module": None, "rag": None},
    "CC106": {"name": "Psiconautas", "program": None, "module": None, "rag": None},
    "CC107": {"name": "Maya Socioemocional", "program": None, "module": None, "rag": None},
    "CC201": {"name": "PIBSE Educadores", "program": PROGRAM_PIBSE, "module": None, "rag": "PIBSE Educadores"},
    "CC202": {"name": "PIBSE FLS", "program": PROGRAM_PIBSE, "module": None, "rag": None},
    "CC203": {"name": "PIBSE Tutores", "program": PROGRAM_PIBSE, "module": None, "rag": None},
    "CC204": {"name": "PIBSE Estudiantes", "program": PROGRAM_PIBSE, "module": None, "rag": None},
    "CC303": {"name": "PIBSE Salud", "program": PROGRAM_PIBSE, "module": None, "rag": "PIBSE Salud"},
    "CC304": {"name": "PIBSE Cuidar", "program": PROGRAM_PIBSE, "module": None, "rag": None},
}

# course_id que no siguen el formato CCnnn -> código CCnnn. Las claves se comparan sin
# mayúsculas, acentos ni signos.
COURSE_ID_ALIASES: dict[str, str] = {}

_CODE_RE = re.compile(r"CC(\d{3})", re.IGNORECASE)
# "CC101-S2" (course_stage de la app) o "M101-S2"
_SESSION_RE = re.compile(r"\b(?:CC|M)(\d{3})-S(\d+)\b", re.IGNORECASE)

# Datos del perfil que SÍ se le muestran al modelo (lista cerrada: nada de CURP, correo,
# teléfono, ids, etc.). clave canónica -> claves aceptadas en `context`.
PROFILE_FIELDS: dict[str, tuple[str, ...]] = {
    "nombre": ("nombre", "name", "first_name", "contact_name"),
    "edad": ("edad", "age"),
    "género": ("genero", "género", "gender", "sexo"),
    "ocupación": ("ocupacion", "ocupación", "occupation", "rol", "role", "puesto", "cargo"),
    "lugar de trabajo": ("escuela", "school", "centro_de_trabajo", "lugar_de_trabajo", "workplace"),
    "estado": ("estado", "entidad", "state"),
}


def get_channel(whatsapp_id: str | None) -> str:
    wid = (whatsapp_id or "").strip().lower()
    if wid.startswith("app:"):
        return CHANNEL_APP
    if wid.startswith("edx:"):
        return CHANNEL_EDX
    return CHANNEL_WHATSAPP


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode("ascii")
    return " ".join(text.lower().split())


def _compact(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", _norm(text))


def resolve_course_name(name: str | None, known: list[str]) -> str | None:
    """Nombre exacto de `known` que coincide con `name` (sin mayúsculas ni acentos)."""
    if not name:
        return None
    target = _norm(name)
    return next((c for c in known if _norm(c) == target), None)


def parse_course_code(course_id: str | None) -> str | None:
    """'CC101', 'course-v1:X+CC101+2026' o 'M101-S1' -> 'CC101'. None si no se reconoce."""
    if not course_id:
        return None
    text = str(course_id)
    cid = _compact(text)
    for alias, code in COURSE_ID_ALIASES.items():
        if _compact(alias) == cid:
            return code.upper()
    match = _CODE_RE.search(text)
    if match and f"CC{match.group(1)}" in COURSE_CODES:
        return f"CC{match.group(1)}"
    match = _SESSION_RE.search(text)
    if match and f"CC{match.group(1)}" in COURSE_CODES:
        return f"CC{match.group(1)}"
    return None


def parse_last_session(user_context: dict | None) -> tuple[str | None, int | None]:
    """Lee `course_stage` ("CC101-S2"): (código CCnnn, número de la última sesión)."""
    value = (user_context or {}).get("course_stage")
    if isinstance(value, str):
        match = _SESSION_RE.search(value)
        if match and f"CC{match.group(1)}" in COURSE_CODES:
            return f"CC{match.group(1)}", int(match.group(2))
    return None, None


def program_from_name(name: str | None) -> str | None:
    n = _norm(name or "")
    if "pibse" in n:
        return PROGRAM_PIBSE
    if "educar para el bienestar" in n or "educar desde el bienestar" in n or re.search(r"\bepb\b", n):
        return PROGRAM_EPB
    return None


def get_course_info(whatsapp_id: str | None, user_context: dict | None, known: list[str]) -> dict:
    """
    {
      "course":      curso con contenido cargado (para filtrar el RAG), o None,
      "course_label": nombre legible del curso para el prompt, o None,
      "program":     "EPB" | "PIBSE" | None (None = no sabemos),
      "module":      módulo de EPB (0 = taller introductorio), o None,
      "session":     última sesión completada, o None,
      "enrolled":    True si sabemos con certeza que está en un curso (course_id en edx o
                     course_stage),
      "course_id":   el valor crudo de la plataforma, si vino,
    }
    """
    ctx = user_context or {}
    info = {
        "course": None, "course_label": None, "program": None, "module": None,
        "session": None, "enrolled": False, "course_id": None,
    }

    course_id = ctx.get("course_id") if get_channel(whatsapp_id) == CHANNEL_EDX else None
    code = parse_course_code(course_id)
    session_code, session = parse_last_session(ctx)
    code = code or session_code
    if course_id:
        info["course_id"] = course_id
    if course_id or session_code:
        info["enrolled"] = True
    if code:
        entry = COURSE_CODES[code]
        info.update(
            course=resolve_course_name(entry["rag"], known) if entry["rag"] else None,
            course_label=entry["name"],
            program=entry["program"],
            module=entry["module"],
        )
        if session_code == code:
            info["session"] = session

    name = ctx.get("course_name")
    if name:
        info["course"] = info["course"] or resolve_course_name(name, known)
        info["course_label"] = info["course_label"] or str(name)
        info["program"] = info["program"] or program_from_name(name)
    if info["course"] and not info["program"]:
        info["program"] = program_from_name(info["course"])
    return info


def find_course_in_text(texts: list[str], known: list[str]) -> str | None:
    """Curso con contenido mencionado por nombre en lo que escribió la persona."""
    blob = _compact(" ".join(texts))
    for course in sorted(known, key=len, reverse=True):
        if _compact(course) and _compact(course) in blob:
            return course
    return None


def get_profile(user_context: dict | None, contact_name: str | None = None) -> dict:
    """Solo los datos de PROFILE_FIELDS, con nombres de clave canónicos."""
    ctx = {_norm(k).replace(" ", "_"): v for k, v in (user_context or {}).items()}
    profile = {}
    for field, keys in PROFILE_FIELDS.items():
        for key in keys:
            value = ctx.get(_norm(key).replace(" ", "_"))
            if value not in (None, "", [], {}):
                profile[field] = str(value)[:120]
                break
    if "nombre" not in profile and contact_name and not contact_name.startswith("@"):
        profile["nombre"] = contact_name
    return profile


def format_profile(profile: dict) -> str:
    return "\n".join(f"- {k}: {v}" for k, v in profile.items()) or "(sin datos)"
