from .client import get_supabase


def save_message(session_id: str, role: str, content: str, phase: int) -> dict:
    sb = get_supabase()
    result = sb.table("messages").insert({
        "session_id": session_id,
        "role": role,
        "content": content,
        "phase": phase,
    }).execute()
    return result.data[0]


def delete_messages(session_id: str) -> None:
    sb = get_supabase()
    sb.table("messages").delete().eq("session_id", session_id).execute()


def get_history(session_id: str, limit: int = 40) -> list[dict]:
    """Retorna los últimos `limit` mensajes como lista de dicts {role, content}."""
    sb = get_supabase()
    result = (
        sb.table("messages")
        .select("role, content, created_at")
        .eq("session_id", session_id)
        .order("created_at", desc=False)
        .limit(limit)
        .execute()
    )
    return [{"role": m["role"], "content": m["content"]} for m in result.data]
