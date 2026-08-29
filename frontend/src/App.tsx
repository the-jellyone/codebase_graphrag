import { useState, useRef, useEffect, useCallback } from 'react'
import {
  ChevronLeft, ChevronRight, ChevronDown, ChevronUp,
  Plus, MessageSquare, Settings, FolderOpen, Network,
  RotateCcw, ArrowUp, Info, ExternalLink, Trash2,
  Copy, Check, Play, Code2, Compass, X, Zap, Bot
} from 'lucide-react'
import './index.css'
import { api, streamMessage } from './api'
import type { Repo, Chat, Message, TraceEntry, RepoStats } from './api'

// ─── Cypher Query Card Component ──────────────────────────────────────────

function QueryCard({
  title,
  desc,
  cypher,
  onRun,
}: {
  title: string
  desc: string
  cypher: string
  onRun: (q: string) => void
}) {
  const [copied, setCopied] = useState(false)

  const copyToClipboard = () => {
    navigator.clipboard.writeText(cypher)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div style={{
      background: 'var(--bg-card)',
      border: '1px solid var(--border)',
      borderRadius: '8px',
      padding: '10px 12px',
      display: 'flex',
      flexDirection: 'column',
      gap: '6px',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div>
          <span style={{ fontWeight: 600, fontSize: '12px', color: 'var(--text)' }}>{title}</span>
          <p style={{ fontSize: '11px', color: 'var(--text-subtle)', margin: 0 }}>{desc}</p>
        </div>
        <div style={{ display: 'flex', gap: 4 }}>
          <button
            className="chevron-btn"
            onClick={copyToClipboard}
            title={copied ? "Copied!" : "Copy Cypher query"}
            style={{ padding: '4px', fontSize: '11px' }}
          >
            {copied ? <Check size={12} color="#16a34a" /> : <Copy size={12} />}
          </button>
          <button
            className="new-chat-btn"
            onClick={() => onRun(cypher)}
            title="Open in Neo4j Browser"
            style={{ fontSize: '11px', padding: '3px 7px', background: '#f3f4f6' }}
          >
            <Play size={10} style={{ fill: 'currentColor' }} /> Run
          </button>
        </div>
      </div>
      <pre style={{
        margin: 0,
        padding: '6px 8px',
        background: '#f8f7f5',
        border: '1px solid var(--border-light)',
        borderRadius: '5px',
        fontFamily: 'monospace',
        fontSize: '11px',
        color: '#1f2937',
        overflowX: 'auto',
        lineHeight: 1.4,
      }}>
        <code>{cypher}</code>
      </pre>
    </div>
  )
}

// ─── Sidebar (Accordion: Repositories with Nested Chats) ─────────────────

function Sidebar({
  repos,
  loading: reposLoading,
  activeRepoId,
  expandedRepoId,
  onToggleRepo,
  onDeleteRepo,
  repoChatsMap,
  loadingChatsRepoId,
  activeChatId,
  onSelectChat,
  onDeleteChat,
  onNewChatForRepo,
  onAddRepo,
  collapsed,
  onToggleCollapse,
}: {
  repos: Repo[]
  loading: boolean
  activeRepoId: string
  expandedRepoId: string
  onToggleRepo: (id: string) => void
  onDeleteRepo: (id: string, name: string) => void
  repoChatsMap: Record<string, Chat[]>
  loadingChatsRepoId: string | null
  activeChatId: string
  onSelectChat: (chatId: string, repoId: string) => void
  onDeleteChat: (chatId: string, repoId: string) => void
  onNewChatForRepo: (repoId: string) => void
  onAddRepo: () => void
  collapsed: boolean
  onToggleCollapse: () => void
}) {
  function relTime(iso?: string | null) {
    if (!iso) return ''
    const diff = Date.now() - new Date(iso).getTime()
    const h = diff / 3600000
    if (h < 1) return 'Just now'
    if (h < 24) return `${Math.floor(h)}h ago`
    const d = h / 24
    if (d < 2) return 'Yesterday'
    if (d < 7) return `${Math.floor(d)}d ago`
    return `${Math.floor(d / 7)}w ago`
  }

  return (
    <aside className={`sidebar${collapsed ? ' collapsed' : ''}`}>
      {/* Top Logo & Collapse Toggle */}
      <div className="sidebar-logo">
        <div className="logo-mark">
          <div className="logo-icon" title="CodeGraph">CG</div>
          <span className="logo-text">CodeGraph</span>
        </div>
        <button
          className="chevron-btn"
          onClick={onToggleCollapse}
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {collapsed ? <ChevronRight size={14} /> : <ChevronLeft size={14} />}
        </button>
      </div>

      {/* Accordion Repositories Section */}
      <div className="sidebar-section" style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column' }}>
        <div className="sidebar-section-label">Repositories</div>

        {reposLoading ? (
          <div style={{ padding: '8px', fontSize: '11.5px', color: 'var(--text-subtle)', textAlign: collapsed ? 'center' : 'left' }}>
            …
          </div>
        ) : repos.length === 0 ? (
          <div style={{ padding: '6px 8px', fontSize: '11.5px', color: 'var(--text-subtle)' }}>
            {!collapsed && "No repositories"}
          </div>
        ) : (
          <ul className="repo-list">
            {repos.map(r => {
              const isExpanded = r.repo_id === expandedRepoId && !collapsed
              const repoChats = repoChatsMap[r.repo_id] || []
              const isLoadingChats = loadingChatsRepoId === r.repo_id

              return (
                <li key={r.repo_id} className="repo-accordion-group">
                  {/* Repo Header Row */}
                  <div
                    className={`repo-header-row${r.repo_id === activeRepoId ? ' active' : ''}`}
                    onClick={() => onToggleRepo(r.repo_id)}
                    title={`${r.name} (${r.status})`}
                  >
                    {!collapsed && (
                      <span className="repo-chevron">
                        {isExpanded ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
                      </span>
                    )}
                    <span className={`status-dot ${r.dot_color === 'green' ? 'dot-green' : r.dot_color === 'amber' ? 'dot-amber' : 'dot-grey'}`} />
                    <span className="repo-name" style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis' }}>{r.name}</span>
                    {!collapsed && (
                      <button
                        className="repo-delete-btn"
                        onClick={(e) => {
                          e.stopPropagation()
                          onDeleteRepo(r.repo_id, r.name)
                        }}
                        title={`Delete ${r.name}`}
                      >
                        <Trash2 size={11} />
                      </button>
                    )}
                  </div>

                  {/* Nested Chats List (Only for expanded repo) */}
                  {isExpanded && (
                    <div className="nested-chats-container">
                      {isLoadingChats ? (
                        <div style={{ fontSize: '11px', color: 'var(--text-subtle)', padding: '3px 8px' }}>
                          Loading chats…
                        </div>
                      ) : repoChats.length === 0 ? (
                        <div style={{ fontSize: '11px', color: 'var(--text-subtle)', padding: '3px 8px' }}>
                          No chats yet
                        </div>
                      ) : (
                        <div className="nested-chats-scroll">
                          {repoChats.map(c => (
                            <div
                              key={c.chat_id}
                              className={`nested-chat-item${c.chat_id === activeChatId ? ' active' : ''}`}
                              onClick={() => onSelectChat(c.chat_id, r.repo_id)}
                            >
                              <MessageSquare size={11} style={{ flexShrink: 0, opacity: 0.7 }} />
                              <span className="nested-chat-title">{c.title}</span>
                              <span className="nested-chat-time">{relTime(c.created_at)}</span>
                              <button
                                className="chat-delete-btn"
                                onClick={(e) => {
                                  e.stopPropagation()
                                  onDeleteChat(c.chat_id, r.repo_id)
                                }}
                                title="Delete this chat"
                              >
                                <Trash2 size={10} />
                              </button>
                            </div>
                          ))}
                        </div>
                      )}

                      {/* Inline + New Chat button under the expanded repo */}
                      <button
                        className="nested-new-chat-btn"
                        onClick={(e) => {
                          e.stopPropagation()
                          onNewChatForRepo(r.repo_id)
                        }}
                        title={`Create new chat for ${r.name}`}
                      >
                        <Plus size={11} /> New Chat
                      </button>
                    </div>
                  )}
                </li>
              )
            })}
          </ul>
        )}

        <button className="add-repo-btn" onClick={onAddRepo} title="Add Repository" style={{ marginTop: 8 }}>
          <Plus size={13} />
          <span className="add-repo-text">Add Repository</span>
        </button>
      </div>

      {/* Sidebar Footer */}
      <div className="sidebar-footer">
        <div className="user-info">
          <div className="user-avatar" title="Local User">U</div>
          <div className="user-details">
            <span className="user-name">local</span>
            <span className="user-plan">self-hosted</span>
          </div>
        </div>
        <button className="settings-btn" title="Settings"><Settings size={14} /></button>
      </div>
    </aside>
  )
}

// ─── KG Viewer Panel (Cypher Query Inspector & Launcher) ─────────────────

function KGPanel({
  repoId, repoName, repoStatus, onClose, onResync, onRebuild, actionStatus,
}: {
  repoId: string
  repoName?: string
  repoStatus?: string
  onClose: () => void
  onResync: () => void
  onRebuild: () => void
  actionStatus: string
}) {
  const [stats, setStats] = useState<RepoStats | null>(null)

  const fetchStats = useCallback(async () => {
    if (!repoId) return
    try {
      const statsData = await api.repos.stats(repoId)
      setStats(statsData)
    } catch (e) {
      console.error('Failed to load KG stats', e)
    }
  }, [repoId])

  useEffect(() => {
    fetchStats()
  }, [fetchStats, actionStatus])

  // Poll stats if indexing or rebuilding
  useEffect(() => {
    if (repoStatus === 'indexing' || actionStatus.includes('Rebuilding') || actionStatus.includes('Resyncing')) {
      const interval = setInterval(fetchStats, 2000)
      return () => clearInterval(interval)
    }
  }, [repoStatus, actionStatus, fetchStats])

  function relTime(iso?: string | null) {
    if (!iso) return 'Never'
    const diff = Date.now() - new Date(iso).getTime()
    const m = diff / 60000
    if (m < 1) return 'Just now'
    if (m < 60) return `${Math.floor(m)}m ago`
    const h = m / 60
    if (h < 24) return `${Math.floor(h)}h ago`
    return new Date(iso).toLocaleDateString()
  }

  const runCypherInNeo4j = (cypher: string) => {
    const encoded = encodeURIComponent(cypher)
    window.open(`http://localhost:7474/browser/?cmd=edit&arg=${encoded}`, '_blank')
  }

  const currentStatus = repoStatus || stats?.status || 'idle'

  // Strictly Scoped Queries for this specific repo_id
  const targetId = repoId || 'test_repo'
  const queries = [
    {
      title: "1. Complete Repository Graph (Connected + Standalone)",
      desc: `Visualizes every single node (connected and standalone) and all relationships in ${repoName || targetId}.`,
      cypher: `MATCH (n {repo_id: '${targetId}'}) OPTIONAL MATCH (n)-[r]-(m {repo_id: '${targetId}'}) RETURN n, r, m LIMIT 200`,
    },
    {
      title: "2. All Entities in this Repository",
      desc: `Lists all functions, classes, and modules belonging to ${repoName || targetId}.`,
      cypher: `MATCH (n {repo_id: '${targetId}'}) RETURN n LIMIT 100`,
    },
    {
      title: "3. Function Call Graph (Execution Chains)",
      desc: "Traces direct calls between functions in this repository.",
      cypher: `MATCH (f:Function {repo_id: '${targetId}'})-[r:CALLS]->(t:Function {repo_id: '${targetId}'}) RETURN f, r, t LIMIT 50`,
    },
    {
      title: "4. Class Methods & Structure",
      desc: "Classes and their encapsulated methods in this repository.",
      cypher: `MATCH (c:Class {repo_id: '${targetId}'})-[r:HAS_METHOD]->(m:Function {repo_id: '${targetId}'}) RETURN c, r, m LIMIT 50`,
    },
    {
      title: "5. Architecture Hubs (Most Coupled Entities)",
      desc: "Most connected symbols inside this repository.",
      cypher: `MATCH (n {repo_id: '${targetId}'}) OPTIONAL MATCH (n)-[r]-(m {repo_id: '${targetId}'}) WITH n, count(r) AS degree ORDER BY degree DESC RETURN n.name, labels(n)[0] AS type, n.file AS file, degree LIMIT 15`,
    },
    {
      title: "6. Module Architecture (Files & Contents)",
      desc: "Module files and everything they contain.",
      cypher: `MATCH (mod:Module {repo_id: '${targetId}'})-[r:CONTAINS]->(item {repo_id: '${targetId}'}) RETURN mod, r, item LIMIT 50`,
    },
  ]

  return (
    <aside className="kg-panel">
      {/* Header */}
      <div className="kg-header">
        <span className="kg-title">Knowledge Graph</span>
        <button className="chevron-btn" onClick={onClose} title="Close KG Panel">
          <ChevronRight size={15} />
        </button>
      </div>

      {/* Part A: Indexing Status Card */}
      <div className="kg-status-card">
        <div className="kg-status-row">
          <div className="kg-metrics-group">
            <div className="kg-metric-item">
              <span className="kg-metric-val">{stats?.node_count?.toLocaleString() ?? '—'}</span>
              <span className="kg-metric-lbl">Nodes</span>
            </div>
            <div className="kg-metric-item">
              <span className="kg-metric-val">{stats?.edge_count?.toLocaleString() ?? '—'}</span>
              <span className="kg-metric-lbl">Edges</span>
            </div>
            <div className="kg-metric-item">
              <span className="kg-metric-val" style={{ fontSize: '11px', marginTop: 1 }}>{relTime(stats?.last_synced)}</span>
              <span className="kg-metric-lbl">Last Synced</span>
            </div>
          </div>

          <span className={`kg-status-pill ${
            currentStatus === 'ready' ? 'pill-synced' :
            currentStatus === 'indexing' ? 'pill-indexing' : 'pill-idle'
          }`}>
            <span className={`status-dot ${
              currentStatus === 'ready' ? 'dot-green' :
              currentStatus === 'indexing' ? 'dot-amber' : 'dot-grey'
            }`} style={{ width: 6, height: 6 }} />
            {currentStatus === 'ready' ? 'Synced' : currentStatus === 'indexing' ? 'Indexing' : 'Idle'}
          </span>
        </div>

        {/* Action Controls */}
        <div className="kg-card-actions">
          <button className="kg-primary-btn" onClick={onResync} title="Scan and update changed files">
            <RotateCcw size={12} /> Resync
          </button>
          <button className="kg-secondary-btn" onClick={onRebuild} title="Full wipe and reparse">
            Full Rebuild
          </button>
        </div>

        {actionStatus && (
          <div style={{ fontSize: '11.5px', color: '#92400e', background: '#fef3c7', padding: '4px 8px', borderRadius: 4, marginTop: 2 }}>
            {actionStatus}
          </div>
        )}
      </div>

      {/* Part B: Launch Banner & Cypher Query Inspector */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflowY: 'auto', padding: '14px', gap: '12px', background: '#faf9f8' }}>
        {/* Launch Neo4j Browser Card */}
        <div style={{
          background: 'var(--btn-dark)',
          color: '#ffffff',
          borderRadius: '10px',
          padding: '14px',
          display: 'flex',
          flexDirection: 'column',
          gap: '8px',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span style={{ fontWeight: 700, fontSize: '13px', letterSpacing: '-0.01em' }}>Neo4j Graph Browser</span>
            <Compass size={16} color="#38bdf8" />
          </div>
          <p style={{ fontSize: '11.5px', color: '#d1d5db', margin: 0, lineHeight: 1.45 }}>
            Open Neo4j's native graph visualizer to explore 2D force graphs, filter relationships, and run custom Cypher queries for <strong>{repoName || 'this repository'}</strong>.
          </p>
          <button
            onClick={() => runCypherInNeo4j(queries[0].cypher)}
            style={{
              marginTop: 4,
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 6,
              background: '#ffffff',
              color: '#1a1a1a',
              border: 'none',
              borderRadius: '6px',
              padding: '7px 12px',
              fontSize: '12px',
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            <ExternalLink size={12} /> Launch in Neo4j Browser
          </button>
        </div>

        {/* Section Header */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 4 }}>
          <Code2 size={13} color="var(--text-muted)" />
          <span style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-subtle)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Ready-To-Run Cypher Queries
          </span>
        </div>

        {/* Query Cards List */}
        {queries.map((q, i) => (
          <QueryCard
            key={i}
            title={q.title}
            desc={q.desc}
            cypher={q.cypher}
            onRun={runCypherInNeo4j}
          />
        ))}
      </div>
    </aside>
  )
}

// ─── Mode Info Modal (Minimalist Popup) ───────────────────────────────────

function ModeInfoModal({ onClose }: { onClose: () => void }) {
  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.35)',
      display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 300,
      backdropFilter: 'blur(2px)',
    }} onClick={onClose}>
      <div style={{
        background: 'var(--bg-card)', border: '1px solid var(--border)',
        borderRadius: 12, padding: '22px 24px', width: 460, maxWidth: '90vw',
        boxShadow: '0 16px 36px rgba(0,0,0,0.14)',
        display: 'flex', flexDirection: 'column', gap: 16,
      }} onClick={e => e.stopPropagation()}>
        
        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
            <Info size={16} color="var(--text)" />
            <h3 style={{ fontWeight: 700, fontSize: 15, margin: 0, color: 'var(--text)' }}>
              Retrieval & Reasoning Modes
            </h3>
          </div>
          <button
            onClick={onClose}
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', padding: 2 }}
          >
            <X size={16} />
          </button>
        </div>

        {/* Comparison Cards */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {/* Graph RAG */}
          <div style={{
            background: '#fbfaf9', border: '1px solid var(--border)',
            borderRadius: 8, padding: '12px 14px', display: 'flex', flexDirection: 'column', gap: 6
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <Zap size={14} color="#f59e0b" />
              <span style={{ fontWeight: 600, fontSize: 13, color: 'var(--text)' }}>Graph RAG Mode</span>
              <span style={{ fontSize: 10, background: '#fef3c7', color: '#92400e', padding: '1px 6px', borderRadius: 4, fontWeight: 600 }}>
                FAST
              </span>
            </div>
            <p style={{ fontSize: 12, color: 'var(--text-muted)', margin: 0, lineHeight: 1.45 }}>
              <strong>What it is:</strong> Performs a single-step vector search to locate matching symbols, then extracts a 2-hop connected subgraph directly into the prompt.
            </p>
            <p style={{ fontSize: 11.5, color: 'var(--text-subtle)', margin: 0, lineHeight: 1.4 }}>
              <strong>Best when:</strong> Looking up specific functions, classes, docstrings, or quick questions where immediate response speed is preferred.
            </p>
          </div>

          {/* Agent */}
          <div style={{
            background: '#fbfaf9', border: '1px solid var(--border)',
            borderRadius: 8, padding: '12px 14px', display: 'flex', flexDirection: 'column', gap: 6
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <Bot size={14} color="#3b82f6" />
              <span style={{ fontWeight: 600, fontSize: 13, color: 'var(--text)' }}>Agent Mode</span>
              <span style={{ fontSize: 10, background: '#eff6ff', color: '#1e40af', padding: '1px 6px', borderRadius: 4, fontWeight: 600 }}>
                AUTONOMOUS
              </span>
            </div>
            <p style={{ fontSize: 12, color: 'var(--text-muted)', margin: 0, lineHeight: 1.45 }}>
              <strong>What it is:</strong> A 3-node LangGraph loop (Orchestrator → Executor → Synthesizer). Follows multi-hop call chains, executes Cypher queries, and detects knowledge gaps before synthesizing answers.
            </p>
            <p style={{ fontSize: 11.5, color: 'var(--text-subtle)', margin: 0, lineHeight: 1.4 }}>
              <strong>Best when:</strong> Tracing call chains, impact analysis (<em>"what breaks if I change X?"</em>), debugging flows, and deep architectural explanations.
            </p>
          </div>
        </div>

        {/* Footer button */}
        <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 2 }}>
          <button
            onClick={onClose}
            className="send-btn"
            style={{ width: 'auto', borderRadius: 6, padding: '6px 16px', fontSize: 12, fontWeight: 600 }}
          >
            Got it
          </button>
        </div>
      </div>
    </div>
  )
}

// ─── Mode Toggle ─────────────────────────────────────────────────────────

function ModeToggle({ mode, onChange }: { mode: 'graph_rag' | 'agent'; onChange: (m: 'graph_rag' | 'agent') => void }) {
  const [showInfo, setShowInfo] = useState(false)

  return (
    <>
      {showInfo && <ModeInfoModal onClose={() => setShowInfo(false)} />}
      <div className="mode-toggle-wrap">
        <div className="mode-toggle" style={{ gap: 2 }}>
          <button
            className={`mode-btn${mode === 'graph_rag' ? ' active' : ''}`}
            onClick={() => onChange('graph_rag')}
          >
            Graph RAG
          </button>
          <button
            className={`mode-btn${mode === 'agent' ? ' active' : ''}`}
            onClick={() => onChange('agent')}
          >
            Agent
          </button>
          <button
            type="button"
            className="mode-btn"
            onClick={() => setShowInfo(true)}
            title="Learn about Graph RAG vs Agent mode"
            style={{ padding: '5px 8px', borderRadius: 18, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)' }}
          >
            <Info size={13} />
          </button>
        </div>
      </div>
    </>
  )
}

// ─── Message Renderer ─────────────────────────────────────────────────────

function AssistantMessage({ msg }: { msg: Message & { streaming?: boolean; streamContent?: string } }) {
  const [traceOpen, setTraceOpen] = useState(false)
  const content = msg.streaming ? (msg.streamContent ?? '') : msg.content

  return (
    <div className="msg-assistant">
      <div className="msg-assistant-header">
        <div className="assistant-icon">CG</div>
        <span className="assistant-name">CodeGraph Agent</span>
        {msg.is_partial && <span className="partial-badge">• Partial answer</span>}
        {msg.streaming && <span style={{ fontSize: 11, color: 'var(--text-subtle)', marginLeft: 4 }}>thinking…</span>}
      </div>
      <div className="msg-assistant-body">
        {content ? (
          <div dangerouslySetInnerHTML={{ __html: renderMd(content) }} />
        ) : (
          <div style={{ color: 'var(--text-subtle)', fontStyle: 'italic' }}>Analyzing repository knowledge graph…</div>
        )}
      </div>
      {msg.trace && msg.trace.length > 0 && (
        <div className="reasoning-trace">
          <div className="reasoning-header" onClick={() => setTraceOpen(o => !o)}>
            {traceOpen ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
            Reasoning trace ({msg.trace.length} steps)
          </div>
          {traceOpen && (
            <div className="reasoning-body">
              {msg.trace.map((t: TraceEntry, i: number) => (
                <div key={i} className="trace-line">
                  <span className="trace-arrow">›</span>
                  <span>
                    {t.tool}({Object.entries(t.args || {}).map(([k, v]) => `${k}=${typeof v === 'string' ? `"${v}"` : JSON.stringify(v)}`).join(', ')})
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function renderMd(text: string): string {
  if (!text) return ''
  return text
    .replace(/```(\w*)\n([\s\S]*?)```/g, (_m, _lang, code) =>
      `<pre class="code-block"><code>${code.replace(/</g, '&lt;').replace(/>/g, '&gt;')}</code></pre>`)
    .replace(/`([^`]+)`/g, '<code style="background:#eeede9;padding:1px 4px;border-radius:3px;font-family:monospace">$1</code>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/^(\d+)\. /gm, '<br/>$1. ')
    .replace(/^- /gm, '<br/>• ')
    .replace(/\n/g, '<br/>')
}

// ─── Input Bar ────────────────────────────────────────────────────────────

function InputBar({ disabled, placeholder, onSend }: {
  disabled?: boolean
  placeholder: string
  onSend: (text: string) => void
}) {
  const [val, setVal] = useState('')
  const ref = useRef<HTMLInputElement>(null)

  function submit() {
    const t = val.trim()
    if (!t || disabled) return
    onSend(t)
    setVal('')
  }

  return (
    <div className="input-area">
      <div className="input-wrap">
        <input
          ref={ref}
          className="input-field"
          placeholder={placeholder}
          value={val}
          onChange={e => setVal(e.target.value)}
          disabled={disabled}
          onKeyDown={e => e.key === 'Enter' && !e.shiftKey && submit()}
        />
        <button className="send-btn" disabled={disabled || !val.trim()} onClick={submit}>
          <ArrowUp size={15} />
        </button>
      </div>
    </div>
  )
}

// ─── Add Repo Modal (With Native OS Folder Picker & Dropzone) ─────────────

function AddRepoModal({ onClose, onAdd }: { onClose: () => void; onAdd: (source: string, name: string) => void }) {
  const [source, setSource] = useState('')
  const [name, setName] = useState('')
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [isDragging, setIsDragging] = useState(false)

  // Handle native OS directory picker selection
  const handleFolderSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files
    if (files && files.length > 0) {
      // First file in webkitRelativePath contains the root folder name
      const relativePath = files[0].webkitRelativePath
      const folderName = relativePath.split('/')[0] || 'Selected Repo'
      
      // If full path is accessible or infer local path
      setSource(folderName)
      if (!name) setName(folderName)
    }
  }

  // Handle Drag & Drop
  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
    if (e.dataTransfer.items && e.dataTransfer.items.length > 0) {
      const item = e.dataTransfer.items[0]
      const entry = item.webkitGetAsEntry ? item.webkitGetAsEntry() : null
      if (entry && entry.isDirectory) {
        setSource(entry.name)
        if (!name) setName(entry.name)
      }
    }
  }

  const quickPresets = [
    { label: 'test_repo', path: 'test_repo' },
    { label: 'disease based diet', path: '/Users/Hakim/Desktop/projects/disease based diet' },
    { label: 'allergen-classifier', path: '/Users/Hakim/Desktop/projects/allergen-classifier' },
  ]

  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.3)',
      display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 200,
    }}>
      <div style={{
        background: 'var(--bg-card)', border: '1px solid var(--border)',
        borderRadius: 12, padding: 24, width: 440, boxShadow: '0 12px 32px rgba(0,0,0,0.12)',
        display: 'flex', flexDirection: 'column', gap: 14,
      }}>
        <div>
          <h3 style={{ fontWeight: 700, fontSize: 16, color: 'var(--text)', margin: '0 0 4px' }}>Add Repository</h3>
          <p style={{ fontSize: 12, color: 'var(--text-muted)', margin: 0 }}>
            Choose a local project folder from your disk or enter a repository path.
          </p>
        </div>

        {/* Hidden Directory Input */}
        <input
          type="file"
          ref={fileInputRef}
          // @ts-expect-error webkitdirectory is standard in all modern browsers
          webkitdirectory=""
          directory=""
          multiple
          onChange={handleFolderSelect}
          style={{ display: 'none' }}
        />

        {/* Native Folder Picker / Dropzone */}
        <div
          onClick={() => fileInputRef.current?.click()}
          onDragOver={(e) => { e.preventDefault(); setIsDragging(true) }}
          onDragLeave={() => setIsDragging(false)}
          onDrop={handleDrop}
          style={{
            border: isDragging ? '2px dashed #3b82f6' : '1.5px dashed var(--border)',
            borderRadius: 8,
            padding: '20px 16px',
            textAlign: 'center',
            cursor: 'pointer',
            background: isDragging ? '#eff6ff' : '#fbfaf9',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: 6,
            transition: 'all 0.15s ease',
          }}
        >
          <FolderOpen size={28} color={isDragging ? '#3b82f6' : 'var(--text-muted)'} />
          <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text)' }}>
            Click to Browse Folder from Disk
          </span>
          <span style={{ fontSize: 11, color: 'var(--text-subtle)' }}>
            or drag & drop a project directory here
          </span>
        </div>

        {/* Quick Suggestion Chips */}
        <div>
          <span style={{ fontSize: 10.5, fontWeight: 600, color: 'var(--text-subtle)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
            Quick Projects:
          </span>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 4 }}>
            {quickPresets.map(p => (
              <button
                key={p.path}
                type="button"
                onClick={() => { setSource(p.path); setName(p.label); }}
                style={{
                  fontSize: 11, padding: '3px 8px', borderRadius: 4,
                  border: '1px solid var(--border)', background: 'var(--bg)',
                  color: 'var(--text)', cursor: 'pointer',
                }}
              >
                📁 {p.label}
              </button>
            ))}
          </div>
        </div>

        {/* Source & Name Form */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <div>
            <label style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', marginBottom: 3, display: 'block' }}>
              Selected Path / Source:
            </label>
            <input
              className="input-field"
              placeholder="e.g. /Users/.../my_project or test_repo"
              value={source}
              onChange={e => setSource(e.target.value)}
              style={{ border: '1px solid var(--border)', borderRadius: 6, padding: '8px 10px', width: '100%', boxSizing: 'border-box' }}
            />
          </div>
          <div>
            <label style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', marginBottom: 3, display: 'block' }}>
              Display Name (optional):
            </label>
            <input
              className="input-field"
              placeholder="e.g. Disease Diet App"
              value={name}
              onChange={e => setName(e.target.value)}
              style={{ border: '1px solid var(--border)', borderRadius: 6, padding: '8px 10px', width: '100%', boxSizing: 'border-box' }}
            />
          </div>
        </div>

        {/* Action Buttons */}
        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 4 }}>
          <button
            type="button"
            onClick={onClose}
            style={{ padding: '7px 14px', border: '1px solid var(--border)', borderRadius: 6, background: 'none', cursor: 'pointer', fontSize: 12 }}
          >
            Cancel
          </button>
          <button
            type="button"
            className="send-btn"
            disabled={!source.trim()}
            style={{ width: 'auto', borderRadius: 6, padding: '7px 16px', fontSize: 12, fontWeight: 600 }}
            onClick={() => { if (source.trim()) { onAdd(source.trim(), name.trim()); onClose() } }}
          >
            Add & Ingest
          </button>
        </div>
      </div>
    </div>
  )
}

// ─── Root App ─────────────────────────────────────────────────────────────

type StreamMsg = Message & { streaming?: boolean; streamContent?: string }

export default function App() {
  const [repos, setRepos] = useState<Repo[]>([])
  const [reposLoading, setReposLoading] = useState(true)
  const [activeRepoId, setActiveRepoId] = useState<string>('')
  const [expandedRepoId, setExpandedRepoId] = useState<string>('')
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)

  // Cache chats per repo_id: Record<repo_id, Chat[]>
  const [repoChatsMap, setRepoChatsMap] = useState<Record<string, Chat[]>>({})
  const [loadingChatsRepoId, setLoadingChatsRepoId] = useState<string | null>(null)
  const [activeChatId, setActiveChatId] = useState<string>('')

  const [messages, setMessages] = useState<StreamMsg[]>([])
  const [messagesLoading, setMessagesLoading] = useState(false)

  const [kgOpen, setKgOpen] = useState(true)
  const [actionStatus, setActionStatus] = useState<string>('')

  const [mode, setMode] = useState<'graph_rag' | 'agent'>('agent')
  const [streaming, setStreaming] = useState(false)
  const [showAddRepo, setShowAddRepo] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  // Load chats for a specific repo lazily
  const loadRepoChats = useCallback(async (repoId: string, autoSelectFirst = false) => {
    if (!repoId) return
    setLoadingChatsRepoId(repoId)
    try {
      const data = await api.chats.list(repoId)
      setRepoChatsMap(prev => ({ ...prev, [repoId]: data }))
      if (autoSelectFirst && data.length > 0) {
        selectChat(data[0].chat_id, repoId)
      } else if (autoSelectFirst && data.length === 0) {
        setActiveChatId('')
        setMessages([])
      }
    } catch (e) {
      console.error('Failed to load chats for repo', repoId, e)
    } finally {
      setLoadingChatsRepoId(null)
    }
  }, [])

  // Load repos on mount
  const loadRepos = useCallback(async () => {
    setReposLoading(true)
    try {
      const data = await api.repos.list()
      setRepos(data)
      if (data.length > 0 && !activeRepoId) {
        const initialRepoId = data[0].repo_id
        setActiveRepoId(initialRepoId)
        setExpandedRepoId(initialRepoId)
        loadRepoChats(initialRepoId, true)
      }
    } catch (e) {
      console.error('Failed to load repos', e)
    } finally {
      setReposLoading(false)
    }
  }, [activeRepoId, loadRepoChats])

  useEffect(() => {
    loadRepos()
  }, [loadRepos])

  // Toggle expanding/collapsing a repo accordion
  function handleToggleRepo(repoId: string) {
    if (expandedRepoId === repoId) {
      // Toggle closed
      setExpandedRepoId('')
    } else {
      // Expand and switch active repo context
      setExpandedRepoId(repoId)
      setActiveRepoId(repoId)
      if (!repoChatsMap[repoId]) {
        loadRepoChats(repoId, true)
      } else {
        const chats = repoChatsMap[repoId] || []
        if (chats.length > 0) {
          selectChat(chats[0].chat_id, repoId)
        } else {
          setActiveChatId('')
          setMessages([])
        }
      }
    }
  }

  // Selecting a chat under an expanded repo
  async function selectChat(chatId: string, repoId: string) {
    setActiveChatId(chatId)
    setActiveRepoId(repoId)
    setExpandedRepoId(repoId)
    setMessagesLoading(true)
    try {
      const data = await api.chats.messages(chatId)
      setMessages(data)
    } catch {
      setMessages([])
    } finally {
      setMessagesLoading(false)
    }
  }

  // Create a new chat inline for a specific repo
  async function handleNewChatForRepo(repoId: string) {
    try {
      const chat = await api.chats.create(repoId)
      setRepoChatsMap(prev => ({
        ...prev,
        [repoId]: [chat as Chat, ...(prev[repoId] || [])],
      }))
      setActiveRepoId(repoId)
      setExpandedRepoId(repoId)
      setActiveChatId(chat.chat_id)
      setMessages([])
    } catch (e) {
      console.error('Create chat failed', e)
    }
  }

  // Delete a chat
  async function handleDeleteChat(chatId: string, repoId: string) {
    try {
      await api.chats.delete(chatId)
      setRepoChatsMap(prev => {
        const currentList = prev[repoId] || []
        const updated = currentList.filter(c => c.chat_id !== chatId)
        return { ...prev, [repoId]: updated }
      })
      if (activeChatId === chatId) {
        const remaining = (repoChatsMap[repoId] || []).filter(c => c.chat_id !== chatId)
        if (remaining.length > 0) {
          selectChat(remaining[0].chat_id, repoId)
        } else {
          setActiveChatId('')
          setMessages([])
        }
      }
    } catch (e) {
      console.error('Failed to delete chat', e)
    }
  }

  async function handleAddRepo(source: string, name: string) {
    setActionStatus('Ingesting repository...')
    try {
      const res = await api.repos.add(source, name || undefined)
      await loadRepos()
      setActiveRepoId(res.repo_id)
      setExpandedRepoId(res.repo_id)
      loadRepoChats(res.repo_id, true)
      setActionStatus('Ingestion complete!')
      setTimeout(() => setActionStatus(''), 3500)
    } catch (e) {
      console.error('Add repo failed', e)
      setActionStatus('Ingestion failed')
    }
  }

  async function handleDeleteRepo(repoId: string, repoName: string) {
    if (!confirm(`Delete repository "${repoName}" and all its chats?`)) return
    try {
      await api.repos.delete(repoId)
      const updated = repos.filter(r => r.repo_id !== repoId)
      setRepos(updated)
      setRepoChatsMap(prev => {
        const next = { ...prev }
        delete next[repoId]
        return next
      })
      if (activeRepoId === repoId) {
        if (updated.length > 0) {
          const nextId = updated[0].repo_id
          setActiveRepoId(nextId)
          setExpandedRepoId(nextId)
          loadRepoChats(nextId, true)
        } else {
          setActiveRepoId('')
          setExpandedRepoId('')
          setActiveChatId('')
          setMessages([])
        }
      }
    } catch (e) {
      console.error('Failed to delete repo', e)
    }
  }

  async function handleResync() {
    if (!activeRepoId) return
    setActionStatus('Resyncing changed files...')
    try {
      await api.repos.resync(activeRepoId)
      setTimeout(() => {
        loadRepos()
        setActionStatus('Resync complete!')
        setTimeout(() => setActionStatus(''), 3000)
      }, 1500)
    } catch {
      setActionStatus('Resync failed')
    }
  }

  async function handleRebuild() {
    if (!activeRepoId) return
    setActionStatus('Rebuilding graph...')
    try {
      await api.repos.rebuild(activeRepoId)
      setTimeout(() => {
        loadRepos()
        setActionStatus('Rebuild complete!')
        setTimeout(() => setActionStatus(''), 3000)
      }, 2500)
    } catch {
      setActionStatus('Rebuild failed')
    }
  }

  async function sendMessage(text: string) {
    if (streaming) return

    let currentChatId = activeChatId
    const currentRepo = activeRepoId || (repos.length > 0 ? repos[0].repo_id : '')

    if (!currentChatId && currentRepo) {
      try {
        const newChat = await api.chats.create(currentRepo)
        setRepoChatsMap(prev => ({
          ...prev,
          [currentRepo]: [newChat as Chat, ...(prev[currentRepo] || [])],
        }))
        setActiveChatId(newChat.chat_id)
        currentChatId = newChat.chat_id
      } catch (e) {
        console.error('Failed to create chat', e)
        return
      }
    }

    if (!currentChatId) return

    const userMsg: StreamMsg = {
      msg_id: `tmp-${Date.now()}`, chat_id: currentChatId, role: 'user',
      content: text, mode, trace: [], is_partial: false, highlighted_nodes: [],
      created_at: new Date().toISOString(),
    }
    const streamId = `streaming-${Date.now()}`
    const streamingMsg: StreamMsg = {
      msg_id: streamId, chat_id: currentChatId, role: 'assistant',
      content: '', mode, trace: [], is_partial: false, highlighted_nodes: [],
      created_at: new Date().toISOString(),
      streaming: true, streamContent: '',
    }

    setMessages(prev => [...prev, userMsg, streamingMsg])
    setStreaming(true)

    if (messages.length === 0) {
      const title = text.split(' ').slice(0, 5).join(' ')
      setRepoChatsMap(prev => {
        const repoChats = prev[currentRepo] || []
        const updated = repoChats.map(c => c.chat_id === currentChatId ? { ...c, title } : c)
        return { ...prev, [currentRepo]: updated }
      })
    }

    let accumulated = ''

    streamMessage(currentChatId, text, mode, {
      onStatus: () => {},
      onToken: (token) => {
        accumulated += token
        setMessages(prev => prev.map(m =>
          m.msg_id === streamId ? { ...m, streamContent: accumulated } : m
        ))
        bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
      },
      onMeta: (meta) => {
        setMessages(prev => prev.map(m =>
          m.msg_id === streamId ? {
            ...m,
            streaming: false,
            content: accumulated,
            trace: meta.trace,
            is_partial: meta.is_partial,
            highlighted_nodes: meta.highlighted_nodes,
          } : m
        ))
      },
      onDone: () => {
        setStreaming(false)
        setMessages(prev => prev.map(m =>
          m.msg_id === streamId ? { ...m, streaming: false, content: accumulated } : m
        ))
      },
      onError: (err) => {
        setStreaming(false)
        setMessages(prev => prev.map(m =>
          m.msg_id === streamId ? { ...m, streaming: false, content: `Error: ${err}` } : m
        ))
      },
    })
  }

  const activeRepo = repos.find(r => r.repo_id === activeRepoId)

  return (
    <div className="app-shell">
      {showAddRepo && <AddRepoModal onClose={() => setShowAddRepo(false)} onAdd={handleAddRepo} />}

      <Sidebar
        repos={repos}
        loading={reposLoading}
        activeRepoId={activeRepoId}
        expandedRepoId={expandedRepoId}
        onToggleRepo={handleToggleRepo}
        onDeleteRepo={handleDeleteRepo}
        repoChatsMap={repoChatsMap}
        loadingChatsRepoId={loadingChatsRepoId}
        activeChatId={activeChatId}
        onSelectChat={selectChat}
        onDeleteChat={handleDeleteChat}
        onNewChatForRepo={handleNewChatForRepo}
        onAddRepo={() => setShowAddRepo(true)}
        collapsed={sidebarCollapsed}
        onToggleCollapse={() => setSidebarCollapsed(c => !c)}
      />

      <div className="main-col">
        {/* Top bar */}
        <div className="topbar">
          <div className="topbar-left">
            <FolderOpen size={15} color="var(--text-muted)" />
            <div className="topbar-repo">
              <span>{activeRepo?.name ?? 'Select a repository'}</span>
              {activeRepo?.status === 'indexing' && <span className="indexing-badge">INDEXING</span>}
            </div>
          </div>
          <button className="view-kg-btn" onClick={() => setKgOpen(o => !o)} title="Toggle Knowledge Graph Panel">
            <Network size={13} /> View KG
          </button>
        </div>

        {/* Chat area */}
        <div className="chat-area">
          <ModeToggle mode={mode} onChange={setMode} />
          
          <div className="messages-list">
            {messagesLoading ? (
              <div style={{ color: 'var(--text-subtle)', fontSize: 12, textAlign: 'center', padding: 24 }}>
                Loading conversation…
              </div>
            ) : messages.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '48px 24px', color: 'var(--text-muted)' }}>
                <h3 style={{ fontSize: 16, fontWeight: 600, color: 'var(--text)', marginBottom: 6 }}>
                  {activeRepo ? `Explore ${activeRepo.name}` : 'Codebase Intelligence'}
                </h3>
                <p style={{ fontSize: 13, maxWidth: 420, margin: '0 auto', lineHeight: 1.5, color: 'var(--text-muted)' }}>
                  Ask questions about call chains, service dependencies, impact analysis, or architectural flows.
                </p>
              </div>
            ) : (
              messages.map(msg =>
                msg.role === 'user' ? (
                  <div key={msg.msg_id} className="msg-user">
                    <div className="msg-user-bubble">{msg.content}</div>
                  </div>
                ) : (
                  <AssistantMessage key={msg.msg_id} msg={msg} />
                )
              )
            )}
            <div ref={bottomRef} />
          </div>

          <InputBar
            disabled={streaming}
            placeholder={activeRepo ? `Ask about ${activeRepo.name} in ${mode === 'agent' ? 'Agent' : 'Graph RAG'} mode…` : 'Add or select a repository to start…'}
            onSend={sendMessage}
          />
        </div>
      </div>

      {kgOpen && (
        <KGPanel
          repoId={activeRepoId}
          repoName={activeRepo?.name}
          repoStatus={activeRepo?.status}
          onClose={() => setKgOpen(false)}
          onResync={handleResync}
          onRebuild={handleRebuild}
          actionStatus={actionStatus}
        />
      )}
    </div>
  )
}
