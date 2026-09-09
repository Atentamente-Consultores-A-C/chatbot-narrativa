# Guide to Connecting an Application to the AtentaMente Remote Bot

This guide explains how to integrate any application with the remote bot over HTTP. The client can be a website, mobile app, backend service, CRM, or another messaging provider. It does not need to use Turn.io, as long as it sends the same JSON payload and maintains a stable identifier for each user.

[Versión en español](./conexion-api-bot-remoto.md)

> Service status verified on September 9, 2026: `https://bot.atentamente.mx/health` returned `HTTP 200` with `{"status":"ok"}`.

## Integration at a Glance

```text
User
  │ writes a message
  ▼
Client application
  │ POST https://bot.atentamente.mx/webhook
  │ Content-Type: application/json
  │
  │ {
  │   "whatsapp_id": "stable-identifier",
  │   "contact_name": "Name",
  │   "message": "User's message"
  │ }
  ▼
Remote bot
  │ HTTP 200
  │ { "reply": "Bot response" }
  ▼
The application displays reply to the user
```

The client application is responsible for capturing the user's message and displaying the response. The bot server maintains the session, message history, and conversation phase.

## Endpoint

```text
POST https://bot.atentamente.mx/webhook
```

Required header:

```http
Content-Type: application/json
```

The endpoint currently does not require an authentication token.

## Request

The application must send this JSON payload on every turn:

```json
{
  "whatsapp_id": "web:user-8f1a2c",
  "contact_name": "Maria",
  "message": "I feel worried"
}
```

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `whatsapp_id` | string | Yes | A unique, stable identifier for the user. It determines which conversation receives the message. |
| `contact_name` | string | No | A name used to personalize the conversation. It may be sent as `""`. It is stored only when the session is created. |
| `message` | string | Yes | The user's text message. It cannot be empty after whitespace is removed. |

### Using `whatsapp_id` Outside WhatsApp

The field name is preserved for compatibility with Turn.io, but the backend does not require it to contain a telephone number. Another application can send its own identifier.

Adding a prefix that identifies the source channel is recommended:

```text
web:550e8400-e29b-41d4-a716-446655440000
mobile:user_18492
crm:contact_7291
telegram:81726354
```

Important rules:

- Always use the same value for the same user and conversation.
- Do not share one identifier between multiple people.
- Do not generate a new identifier for every message; doing so would create independent sessions.
- Include the channel name to prevent collisions when a person uses more than one application.
- Avoid using telephone numbers or email addresses when they are unnecessary. An internal UUID reduces the exposure of personal data.

## Response

### Normal Response

The server returns `HTTP 200` and a JSON object:

```json
{
  "reply": "Thank you for sharing that. What do you notice right now?"
}
```

The application should read `reply` and display it as a bot message.

### Response Without a Message

In some cases, the server returns `HTTP 200` with an empty object:

```json
{}
```

This means there is no response to display. The application must not print `undefined`, `null`, or the field name.

### Invalid Request

If `whatsapp_id` or `message` is missing, the server returns `HTTP 400`:

```json
{
  "detail": "Faltan campos requeridos"
}
```

The error text is currently returned in Spanish and means “Required fields are missing.”

### Internal or Network Error

The application should handle:

- request timeouts;
- DNS or connection errors;
- a response that is not valid JSON;
- any HTTP status outside the `2xx` range;
- JSON without a `reply` property.

Do not retry a `POST` automatically without a limit. The server may have saved the message even if the response was lost, and a retry could duplicate the conversation turn.

## Complete Conversation Lifecycle

### 1. Create or Retrieve the Local Identifier

When opening the chat, the application must obtain the user's stable identifier. It can come from the authenticated account or be generated once and stored locally.

Example for an authenticated user:

```text
whatsapp_id = "web:" + user.id
```

Example for an anonymous user:

```text
whatsapp_id = "web:" + UUID_GENERATED_ONCE
```

### 2. Initialize the Conversation

For a session that does not exist yet, the first request creates the session and returns the welcome message. The current backend does not process the content of this first request as a conversational answer.

A new application should therefore initialize the chat explicitly:

```json
{
  "whatsapp_id": "web:user-8f1a2c",
  "contact_name": "Maria",
  "message": "Hello"
}
```

The application displays the welcome `reply`. Messages from the next request onward are processed as part of the conversation.

### 3. Send Each New Message

Reuse exactly the same `whatsapp_id` for every subsequent turn:

```json
{
  "whatsapp_id": "web:user-8f1a2c",
  "contact_name": "Maria",
  "message": "I have been having trouble concentrating lately"
}
```

While waiting for a response, the interface should temporarily disable the send button or otherwise prevent simultaneous requests for the same user.

### 4. End the Conversation

When the user sends a recognized farewell such as `salir`, `adiós`, `hasta luego`, or `gracias`, the bot marks the conversation as finished and returns one final message. These commands are currently recognized in Spanish.

If the application provides an **End conversation** button, it should send one final request before closing the interface:

```json
{
  "whatsapp_id": "web:user-8f1a2c",
  "contact_name": "Maria",
  "message": "Hasta luego"
}
```

After the conversation has ended:

