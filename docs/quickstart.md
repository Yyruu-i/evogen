# EvoGen 快速开始指南

> 目标：从零开始，30 分钟内让 EvoGen 跑起来。

---

## 1. 环境要求

| 组件 | 最低版本 | 说明 |
|------|----------|------|
| Python | 3.12+ | 推荐 3.12 |
| pip | 最新版 | `pip install --upgrade pip` |
| Node.js | 18+ (仅前端开发) | 如果只用 API 可跳过 |
| npm | 9+ (仅前端开发) | 随 Node.js 附带 |

## 2. 安装步骤

```bash
# 进入项目目录
cd /root/next-gen-agent

# 安装后端依赖
pip install -r requirements.txt

# （可选）安装 agent-framework（用于 Gateway）
pip install -e /root/agent-framework
```

**依赖说明：**

| 依赖 | 用途 |
|------|------|
| `fastapi` + `uvicorn` | Web 框架与 ASGI 服务器 |
| `chromadb` | 向量存储（语义搜索） |
| `sentence-transformers` + `torch` | BGE-M3 嵌入模型 |
| `openai` | LLM 客户端（兼容 DeepSeek API） |
| `python-dotenv` | 环境变量管理 |
| `pydantic` | 数据校验 |

## 3. 配置 LLM API Key

EvoGen 使用 DeepSeek 作为默认 LLM 提供商。

```bash
# 设置环境变量
export DEEPSEEK_API_KEY="sk-your-deepseek-api-key"

# 可选：自定义模型或 Base URL
export LLM_MODEL="deepseek-v4-pro"          # 默认值
export LLM_BASE_URL="https://api.deepseek.com"  # 默认值
```

