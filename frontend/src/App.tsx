import { useEffect, useMemo, useRef, useState, useCallback, type MouseEvent as ReactMouseEvent } from 'react'
import ReactMarkdown, { type Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'
import logoMark from './assets/turbogpt-logo.svg'

import {
  asApiErrorMessage,
  completeChat,
  createLogEvent,
  createChat,
  deleteUpload,
  deleteChat,
  getChat,
  getChatTelemetry,
  getHealth,
  listAddonCatalog,
  listChats,
  listModels,
  listUploads,
  setModelSelection,
  startUpload,
  streamChatCompletion,
  updateChat,
  uploadChunk,
} from './api'
import type {
  AddonDescriptor,
  ChatDetail,
  ChatSummary,
  MessageInput,
  ModelDescriptor,
  UploadRecord,
  ChatTelemetryResponse,
} from './types'

import './styles.css'

interface UiMessage {
  id: string
  role: 'user' | 'assistant' | 'system' | 'tool'
  content: string
}

interface CbiScorecard {
  role: string
  level: string
  overall_readiness_0_to_100: number
  competencies: Array<{
    name: string
    score_1_to_5: number
    evidence: string
    gaps: string
  }>
  delivery: {
    confidence: number
    clarity: number
    presence: number
    feedback: string
  }
  panel_summary: string
  verdict: string
}

const MAX_UPLOAD_BYTES = 500 * 1024 * 1024 * 1024
const CHUNK_SIZE_BYTES = 8 * 1024 * 1024
const CHAT_PATH_PREFIX = '/chat/'
const STREAM_RESPONSE_TIMEOUT_MS = 45000
const CBI_STREAM_RESPONSE_TIMEOUT_MS = 150000
type VoiceGender = 'female' | 'male' | 'unknown'
type PanelistGender = 'female' | 'male' | 'unknown'
type AccentPreference = 'auto' | 'en-gb' | 'en-us' | 'en-au' | 'en-in' | 'en-za'

type PanelistTone = 'formal' | 'probing' | 'neutral' | 'supportive' | 'skeptical'
type SpeakingStyle = 'fast' | 'structured' | 'conversational' | 'strict'

type InterviewPanelist = {
  name: string
  title: string
  nationality: string
  gender: PanelistGender
  accent: AccentPreference
  tone: PanelistTone
  speaking_style: SpeakingStyle
  avatar_url?: string
}

const DEFAULT_PANELISTS: InterviewPanelist[] = [
  { name: 'Dr. Elena Sokolov', title: 'Panel Chair', nationality: 'Switzerland', gender: 'female', accent: 'en-gb', tone: 'formal', speaking_style: 'structured', avatar_url: 'https://i.pravatar.cc/150?u=elena' },
  { name: 'Kwame Mensah', title: 'Technical Lead', nationality: 'Ghana', gender: 'male', accent: 'auto', tone: 'probing', speaking_style: 'strict', avatar_url: 'https://i.pravatar.cc/150?u=kwame' },
  { name: 'Maria Garcia', title: 'HR Representative', nationality: 'Spain', gender: 'female', accent: 'auto', tone: 'supportive', speaking_style: 'conversational', avatar_url: 'https://i.pravatar.cc/150?u=maria' },
  { name: 'Chen Wei', title: 'Director of Operations', nationality: 'China', gender: 'male', accent: 'auto', tone: 'skeptical', speaking_style: 'strict', avatar_url: 'https://i.pravatar.cc/150?u=chen' },
  { name: 'Linda Miller', title: 'Stakeholder Representative', nationality: 'USA', gender: 'female', accent: 'en-us', tone: 'neutral', speaking_style: 'structured', avatar_url: 'https://i.pravatar.cc/150?u=linda' },
]

const PANEL_GENDER_PREF: Record<string, VoiceGender> = {
  'Dr. Elena Sokolov': 'female',
  'Kwame Mensah': 'male',
  'Maria Garcia': 'female',
  'Chen Wei': 'male',
  'Linda Miller': 'female',
}

const PANEL_NATIONALITY_PREF: Record<string, string> = {
  'Dr. Elena Sokolov': 'Switzerland',
  'Kwame Mensah': 'Ghana',
  'Maria Garcia': 'Spain',
  'Chen Wei': 'China',
  'Linda Miller': 'USA',
}

const PANEL_ACCENT_PREF: Record<string, AccentPreference> = {
  'Dr. Elena Sokolov': 'en-gb',
  'Kwame Mensah': 'auto',
  'Maria Garcia': 'auto',
  'Chen Wei': 'auto',
  'Linda Miller': 'en-us',
}

const ACCENT_OPTIONS: Array<{ value: AccentPreference; label: string }> = [
  { value: 'auto', label: 'Accent: Auto' },
  { value: 'en-gb', label: 'Accent: UK' },
  { value: 'en-us', label: 'Accent: US' },
  { value: 'en-au', label: 'Accent: AU' },
  { value: 'en-in', label: 'Accent: IN' },
  { value: 'en-za', label: 'Accent: ZA' },
]

const FEMALE_VOICE_MARKERS = [
  'female', 'woman', 'samantha', 'karen', 'moira', 'victoria', 'zira', 'ava', 'aria', 'jenny', 'libby', 'susan',
]

const MALE_VOICE_MARKERS = [
  'male', 'man', 'david', 'alex', 'daniel', 'fred', 'george', 'john', 'matthew', 'tom', 'oliver', 'james',
]

type BrowserSpeechRecognition = {
  continuous: boolean
  interimResults: boolean
  lang: string
  start: () => void
  stop: () => void
  onresult: ((event: { results: ArrayLike<(ArrayLike<{ transcript: string }> & { isFinal?: boolean })> }) => void) | null
  onerror: ((event: { error?: string }) => void) | null
  onend: (() => void) | null
}

type BrowserSpeechRecognitionCtor = new () => BrowserSpeechRecognition

function toUiMessages(chat: ChatDetail | null): UiMessage[] {
  if (!chat) return []
  return chat.messages.map((message) => ({
    id: message.id,
    role: message.role,
    content: message.content,
  }))
}

function summarizeTitleFromPrompt(prompt: string): string {
  const compact = prompt.trim().replace(/\s+/g, ' ')
  if (!compact) return 'Untitled Chat'
  if (compact.length <= 56) return compact
  return `${compact.slice(0, 53).trim()}...`
}

function formatChatTimestamp(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  }).format(date)
}

function parseChatIdFromPath(pathname: string): string | null {
  if (!pathname.startsWith(CHAT_PATH_PREFIX)) return null
  const id = decodeURIComponent(pathname.slice(CHAT_PATH_PREFIX.length)).trim()
  return id || null
}

function setChatPath(chatId: string | null, replace = false) {
  const target = chatId ? `${CHAT_PATH_PREFIX}${encodeURIComponent(chatId)}` : '/'
  if (replace) {
    window.history.replaceState({}, '', target)
  } else {
    window.history.pushState({}, '', target)
  }
}

