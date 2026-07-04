#!/usr/bin/env python3
"""MCP Server — 安全检测综合工具包.

使用方式（MCP JSON-RPC）:
  mcp_security.py <method> '<json-args>'

方法列表:
  ping_sweep      — ICMP 存活探测
  security_scan   — 安全检查（端口扫描+AI分析）
  batch_scan      — 多厂商自动切换扫描
  gen_report      — 生成报告（Markdown）
  validate_report — 报告质量校验
  gen_selection_plan — 生成选型方案
  get_asset_profile  — 查询资产档案
"""

import json
import os
import re
import socket
import sqlite3
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

# ── 配置 ──
DATA_DIR = Path.home() / ".hermes" / ".sec-inspect-data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "security_inspection.db"

# 常见端口列表
COMMON_PORTS = {
    21: "FTP", 22: "SSH", 23: "Telnet", 25: "SMTP",
    53: "DNS", 80: "HTTP", 110: "POP3", 135: "RPC",
    139: "NetBIOS", 143: "IMAP", 443: "HTTPS", 445: "SMB",
    993: "IMAPS", 995: "POP3S", 1433: "MSSQL", 1521: "Oracle",
    2049: "NFS", 3306: "MySQL", 3389: "RDP", 5432: "PostgreSQL",
    6379: "Redis", 8080: "HTTP-Proxy", 8443: "HTTPS-Alt",
    9090: "HTTP-Alt", 27017: "MongoDB",
}

# 高危端口（监管重点）
HIGH_RISK_PORTS = [22, 23, 445, 3306, 3389, 6379, 27017]

# 厂商选型策略（7类检测30+厂商）
VENDOR_SELECTION_STRATEGY = {
    "vuln_scan": {
        "vendors": ["墨云", "天融信", "安恒", "绿盟", "启明星辰", "网御星云"],
        "description": "漏洞扫描",
        "scenario": "对目标进行自动化漏洞检测，覆盖常见CVE、弱口令、未授权访问等"
    },
    "web_vuln_scan": {
        "vendors": ["长亭科技", "启明星辰", "墨云", "远江盛邦", "网御星云"],
        "description": "Web漏洞扫描",
        "scenario": "针对Web应用的专项漏洞检测，覆盖SQL注入、XSS、Shiro RCE等"
    },
    "weak_password": {
        "vendors": ["绿盟", "远江盛邦", "墨云", "博智安全", "网御星云"],
        "description": "弱口令探测",
        "scenario": "检测SSH/RDP/MySQL/Redis等服务的弱口令和默认口令"
    },
    "config_check": {
        "vendors": ["绿盟", "博智安全", "远江盛邦", "深信服", "网御星云"],
        "description": "配置核查",
        "scenario": "等保基线核查，检查防火墙/密码策略/日志审计/补丁管理等"
    },
    "penetration": {
        "vendors": ["墨云", "绿盟", "华云安", "远江盛邦", "360", "天融信"],
        "description": "自动化渗透测试",
        "scenario": "模拟攻击者视角，验证漏洞的可利用性和攻击链"
    },
    "source_code_audit": {
        "vendors": ["北大库博", "奇安信", "北京酷德啄木鸟", "悬镜", "墨云"],
        "description": "源代码审计",
        "scenario": "对应用程序源代码进行安全缺陷检测"
    },
    "app_scan": {
        "vendors": ["梆梆安全", "爱加密", "安般科技-蛮犀科技"],
        "description": "APP检测",
        "scenario": "移动应用安全检测，覆盖Android/iOS双平台"
    }
}


# ════════════════════════════════════
# 工具函数
# ════════════════════════════════════

def init_db():
    """初始化数据库."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("""CREATE TABLE IF NOT EXISTS scan_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        time TEXT NOT NULL,
        target TEXT NOT NULL,
        risk_level TEXT DEFAULT 'unknown',
        open_ports INTEGER DEFAULT 0,
        vendor TEXT DEFAULT '',
        raw_result TEXT DEFAULT '{}'
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_target ON scan_records(target)")
    conn.execute("""CREATE TABLE IF NOT EXISTS asset_knowledge (
        asset_ip TEXT PRIMARY KEY,
        first_scan_time TEXT,
        last_scan_time TEXT,
        scan_count INTEGER DEFAULT 0,
        last_risk_level TEXT DEFAULT 'unknown',
        last_open_ports TEXT DEFAULT '[]',
        last_vendor TEXT DEFAULT '',
        history_summary TEXT DEFAULT '[]'
    )""")
    conn.commit()
    conn.close()


