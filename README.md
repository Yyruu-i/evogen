# EvoGen — 个人 AI 智能体，越用越懂你

<p align="center">
  <em>三层记忆 · 经验学习 · 统一人格 · 持续进化</em>
</p>

---

## 定位

EvoGen 是一个**自我进化的个人 AI 智能体**（Fork Hermes Agent），核心理念是"越用越懂你"。它通过三层记忆系统沉淀认知、从交互经验中学习反馈、并基于人格引擎形成一致的交互风格——每次对话都在让你更接近一个真正懂你的 AI。

## 核心能力

### 🧠 三层记忆系统

| 层级 | 说明 | 生命周期 |
|------|------|----------|
| **transient** | 会话临时记忆 | 单次会话 |
| **working** | 近期工作记忆 | 数天到数周 |
| **core** | 核心长期记忆 | 持续积累 |
| **archive** | 归档记忆 | 永久保存 |

- 自动提取：从对话中智能提取偏好、事实、流程、关系
- 语义搜索：基于 BGE-M3 嵌入的向量检索
- 记忆强化：根据使用频率调整权重
- 衰减淘汰：不活跃的记忆自动降级

### 📊 经验记录

- **会话轨迹**：完整记录每次交互的 turns、工具调用、token 消耗
- **用户反馈**：good / neutral / bad 评分 + 备注
- **反馈状态流转**：pending → reviewed → applied / dismissed
- **经验回溯**：按成功/失败筛选，追踪改进历程

### 🎭 统一人格

- **12 项预设属性**：名称、语言、简洁度、正式度、温暖度、直接度等
- **动态调整**：支持运行时修改任意属性
- **System Prompt 注入**：将人格属性转化为 LLM 系统提示词
- **导入/导出**：支持人格配置备份与迁移

## 技术栈

| 层级 | 技术 |
|------|------|
| **后端框架** | Python 3.12+ / FastAPI / Uvicorn |
| **向量存储** | ChromaDB |
| **嵌入模型** | BAAI/bge-m3（1024 维） |
| **关系数据库** | SQLite（WAL 模式） |
| **LLM** | DeepSeek V4（兼容 OpenAI API） |
| **前端** | React 18 / TypeScript / Tailwind CSS 4 / Vite |
| **基座框架** | Hermes Agent（Gateway + WebSocket 协议） |

## 项目结构

```
next-gen-agent/
├── backend/
│   ├── main.py                  # FastAPI 入口 + 生命周期管理
│   ├── config.py                # 全局配置（支持环境变量覆盖）
│   ├── api/
│   │   ├── __init__.py          # API 路由注册（/api/v1）
│   │   ├── memory_routes.py     # 记忆 REST API（7 个端点）
│   │   ├── experience_routes.py # 经验 REST API（5 个端点）
│   │   └── persona_routes.py    # 人格 REST API（6 个端点）
│   ├── memory/
│   │   ├── engine.py            # 记忆引擎（CRUD + 搜索 + 统计）
│   │   ├── embedding.py         # BGE-M3 嵌入生成
│   │   ├── extractor.py         # 对话事实自动提取器
│   │   ├── anchor_extractor.py  # 锚点提取器（结构化信息）
│   │   └── events.py            # 记忆事件定义
│   ├── experience/
│   │   ├── recorder.py          # 经验记录器（轨迹 + 反馈）
│   │   └── __init__.py
│   ├── persona/
│   │   ├── engine.py            # 人格引擎（属性管理 + Prompt 生成）
│   │   ├── dao.py               # 人格数据访问层
│   │   └── __init__.py
│   ├── compaction/
│   │   ├── integration.py       # 记忆压缩集成
│   │   └── __init__.py
│   ├── agent/
│   │   ├── evogen_loop.py       # EvoGen 主循环（进化型 Agent）
│   │   ├── context_builder.py   # 上下文构建器
│   │   └── __init__.py
│   └── db/
│       ├── connection.py        # SQLite 连接管理（线程安全单例）
│       ├── migrations.py        # 幂等迁移管理
│       ├── vector_store.py      # ChromaDB 向量存储封装
│       └── schema.sql           # 数据库 DDL（5 张 MVP 表）
├── frontend/                    # React + TypeScript + Tailwind
│   ├── src/
│   │   ├── pages/               # chat, memory, experience, persona, settings 等
│   │   ├── components/          # 共享组件（layout, shared）
│   │   └── main.tsx             # 前端入口
│   ├── vite.config.ts           # Vite 配置（含 API 代理）
│   └── package.json
├── tests/
│   ├── unit/                    # 单元测试
│   │   ├── test_memory_engine.py
│   │   ├── test_memory_api.py
│   │   ├── test_experience_recorder.py
│   │   ├── test_experience_api.py
│   │   ├── test_persona_engine.py
│   │   ├── test_persona_api.py
│   │   └── ...
│   └── conftest.py              # Pytest 配置
├── docs/
│   ├── quickstart.md            # 快速开始指南
│   ├── api-reference.md         # REST API 完整参考
│   └── ...
├── data/                        # 运行时数据（数据库 + Chroma）
│   └── chroma/
├── requirements.txt             # Python 依赖
└── pytest.ini                   # Pytest 配置
```

