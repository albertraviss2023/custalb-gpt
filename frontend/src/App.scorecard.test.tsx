import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import App from './App'

const apiMocks = vi.hoisted(() => ({
  asApiErrorMessage: vi.fn((raw: string, fallback: string) => raw || fallback),
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

// Mock SpeechSynthesis
const mockSpeechSynthesis = {
  cancel: vi.fn(),
  speak: vi.fn(),
  getVoices: vi.fn().mockReturnValue([]),
  onvoiceschanged: null,
}
vi.stubGlobal('speechSynthesis', mockSpeechSynthesis)

const nowIso = '2026-04-10T08:00:00.000Z'

describe('App Scorecard Stability', () => {
  let container: HTMLDivElement
  let root: Root

  beforeEach(() => {
    vi.clearAllMocks()
    window.history.replaceState({}, '', '/chat/broken-scorecard')

    apiMocks.listModels.mockResolvedValue({
      default_model_id: 'test-model',
      models: [{ id: 'test-model', display_name: 'Test Model', available: true }],
    })
    apiMocks.listChats.mockResolvedValue([
      { id: 'broken-scorecard', title: 'Broken Scorecard', updated_at: nowIso },
    ])
    apiMocks.getHealth.mockResolvedValue({ runtime_reachable: true })
    apiMocks.listAddonCatalog.mockResolvedValue({ addons: [] })
    apiMocks.listUploads.mockResolvedValue([])
    apiMocks.getChatTelemetry.mockResolvedValue({
      context_ceiling_tokens: 4000,
      active_tokens_estimate: 100,
      pressure_status: 'green',
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

  it('renders without crashing when scorecard delivery data is missing', async () => {
    // Mock a chat with a broken scorecard (missing .delivery object)
    apiMocks.getChat.mockResolvedValue({
      id: 'broken-scorecard',
      title: 'Broken Scorecard',
      messages: [
        {
          id: 'msg-1',
          role: 'assistant',
          content: 'CBI_SCORECARD_JSON: {"level": "P3", "verdict": "Qualified", "overall_readiness_0_to_100": 85, "competencies": []}',
        },
      ],
    })

    await act(async () => {
      root.render(<App />)
    })

    // Wait for async load
    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
    })

    // If it didn't crash, the brand name should be visible
    expect(container.querySelector('.brand-name')?.textContent).toBe('TurboGPT')

    // Check that fallback values (0%) are rendered instead of crashing
    const deliveryAssessment = container.querySelector('.delivery-assessment')
    expect(deliveryAssessment).toBeTruthy()
    
    const confidenceValue = Array.from(deliveryAssessment!.querySelectorAll('.stat-item'))
      .find(el => el.querySelector('.stat-label')?.textContent === 'Confidence')
      ?.querySelector('.stat-value')
      
    expect(confidenceValue?.textContent).toBe('0%')
  })
})