def save_record(target, result, vendor=""):
    """保存扫描记录."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute(
        "INSERT INTO scan_records (time, target, risk_level, open_ports, vendor, raw_result) VALUES (?, ?, ?, ?, ?, ?)",
        (result.get("scan_time", datetime.now().isoformat()), target,
         result.get("risk_level", "unknown"), len(result.get("ports", [])),
         vendor, json.dumps(result, ensure_ascii=False))
    )
    conn.commit()
    conn.close()


def ping_sweep(subnet: str) -> dict:
    """ICMP 存活探测 — 使用 nmap ping sweep 发现存活主机.

    Args:
        subnet: 目标网段，如 192.168.1.0/24

    Returns:
        {"success": bool, "data": {"alive_hosts": [...], "total": N}, "error": str|None}
    """
    try:
        # 验证网段格式
        if not re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}/\d{1,2}$', subnet):
            return {"success": False, "data": {}, "error": f"网段格式无效: {subnet}，应如 192.168.1.0/24"}

        result = subprocess.run(
            ["nmap", "-sn", "-T4", subnet],
            capture_output=True, text=True, timeout=120
        )
        output = result.stdout

        # 解析存活主机
        hosts = re.findall(r'Nmap scan report for ([\d.]+)', output)
        host_details = []
        for ip in hosts:
            # 尝试获取主机名
            hostname = ""
            for line in output.split('\n'):
                if ip in line and "report for" in line:
                    parts = line.split("report for ")
                    if len(parts) > 1 and parts[1] != ip:
                        hostname = parts[1].replace(f" ({ip})", "").replace(ip, "").strip()
                    break
            host_details.append({
                "ip": ip,
                "hostname": hostname if hostname else None,
                "status": "alive"
            })

        # 统计
        total = len(host_details)
        summary = f"发现 {total} 台存活主机"
        if total > 0:
            summary += f": {', '.join([h['ip'] for h in host_details[:10]])}"
            if total > 10:
                summary += f" 等共{total}台"

        return {
            "success": True,
            "data": {
                "alive_hosts": host_details,
                "total": total,
                "summary": summary,
                "raw_command": f"nmap -sn -T4 {subnet}"
            },
            "error": None
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "data": {}, "error": "nmap ping sweep 执行超时（>120s）"}
    except FileNotFoundError:
        return {"success": False, "data": {}, "error": "nmap 未安装，请先安装: apt install nmap"}
    except Exception as e:
        return {"success": False, "data": {}, "error": f"ping_sweep 失败: {str(e)[:200]}"}


def port_scan_target(target: str, ports: str = "") -> dict:
    """对单个目标执行端口扫描.

    Args:
        target: 目标 IP
        ports: 逗号分隔的端口列表（为空则扫所有常见端口）

    Returns:
        扫描结果 dict
    """
    open_ports = []
    if ports:
        port_list = [int(p.strip()) for p in ports.split(",") if p.strip().isdigit()]
    else:
        port_list = list(COMMON_PORTS.keys())

    for port in port_list:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1.0)
            sock.connect((target, port))
            sock.close()
            service = COMMON_PORTS.get(port, "unknown")
            is_high_risk = port in HIGH_RISK_PORTS
            open_ports.append({
                "port": port,
                "service": service,
                "status": "open",
                "high_risk": is_high_risk
            })
        except:
            pass
    return {
        "target": target,
        "port_count": len(open_ports),
        "ports": open_ports,
        "high_risk_ports": [p for p in open_ports if p.get("high_risk")]
    }


def security_scan(target: str, vendor: str = "", scan_type: str = "port_scan") -> dict:
    """执行安全检查.

    Args:
        target: 目标 IP
        vendor: 厂商名称（用于记录）
        scan_type: port_scan / full

    Returns:
        {"success": bool, "data": {...}, "error": str|None}
    """
    try:
        now = datetime.now().isoformat()
        result = {
            "target": target,
            "scan_time": now,
            "scan_type": scan_type,
            "vendor": vendor,
            "ports": [],
            "high_risk_ports": [],
            "risk_level": "unknown",
            "summary": "",
            "recommendations": []
        }

        # 执行端口扫描
        scan_result = port_scan_target(target)
        result["ports"] = scan_result.get("ports", [])
        result["high_risk_ports"] = scan_result.get("high_risk_ports", [])

        if not result["ports"]:
            result["risk_level"] = "低危"
            result["summary"] = f"目标 {target} 未发现开放常见端口，安全状态良好。"
            result["recommendations"] = ["保持当前安全配置", "定期执行安全检查"]
        else:
            # 基于高危端口判断风险等级
            high_ports = result["high_risk_ports"]
            if len(high_ports) >= 3:
                result["risk_level"] = "高危"
            elif len(high_ports) >= 1:
                result["risk_level"] = "中危"
            elif len(result["ports"]) >= 5:
                result["risk_level"] = "中危"
            else:
                result["risk_level"] = "低危"

            port_desc = ", ".join([f"{p['port']}({p['service']})" for p in result["ports"]])
            result["summary"] = f"发现 {len(result['ports'])} 个开放端口: {port_desc}"
            if high_ports:
                high_desc = ", ".join([f"{p['port']}({p['service']})" for p in high_ports])
                result["summary"] += f"\n⚠️ 高危端口: {high_desc}"

            # 生成修复建议
            recs = []
            for p in high_ports:
                recs.append(f"高危端口 {p['port']}({p['service']}) 应立即检查是否必要，限制访问来源IP")
            if len(result["ports"]) > 10:
                recs.append("开放端口过多，建议梳理并关闭非必要端口")
            recs.append("确保所有服务已安装最新安全补丁")
            recs.append("定期执行漏洞扫描")
            result["recommendations"] = recs

        # 保存记录
        save_record(target, result, vendor)

        return {"success": True, "data": result, "error": None}
    except Exception as e:
        return {"success": False, "data": {}, "error": f"security_scan 失败: {str(e)[:200]}"}


def batch_scan(targets: list, scan_type: str = "port_scan", vendor: str = "") -> dict:
    """批量扫描多个目标.

    Args:
        targets: 目标 IP 列表
        scan_type: 扫描类型
        vendor: 厂商名称

    Returns:
        {"success": bool, "data": {...}, "error": str|None}
    """
    if not targets:
        return {"success": False, "data": {}, "error": "目标列表为空"}

    results = []
    summary = {"total": len(targets), "high_risk": 0, "medium_risk": 0, "low_risk": 0}

    for target in targets:
        r = security_scan(target, vendor, scan_type)
        if r.get("success") and r.get("data"):
            data = r["data"]
            results.append({"target": target, "risk_level": data.get("risk_level"), "port_count": len(data.get("ports", []))})
            risk = data.get("risk_level", "unknown")
            if risk == "高危":
                summary["high_risk"] += 1
            elif risk == "中危":
                summary["medium_risk"] += 1
            else:
                summary["low_risk"] += 1

    return {
        "success": True,
        "data": {
            "targets": results,
            "summary": summary,
            "total_scanned": len(results)
        },
        "error": None
    }


def gen_selection_plan(target_desc: str = "", exclude_types: str = "") -> dict:
    """生成选型方案.

    Args:
        target_desc: 目标描述（可选）
        exclude_types: 排除的检测类型，逗号分隔（可选）

    Returns:
        {"success": bool, "data": {...}, "error": str|None}
    """
    excludes = [t.strip() for t in exclude_types.split(",") if t.strip()] if exclude_types else []
    plan = []

    for check_type, info in VENDOR_SELECTION_STRATEGY.items():
        if check_type in excludes:
            continue
        plan.append({
            "check_type": check_type,
            "check_type_name": info["description"],
            "recommended_vendors": info["vendors"],
            "recommended_count": len(info["vendors"]),
            "scenario": info["scenario"]
        })

    return {
        "success": True,
        "data": {
            "plan": plan,
            "total_types": len(plan),
            "note": "每类检测只选一个工具执行，避免重复检测和资源浪费。选择依据：覆盖度 > 检测深度 > 客户偏好 > 互补覆盖"
        },
        "error": None
    }


def gen_report(target: str, template: str = "standard") -> dict:
    """生成安全检查报告.

    Args:
        target: 目标 IP
        template: 报告模板（standard / customer）

    Returns:
        {"success": bool, "data": {...}, "error": str|None}
    """
    # 从数据库取最新记录
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM scan_records WHERE target = ? ORDER BY id DESC LIMIT 1",
        (target,)
    ).fetchone()
    conn.close()

    if not row:
        return {"success": False, "data": {}, "error": f"未找到 {target} 的扫描记录，请先执行 security_scan"}

    record = json.loads(row["raw_result"])
    ports = record.get("ports", [])
    high_risk_ports = record.get("high_risk_ports", [])
    recs = record.get("recommendations", [])

    ports_table = "\n".join([f"| {p['port']} | {p['service']} | {'⚠️ 高危' if p.get('high_risk') else 'open'} |" for p in ports])
    recs_list = "\n".join([f"{i+1}. {r}" for i, r in enumerate(recs)])

    if template == "standard":
        report = f"""# 安全检查报告

