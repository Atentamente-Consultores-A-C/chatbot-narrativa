from .client import get_supabase


def get_or_create_session(whatsapp_id: str, contact_name: str | None = None) -> dict:
    sb = get_supabase()
    result = sb.table("sessions").select("*").eq("whatsapp_id", whatsapp_id).execute()

    if result.data:
        return result.data[0]

    new_session = {
        "whatsapp_id": whatsapp_id,
        "contact_name": contact_name,
        "phase": 1,
        "research_consent": None,
        "collected_data": {},
    }
    inserted = sb.table("sessions").insert(new_session).execute()
    return inserted.data[0]


def update_session(session_id: str, updates: dict) -> dict:
    sb = get_supabase()
    result = sb.table("sessions").update(updates).eq("id", session_id).execute()
    return result.data[0]


def advance_phase(session_id: str, current_phase: int) -> int:
    next_phase = current_phase + 1
    update_session(session_id, {"phase": next_phase})
    return next_phase


def update_collected_data(session_id: str, session: dict, new_fields: dict) -> dict:
    merged = {**session.get("collected_data", {}), **new_fields}
    update_session(session_id, {"collected_data": merged})
    return merged