## 快速开始

> 30 分钟内跑通 EvoGen。

详见 **[快速开始指南 →](./docs/quickstart.md)**

```bash
# 1. 安装依赖
cd /root/next-gen-agent
pip install -r requirements.txt

# 2. 配置 API Key
export DEEPSEEK_API_KEY="sk-your-key"

# 3. 启动后端
uvicorn backend.main:app --host 0.0.0.0 --port 8100 --reload

# 4. 启动前端（开发模式）
cd frontend && npm install && npm run dev

# 5. 打开浏览器访问 http://localhost:5174
```

## API 文档

> 18 个 REST API 端点的完整参考。

详见 **[API 参考文档 →](./docs/api-reference.md)**

**快捷入口：**

| 模块 | 端点 | 文档 |
|------|------|------|
| Memory | `GET/POST /api/v1/memory/facts` | [Memory API](#) |
| Memory | `GET/PUT/DELETE /api/v1/memory/facts/{id}` | [Memory API](#) |
| Memory | `GET /api/v1/memory/stats` | [Memory API](#) |
| Memory | `POST /api/v1/memory/facts/{id}/reinforce` | [Memory API](#) |
| Experience | `GET /api/v1/experience/trajectories` | [Experience API](#) |
| Experience | `GET /api/v1/experience/trajectories/{id}` | [Experience API](#) |
| Experience | `GET/POST /api/v1/experience/feedback` | [Experience API](#) |
| Experience | `PUT /api/v1/experience/feedback/{id}/status` | [Experience API](#) |
| Persona | `GET/PUT /api/v1/persona/attributes` | [Persona API](#) |
| Persona | `PUT /api/v1/persona/attributes/{key}` | [Persona API](#) |
| Persona | `GET /api/v1/persona/export` | [Persona API](#) |
| Persona | `POST /api/v1/persona/import` | [Persona API](#) |
| Persona | `GET /api/v1/persona/preview-prompt` | [Persona API](#) |

健康检查：`GET /health` → `{"status": "ok", "version": "0.1.0"}`

## 运行测试

```bash
cd /root/next-gen-agent

# 运行全部单元测试
pytest tests/unit/ -v

# 运行指定模块测试
pytest tests/unit/test_memory_engine.py -v
pytest tests/unit/test_persona_engine.py -v
pytest tests/unit/test_experience_recorder.py -v

# 运行 API 测试
pytest tests/unit/test_memory_api.py -v
pytest tests/unit/test_persona_api.py -v
pytest tests/unit/test_experience_api.py -v
```

## 配置参考

所有配置项通过 `backend/config.py` 管理，支持环境变量覆盖：

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `DEEPSEEK_API_KEY` | (空) | DeepSeek API Key |
| `LLM_MODEL` | `deepseek-v4-pro` | LLM 模型名称 |
| `LLM_BASE_URL` | `https://api.deepseek.com` | LLM API 地址 |
| `EMBEDDING_MODEL` | `BAAI/bge-m3` | 嵌入模型 |
| `EMBEDDING_DEVICE` | `cpu` | 嵌入推理设备（cpu/cuda） |

---

<p align="center">
  <sub>Built with ❤️ by EvoGen Team · v0.1.0 MVP</sub>
</p>
