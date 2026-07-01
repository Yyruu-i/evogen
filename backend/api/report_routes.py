"""报告引擎 — 接收扫描/检测结果，通过 DeepSeek 生成结构化报告."""
import json
import logging
import os
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException

from backend.auth.dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/report", tags=["report"])

# ── 报告模板定义 ────────────────

TEMPLATES: dict[str, dict[str, Any]] = {
    "vuln-advisory": {
        "name": "安全通告检测报告",
        "version": "1.0",
        "sections": [
            {
                "key": "summary",
                "label": "检测概要",
                "required": True,
                "fields": [
                    {"key": "advisory_id", "label": "通告编号", "type": "str"},
                    {"key": "advisory_title", "label": "通告标题", "type": "str"},
                    {"key": "severity", "label": "严重等级", "type": "str"},
                    {"key": "target", "label": "检测目标", "type": "str"},
                    {"key": "scan_time", "label": "检测时间", "type": "str"},
                ],
            },
            {
                "key": "tools",
                "label": "检测工具",
                "required": True,
                "fields": [
                    {"key": "tool_used", "label": "工具列表", "type": "str"},
                    {"key": "tool_results", "label": "检测结果摘要", "type": "text"},
                ],
            },
            {
                "key": "findings",
                "label": "发现项",
                "required": True,
                "fields": [
                    {"key": "open_ports", "label": "开放端口", "type": "text", "optional": True},
                    {"key": "vulnerabilities", "label": "漏洞列表", "type": "list"},
                    {"key": "rootkit_findings", "label": "Rootkit 检测结果", "type": "text", "optional": True},
                ],
            },
            {
                "key": "recommendations",
                "label": "安全建议",
                "required": True,
                "fields": [
                    {"key": "actions", "label": "修复建议", "type": "list"},
                ],
            },
            {
                "key": "appendix",
                "label": "附录",
                "required": False,
                "fields": [
                    {"key": "raw_output", "label": "原始输出摘要", "type": "text", "optional": True},
                    {"key": "scan_id", "label": "扫描记录ID", "type": "str", "optional": True},
                ],
            },
        ],
    },
    "port-scan": {
        "name": "端口扫描报告",
        "version": "1.0",
        "sections": [
            {
                "key": "summary",
                "label": "检测概要",
                "required": True,
                "fields": [
                    {"key": "target", "label": "检测目标", "type": "str"},
                    {"key": "scan_type", "label": "扫描类型", "type": "str"},
                    {"key": "scan_time", "label": "检测时间", "type": "str"},
                ],
            },
            {
                "key": "findings",
                "label": "开放端口",
                "required": True,
                "fields": [
                    {"key": "open_ports", "label": "端口列表", "type": "list"},
                ],
            },
            {
                "key": "recommendations",
                "label": "建议",
                "required": False,
                "fields": [
                    {"key": "actions", "label": "行动项", "type": "list"},
                ],
            },
        ],
    },
}


def extract_field(fields: list[dict], data: dict) -> tuple[dict[str, Any], list[str]]:
    """从 data 中提取模板定义的所有字段，标记缺失的必填字段."""
    result: dict[str, Any] = {}
    missing = []
    for field in fields:
        key = field["key"]
        label = field["label"]
        ftype = field["type"]
        optional = field.get("optional", False)
        optional_default = field.get("optional") is True or field.get("required") is False
        # 从 data 取值
        val = data.get(key, data.get(label, ""))
        if val is None or val == "":
            if not optional and not optional_default:
                missing.append(label)
            val = f"【{label}】待补充"
        else:
            val = _format_field(val, ftype)
        result[key] = val
    return result, missing


def _format_field(val: Any, ftype: str) -> str:
    """根据字段类型格式化值."""
    if ftype == "list":
        if isinstance(val, list):
            return "\n".join(f"- {v}" for v in val)
        return str(val)
    if ftype == "text":
        return str(val)
    return str(val).strip()


