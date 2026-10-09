from .client import get_supabase


def get_or_create_contact(whatsapp_id: str, contact_name: str | None = None) -> dict:
    """Un contacto por número de WhatsApp. Guarda qué bot está activo (active_bot_type)
    y datos libres del usuario (context) que se comparten entre los 3 bots."""
    sb = get_supabase()
    result = sb.table("contacts").select("*").eq("whatsapp_id", whatsapp_id).execute()

    if result.data:
        return result.data[0]

    new_contact = {
        "whatsapp_id": whatsapp_id,
        "contact_name": contact_name,
        "active_bot_type": None,
        "context": {},
    }
    inserted = sb.table("contacts").insert(new_contact).execute()
    return inserted.data[0]


def update_contact(whatsapp_id: str, updates: dict) -> dict:
    sb = get_supabase()
    result = sb.table("contacts").update(updates).eq("whatsapp_id", whatsapp_id).execute()
    return result.data[0]


def merge_contact_context(whatsapp_id: str, contact: dict, new_fields: dict) -> dict:
    """Mezcla claves libres (nombre de curso, etc.) sin importar cuáles sean todavía."""
    merged = {**contact.get("context", {}), **new_fields}
    update_contact(whatsapp_id, {"context": merged})
    return merged
