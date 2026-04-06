import type {
  ChatCompletionRequest,
  ChatDetail,
  ChatSummary,
  ModelSelectionResponse,
  ModelsResponse,
  StreamChunk,
} from './types'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api'
const API_KEY = import.meta.env.VITE_API_KEY as string | undefined

const baseHeaders: HeadersInit = {
  'Content-Type': 'application/json',
}

if (API_KEY) {
  baseHeaders.Authorization = `Bearer ${API_KEY}`
}

async function requestJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      ...baseHeaders,
      ...(init.headers ?? {}),
    },
  })

  if (!response.ok) {
    const body = await response.text()
    throw new Error(body || `Request failed: ${response.status}`)
  }

  if (response.status === 204) {
    return undefined as T
  }

  return (await response.json()) as T
}

export function getHealth() {
  return requestJson<{ status: string; ollama_reachable: boolean }>('/health')
}

export function listModels() {
  return requestJson<ModelsResponse>('/v1/models')
}

export function getModelSelection() {
  return requestJson<ModelSelectionResponse>('/v1/model-selection')
}

export function setModelSelection(modelId: string) {
  return requestJson<ModelSelectionResponse>('/v1/model-selection', {
    method: 'POST',
    body: JSON.stringify({ model_id: modelId }),
  })
}

export function listChats() {
  return requestJson<ChatSummary[]>('/v1/chats')
}

export function createChat(payload: { title?: string; selected_model_id?: string }) {
  return requestJson<ChatSummary>('/v1/chats', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function getChat(chatId: string) {
  return requestJson<ChatDetail>(`/v1/chats/${chatId}`)
}

export function updateChat(
  chatId: string,
  payload: { title?: string; selected_model_id?: string },
) {
  return requestJson<ChatSummary>(`/v1/chats/${chatId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}

export function deleteChat(chatId: string) {
  return requestJson<void>(`/v1/chats/${chatId}`, {
    method: 'DELETE',
  })
}

export async function streamChatCompletion(
  payload: ChatCompletionRequest,
  onChunk: (chunk: StreamChunk) => void,
): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/v1/chat/completions`, {
    method: 'POST',
    headers: baseHeaders,
    body: JSON.stringify({ ...payload, stream: true }),
  })

  if (!response.ok || !response.body) {
    const body = await response.text()
    throw new Error(body || 'Streaming request failed')
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) {
      break
    }

    buffer += decoder.decode(value, { stream: true })

    let separator = buffer.indexOf('\n\n')
    while (separator !== -1) {
      const rawEvent = buffer.slice(0, separator)
      buffer = buffer.slice(separator + 2)

      if (rawEvent.startsWith('data: ')) {
        const data = rawEvent.slice(6).trim()
        if (data === '[DONE]') {
          onChunk({ done: true })
          return
        }

        const parsed = JSON.parse(data) as {
          choices?: Array<{ delta?: { content?: string } }>
          model?: string
          metadata?: Record<string, unknown>
        }
        const token = parsed.choices?.[0]?.delta?.content
        onChunk({
          token,
          done: false,
          usedModelId: parsed.model,
          metadata: parsed.metadata,
        })
      }

      separator = buffer.indexOf('\n\n')
    }
  }
}