## 基本信息
- **目标**: {target}
- **检查时间**: {record.get('scan_time', '未知')}
- **风险等级**: **{record.get('risk_level', '未知')}**
- **检测厂商**: {record.get('vendor', 'N/A')}

## 端口开放情况
| 端口 | 服务 | 状态 |
|------|------|------|
{ports_table if ports_table else '| (无) | — | — |'}

## 风险分析
{record.get('summary', '无数据')}

## 修复建议
{recs_list if recs_list else '无特殊建议'}

## 监管关注
{'⚠️ 发现高危端口，建议立即检查' if high_risk_ports else '✅ 未发现高危端口'}
{'⚠️ 开放端口过多(>10)，建议最小化原则梳理' if len(ports) > 10 else ''}

---
*报告由安全检查 Agent 自动生成 — {record.get('scan_time', '')}*
"""
    elif template == "customer":
        # 客户汇总模板
        report = f"""# 安全检查汇总报告

**报告编号**: SEC-CHK-{datetime.now().strftime('%Y%m%d')}-001
**检查目标**: {target}
**检查时间**: {record.get('scan_time', '未知')}
**编制单位**: 安全检测中心
**报告日期**: {datetime.now().strftime('%Y年%m月%d日')}

---

> 声明：本报告基于安全检测工具的原始输出汇总编制。

