# API Reference

Base URL:

- Local Compose: `http://localhost:8000`
- Frontend proxy path: `/api`

Auth:

- If `GOI_API_KEY` is set, include `Authorization: Bearer <token>`.

## Health

- `GET /health`
- Returns service status and runtime reachability.

## Model Selection

- `GET /v1/models`
- `GET /v1/model-selection`
- `POST /v1/model-selection`

Request:

```json
{ "model_id": "gemma4_e4b_8bit" }
```

## Chats

- `GET /v1/chats`
- `POST /v1/chats`
- `GET /v1/chats/{chat_id}`
- `PATCH /v1/chats/{chat_id}`
- `DELETE /v1/chats/{chat_id}`

Create body:

```json
{
  "title": "Architecture Session",
  "selected_model_id": "gemma4_26b_a4b_4bit"
}
```

Patch body:

```json
{
  "title": "Renamed Chat",
  "selected_model_id": "gemma4_e4b_8bit"
}
```

## Chat Completions

- `POST /v1/chat/completions`

Body:

```json
{
  "chat_id": "<optional-chat-id>",
  "model": "gemma4_e4b_8bit",
  "stream": true,
  "messages": [
    { "role": "user", "content": "Explain this deployment topology." }
  ]
}
```

Streaming format:

- Server-Sent Events (SSE)
- `data: {...}` chunks
- terminal `data: [DONE]`

Non-streaming response is OpenAI-compatible `chat.completion` JSON.