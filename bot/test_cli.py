"""
Modo de prueba local — simula una conversación completa por terminal.

Uso:
  python -m bot.test_cli [whatsapp_id]

Comandos especiales durante la conversación:
  salir          -> termina el CLI
  debugg: reset  -> resetea la sesión (nueva conversación, mismo ID)
  debugg: end    -> marca la conversación como terminada (phase 6)
"""
import asyncio
import sys
from dotenv import load_dotenv

load_dotenv()

TEST_WHATSAPP_ID = sys.argv[1] if len(sys.argv) > 1 else "test_local_001"
TEST_NAME = "Tester Local"

from bot.main import handle_message


async def run_cli():
    print("=" * 60)
    print("  AtentaMente Bot — Modo de prueba local")
    print(f"  ID de sesión: {TEST_WHATSAPP_ID}")
    print("  Escribe 'salir' para salir del CLI.")
    print("  Comandos: 'debugg: reset' | 'debugg: end'")
    print("=" * 60)
    print()

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

        if not user_input:
            continue

        print("   [procesando...]")
        reply = await handle_message(TEST_WHATSAPP_ID, TEST_NAME, user_input)
        if reply:
            print(f"\n🤖 Bot:\n{reply}\n")
        else:
            print("   [sin respuesta — despedida o comando procesado]\n")


if __name__ == "__main__":
    asyncio.run(run_cli())
