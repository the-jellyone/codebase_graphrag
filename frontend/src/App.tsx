import React, { useState, useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { 
  Send, Bot, User, Database, Cpu, Search, FolderGit2, 
  ChevronDown, ChevronRight, RefreshCw, Zap, Code2, Layers, CheckCircle2, AlertCircle
} from 'lucide-react';

interface Message {
  role: 'user' | 'assistant';
  content: string;
  metrics?: {
    total_retrieval_ms?: number;
    embed_ms?: number;
    graph_traversal_ms?: number;
  };
  seedNodes?: any[];
  context?: string;
  statusText?: string;
}

export default function App() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [repoPath, setRepoPath] = useState('test_repo');
  const [indexingStatus, setIndexingStatus] = useState<string | null>(null);
  const [systemStatus, setSystemStatus] = useState({ online: false, neo4j: false });
  const [activeTab, setActiveTab] = useState<'chat' | 'subgraph'>('chat');
  const [selectedNode, setSelectedNode] = useState<any | null>(null);

  const chatEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll chat
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Check health status on mount
  useEffect(() => {
    checkHealth();
  }, []);

  const checkHealth = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/health');
      const data = await res.json();
      setSystemStatus({ online: data.status === 'online', neo4j: data.neo4j });
    } catch {
      setSystemStatus({ online: false, neo4j: false });
    }
  };

  const handleIndexRepo = async () => {
    setIndexingStatus('Indexing repo...');
    try {
      const res = await fetch('http://localhost:8000/api/index', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ repo_path: repoPath }),
      });
      const data = await res.json();
      if (res.ok) {
        setIndexingStatus(`✅ Indexed ${data.nodes} nodes, ${data.edges} edges!`);
      } else {
        setIndexingStatus(`❌ Indexing error: ${data.detail}`);
      }
    } catch (err: any) {
      setIndexingStatus(`❌ Failed to connect: ${err.message}`);
    }
  };

  const handleSend = async () => {
    if (!input.trim() || isStreaming) return;

    const userText = input.trim();
    setInput('');

    const newMessages: Message[] = [...messages, { role: 'user', content: userText }];
    setMessages(newMessages);
    setIsStreaming(true);

    // Assistant placeholder
    const assistantIndex = newMessages.length;
    setMessages(prev => [...prev, { role: 'assistant', content: '', statusText: 'Initializing Graph Search...' }]);

    try {
      const response = await fetch('http://localhost:8000/api/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: 'default_session',
          messages: newMessages.map(m => ({ role: m.role, content: m.content })),
          model_name: 'qwen3:4b',
          embed_model: 'qwen3-embedding:0.6b',
        }),
      });


      if (!response.body) throw new Error('No SSE response stream body');

      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let accumulatedContent = '';

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value, { stream: true });
        const lines = chunk.split('\n');

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const dataStr = line.replace('data: ', '').trim();
            if (dataStr === '[DONE]') break;

            try {
              const event = JSON.parse(dataStr);

              if (event.type === 'status') {
                setMessages(prev => {
                  const copy = [...prev];
                  copy[assistantIndex] = { ...copy[assistantIndex], statusText: event.content };
                  return copy;
                });
              } else if (event.type === 'metrics') {
                setMessages(prev => {
                  const copy = [...prev];
                  copy[assistantIndex] = {
                    ...copy[assistantIndex],
                    metrics: event.data,
                    seedNodes: event.seed_nodes,
                    context: event.context,
                    statusText: undefined,
                  };
                  return copy;
                });
              } else if (event.type === 'token') {
                accumulatedContent += event.content;
                setMessages(prev => {
                  const copy = [...prev];
                  copy[assistantIndex] = {
                    ...copy[assistantIndex],
                    content: accumulatedContent,
                    statusText: undefined,
                  };
                  return copy;
                });
              }
            } catch {
              // Ignore non-JSON lines
            }
          }
        }
      }
    } catch (err: any) {
      setMessages(prev => {
        const copy = [...prev];
        copy[assistantIndex] = {
          role: 'assistant',
          content: `❌ **Connection Error:** ${err.message}`,
        };
        return copy;
      });
    } finally {
      setIsStreaming(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div style={{ display: 'flex', height: '100vh', backgroundColor: '#090d16', color: '#f8fafc' }}>
      
      {/* SIDEBAR */}
      <div style={{ width: '320px', backgroundColor: '#0f172a', borderRight: '1px solid #1e293b', display: 'flex', flexDirection: 'column', padding: '1.25rem' }}>
        
        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '1.5rem' }}>
          <div style={{ padding: '0.5rem', backgroundColor: '#0284c7', borderRadius: '0.5rem' }}>
            <Layers size={22} color="#fff" />
          </div>
          <div>
            <h1 style={{ margin: 0, fontSize: '1.1rem', fontWeight: 700 }}>Graph RAG</h1>
            <span style={{ fontSize: '0.75rem', color: '#94a3b8' }}>Code Intelligence Engine</span>
          </div>
        </div>

        {/* System Health Status */}
        <div style={{ padding: '0.75rem', backgroundColor: '#1e293b', borderRadius: '0.5rem', marginBottom: '1.5rem', fontSize: '0.85rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
            <span style={{ color: '#94a3b8', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
              <Database size={14} /> Neo4j Status
            </span>
            <span style={{ color: systemStatus.neo4j ? '#4ade80' : '#f87171', fontWeight: 600 }}>
              {systemStatus.neo4j ? 'Online' : 'Offline'}
            </span>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ color: '#94a3b8', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
              <Cpu size={14} /> Ollama Models
            </span>
            <span style={{ color: '#4ade80', fontWeight: 600 }}>qwen3-4b</span>
          </div>
        </div>

        {/* Repo Indexer */}
        <div style={{ marginBottom: '1.5rem' }}>
          <label style={{ fontSize: '0.8rem', color: '#94a3b8', display: 'block', marginBottom: '0.5rem' }}>
            <FolderGit2 size={14} style={{ display: 'inline', marginRight: '4px' }} /> Target Repository
          </label>
          <input
            type="text"
            value={repoPath}
            onChange={e => setRepoPath(e.target.value)}
            style={{ width: '100%', padding: '0.6rem', backgroundColor: '#1e293b', border: '1px solid #334155', borderRadius: '0.4rem', color: '#fff', fontSize: '0.85rem', marginBottom: '0.6rem' }}
          />
          <button
            onClick={handleIndexRepo}
            style={{ width: '100%', padding: '0.6rem', backgroundColor: '#0284c7', color: '#fff', border: 'none', borderRadius: '0.4rem', fontWeight: 600, fontSize: '0.85rem', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.4rem' }}
          >
            <Zap size={16} /> Index Repository
          </button>

          {indexingStatus && (
            <div style={{ marginTop: '0.5rem', fontSize: '0.75rem', color: '#38bdf8' }}>
              {indexingStatus}
            </div>
          )}
        </div>

        <div style={{ marginTop: 'auto', fontSize: '0.75rem', color: '#64748b', textAlign: 'center' }}>
          Codebase Graph RAG • 100% Offline
        </div>
      </div>

      {/* MAIN CHAT AREA */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', height: '100vh', backgroundColor: '#090d16' }}>
        
        {/* Top Bar */}
        <div style={{ height: '56px', borderBottom: '1px solid #1e293b', display: 'flex', alignItems: 'center', padding: '0 1.5rem', justifyContent: 'space-between', backgroundColor: '#0f172a' }}>
          <div style={{ display: 'flex', gap: '1rem' }}>
            <button
              onClick={() => setActiveTab('chat')}
              style={{ background: 'none', border: 'none', color: activeTab === 'chat' ? '#38bdf8' : '#94a3b8', fontWeight: 600, borderBottom: activeTab === 'chat' ? '2px solid #38bdf8' : 'none', padding: '0.5rem 0', cursor: 'pointer' }}
            >
              💬 Chat & Reasoning
            </button>
          </div>
          <button onClick={() => setMessages([])} style={{ background: 'none', border: 'none', color: '#64748b', fontSize: '0.8rem', cursor: 'pointer' }}>
            Clear Session
          </button>
        </div>

        {/* Messages List */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '1.5rem' }}>
          {messages.length === 0 ? (
            <div style={{ height: '100%', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', color: '#64748b' }}>
              <Code2 size={48} style={{ marginBottom: '1rem', color: '#38bdf8' }} />
              <h2 style={{ margin: 0, color: '#f8fafc', fontSize: '1.2rem' }}>Codebase Intelligence System</h2>
              <p style={{ fontSize: '0.9rem', maxWidth: '400px', textAlign: 'center', marginTop: '0.5rem' }}>
                Ask multi-hop questions about function calls, dependencies, custom exceptions, or config references.
              </p>
            </div>
          ) : (
            messages.map((msg, idx) => (
              <div key={idx} style={{ marginBottom: '1.5rem', display: 'flex', gap: '1rem' }}>
                <div style={{ width: '32px', height: '32px', borderRadius: '50%', backgroundColor: msg.role === 'user' ? '#0284c7' : '#475569', display: 'flex', alignItems: 'center', justifyContent: 'center', shrink: 0 }}>
                  {msg.role === 'user' ? <User size={18} color="#fff" /> : <Bot size={18} color="#fff" />}
                </div>

                <div style={{ flex: 1, backgroundColor: '#0f172a', padding: '1rem', borderRadius: '0.75rem', border: '1px solid #1e293b' }}>
                  
                  {/* Status Indicator */}
                  {msg.statusText && (
                    <div style={{ color: '#38bdf8', fontSize: '0.85rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                      <RefreshCw size={14} className="animate-spin" /> {msg.statusText}
                    </div>
                  )}

                  {/* Content */}
                  {msg.content && (
                    <div className="prose prose-invert" style={{ fontSize: '0.92rem', lineHeight: 1.6 }}>
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>
                        {msg.content}
                      </ReactMarkdown>
                    </div>
                  )}

                  {/* Metrics Badge & Subgraph Context */}
                  {msg.metrics && (
                    <div style={{ marginTop: '1rem', paddingTop: '0.75rem', borderTop: '1px solid #1e293b' }}>
                      <div style={{ fontSize: '0.75rem', color: '#94a3b8', display: 'flex', gap: '1rem', marginBottom: '0.5rem' }}>
                        <span>⚡ Retrieval: <strong>{msg.metrics.total_retrieval_ms}ms</strong></span>
                        <span>🌱 Seed Nodes: <strong>{msg.seedNodes?.length || 0}</strong></span>
                      </div>

                      {msg.context && (
                        <details style={{ fontSize: '0.8rem', color: '#64748b' }}>
                          <summary style={{ cursor: 'pointer', color: '#38bdf8' }}>View Retrieved Subgraph Context</summary>
                          <div style={{ marginTop: '0.5rem', padding: '0.75rem', backgroundColor: '#090d16', borderRadius: '0.4rem', overflowX: 'auto' }}>
                            <ReactMarkdown remarkPlugins={[remarkGfm]}>
                              {msg.context}
                            </ReactMarkdown>
                          </div>
                        </details>
                      )}
                    </div>
                  )}
                </div>
              </div>
            ))
          )}
          <div ref={chatEndRef} />
        </div>

        {/* Input Bar */}
        <div style={{ padding: '1rem 1.5rem', backgroundColor: '#0f172a', borderTop: '1px solid #1e293b' }}>
          <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
            <textarea
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask a question about the codebase (Enter to send)..."
              rows={2}
              style={{ width: '100%', padding: '0.75rem 3rem 0.75rem 1rem', backgroundColor: '#1e293b', border: '1px solid #334155', borderRadius: '0.5rem', color: '#fff', fontSize: '0.9rem', resize: 'none', outline: 'none' }}
            />
            <button
              onClick={handleSend}
              disabled={isStreaming || !input.trim()}
              style={{ position: 'absolute', right: '0.75rem', padding: '0.5rem', backgroundColor: isStreaming || !input.trim() ? '#334155' : '#0284c7', border: 'none', borderRadius: '0.4rem', color: '#fff', cursor: isStreaming || !input.trim() ? 'not-allowed' : 'pointer' }}
            >
              <Send size={18} />
            </button>
          </div>
        </div>

      </div>

    </div>
  );
}
