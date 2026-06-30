/* ═══════════════════════════════════════════════════════════
   EvoGen — REST API client
   Auto-injects Bearer token from localStorage auth store.
   ═══════════════════════════════════════════════════════════ */

const AUTH_TOKEN_KEY = 'evogen-auth-token';
const BASE_URL = '/api/v1';

function getToken(): string {
  try {
    return localStorage.getItem(AUTH_TOKEN_KEY) || '';
  } catch {
    return '';
  }
}

export function setToken(token: string) {
  try {
    localStorage.setItem(AUTH_TOKEN_KEY, token);
  } catch {
    // localStorage may be unavailable
  }
}

export function clearToken() {
  try {
    localStorage.removeItem(AUTH_TOKEN_KEY);
  } catch {
    // localStorage may be unavailable
  }
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const token = getToken();
  const res = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options?.headers,
    },
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const msg = typeof body.detail === 'object'
      ? (body.detail?.error || JSON.stringify(body.detail))
      : (body.detail || body.error);
    throw new Error(msg || `HTTP ${res.status}`);
  }

  const json = await res.json();

  // Support both { ok: true, data: ... } and plain body
  if (json.ok === true && 'data' in json) {
    return json.data as T;
  }
  return json as T;
}

// ── Auth ────────────────────────────────────────────────────────
interface AuthUser {
  id: string;
  username: string;
  email: string;
}

interface AuthResponse {
  token: string;
  user: AuthUser;
}

export const authApi = {
  async login(body: { username: string; password: string }): Promise<AuthResponse> {
    return request<AuthResponse>('/auth/login', {
      method: 'POST',
      body: JSON.stringify(body),
    });
  },

  async register(body: { username: string; email: string; password: string }): Promise<AuthResponse> {
    return request<AuthResponse>('/auth/register', {
      method: 'POST',
      body: JSON.stringify(body),
    });
  },

  async me(): Promise<AuthUser> {
    return request<AuthUser>('/auth/me');
  },
};

// ── Sessions ───────────────────────────────────────────────────
export const sessionsApi = {
  list(params?: { limit?: number; offset?: number; source?: string }) {
    const qs = new URLSearchParams();
    if (params?.limit) qs.set('limit', String(params.limit));
    if (params?.offset) qs.set('offset', String(params.offset));
    if (params?.source) qs.set('source', params.source);
    const query = qs.toString();
    return request<import('@/types').SessionListResponse>(`/sessions${query ? '?' + query : ''}`);
  },

  get(id: string) {
    return request<import('@/types').Session>(`/sessions/${id}`);
  },

  delete(id: string) {
    return request<{ ok: true }>(`/sessions/${id}`, { method: 'DELETE' });
  },

  messages(id: string, params?: { limit?: number; offset?: number }) {
    const qs = new URLSearchParams();
    if (params?.limit) qs.set('limit', String(params.limit));
    if (params?.offset) qs.set('offset', String(params.offset));
    const query = qs.toString();
    return request<import('@/types').MessageListResponse>(`/sessions/${id}/messages${query ? '?' + query : ''}`);
  },

  search(query: string) {
    return request<{ results: import('@/types').SessionSummary[] }>(`/sessions/search`, {
      method: 'POST',
      body: JSON.stringify({ query }),
    });
  },
};

// ── Memory ─────────────────────────────────────────────────────
export const memoryApi = {
  list(params?: {
    layer?: string; type?: string; limit?: number; offset?: number; q?: string;
  }) {
    const qs = new URLSearchParams();
    if (params?.layer && params.layer !== 'all') qs.set('layer', params.layer);
    if (params?.type) qs.set('type', params.type);
    if (params?.limit) qs.set('limit', String(params.limit));
    if (params?.offset) qs.set('offset', String(params.offset));
    if (params?.q) qs.set('q', params.q);
    const query = qs.toString();
    return request<import('@/types').MemoryFactListResponse>(`/memory/facts${query ? '?' + query : ''}`);
  },

  get(id: string) {
    return request<import('@/types').MemoryFact>(`/memory/facts/${id}`);
  },

  create(input: import('@/types').ManualFactInput) {
    return request<import('@/types').MemoryFact>('/memory/facts', {
      method: 'POST',
      body: JSON.stringify(input),
    });
  },

  update(id: string, updates: import('@/types').FactUpdate) {
    return request<import('@/types').MemoryFact>(`/memory/facts/${id}`, {
      method: 'PUT',
      body: JSON.stringify(updates),
    });
  },

  delete(id: string) {
    return request<{ ok: true }>(`/memory/facts/${id}`, { method: 'DELETE' });
  },

  stats() {
    return request<import('@/types').MemoryStats>('/memory/stats');
  },

  reinforce(id: string, amount = 0.1) {
    return request<import('@/types').MemoryFact>(`/memory/facts/${id}/reinforce`, {
      method: 'POST',
      body: JSON.stringify({ amount }),
    });
  },
};

