"""报告引擎 — 接收扫描/检测结果，填充固定模板，返回结构化报告."""

import json
import logging
from typing import Any

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
    """渲染指定模板的报告."""
    if template_name not in TEMPLATES:
        raise ValueError(f"Unknown template: {template_name}")

    template = TEMPLATES[template_name]
    all_missing: list[str] = []
    rendered_sections: list[dict[str, Any]] = []

    for section in template["sections"]:
        section_data = {}
        extracted_data = {}
        all_missing_for_section = []
        for fmeta in section.get("fields", []):
            key = fmeta["key"]
            val = data.get(key, data.get(fmeta.get("label", ""), ""))
            if val and val != "":
                extracted_data[key] = _format_field(val, fmeta.get("type", "str"))
            else:
                optional = fmeta.get("optional", False)
                if optional:
                    extracted_data[key] = "（无）"
                else:
                    extracted_data[key] = f"【{fmeta['label']}】待补充"
                    all_missing_for_section.append(fmeta["label"])
        all_missing.extend(all_missing_for_section)
        rendered_sections.append({
            "label": section["label"],
            "required": section.get("required", True),
            "fields": extracted_data,
        })

    return {
        "template_name": template_name,
        "report_title": template["name"],
        "version": template["version"],
        "sections": rendered_sections,
        "missing_fields": all_missing if all_missing else None,
        "complete": len(all_missing) == 0,
        "raw_markdown": _to_markdown(template["name"], rendered_sections, all_missing),
    }


def _to_markdown(title: str, sections: list[dict], missing: list[str]) -> str:
    """将报告渲染为 Markdown 文本."""
    lines = [
        f"# 📋 {title}",
        "",
    ]
    for sec in sections:
        label = sec["label"]
        fields = sec["fields"]
        lines.append(f"## {label}")
        lines.append("")
        for key, val in fields.items():
            if val:
                lines.append(f"**{key}**:")
                lines.append(val)
                lines.append("")
        lines.append("---")
        lines.append("")
    if missing:
        lines.append("> ⚠️ 以下字段缺失：")
        for m in missing:
            lines.append(f"> - {m}")
        lines.append("")
    lines.append("_报告由 EvoGen 报告引擎自动生成_")
    return "\n".join(lines)


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
