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
}

export interface StreamChunk {
  token?: string
  done: boolean
  usedModelId?: string
  metadata?: Record<string, unknown>
}