// ── Experience ─────────────────────────────────────────────────
export const experienceApi = {
  listTrajectories(params?: {
    limit?: number; offset?: number; with_feedback_only?: boolean; success?: boolean;
  }) {
    const qs = new URLSearchParams();
    if (params?.limit) qs.set('limit', String(params.limit));
    if (params?.offset) qs.set('offset', String(params.offset));
    if (params?.with_feedback_only) qs.set('with_feedback_only', 'true');
    if (params?.success !== undefined) qs.set('success', String(params.success));
    const query = qs.toString();
    return request<import('@/types').TrajectoryListResponse>(`/experience/trajectories${query ? '?' + query : ''}`);
  },

  getTrajectory(id: string) {
    return request<import('@/types').TrajectorySummary & { turns: import('@/types').TrajectoryTurn[]; outcome: import('@/types').TaskOutcome; feedback: import('@/types').FeedbackRecord[] }>(`/experience/trajectories/${id}`);
  },

  listFeedback(params?: { status?: string; limit?: number; offset?: number }) {
    const qs = new URLSearchParams();
    if (params?.status) qs.set('status', params.status);
    if (params?.limit) qs.set('limit', String(params.limit));
    if (params?.offset) qs.set('offset', String(params.offset));
    const query = qs.toString();
    return request<import('@/types').FeedbackListResponse>(`/experience/feedback${query ? '?' + query : ''}`);
  },

  addFeedback(opt: { trajectory_id: string; rating: 'good' | 'neutral' | 'bad'; note?: string }) {
    return request<import('@/types').FeedbackRecord>('/experience/feedback', {
      method: 'POST',
      body: JSON.stringify(opt),
    });
  },

  updateFeedbackStatus(id: string, status: 'reviewed' | 'applied' | 'dismissed') {
    return request<import('@/types').FeedbackRecord>(`/experience/feedback/${id}/status`, {
      method: 'PUT',
      body: JSON.stringify({ status }),
    });
  },
};

// ── Persona ────────────────────────────────────────────────────
export const personaApi = {
  getAttributes() {
    return request<{ attributes: import('@/types').PersonaAttributes }>('/persona/attributes');
  },

  updateAttributes(attrs: Record<string, unknown>) {
    return request<{ attributes: import('@/types').PersonaAttributes }>('/persona/attributes', {
      method: 'PUT',
      body: JSON.stringify(attrs),
    });
  },

  updateAttribute(key: string, value: unknown) {
    return request<{ key: string; value: unknown }>(`/persona/attributes/${key}`, {
      method: 'PUT',
      body: JSON.stringify({ value }),
    });
  },

  export() {
    return request<string>('/persona/export');
  },

  importPersona(jsonStr: string) {
    return request<{ attributes: import('@/types').PersonaAttributes }>('/persona/import', {
      method: 'POST',
      body: JSON.stringify({ json_str: jsonStr }),
    });
  },

  previewPrompt() {
    return request<{ prompt_injection: string }>('/persona/preview-prompt');
  },
};

// ── Skills ─────────────────────────────────────────────────────
export const skillsApi = {
  list() {
    return request<import('@/types').SkillListResponse>('/skills');
  },
};