- sending `Hola` with the same identifier starts a new conversation;
- any other message returns a notice that the previous conversation has already ended.

The restart greeting is also currently recognized in Spanish.

## cURL Example

### Check Service Health

```bash
curl --silent --show-error \
  --write-out '\nHTTP %{http_code}\n' \
  https://bot.atentamente.mx/health
```

Expected result:

```text
{"status":"ok"}
HTTP 200
```

### Send a Message

```bash
curl --silent --show-error \
  --request POST \
  --header 'Content-Type: application/json' \
  --data '{
    "whatsapp_id": "web:user-8f1a2c",
    "contact_name": "Maria",
    "message": "Hola"
  }' \
  https://bot.atentamente.mx/webhook
```

## JavaScript or TypeScript Example

This example is intended for a Node.js backend. `JSON.stringify()` correctly escapes quotation marks, line breaks, and other special characters.

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
    throw new Error("The bot returned a response that is not valid JSON");
  }

  if (!response.ok) {
    throw new Error(data.detail ?? `HTTP error ${response.status}`);
  }

  return typeof data.reply === "string" ? data.reply : null;
}
```

Usage:

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

## Python Example

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

## Postman or Similar Tools

1. Create a `POST` request.
2. Set the URL to `https://bot.atentamente.mx/webhook`.
3. Under **Headers**, add `Content-Type` with the value `application/json`.
4. Under **Body**, select **raw**, then select **JSON**.
5. Paste the following payload:

```json
{
  "whatsapp_id": "postman:test-001",
  "contact_name": "Test",
  "message": "Hola"
}
```

6. Send another request with the same `whatsapp_id` to confirm that the bot retains the conversation context.

Requests to this URL create sessions and messages in the production database. Test identifiers should include `test` or `prueba`, and should never contain unnecessary real user data.

## Integration From a Web Frontend

The current FastAPI application does not configure CORS. A website hosted on another domain should not call `bot.atentamente.mx` directly from the browser, because the browser may block the request.

The recommended architecture is:

```text
Browser or frontend
        │ calls /api/chat on its own domain
        ▼
Application backend
        │ adds the authenticated user identifier
        │ POST https://bot.atentamente.mx/webhook
        ▼
Remote bot
```

This pattern also allows the application backend to:

- derive `whatsapp_id` from the authenticated session instead of trusting a value supplied by the browser;
- apply rate limits;
- control timeouts and errors;
- add authentication when the webhook supports it;
- avoid exposing internal data or future credentials in the frontend.

A native mobile application or server-to-server integration is not subject to browser CORS policy, although it must apply the same security and error-handling measures.

## Turn.io Equivalence

Turn.io calls the bot using the same contract. The Turn.io variables simply map to the three JSON fields:

| Turn.io | Another application |
| --- | --- |
| `@contact.whatsapp_id` | Stable user ID in the application |
| `@contact.name` | Profile name |
| `@event.message.text.body` | Text captured by the interface |
| `@api_response.body.reply` | The `reply` property from the JSON response |

The generic equivalent of the Turn.io request is therefore:

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

## Integration Checklist

- [ ] The application can query `/health`.
- [ ] Every user has a unique, stable identifier.
- [ ] The same identifier is reused for every conversation turn.
- [ ] The application sends `Content-Type: application/json`.
- [ ] The body is serialized with a JSON library instead of string concatenation.
- [ ] The first request initializes the chat and displays the welcome message.
- [ ] The interface displays `reply` only when it is a non-empty string.
- [ ] The application handles `400`, other HTTP errors, timeouts, and non-JSON responses.
- [ ] Simultaneous requests from the same user are prevented.
- [ ] The end-conversation button sends `Hasta luego` before leaving the chat.
- [ ] Tests use recognizable, fictional identifiers.

## Security and Production Considerations

- The current webhook code does not authenticate clients. Before opening the integration to third parties, it should require a token or signature and enforce rate limits.
- The API receives potentially sensitive content. Users should be informed about how their data is processed, and logs should avoid complete names, identifiers, or messages.
- When user authentication is available, the endpoint should be called from the application's backend.
- The client must not be allowed to freely select another person's identifier, as this could mix conversations.
- This contract supports text only. Images, audio, and files require an explicit API extension.
- The webhook does not return a message ID or support an idempotency key. Retries must be conservative.
- Sessions persist in the database. Closing the browser window or reinstalling the client application does not delete the remote history.

## Current Contract Limitations

- The name `whatsapp_id` is historically coupled to WhatsApp, even though it can functionally accept other identifiers.
- The first input for a new session initializes the chat but is not processed as a user response.
- The response contains only `reply`; it does not expose session state, phase, a conversation-ended flag, or a message ID.
- There is no public endpoint specifically for creating, retrieving, resetting, or deleting a session.
- The current implementation does not provide authentication, API versioning, or idempotency protection.

These limitations do not prevent a basic integration. For multiple production applications, the contract should eventually evolve to a versioned route such as `/v1/chat/messages`, with authentication, a `conversation_id`, explicit state, and idempotency support.

The current endpoint implementation is available in [`bot/main.py`](../bot/main.py), and session persistence is implemented in [`bot/db/sessions.py`](../bot/db/sessions.py).
