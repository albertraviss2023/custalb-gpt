import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import App from './App'

const apiMocks = vi.hoisted(() => ({
  asApiErrorMessage: vi.fn((raw: string, fallback: string) => raw || fallback),
  compactChatMemory: vi.fn(),
  completeChat: vi.fn(),
  createLogEvent: vi.fn(),
  createChat: vi.fn(),
  deleteUpload: vi.fn(),
  deleteChat: vi.fn(),
  getChat: vi.fn(),
  getChatTelemetry: vi.fn(),
  getHealth: vi.fn(),
  listAddonCatalog: vi.fn(),
  listChats: vi.fn(),
  listModels: vi.fn(),
  listUploads: vi.fn(),
  setModelSelection: vi.fn(),
  startUpload: vi.fn(),
  streamChatCompletion: vi.fn(),
  updateChat: vi.fn(),
  uploadChunk: vi.fn(),
}))

vi.mock('./api', () => apiMocks)

const nowIso = '2026-04-09T16:00:00.000Z'

describe('App chat route restore', () => {
  let container: HTMLDivElement
  let root: Root

  beforeEach(() => {
    vi.clearAllMocks()
    window.history.replaceState({}, '', '/chat/chat-2')

    apiMocks.listModels.mockResolvedValue({
      default_model_id: 'gemma4_e4b',
      models: [
        {
          id: 'gemma4_e4b',
          display_name: 'Gemma 4 E4B (Default)',
          quantization: 'q4',
          tier: 'balanced',
          description: 'default',
          runtime_ref: 'gemma4:e4b',
          available: true,
        },
      ],
    })
    apiMocks.listChats.mockResolvedValue([
      {
        id: 'chat-1',
        title: 'Chat One',
        selected_model_id: 'gemma4_e4b',
        created_at: nowIso,
        updated_at: nowIso,
      },
      {
        id: 'chat-2',
        title: 'Restored Chat',
        selected_model_id: 'gemma4_e4b',
        created_at: nowIso,
        updated_at: nowIso,
      },
    ])
    apiMocks.getHealth.mockResolvedValue({ status: 'ok', runtime_reachable: true })
    apiMocks.listAddonCatalog.mockResolvedValue({ addons: [] })
    apiMocks.listUploads.mockResolvedValue([])
    apiMocks.getChat.mockResolvedValue({
      id: 'chat-2',
      title: 'Restored Chat',
      selected_model_id: 'gemma4_e4b',
      created_at: nowIso,
      updated_at: nowIso,
      messages: [],
    })
    apiMocks.getChatTelemetry.mockResolvedValue({
      chat_id: 'chat-2',
      model_id: 'gemma4_e4b',
      context_ceiling_tokens: 4096,
      active_tokens_estimate: 256,
      pressure_status: 'green',
      trigger_ratio: 0.98,
      trigger_tokens: 4014,
      compaction_count: 0,
      summary_version: 0,
      last_compacted_message_id: null,
      recent_events: [],
    })

    container = document.createElement('div')
    document.body.appendChild(container)
    root = createRoot(container)
  })

  afterEach(async () => {
    await act(async () => {
      root.unmount()
    })
    container.remove()
  })

  it('hydrates selected chat from /chat/:id and keeps URL', async () => {
    await act(async () => {
      root.render(<App />)
    })

    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(apiMocks.getChat).toHaveBeenCalledWith('chat-2')
    expect(apiMocks.getChatTelemetry).toHaveBeenCalledWith('chat-2')
    expect(window.location.pathname).toBe('/chat/chat-2')
    expect(container.querySelector('.header-center')?.textContent).toContain('Restored Chat')
    expect(container.querySelector('.chat-item.active .chat-title')?.textContent).toContain('Restored Chat')
    expect(container.querySelector('.context-meter-orb strong')?.textContent).toContain('6%')
  })
})
