# EvoGen REST API 参考

> 版本：v1 | 基础 URL：`http://localhost:8100/api/v1`

---

## 概述

EvoGen API 采用 RESTful 风格，统一响应格式：

**成功响应：**

```json
{ "ok": true, "data": { ... } }
```

**错误响应：**

```json
{ "ok": false, "error": "错误描述信息" }
```

---

## 目录

- [Memory（记忆）](#memory记忆) — 7 个端点
- [Experience（经验）](#experience经验) — 5 个端点
- [Persona（人格）](#persona人格) — 6 个端点

---

# Memory（记忆）

三层记忆管理：`transient` → `working` → `core` → `archive`。

---

## 1. 获取记忆列表

```http
GET /api/v1/memory/facts
```

**查询参数：**

| 名称 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `layer` | string | 否 | 按层级筛选：`transient` / `working` / `core` / `all` |
| `type` | string | 否 | 按类型筛选：`preference` / `fact` / `procedure` / `relationship` |
| `limit` | integer | 否 | 每页数量（1-500，默认 50） |
| `offset` | integer | 否 | 偏移量（默认 0） |
| `q` | string | 否 | 语义搜索关键词，触发 BGE-M3 向量检索 |

**curl 示例（列表查询）：**

```bash
curl "http://localhost:8100/api/v1/memory/facts?layer=core&limit=10"
```

**curl 示例（语义搜索）：**

```bash
curl "http://localhost:8100/api/v1/memory/facts?q=川菜&limit=5"
```

**成功响应：**

```json
{
  "ok": true,
  "data": {
    "facts": [
      {
        "id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
        "type": "preference",
        "content": "用户喜欢吃川菜，尤其是麻婆豆腐和水煮鱼",
        "importance": 0.8,
        "weight": 1.0,
        "layer": "core",
        "source_session_id": null,
        "source_interaction_id": null,
        "privacy_level": "private",
        "tags": ["food", "preference"],
        "created_at": "2026-05-31T10:00:00",
        "updated_at": "2026-05-31T10:00:00",
        "last_accessed_at": "2026-05-31T10:00:00",
        "similarity": 0.92
      }
    ],
    "total": 1,
    "limit": 5,
    "offset": 0
  }
}
```

**错误响应（500）：**

```json
{
  "detail": {
    "ok": false,
    "error": "Internal server error message"
  }
}
```

---

## 2. 获取单条记忆

```http
GET /api/v1/memory/facts/{fact_id}
```

**路径参数：**

| 名称 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `fact_id` | string | 是 | 记忆事实 ID |

**curl 示例：**

```bash
curl "http://localhost:8100/api/v1/memory/facts/f47ac10b-58cc-4372-a567-0e02b2c3d479"
```

**成功响应：**

```json
{
  "ok": true,
  "data": {
    "id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
    "type": "preference",
    "content": "用户喜欢吃川菜，尤其是麻婆豆腐和水煮鱼",
    "importance": 0.8,
    "weight": 1.0,
    "layer": "core",
    "source_session_id": null,
    "source_interaction_id": null,
    "privacy_level": "private",
    "tags": ["food", "preference"],
    "created_at": "2026-05-31T10:00:00",
    "updated_at": "2026-05-31T10:00:00",
    "last_accessed_at": "2026-05-31T10:00:00",
    "similarity": null
  }
}
```

**错误响应（404）：**

```json
{
  "detail": {
    "ok": false,
    "error": "Fact not found: f47ac10b-58cc-4372-a567-0e02b2c3d479"
  }
}
```

---

## 3. 创建记忆

```http
POST /api/v1/memory/facts
```

**请求体：**

| 名称 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `content` | string | **是** | 记忆内容文本 |
| `type` | string | 否 | 记忆类型：`preference` / `fact` / `procedure` / `relationship`（默认 `fact`） |
| `importance` | number | 否 | 重要度 0-1（默认 0.5） |
| `layer` | string | 否 | 记忆层级：`transient` / `working` / `core`（默认 `working`） |
| `tags` | string[] | 否 | 标签列表（默认 `[]`） |
| `privacy_level` | string | 否 | 隐私级别：`public` / `private` / `sensitive`（默认 `private`） |

**curl 示例：**

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

**成功响应（201）：**

```json
{
  "ok": true,
  "data": {
    "id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
    "type": "preference",
    "content": "用户喜欢吃川菜，尤其是麻婆豆腐和水煮鱼",
    "importance": 0.8,
    "weight": 1.0,
    "layer": "core",
    "source_session_id": null,
    "source_interaction_id": null,
    "privacy_level": "private",
    "tags": ["food", "preference"],
    "created_at": "2026-05-31T10:00:00",
    "updated_at": "2026-05-31T10:00:00",
    "last_accessed_at": "2026-05-31T10:00:00",
    "similarity": null
  }
}
```

**错误响应（400）：**

```json
{
  "detail": {
    "ok": false,
    "error": "content is required"
  }
}
```

---

## 4. 更新记忆

```http
PUT /api/v1/memory/facts/{fact_id}
```

**路径参数：**

| 名称 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `fact_id` | string | 是 | 记忆事实 ID |

**请求体（所有字段可选，支持部分更新）：**

| 名称 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `content` | string | 否 | 更新记忆内容 |
| `type` | string | 否 | 更新记忆类型 |
| `importance` | number | 否 | 更新重要度 0-1 |
| `layer` | string | 否 | 更新层级 |
| `tags` | string[] | 否 | 更新标签列表 |
| `privacy_level` | string | 否 | 更新隐私级别 |

**curl 示例：**

```bash
curl -X PUT http://localhost:8100/api/v1/memory/facts/f47ac10b-58cc-4372-a567-0e02b2c3d479 \
  -H "Content-Type: application/json" \
  -d '{
    "importance": 0.9,
    "tags": ["food", "preference", "spicy"]
  }'
```

**成功响应：**

```json
{
  "ok": true,
  "data": {
    "id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
    "type": "preference",
    "content": "用户喜欢吃川菜，尤其是麻婆豆腐和水煮鱼",
    "importance": 0.9,
    "weight": 1.0,
    "layer": "core",
    "tags": ["food", "preference", "spicy"],
    ...
  }
}
```

**错误响应（404）：**

```json
{
  "detail": {
    "ok": false,
    "error": "Fact not found: f47ac10b-58cc-4372-a567-0e02b2c3d479"
  }
}
```

---

## 5. 删除记忆

```http
DELETE /api/v1/memory/facts/{fact_id}
```

**路径参数：**

| 名称 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `fact_id` | string | 是 | 记忆事实 ID |

**curl 示例：**

```bash
curl -X DELETE http://localhost:8100/api/v1/memory/facts/f47ac10b-58cc-4372-a567-0e02b2c3d479
```

**成功响应：**

```json
{
  "ok": true,
  "data": {
    "deleted_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479"
  }
}
```

**错误响应（404）：**

```json
{
  "detail": {
    "ok": false,
    "error": "Fact not found: f47ac10b-58cc-4372-a567-0e02b2c3d479"
  }
}
```

---

## 6. 获取记忆统计

```http
GET /api/v1/memory/stats
```

无请求参数。

**curl 示例：**

```bash
curl http://localhost:8100/api/v1/memory/stats
```

**成功响应：**

```json
{
  "ok": true,
  "data": {
    "total_facts": 42,
    "by_layer": {
      "transient": 5,
      "working": 20,
      "core": 15,
      "archive": 2
    },
    "by_type": {
      "preference": 12,
      "fact": 20,
      "procedure": 7,
      "relationship": 3
    },
    "last_extraction_at": "2026-05-31T09:55:00",
    "total_vector_bytes": 1048576
  }
}
```

---

## 7. 强化记忆

```http
POST /api/v1/memory/facts/{fact_id}/reinforce
```

增加记忆的权重和重要性，使其更难被衰减淘汰。

**路径参数：**

| 名称 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `fact_id` | string | 是 | 记忆事实 ID |

**请求体（可选）：**

| 名称 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `amount` | number | 否 | 强化量（默认 0.1） |

**curl 示例：**

```bash
curl -X POST http://localhost:8100/api/v1/memory/facts/f47ac10b-58cc-4372-a567-0e02b2c3d479/reinforce \
  -H "Content-Type: application/json" \
  -d '{"amount": 0.2}'
```

**成功响应：**

```json
{
  "ok": true,
  "data": {
    "id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
    "type": "preference",
    "content": "用户喜欢吃川菜，尤其是麻婆豆腐和水煮鱼",
    "importance": 0.85,
    "weight": 1.2,
    "layer": "core",
    ...
  }
}
```

**错误响应（404）：**

```json
{
  "detail": {
    "ok": false,
    "error": "Fact not found: f47ac10b-58cc-4372-a567-0e02b2c3d479"
  }
}
```

---

# Experience（经验）

会话轨迹记录与用户反馈管理。

---

## 8. 获取轨迹列表

```http
GET /api/v1/experience/trajectories
```

**查询参数：**

| 名称 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `limit` | integer | 否 | 每页数量（1-500，默认 50） |
| `offset` | integer | 否 | 偏移量（默认 0） |
| `with_feedback_only` | boolean | 否 | 仅返回有反馈的轨迹（默认 false） |
| `success` | boolean | 否 | 按任务成功/失败筛选 |

**curl 示例：**

```bash
curl "http://localhost:8100/api/v1/experience/trajectories?limit=20&success=true"
```

**成功响应：**

```json
{
  "ok": true,
  "data": {
    "trajectories": [
      {
        "id": "traj-001",
        "session_id": "sess-abc",
        "session_title": "帮我制定健身计划",
        "created_at": "2026-05-31T09:00:00",
        "turn_count": 8,
        "success": true,
        "feedback_count": 2,
        "last_feedback_at": "2026-05-31T09:15:00"
      }
    ],
    "total": 15,
    "limit": 20,
    "offset": 0
  }
}
```

---

## 9. 获取轨迹详情

```http
GET /api/v1/experience/trajectories/{trajectory_id}
```

**路径参数：**

| 名称 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `trajectory_id` | string | 是 | 轨迹 ID |

**curl 示例：**

```bash
curl "http://localhost:8100/api/v1/experience/trajectories/traj-001"
```

**成功响应：**

```json
{
  "ok": true,
  "data": {
    "id": "traj-001",
    "session_id": "sess-abc",
    "session_title": "帮我制定健身计划",
    "turns": [
      {
        "turn_index": 0,
        "llm_response_chunk": "好的，我来帮你制定健身计划...",
        "token_usage": 150,
        "tool_calls": null
      },
      {
        "turn_index": 1,
        "llm_response_chunk": "根据你的情况，我建议...",
        "token_usage": 200,
        "tool_calls": [
          {
            "tool_name": "search",
            "arguments": "健身计划 初学者",
            "result_summary": "找到 3 条相关结果",
            "success": true,
            "execution_time_ms": 450
          }
        ]
      }
    ],
    "outcome": {
      "success": true,
      "total_tokens": 1200,
      "wall_time_ms": 15000,
      "user_cancelled": false
    },
    "created_at": "2026-05-31T09:00:00",
    "feedback": [
      {
        "id": "fb-001",
        "trajectory_id": "traj-001",
        "rating": "good",
        "note": "计划很详细，非常实用",
        "status": "reviewed",
        "created_at": "2026-05-31T09:10:00",
        "reviewed_at": "2026-05-31T09:15:00"
      }
    ]
  }
}
```

**错误响应（404）：**

```json
{
  "detail": {
    "ok": false,
    "error": "Trajectory not found: traj-001"
  }
}
```

---

## 10. 获取反馈列表

```http
GET /api/v1/experience/feedback
```

**查询参数：**

| 名称 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `status` | string | 否 | 按状态筛选：`pending` / `reviewed` / `applied` / `dismissed` |
| `limit` | integer | 否 | 每页数量（1-500，默认 50） |
| `offset` | integer | 否 | 偏移量（默认 0） |

**curl 示例：**

```bash
curl "http://localhost:8100/api/v1/experience/feedback?status=pending&limit=10"
```

**成功响应：**

```json
{
  "ok": true,
  "data": {
    "feedback": [
      {
        "id": "fb-002",
        "trajectory_id": "traj-002",
        "rating": "bad",
        "note": "回复太啰嗦了，不够简洁",
        "status": "pending",
        "created_at": "2026-05-31T10:00:00",
        "reviewed_at": null
      }
    ],
    "total": 1,
    "limit": 10,
    "offset": 0
  }
}
```

---

## 11. 添加反馈

```http
POST /api/v1/experience/feedback
```

**请求体：**

| 名称 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `trajectory_id` | string | **是** | 关联的轨迹 ID |
| `rating` | string | **是** | 评分：`good` / `neutral` / `bad` |
| `note` | string | 否 | 用户备注 |

**curl 示例：**

```bash
curl -X POST http://localhost:8100/api/v1/experience/feedback \
  -H "Content-Type: application/json" \
  -d '{
    "trajectory_id": "traj-001",
    "rating": "good",
    "note": "计划很详细，非常实用"
  }'
```

**成功响应（201）：**

```json
{
  "ok": true,
  "data": {
    "id": "fb-003",
    "trajectory_id": "traj-001",
    "rating": "good",
    "note": "计划很详细，非常实用",
    "status": "pending",
    "created_at": "2026-05-31T10:30:00",
    "reviewed_at": null
  }
}
```

**错误响应（400）：**

```json
{
  "detail": {
    "ok": false,
    "error": "Invalid rating: xxx"
  }
}
```

---

## 12. 更新反馈状态

```http
PUT /api/v1/experience/feedback/{feedback_id}/status
```

**状态流转：** `pending` → `reviewed` → `applied` / `dismissed`

**路径参数：**

| 名称 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `feedback_id` | string | 是 | 反馈 ID |

**请求体：**

| 名称 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `status` | string | **是** | 新状态：`reviewed` / `applied` / `dismissed` |

**curl 示例：**

```bash
curl -X PUT http://localhost:8100/api/v1/experience/feedback/fb-003/status \
  -H "Content-Type: application/json" \
  -d '{"status": "reviewed"}'
```

**成功响应：**

```json
{
  "ok": true,
  "data": {
    "id": "fb-003",
    "trajectory_id": "traj-001",
    "rating": "good",
    "note": "计划很详细，非常实用",
    "status": "reviewed",
    "created_at": "2026-05-31T10:30:00",
    "reviewed_at": "2026-05-31T10:35:00"
  }
}
```

**错误响应（400）：**

```json
{
  "detail": {
    "ok": false,
    "error": "Invalid status: unknown, must be reviewed/applied/dismissed"
  }
}
```

---

# Persona（人格）

AI 人格属性管理与 System Prompt 注入。

---

## 13. 获取人格属性

```http
GET /api/v1/persona/attributes
```

无请求参数。返回所有 12 项默认属性及用户自定义属性。

**curl 示例：**

```bash
curl http://localhost:8100/api/v1/persona/attributes
```

**成功响应：**

```json
{
  "ok": true,
  "data": {
    "attributes": {
      "display_name": null,
      "preferred_language": "zh",
      "timezone": null,
      "conciseness": 0.5,
      "formality": 0.5,
      "warmth": 0.7,
      "directness": 0.5,
      "auto_approve_tools": false,
      "show_thinking": true,
      "response_language": "zh",
      "learned_preferences": {},
      "discovery_questions_asked": 0
    }
  }
}
```

---

## 14. 批量更新人格属性

```http
PUT /api/v1/persona/attributes
```

**请求体（扁平 JSON 对象，key 为属性名）：**

| 名称 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `{key}` | any | 是 | 要更新的属性键值对，可传多个 |

**curl 示例：**

```bash
curl -X PUT http://localhost:8100/api/v1/persona/attributes \
  -H "Content-Type: application/json" \
  -d '{
    "conciseness": 0.8,
    "formality": 0.3,
    "display_name": "Evo"
  }'
```

**成功响应：**

```json
{
  "ok": true,
  "data": {
    "attributes": {
      "display_name": "Evo",
      "preferred_language": "zh",
      "timezone": null,
      "conciseness": 0.8,
      "formality": 0.3,
      "warmth": 0.7,
      "directness": 0.5,
      "auto_approve_tools": false,
      "show_thinking": true,
      "response_language": "zh",
      "learned_preferences": {},
      "discovery_questions_asked": 0
    },
    "persona": { ... }
  }
}
```

**错误响应（400）：**

```json
{
  "detail": {
    "ok": false,
    "error": "No attributes provided"
  }
}
```

---

## 15. 更新单个属性

```http
PUT /api/v1/persona/attributes/{key}
```

**路径参数：**

| 名称 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `key` | string | 是 | 属性名（如 `conciseness`） |

**请求体：**

| 名称 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `value` | any | **是** | 属性新值 |

**curl 示例：**

```bash
curl -X PUT http://localhost:8100/api/v1/persona/attributes/conciseness \
  -H "Content-Type: application/json" \
  -d '{"value": 0.9}'
```

**成功响应：**

```json
{
  "ok": true,
  "data": {
    "key": "conciseness",
    "value": 0.9,
    "persona": { ... }
  }
}
```

**错误响应（400）：**

```json
{
  "detail": {
    "ok": false,
    "error": "Missing 'value' in request body"
  }
}
```

---

## 16. 导出人格

```http
GET /api/v1/persona/export
```

导出当前人格配置为 JSON 字符串，可用于备份或迁移。

**curl 示例：**

```bash
curl http://localhost:8100/api/v1/persona/export
```

**成功响应：**

```json
{
  "ok": true,
  "data": {
    "json": "{\"display_name\": \"Evo\", \"conciseness\": 0.8, ...}"
  }
}
```

---

## 17. 导入人格

```http
POST /api/v1/persona/import
```

从 JSON 字符串导入人格配置，覆盖当前设置。

**请求体：**

| 名称 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `json_str` | string | **是** | 从 `/persona/export` 获取的 JSON 字符串 |

**curl 示例：**

```bash
curl -X POST http://localhost:8100/api/v1/persona/import \
  -H "Content-Type: application/json" \
  -d '{"json_str": "{\"display_name\":\"Evo\",\"conciseness\":0.8}"}'
```

**成功响应：**

```json
{
  "ok": true,
  "data": {
    "attributes": {
      "display_name": "Evo",
      "conciseness": 0.8,
      ...
    },
    "persona": { ... }
  }
}
```

**错误响应（400）：**

```json
{
  "detail": {
    "ok": false,
    "error": "Missing 'json_str' in request body"
  }
}
```

---

## 18. 预览 System Prompt

```http
GET /api/v1/persona/preview-prompt
```

预览基于当前人格属性生成的 System Prompt 注入片段。

**curl 示例：**

```bash
curl http://localhost:8100/api/v1/persona/preview-prompt
```

**成功响应：**

```json
{
  "ok": true,
  "data": {
    "prompt_injection": "## 人格设定\n- 名字：Evo\n- 语言：中文\n- 简洁度：0.8\n- 正式度：0.3\n..."
  }
}
```

---

# 附录

## HTTP 状态码

| 状态码 | 说明 |
|--------|------|
| `200` | 请求成功 |
| `201` | 创建成功（POST） |
| `400` | 请求参数错误 |
| `404` | 资源不存在 |
| `500` | 服务器内部错误 |

## 通用错误格式

所有错误响应遵循统一格式（通过 FastAPI `HTTPException` 的 `detail` 字段返回）：

```json
{
  "detail": {
    "ok": false,
    "error": "具体错误信息"
  }
}
```

## 健康检查

```http
GET /health
```

```bash
curl http://localhost:8100/health
```

```json
{
  "status": "ok",
  "version": "0.1.0",
  "llm": "deepseek/deepseek-v4-pro",
  "embedding": "BAAI/bge-m3(1024d)"
}
```
