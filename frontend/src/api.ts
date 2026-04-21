import type {
  AddonCatalogResponse,
  AddonInstallResponse,
  ChatCompletionRequest,
  ChatDetail,
  ChatSummary,
  ModelSelectionResponse,
  ModelsResponse,
  StreamChunk,
  LogEventRecord,
  ChatTelemetryResponse,
  ChatMemoryCompactionResponse,
  UploadChunkResponse,
  UploadRecord,
  UploadStartResponse,
  TtsSynthesisRequest,
} from './types'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api'
const API_KEY = import.meta.env.VITE_API_KEY as string | undefined

const baseHeaders: HeadersInit = {
  'Content-Type': 'application/json',
}

if (API_KEY) {
  baseHeaders.Authorization = `Bearer ${API_KEY}`
}

export function asApiErrorMessage(raw: string, fallback: string): string {
  if (!raw) return fallback
  try {
    const parsed = JSON.parse(raw) as { detail?: string | { error?: string } }
    if (typeof parsed.detail === 'string') {
      return parsed.detail
    }
    if (parsed.detail && typeof parsed.detail === 'object' && 'error' in parsed.detail) {
      const errorText = parsed.detail.error
      if (typeof errorText === 'string') return errorText
    }
  } catch {
    // keep raw
  }
  return raw
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
    throw new Error(asApiErrorMessage(body, `Request failed: ${response.status}`))
  }

  if (response.status === 204) {
    return undefined as T
  }

  return (await response.json()) as T
}

export function getHealth() {
  return requestJson<{ status: string; runtime_reachable: boolean }>('/health')
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

export function createChat(payload: {
  title?: string
  selected_model_id?: string
  inherit_from_chat_id?: string
  inherit_recent_messages?: number
}) {
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

export function compactChatMemory(chatId: string, forgetMessageIds: string[]) {
  return requestJson<ChatMemoryCompactionResponse>(`/v1/chats/${chatId}/memory/compact`, {
    method: 'POST',
    body: JSON.stringify({ forget_message_ids: forgetMessageIds }),
  })
}

export function listAddonCatalog() {
  return requestJson<AddonCatalogResponse>('/v1/addons/catalog')
}

export function listInstalledAddons() {
  return requestJson<AddonInstallResponse[]>('/v1/addons/installed')
}

export function installAddon(addonId: string) {
  return requestJson<AddonInstallResponse>('/v1/addons/install', {
    method: 'POST',
    body: JSON.stringify({ addon_id: addonId }),
  })
}

export function uninstallAddon(addonId: string) {
  return requestJson<AddonInstallResponse>('/v1/addons/uninstall', {
    method: 'POST',
    body: JSON.stringify({ addon_id: addonId }),
  })
}

export function startUpload(payload: { filename: string; total_size_bytes: number; mime_type?: string }) {
  return requestJson<UploadStartResponse>('/v1/files/uploads/start', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function uploadChunk(
  uploadId: string,
  chunk: Blob,
  offset: number,
  isFinal: boolean,
): Promise<UploadChunkResponse> {
  const headers: HeadersInit = {
    ...(API_KEY ? { Authorization: `Bearer ${API_KEY}` } : {}),
    'X-Upload-Offset': String(offset),
    'X-Upload-Complete': isFinal ? 'true' : 'false',
  }
  const response = await fetch(`${API_BASE_URL}/v1/files/uploads/${uploadId}/chunk`, {
    method: 'PUT',
    headers,
    body: chunk,
  })

  if (!response.ok) {
    const body = await response.text()
    throw new Error(asApiErrorMessage(body, `Upload failed: ${response.status}`))
  }
  return (await response.json()) as UploadChunkResponse
}

export function listUploads() {
  return requestJson<UploadRecord[]>('/v1/files/uploads')
}

export function deleteUpload(uploadId: string) {
  return requestJson<void>(`/v1/files/uploads/${uploadId}`, {
    method: 'DELETE',
  })
}

export function listLogEvents(limit = 100) {
  return requestJson<LogEventRecord[]>(`/v1/logs/events?limit=${encodeURIComponent(String(limit))}`)
}

export function createLogEvent(payload: {
  level: 'debug' | 'info' | 'warning' | 'error'
  source: string
  message: string
  chat_id?: string
  context?: Record<string, unknown>
}) {
  return requestJson<LogEventRecord>('/v1/logs/events', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function getChatTelemetry(chatId: string) {
  return requestJson<ChatTelemetryResponse>(`/v1/chats/${chatId}/telemetry`)
}

export async function streamChatCompletion(
  payload: ChatCompletionRequest,
  onChunk: (chunk: StreamChunk) => void,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/v1/chat/completions`, {
    method: 'POST',
    headers: baseHeaders,
    body: JSON.stringify({ ...payload, stream: true }),
    signal,
  })

  if (!response.ok || !response.body) {
    const body = await response.text()
    throw new Error(asApiErrorMessage(body, 'Streaming request failed'))
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

export async function completeChat(payload: ChatCompletionRequest, signal?: AbortSignal): Promise<string> {
  const response = await requestJson<{
    choices?: Array<{ message?: { content?: string } }>
  }>('/v1/chat/completions', {
    method: 'POST',
    body: JSON.stringify({ ...payload, stream: false }),
    signal,
  })
  return response.choices?.[0]?.message?.content ?? ''
}

export async function synthesizeLocalTts(payload: TtsSynthesisRequest, signal?: AbortSignal): Promise<Blob> {
  const response = await fetch(`${API_BASE_URL}/v1/tts/speak`, {
    method: 'POST',
    headers: baseHeaders,
    body: JSON.stringify(payload),
    signal,
  })
  if (!response.ok) {
    const body = await response.text()
    throw new Error(asApiErrorMessage(body, 'Local TTS synthesis failed'))
  }
  return await response.blob()
}
