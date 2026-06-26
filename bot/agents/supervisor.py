"""
Agente B — supervisor de calidad.

Evalúa la respuesta del agente principal de forma asíncrona (fire-and-forget).
Si detecta un problema, genera una lección y la guarda en Supabase.
"""
import json
import asyncio
from openai import AsyncOpenAI
from bot.db.lessons import save_lesson, save_evaluation

SUPERVISOR_MODEL = "gpt-4.1-mini"

SUPERVISOR_PROMPT = """Eres un SUPERVISOR DE CALIDAD que evalúa las respuestas de un agente \
conversacional de AtentaMente.

El agente acompaña a personas a través de 5 fases:
1. Construcción de la micronarrativa
2. Exploración del componente mental
3. Reconocimiento de desequilibrios ABCD
4. Diálogo socrático con conexión a recursos
5. Cierre y retroalimentación

TU TRABAJO: evaluar cada respuesta según:
1. ADHERENCIA AL FLUJO: ¿Respetó las reglas de la fase actual? (una sola pregunta por mensaje, \
máximo de preguntas por fase, no ofrecer prácticas antes de la fase 4, etc.)
2. TONO: ¿Fue empático, socrático, sin juicio?
3. NO INVENCIÓN: ¿Inventó instrucciones de prácticas no sustentadas en materiales?
4. BREVEDAD: ¿Evitó párrafos largos o múltiples preguntas en un mensaje?
5. PERTINENCIA: ¿Respondió lo que el usuario realmente trajo?

CUÁNDO GENERAR UNA LECCIÓN:
- SOLO si hay un problema REAL, ESPECÍFICO y REPETIBLE.
- NO para respuestas que están bien aunque sean perfectibles.
- La lección debe servir en situaciones futuras similares.

FORMATO DE RESPUESTA (JSON puro, sin markdown):
{
  "quality": "buena" | "mejorable" | "incorrecta",
  "problem": "descripción breve del problema o null",
  "reasoning": "tu razonamiento",
  "lesson": {
    "trigger": "tipo de situación en que aplica (no la pregunta exacta)",
    "rule": "acción concreta a tomar",
    "reason": "por qué es importante"
  }
}

Si no hay lección, usa "lesson": null.

SÉ EXIGENTE. Marca como "mejorable" si:
- Hizo más de una pregunta en un mensaje.
- Usó lenguaje vago cuando podría ser específico.
- Ofreció prácticas antes de la fase 4.

Marca como "incorrecta" si:
- Inventó instrucciones de prácticas.
- Avanzó de fase sin cumplir el criterio de salida.
- Hizo referencia explícita a "materiales de AtentaMente"."""


_openai: AsyncOpenAI | None = None


def _get_openai() -> AsyncOpenAI:
    global _openai
    if _openai is None:
        _openai = AsyncOpenAI()
    return _openai


def _extract_json(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1:
        return text[start:end + 1]
    return text


async def evaluate_response(
    message_id: str,
    user_message: str,
    agent_response: str,
    phase: int,
    conversation_history: list[dict],
) -> None:
    """
    Evalúa la respuesta del agente y guarda el resultado en Supabase.
    Se llama con asyncio.create_task() para no bloquear la respuesta al usuario.
    """
    client = _get_openai()

    history_text = "\n".join(
        f"{'Usuario' if m['role'] == 'user' else 'Agente'}: {m['content']}"
        for m in conversation_history[-6:]
    ) or "(primer mensaje)"

    user_prompt = (
        f"FASE ACTUAL: {phase}\n\n"
        f"HISTORIAL RECIENTE:\n{history_text}\n\n"
        f"MENSAJE DEL USUARIO:\n{user_message}\n\n"
        f"RESPUESTA DEL AGENTE A EVALUAR:\n{agent_response}\n\n"
        "Evalúa y devuelve el JSON."
    )

    try:
        response = await client.chat.completions.create(
            model=SUPERVISOR_MODEL,
            messages=[
                {"role": "system", "content": SUPERVISOR_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,
            max_tokens=600,
        )
        raw = response.choices[0].message.content or "{}"
        parsed = json.loads(_extract_json(raw))
    except Exception as e:
        print(f"[Supervisor] Error al evaluar: {e}")
        return

    quality = parsed.get("quality", "buena")
    problem = parsed.get("problem")
    reasoning = parsed.get("reasoning", "")
    lesson_data = parsed.get("lesson")

    lesson_id = None
    if lesson_data and quality != "buena":
        try:
            lesson = save_lesson(
                trigger=lesson_data["trigger"],
                rule=lesson_data["rule"],
                reason=lesson_data["reason"],
            )
            lesson_id = lesson["id"]
            print(f"[Supervisor] ⚠️  Lección guardada: {lesson_data['trigger'][:60]}...")
        except Exception as e:
            print(f"[Supervisor] Error guardando lección: {e}")

    try:
        save_evaluation(
            message_id=message_id,
            quality=quality,
            problem=problem,
            reasoning=reasoning,
            lesson_id=lesson_id,
        )
    except Exception as e:
        print(f"[Supervisor] Error guardando evaluación: {e}")

    if quality != "buena":
        print(f"[Supervisor] {quality.upper()} — {problem}")
    else:
        print(f"[Supervisor] ✓ Respuesta evaluada: buena")
