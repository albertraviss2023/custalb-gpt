export type Role = 'system' | 'user' | 'assistant' | 'tool'

export interface MessageInput {
  role: Role
  content: string
}

export interface MessageRecord {
  id: string
  chat_id: string
  role: Role
  content: string
  model_id?: string | null
  created_at: string
}

export interface ChatSummary {
  id: string
  title: string
  selected_model_id?: string | null
  created_at: string
  updated_at: string
}

export interface ChatDetail extends ChatSummary {
  messages: MessageRecord[]
}

export interface ModelDescriptor {
  id: string
  display_name: string
  quantization: string
  tier: string
  description: string
  runtime_ref?: string | null
  available?: boolean
}

export interface ModelsResponse {
  default_model_id: string
  models: ModelDescriptor[]
}

export interface ModelSelectionResponse {
  model_id: string
}

export interface ChatCompletionRequest {
  model?: string
  messages: MessageInput[]
  stream: boolean
  chat_id?: string
  temperature?: number
  max_tokens?: number
  thinking_level?: 'fast' | 'balanced' | 'deep'
  response_length?: 'concise' | 'standard' | 'detailed'
  addon_id?: string
  attachment_upload_ids?: string[]
  web_mode?: boolean
  interview_role?: string
  interview_panel_members?: number
  interview_organization_type?: 'un' | 'private_sector'
  interview_organization_name?: string
  interview_location?: string
  interview_is_hq?: boolean
  interview_duration_minutes?: number
  interview_role_level?: 'P2' | 'P3' | 'P4' | 'P5' | 'D1' | 'D2'
  interview_panelists?: Array<{
    name: string
    title: string
    nationality?: string
    voice_id?: string
    gender?: 'female' | 'male' | 'unknown'
    accent?: 'auto' | 'en-gb' | 'en-us' | 'en-au' | 'en-in' | 'en-za'
    tone?: 'formal' | 'probing' | 'neutral' | 'supportive' | 'skeptical'
    speaking_style?: 'fast' | 'structured' | 'conversational' | 'strict'
    avatar_url?: string
  }>
  interview_difficulty?: 'medium' | 'high'
  interview_realism_intensity?: 'low' | 'medium' | 'high' | 'extreme'
  delivery_signals?: Record<string, unknown>
  regenerate_target_message_id?: string
}

export interface StreamChunk {
  token?: string
  done: boolean
  usedModelId?: string
  metadata?: Record<string, unknown>
}

export interface AddonDescriptor {
  id: string
  name: string
  tagline: string
  description: string
  category: string
  capabilities: string[]
  installed: boolean
}

export interface AddonCatalogResponse {
  addons: AddonDescriptor[]
}

export interface AddonInstallResponse {
  addon_id: string
  installed: boolean
  installed_at?: string | null
}

export interface UploadRecord {
  id: string
  original_name: string
  mime_type?: string | null
  total_size_bytes: number
  received_bytes: number
  status: string
  created_at: string
  updated_at: string
}

export interface UploadStartResponse {
  upload_id: string
  max_upload_size_bytes: number
  chunk_endpoint: string
  record: UploadRecord
}

export interface UploadChunkResponse {
  upload_id: string
  received_bytes: number
  total_size_bytes: number
  status: string
}

export interface LogEventRecord {
  id: string
  level: 'debug' | 'info' | 'warning' | 'error'
  source: string
  message: string
  chat_id?: string | null
  context: Record<string, unknown>
  created_at: string
}

export interface ChatTelemetryResponse {
  chat_id: string
  model_id: string
  context_ceiling_tokens: number
  active_tokens_estimate: number
  pressure_status: 'green' | 'yellow' | 'red' | 'unknown'
  trigger_ratio: number
  trigger_tokens: number
  compaction_count: number
  summary_version: number
  last_compacted_message_id?: string | null
  recent_events: LogEventRecord[]
}

export interface ChatMemoryCompactionResponse {
  chat_id: string
  forgotten_messages: number
  summary_version: number
  compaction_count: number
  token_estimate: number
}
