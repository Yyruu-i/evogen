/* ═══════════════════════════════════════════════════════════
   EvoGen — Utility helpers
   ═══════════════════════════════════════════════════════════ */

export function cn(...classes: (string | boolean | undefined | null)[]): string {
  return classes.filter(Boolean).join(' ');
}

export function formatDate(iso: string): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  const now = new Date();
  const diff = now.getTime() - d.getTime();

  // < 1 minute
  if (diff < 60_000) return '刚刚';
  // < 1 hour
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)} 分钟前`;
  // < 24 hours
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)} 小时前`;
  // < 7 days
  if (diff < 604_800_000) return `${Math.floor(diff / 86_400_000)} 天前`;

  return d.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' });
}

export function formatTime(iso: string): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
}

export function formatUptime(seconds: number): string {
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (d > 0) return `${d}d ${h}h`;
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

export function truncate(text: string, len: number): string {
  if (text.length <= len) return text;
  return text.slice(0, len) + '…';
}

export function generateId(): string {
  return crypto.randomUUID().slice(0, 12);
}

// Memory layer / type labels (Chinese)
export const LAYER_LABELS: Record<string, string> = {
  transient: '瞬态',
  working: '工作',
  core: '核心',
  archive: '归档',
};

export const FACT_TYPE_LABELS: Record<string, string> = {
  preference: '偏好',
  fact: '事实',
  procedure: '流程',
  relationship: '关系',
};

export const FEEDBACK_RATING_LABELS: Record<string, string> = {
  good: '👍 做得好',
  neutral: '➖ 一般',
  bad: '👎 有问题',
};

export const FEEDBACK_STATUS_LABELS: Record<string, string> = {
  pending: '待处理',
  reviewed: '已查看',
  applied: '已应用',
  dismissed: '已忽略',
};

// Skill category / name / tag → Chinese mapping
const SKILL_CATEGORY_CN: Record<string, string> = {
  apple: 'Apple',
  autonomous: '自主代理',
  'autonomous-ai-agents': '自主 AI 代理',
  creative: '创意设计',
  'data-science': '数据科学',
  devops: '开发运维',
  dogfood: '质量测试',
  email: '邮件管理',
  gaming: '游戏娱乐',
  github: '代码托管',
  mcp: 'MCP 协议',
  media: '媒体处理',
  mlops: '机器学习',
  'mlops/evaluation': '模型评估',
  'mlops/inference': '模型推理',
  'mlops/models': '模型架构',
  'mlops/research': 'ML 研究',
  'note-taking': '笔记管理',
  productivity: '效率工具',
  'red-teaming': '红队测试',
  research: '学术研究',
  'smart-home': '智能家居',
  'social-media': '社交媒体',
  'software-development': '软件开发',
  yuanbao: '元宝集成',
};

const SKILL_NAME_CN: Record<string, string> = {
  'ascii-art': 'ASCII 艺术',
  'ascii-video': 'ASCII 视频',
  'architecture-diagram': '架构图表',
  'apple-notes': 'Apple 备忘录',
  'apple-reminders': 'Apple 提醒事项',
  'baoyu-article-illustrator': '文章插图生成',
  'baoyu-comic': '知识漫画',
  'baoyu-infographic': '信息图表',
  'claude-code': 'Claude Code',
  'claude-design': 'Claude 设计',
  'codex': 'Codex CLI',
  comfyui: 'ComfyUI 绘图',
  'design-md': 'Design.md 规范',
  dogfood: '应用测试',
  'evogen-frontend': 'EvoGen 前端',
  excalidraw: '手绘风格图表',
  findmy: 'Find My',
  'frontend-api-integration': '前端 API 集成',
  humanizer: '文本人性化',
  'hermes-agent': 'Hermes Agent',
  ideation: '创意生成',
  imessage: 'iMessage',
  'kanban-codex-lane': '看板 Codex 通道',
  'manim-video': 'Manim 数学动画',
  'macos-computer-use': 'macOS 桌面操作',
  opencode: 'OpenCode',
  'p5js': 'p5.js 创意编程',
  'prd-review': 'PRD 评审',
  'pixel-art': '像素艺术',
  'popular-web-designs': '流行 Web 设计',
  pretext: 'Pretext 演示',
  'research-paper-writing': '论文写作',
  sketch: '快速原型',
  'songwriting-and-ai-music': 'AI 音乐创作',
  'touchdesigner-mcp': 'TouchDesigner 集成',
  'jupyter-live-kernel': 'Jupyter 实时内核',
  'kanban-orchestrator': '看板编排器',
  'kanban-worker': '看板执行器',
  'webhook-subscriptions': 'Webhook 订阅',
  himalaya: 'Himalaya 邮件',
  'minecraft-modpack-server': 'Minecraft 服务器',
  'pokemon-player': '宝可梦模拟器',
  'github-auth': 'GitHub 认证',
  'github-code-review': '代码审查',
  'github-issues': 'Issue 管理',
  'github-pr-workflow': 'PR 工作流',
  'github-repo-management': '仓库管理',
  'codebase-inspection': '代码库分析',
  'native-mcp': 'MCP 原生客户端',
  'gif-search': 'GIF 搜索',
  heartmula: 'HeartMuLa 音乐',
  songsee: '音频分析',
  spotify: 'Spotify 控制',
  'youtube-content': 'YouTube 内容',
  'huggingface-hub': 'HF Hub 管理',
  'evaluating-llms-harness': 'LLM 评测框架',
  'weights-and-biases': 'W&B 实验追踪',
  'llama-cpp': 'llama.cpp 推理',
  obliteratus: 'Obliteratus 消融',
  'serving-llms-vllm': 'vLLM 推理服务',
  'audiocraft-audio-generation': 'AudioCraft 音频生成',
  'segment-anything-model': 'SAM 图像分割',
  dspy: 'DSPy 编程框架',
  obsidian: 'Obsidian 笔记',
  airtable: 'Airtable 管理',
  'google-workspace': 'Google 套件',
  linear: 'Linear 项目管理',
  maps: '地图服务',
  'nano-pdf': 'PDF 编辑',
  notion: 'Notion 管理',
  'ocr-and-documents': 'OCR 文档提取',
  powerpoint: 'PPT 制作',
  'teams-meeting-pipeline': 'Teams 会议',
  godmode: 'GODMODE 越狱',
  arxiv: 'arXiv 论文搜索',
  blogwatcher: '博客监控',
  'llm-wiki': 'LLM Wiki 知识库',
  polymarket: 'PolyMarket 预测',
  openhue: 'Philips Hue 灯光',
  xurl: 'X/Twitter 集成',
  'debugging-hermes-tui-commands': 'TUI 命令调试',
  'frontend-spec-verification': '前端规范验证',
  'hermes-agent-skill-authoring': '技能创作工具',
  'node-inspect-debugger': 'Node 调试器',
  plan: '计划模式',
  'python-debugpy': 'Python 调试器',
  'requesting-code-review': '代码审查请求',
  spike: '技术探索',
  'subagent-driven-development': '子代理开发',
  'systematic-debugging': '系统化调试',
  'test-driven-development': 'TDD 测试驱动',
  'writing-plans': '计划编写',
  yuanbao: '元宝助手',
};

const SKILL_TAG_CN: Record<string, string> = {
  cli: 'CLI',
  python: 'Python',
  typescript: 'TypeScript',
  javascript: 'JavaScript',
  rust: 'Rust',
  api: 'API',
  sdk: 'SDK',
  'machine-learning': '机器学习',
  'deep-learning': '深度学习',
  visualization: '可视化',
  audio: '音频',
  video: '视频',
  image: '图像',
  text: '文本',
  automation: '自动化',
  security: '安全',
  testing: '测试',
  deployment: '部署',
  monitoring: '监控',
  database: '数据库',
  messaging: '消息',
  networking: '网络',
  container: '容器',
  cloud: '云服务',
  local: '本地',
  remote: '远程',
  streaming: '流式',
  batch: '批处理',
  interactive: '交互式',
  headless: '无头',
  gui: 'GUI',
};

export function skillLabel(value: string, map: Record<string, string>): string {
  return map[value] || value;
}

export { SKILL_CATEGORY_CN, SKILL_NAME_CN, SKILL_TAG_CN };
