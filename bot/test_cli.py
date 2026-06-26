"""
Modo de prueba local — simula una conversación completa por terminal.

Uso:
  cd atentamente_fake
  python -m bot.test_cli

Simula exactamente la misma lógica que el webhook de Turn.io,
pero en lugar de recibir un POST HTTP, lee del teclado.

Requiere .env con OPENAI_API_KEY, SUPABASE_URL, SUPABASE_SERVICE_KEY.
"""
import asyncio
import os
import sys
from dotenv import load_dotenv

load_dotenv()

# Usar un ID fijo para pruebas locales (o pasar uno como argumento)
TEST_WHATSAPP_ID = sys.argv[1] if len(sys.argv) > 1 else "test_local_001"
TEST_NAME = "Tester Local"

# Importar después de cargar el .env
from bot.main import handle_message


async def run_cli():
    print("=" * 60)
    print("  AtentaMente Bot — Modo de prueba local")
    print(f"  ID de sesión: {TEST_WHATSAPP_ID}")
    print("  Escribe 'salir' para terminar, 'reset' para nueva sesión.")
    print("=" * 60)
    print()

    # Primer mensaje: activa la bienvenida
    welcome = await handle_message(TEST_WHATSAPP_ID, TEST_NAME, "__init__")
    print(f"\n🤖 Bot:\n{welcome}\n")

    while True:
        try:
            user_input = input("👤 Tú: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\nSesión terminada.")
            break

        if user_input.lower() == "salir":
            print("Hasta luego.")
            break

        if user_input.lower() == "reset":
            from bot.db.sessions import get_or_create_session, update_session
            session = get_or_create_session(TEST_WHATSAPP_ID)
            update_session(session["id"], {"phase": 1, "collected_data": {}})
            print("🔄 Sesión reiniciada.\n")
            welcome = await handle_message(TEST_WHATSAPP_ID, TEST_NAME, "__init__")
            print(f"\n🤖 Bot:\n{welcome}\n")
            continue

        if not user_input:
            continue

        print("   [procesando...]")
        reply = await handle_message(TEST_WHATSAPP_ID, TEST_NAME, user_input)
        print(f"\n🤖 Bot:\n{reply}\n")


if __name__ == "__main__":
    asyncio.run(run_cli())
