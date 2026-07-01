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
        "description": "安全漏洞扫描结果的结构化通告，包含漏洞详情、影响范围和修复建议",
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
        ],
    },
    "port-scan": {
        "name": "端口扫描报告",
        "version": "1.0",
        "description": "目标主机的端口开放情况与服务指纹识别报告",
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
    "server-health": {
        "name": "服务器健康巡检报告",
        "version": "1.0",
        "description": "服务器系统资源、进程状态和运行时间的综合健康检查报告",
        "sections": [
            {
                "key": "summary",
                "label": "巡检概要",
                "required": True,
                "fields": [
                    {"key": "hostname", "label": "主机名", "type": "str"},
                    {"key": "check_time", "label": "巡检时间", "type": "str"},
                    {"key": "uptime", "label": "运行时间", "type": "str"},
                    {"key": "overall_status", "label": "总体状态", "type": "str"},
                ],
            },
            {
                "key": "system_resources",
                "label": "系统资源",
                "required": True,
                "fields": [
                    {"key": "cpu_usage", "label": "CPU使用率", "type": "str"},
                    {"key": "memory_usage", "label": "内存使用率", "type": "str"},
                    {"key": "disk_usage", "label": "磁盘使用率", "type": "str"},
                    {"key": "load_average", "label": "负载均值", "type": "str"},
                ],
            },
            {
                "key": "process_status",
                "label": "进程状态",
                "required": True,
                "fields": [
                    {"key": "running_processes", "label": "运行中关键进程", "type": "list"},
                    {"key": "zombie_processes", "label": "僵尸进程", "type": "str"},
                ],
            },
            {
                "key": "recommendations",
                "label": "优化建议",
                "required": False,
                "fields": [
                    {"key": "actions", "label": "建议项", "type": "list"},
                ],
            },
        ],
    },
    "code-review": {
        "name": "代码审查报告",
        "version": "1.0",
        "description": "代码静态分析结果汇总，包含代码质量、安全缺陷和最佳实践建议",
        "sections": [
            {
                "key": "summary",
                "label": "审查概要",
                "required": True,
                "fields": [
                    {"key": "project", "label": "项目名称", "type": "str"},
                    {"key": "branch", "label": "分支", "type": "str"},
                    {"key": "commit", "label": "提交哈希", "type": "str"},
                    {"key": "review_time", "label": "审查时间", "type": "str"},
                    {"key": "total_files", "label": "审查文件数", "type": "str"},
                ],
            },
            {
                "key": "issues",
                "label": "发现的问题",
                "required": True,
                "fields": [
                    {"key": "critical_issues", "label": "严重问题", "type": "list"},
                    {"key": "warnings", "label": "警告", "type": "list"},
                    {"key": "suggestions", "label": "改进建议", "type": "list"},
                ],
            },
            {
                "key": "quality_metrics",
                "label": "质量指标",
                "required": False,
                "fields": [
                    {"key": "code_smells", "label": "代码坏味", "type": "str"},
                    {"key": "duplication", "label": "重复率", "type": "str"},
                    {"key": "coverage", "label": "测试覆盖率", "type": "str"},
                ],
            },
        ],
    },
    "network-topology": {
        "name": "网络拓扑探测报告",
        "version": "1.0",
        "description": "目标网络的存活主机、路由路径和拓扑结构探测结果",
        "sections": [
            {
                "key": "summary",
                "label": "探测概要",
                "required": True,
                "fields": [
                    {"key": "target_network", "label": "目标网段", "type": "str"},
                    {"key": "scan_time", "label": "探测时间", "type": "str"},
                    {"key": "alive_hosts", "label": "存活主机数", "type": "str"},
                ],
            },
            {
                "key": "hosts",
                "label": "存活主机",
                "required": True,
                "fields": [
                    {"key": "host_list", "label": "主机列表", "type": "list"},
                    {"key": "open_ports_summary", "label": "开放端口汇总", "type": "text"},
                ],
            },
            {
                "key": "topology",
                "label": "拓扑信息",
                "required": False,
                "fields": [
                    {"key": "route_hops", "label": "路由跳数", "type": "str"},
                    {"key": "latency", "label": "延迟", "type": "str"},
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

    # 如果有完整扫描输出，追加给 LLM
    full_output = data.get("_full_scan_output", "")
    scan_context = ""
    if full_output:
        # 取前 2000 字符的控制台输出
        scan_context = f"\n\n以下是本次扫描的完整控制台输出（供参考）：\n```\n{full_output[:2000]}\n```\n"

    prompt = f"""你是一个网络安全报告撰写专家。请根据以下扫描数据和模板结构，生成一份专业的 Markdown 格式安全检测报告。

模板名称：{template['name']}

模板结构说明：
{chr(10).join(f"- 「{sec['label']}」" for sec in template['sections'])}

以下是本次扫描的原始数据（字段名: 值）：

{data_summary}{scan_context}

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
                "description": t.get("description", ""),
                "version": t["version"],
                "section_count": len(t["sections"]),
                "sections": [
                    {
                        "label": s["label"],
                        "required": s.get("required", False),
                        "fields": [f["label"] for f in s.get("fields", [])],
                    }
                    for s in t["sections"]
                ],
            }
            for tid, t in TEMPLATES.items()
        ],
    }


@router.post("/generate-artifact")
async def generate_report_artifact(body: dict, user_id: str = Depends(get_current_user)):
    """渲染模板并存入制品（Agent 在对话中调用）.

    Request body:
    {
        "template": "vuln-advisory",
        "data": { ... },
        "session_id": "xxx",
        "artifact_title": "报告标题（可选）"
    }
    """
    template_name = body.get("template", "vuln-advisory")
    data = body.get("data", {})
    session_id = body.get("session_id", "")
    artifact_title = body.get("artifact_title", f"报告_{template_name}")

    if template_name not in TEMPLATES:
        raise HTTPException(
            status_code=400,
            detail={"ok": False, "error": f"Unknown template: {template_name}"},
        )

    try:
        report = render_report(template_name, data)
        rmd = report.get("raw_markdown", "")

        if not rmd:
            return {"ok": False, "error": "报告渲染返回为空"}

        # 存入制品
        try:
            from backend.api.artifacts_routes import store_artifact
            artifact_id = store_artifact(
                "doc",
                artifact_title,
                rmd,
                session_id=session_id,
                user_id=user_id,
            )
            logger.info(f"Report artifact stored: {artifact_id} for template={template_name}")
        except Exception as e:
            logger.warning(f"Failed to store report artifact: {e}")
            return {"ok": True, "data": report, "artifact_error": str(e)}

        return {
            "ok": True,
            "data": {
                **report,
                "artifact_id": artifact_id,
            },
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"ok": False, "error": str(e)})
