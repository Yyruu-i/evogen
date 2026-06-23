#!/usr/bin/env python3
"""MCP Server — Nmap 端口扫描工具封装.

使用方式（MCP JSON-RPC）:
  mcp_nmap_server.py <port_scan '{"target":"127.0.0.1","ports":"1-1000"}'

或直接 CLI:
  mcp_nmap_server.py --cli --target 127.0.0.1 --ports 22,80,443
"""

import argparse
import json
import subprocess
import sys
import re


def port_scan(target: str, ports: str = "1-1000", arguments: str = "") -> dict:
    """执行 nmap 端口扫描，返回结构化结果.

    Args:
        target: 目标 IP 或域名
        ports:  端口范围/列表，如 "22,80,443" 或 "1-1000"
        arguments: 额外 nmap 参数（如 -sV -sC）

    Returns:
        {"success": bool, "data": {...}, "error": str|None}
    """
    try:
        cmd = ["nmap", "-T4", "-oX", "-"]
        if arguments:
            cmd.extend(arguments.split())
        cmd.extend(["-p", ports, target])

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
        )

        if result.returncode not in (0, 1):  # nmap exit 1 still has results
            return {"success": False, "data": {}, "error": f"nmap failed: {result.stderr[:500]}"}

        xml_output = result.stdout
        parsed = _parse_nmap_xml(xml_output)
        parsed["raw_command"] = " ".join(cmd)
        return {"success": True, "data": parsed, "error": None}

    except subprocess.TimeoutExpired:
        return {"success": False, "data": {}, "error": "扫描超时（300秒）"}
    except FileNotFoundError:
        return {"success": False, "data": {}, "error": "nmap 未安装"}
    except Exception as e:
        return {"success": False, "data": {}, "error": str(e)}


def _parse_nmap_xml(xml_text: str) -> dict:
    """简易 nmap XML 解析."""
    result = {
        "target": "",
        "status": "unknown",
        "hostname": "",
        "open_ports": [],
        "os_guess": "",
        "scan_time": "",
        "summary": "",
    }

    # Extract target
    m = re.search(r'<address addr="([^"]+)"', xml_text)
    if m:
        result["target"] = m.group(1)

    # Extract hostname
    m = re.search(r'<hostname name="([^"]+)"', xml_text)
    if m:
        result["hostname"] = m.group(1)

    # Extract port info
    for port_match in re.finditer(
        r'<port protocol="([^"]*)" portid="(\d+)".*?<state state="([^"]*)"[^>]*/>.*?<service name="([^"]*)"',
        xml_text, re.DOTALL,
    ):
        result["open_ports"].append({
            "port": int(port_match.group(2)),
            "protocol": port_match.group(1),
            "state": port_match.group(3),
            "service": port_match.group(4),
        })

    # Extract OS guess
    m = re.search(r'<osmatch name="([^"]+)"', xml_text)
    if m:
        result["os_guess"] = m.group(1)

    # Extract scan stats
    m = re.search(r'<runstats>.*?<finished.*?summary="([^"]+)"', xml_text, re.DOTALL)
    if m:
        result["summary"] = m.group(1)

    # Overall status
    if result["open_ports"]:
        result["status"] = "vulnerable"
    else:
        result["status"] = "secure"

    return result


def _mcp_handler(method: str, params: dict) -> dict:
    """MCP JSON-RPC handler."""
    if method == "port_scan":
        result = port_scan(
            target=params.get("target", ""),
            ports=params.get("ports", "1-1000"),
            arguments=params.get("arguments", ""),
        )
        return {"jsonrpc": "2.0", "result": result, "id": params.get("id", 1)}
    else:
        return {
            "jsonrpc": "2.0",
            "error": {"code": -32601, "message": f"未知方法: {method}"},
            "id": params.get("id", None),
        }


def main():
    parser = argparse.ArgumentParser(description="Nmap MCP Server")
    parser.add_argument("--cli", action="store_true", help="CLI 模式")
    parser.add_argument("--target", default="127.0.0.1", help="扫描目标")
    parser.add_argument("--ports", default="22,80,443", help="端口")
    parser.add_argument("--args", default="", help="额外 nmap 参数")
    args, unknown = parser.parse_known_args()

    if args.cli:
        result = port_scan(args.target, args.ports, args.args)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    # MCP JSON-RPC mode: accept JSON on stdin or argv
    if len(sys.argv) > 1:
        # Format: script.py <method> <params_json>
        method = sys.argv[1]
        params = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
        output = _mcp_handler(method, params)
    else:
        # Read from stdin
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