// ── Artifacts ──────────────────────────────────────────────────
export const artifactsApi = {
  list(params?: { type?: string; session_id?: string; limit?: number; offset?: number }) {
    const qs = new URLSearchParams();
    if (params?.type) qs.set('type', params.type);
    if (params?.session_id) qs.set('session_id', params.session_id);
    if (params?.limit) qs.set('limit', String(params.limit));
    if (params?.offset) qs.set('offset', String(params.offset));
    const query = qs.toString();
    return request<import('@/types').ArtifactListResponse>(`/artifacts${query ? '?' + query : ''}`);
  },

  get(id: string) {
    return request<import('@/types').Artifact>(`/artifacts/${id}`);
  },

  delete(id: string) {
    return request<{ deleted: string }>(`/artifacts/${id}`, { method: 'DELETE' });
  },
};

// ── Chat (SSE streaming) ──────────────────────────────────────
export function streamChat(
  message: string,
  sessionId: string | undefined,
  onMeta: (meta: { session: string; isNew: boolean }) => void,
  onChunk: (chunk: string) => void,
  onDone: (summary?: string) => void,
  onError: (err: Error) => void,
): AbortController {
  const controller = new AbortController();
  const body: Record<string, unknown> = { message };
  if (sessionId) body.session = sessionId;
  const token = getToken();

  fetch(`${BASE_URL}/agent/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
    signal: controller.signal,
  })
    .then(async (res) => {
      if (!res.ok) {
        const errBody = await res.json().catch(() => ({}));
        const msg = typeof errBody.detail === 'object'
          ? (errBody.detail?.error || JSON.stringify(errBody.detail))
          : (errBody.detail || errBody.error);
        throw new Error(msg || `HTTP ${res.status}`);
      }
      const reader = res.body?.getReader();
      if (!reader) throw new Error('No response body');

      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = line.slice(6).trim();
            if (data === '[DONE]') { onDone(); return; }
            try {
              const parsed = JSON.parse(data);
              if (parsed.session) onMeta({ session: parsed.session, isNew: parsed.is_new || false });
              if (parsed.chunk) onChunk(parsed.chunk);
              if (parsed.status === 'complete') onDone(parsed.summary);
            } catch {
              if (data) onChunk(data);
            }
          }
        }
      }
      onDone();
    })
    .catch((err) => {
      if (err.name !== 'AbortError') onError(err);
    });

  return controller;
}

// ── System ─────────────────────────────────────────────────────
export const systemApi = {
  status() {
    return request<import('@/types').SystemStatusResponse>('/system/status');
  },

  platforms() {
    return request<import('@/types').PlatformListResponse>('/config/platforms');
  },

  connectPlatform(name: string, config: Record<string, string>) {
    return request<{ ok: true; platform_status: import('@/types').PlatformInfo }>(`/config/platforms/${name}/connect`, {
      method: 'POST',
      body: JSON.stringify(config),
    });
  },

  logs(params?: { limit?: number; level?: string }) {
    const qs = new URLSearchParams();
    if (params?.limit) qs.set('limit', String(params.limit));
    if (params?.level) qs.set('level', params.level);
    return request<import('@/types').LogListResponse>(`/system/logs?${qs}`);
  },

  getConfig() {
    return request<Record<string, unknown>>('/system/config');
  },

  updateConfig(config: Record<string, unknown>) {
    return request<Record<string, unknown>>('/system/config', {
      method: 'PUT',
      body: JSON.stringify(config),
    });
  },

  capacity() {
    return request<import('@/types').MemoryCapacityResponse>('/memory/capacity');
  },

  // ── 智能更新 ──
  checkUpdate() {
    return request<{ ok: boolean; data: { updated: boolean; message: string; before: string; after: string; changelog: string[] }; error?: string }>('/tools/update', {
      method: 'POST',
    });
  },

  // ── 自定义模型 ──
  async getCustomModels() {
    return request<Record<string, { label: string; base_url: string; description: string; api_key_masked?: string }>>('/system/models/custom');
  },

  async addCustomModel(body: { id: string; label: string; api_key: string; base_url: string; description?: string }) {
    return request<{ id: string; label: string; api_key: string; base_url: string; description: string }>('/system/models/custom', {
      method: 'POST',
      body: JSON.stringify(body),
    });
  },

  async deleteCustomModel(modelId: string) {
    return request<{ deleted: string }>(`/system/models/custom/${modelId}`, {
      method: 'DELETE',
    });
  },
};