> 💡 **获取 API Key**：前往 [DeepSeek 开放平台](https://platform.deepseek.com/) 注册并创建 API Key。

> 💡 **持久化配置**：建议将上述 `export` 写入 `~/.bashrc` 或 `~/.zshrc`。

## 4. 初始化数据库

数据库初始化是**自动**的——启动后端服务时会自动运行迁移脚本，创建所需的所有表和默认数据。

如果想手动验证数据库状态：

```bash
# 启动后端会自动初始化
# 数据库文件位置：~/.evogen/data/evogen.db
# 向量存储位置：~/.evogen/data/chroma/

# 手动检查表是否创建成功
sqlite3 ~/.evogen/data/evogen.db ".tables"
# 预期输出：
# _migration_versions    experience_feedback    memory_facts
# experience_trajectories  memory_snapshots       persona_attributes
```

## 5. 启动服务

EvoGen 包含两个服务组件：

| 组件 | 端口 | 说明 |
|------|------|------|
| **Backend API** | `8100` | REST API 服务（记忆/经验/人格） |
| **Gateway** | `9180` | Web 前端 + WebSocket + API 代理 |

### 方式 A：开发模式（推荐入门）

**终端 1 — 启动后端 API：**

```bash
cd /root/next-gen-agent
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8100 --reload
```

预期输出：

```
🚀 EvoGen Backend starting...
  Database: /root/.evogen/data/evogen.db
  Chroma:   /root/.evogen/data/chroma
  LLM:      deepseek/deepseek-v4-pro
  Database: ✅ migration complete
INFO:     Uvicorn running on http://0.0.0.0:8100
```

验证 API 可用：

```bash
curl http://localhost:8100/health
# {"status":"ok","version":"0.1.0","llm":"deepseek/deepseek-v4-pro","embedding":"BAAI/bge-m3(1024d)"}
```

**终端 2 — 启动 Gateway（Web 前端）：**

```bash
# 安装 agent-framework（如未安装）
pip install -e /root/agent-framework

# 启动 Gateway，挂载前端静态文件
hermes gateway start --host 0.0.0.0 --port 9180 --webchat-dir /root/next-gen-agent/frontend/dist
```

### 方式 B：前端开发模式

如果不使用 Gateway，可以直接用 Vite 开发服务器：

**终端 1（后端）：**

```bash
cd /root/next-gen-agent
uvicorn backend.main:app --host 0.0.0.0 --port 8100 --reload
```

**终端 2（前端）：**

```bash
cd /root/next-gen-agent/frontend
npm install        # 首次运行
npm run dev        # 启动 Vite 开发服务器，默认端口 5174
```

## 6. 访问 Web 前端

- **Gateway 模式**：打开浏览器访问 `http://localhost:9180`
- **Vite 开发模式**：打开浏览器访问 `http://localhost:5174`

前端页面包括：

| 页面 | 路径 | 功能 |
|------|------|------|
| 对话 | `/chat` | AI 对话交互 |
| 记忆管理 | `/memory` | 查看/搜索/管理记忆 |
| 经验轨迹 | `/experience` | 查看会话轨迹与反馈 |
| 人格设置 | `/persona` | 管理 AI 人格属性 |
| 设置 | `/settings` | 模型配置等 |

## 7. Hello World 验证

通过 API 创建一条记忆并搜索验证，确认端到端流程正常。

### 步骤 1：创建一条记忆

```bash
curl -X POST http://localhost:8100/api/v1/memory/facts \
  -H "Content-Type: application/json" \
  -d '{
    "content": "用户喜欢吃川菜，尤其是麻婆豆腐和水煮鱼",
    "type": "preference",
    "importance": 0.8,
    "layer": "core",
    "tags": ["food", "preference"]
  }'
```

**成功响应：**

```json
{
  "ok": true,
  "data": {
    "id": "abc123...",
    "type": "preference",
    "content": "用户喜欢吃川菜，尤其是麻婆豆腐和水煮鱼",
    "importance": 0.8,
    "weight": 1.0,
    "layer": "core",
    "tags": ["food", "preference"],
    "created_at": "2026-05-31T..."
  }
}
```

### 步骤 2：语义搜索验证

```bash
curl "http://localhost:8100/api/v1/memory/facts?q=川菜&limit=5"
```

**成功响应 — 应该搜到刚才创建的记忆：**

```json
{
  "ok": true,
  "data": {
    "facts": [
      {
        "id": "abc123...",
        "type": "preference",
        "content": "用户喜欢吃川菜，尤其是麻婆豆腐和水煮鱼",
        "similarity": 0.92,
        ...
      }
    ],
    "total": 1,
    "limit": 5,
    "offset": 0
  }
}
```

### 步骤 3：查看统计信息

```bash
curl http://localhost:8100/api/v1/memory/stats
```

### 步骤 4：验证人格 API

```bash
# 获取当前人格属性
curl http://localhost:8100/api/v1/persona/attributes

# 更新人格属性
curl -X PUT http://localhost:8100/api/v1/persona/attributes/conciseness \
  -H "Content-Type: application/json" \
  -d '{"value": 0.8}'
```

✅ **全部通过即表示 EvoGen 已成功运行！**

## 8. BGE-M3 模型首次下载说明

EvoGen 使用 **BAAI/bge-m3** 嵌入模型进行语义搜索。首次使用时会自动从 Hugging Face 下载模型文件（约 2.2GB）。

**自动下载：**

- 触发时机：首次调用向量搜索 API（如 `GET /memory/facts?q=xxx`）
- 下载位置：`~/.cache/huggingface/hub/`
- 耗时：取决于网络速度，通常 1-5 分钟

**手动预下载（推荐）：**

```bash
# 预下载 BGE-M3，避免首次请求等待
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-m3')"
```

**配置选项：**

```bash
# 使用 GPU 加速（需要 CUDA）
export EMBEDDING_DEVICE="cuda"

# 使用自定义嵌入模型
export EMBEDDING_MODEL="BAAI/bge-m3"
export EMBEDDING_DIM="1024"
```

> ⚠️ **注意**：
> - 默认使用 CPU 推理。如有 NVIDIA GPU 并安装 CUDA 版 PyTorch，设置 `EMBEDDING_DEVICE=cuda` 可大幅加速。
> - 国内用户如 Hugging Face 下载慢，可设置镜像：
>   ```bash
>   export HF_ENDPOINT=https://hf-mirror.com
>   ```

---

## 常见问题

### Q: 启动时报 `ModuleNotFoundError: No module named 'backend'`
**A:** 确保在项目根目录（`/root/next-gen-agent`）下运行命令，或将项目根目录加入 `PYTHONPATH`。

### Q: API 调用返回 500 且提示 DEEPSEEK_API_KEY
**A:** 检查 `DEEPSEEK_API_KEY` 环境变量是否已设置且正确。

### Q: 向量搜索很慢或报错
**A:** 检查 BGE-M3 模型是否已下载完成。首次搜索需要加载模型到内存，耗时约 10-30 秒。

### Q: 前端无法连接后端
**A:** 确保后端已启动在 `8100` 端口，且 Gateway 的 API 代理配置正确。开发模式下检查 Vite 代理配置（`vite.config.ts` 中 `/api` 指向的地址）。

---

**下一步**：查看 [API 参考文档](./api-reference.md) 了解完整的 REST API。
