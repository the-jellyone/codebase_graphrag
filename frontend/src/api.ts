/**
 * CodeGraph typed API client.
 *
 * All backend calls are centralized here. Field names match the backend JSON exactly.
 * No dummy data — real endpoints only.
 */

const BASE = "http://localhost:8000";

// ─── Types ────────────────────────────────────────────────────────────────

export interface Repo {
  repo_id: string;
  name: string;
  source: string;
  status: "idle" | "indexing" | "ready" | "error";
  dot_color: "green" | "amber" | "grey";
  last_synced: string | null;
  created_at: string;
}

export interface IndexStage {
  name: string;
  status: "pending" | "in_progress" | "done" | "error";
  percent: number;
  detail: string;
}

export interface IndexStatus {
  status: "idle" | "indexing" | "ready" | "error";
  stages: IndexStage[];
  error?: string | null;
}

export interface Chat {
  chat_id: string;
  repo_id: string;
  repo_name?: string;
  title: string;
  created_at: string;
}

export interface TraceEntry {
  tool: string;
  args: Record<string, unknown>;
}

export interface Message {
  msg_id: string;
  chat_id: string;
  role: "user" | "assistant";
  content: string;
  mode: "graph_rag" | "agent";
  trace: TraceEntry[];
  is_partial: boolean;
  highlighted_nodes: string[];
  created_at: string;
}

export interface GraphNode {
  id: string;
  name: string;
  label: string;
  degree: number;
  highlighted: boolean;
}

export interface GraphEdge {
  source: string;
  target: string;
  type: string;
}

export interface GraphPreview {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface RepoStats {
  repo_id: string;
  name: string;
  node_count: number;
  edge_count: number;
  last_synced: string | null;
  status: string;
}

// ─── SSE Stream Events ────────────────────────────────────────────────────

export type SseEventType = "status" | "token" | "meta" | "done" | "error";

export interface SseEvent {
  type: SseEventType;
  content?: string;
  trace?: TraceEntry[];
  is_partial?: boolean;
  highlighted_nodes?: string[];
  metrics?: Record<string, number>;
}

// ─── API Helpers ──────────────────────────────────────────────────────────

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(`API ${res.status}: ${err}`);
  }
  return res.json() as Promise<T>;
}

// ─── Repo API ─────────────────────────────────────────────────────────────

export const api = {
  repos: {
    list: (): Promise<Repo[]> => apiFetch("/repos"),

    add: (source: string, name?: string): Promise<{ repo_id: string; name: string; status: string }> =>
      apiFetch("/repos", {
        method: "POST",
        body: JSON.stringify({ source, name }),
      }),

    delete: (repo_id: string): Promise<{ status: string; repo_id: string }> =>
      apiFetch(`/repos/${repo_id}`, { method: "DELETE" }),

    indexStatus: (repo_id: string): Promise<IndexStatus> =>
      apiFetch(`/repos/${repo_id}/index-status`),

    resync: (repo_id: string): Promise<{ status: string }> =>
      apiFetch(`/repos/${repo_id}/resync`, { method: "POST", body: "{}" }),

    rebuild: (repo_id: string): Promise<{ status: string }> =>
      apiFetch(`/repos/${repo_id}/rebuild`, { method: "POST", body: "{}" }),

    stats: (repo_id: string): Promise<RepoStats> =>
      apiFetch(`/repos/${repo_id}/stats`),

    graphPreview: (repo_id: string, highlighted: string[] = []): Promise<GraphPreview> =>
      apiFetch(`/repos/${repo_id}/graph-preview?highlighted=${highlighted.join(",")}`),

    kgQueryUrl: (repo_id: string): Promise<{ url: string }> =>
      apiFetch(`/repos/${repo_id}/kg-query-url`),
  },

  chats: {
    create: (repo_id: string): Promise<{ chat_id: string; repo_id: string; repo_name?: string; title: string }> =>
      apiFetch("/chats", { method: "POST", body: JSON.stringify({ repo_id }) }),

    list: (repo_id?: string): Promise<Chat[]> =>
      apiFetch(repo_id ? `/chats?repo_id=${encodeURIComponent(repo_id)}` : "/chats"),

    update: (chat_id: string, data: { repo_id?: string; title?: string }): Promise<{ status: string }> =>
      apiFetch(`/chats/${chat_id}`, { method: "PATCH", body: JSON.stringify(data) }),

    delete: (chat_id: string): Promise<{ status: string }> =>
      apiFetch(`/chats/${chat_id}`, { method: "DELETE" }),

    messages: (chat_id: string): Promise<Message[]> =>
      apiFetch(`/chats/${chat_id}/messages`),
  },
};

// ─── SSE Message Stream ───────────────────────────────────────────────────

export interface StreamCallbacks {
  onStatus?: (msg: string) => void;
  onToken: (token: string) => void;
  onMeta?: (meta: { trace: TraceEntry[]; is_partial: boolean; highlighted_nodes: string[]; metrics?: Record<string, number> }) => void;
  onDone?: () => void;
  onError?: (err: string) => void;
}

export function streamMessage(
  chat_id: string,
  text: string,
  mode: "graph_rag" | "agent",
  callbacks: StreamCallbacks,
): () => void {
  const controller = new AbortController();

  (async () => {
    try {
      const res = await fetch(`${BASE}/chats/${chat_id}/messages`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, mode }),
        signal: controller.signal,
      });

      if (!res.ok || !res.body) {
        const err = await res.text();
        callbacks.onError?.(`Stream failed: ${err}`);
        return;
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        // Parse SSE lines
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const raw = line.slice(6).trim();
          if (!raw) continue;

          try {
            const evt: SseEvent = JSON.parse(raw);
            switch (evt.type) {
              case "status":
                callbacks.onStatus?.(evt.content ?? "");
                break;
              case "token":
                callbacks.onToken(evt.content ?? "");
                break;
              case "meta":
                callbacks.onMeta?.({
                  trace: evt.trace ?? [],
                  is_partial: evt.is_partial ?? false,
                  highlighted_nodes: evt.highlighted_nodes ?? [],
                  metrics: evt.metrics,
                });
                break;
              case "done":
                callbacks.onDone?.();
                return;
              case "error":
                callbacks.onError?.(evt.content ?? "Unknown error");
                return;
            }
          } catch {
            // Ignore malformed SSE lines
          }
        }
      }
      callbacks.onDone?.();
    } catch (err: unknown) {
      if ((err as Error).name !== "AbortError") {
        callbacks.onError?.((err as Error).message);
      }
    }
  })();

  // Return cancel function
  return () => controller.abort();
}