def render_report(template_name: str, data: dict) -> dict[str, Any]:
    """渲染指定模板的报告 — 通过 DeepSeek 生成 Markdown."""
    if template_name not in TEMPLATES:
        raise ValueError(f"Unknown template: {template_name}")

    template = TEMPLATES[template_name]

    # 构建 prompt：模板结构 + 数据
    sections_desc = []
    for sec in template["sections"]:
        fields_desc = []
        for f in sec.get("fields", []):
            key = f["key"]
            label = f["label"]
            val = data.get(key, "（未提供）")
            if isinstance(val, list):
                val = "\n".join(f"  - {v}" for v in val)
            fields_desc.append(f"  - {label}（{key}）: {val}")
        sections_desc.append(f"## {sec['label']}\n" + "\n".join(fields_desc))

    data_summary = "\n\n".join(sections_desc)

    prompt = f"""你是一个网络安全报告撰写专家。请根据以下扫描数据和模板结构，生成一份专业的 Markdown 格式安全检测报告。

模板名称：{template['name']}

模板结构说明：
{chr(10).join(f"- 「{sec['label']}」" for sec in template['sections'])}

以下是本次扫描的原始数据（字段名: 值）：

{data_summary}

要求：
1. 严格按照模板结构组织报告，每个章节都要有
2. 使用 Markdown 格式，善用表格、列表、加粗等排版
3. 如果扫描结果中包含端口列表、CVE 编号等结构化数据，请用表格呈现
4. 语言：中文
5. 最后加一行：_报告由 EvoGen AI 报告引擎自动生成_
6. 报告标题用 # 📋 开头"""

    now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    # 获取 LLM 配置（复用 chat_routes 的配置获取逻辑）
    try:
        from backend.api.chat_routes import _get_llm_base_url, _get_llm_api_key, _get_current_model
        model = _get_current_model()
        base_url = _get_llm_base_url()
        api_key = _get_llm_api_key()
    except Exception:
        model = "deepseek-chat"
        base_url = "https://api.deepseek.com"
        api_key = os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("LLM_API_KEY") or ""

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
        "max_tokens": 4096,
    }

    try:
        import httpx
        resp = httpx.post(
            f"{base_url.rstrip('/')}/v1/chat/completions",
            json=payload,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            timeout=60.0,
        )
        if resp.status_code == 200:
            raw_md = resp.json()["choices"][0]["message"]["content"]
        else:
            raw_md = f"# 📋 {template['name']}\n\n（报告引擎调用失败：HTTP {resp.status_code}）\n\n_报告由 EvoGen AI 报告引擎自动生成_"
    except Exception as e:
        raw_md = f"# 📋 {template['name']}\n\n（报告引擎调用失败：{e}）\n\n_报告由 EvoGen AI 报告引擎自动生成_"

    return {
        "template_name": template_name,
        "report_title": template["name"],
        "version": template["version"],
        "raw_markdown": raw_md,
        "complete": True,
        "missing_fields": None,
    }


# ── API 端点 ────────────────────


@router.post("/render")
@router.post("/v2/render")
async def render_report_endpoint(body: dict, user_id: str = Depends(get_current_user)):
    """渲染安全检测报告.

    Request body:
    {
        "template": "vuln-advisory" | "port-scan",
        "data": {
            "advisory_id": "CVE-2026-12345",
            "advisory_title": "Apache HTTP Server RCE",
            "severity": "高危",
            "target": "192.168.1.1",
            "tool_used": "nmap + nuclei",
            "tool_results": "...",
            "vulnerabilities": ["CVE-2026-12345 - Apache RCE"],
            "actions": ["升级Apache至2.4.63"],
            ...
        }
    }
    """
    template_name = body.get("template", "vuln-advisory")
    data = body.get("data", {})

    if template_name not in TEMPLATES:
        raise HTTPException(
            status_code=400,
            detail={"ok": False, "error": f"Unknown template: {template_name}. Available: {list(TEMPLATES.keys())}"},
        )

    try:
        report = render_report(template_name, data)
        return {"ok": True, "data": report}
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"ok": False, "error": str(e)})


@router.get("/templates")
async def list_templates():
    """列出所有可用的报告模板."""
    return {
        "ok": True,
        "data": [
            {
                "id": tid,
                "name": t["name"],
                "version": t["version"],
                "section_count": len(t["sections"]),
            }
            for tid, t in TEMPLATES.items()
        ],
    }
