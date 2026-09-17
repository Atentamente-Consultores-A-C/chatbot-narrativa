# Guía para conectar una aplicación al bot remoto de AtentaMente

Esta guía explica cómo integrar cualquier aplicación con el bot remoto mediante HTTP. La aplicación puede ser un sitio web, una app móvil, un backend, un CRM u otro proveedor de mensajería. No necesita usar Turn.io, siempre que envíe el mismo cuerpo JSON y conserve un identificador estable por usuario.

[English version](./connecting-app-to-remote-bot.md)

> Estado verificado el 9 de septiembre de 2026: `https://bot.atentamente.mx/health` respondió `HTTP 200` con `{"status":"ok"}`.

## Integración en una mirada

```text
Usuario
  │ escribe un mensaje
  ▼
Aplicación cliente
  │ POST https://bot.atentamente.mx/webhook
  │ Content-Type: application/json
  │
  │ {
  │   "whatsapp_id": "identificador-estable",
  │   "contact_name": "Nombre",
  │   "message": "Mensaje del usuario"
  │ }
  ▼
Bot remoto
  │ HTTP 200
  │ { "reply": "Respuesta del bot" }
  ▼
La aplicación muestra reply al usuario
```

La aplicación es responsable de capturar el mensaje y mostrar la respuesta. El servidor del bot se encarga de conservar la sesión, el historial y la fase de la conversación.

## Endpoint

```text
POST https://bot.atentamente.mx/webhook
```

Encabezado obligatorio:

```http
Content-Type: application/json
```

Actualmente el endpoint no requiere un token de autenticación.

## Request

La aplicación debe enviar este JSON en cada turno:

```json
{
  "whatsapp_id": "web:usuario-8f1a2c",
  "contact_name": "María",
  "message": "Me siento preocupada"
}
```

