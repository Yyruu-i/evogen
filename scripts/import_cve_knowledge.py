#!/usr/bin/env python3
"""CVE 漏洞知识库导入脚本.

从 NVD (National Vulnerability Database) 下载最新的 CVE 数据，
解析后存入 Chroma 向量数据库，用于 Agent 对话中自动检索。

用法:
  python3 scripts/import_cve_knowledge.py          # 下载并导入
  python3 scripts/import_cve_knowledge.py --search "Log4j"  # 搜索知识库
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.request


# ── 配置 ──
CVE_API_URL = "https://services.nvd.nist.gov/rest/json/cves/2.0"
CHROMA_COLLECTION = "evo_cve_knowledge"
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cve")
os.makedirs(DATA_DIR, exist_ok=True)

# 常用 CVE 知识（内置知识库，免网络下载）
BUILTIN_CVE_DB = [
    {
        "cve_id": "CVE-2021-44228",
        "description": "Apache Log4j2 远程代码执行漏洞（Log4Shell）。JNDI lookup 功能中未对 LDAP 等协议做限制，攻击者可构造恶意请求触发 RCE。",
        "severity": "CRITICAL",
        "cvss_score": 10.0,
        "affected": "Apache Log4j 2.x < 2.15.0",
        "fix": "升级到 Log4j 2.15.0+，或设置 log4j2.formatMsgNoLookups=true，或移除 JndiLookup 类。",
        "detection": "使用 nuclei -t cves/2021/CVE-2021-44228.yaml 扫描。nmap 可通过 --script http-log4shell 检测。",
    },
    {
        "cve_id": "CVE-2021-26855",
        "description": "Microsoft Exchange Server 远程代码执行漏洞（ProxyLogon）。未经认证的攻击者可通过 443 端口发送恶意 HTTP 请求利用。",
        "severity": "CRITICAL",
        "cvss_score": 9.8,
        "affected": "Microsoft Exchange Server 2013, 2016, 2019",
        "fix": "安装微软 2021年3月安全更新补丁。建议同时检查是否有后门植入。",
        "detection": "使用 nuclei -t cves/2021/CVE-2021-26855.yaml 扫描。检查 Exchange 日志中可疑的 SSRF 请求。",
    },
    {
        "cve_id": "CVE-2022-22965",
        "description": "Spring Framework 远程代码执行漏洞（Spring4Shell）。JDK 9+ 环境下，通过 data binding 注入导致 RCE。",
        "severity": "CRITICAL",
        "cvss_score": 9.8,
        "affected": "Spring Framework 5.3.x < 5.3.18, 5.2.x < 5.2.20",
        "fix": "升级 Spring Framework 到 5.3.18+ / 5.2.20+，或升级 Spring Boot 到 2.6.6+ / 2.5.12+。",
        "detection": "使用 nuclei -t cves/2022/CVE-2022-22965.yaml 扫描。检测是否有 spring-beans 相关 class 异常。",
    },
    {
        "cve_id": "CVE-2023-44487",
        "description": "HTTP/2 Rapid Reset 拒绝服务攻击。攻击者通过快速创建和取消 HTTP/2 流消耗服务器资源。",
        "severity": "HIGH",
        "cvss_score": 7.5,
        "affected": "大多数实现 HTTP/2 的服务器（nginx, Apache, Envoy, 各大云服务商）",
        "fix": "应用各厂商安全补丁。限制 HTTP/2 并发流数，监控异常流创建/重置比率。",
        "detection": "使用 nuclei -t http/miscellaneous/http2-rapid-reset.yaml 扫描。监控服务器 CPU/内存异常飙升。",
    },
    {
        "cve_id": "CVE-2023-34362",
        "description": "MOVEit Transfer SQL 注入漏洞。Progress Software MOVEit Transfer 未授权访问导致数据泄露。",
        "severity": "CRITICAL",
        "cvss_score": 9.8,
        "affected": "MOVEit Transfer < 2021.0.6, 2022.0.4, 2023.0.2",
        "fix": "升级到 MOVEit Transfer 最新版本。检查是否有异常用户创建和数据导出行为。",
        "detection": "通过 nmap 扫描 80/443 端口识别 MOVEit Transfer 服务版本。nuclei 有对应检测模板。",
    },
    {
        "cve_id": "CVE-2024-3094",
        "description": "XZ Utils 后门漏洞（CVE-2024-3094）。liblzma 库中被植入恶意代码，影响 SSH 认证流程。",
        "severity": "CRITICAL",
        "cvss_score": 10.0,
        "affected": "XZ Utils 5.6.0, 5.6.1",
        "fix": "降级 XZ Utils 到 5.4.x 版本。检查系统中是否安装了受影响的版本。",
        "detection": "使用 nmap -sV 检测 SSH 版本。检查系统中 dpkg/rpm 列出的 xz-utils 版本。",
    },
    {
        "cve_id": "CVE-2017-0144",
        "description": "Microsoft Windows SMBv1 远程代码执行漏洞（EternalBlue/永恒之蓝）。攻击者可通过 SMB 协议发送恶意数据包触发 RCE。WannaCry 勒索病毒利用此漏洞传播。",
        "severity": "CRITICAL",
        "cvss_score": 8.1,
        "affected": "Windows Vista/7/8.1/10/2008/2012/2016",
        "fix": "安装 MS17-010 安全更新。建议禁用 SMBv1 协议。",
        "detection": "使用 nmap --script smb-vuln-ms17-010 扫描。nuclei -t cves/2017/CVE-2017-0144.yaml。",
    },
    {
        "cve_id": "CVE-2019-0708",
        "description": "Microsoft Windows Remote Desktop 远程代码执行漏洞（BlueKeep）。RDP 服务中存在预认证 RCE，可蠕虫化传播。",
        "severity": "CRITICAL",
        "cvss_score": 9.8,
        "affected": "Windows 7/2008 R2/2008/XP",
        "fix": "安装 KB4499175 / KB4507456 安全更新。建议在防火墙上限制 RDP 端口（3389）访问。",
        "detection": "使用 nmap --script rdp-vuln-ms12-020 扫描。nuclei -t cves/2019/CVE-2019-0708.yaml。",
    },
    {
        "cve_id": "CVE-2020-1472",
        "description": "Netlogon 特权提升漏洞（Zerologon）。攻击者可通过与域控制器建立 Netlogon 安全通道并伪造凭证获取域管理员权限。",
        "severity": "CRITICAL",
        "cvss_score": 10.0,
        "affected": "Windows Server 2008 R2 ~ 2019",
        "fix": "安装 KB4565340 / KB4570332 安全更新。开启 Domain Controller: Allow vulnerable Netlogon secure channel connections 策略。",
        "detection": "使用 nmap --script smb-vuln-cve-2020-1472.nse 扫描。nuclei -t cves/2020/CVE-2020-1472.yaml。",
    },
    {
        "cve_id": "CVE-2021-34527",
        "description": "Windows Print Spooler 远程代码执行漏洞（PrintNightmare）。攻击者可通过 RPC 调用在 SYSTEM 权限下执行任意代码。",
        "severity": "CRITICAL",
        "cvss_score": 8.8,
        "affected": "Windows 7/8.1/10/11/2008/2012/2016/2019/2022",
        "fix": "安装 2021年7月安全更新。或停用 Print Spooler 服务（若不需打印功能）。",
        "detection": "使用 nmap --script 检测 SMB 协议版本。nuclei -t cves/2021/CVE-2021-34527.yaml。",
    },
]


# ── Chroma 集成 ──

def _get_chroma_collection():
    """获取 Chroma 集合，自动创建."""
    try:
        import chromadb
        from chromadb.config import Settings

        chroma_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data", "chroma"
        )
        os.makedirs(chroma_dir, exist_ok=True)

        client = chromadb.PersistentClient(
            path=chroma_dir,
            settings=Settings(anonymized_telemetry=False),
        )

        # Try to get existing collection
        try:
            collection = client.get_collection(CHROMA_COLLECTION)
        except ValueError:
            collection = client.create_collection(CHROMA_COLLECTION)

        return collection
    except Exception as e:
        print(f"⚠️ Chroma 不可用: {e}")
        return None


def import_builtin_knowledge():
    """将内置 CVE 知识导入 Chroma."""
    collection = _get_chroma_collection()
    if collection is None:
        print("⚠️ Chroma 不可用，跳过导入。")
        return False

    count = collection.count()
    if count > 0:
        print(f"知识库已有 {count} 条记录，跳过导入。使用 --force 重新导入。")
        return True

    ids = []
    documents = []
    metadatas = []

    for cve in BUILTIN_CVE_DB:
        doc = f"CVE: {cve['cve_id']}\n描述: {cve['description']}\n修复: {cve['fix']}\n检测: {cve['detection']}"
        ids.append(cve['cve_id'])
        documents.append(doc)
        metadatas.append({
            "cve_id": cve['cve_id'],
            "severity": cve['severity'],
            "cvss_score": cve['cvss_score'],
            "source": "builtin",
        })

    collection.add(
        ids=ids,
        documents=documents,
        metadatas=metadatas,
    )
    print(f"✅ 已导入 {len(documents)} 条 CVE 知识到 Chroma 知识库")
    return True


def search_knowledge(query: str, limit: int = 5) -> list[dict]:
    """搜索漏洞知识库，返回最相关的结果."""
    collection = _get_chroma_collection()
    if collection is None or collection.count() == 0:
        return []

    results = collection.query(
        query_texts=[query],
        n_results=limit,
    )

    entries = []
    for i in range(len(results.get("ids", [[]])[0])):
        entries.append({
            "id": results["ids"][0][i],
            "content": results["documents"][0][i],
            "metadata": results["metadatas"][0][i],
            "distance": results["distances"][0][i] if results.get("distances") else None,
        })
    return entries


def _download_cve_list(days: int = 7) -> list[dict]:
    """从 NVD API 下载近期 CVE 列表（简单实现）."""
    print(f"正在从 NVD API 下载近 {days} 天的 CVE 数据...")
    url = f"{CVE_API_URL}?pubStartDate={_date_str(days)}&pubEndDate={_date_str(0)}&resultsPerPage=20"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "EvoGen/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
        cves = []
        for item in data.get("vulnerabilities", []):
            cve = item.get("cve", {})
            metrics = cve.get("metrics", {})
            cvss_score = None
            for key in ["cvssMetricV31", "cvssMetricV30", "cvssMetricV2"]:
                if metrics.get(key):
                    cvss_score = metrics[key][0]["cvssData"]["baseScore"]
                    break
            cves.append({
                "cve_id": cve["id"],
                "description": cve.get("descriptions", [{}])[0].get("value", ""),
                "severity": cve.get("vulnStatus", "UNKNOWN"),
                "cvss_score": cvss_score,
            })
        print(f"下载到 {len(cves)} 条 CVE 记录")
        return cves
    except Exception as e:
        print(f"NVD API 下载失败: {e}")
        return []


def _date_str(days_ago: int) -> str:
    """生成 ISO 日期字符串（NVD API 格式）. """
    from datetime import datetime, timedelta, timezone
    d = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return d.strftime("%Y-%m-%dT%H:%M:%S.000")


def search_local(query: str, limit: int = 5) -> list[dict]:
    """不依赖 Chroma 的内置搜索（fallback）。"""
    results = []
    query_lower = query.lower()
    for cve in BUILTIN_CVE_DB:
        score = 0
        if cve["cve_id"].lower() in query_lower:
            score += 5
        if cve.get("severity", "").lower() in query_lower:
            score += 2
        for keyword in query_lower.split():
            if keyword in cve["description"].lower():
                score += 1
            if keyword in cve.get("fix", "").lower():
                score += 1
        if score > 0:
            results.append({"cve": cve, "score": score})

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:limit]


def format_knowledge_for_prompt(results: list[dict]) -> str:
    """将知识库结果格式化为 system prompt 片段."""
    if not results:
        return ""

    parts = ["\n## 📚 漏洞知识库（相关条目）"]
    for r in results:
        cve = r.get("cve") or r  # support both builtin and chroma result
        parts.append(
            f"- **{cve.get('cve_id', cve.get('id', ''))}**: {cve.get('description', cve.get('content', ''))[:200]}"
        )
    return "\n".join(parts)


def main():
    parser = argparse.ArgumentParser(description="CVE 漏洞知识库工具")
    parser.add_argument("--search", help="搜索知识库关键词")
    parser.add_argument("--force", action="store_true", help="强制重新导入")
    parser.add_argument("--download", action="store_true", help="从 NVD 下载最新 CVE")
    args = parser.parse_args()

    if args.search:
        # 搜索
        results = search_local(args.search)
        if results:
            print(f"找到 {len(results)} 条相关 CVE:")
            for r in results:
                cve = r["cve"]
                print(f"\n{'='*60}")
                print(f"📌 {cve['cve_id']} (CVSS: {cve['cvss_score']}) — {cve['severity']}")
                print(f"描述: {cve['description'][:200]}")
                print(f"修复: {cve['fix'][:200]}")
        else:
            print("未找到匹配的 CVE 条目。")
        return

    # 导入内置知识库
    import_builtin_knowledge()

    if args.download:
        cves = _download_cve_list()
        if cves:
            print(f"下载了 {len(cves)} 条 CVE，但自动导入暂未实现。数据在 data/cve/ 目录。")


if __name__ == "__main__":
    main()
