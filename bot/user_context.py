# -*- coding: utf-8 -*-
"""
Canal y curso de la persona, deducidos del whatsapp_id y del `context` que manda el cliente.

Canal (por prefijo del whatsapp_id):
  "app:<id>"  -> app de AtentaMente
  "edx:<id>"  -> plataforma de cursos (eduNEXT / Open edX)
  otro        -> WhatsApp (número de teléfono)

Curso:
  - `context.course_name` (cualquier canal): nombre legible del curso.
  - `context.course_id` (solo canal edx): id del curso en la plataforma, ej.
    "course-v1:AtentaMente+EPB+2026". Si viene, sabemos que la persona SÍ está en un curso,
    aunque no logremos mapearlo a un curso con contenido cargado.
"""
import re
import unicodedata

CHANNEL_WHATSAPP = "whatsapp"
CHANNEL_APP = "app"
CHANNEL_EDX = "edx"

# course_id de la plataforma -> nombre EXACTO del curso en la base de conocimiento
# (metadata.course de los documentos). Agregar aquí los ids que no se puedan deducir
# del propio id. Las claves se comparan sin mayúsculas, acentos ni signos.
COURSE_ID_ALIASES: dict[str, str] = {}


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


def resolve_course_id(course_id: str | None, known: list[str]) -> str | None:
    """Mapea un course_id de la plataforma a un curso con contenido: primero por
    COURSE_ID_ALIASES, luego si el nombre del curso aparece dentro del id."""
    if not course_id:
        return None
    cid = _compact(course_id)
    for alias, course in COURSE_ID_ALIASES.items():
        if _compact(alias) == cid or _compact(alias) in cid:
            return resolve_course_name(course, known) or course
    # Nombres más largos primero para no confundir "ABCD" con "ABCD Nivel 1"
    for course in sorted(known, key=len, reverse=True):
        if _compact(course) and _compact(course) in cid:
            return course
    return None


def get_course_info(whatsapp_id: str | None, user_context: dict | None, known: list[str]) -> dict:
    """
    {
      "course": nombre exacto con contenido, o None,
      "enrolled": True si sabemos con certeza que la persona está en un curso (edx + course_id),
      "course_id": el id crudo de la plataforma, si vino,
    }
    """
    ctx = user_context or {}
    course = resolve_course_name(ctx.get("course_name"), known)
    course_id = ctx.get("course_id") if get_channel(whatsapp_id) == CHANNEL_EDX else None
    if course_id and not course:
        course = resolve_course_id(course_id, known)
    return {"course": course, "enrolled": bool(course_id), "course_id": course_id}


def find_course_in_text(texts: list[str], known: list[str]) -> str | None:
    """Curso con contenido mencionado por nombre en lo que escribió la persona."""
    blob = _compact(" ".join(texts))
    for course in sorted(known, key=len, reverse=True):
        if _compact(course) and _compact(course) in blob:
            return course
    return None
