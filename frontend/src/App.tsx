import { useEffect, useMemo, useState } from 'react'

import {
  createChat,
  deleteChat,
  getChat,
  getHealth,
  listChats,
  listModels,
  setModelSelection,
  streamChatCompletion,
  updateChat,
} from './api'
import type { ChatDetail, ChatSummary, MessageInput, ModelDescriptor } from './types'

import './styles.css'

interface UiMessage {
  id: string
  role: 'user' | 'assistant' | 'system' | 'tool'
  content: string
}

function toUiMessages(chat: ChatDetail | null): UiMessage[] {
  if (!chat) return []
  return chat.messages.map((message) => ({
    id: message.id,
    role: message.role,
    content: message.content,
  }))
}

function App() {
  const [models, setModels] = useState<ModelDescriptor[]>([])
  const [defaultModelId, setDefaultModelId] = useState<string>('')
  const [chats, setChats] = useState<ChatSummary[]>([])
  const [activeChatId, setActiveChatId] = useState<string | null>(null)
  const [activeChat, setActiveChat] = useState<ChatDetail | null>(null)
  const [messages, setMessages] = useState<UiMessage[]>([])
  const [input, setInput] = useState('')
  const [isSending, setIsSending] = useState(false)
  const [healthStatus, setHealthStatus] = useState('checking')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    void bootstrap()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function bootstrap() {
    try {
      const [modelsResponse, chatList, health] = await Promise.all([
        listModels(),
        listChats(),
        getHealth(),
      ])

      setModels(modelsResponse.models)
      setDefaultModelId(modelsResponse.default_model_id)
      setChats(chatList)
      setHealthStatus(health.ollama_reachable ? 'ready' : 'runtime unavailable')

      if (chatList.length > 0) {
        await selectChat(chatList[0].id)
      }
    } catch (loadError) {
      setError(String(loadError))
      setHealthStatus('degraded')
    }
  }

  const activeModelId = useMemo(() => {
    return activeChat?.selected_model_id ?? defaultModelId
  }, [activeChat?.selected_model_id, defaultModelId])

  async function refreshChats(selectId?: string) {
    const latest = await listChats()
    setChats(latest)
    if (selectId) {
      setActiveChatId(selectId)
    }
  }

  async function selectChat(chatId: string) {
    setActiveChatId(chatId)
    const detail = await getChat(chatId)
    setActiveChat(detail)
    setMessages(toUiMessages(detail))
  }

  async function handleCreateChat() {
    try {
      const chat = await createChat({ selected_model_id: defaultModelId || undefined })
      await refreshChats(chat.id)
      await selectChat(chat.id)
    } catch (creationError) {
      setError(String(creationError))
    }
  }

  async function handleDeleteChat(chatId: string) {
    try {
      await deleteChat(chatId)
      const nextChats = await listChats()
      setChats(nextChats)

      if (activeChatId === chatId) {
        if (nextChats.length > 0) {
          await selectChat(nextChats[0].id)
        } else {
          setActiveChatId(null)
          setActiveChat(null)
          setMessages([])
        }
      }
    } catch (deleteError) {
      setError(String(deleteError))
    }
  }

  async function handleModelSelection(modelId: string) {
    try {
      if (activeChatId) {
        const updated = await updateChat(activeChatId, { selected_model_id: modelId })
        setActiveChat((current) =>
          current
            ? {
                ...current,
                selected_model_id: updated.selected_model_id,
                updated_at: updated.updated_at,
              }
            : current,
        )
        await refreshChats(activeChatId)
      } else {
        const updated = await setModelSelection(modelId)
        setDefaultModelId(updated.model_id)
      }
    } catch (selectionError) {
      setError(String(selectionError))
    }
  }

  async function handleSend() {
    const content = input.trim()
    if (!content || isSending) return

    setError(null)
    setInput('')
    setIsSending(true)

    try {
      let chatId = activeChatId
      let workingChat = activeChat

      if (!chatId) {
        const created = await createChat({ selected_model_id: defaultModelId || undefined })
        chatId = created.id
        await refreshChats(created.id)
        workingChat = await getChat(created.id)
        setActiveChatId(created.id)
        setActiveChat(workingChat)
      }

      const priorMessages = toUiMessages(workingChat)
      const userMessage: UiMessage = {
        id: crypto.randomUUID(),
        role: 'user',
        content,
      }
      const assistantMessage: UiMessage = {
        id: crypto.randomUUID(),
        role: 'assistant',
        content: '',
      }

      const nextUiMessages = [...priorMessages, userMessage, assistantMessage]
      setMessages(nextUiMessages)

      const modelId = workingChat?.selected_model_id ?? (defaultModelId || undefined)
      const requestMessages: MessageInput[] = [...priorMessages, userMessage].map((message) => ({
        role: message.role,
        content: message.content,
      }))

      await streamChatCompletion(
        {
          chat_id: chatId,
          model: modelId,
          messages: requestMessages,
          stream: true,
        },
        (chunk) => {
          if (chunk.done) {
            return
          }
          if (!chunk.token) {
            return
          }

          setMessages((current) => {
            const clone = [...current]
            const last = clone[clone.length - 1]
            if (!last || last.role !== 'assistant') {
              return current
            }
            clone[clone.length - 1] = {
              ...last,
              content: `${last.content}${chunk.token}`,
            }
            return clone
          })
        },
      )

      const refreshed = await getChat(chatId)
      setActiveChat(refreshed)
      setMessages(toUiMessages(refreshed))
      await refreshChats(chatId)
    } catch (sendError) {
      setError(String(sendError))
    } finally {
      setIsSending(false)
    }
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand-block">
          <h1>Personal GOI</h1>
          <p>Local-first Gemma 4 assistant</p>
        </div>

        <button className="primary-btn" onClick={handleCreateChat}>
          New Chat
        </button>

        <div className="chat-list">
          {chats.map((chat) => (
            <button
              key={chat.id}
              className={`chat-item ${chat.id === activeChatId ? 'active' : ''}`}
              onClick={() => void selectChat(chat.id)}
            >
              <span>{chat.title}</span>
              <small>{chat.selected_model_id ?? defaultModelId}</small>
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
        </div>

        <div className="status-card">
          <strong>Runtime:</strong> {healthStatus}
        </div>
      </aside>

      <main className="chat-panel">
        <header className="chat-header">
          <div>
            <h2>{activeChat?.title ?? 'Start a new conversation'}</h2>
            <p>Choose model quality per chat</p>
          </div>
          <select
            value={activeModelId}
            onChange={(event) => void handleModelSelection(event.target.value)}
            className="model-selector"
          >
            {models.map((model) => (
              <option key={model.id} value={model.id}>
                {model.display_name}
              </option>
            ))}
          </select>
        </header>

        <section className="message-feed">
          {messages.length === 0 ? (
            <div className="empty-state">
              <h3>Ask anything</h3>
              <p>Use the model selector to switch between speed, balance, and deep quality modes.</p>
            </div>
          ) : (
            messages.map((message) => (
              <article key={message.id} className={`bubble ${message.role}`}>
                <span className="role">{message.role}</span>
                <p>{message.content || (isSending && message.role === 'assistant' ? 'Thinking...' : '')}</p>
              </article>
            ))
          )}
        </section>

        <footer className="composer">
          <textarea
            value={input}
            placeholder="Ask your assistant..."
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault()
                void handleSend()
              }
            }}
          />
          <button className="primary-btn" disabled={isSending} onClick={() => void handleSend()}>
            {isSending ? 'Sending...' : 'Send'}
          </button>
        </footer>

        {error ? <div className="error-banner">{error}</div> : null}
      </main>
    </div>
  )
}

export default App
