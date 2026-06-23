#!/usr/bin/env python3
"""MCP Server — Nuclei 漏洞扫描工具封装.

使用方式（MCP JSON-RPC）:
  mcp_nuclei_server.py vuln_scan '{"target":"http://example.com","severity":"critical,high"}'

或直接 CLI:
  mcp_nuclei_server.py --cli --target http://example.com
"""

import argparse
import json
import subprocess
import sys
import re


def vuln_scan(target: str, severity: str = "critical,high", templates: str = "") -> dict:
    """执行 Nuclei 漏洞扫描，返回结构化结果.

    Args:
        target:   目标 URL 或 IP
        severity: 严重级别过滤，如 "critical,high,medium"
        templates: 指定模板路径或类型

    Returns:
        {"success": bool, "data": {...}, "error": str|None}
    """
    try:
        cmd = ["nuclei", "-json", "-silent"]
        if severity:
            cmd.extend(["-severity", severity])
        if templates:
            cmd.extend(["-t", templates])
        cmd.append("-u")
        cmd.append(target)

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
        )

        parsed = _parse_nuclei_output(result.stdout, result.stderr)
        parsed["raw_command"] = " ".join(cmd)
        parsed["return_code"] = result.returncode

        return {"success": True, "data": parsed, "error": None if result.returncode == 0 else result.stderr[:500]}

    except subprocess.TimeoutExpired:
        return {"success": False, "data": {}, "error": "扫描超时（300秒）"}
    except FileNotFoundError:
        return {"success": False, "data": {}, "error": "nuclei 未安装。请安装: go install -v github.com/projectdiscovery/nuclei/v3/cmd/nuclei@latest", "fallback": True}
    except Exception as e:
        return {"success": False, "data": {}, "error": str(e)}


def _parse_nuclei_output(stdout: str, stderr: str) -> dict:
    """解析 Nuclei 的 JSON 逐行输出."""
    findings = []
    for line in stdout.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            finding = json.loads(line)
            findings.append({
                "template": finding.get("template-id", ""),
                "name": finding.get("info", {}).get("name", ""),
                "severity": finding.get("info", {}).get("severity", ""),
                "type": finding.get("type", ""),
                "matched_at": finding.get("matched-at", ""),
                "host": finding.get("host", ""),
                "description": finding.get("info", {}).get("description", ""),
                "reference": (finding.get("info", {}) or {}).get("reference", ""),
            })
        except json.JSONDecodeError:
            continue

    return {
        "total_findings": len(findings),
        "findings": findings,
        "warnings": stderr[:1000] if stderr else "",
    }


def _mcp_handler(method: str, params: dict) -> dict:
    """MCP JSON-RPC handler."""
    if method == "vuln_scan":
        result = vuln_scan(
            target=params.get("target", ""),
            severity=params.get("severity", "critical,high"),
            templates=params.get("templates", ""),
        )
        return {"jsonrpc": "2.0", "result": result, "id": params.get("id", 1)}
    else:
        return {
            "jsonrpc": "2.0",
            "error": {"code": -32601, "message": f"未知方法: {method}"},
            "id": params.get("id", None),
        }


def main():
    parser = argparse.ArgumentParser(description="Nuclei MCP Server")
    parser.add_argument("--cli", action="store_true", help="CLI 模式")
    parser.add_argument("--target", default="http://example.com", help="扫描目标")
    parser.add_argument("--severity", default="critical,high", help="严重级别")
    parser.add_argument("--templates", default="", help="模板路径")
    args, unknown = parser.parse_known_args()

    if args.cli:
        result = vuln_scan(args.target, args.severity, args.templates)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    # MCP JSON-RPC mode
    if len(sys.argv) > 1:
        method = sys.argv[1]
        params = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
        output = _mcp_handler(method, params)
    else:
        try:
            raw = sys.stdin.read()
            req = json.loads(raw)
            method = req.get("method", "")
            params = req.get("params", {})
            output = _mcp_handler(method, params)
        except (json.JSONDecodeError, Exception) as e:
            output = {
                "jsonrpc": "2.0",
                "error": {"code": -32700, "message": f"解析错误: {e}"},
                "id": None,
            }

    print(json.dumps(output, ensure_ascii=False))


if __name__ == "__main__":
    main()