function App() {
  const [models, setModels] = useState<ModelDescriptor[]>([])
  const [defaultModelId, setDefaultModelId] = useState<string>('')
  const [addons, setAddons] = useState<AddonDescriptor[]>([])
  const [activeAddonId, setActiveAddonId] = useState<string>('')
  const [leftRailWidth, setLeftRailWidth] = useState(320)
  const [isResizingRail, setIsResizingRail] = useState(false)
  const [isGemDrawerOpen, setIsGemDrawerOpen] = useState(false)
  const [chatDateFilter, setChatDateFilter] = useState<'today' | 'yesterday' | '7d' | '30d'>('30d')
  const [webMode, setWebMode] = useState(false)
  const [interviewRole, setInterviewRole] = useState('Program Manager')
  const [interviewPanelMembers] = useState(3)
  const [interviewOrgType] = useState<'un' | 'private_sector'>('un')
  const [interviewOrgName, setInterviewOrgName] = useState('United Nations')
  const [interviewLocation, setInterviewLocation] = useState('New York')
  const [interviewIsHq] = useState(true)
  const [interviewRoleLevel, setInterviewRoleLevel] = useState<'P2' | 'P3' | 'P4' | 'P5' | 'D1' | 'D2'>('P3')
  const [interviewDurationMinutes, setInterviewDurationMinutes] = useState(30)
  const [interviewDifficulty] = useState<'medium' | 'high'>('medium')
  const [interviewRealismIntensity, setInterviewRealismIntensity] = useState<'low' | 'medium' | 'high' | 'extreme'>('medium')
  const [interviewPanelists, setInterviewPanelists] = useState<InterviewPanelist[]>(DEFAULT_PANELISTS.slice(0, 3))
  const [interviewSessionState, setInterviewSessionState] = useState<'idle' | 'running' | 'paused' | 'ended'>('idle')
  const [interviewRemainingSeconds, setInterviewRemainingSeconds] = useState(30 * 60)
  const [autoStartCamera, setAutoStartCamera] = useState(true)
  const [cameraActive, setCameraActive] = useState(false)
  const [cameraDetached, setCameraDetached] = useState(false)
  const [cameraError, setCameraError] = useState<string | null>(null)
  const [cameraDockPosition, setCameraDockPosition] = useState({ x: 0, y: 0 })
  const [cbiTtsEnabled, setCbiTtsEnabled] = useState(true)
  const [isVoiceListening, setIsVoiceListening] = useState(false)
  const [voiceDraft, setVoiceDraft] = useState('')
  const [showAdvancedSetup, setShowAdvancedSetup] = useState(false)
  const [activeSpeaker, setActiveSpeaker] = useState<string | null>(null)

  const [chats, setChats] = useState<ChatSummary[]>([])
  const [activeChatId, setActiveChatId] = useState<string | null>(null)
  const [activeChat, setActiveChat] = useState<ChatDetail | null>(null)
  const [messages, setMessages] = useState<UiMessage[]>([])
  const [input, setInput] = useState('')
  const [pastedImages, setPastedImages] = useState<string[]>([])
  const [isSending, setIsSending] = useState(false)
  const [isSwitchingModel, setIsSwitchingModel] = useState(false)
  const [healthStatus, setHealthStatus] = useState('checking')
  const [error, setError] = useState<string | null>(null)
  const [chatTelemetry, setChatTelemetry] = useState<ChatTelemetryResponse | null>(null)
  const [messageFeedback, setMessageFeedback] = useState<Record<string, 'up' | 'down'>>({})
  const [showInheritChooser, setShowInheritChooser] = useState(false)
  const [inheritSourceChatId, setInheritSourceChatId] = useState<string>('')
  const [thinkingLevel, setThinkingLevel] = useState<'fast' | 'balanced' | 'deep'>('fast')
  const [responseLength, setResponseLength] = useState<'concise' | 'standard' | 'detailed'>('concise')

  const [uploads, setUploads] = useState<UploadRecord[]>([])
  const [chatAttachmentMap, setChatAttachmentMap] = useState<Record<string, string[]>>({})

  const fileInputRef = useRef<HTMLInputElement>(null)
  const activeSendController = useRef<AbortController | null>(null)
  const messageEndRef = useRef<HTMLDivElement>(null)
  const speechRecognitionRef = useRef<BrowserSpeechRecognition | null>(null)
  const voicePauseTimerRef = useRef<number | null>(null)
  const voiceAutoSendingRef = useRef(false)
  const voiceDraftRef = useRef('')
  const isSendingRef = useRef(false)
  const speechVoicesRef = useRef<SpeechSynthesisVoice[]>([])
  const panelVoiceMapRef = useRef<Record<string, SpeechSynthesisVoice>>({})
  const voicePoolsRef = useRef<{ female: SpeechSynthesisVoice[]; male: SpeechSynthesisVoice[]; unknown: SpeechSynthesisVoice[] }>({
    female: [],
    male: [],
    unknown: [],
  })
  const voiceRotationRef = useRef<{ female: number; male: number; unknown: number }>({ female: 0, male: 0, unknown: 0 })
  const lastSpokenSignatureRef = useRef<string>('')
  const interviewAutoConcludeRef = useRef(false)
  const [voiceLevel, setVoiceLevel] = useState(0)
  const voiceMeterRafRef = useRef<number | null>(null)
  const voiceMeterContextRef = useRef<AudioContext | null>(null)
  const voiceMeterStreamRef = useRef<MediaStream | null>(null)
  const cameraStreamRef = useRef<MediaStream | null>(null)
  const cameraVideoRef = useRef<HTMLVideoElement>(null)
  const cameraDockRef = useRef<HTMLDivElement>(null)
  const cameraDraggingRef = useRef<{ active: boolean; offsetX: number; offsetY: number }>({
    active: false,
    offsetX: 0,
    offsetY: 0,
  })
  const railResizeRef = useRef<{ active: boolean; startX: number; startWidth: number }>({
    active: false,
    startX: 0,
    startWidth: 320,
  })

  const selectedAttachmentIds = useMemo(() => {
    if (!activeChatId) return []
    return chatAttachmentMap[activeChatId] ?? []
  }, [activeChatId, chatAttachmentMap])

  const activeModelId = useMemo(() => activeChat?.selected_model_id ?? defaultModelId, [activeChat?.selected_model_id, defaultModelId])
  const activeModel = useMemo(() => models.find((model) => model.id === activeModelId), [models, activeModelId])

  const activeGemName = useMemo(() => {
    if (!activeAddonId) return 'General'
    return addons.find((addon) => addon.id === activeAddonId)?.name ?? activeAddonId
  }, [activeAddonId, addons])

  const hasScorecardInHistory = useMemo(() => {
    return messages.some((m) => m.role === 'assistant' && m.content.includes('CBI_SCORECARD_JSON:'))
  }, [messages])

  const activeAddon = useMemo(() => addons.find(a => a.id === activeAddonId), [addons, activeAddonId])
  
  const isCbiMode = 
    activeAddonId.toLowerCase().includes('interview') || 
    activeGemName.toLowerCase().includes('interview') ||
    activeGemName.toLowerCase().includes('cbi') ||
    activeAddon?.category === 'interview' ||
    hasScorecardInHistory

  const filteredChats = useMemo(() => {
    const now = new Date()
    const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime()
    const oneDayMs = 24 * 60 * 60 * 1000

    return chats.filter((chat) => {
      const updated = new Date(chat.updated_at).getTime()
      if (Number.isNaN(updated)) return true
      if (chatDateFilter === 'today') return updated >= todayStart
      if (chatDateFilter === 'yesterday') return updated >= (todayStart - oneDayMs) && updated < todayStart
      if (chatDateFilter === '7d') return updated >= (todayStart - (7 * oneDayMs))
      return updated >= (todayStart - (30 * oneDayMs))
    })
  }, [chats, chatDateFilter])

  const contextUsagePercent = useMemo(() => {
    if (!chatTelemetry || chatTelemetry.context_ceiling_tokens <= 0) return 0
    return Math.min(
      100,
      Math.max(0, Math.round((chatTelemetry.active_tokens_estimate / chatTelemetry.context_ceiling_tokens) * 100)),
    )
  }, [chatTelemetry])

  const latestAssistantMessageId = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i -= 1) {
      if (messages[i]?.role === 'assistant') return messages[i].id
    }
    return null
  }, [messages])

  const inheritCandidates = useMemo(() => {
    return chats.map((chat) => ({ id: chat.id, title: chat.title }))
  }, [chats])

  useEffect(() => {
    messageEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  useEffect(() => {
    voiceDraftRef.current = voiceDraft
  }, [voiceDraft])

  useEffect(() => {
    isSendingRef.current = isSending
  }, [isSending])

  useEffect(() => {
    const defaultX = Math.max(12, window.innerWidth - 390)
    const defaultY = Math.max(72, window.innerHeight - 310)
    setCameraDockPosition({ x: defaultX, y: defaultY })
  }, [])

  useEffect(() => {
    panelVoiceMapRef.current = {}
  }, [interviewPanelists, cbiTtsEnabled])

  useEffect(() => {
    if (interviewSessionState === 'running') return
    setInterviewRemainingSeconds(interviewDurationMinutes * 60)
  }, [interviewDurationMinutes, interviewSessionState])

  function hashSpeaker(inputText: string): number {
    let hash = 0
    for (let i = 0; i < inputText.length; i += 1) {
      hash = ((hash << 5) - hash) + inputText.charCodeAt(i)
      hash |= 0
    }
    return Math.abs(hash)
  }

  function detectVoiceGender(voice: SpeechSynthesisVoice): VoiceGender {
    const label = `${voice.name} ${voice.lang}`.toLowerCase()
    if (FEMALE_VOICE_MARKERS.some((token) => label.includes(token))) return 'female'
    if (MALE_VOICE_MARKERS.some((token) => label.includes(token))) return 'male'
    return 'unknown'
  }

  const getPanelistProfile = useCallback((speakerName: string): InterviewPanelist => {
    const configured = interviewPanelists.find((entry) => entry.name === speakerName)
    if (configured) return configured
    return {
      name: speakerName,
      title: 'Panel Member',
      nationality: PANEL_NATIONALITY_PREF[speakerName] || '',
      gender: PANEL_GENDER_PREF[speakerName] || (hashSpeaker(speakerName) % 2 === 0 ? 'female' : 'male'),
      accent: PANEL_ACCENT_PREF[speakerName] || 'auto',
      tone: 'neutral',
      speaking_style: 'structured',
    }
  }, [interviewPanelists])

  function nationalityToLangPrefixes(nationality: string): string[] {
    const key = nationality.toLowerCase()
    if (key.includes('brit')) return ['en-gb']
    if (key.includes('american') || key.includes('usa') || key.includes('u.s.')) return ['en-us']
    if (key.includes('australian')) return ['en-au']
    if (key.includes('irish')) return ['en-ie', 'en-gb']
    if (key.includes('indian')) return ['en-in', 'en-gb']
    if (key.includes('south african')) return ['en-za', 'en-gb']
    if (key.includes('nigerian') || key.includes('ugandan') || key.includes('kenyan')) return ['en-gb', 'en-za', 'en-us']
    return ['en-gb', 'en-us']
  }

  function accentPreferenceToLangPrefixes(accent: AccentPreference | undefined, nationality: string): string[] {
    if (accent && accent !== 'auto') return [accent]
    return nationalityToLangPrefixes(nationality)
  }

  function stopVoiceMeter() {
    if (voiceMeterRafRef.current !== null) {
      window.cancelAnimationFrame(voiceMeterRafRef.current)
      voiceMeterRafRef.current = null
    }
    if (voiceMeterStreamRef.current) {
      for (const track of voiceMeterStreamRef.current.getTracks()) {
        track.stop()
      }
      voiceMeterStreamRef.current = null
    }
    if (voiceMeterContextRef.current) {
      void voiceMeterContextRef.current.close()
      voiceMeterContextRef.current = null
    }
    setVoiceLevel(0)
  }

  async function startVoiceMeter() {
    stopVoiceMeter()
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const AudioCtx = window.AudioContext || (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
      if (!AudioCtx) return
      const context = new AudioCtx()
      const source = context.createMediaStreamSource(stream)
      const analyser = context.createAnalyser()
      analyser.fftSize = 512
      source.connect(analyser)
      const data = new Uint8Array(analyser.frequencyBinCount)
      voiceMeterContextRef.current = context
      voiceMeterStreamRef.current = stream
      const tick = () => {
        analyser.getByteTimeDomainData(data)
        let sum = 0
        for (let i = 0; i < data.length; i += 1) {
          const centered = (data[i] - 128) / 128
          sum += centered * centered
        }
        const rms = Math.sqrt(sum / data.length)
        setVoiceLevel(Math.max(0, Math.min(1, rms * 4.2)))
        voiceMeterRafRef.current = window.requestAnimationFrame(tick)
      }
      voiceMeterRafRef.current = window.requestAnimationFrame(tick)
    } catch {
      // keep flow working even if meter permissions are blocked
    }
  }

  function getUsableTtsVoices(): SpeechSynthesisVoice[] {
    const synth = window.speechSynthesis
    if (!synth || typeof synth.getVoices !== 'function') {
      speechVoicesRef.current = []
      voicePoolsRef.current = { female: [], male: [], unknown: [] }
      return []
    }
    const loaded = synth.getVoices()
    if (loaded.length > 0) {
      const english = loaded.filter((voice) => voice.lang.toLowerCase().startsWith('en'))
      const usable = english.length > 0 ? english : loaded
      speechVoicesRef.current = usable
      const female: SpeechSynthesisVoice[] = []
      const male: SpeechSynthesisVoice[] = []
      const unknown: SpeechSynthesisVoice[] = []
      for (const voice of usable) {
        const gender = detectVoiceGender(voice)
        if (gender === 'female') female.push(voice)
        else if (gender === 'male') male.push(voice)
        else unknown.push(voice)
      }
      voicePoolsRef.current = { female, male, unknown }
    }
    return speechVoicesRef.current
  }

  function getVoiceForSpeaker(
    speakerName: string,
    options?: { nationality?: string; gender?: PanelistGender; accent?: AccentPreference },
  ): SpeechSynthesisVoice | null {
    const existing = panelVoiceMapRef.current[speakerName]
    if (existing) return existing
    getUsableTtsVoices()
    const panelist = getPanelistProfile(speakerName)
    const desired = options?.gender || panelist.gender
    const pools = voicePoolsRef.current
    const primaryPool = desired === 'female' ? pools.female : pools.male
    const fallbackPool = pools.unknown.length ? pools.unknown : speechVoicesRef.current
    const accentPrefixes = accentPreferenceToLangPrefixes(options?.accent || panelist.accent, options?.nationality || panelist.nationality || '')
    const accentMatchedPrimary = primaryPool.filter((voice) => accentPrefixes.some((prefix) => voice.lang.toLowerCase().startsWith(prefix)))
    const accentMatchedFallback = fallbackPool.filter((voice) => accentPrefixes.some((prefix) => voice.lang.toLowerCase().startsWith(prefix)))
    const candidatePool = accentMatchedPrimary.length
      ? accentMatchedPrimary
      : (primaryPool.length ? primaryPool : (accentMatchedFallback.length ? accentMatchedFallback : fallbackPool))
    if (!candidatePool.length) return null
    const rotation = voiceRotationRef.current[desired]
    const picked = candidatePool[rotation % candidatePool.length]
    voiceRotationRef.current[desired] = rotation + 1
    panelVoiceMapRef.current[speakerName] = picked
    return picked
  }

  function parsePanelSpeechSegments(content: string): Array<{ speaker: string; text: string; nationality?: string; gender?: PanelistGender; accent?: AccentPreference }> {
    const segments: Array<{ speaker: string; text: string; nationality?: string; gender?: PanelistGender; accent?: AccentPreference }> = []
    const lines = content.split('\n').map((line) => line.trim()).filter(Boolean)
    let pendingSpeaker: string | null = null
    let pendingNationality: string | undefined
    let pendingGender: PanelistGender | undefined
    let pendingAccent: AccentPreference | undefined
    const genericSpeakerMap: Record<string, string> = {
      Chair: 'Amina Okello',
      Panelist: 'David Mwesige',
      Interviewer: 'Sarah Nambatya',
      Panel: 'Michael Kato',
    }
    const normalizeSpeaker = (rawSpeaker: string) => genericSpeakerMap[rawSpeaker] ?? rawSpeaker

    for (const line of lines) {
      if (line.startsWith('CBI_SCORECARD_JSON:')) break
      if (line.startsWith('PANEL_SPEAKER:')) {
        const speakerBlock = line.replace('PANEL_SPEAKER:', '').trim()
        const speakerParts = speakerBlock.split('|').map((part) => part.trim()).filter(Boolean)
        pendingSpeaker = normalizeSpeaker(speakerParts[0] || 'Panel')
        const panelist = getPanelistProfile(pendingSpeaker)
        pendingNationality = speakerParts[2]
          || panelist.nationality
          || PANEL_NATIONALITY_PREF[pendingSpeaker]
        pendingGender = (speakerParts[3] as PanelistGender | undefined) || panelist.gender
        pendingAccent = (speakerParts[4] as AccentPreference | undefined) || panelist.accent
        continue
      }
      if (line.startsWith('PANEL_QUESTION:')) {
        const body = line.replace('PANEL_QUESTION:', '').trim()
        const withSpeaker = body.match(/^\[([^\]]+)\]\s*(.+)$/)
        if (withSpeaker) {
          const normalized = normalizeSpeaker(withSpeaker[1].trim())
          const panelist = getPanelistProfile(normalized)
          const nationality = panelist.nationality || PANEL_NATIONALITY_PREF[normalized]
          segments.push({ speaker: normalized, text: withSpeaker[2].trim(), nationality, gender: panelist.gender, accent: panelist.accent })
        } else if (body) {
          const chair = getPanelistProfile('Amina Okello')
          segments.push({ speaker: 'Amina Okello', text: body, nationality: chair.nationality, gender: chair.gender, accent: chair.accent })
        }
        pendingSpeaker = null
        pendingNationality = undefined
        pendingGender = undefined
        pendingAccent = undefined
        continue
      }
      if (line.startsWith('PANEL_TEXT:')) {
        const spoken = line.replace('PANEL_TEXT:', '').trim()
        if (spoken) {
          segments.push({
            speaker: pendingSpeaker || 'Panel',
            text: spoken,
            nationality: pendingNationality,
            gender: pendingGender,
            accent: pendingAccent,
          })
        }
        pendingSpeaker = null
        pendingNationality = undefined
        pendingGender = undefined
        pendingAccent = undefined
        continue
      }
      const bracketMatch = line.match(/^\[([^\]]+)\]\s*(.+)$/)
      if (bracketMatch) {
        const normalized = normalizeSpeaker(bracketMatch[1].trim())
        const panelist = getPanelistProfile(normalized)
        const nationality = panelist.nationality || PANEL_NATIONALITY_PREF[normalized]
        segments.push({ speaker: normalized, text: bracketMatch[2].trim(), nationality, gender: panelist.gender, accent: panelist.accent })
      }
    }

    if (segments.length === 0) {
      const readable = content.split('CBI_SCORECARD_JSON:')[0].trim().slice(0, 500)
      if (readable) segments.push({ speaker: 'Panel', text: readable, nationality: '', gender: 'unknown', accent: 'auto' })
    }
    return segments
  }

  function extractCbiScorecard(content: string): CbiScorecard | null {
    const marker = 'CBI_SCORECARD_JSON:'
    const index = content.indexOf(marker)
    if (index < 0) return null
    const after = content.slice(index + marker.length).trim()
    const start = after.indexOf('{')
    if (start < 0) return null
    let depth = 0
    let end = -1
    for (let i = start; i < after.length; i += 1) {
      const ch = after[i]
      if (ch === '{') depth += 1
      if (ch === '}') {
        depth -= 1
        if (depth === 0) {
          end = i
          break
        }
      }
    }
    if (end < 0) return null
    const jsonSlice = after.slice(start, end + 1)
    try {
      const parsed = JSON.parse(jsonSlice) as CbiScorecard
      if (!parsed || typeof parsed !== 'object') return null
      return parsed
    } catch {
      return null
    }
  }

  function stripCbiScorecardBlock(content: string): string {
    const marker = 'CBI_SCORECARD_JSON:'
    const index = content.indexOf(marker)
    if (index < 0) return content
    return content.slice(0, index).trim()
  }

  function speakCbiSegments(segments: Array<{ speaker: string; text: string; nationality?: string; gender?: PanelistGender; accent?: AccentPreference }>) {
    if (!segments.length) return
    const synth = window.speechSynthesis
    if (!synth) return
    synth.cancel()
    for (const segment of segments) {
      const utter = new SpeechSynthesisUtterance(segment.text)
      utter.onstart = () => setActiveSpeaker(segment.speaker)
      utter.onend = () => setActiveSpeaker(null)
      const voice = getVoiceForSpeaker(segment.speaker, {
        nationality: segment.nationality,
        gender: segment.gender,
        accent: segment.accent,
      })
      if (voice) utter.voice = voice
      const desired = segment.gender || PANEL_GENDER_PREF[segment.speaker] || (hashSpeaker(segment.speaker) % 2 === 0 ? 'female' : 'male')
      utter.rate = desired === 'female' ? 1.02 : 0.98
      utter.pitch = desired === 'female' ? 1.08 : 0.92
      synth.speak(utter)
    }
  }

  function formatTimer(totalSeconds: number): string {
    const safe = Math.max(0, totalSeconds)
    const minutes = Math.floor(safe / 60).toString().padStart(2, '0')
    const seconds = (safe % 60).toString().padStart(2, '0')
    return `${minutes}:${seconds}`
  }

  function stopInterviewCamera() {
    if (document.pictureInPictureElement) {
      void document.exitPictureInPicture().catch(() => undefined)
      setCameraDetached(false)
    }
    if (cameraStreamRef.current) {
      for (const track of cameraStreamRef.current.getTracks()) {
        track.stop()
      }
      cameraStreamRef.current = null
    }
    if (cameraVideoRef.current) {
      cameraVideoRef.current.srcObject = null
    }
    setCameraActive(false)
  }

  async function startInterviewCamera() {
    if (!isCbiMode) return
    if (!navigator.mediaDevices || typeof navigator.mediaDevices.getUserMedia !== 'function') {
      setCameraError('Camera preview is not supported in this browser.')
      return
    }
    try {
      setCameraError(null)
      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          facingMode: 'user',
          width: { ideal: 1280 },
          height: { ideal: 720 },
        },
        audio: false,
      })
      cameraStreamRef.current = stream
      if (cameraVideoRef.current) {
        cameraVideoRef.current.srcObject = stream
        await cameraVideoRef.current.play().catch(() => undefined)
      }
      setCameraActive(true)
    } catch {
      setCameraError('Camera permission denied or camera unavailable.')
      setCameraActive(false)
    }
  }

  async function toggleInterviewCamera() {
    if (cameraActive) {
      stopInterviewCamera()
      return
    }
    await startInterviewCamera()
  }

  async function toggleDetachedCameraPreview() {
    const video = cameraVideoRef.current
    if (!video) {
      setCameraError('Camera preview is not ready yet.')
      return
    }
    if (!cameraActive) {
      await startInterviewCamera()
    }
    try {
      if (document.pictureInPictureElement) {
        await document.exitPictureInPicture()
        setCameraDetached(false)
        return
      }
      if (cameraStreamRef.current && video.srcObject !== cameraStreamRef.current) {
        video.srcObject = cameraStreamRef.current
      }
      await video.play().catch(() => undefined)
      if ('requestPictureInPicture' in video) {
        await (video as HTMLVideoElement & { requestPictureInPicture: () => Promise<unknown> }).requestPictureInPicture()
        setCameraDetached(true)
        return
      }
      setCameraError('Detach mode is not supported in this browser.')
    } catch {
      setCameraError('Unable to open detached camera preview.')
      setCameraDetached(false)
    }
  }

  function startRailResize(event: ReactMouseEvent<HTMLDivElement>) {
    railResizeRef.current = {
      active: true,
      startX: event.clientX,
      startWidth: leftRailWidth,
    }
    setIsResizingRail(true)
    event.preventDefault()
  }

  async function handleStartInterviewSession(resume = false) {
    if (!isCbiMode) return
    if (interviewSessionState === 'running') return
    
    if (autoStartCamera && !cameraActive) {
      await startInterviewCamera()
    }
    
    setInterviewSessionState('running')
    interviewAutoConcludeRef.current = false
    
    if (resume) {
      // Just notify the panel we are back
      await handleSend(
        'I am back. Please continue the interview from where we left off.',
        false,
        true,
      )
    } else {
      // Fresh start
      await handleSend(
        'Start CBI practice now. Ask exactly one primary UN-style competency question only, then wait for my answer.',
        false,
        true,
      )
    }
  }

  function handlePauseInterviewSession() {
    if (interviewSessionState !== 'running') return
    setInterviewSessionState('paused')
    window.speechSynthesis?.cancel()
  }

  async function handleEndInterviewSession(reason: 'manual' | 'timeout' = 'manual') {
    if (!isCbiMode) return
    setInterviewSessionState('ended')
    stopInterviewCamera()
    window.speechSynthesis?.cancel()
    const closingPrompt = reason === 'timeout'
      ? `Interview timer has reached ${interviewDurationMinutes} minutes. Conclude the panel and generate final CBI performance report now.`
      : 'End this interview now and generate final CBI performance report now.'
    await handleSend(closingPrompt, false, true)
  }

  useEffect(() => {
    if (!showInheritChooser) return
    if (!inheritSourceChatId) {
      const preferred = activeChatId && chats.some((chat) => chat.id === activeChatId)
        ? activeChatId
        : (inheritCandidates[0]?.id ?? '')
      setInheritSourceChatId(preferred)
    }
  }, [showInheritChooser, inheritSourceChatId, activeChatId, chats, inheritCandidates])

  useEffect(() => {
    setInterviewPanelists((current) => {
      const trimmed = current.slice(0, interviewPanelMembers)
      if (trimmed.length === interviewPanelMembers) return trimmed
      const next = [...trimmed]
      for (let i = trimmed.length; i < interviewPanelMembers; i += 1) {
        next.push(DEFAULT_PANELISTS[i] ?? {
          name: `Panelist ${i + 1}`,
          title: 'Panel Member',
          nationality: '',
          gender: i % 2 === 0 ? 'female' : 'male',
          accent: 'auto',
        })
      }
      return next
    })
  }, [interviewPanelMembers])

  useEffect(() => {
    if (interviewSessionState !== 'running') return
    const timer = window.setInterval(() => {
      setInterviewRemainingSeconds((current) => Math.max(0, current - 1))
    }, 1000)
    return () => window.clearInterval(timer)
  }, [interviewSessionState])

  useEffect(() => {
    setInterviewSessionState('idle')
    setInterviewRemainingSeconds(interviewDurationMinutes * 60)
    interviewAutoConcludeRef.current = false
    stopInterviewCamera()
    setCameraError(null)
  }, [activeChatId, interviewDurationMinutes])

  useEffect(() => {
    if (!isCbiMode) {
      setInterviewSessionState('idle')
      stopInterviewCamera()
    }
  }, [isCbiMode])

  useEffect(() => {
    if (!isCbiMode || !cameraActive) return
    const video = cameraVideoRef.current
    const stream = cameraStreamRef.current
    if (!video || !stream) return
    if (video.srcObject !== stream) {
      video.srcObject = stream
    }
    void video.play().catch(() => undefined)
  }, [isCbiMode, cameraActive])

  useEffect(() => {
    const handleLeavePip = () => setCameraDetached(false)
    document.addEventListener('leavepictureinpicture', handleLeavePip)
    return () => {
      document.removeEventListener('leavepictureinpicture', handleLeavePip)
    }
  }, [])

  useEffect(() => {
    const handleMove = (event: MouseEvent) => {
      if (cameraDraggingRef.current.active) {
        const dock = cameraDockRef.current
        const dockWidth = dock?.offsetWidth ?? 360
        const dockHeight = dock?.offsetHeight ?? 280
        const nextX = Math.min(
          Math.max(8, event.clientX - cameraDraggingRef.current.offsetX),
          Math.max(8, window.innerWidth - dockWidth - 8),
        )
        const nextY = Math.min(
          Math.max(56, event.clientY - cameraDraggingRef.current.offsetY),
          Math.max(56, window.innerHeight - dockHeight - 8),
        )
        setCameraDockPosition({ x: nextX, y: nextY })
      }
      if (railResizeRef.current.active) {
        const delta = event.clientX - railResizeRef.current.startX
        const nextWidth = Math.min(520, Math.max(250, railResizeRef.current.startWidth + delta))
        setLeftRailWidth(nextWidth)
      }
    }
    const handleUp = () => {
      cameraDraggingRef.current.active = false
      if (railResizeRef.current.active) {
        railResizeRef.current.active = false
        setIsResizingRail(false)
      }
    }
    window.addEventListener('mousemove', handleMove)
    window.addEventListener('mouseup', handleUp)
    return () => {
      window.removeEventListener('mousemove', handleMove)
      window.removeEventListener('mouseup', handleUp)
    }
  }, [])

  useEffect(() => {
    const synth = window.speechSynthesis
    if (!synth) return
    const refreshVoices = () => {
      getUsableTtsVoices()
    }
    refreshVoices()
    if ('onvoiceschanged' in synth) {
      synth.onvoiceschanged = refreshVoices
    }
    return () => {
      if ('onvoiceschanged' in synth) {
        synth.onvoiceschanged = null
      }
    }
    // Voice inventory is browser-managed.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (!isCbiMode || !cbiTtsEnabled || isSending || interviewSessionState !== 'running') return
    const latestAssistant = [...messages].reverse().find((message) => message.role === 'assistant')
    if (!latestAssistant || !latestAssistant.content.trim()) return
    const signature = `${activeChatId ?? 'no-chat'}:${latestAssistant.content.trim()}`
    if (signature === lastSpokenSignatureRef.current) return
    const segments = parsePanelSpeechSegments(latestAssistant.content)
    if (!segments.length) return
    speakCbiSegments(segments)
    lastSpokenSignatureRef.current = signature
  }, [messages, isCbiMode, cbiTtsEnabled, isSending, activeChatId, speakCbiSegments])

  useEffect(() => {
    if (!isCbiMode) return
    if (interviewSessionState !== 'running') return
    if (interviewRemainingSeconds > 0) return
    if (interviewAutoConcludeRef.current) return
    interviewAutoConcludeRef.current = true
    void handleEndInterviewSession('timeout')
  }, [isCbiMode, interviewSessionState, interviewRemainingSeconds, handleEndInterviewSession])

  useEffect(() => {
    void bootstrap()

    const onPopState = () => {
      const routeChatId = parseChatIdFromPath(window.location.pathname)
      if (routeChatId) {
        void selectChat(routeChatId, false)
      } else {
        setActiveChatId(null)
        setActiveChat(null)
        setMessages([])
        setChatTelemetry(null)
      }
    }

    window.addEventListener('popstate', onPopState)
    return () => {
      window.removeEventListener('popstate', onPopState)
      if (voicePauseTimerRef.current !== null) {
        window.clearTimeout(voicePauseTimerRef.current)
        voicePauseTimerRef.current = null
      }
      stopVoiceMeter()
      stopInterviewCamera()
      speechRecognitionRef.current?.stop()
      window.speechSynthesis?.cancel()
    }
    // bootstrap/selectChat are intentionally run once for initial route hydration.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function bootstrap() {
    try {
      const [modelsResponse, chatList, health, addonCatalog, uploadList] = await Promise.all([
        listModels(),
        listChats(),
        getHealth(),
        listAddonCatalog(),
        listUploads(),
      ])

      setModels(modelsResponse.models)
      setDefaultModelId(modelsResponse.default_model_id)
      setChats(chatList)
      setHealthStatus(health.runtime_reachable ? 'ready' : 'runtime unavailable')
      setAddons(addonCatalog.addons)
      setUploads(uploadList)

      const routeChatId = parseChatIdFromPath(window.location.pathname)
      const preferredChatId = routeChatId && chatList.some((chat) => chat.id === routeChatId)
        ? routeChatId
        : chatList[0]?.id

      if (preferredChatId) {
        await selectChat(preferredChatId, false)
        setChatPath(preferredChatId, routeChatId == null)
      } else {
        setChatPath(null, true)
      }
    } catch (loadError) {
      await reportError('bootstrap', loadError, { stage: 'initial-load' })
      setHealthStatus('degraded')
    }
  }

  async function reportError(source: string, rawError: unknown, context: Record<string, unknown> = {}) {
    const message = asApiErrorMessage(String(rawError), 'Unexpected error')
    setError(message)
    try {
      await createLogEvent({
        level: 'error',
        source,
        message,
        chat_id: activeChatId ?? undefined,
        context,
      })
    } catch {
      // noop
    }
  }

  function stopGeneration() {
    activeSendController.current?.abort()
    activeSendController.current = null
    setIsSending(false)
  }

  function toggleVoiceInput() {
    if (interviewSessionState !== 'running') {
      setError('Start interview to enable voice input.')
      return
    }

    const maybeWindow = window as Window & {
      SpeechRecognition?: BrowserSpeechRecognitionCtor
      webkitSpeechRecognition?: BrowserSpeechRecognitionCtor
    }
    const Recognition = maybeWindow.SpeechRecognition ?? maybeWindow.webkitSpeechRecognition
    if (!Recognition) {
      setError('Voice input is not supported in this browser.')
      return
    }

    if (isVoiceListening) {
      speechRecognitionRef.current?.stop()
      stopVoiceMeter()
      setIsVoiceListening(false)
      if (voicePauseTimerRef.current !== null) {
        window.clearTimeout(voicePauseTimerRef.current)
        voicePauseTimerRef.current = null
      }
      if (voiceDraftRef.current.trim() && !isSendingRef.current && !voiceAutoSendingRef.current) {
        voiceAutoSendingRef.current = true
        void handleSend(voiceDraftRef.current.trim(), true)
          .finally(() => {
            voiceAutoSendingRef.current = false
          })
      }
      return
    }

    const recognition = new Recognition()
    recognition.continuous = true
    recognition.interimResults = true
    recognition.lang = 'en-US'
    const scheduleAutoSend = () => {
      if (voicePauseTimerRef.current !== null) {
        window.clearTimeout(voicePauseTimerRef.current)
        voicePauseTimerRef.current = null
      }
      voicePauseTimerRef.current = window.setTimeout(() => {
        if (!voiceDraftRef.current.trim() || isSendingRef.current || voiceAutoSendingRef.current) return
        speechRecognitionRef.current?.stop()
        stopVoiceMeter()
        setIsVoiceListening(false)
        voiceAutoSendingRef.current = true
        void handleSend(voiceDraftRef.current.trim(), true)
          .finally(() => {
            voiceAutoSendingRef.current = false
          })
      }, 5000)
    }
    recognition.onresult = (event) => {
      let merged = ''
      for (let i = 0; i < event.results.length; i += 1) {
        const part = event.results[i]?.[0]?.transcript ?? ''
        if (part) merged += `${part} `
      }
      const transcript = merged.trim()
      if (!transcript) return
      setVoiceDraft(transcript)
      voiceDraftRef.current = transcript
      scheduleAutoSend()
    }
    recognition.onerror = (event) => {
      setIsVoiceListening(false)
      stopVoiceMeter()
      if (voicePauseTimerRef.current !== null) {
        window.clearTimeout(voicePauseTimerRef.current)
      }
      const rawError = String(event?.error ?? '').toLowerCase()
      if (rawError === 'not-allowed' || rawError === 'service-not-allowed') {
        setError('Microphone access was denied. Allow microphone permission and try again.')
        return
      }
      setError('Voice capture failed. Please try again.')
    }
    recognition.onend = () => {
      setIsVoiceListening(false)
      stopVoiceMeter()
      if (voicePauseTimerRef.current !== null) {
        window.clearTimeout(voicePauseTimerRef.current)
        voicePauseTimerRef.current = null
      }
      if (voiceDraftRef.current.trim() && !isSendingRef.current && !voiceAutoSendingRef.current) {
        voiceAutoSendingRef.current = true
        void handleSend(voiceDraftRef.current.trim(), true)
          .finally(() => {
            voiceAutoSendingRef.current = false
          })
      }
    }
    speechRecognitionRef.current = recognition
    setIsVoiceListening(true)
    setError(null)
    void startVoiceMeter()
    try {
      recognition.start()
    } catch {
      setIsVoiceListening(false)
      stopVoiceMeter()
      setError('Unable to start voice capture. Please click again and allow microphone access.')
    }
  }

  async function refreshChats(selectId?: string) {
    const latest = await listChats()
    setChats(latest)
    if (selectId) setActiveChatId(selectId)
  }

  async function selectChat(chatId: string, syncUrl = true) {
    try {
      setActiveChatId(chatId)
      const detail = await getChat(chatId)
      setActiveChat(detail)
      setMessages(toUiMessages(detail))
      const telemetry = await getChatTelemetry(chatId)
      setChatTelemetry(telemetry)
      if (syncUrl) setChatPath(chatId)
    } catch (chatError) {
      await reportError('select-chat', chatError, { chatId })
    }
  }

  async function handleCreateChat() {
    try {
      const chat = await createChat({ selected_model_id: defaultModelId || undefined })
      setChatAttachmentMap((current) => ({ ...current, [chat.id]: [] }))
      await refreshChats(chat.id)
      await selectChat(chat.id, true)
    } catch (creationError) {
      await reportError('create-chat', creationError)
    }
  }

  async function handleCreateInheritedChat(sourceChatId?: string) {
    const sourceId = sourceChatId || inheritSourceChatId || activeChatId
    if (!sourceId) return
    try {
      const chat = await createChat({
        selected_model_id: activeModelId || defaultModelId || undefined,
        inherit_from_chat_id: sourceId,
        inherit_recent_messages: 0,
      })
      setChatAttachmentMap((current) => ({ ...current, [chat.id]: [] }))
      await refreshChats(chat.id)
      await selectChat(chat.id, true)
      setShowInheritChooser(false)
    } catch (creationError) {
      await reportError('create-inherited-chat', creationError, { source_chat_id: sourceId })
    }
  }

  async function handleCopyText(content: string, source: 'message' | 'code' = 'message') {
    try {
      await navigator.clipboard.writeText(content)
    } catch (copyError) {
      await reportError('copy-output', copyError, { source })
    }
  }

  async function handleMessageFeedback(messageId: string, vote: 'up' | 'down') {
    setMessageFeedback((current) => ({ ...current, [messageId]: vote }))
    try {
      await createLogEvent({
        level: 'info',
        source: 'quality-feedback',
        message: vote === 'up' ? 'assistant-response-upvote' : 'assistant-response-downvote',
        chat_id: activeChatId ?? undefined,
        context: { message_id: messageId, vote },
      })
    } catch {
      // Best-effort feedback capture.
    }
  }

  async function handleRegenerateFromAssistant(assistantMessageId: string) {
    if (!activeChatId || isSending) return

    const assistantIndex = messages.findIndex((message) => message.id === assistantMessageId && message.role === 'assistant')
    if (assistantIndex <= 0) return

    let userIndex = -1
    for (let i = assistantIndex - 1; i >= 0; i -= 1) {
      if (messages[i]?.role === 'user') {
        userIndex = i
        break
      }
    }
    if (userIndex < 0) return

    const triggerMessage = messages[userIndex]
    const contextBefore = messages
      .slice(0, userIndex)
      .filter((message) => message.role === 'user' || message.role === 'assistant')
      .map((message) => ({ role: message.role, content: message.content }))

    setError(null)
    setIsSending(true)
    try {
      const response = await completeChat({
        chat_id: activeChatId,
        model: activeModelId || undefined,
        messages: [...contextBefore, { role: 'user', content: triggerMessage.content }],
        stream: false,
        temperature: 0.9,
        thinking_level: thinkingLevel,
        response_length: responseLength,
        addon_id: activeAddonId || undefined,
        attachment_upload_ids: selectedAttachmentIds,
        web_mode: webMode,
        interview_role: isCbiMode ? interviewRole : undefined,
        interview_panel_members: isCbiMode ? interviewPanelMembers : undefined,
        interview_organization_type: isCbiMode ? interviewOrgType : undefined,
        interview_organization_name: isCbiMode ? interviewOrgName : undefined,
        interview_location: isCbiMode ? interviewLocation : undefined,
        interview_is_hq: isCbiMode ? interviewIsHq : undefined,
        interview_duration_minutes: isCbiMode ? interviewDurationMinutes : undefined,
        interview_role_level: isCbiMode ? interviewRoleLevel : undefined,
        interview_realism_intensity: isCbiMode ? interviewRealismIntensity : undefined,
        delivery_signals: isCbiMode ? {
          tone_detected: 'confident',
          pacing: 'moderate',
          speech_clarity: 'high',
          filler_word_count: 2,
        } : undefined,
        interview_panelists: isCbiMode ? interviewPanelists.slice(0, interviewPanelMembers).map((panelist) => ({
          name: panelist.name,
          title: panelist.title,
          nationality: panelist.nationality,
          gender: panelist.gender,
          accent: panelist.accent,
          tone: panelist.tone,
          speaking_style: panelist.speaking_style,
          avatar_url: panelist.avatar_url,
        })) : undefined,
        interview_difficulty: isCbiMode ? interviewDifficulty : undefined,
        regenerate_target_message_id: assistantMessageId,
      })

      if (!response.trim()) {
        throw new Error('Regenerate returned empty output.')
      }

      const refreshed = await getChat(activeChatId)
      setActiveChat(refreshed)
      setMessages(toUiMessages(refreshed))
      const telemetry = await getChatTelemetry(activeChatId)
      setChatTelemetry(telemetry)
      await refreshChats(activeChatId)
    } catch (regenerateError) {
      await reportError('regenerate', regenerateError, { assistant_message_id: assistantMessageId })
    } finally {
      setIsSending(false)
    }
  }

  async function handleDeleteChat(chatId: string) {
    try {
      await deleteChat(chatId)
      const nextChats = await listChats()
      setChats(nextChats)
      if (activeChatId === chatId) {
        if (nextChats.length > 0) {
          await selectChat(nextChats[0].id, true)
        } else {
          setActiveChatId(null)
          setActiveChat(null)
          setMessages([])
          setChatTelemetry(null)
          setChatPath(null)
        }
      }
    } catch (deleteError) {
      await reportError('delete-chat', deleteError, { chatId })
    }
  }

  async function handleModelSelection(modelId: string) {
    setIsSwitchingModel(true)
    try {
      if (activeChatId) {
        const updated = await updateChat(activeChatId, { selected_model_id: modelId })
        setActiveChat((current) =>
          current ? { ...current, selected_model_id: updated.selected_model_id, updated_at: updated.updated_at } : current,
        )
        await refreshChats(activeChatId)
      } else {
        const updated = await setModelSelection(modelId)
        setDefaultModelId(updated.model_id)
      }
    } catch (selectionError) {
      await reportError('model-switch', selectionError, { modelId })
    } finally {
      setIsSwitchingModel(false)
    }
  }

  function toggleAttachmentForCurrentChat(uploadId: string) {
    if (!activeChatId) return
    setChatAttachmentMap((current) => {
      const existing = current[activeChatId] ?? []
      const next = existing.includes(uploadId) ? existing.filter((id) => id !== uploadId) : [...existing, uploadId]
      return { ...current, [activeChatId]: next }
    })
  }

  async function handleUploadFiles(files: FileList | null) {
    if (!files || files.length === 0) return

    setError(null)
    for (const file of Array.from(files)) {
      if (file.size > MAX_UPLOAD_BYTES) {
        await reportError('upload', `${file.name}: exceeds 500 GB limit`, { filename: file.name, size: file.size })
        continue
      }

      try {
        const started = await startUpload({
          filename: file.name,
          total_size_bytes: file.size,
          mime_type: file.type || undefined,
        })

        let offset = 0
        while (offset < file.size) {
          const end = Math.min(offset + CHUNK_SIZE_BYTES, file.size)
          const chunk = file.slice(offset, end)
          const isFinal = end >= file.size
          const progress = await uploadChunk(started.upload_id, chunk, offset, isFinal)
          offset = progress.received_bytes
        }
        if (activeChatId) {
          setChatAttachmentMap((current) => ({
            ...current,
            [activeChatId]: [...new Set([...(current[activeChatId] ?? []), started.upload_id])],
          }))
        }
      } catch (uploadError) {
        await reportError('upload', uploadError, { filename: file.name })
      }
    }

    const uploadList = await listUploads()
    setUploads(uploadList)
  }

  async function handleDeleteUpload(uploadId: string) {
    try {
      await deleteUpload(uploadId)
      setUploads((current) => current.filter((upload) => upload.id !== uploadId))
      setChatAttachmentMap((current) => {
        const next: Record<string, string[]> = {}
        for (const [chatId, ids] of Object.entries(current)) {
          next[chatId] = ids.filter((id) => id !== uploadId)
        }
        return next
      })
    } catch (deleteError) {
      await reportError('upload-delete', deleteError, { uploadId })
    }
  }

  async function handleSend(overrideContent?: string, isVoiceSubmit = false, bypassInterviewSessionGate = false) {
    const content = (overrideContent ?? input).trim()
    if ((!content && pastedImages.length === 0) || isSending) return
    if (activeModel && activeModel.available === false) {
      setError('Selected model is not loaded yet. Pick an available model first.')
      return
    }
    if (isCbiMode && !bypassInterviewSessionGate && interviewSessionState !== 'running') {
      setError('Click Start Interview to begin the CBI session.')
      return
    }

    setError(null)
    if (isVoiceSubmit) {
      setVoiceDraft('')
      voiceDraftRef.current = ''
    } else {
      setInput('')
    }
    setIsSending(true)
    let streamTimeoutId: number | null = null

    try {
      let chatId = activeChatId
      let workingChat = activeChat

      if (!chatId) {
        const created = await createChat({ selected_model_id: defaultModelId || undefined })
        chatId = created.id
        setChatAttachmentMap((current) => ({ ...current, [created.id]: [] }))
        await refreshChats(created.id)
        workingChat = await getChat(created.id)
        setActiveChatId(created.id)
        setActiveChat(workingChat)
        setChatPath(created.id)
      }

      if (chatId && workingChat?.title.startsWith('New Chat')) {
        const title = summarizeTitleFromPrompt(content || 'Image conversation')
        const renamed = await updateChat(chatId, { title })
        setActiveChat((current) =>
          current ? { ...current, title: renamed.title, updated_at: renamed.updated_at } : current,
        )
      }

      const priorMessages = toUiMessages(workingChat)

      let userMessageContent: string | Array<{ type: string; text?: string; image_url?: { url: string } }> = content
      if (pastedImages.length > 0) {
        const parts: Array<{ type: string; text?: string; image_url?: { url: string } }> = [{ type: 'text', text: content || 'Describe this image' }]
        for (const img of pastedImages) {
          parts.push({ type: 'image_url', image_url: { url: img } })
        }
        userMessageContent = parts
      }

      const userMessage: UiMessage = {
        id: crypto.randomUUID(),
        role: 'user',
        content: typeof userMessageContent === 'string' ? userMessageContent : (content || 'Image message'),
      }
      const assistantMessage: UiMessage = { id: crypto.randomUUID(), role: 'assistant', content: '' }

      setMessages([...priorMessages, userMessage, assistantMessage])
      setPastedImages([])

      const modelId = (workingChat?.selected_model_id ?? defaultModelId) || undefined
      const requestMessages: MessageInput[] = [
        ...priorMessages.map((m) => ({ role: m.role, content: m.content })),
        { role: 'user', content: userMessage.content },
      ]

      const controller = new AbortController()
      let timeoutTriggered = false
      const streamTimeoutMs = isCbiMode ? CBI_STREAM_RESPONSE_TIMEOUT_MS : STREAM_RESPONSE_TIMEOUT_MS
      streamTimeoutId = window.setTimeout(() => {
        timeoutTriggered = true
        controller.abort()
      }, streamTimeoutMs)
      activeSendController.current = controller

      await streamChatCompletion(
        {
          chat_id: chatId,
          model: modelId,
          messages: requestMessages,
          stream: true,
          thinking_level: thinkingLevel,
          response_length: responseLength,
          addon_id: activeAddonId || undefined,
          attachment_upload_ids: selectedAttachmentIds,
          web_mode: webMode,
          interview_role: isCbiMode ? interviewRole : undefined,
          interview_panel_members: isCbiMode ? interviewPanelMembers : undefined,
          interview_organization_type: isCbiMode ? interviewOrgType : undefined,
          interview_organization_name: isCbiMode ? interviewOrgName : undefined,
          interview_location: isCbiMode ? interviewLocation : undefined,
          interview_is_hq: isCbiMode ? interviewIsHq : undefined,
          interview_duration_minutes: isCbiMode ? interviewDurationMinutes : undefined,
          interview_realism_intensity: isCbiMode ? interviewRealismIntensity : undefined,
          interview_panelists: isCbiMode ? interviewPanelists.slice(0, interviewPanelMembers).map((panelist) => ({
            name: panelist.name,
            title: panelist.title,
            nationality: panelist.nationality,
            gender: panelist.gender,
            accent: panelist.accent,
            tone: panelist.tone,
            speaking_style: panelist.speaking_style,
          })) : undefined,
          interview_difficulty: isCbiMode ? interviewDifficulty : undefined,

        },
        (chunk) => {
          if (chunk.done || !chunk.token) return
          setMessages((current) => {
            const clone = [...current]
            const last = clone[clone.length - 1]
            if (!last || last.role !== 'assistant') return current
            clone[clone.length - 1] = { ...last, content: `${last.content}${chunk.token}` }
            return clone
          })
        },
        controller.signal,
      ).catch(async (streamError) => {
        if (controller.signal.aborted) {
          if (!timeoutTriggered) return
          throw streamError
        }
        const fallbackText = await completeChat(
          {
            chat_id: chatId,
            model: modelId,
            messages: requestMessages,
            stream: false,
            thinking_level: thinkingLevel,
            response_length: responseLength,
            addon_id: activeAddonId || undefined,
            attachment_upload_ids: selectedAttachmentIds,
            web_mode: webMode,
            interview_role: isCbiMode ? interviewRole : undefined,
            interview_panel_members: isCbiMode ? interviewPanelMembers : undefined,
            interview_organization_type: isCbiMode ? interviewOrgType : undefined,
            interview_organization_name: isCbiMode ? interviewOrgName : undefined,
            interview_location: isCbiMode ? interviewLocation : undefined,
            interview_is_hq: isCbiMode ? interviewIsHq : undefined,
            interview_duration_minutes: isCbiMode ? interviewDurationMinutes : undefined,
            interview_realism_intensity: isCbiMode ? interviewRealismIntensity : undefined,
            interview_panelists: isCbiMode ? interviewPanelists.slice(0, interviewPanelMembers).map((panelist) => ({
              name: panelist.name,
              title: panelist.title,
              nationality: panelist.nationality,
              gender: panelist.gender,
              accent: panelist.accent,
              tone: panelist.tone,
              speaking_style: panelist.speaking_style,
            })) : undefined,
            interview_difficulty: isCbiMode ? interviewDifficulty : undefined,

          },
          controller.signal,
        )

        if (fallbackText.trim()) {
          setMessages((current) => {
            const clone = [...current]
            const last = clone[clone.length - 1]
            if (!last || last.role !== 'assistant') return current
            clone[clone.length - 1] = { ...last, content: fallbackText }
            return clone
          })
          return
        }

        throw streamError
      })

      const refreshed = await getChat(chatId)
      setActiveChat(refreshed)
      setMessages(toUiMessages(refreshed))
      const telemetry = await getChatTelemetry(chatId)
      setChatTelemetry(telemetry)
      await refreshChats(chatId)
    } catch (sendError) {
      const lowered = String(sendError).toLowerCase()
      if (lowered.includes('aborted')) {
        await reportError(
          'chat-send-timeout',
          'Inference timed out. Please try another model or regenerate.',
          { addon: activeAddonId || 'general', thinkingLevel, responseLength, timeout_ms: (isCbiMode ? CBI_STREAM_RESPONSE_TIMEOUT_MS : STREAM_RESPONSE_TIMEOUT_MS) },
        )
        return
      }
      const message = lowered.includes('network')
        ? 'Network error while sending. Check API runtime and try again.'
        : asApiErrorMessage(String(sendError), 'Send failed')
      await reportError('chat-send', message, { addon: activeAddonId || 'general', thinkingLevel, responseLength })
    } finally {
      if (streamTimeoutId !== null) {
        window.clearTimeout(streamTimeoutId)
      }
      activeSendController.current = null
      setIsSending(false)
    }
  }

  const markdownComponents: Components = {
    code({ className, children, ...props }) {
      const childText = String(children ?? '')
      const language = className?.replace('language-', '') ?? ''
      const isBlock = childText.includes('\n')
      if (!isBlock) {
        return (
          <code className={className} {...props}>
            {children}
          </code>
        )
      }
      return (
        <div className="code-block-wrap">
          <div className="code-block-head">
            <span>{language || 'script'}</span>
            <button className="message-action-btn" onClick={() => void handleCopyText(childText, 'code')} type="button">
              Copy code
            </button>
          </div>
          <pre className="code-block-pre">
            <code className={className} {...props}>
              {children}
            </code>
          </pre>
        </div>
      )
    },
  }

  return (
    <div className={`app-shell ${isResizingRail ? 'resizing-rail' : ''}`}>
      <aside className="left-rail" style={{ width: `${leftRailWidth}px` }}>
        <div className="left-rail-top">
          <div className="brand-row">
            <img src={logoMark} alt="TurboGPT" className="brand-logo" />
            <span className="brand-name">TurboGPT</span>
          </div>

          <div className="new-chat-row">
            <button className="nav-btn primary" onClick={handleCreateChat}>+ New chat</button>
            <div className="inherit-row">
              <button
                className="secondary-btn"
                onClick={() => {
                  setShowInheritChooser((current) => !current)
                  if (!inheritSourceChatId) {
                    const preferred = activeChatId || inheritCandidates[0]?.id || ''
                    setInheritSourceChatId(preferred)
                  }
                }}
                disabled={chats.length === 0}
                title={chats.length ? 'Start a new chat inheriting a summary from another chat' : 'No chats available yet'}
              >
                Inherit summary
              </button>
              {showInheritChooser ? (
                <div className="inherit-chooser">
                  <select
                    className="model-selector inherit-select"
                    value={inheritSourceChatId}
                    onChange={(event) => setInheritSourceChatId(event.target.value)}
                  >
                    {inheritCandidates.map((candidate) => (
                      <option key={candidate.id} value={candidate.id}>{candidate.title}</option>
                    ))}
                    {!inheritCandidates.length ? (
                      <option value="">No source chat</option>
                    ) : null}
                  </select>
                  <button
                    className="secondary-btn"
                    onClick={() => void handleCreateInheritedChat(inheritSourceChatId)}
                    disabled={!inheritSourceChatId}
                  >
                    Create
                  </button>
                </div>
              ) : null}
            </div>
          </div>

          <div className="nav-section">
            <h4>My stuff</h4>
            <div className="my-stuff-card">
              <span>{uploads.length} uploads</span>
              <span>{healthStatus}</span>
            </div>
          </div>

          <div className="nav-section">
            <div className="drawer-head">
              <h4>Gems</h4>
              <button className="drawer-toggle" onClick={() => setIsGemDrawerOpen((open) => !open)} aria-expanded={isGemDrawerOpen}>
                {isGemDrawerOpen ? 'Hide' : 'Open'}
              </button>
            </div>
            <div className={`gem-drawer ${isGemDrawerOpen ? 'open' : ''}`}>
              <div className="gem-list">
                {addons.map((addon) => (
                  <button
                    key={addon.id}
                    className={`gem-item ${activeAddonId === addon.id ? 'active' : ''}`}
                    onClick={() => setActiveAddonId(addon.id)}
                    title={addon.tagline}
                  >
                    {addon.name}
                  </button>
                ))}
              </div>
            </div>
            <button className={`general-mode-btn ${activeAddonId === '' ? 'active' : ''}`} onClick={() => setActiveAddonId('')}>
              Use General Mode
            </button>
          </div>

          <div className="nav-section chats-section">
            <div className="drawer-head">
              <h4>Chats</h4>
              <div className="chat-filter-row">
                <button className={`chat-filter-btn ${chatDateFilter === 'today' ? 'active' : ''}`} onClick={() => setChatDateFilter('today')}>Today</button>
                <button className={`chat-filter-btn ${chatDateFilter === 'yesterday' ? 'active' : ''}`} onClick={() => setChatDateFilter('yesterday')}>Yesterday</button>
                <button className={`chat-filter-btn ${chatDateFilter === '7d' ? 'active' : ''}`} onClick={() => setChatDateFilter('7d')}>7d</button>
                <button className={`chat-filter-btn ${chatDateFilter === '30d' ? 'active' : ''}`} onClick={() => setChatDateFilter('30d')}>30d</button>
              </div>
            </div>
            <div className="chat-list">
              {filteredChats.map((chat) => (
                <button
                  key={chat.id}
                  className={`chat-item ${chat.id === activeChatId ? 'active' : ''}`}
                  onClick={() => void selectChat(chat.id, true)}
                >
                  <span className="chat-title">{chat.title}</span>
                  <span className="chat-time">{formatChatTimestamp(chat.updated_at)}</span>
                  <span
                    className="delete-chat"
                    role="button"
                    tabIndex={0}
                    onClick={(event) => {
                      event.stopPropagation()
                      void handleDeleteChat(chat.id)
                    }}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter') {
                        event.stopPropagation()
                        void handleDeleteChat(chat.id)
                      }
                    }}
                  >
                    x
                  </span>
                </button>
              ))}
              {filteredChats.length === 0 ? <div className="empty-chats">No chats in this period.</div> : null}
            </div>
          </div>
        </div>

        <div className="left-rail-footer">Settings & help</div>
      </aside>
      <div
        className="left-rail-resizer"
        role="separator"
        aria-label="Resize sidebar"
        onMouseDown={startRailResize}
      />

      <main className="chat-panel">
        {isCbiMode ? (
          <div className="interview-room-layout">
            <header className="interview-room-header">
              <div className="session-meta">
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                  <div className="un-logo-mini" />
                  <div>
                    <div className="session-role">{interviewRole} <span className="level-badge">{interviewRoleLevel}</span></div>
                    <div className="session-org">{interviewOrgName} | {interviewLocation}</div>
                  </div>
                </div>
              </div>

              <div className="session-stats">
                <div className="stat-item">
                  <div className="stat-label">Panel</div>
                  <div className="stat-value">{interviewPanelMembers} members</div>
                </div>
                <div className="stat-item">
                  <div className="stat-label">Duration</div>
                  <div className="stat-value">{interviewDurationMinutes}m</div>
                </div>
                <div className="stat-item">
                  <div className="stat-label">Difficulty</div>
                  <div className="stat-value">{interviewDifficulty.toUpperCase()}</div>
                </div>
              </div>

              <div className="session-actions">
                <div className={`state-badge ${interviewSessionState}`}>
                  {interviewSessionState === 'idle' ? 'Ready' : interviewSessionState.toUpperCase()}
                </div>
                {interviewSessionState === 'idle' ? (
                  <button className="nav-btn primary" onClick={() => void handleStartInterviewSession()}>Start Interview</button>
                ) : (
                  <>
                    <button className="secondary-btn" onClick={handlePauseInterviewSession} disabled={interviewSessionState !== 'running'}>Pause</button>
                    <button className="secondary-btn" onClick={() => void handleEndInterviewSession('manual')}>End Session</button>
                  </>
                )}
                <button className={`secondary-btn ${cameraActive ? 'active' : ''}`} onClick={() => void toggleInterviewCamera()}>
                  Camera {cameraActive ? 'On' : 'Off'}
                </button>
                <button className="secondary-btn" onClick={() => setShowAdvancedSetup(true)}>Setup</button>
              </div>
            </header>

            <div className="interview-room-main">
              <div className="panel-area">
                <div className="panelist-grid">
                  {interviewPanelists.slice(0, interviewPanelMembers).map((panelist, idx) => (
                    <div key={`${idx}-${panelist.name}`} className={`panelist-card ${activeSpeaker === panelist.name ? 'active-speaker' : ''}`}>
                      <div className="panelist-avatar">
                        {panelist.avatar_url ? (
                          <img src={panelist.avatar_url} alt={panelist.name} />
                        ) : (
                          panelist.name.charAt(0)
                        )}
                      </div>
                      <div className="panelist-info">
                        <div className="panelist-name">{panelist.name}</div>
                        <div className="panelist-title">{panelist.title}</div>
                        <div className="panelist-dept">{panelist.nationality}</div>
                      </div>
                    </div>
                  ))}
                </div>

                <div className="current-question-box">
                  <div className="question-label">
                    <span>Panel Evaluation / Current Question</span>
                    <span>{messages.filter(m => m.role === 'assistant').length} of 8 typical</span>
                  </div>
                  <div className="question-text">
                    {(() => {
                      const latestAssistant = [...messages].reverse().find(m => m.role === 'assistant')
                      if (!latestAssistant) return 'Waiting for panel to begin...'
                      const scorecard = extractCbiScorecard(latestAssistant.content)
                      return scorecard ? 'Interview concluded. View report below.' : stripCbiScorecardBlock(latestAssistant.content)
                    })()}
                  </div>
                  {(() => {
                    const latestAssistant = [...messages].reverse().find(m => m.role === 'assistant')
                    const scorecard = latestAssistant ? extractCbiScorecard(latestAssistant.content) : null
                    if (!scorecard) return null
                    return (
                      <div className="cbi-report-card" style={{ marginTop: '1.5rem' }}>
                        <div className="cbi-report-head">
                          <div>
                            <h4>Final Performance Report</h4>
                            <div style={{ fontSize: '0.75rem', color: '#718096', fontWeight: 600 }}>Level: {scorecard.level} | Verdict: {scorecard.verdict}</div>
                          </div>
                          <span className="cbi-score-badge">{Math.round(scorecard.overall_readiness_0_to_100)}% Readiness</span>
                        </div>

                        <div className="cbi-competency-list">
                          <h5 style={{ margin: '1rem 0 0.5rem', fontSize: '0.85rem', color: '#2d3748' }}>Competency Assessment</h5>
                          {scorecard.competencies?.map((competency) => {
                            const pct = Math.max(0, Math.min(100, Math.round((competency.score_1_to_5 / 5) * 100)))
                            return (
                              <div key={competency.name} className="cbi-competency-item">
                                <div className="cbi-competency-row">
                                  <strong>{competency.name}</strong>
                                  <span>{competency.score_1_to_5}/5</span>
                                </div>
                                <div className="cbi-competency-bar">
                                  <div className="cbi-competency-fill" style={{ width: `${pct}%` }} />
                                </div>
                                <p style={{ fontSize: '0.75rem' }}><strong>Evidence:</strong> {competency.evidence}</p>
                                <p style={{ fontSize: '0.75rem' }}><strong>Gaps:</strong> {competency.gaps}</p>
                              </div>
                            )
                          })}
                        </div>

                        <div className="delivery-assessment" style={{ marginTop: '1.5rem', padding: '1rem', background: '#f7fafc', borderRadius: '0.75rem', border: '1px solid #e2e8f0' }}>
                          <h5 style={{ margin: '0 0 0.75rem', fontSize: '0.85rem', color: '#2d3748' }}>Delivery & Presence</h5>
                          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '1rem', marginBottom: '0.75rem' }}>
                            <div className="stat-item">
                              <div className="stat-label" style={{ fontSize: '0.6rem' }}>Confidence</div>
                              <div className="stat-value" style={{ fontSize: '0.9rem' }}>{scorecard.delivery?.confidence ?? 0}%</div>
                            </div>
                            <div className="stat-item">
                              <div className="stat-label" style={{ fontSize: '0.6rem' }}>Clarity</div>
                              <div className="stat-value" style={{ fontSize: '0.9rem' }}>{scorecard.delivery?.clarity ?? 0}%</div>
                            </div>
                            <div className="stat-item">
                              <div className="stat-label" style={{ fontSize: '0.6rem' }}>Presence</div>
                              <div className="stat-value" style={{ fontSize: '0.9rem' }}>{scorecard.delivery?.presence ?? 0}%</div>
                            </div>
                          </div>
                          <p style={{ fontSize: '0.75rem', margin: 0 }}><strong>Feedback:</strong> {scorecard.delivery?.feedback ?? 'No feedback available'}</p>
                        </div>

                        <div className="panel-summary-box" style={{ marginTop: '1rem' }}>
                          <p style={{ fontSize: '0.8rem', color: '#4a5568' }}><strong>Panel Summary:</strong> {scorecard.panel_summary}</p>
                        </div>
                      </div>
                    )
                  })()}
                </div>
              </div>

              <div className="candidate-area">
                <div className={`candidate-self-view ${cameraActive ? 'active' : ''}`}>
                  {cameraActive ? (
                    <video ref={cameraVideoRef} className="candidate-video" autoPlay muted playsInline />
                  ) : (
                    <div className="camera-preview-empty" style={{ height: '100%', display: 'grid', placeItems: 'center', margin: 0 }}>
                      Camera is off
                    </div>
                  )}
                  <div className="self-view-overlay">
                    <div className="mic-status">
                      <div className={`mic-indicator ${isVoiceListening ? '' : 'silent'}`} />
                      {isVoiceListening ? 'MIC ACTIVE' : 'MIC MUTED'}
                    </div>
                  </div>
                </div>

                <div className="interview-timer-large">
                  <div className="timer-label">Remaining Time</div>
                  <div className={`timer-value ${interviewRemainingSeconds < 120 ? 'warning' : ''}`}>
                    {formatTimer(interviewRemainingSeconds)}
                  </div>
                </div>

                <div className="modal-section" style={{ background: 'white', padding: '1rem', borderRadius: '1rem', border: '1px solid #e2e8f0' }}>
                  <h4>Settings</h4>
                  <div style={{ display: 'grid', gap: '0.5rem' }}>
                    <button
                      className={`secondary-btn ${cbiTtsEnabled ? 'active' : ''}`}
                      onClick={() => setCbiTtsEnabled(!cbiTtsEnabled)}
                      style={{ width: '100%', justifyContent: 'center' }}
                    >
                      {cbiTtsEnabled ? 'Panel Audio: ON' : 'Panel Audio: OFF'}
                    </button>
                    <button
                      className="secondary-btn"
                      onClick={toggleDetachedCameraPreview}
                      style={{ width: '100%', justifyContent: 'center' }}
                    >
                      {cameraDetached ? 'Re-attach Camera' : 'Detach Camera (PiP)'}
                    </button>
                  </div>
                </div>
              </div>
            </div>

            <footer className="interview-response-bar">
              <div className="response-status">
                <div className={`status-dot ${isSending ? 'active' : ''}`} />
                {isSending ? 'Panel is listening...' : interviewSessionState === 'running' ? 'Awaiting candidate response' : 'Interview Room Ready'}
              </div>

              <div className="composer-inner" style={{ boxShadow: 'none', border: '1px solid #e2e8f0' }}>
                <div style={{ display: 'flex', gap: '1rem', alignItems: 'flex-end' }}>
                  <textarea
                    value={input}
                    placeholder="Type your response or use voice..."
                    onChange={(event) => {
                      setInput(event.target.value)
                      event.target.style.height = 'auto'
                      event.target.style.height = `${event.target.scrollHeight}px`
                    }}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter' && !event.shiftKey) {
                        event.preventDefault()
                        void handleSend(undefined, false)
                      }
                    }}
                    rows={1}
                    style={{ flex: 1 }}
                  />
                  <div className="send-stack">
                    {isSending ? (
                      <button className="stop-btn" onClick={stopGeneration}><div className="stop-icon" /></button>
                    ) : (
                      <div style={{ display: 'flex', gap: '0.5rem' }}>
                        <button
                          className={`voice-wave-btn ${isVoiceListening ? 'listening' : ''}`}
                          onClick={toggleVoiceInput}
                          type="button"
                        >
                          <span className="wave-icon"><i style={{ height: `${5 + (voiceLevel * 7)}px` }} /><i style={{ height: `${6 + (voiceLevel * 11)}px` }} /><i style={{ height: `${4 + (voiceLevel * 9)}px` }} /></span>
                          <span>{isVoiceListening ? 'Stop' : 'Voice'}</span>
                        </button>
                        <button className="nav-btn primary" disabled={!input.trim()} onClick={() => void handleSend(undefined, false)}>Send</button>
                      </div>
                    )}
                  </div>
                </div>
                {isVoiceListening || voiceDraft ? (
                  <div className="voice-live-text" style={{ marginTop: '0.75rem', padding: '0.5rem', background: '#f7fafc', borderRadius: '0.5rem' }}>
                    <strong>Draft:</strong> {voiceDraft || '...'}
                  </div>
                ) : null}
              </div>
            </footer>

            {interviewSessionState === 'idle' && (
              <div className="quick-setup-overlay">
                <div className="quick-setup-card">
                  <h2>Interview Room Ready</h2>
                  <p>Prepare for a realistic competency-based interview. Configure the basics or use advanced setup.</p>
                  
                  <div className="quick-setup-grid">
                    <div className="setup-field">
                      <label>Target Role</label>
                      <input value={interviewRole} onChange={(e) => setInterviewRole(e.target.value)} placeholder="e.g. Program Manager" />
                    </div>
                    <div className="setup-field">
                      <label>Role Level</label>
                      <select value={interviewRoleLevel} onChange={(e) => setInterviewRoleLevel(e.target.value as 'P2' | 'P3' | 'P4' | 'P5' | 'D1' | 'D2')}>
                        <option value="P2">P2 - Associate</option>
                        <option value="P3">P3 - Professional</option>
                        <option value="P4">P4 - Senior Professional</option>
                        <option value="P5">P5 - Managerial</option>
                        <option value="D1">D1 - Director</option>
                      </select>
                    </div>
                    <div className="setup-field">
                      <label>Organization</label>
                      <input value={interviewOrgName} onChange={(e) => setInterviewOrgName(e.target.value)} placeholder="e.g. United Nations" />
                    </div>
                    <div className="setup-field">
                      <label>Location</label>
                      <input value={interviewLocation} onChange={(e) => setInterviewLocation(e.target.value)} placeholder="e.g. Geneva, Switzerland" />
                    </div>
                  </div>

                  <div className="setup-actions">
                    <button className="primary-setup-btn" onClick={() => void handleStartInterviewSession(false)}>Start Practice Session</button>
                    {messages.length > 0 && (
                      <button className="primary-setup-btn" style={{ background: '#48bb78' }} onClick={() => void handleStartInterviewSession(true)}>Resume Session</button>
                    )}
                    <button className="secondary-btn" style={{ padding: '1rem' }} onClick={() => setShowAdvancedSetup(true)}>Advanced Setup</button>
                  </div>
                </div>
              </div>
            )}

            {showAdvancedSetup && (
              <div className="advanced-setup-modal">
                <div className="advanced-setup-content">
                  <header className="modal-header">
                    <h3>Interview Configuration</h3>
                    <button className="drawer-toggle" onClick={() => setShowAdvancedSetup(false)}>Close</button>
                  </header>
                  <div className="modal-body">
                    <div className="modal-section">
                      <h4>Session Settings</h4>
                      <div className="quick-setup-grid">
                        <div className="setup-field">
                          <label>Realism Intensity</label>
                          <select value={interviewRealismIntensity} onChange={(e) => setInterviewRealismIntensity(e.target.value as 'low' | 'medium' | 'high' | 'extreme')}>
                            <option value="low">Low - Supportive, Minimal probing</option>
                            <option value="medium">Medium - Standard CBI probing</option>
                            <option value="high">High - Strict, Deep probing, Pressure</option>
                            <option value="extreme">Extreme - Highly critical, Extreme pressure</option>
                          </select>
                        </div>
                        <div className="setup-field">
                          <label>Duration (Minutes)</label>
                          <input type="number" value={String(interviewDurationMinutes)} onChange={(e) => setInterviewDurationMinutes(Number(e.target.value))} />
                        </div>
                      </div>
                    </div>

                    <div className="modal-section">
                      <h4>Panel Demographics</h4>
                      <div className="interview-panelists" style={{ overflowX: 'visible' }}>
                        {interviewPanelists.slice(0, interviewPanelMembers).map((panelist, idx) => (
                          <div key={idx} className="interview-panelist-row" style={{ minWidth: 'auto', marginBottom: '1.5rem', display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '0.5rem' }}>
                            <div className="setup-field">
                              <label>Name & Role</label>
                              <input className="interview-input" style={{ marginBottom: '0.25rem' }} value={panelist.name} onChange={(e) => {
                                const val = e.target.value;
                                setInterviewPanelists(curr => curr.map((p, i) => i === idx ? { ...p, name: val } : p));
                              }} placeholder="Name" />
                              <input className="interview-input" value={panelist.title} onChange={(e) => {
                                const val = e.target.value;
                                setInterviewPanelists(curr => curr.map((p, i) => i === idx ? { ...p, title: val } : p));
                              }} placeholder="Role" />
                            </div>
                            <div className="setup-field">
                              <label>Voice & Accent</label>
                              <select className="model-selector" style={{ marginBottom: '0.25rem' }} value={panelist.gender} onChange={(e) => {
                                const val = e.target.value as PanelistGender;
                                setInterviewPanelists(curr => curr.map((p, i) => i === idx ? { ...p, gender: val } : p));
                              }}>
                                <option value="female">Female Voice</option>
                                <option value="male">Male Voice</option>
                                <option value="unknown">Neutral Voice</option>
                              </select>
                              <select className="model-selector" value={panelist.accent} onChange={(e) => {
                                const val = e.target.value as AccentPreference;
                                setInterviewPanelists(curr => curr.map((p, i) => i === idx ? { ...p, accent: val } : p));
                              }}>
                                {ACCENT_OPTIONS.map(opt => <option key={opt.value} value={opt.value}>{opt.label}</option>)}
                              </select>
                            </div>
                            <div className="setup-field">
                              <label>Tone & Style</label>
                              <select className="model-selector" style={{ marginBottom: '0.25rem' }} value={panelist.tone} onChange={(e) => {
                                const val = e.target.value as PanelistTone;
                                setInterviewPanelists(curr => curr.map((p, i) => i === idx ? { ...p, tone: val } : p));
                              }}>
                                <option value="formal">Formal</option>
                                <option value="probing">Probing</option>
                                <option value="neutral">Neutral</option>
                                <option value="supportive">Supportive</option>
                                <option value="skeptical">Skeptical</option>
                              </select>
                              <select className="model-selector" value={panelist.speaking_style} onChange={(e) => {
                                const val = e.target.value as SpeakingStyle;
                                setInterviewPanelists(curr => curr.map((p, i) => i === idx ? { ...p, speaking_style: val } : p));
                              }}>
                                <option value="fast">Fast</option>
                                <option value="structured">Structured</option>
                                <option value="conversational">Conversational</option>
                                <option value="strict">Strict</option>
                              </select>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>

                    <div className="modal-section">
                      <h4>Realism & Audio</h4>
                      <div style={{ display: 'flex', gap: '1rem' }}>
                        <label className="interview-toggle">
                          <input type="checkbox" checked={cbiTtsEnabled} onChange={(e) => setCbiTtsEnabled(e.target.checked)} />
                          <span>Enable Panel Voice</span>
                        </label>
                        <label className="interview-toggle">
                          <input type="checkbox" checked={autoStartCamera} onChange={(e) => setAutoStartCamera(e.target.checked)} />
                          <span>Auto-start Camera</span>
                        </label>
                      </div>
                    </div>
                  </div>
                  <footer className="modal-footer">
                    <button className="primary-setup-btn" style={{ flex: 'none', padding: '0.75rem 2rem' }} onClick={() => setShowAdvancedSetup(false)}>Save & Close</button>
                  </footer>
                </div>
              </div>
            )}
          </div>
        ) : (
          <>
            <header className="chat-header">
              <div className="header-left">TurboGPT</div>
              <div className="header-center">{activeChat?.title ?? 'New chat'}</div>
              <div className="header-right">{activeGemName} | {webMode ? 'Web mode' : 'Chat mode'}</div>
            </header>

            <div className="control-strip">
              <select value={activeModelId} onChange={(event) => void handleModelSelection(event.target.value)} className="model-selector" disabled={isSending || isSwitchingModel}>
                {models.map((model) => (
                  <option key={model.id} value={model.id} disabled={model.available === false}>
                    {model.display_name}{model.available === false ? ' (not loaded)' : ''}
                  </option>
                ))}
              </select>
              <select value={thinkingLevel} onChange={(event) => setThinkingLevel(event.target.value as 'fast' | 'balanced' | 'deep')} className="model-selector" disabled={isSending}>
                <option value="fast">Fast</option>
                <option value="balanced">Balanced</option>
                <option value="deep">Deep</option>
              </select>
              <select value={responseLength} onChange={(event) => setResponseLength(event.target.value as 'concise' | 'standard' | 'detailed')} className="model-selector" disabled={isSending}>
                <option value="concise">Concise</option>
                <option value="standard">Standard</option>
                <option value="detailed">Detailed</option>
              </select>
              <select value={webMode ? 'web' : 'chat'} onChange={(event) => setWebMode(event.target.value === 'web')} className="model-selector" disabled={isSending}>
                <option value="chat">Chat mode</option>
                <option value="web">Web mode</option>
              </select>
              <div className="context-meter" title="Context window usage">
                <div className="context-meter-top">
                  <span>Context</span>
                  <span className={`context-pressure-pill ${chatTelemetry?.pressure_status ?? 'unknown'}`}>
                    {(chatTelemetry?.pressure_status ?? 'unknown').toUpperCase()}
                  </span>
                </div>
                <div className="context-meter-center">
                  <div className={`context-meter-orb ${chatTelemetry?.pressure_status ?? 'unknown'}`}>
                    <strong>{contextUsagePercent}%</strong>
                    <small>used</small>
                  </div>
                  <div className="context-meter-details">
                    <div className="context-meter-track">
                      <div className={`context-meter-fill ${chatTelemetry?.pressure_status ?? 'unknown'}`} style={{ width: `${contextUsagePercent}%` }} />
                    </div>
                    <div className="context-meter-meta">
                      {chatTelemetry ? `${chatTelemetry.active_tokens_estimate}/${chatTelemetry.context_ceiling_tokens} tokens` : 'No data'}
                    </div>
                    <div className="context-meter-submeta">
                      Auto compaction ON at 98% context pressure.
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <section className="message-feed">
              {messages.length === 0 ? (
                <div className="empty-state">
                  <h3>Start chatting</h3>
                  <p>Each conversation has a unique browser URL and can use a specific Gem.</p>
                </div>
              ) : (
                messages.map((message) => (
                  <article key={message.id} className={`bubble ${message.role}`}>
                    {message.role === 'assistant' ? (
                      <div className="assistant-message">
                        <div className="markdown-body">
                          <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
                            {message.content || (isSending ? 'Thinking...' : '')}
                          </ReactMarkdown>
                        </div>
                        <div className="assistant-actions">
                          <button
                            className={`message-action-btn ${messageFeedback[message.id] === 'up' ? 'active' : ''}`}
                            onClick={() => void handleMessageFeedback(message.id, 'up')}
                            title="Thumbs up"
                            type="button"
                          >
                            {'\u{1F44D}'}
                          </button>
                          <button
                            className={`message-action-btn ${messageFeedback[message.id] === 'down' ? 'active' : ''}`}
                            onClick={() => void handleMessageFeedback(message.id, 'down')}
                            title="Thumbs down"
                            type="button"
                          >
                            {'\u{1F44E}'}
                          </button>
                          <button className="message-action-btn" onClick={() => void handleCopyText(message.content, 'message')} title="Copy response" type="button">
                            {'\u29C9'}
                          </button>
                          <button
                            className="message-action-btn"
                            onClick={() => void handleRegenerateFromAssistant(message.id)}
                            disabled={isSending || message.id !== latestAssistantMessageId}
                            title={message.id === latestAssistantMessageId ? 'Regenerate this response' : 'Only latest response can be regenerated'}
                            type="button"
                          >
                            {'\u21BB'}
                          </button>
                        </div>
                      </div>
                    ) : (
                      <p>{message.content}</p>
                    )}
                  </article>
                ))
              )}
              <div ref={messageEndRef} />
            </section>

            <footer className="composer">
              <div className="composer-inner">
                {pastedImages.length > 0 ? (
                  <div className="pasted-images-strip">
                    {pastedImages.map((src, idx) => (
                      <div key={idx} className="pasted-image-preview">
                        <img src={src} alt="Pasted" />
                        <button className="remove-pasted" onClick={() => setPastedImages((prev) => prev.filter((_, i) => i !== idx))}>x</button>
                      </div>
                    ))}
                  </div>
                ) : null}

                <textarea
                  value={input}
                  placeholder="Message TurboGPT"
                  onChange={(event) => {
                    setInput(event.target.value)
                    event.target.style.height = 'auto'
                    event.target.style.height = `${event.target.scrollHeight}px`
                  }}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' && !event.shiftKey) {
                      event.preventDefault()
                      void handleSend(undefined, false)
                    }
                  }}
                  rows={1}
                />

                <div className="composer-tools">
                  <div className="attachment-strip">
                    <input ref={fileInputRef} type="file" multiple className="hidden-input" onChange={(event) => void handleUploadFiles(event.target.files)} />
                    <button className="secondary-btn" onClick={() => fileInputRef.current?.click()}>Upload</button>
                    {uploads.slice(0, 3).map((upload) => {
                      const selected = selectedAttachmentIds.includes(upload.id)
                      return (
                        <button key={upload.id} className={`secondary-btn ${selected ? 'active' : ''}`} onClick={() => toggleAttachmentForCurrentChat(upload.id)} title={upload.original_name}>
                          {upload.original_name.slice(0, 10)}...
                        </button>
                      )
                    })}
                    {uploads.slice(0, 1).map((upload) => (
                      <button key={`${upload.id}-delete`} className="secondary-btn" onClick={() => void handleDeleteUpload(upload.id)}>
                        Remove latest
                      </button>
                    ))}
                  </div>

                  <div className="send-stack">
                    <button className="nav-btn primary" disabled={isSending || (!input.trim() && pastedImages.length === 0)} onClick={() => void handleSend(undefined, false)}>
                      {isSending ? 'Sending...' : 'Send'}
                    </button>
                  </div>
                </div>

                {error ? <div className="error-banner">{error}</div> : null}
              </div>
            </footer>
          </>
        )}
        {isCbiMode && !cameraDetached ? (
          <aside
            ref={cameraDockRef}
            className={`camera-dock ${cameraActive ? 'active' : ''} ${interviewSessionState !== 'idle' ? 'hidden-input' : ''}`}
            style={{ left: `${cameraDockPosition.x}px`, top: `${cameraDockPosition.y}px` }}
          >
            {/* Standard camera dock logic preserved but hidden during active room session */}
            {cameraError && <div className="camera-preview-error">{cameraError}</div>}
          </aside>
        ) : null}
      </main>
    </div>
  )
}

export default App


