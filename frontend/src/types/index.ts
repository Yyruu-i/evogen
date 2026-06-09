/* ═══════════════════════════════════════════════════════════
   EvoGen — TypeScript types (mirrors backend Pydantic models)
   ═══════════════════════════════════════════════════════════ */

// ── Session ─────────────────────────────────────────────────────
export interface Session {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  source: string;
  profile?: string;
  metadata?: Record<string, unknown>;
  message_count: number;
  token_estimate: number;
  active_memory_snapshot_id?: string;
  active_persona_id?: string;
}

export interface SessionSummary {
  id: string;
  title: string;
  source: string;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export interface SessionListResponse {
  sessions: SessionSummary[];
  total: number;
}

export interface Message {
  id: number;
  session_id: string;
  role: 'user' | 'assistant' | 'tool' | 'system';
  content: string;
  tool_calls_json?: string;
  tool_call_id?: string;
  timestamp: string;
  token_count?: number;
}

export interface MessageListResponse {
  messages: Message[];
}

// ── Memory ──────────────────────────────────────────────────────
export type MemoryFactType = 'preference' | 'fact' | 'procedure' | 'relationship';
export type MemoryLayer = 'transient' | 'working' | 'core' | 'archive';
export type PrivacyLevel = 'public' | 'private' | 'sensitive';

export interface MemoryFact {
  id: string;
  type: MemoryFactType;
  content: string;
  chroma_id: string;
  importance: number;
  weight: number;
  layer: MemoryLayer;
  source_session_id?: string;
  source_interaction_id?: string;
  privacy_level: PrivacyLevel;
  tags?: string[];
  created_at: string;
  updated_at: string;
  last_accessed_at: string;
}

export interface MemoryFactListResponse {
  facts: MemoryFact[];
  total: number;
}

export interface ManualFactInput {
  content: string;
  type: MemoryFactType;
  importance?: number;
  layer?: MemoryLayer;
  tags?: string[];
}

export interface FactUpdate {
  content?: string;
  type?: MemoryFactType;
  importance?: number;
  layer?: MemoryLayer;
  privacy_level?: PrivacyLevel;
  tags?: string[];
}

export interface MemoryStats {
  total_facts: number;
  by_layer: Record<string, number>;
  by_type: Record<string, number>;
  last_extraction_at?: string;
  total_vector_bytes: number;
}

// ── Experience ──────────────────────────────────────────────────
export interface TrajectoryTurn {
  turn_index: number;
  tool_calls?: ToolCallRecord[];
  llm_response_chunk?: string;
  token_usage: number;
}

export interface ToolCallRecord {
  tool_name: string;
  arguments: Record<string, unknown>;
  result_summary: string;
  success: boolean;
  execution_time_ms: number;
}

export interface TaskOutcome {
  success: boolean;
  total_tokens: number;
  wall_time_ms: number;
  user_cancelled: boolean;
}

export interface TrajectorySummary {
  id: string;
  session_id: string;
  session_title?: string;
  created_at: string;
  turn_count: number;
  success: boolean;
  feedback_count: number;
  last_feedback_at?: string;
}

export interface TrajectoryListResponse {
  trajectories: TrajectorySummary[];
  total: number;
}

export interface FeedbackRecord {
  id: string;
  trajectory_id: string;
  rating: 'good' | 'neutral' | 'bad';
  note?: string;
  status: 'pending' | 'reviewed' | 'applied' | 'dismissed';
  created_at: string;
  reviewed_at?: string;
}

export interface FeedbackListResponse {
  feedback: FeedbackRecord[];
  total: number;
}

export interface SceneHint {
  trajectory_id: string;
  summary: string;
  relevant_feedback?: string;
  similarity_score: number;
}

// ── Persona ─────────────────────────────────────────────────────
export interface PersonaAttributes {
  display_name?: string;
  preferred_language: string;
  timezone?: string;
  conciseness: number;
  formality: number;
  warmth: number;
  directness: number;
  auto_approve_tools: boolean;
  show_thinking: boolean;
  response_language: string;
  learned_preferences: Record<string, unknown>;
  discovery_questions_asked: number;
}

// ── Skill ───────────────────────────────────────────────────────
export interface Skill {
  id: string;
  name: string;
  description: string;
  tags: string[];
  category: string;
  source: 'hub' | 'local' | 'auto-generated';
  scope: 'builtin' | 'user';
  version: number;
  use_count: number;
  success_rate: number;
  created_at: string;
}

export interface SkillListResponse {
  skills: Skill[];
  total: number;
}

// ── Artifact ────────────────────────────────────────────────────
export interface Artifact {
  id: string;
  type: 'code' | 'image' | 'doc';
  title: string;
  content: string;
  language?: string;
  session_id?: string;
  created_at: string;
}

export interface ArtifactListResponse {
  artifacts: Artifact[];
  total: number;
}

// ── Platform ────────────────────────────────────────────────────
export interface PlatformInfo {
  name: string;
  status: 'connected' | 'disconnected' | 'connecting';
  connected_at?: string;
}

export interface PlatformListResponse {
  platforms: PlatformInfo[];
}

// ── Health / System ─────────────────────────────────────────────
export interface SystemStatusResponse {
  agent: {
    status: string;
    version: string;
    uptime_seconds: number;
    uptime_human: string;
    python_version: string;
    started_at: string;
  };
  gateway: {
    running: boolean;
    profiles: Array<{ profile: string; pid: number | null }>;
    error: string | null;
  };
  database: {
    connected: boolean;
    memory_facts: number;
    error?: string;
  };
  memory_capacity: {
    total_facts: number;
    archive_count: number;
    capacity_limit: number;
    usage_percent: number;
    storage_estimate_bytes: number;
    by_layer: Record<string, number>;
    error?: string;
  };
  server_time: string;
}

export interface LogEntry {
  timestamp: string;
  level: string;
  message: string;
}

export interface LogListResponse {
  total: number;
  entries: LogEntry[];
  log_file: string;
}

export interface MemoryCapacityResponse {
  total_facts: number;
  storage_estimate_bytes: number;
  capacity_limit: number;
  usage_percent: number;
  total_vector_bytes: number;
  by_layer: Record<string, number>;
  by_type: Record<string, number>;
}

// ── API wrappers ───────────────────────────────────────────────
export interface ApiResponse<T> {
  ok: true;
  data: T;
}

export interface ApiError {
  ok: false;
  error: string;
}

// ── Chat WS ─────────────────────────────────────────────────────
export interface WsConnectRequest {
  type: 'req';
  method: 'connect';
  params: {
    deviceId: string;
    deviceName: string;
    platform: string;
    auth: { token: string };
    role: 'client';
  };
}

export interface WsAgentRequest {
  type: 'req';
  method: 'agent';
  params: {
    message: string;
    session?: string;
  };
}

export interface WsAgentEvent {
  type: 'event';
  event: 'agent';
  payload: {
    runId: string;
    chunk?: string;
    status?: string;
    summary?: string;
  };
}

export interface ChatMsg {
  id: string;
  role: 'user' | 'assistant' | 'tool' | 'system';
  content: string;
  timestamp: string;
}
