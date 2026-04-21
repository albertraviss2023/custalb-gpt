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

const nowIso = '2026-04-10T08:00:00.000Z'

describe('CBI workflows', () => {
  let container: HTMLDivElement
  let root: Root

  beforeEach(() => {
    vi.clearAllMocks()
    window.history.replaceState({}, '', '/chat/chat-cbi')

    apiMocks.listModels.mockResolvedValue({
      default_model_id: 'qwen3_8b_vllm',
      models: [
        {
          id: 'qwen3_8b_vllm',
          display_name: 'Qwen3 8B vLLM',
          quantization: 'fp16',
          tier: 'fast',
          description: 'test model',
          runtime_ref: 'qwen',
          available: true,
        },
      ],
    })
    apiMocks.listChats.mockResolvedValue([
      {
        id: 'chat-cbi',
        title: 'CBI Session',
        selected_model_id: 'qwen3_8b_vllm',
        created_at: nowIso,
        updated_at: nowIso,
      },
    ])
    apiMocks.getHealth.mockResolvedValue({ status: 'ok', runtime_reachable: true })
    apiMocks.listAddonCatalog.mockResolvedValue({
      addons: [
        {
          id: 'competency_interview_coach',
          name: 'Competency Interview Coach',
          tagline: 'CBI practice',
          description: 'CBI helper',
          category: 'interview',
          capabilities: [],
          installed: true,
        },
      ],
    })
    apiMocks.listUploads.mockResolvedValue([])
    apiMocks.getChat.mockResolvedValue({
      id: 'chat-cbi',
      title: 'CBI Session',
      selected_model_id: 'qwen3_8b_vllm',
      created_at: nowIso,
      updated_at: nowIso,
      messages: [],
    })
    apiMocks.getChatTelemetry.mockResolvedValue({
      chat_id: 'chat-cbi',
      model_id: 'qwen3_8b_vllm',
      context_ceiling_tokens: 4096,
      active_tokens_estimate: 140,
      pressure_status: 'green',
      trigger_ratio: 0.98,
      trigger_tokens: 4014,
      compaction_count: 0,
      summary_version: 0,
      last_compacted_message_id: null,
      recent_events: [],
    })
    apiMocks.streamChatCompletion.mockImplementation(async () => {})

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

  async function bootAndEnableCbi() {
    await act(async () => {
      root.render(<App />)
    })
    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
    })
    const openDrawerButton = Array.from(container.querySelectorAll('.drawer-toggle')).find((el) => el.textContent?.includes('Open'))
    expect(openDrawerButton).toBeTruthy()
    await act(async () => {
      ;(openDrawerButton as HTMLButtonElement).click()
    })
    const cbiGemButton = Array.from(container.querySelectorAll('.gem-item')).find((el) => el.textContent?.includes('Competency Interview Coach'))
    expect(cbiGemButton).toBeTruthy()
    await act(async () => {
      ;(cbiGemButton as HTMLButtonElement).click()
    })
  }

  it('shows CBI configuration drawer and updates interview duration', async () => {
    await bootAndEnableCbi()
    const setupButton = Array.from(container.querySelectorAll('button')).find((el) => el.textContent?.trim() === 'Setup')
    expect(setupButton).toBeTruthy()
    expect(container.textContent).toContain('Program Manager')
    expect(container.textContent).toContain('30m')
  })

  it('restores voice input button after interview start request completes', async () => {
    await bootAndEnableCbi()

    const startButton = Array.from(container.querySelectorAll('button')).find((el) => el.textContent?.includes('Start'))
    expect(startButton).toBeTruthy()

    await act(async () => {
      ;(startButton as HTMLButtonElement).click()
    })
    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
    })

    const voiceButton = container.querySelector('.voice-wave-btn') as HTMLButtonElement | null
    expect(voiceButton).toBeTruthy()
    expect(voiceButton?.disabled).toBe(false)
    expect(apiMocks.streamChatCompletion).toHaveBeenCalledTimes(1)
  })

  it('shows actionable error when voice button is clicked before interview starts', async () => {
    await bootAndEnableCbi()

    const voiceButton = container.querySelector('.voice-wave-btn') as HTMLButtonElement | null
    expect(voiceButton).toBeTruthy()

    await act(async () => {
      ;(voiceButton as HTMLButtonElement).click()
    })

    expect(apiMocks.streamChatCompletion).not.toHaveBeenCalled()
    expect((voiceButton as HTMLButtonElement).className).not.toContain('listening')
  })

  it('supports pause and resume with session controls', async () => {
    apiMocks.getChat.mockResolvedValueOnce({
      id: 'chat-cbi',
      title: 'CBI Session',
      selected_model_id: 'qwen3_8b_vllm',
      created_at: nowIso,
      updated_at: nowIso,
      messages: [
        { id: 'm1', chat_id: 'chat-cbi', role: 'user', content: 'Start CBI practice now.', created_at: nowIso },
        { id: 'm2', chat_id: 'chat-cbi', role: 'assistant', content: 'PANEL_SPEAKER: Dr. Elena Sokolov | Panel Chair | Switzerland | female | en-gb\nPANEL_TEXT: Tell us about a teamwork challenge you handled.', created_at: nowIso },
      ],
    })
    await bootAndEnableCbi()

    const startButton = Array.from(container.querySelectorAll('button')).find((el) => el.textContent?.includes('Start'))
    expect(startButton).toBeTruthy()
    await act(async () => {
      ;(startButton as HTMLButtonElement).click()
      await Promise.resolve()
      await Promise.resolve()
    })

    const pauseButton = Array.from(container.querySelectorAll('button')).find((el) => el.textContent?.trim() === 'Pause')
    expect(pauseButton).toBeTruthy()
    await act(async () => {
      ;(pauseButton as HTMLButtonElement).click()
    })
    expect(container.textContent).toContain('PAUSED')

    const resumeButton = Array.from(container.querySelectorAll('button')).find((el) => el.textContent?.trim() === 'Resume Interview')
    expect(resumeButton).toBeTruthy()
    await act(async () => {
      ;(resumeButton as HTMLButtonElement).click()
    })
    expect(container.textContent).toContain('RUNNING')
  })

  it('shows timeline controls and allows rewind after a panel step', async () => {
    apiMocks.getChat.mockResolvedValueOnce({
      id: 'chat-cbi',
      title: 'CBI Session',
      selected_model_id: 'qwen3_8b_vllm',
      created_at: nowIso,
      updated_at: nowIso,
      messages: [
        { id: 'm1', chat_id: 'chat-cbi', role: 'user', content: 'Start CBI practice now.', created_at: nowIso },
        { id: 'm2', chat_id: 'chat-cbi', role: 'assistant', content: 'PANEL_SPEAKER: Dr. Elena Sokolov | Panel Chair | Switzerland | female | en-gb\nPANEL_TEXT: Share a time you coordinated stakeholders under pressure.\nPANEL_TEXT: Follow-up: what did you measure?', created_at: nowIso },
      ],
    })
    await bootAndEnableCbi()

    const startButton = Array.from(container.querySelectorAll('button')).find((el) => el.textContent?.includes('Start'))
    expect(startButton).toBeTruthy()
    await act(async () => {
      ;(startButton as HTMLButtonElement).click()
      await Promise.resolve()
      await Promise.resolve()
    })

    const timelineLabel = Array.from(container.querySelectorAll('strong')).find((el) => el.textContent?.includes('Interview Timeline'))
    expect(timelineLabel).toBeTruthy()

    const rewindButton = Array.from(container.querySelectorAll('button')).find((el) => el.textContent?.trim() === 'Rewind')
    expect(rewindButton).toBeTruthy()

    const timelineSelect = container.querySelector('.timeline-controls select') as HTMLSelectElement | null
    expect(timelineSelect).toBeTruthy()
    expect(timelineSelect?.options.length).toBeGreaterThan(1)
    await act(async () => {
      timelineSelect!.value = timelineSelect!.options[1].value
      timelineSelect!.dispatchEvent(new Event('change', { bubbles: true }))
      ;(rewindButton as HTMLButtonElement).click()
    })
    expect(container.textContent).toContain('PAUSED')
  })
})
