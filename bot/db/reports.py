from .client import get_supabase


def save_report(
    reply_text: str,
    sent_at: str,
    reason: str,
    comment: str | None,
    whatsapp_id: str | None,
) -> dict:
    sb = get_supabase()
    result = sb.table("reports").insert({
        "reply_text": reply_text,
        "sent_at": sent_at,
        "reason": reason,
        "comment": comment,
        "whatsapp_id": whatsapp_id,
    }).execute()
    return result.data[0]