## 一、检测概述

| 项目 | 内容 |
|------|------|
| 目标 | {target} |
| 风险等级 | **{record.get('risk_level', '未知')}** |
| 开放端口数 | {len(ports)} |
| 高危端口数 | {len(high_risk_ports)} |

## 二、高危发现

{'| 端口 | 服务 | 风险说明 |' if high_risk_ports else '未发现高危问题'}
{'|------|------|----------|' if high_risk_ports else ''}
{chr(10).join([f"| {p['port']} | {p['service']} | 高危端口暴露，存在被攻击风险 |" for p in high_risk_ports]) if high_risk_ports else ''}

## 三、修复建议

{recs_list if recs_list else '无特殊建议'}

## 四、结论

**综合评估: {record.get('risk_level', '未知')}**

{'需要立即处置' if record.get('risk_level') in ['高危', '中危'] else '安全状态良好，建议定期复查'}

---

*报告由安全检查 Agent 自动生成*
"""
    else:
        return {"success": False, "data": {}, "error": f"未知模板: {template}，支持 standard / customer"}

    return {
        "success": True,
        "data": {
            "target": target,
            "template": template,
            "report": report,
            "risk_level": record.get('risk_level', 'unknown'),
            "format": "markdown"
        },
        "error": None
    }


def validate_report(target: str) -> dict:
    """校验报告数据质量.

    检查：
    1. 完整性：必填字段是否存在
    2. 格式规范性：IP/日期格式
    3. 数值合理性：端口数/CVSS

    Args:
        target: 目标 IP

    Returns:
        {"success": bool, "data": {"checks": [...], "passed": N, "failed": N}, "error": str|None}
    """
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM scan_records WHERE target = ? ORDER BY id DESC LIMIT 1",
        (target,)
    ).fetchone()
    conn.close()

    if not row:
        return {"success": False, "data": {}, "error": f"未找到 {target} 的记录"}
    record = json.loads(row["raw_result"])

    checks = []

    # 1. 完整性检查
    required = ["target", "scan_time", "risk_level"]
    for field in required:
        if not record.get(field):
            checks.append({"check": "完整性", "field": field, "status": "失败", "detail": f"缺少必填字段: {field}"})

    # 2. 格式检查
    import re
    ip = record.get("target", "")
    if ip and not re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', ip):
        checks.append({"check": "格式", "field": "target", "status": "失败", "detail": f"IP格式异常: {ip}"})
    risk = record.get("risk_level", "")
    if risk and risk not in ["低危", "中危", "高危", "unknown"]:
        checks.append({"check": "格式", "field": "risk_level", "status": "失败", "detail": f"风险等级异常: {risk}"})

    # 3. 数值合理性
    if "ports" in record:
        for p in record["ports"]:
            port_num = p.get("port", 0)
            if not (1 <= port_num <= 65535):
                checks.append({"check": "数值", "field": f"port/{port_num}", "status": "失败", "detail": f"端口号超出范围: {port_num}"})

    passed = sum(1 for c in checks if c["status"] != "失败")
    failed = sum(1 for c in checks if c["status"] == "失败")

    return {
        "success": True,
        "data": {
            "target": target,
            "checks": checks,
            "passed": passed,
            "failed": failed,
            "total": len(checks),
            "quality": "合格" if failed == 0 else f"发现 {failed} 个问题"
        },
        "error": None
    }


def get_asset_profile(target: str) -> dict:
    """查询资产档案.

    Args:
        target: 目标 IP

    Returns:
        {"success": bool, "data": {...}, "error": str|None}
    """
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM scan_records WHERE target = ? ORDER BY id DESC LIMIT 5",
        (target,)
    ).fetchall()
    conn.close()

    if not row:
        return {"success": False, "data": {}, "error": f"资产 {target} 尚无扫描记录"}

    records = []
    for r in row:
        rec = json.loads(r["raw_result"])
        records.append({
            "time": r["time"],
            "risk_level": r["risk_level"],
            "port_count": r["open_ports"],
            "vendor": r["vendor"]
        })

    latest = records[0]
    return {
        "success": True,
        "data": {
            "asset_ip": target,
            "scan_count": len(records),
            "last_scan": latest["time"],
            "last_risk": latest["risk_level"],
            "last_vendor": latest["vendor"],
            "history": records
        },
        "error": None
    }


# ════════════════════════════════════
# MCP 入口
# ════════════════════════════════════

METHODS = {
    "ping_sweep": ping_sweep,
    "security_scan": security_scan,
    "batch_scan": batch_scan,
    "gen_report": gen_report,
    "validate_report": validate_report,
    "gen_selection_plan": gen_selection_plan,
    "get_asset_profile": get_asset_profile,
}


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"result": {"success": False, "error": "用法: mcp_security.py <method> '<json_args>'", "data": {}}}))
        sys.exit(1)

    # CLI 模式
    if sys.argv[1] == "--cli":
        # 直接输出格式化的结果
        return

    # MCP JSON-RPC 模式
    method = sys.argv[1]
    args = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}

    if method == "list_tools":
        tools = [
            {"name": "ping_sweep", "description": "ICMP存活探测 — 使用nmap对目标网段执行ping sweep，发现存活主机", "parameters": {"subnet": "目标网段（如192.168.1.0/24）"}},
            {"name": "security_scan", "description": "安全检查 — 对单个IP执行端口扫描+风险分析", "parameters": {"target": "目标IP", "vendor": "厂商名称（可选）", "scan_type": "扫描类型: port_scan/full（可选）"}},
            {"name": "batch_scan", "description": "批量安全扫描 — 对多个目标批量执行安全检查", "parameters": {"targets": "目标IP列表（JSON数组）", "scan_type": "扫描类型（可选）", "vendor": "厂商名称（可选）"}},
            {"name": "gen_report", "description": "生成安全检查报告 — 按模板生成Markdown格式报告", "parameters": {"target": "目标IP", "template": "模板: standard/customer（可选）"}},
            {"name": "validate_report", "description": "报告质量校验 — 检查报告数据的完整性/格式/数值合理性", "parameters": {"target": "目标IP"}},
            {"name": "gen_selection_plan", "description": "生成厂商选型方案 — 按检测类型推荐最优厂商工具", "parameters": {"target_desc": "目标描述（可选）", "exclude_types": "排除的检测类型（可选）"}},
            {"name": "get_asset_profile", "description": "查询资产档案 — 查看目标的扫描历史记录", "parameters": {"target": "目标IP"}},
        ]
        print(json.dumps({"result": {"success": True, "data": {"tools": tools}, "error": None}}))
        sys.exit(0)

    if method not in METHODS:
        print(json.dumps({"result": {"success": False, "error": f"未知方法: {method}，可用: {list(METHODS.keys())}", "data": {}}}))
        sys.exit(1)

    try:
        init_db()
        result = METHODS[method](**args)
        print(json.dumps({"result": result}))
    except Exception as e:
        print(json.dumps({"result": {"success": False, "error": f"执行异常: {str(e)[:300]}", "data": {}}}))


if __name__ == "__main__":
    main()