| Campo | Tipo | Obligatorio | Descripción |
| --- | --- | --- | --- |
| `whatsapp_id` | string | Sí | Identificador único y estable del usuario. Determina a qué conversación pertenece el mensaje. |
| `contact_name` | string | No | Nombre para personalizar la conversación. Puede enviarse como `""`. Solo se guarda al crear la sesión. |
| `message` | string | Sí | Mensaje de texto del usuario. No puede quedar vacío después de quitar espacios. |
| `context` | object | No | Datos libres del usuario (nombre de curso, requisitos pendientes, etc.). Ver [El campo `context`](#el-campo-context) abajo. |

### El campo `context`

`context` es un objeto JSON sin esquema fijo: cualquier clave que se envíe se guarda asociada al `whatsapp_id` y se conserva entre turnos, sin necesidad de cambios en el backend cada vez que se agrega una clave nueva.

```json
{
  "whatsapp_id": "web:usuario-8f1a2c",
  "contact_name": "María",
  "message": "DUDAS SOBRE EL CURSO",
  "context": {
    "course_name": "ABCD Nivel 1",
    "enrollment_status": "activo"
  }
}
```

Reglas:

- Es opcional; si no se envía o no es un objeto JSON, se ignora.
- Las claves que se manden se mezclan (merge superficial) con lo que ya se tenía guardado — no hace falta reenviar todas las claves en cada turno, solo las que cambiaron.
- Es compartido entre los 3 bots (apoyo emocional, dudas sobre el curso, dudas sobre el contenido) porque describe al usuario, no a una conversación en particular.
- Todavía no hay una lista fija de claves esperadas: cada bot leerá las que necesite a medida que se implemente.

### Los 3 bots y cómo se elige uno

El bot ya no es uno solo: el primer mensaje de cada conversación debe ser exactamente una de estas 3 etiquetas (normalmente presentadas como botones antes de llegar al webhook; se aceptan sin distinguir mayúsculas/minúsculas ni acentos):

- `APOYO EMOCIONAL` — el flujo de acompañamiento de siempre (5 fases).
- `DUDAS SOBRE EL CURSO` — todavía no implementado.
- `DUDAS SOBRE EL CONTENIDO` — todavía no implementado.

Comportamiento:

- Si el mensaje coincide con una de las 3 etiquetas, esa pasa a ser la conversación activa para ese `whatsapp_id`. Cada una de las 3 mantiene su propio historial y estado, independiente de las otras — un mismo usuario puede tener una conversación de apoyo emocional en curso y, en otro momento, elegir "dudas sobre el curso" sin perder el progreso de la primera.
- Si el mensaje no coincide con ninguna etiqueta, se usa la conversación activa más reciente para ese usuario; si nunca eligió ninguna, se asume `APOYO EMOCIONAL`.
- `DUDAS SOBRE EL CURSO` y `DUDAS SOBRE EL CONTENIDO` responden una sola vez con un mensaje fijo de "no disponible todavía" y después ya no responden nada más, hasta que el usuario vuelva a mandar explícitamente una de las 3 etiquetas.

### El campo `whatsapp_id` en aplicaciones que no usan WhatsApp

El nombre del campo se conserva por compatibilidad con Turn.io, pero el backend no valida que contenga un número telefónico. Otra aplicación puede enviar su propio identificador.

Se recomienda agregar un prefijo que identifique el canal:

```text
web:550e8400-e29b-41d4-a716-446655440000
mobile:usuario_18492
crm:contacto_7291
telegram:81726354
```

Reglas importantes:

- Usar siempre el mismo valor para el mismo usuario y la misma conversación.
- No compartir un identificador entre dos personas.
- No generar un identificador nuevo en cada mensaje; eso crearía sesiones independientes.
- Incluir el nombre del canal evita colisiones si una persona usa más de una aplicación.
- Evitar teléfonos o correos cuando no sean necesarios. Un UUID interno reduce la exposición de datos personales.

## Response

### Respuesta normal

El servidor devuelve `HTTP 200` y un objeto JSON:

```json
{
  "reply": "Gracias por compartirlo. ¿Qué notas en este momento?"
}
```

La aplicación debe leer `reply` y mostrarlo como un mensaje del bot.

### Respuesta sin mensaje

En algunos casos el servidor devuelve `HTTP 200` con un objeto vacío:

```json
{}
```

Esto significa que no hay una respuesta que mostrar. La aplicación no debe imprimir `undefined`, `null` ni el nombre del campo.

### Request inválido

Si faltan `whatsapp_id` o `message`, el servidor devuelve `HTTP 400`:

```json
{
  "detail": "Faltan campos requeridos"
}
```

### Error interno o de red

La aplicación debe contemplar:

- timeout;
- error de DNS o conexión;
- respuesta que no sea JSON;
- código HTTP distinto de `2xx`;
- JSON sin la propiedad `reply`.

No conviene reintentar automáticamente un `POST` sin límite. El servidor pudo haber guardado el mensaje aunque la respuesta se perdiera, y un reintento podría duplicar el turno.

## Ciclo completo de una conversación

### 1. Crear o recuperar el identificador local

Al iniciar el chat, la aplicación debe obtener el identificador estable del usuario. Puede venir de la cuenta autenticada o generarse una vez y guardarse localmente.

Ejemplo para un usuario autenticado:

```text
whatsapp_id = "web:" + usuario.id
```

Ejemplo para un usuario anónimo:

```text
whatsapp_id = "web:" + UUID_GENERADO_UNA_SOLA_VEZ
```

### 2. Inicializar la conversación

El primer mensaje de una conversación nueva debería ser una de las 3 etiquetas de bot (ver [Los 3 bots y cómo se elige uno](#los-3-bots-y-cómo-se-elige-uno)). El backend crea la sesión correspondiente y no procesa ese primer mensaje como una respuesta conversacional; solo decide qué bot atiende.

Por ello, una app nueva debería inicializar el chat explícitamente con una etiqueta válida:

```json
{
  "whatsapp_id": "web:usuario-8f1a2c",
  "contact_name": "María",
  "message": "APOYO EMOCIONAL"
}
```

Si se envía cualquier otro texto (por ejemplo "Hola") como primer mensaje, el backend lo trata igual que si no hubiera elegido bot y asume `APOYO EMOCIONAL` por default — pero para las apps nuevas es más explícito y confiable mandar la etiqueta.

La aplicación muestra el `reply` de bienvenida. A partir de la siguiente llamada, los mensajes ya se procesan dentro de la conversación.

### 3. Enviar cada nuevo mensaje

Para cada turno posterior, se reutiliza exactamente el mismo `whatsapp_id`:

```json
{
  "whatsapp_id": "web:usuario-8f1a2c",
  "contact_name": "María",
  "message": "Últimamente me cuesta concentrarme"
}
```

Mientras espera la respuesta, la interfaz debería deshabilitar temporalmente el botón de envío o impedir dos solicitudes simultáneas para el mismo usuario.

### 4. Terminar la conversación

Si el usuario escribe una despedida reconocida, como `salir`, `adiós`, `hasta luego` o `gracias`, el bot marca la conversación como terminada y devuelve un último mensaje.

Si la app tiene un botón **Cerrar conversación**, debe enviar una última petición antes de cerrar la interfaz:

```json
{
  "whatsapp_id": "web:usuario-8f1a2c",
  "contact_name": "María",
  "message": "Hasta luego"
}
```

Una vez terminada:

- enviar `Hola` con el mismo identificador inicia una conversación nueva;
- cualquier otro mensaje recibe un aviso de que la conversación anterior ya terminó.

## Ejemplo con cURL

### Verificar el servicio

```bash
curl --silent --show-error \
  --write-out '\nHTTP %{http_code}\n' \
  https://bot.atentamente.mx/health
```

Resultado esperado:

```text
{"status":"ok"}
HTTP 200
```

### Enviar un mensaje

```bash
curl --silent --show-error \
  --request POST \
  --header 'Content-Type: application/json' \
  --data '{
    "whatsapp_id": "web:usuario-8f1a2c",
    "contact_name": "María",
    "message": "Hola"
  }' \
  https://bot.atentamente.mx/webhook
```

## Ejemplo con JavaScript o TypeScript

Este ejemplo está pensado para un backend en Node.js. `JSON.stringify()` escapa correctamente comillas, saltos de línea y otros caracteres especiales.

```js
const BOT_URL = "https://bot.atentamente.mx/webhook";

export async function sendMessageToBot({ userId, name, message }) {
  const response = await fetch(BOT_URL, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      whatsapp_id: `web:${userId}`,
      contact_name: name ?? "",
      message,
    }),
    signal: AbortSignal.timeout(20_000),
  });

  let data;
  try {
    data = await response.json();
  } catch {
    throw new Error("El bot devolvió una respuesta que no es JSON");
  }

  if (!response.ok) {
    throw new Error(data.detail ?? `Error HTTP ${response.status}`);
  }

  return typeof data.reply === "string" ? data.reply : null;
}
```

Uso:

```js
const reply = await sendMessageToBot({
  userId: currentUser.id,
  name: currentUser.name,
  message: userInput,
});

if (reply) {
  addMessage({ author: "bot", text: reply });
}
```

## Ejemplo con Python

```python
import httpx

BOT_URL = "https://bot.atentamente.mx/webhook"


async def send_message_to_bot(user_id: str, name: str, message: str) -> str | None:
    payload = {
        "whatsapp_id": f"app:{user_id}",
        "contact_name": name,
        "message": message,
    }

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(BOT_URL, json=payload)

    response.raise_for_status()
    data = response.json()
    reply = data.get("reply")
    return reply if isinstance(reply, str) else None
```

## Configuración en Postman o herramientas similares

1. Crear una petición `POST`.
2. Usar la URL `https://bot.atentamente.mx/webhook`.
3. En **Headers**, agregar `Content-Type` con valor `application/json`.
4. En **Body**, seleccionar **raw** y después **JSON**.
5. Pegar el siguiente cuerpo:

```json
{
  "whatsapp_id": "postman:prueba-001",
  "contact_name": "Prueba",
  "message": "Hola"
}
```

6. Enviar otra petición con el mismo `whatsapp_id` para comprobar que el bot conserva el contexto.

Las pruebas contra esta URL crean sesiones y mensajes en la base de datos de producción. Se deben utilizar identificadores que incluyan `prueba` o `test` y nunca datos reales innecesarios.

## Integración desde un frontend web

La aplicación FastAPI actual no configura CORS. Un sitio web servido desde otro dominio no debería llamar directamente a `bot.atentamente.mx` desde el navegador, porque el navegador puede bloquear la solicitud.

La arquitectura recomendada es:

```text
Navegador o frontend
        │ llama a /api/chat en su propio dominio
        ▼
Backend de la aplicación
        │ agrega el identificador del usuario
        │ POST https://bot.atentamente.mx/webhook
        ▼
Bot remoto
```

Este patrón también permite que el backend:

- derive `whatsapp_id` de la sesión autenticada en lugar de confiar en un valor enviado por el navegador;
- aplique límites de frecuencia;
- controle timeouts y errores;
- agregue autenticación cuando el webhook la implemente;
- evite exponer datos internos o credenciales futuras en el frontend.

Una app móvil nativa o una integración servidor a servidor no está sujeta a la política CORS del navegador, aunque debe aplicar las mismas medidas de seguridad y manejo de errores.

## Equivalencia con Turn.io

Turn.io llama al bot con el mismo contrato. Las variables de Turn.io simplemente se convierten en los tres campos del JSON:

| Turn.io | Otra aplicación |
| --- | --- |
| `@contact.whatsapp_id` | ID estable del usuario en la app |
| `@contact.name` | Nombre del perfil |
| `@event.message.text.body` | Texto capturado en la interfaz |
| `@api_response.body.reply` | Propiedad `reply` de la respuesta JSON |

Por lo tanto, el equivalente genérico de la llamada de Turn.io es:

```js
await fetch("https://bot.atentamente.mx/webhook", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    whatsapp_id: stableUserId,
    contact_name: userName,
    message: userMessage,
  }),
});
```

## Lista de verificación

- [ ] La app puede consultar `/health`.
- [ ] Cada usuario tiene un identificador único y estable.
- [ ] El mismo identificador se reutiliza en todos los turnos.
- [ ] La app envía `Content-Type: application/json`.
- [ ] El cuerpo se serializa con una librería JSON, no concatenando strings.
- [ ] La primera llamada inicializa el chat y muestra la bienvenida.
- [ ] La interfaz muestra `reply` únicamente cuando es un string no vacío.
- [ ] La app maneja `400`, otros errores HTTP, timeout y respuestas no JSON.
- [ ] Se evitan solicitudes simultáneas del mismo usuario.
- [ ] El botón de cierre envía `Hasta luego` antes de abandonar el chat.
- [ ] Las pruebas utilizan identificadores ficticios y reconocibles.

## Consideraciones de seguridad y producción

- El código actual del webhook no autentica al cliente. Antes de abrir la integración a terceros se recomienda exigir un token o firma y aplicar límites de frecuencia.
- La API recibe contenido sensible. Se debe informar al usuario sobre su tratamiento y evitar registrar nombres, identificadores o mensajes completos.
- El endpoint debe invocarse desde el backend de la aplicación cuando exista autenticación de usuarios.
- No se debe permitir que el cliente elija libremente el identificador de otra persona; eso podría mezclar conversaciones.
- El servidor solo admite texto en este contrato. Imágenes, audio y archivos requieren una extensión explícita de la API.
- El webhook no devuelve un ID de mensaje ni una clave de idempotencia. Los reintentos deben ser conservadores.
- La sesión persiste en la base de datos. Cerrar la ventana o reinstalar la app no borra el historial remoto.

## Limitaciones actuales del contrato

- El nombre `whatsapp_id` está acoplado históricamente a WhatsApp, aunque funcionalmente admite otros identificadores.
- La primera entrada de una sesión nueva inicia el chat, pero no se procesa como respuesta del usuario.
- La respuesta solo contiene `reply`; no expone estado de sesión, fase, indicador de conversación terminada ni ID del mensaje.
- No existe un endpoint público específico para crear, consultar, reiniciar o eliminar una sesión.
- No hay autenticación, versionado de API ni protección de idempotencia en la implementación actual.

Estas limitaciones no impiden una integración básica. Para integrar múltiples aplicaciones en producción, convendría evolucionar el contrato a una ruta versionada, por ejemplo `/v1/chat/messages`, con autenticación, `conversation_id`, estado explícito e idempotencia.

La implementación actual del endpoint está en [`bot/main.py`](../bot/main.py), y la persistencia de sesiones en [`bot/db/sessions.py`](../bot/db/sessions.py).
