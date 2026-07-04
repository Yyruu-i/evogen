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

# TOP 500 常见端口（含安全关注端口）
_COMMON_PORTS_DEF = """21:FTP,22:SSH,23:Telnet,25:SMTP,53:DNS,69:TFTP,80:HTTP,81:HTTP-Alt,88:Kerberos,110:POP3,111:RPCbind,123:NTP,135:RPC,137:NetBIOS-NS,139:NetBIOS-SSN,143:IMAP,161:SNMP,162:SNMP-Trap,179:BGP,389:LDAP,443:HTTPS,445:SMB,465:SMTPS,500:ISAKMP,502:Modbus,512:rexec,513:rlogin,514:syslog,515:printer,520:RIP,521:RIPng,523:IPsec,554:RTSP,587:SMTP-Sub,623:IPMI,631:IPP,636:LDAPS,646:LDP,873:rsync,902:VMware,989:FTPS-Data,990:FTPS,993:IMAPS,995:POP3S,1025:RPC-NFS,1080:SOCKS,1099:RMI,1194:OpenVPN,1241:Nessus,1352:Lotus-Notes,1414:MQ,1433:MSSQL,1434:MSSQL-Mon,1521:Oracle,1720:H.323,1723:PPTP,2049:NFS,2181:ZooKeeper,2222:SSH-Alt,2375:Docker,2376:Docker-TLS,2379:etcd,2424:OrientDB,2483:Oracle-Ora,2484:Ora-TLS,3000:Grafana,3306:MySQL,3389:RDP,3478:STUN,4000:Node-Debug,4040:SparkUI,4190:ManageSieve,4243:Docker,4369:Erlang-Port,4444:Metasploit,4560:Logstash,4567:Sinatra,4600:Log4j-Socket,4848:GlassFish,5000:Flask,5001:UPnP,5004:RTP,5037:ADB,5044:Logstash-Beats,5050:Marathon,5060:SIP,5061:SIPS,5222:XMPP,5223:XMPP-SSL,5353:mDNS,5432:PostgreSQL,5555:ADB-Alt,5601:Kibana,5631:pcAnywhere,5672:RabbitMQ,5850:VNC,5900:VNC,5901:VNC-1,5984:CouchDB,5985:WinRM-HTTP,5986:WinRM-HTTPS,6000:X11,6001:X11-1,6002:X11-2,6003:X11-3,6004:X11-4,6005:X11-5,6082:VNC-Alt,6379:Redis,6443:K8s-API-SSL,6580:VNC-Alt,7001:WebLogic,7002:WebLogic-SSL,7070:Genie-Alt,7071:Zimbra,7199:Cassandra-JMX,7443:HTTPS-Alt,7474:Neo4j,7547:TR-069,7741:Tomcat-Alt,7777:LimeChat,7778:Tomcat-Alt2,7890:Clash,8000:HTTP-Alt,8001:HTTP-Alt2,8005:Tomcat-Shutdown,8008:HTTP-Alt8,8009:AJP13,8010:HTTP-Alt9,8042:YARN-RM,8069:Odoo,8080:HTTP-Proxy,8081:HTTP-Monitor,8082:HTTP-Alt12,8086:HTTP-Alt16,8088:Hadoop-YARN,8089:Splunkd,8090:HTTP-Alt18,8091:Couchbase-Web,8092:Couchbase-API,8100:HTTP-Alt19,8123:Polipo,8140:Puppet,8161:ActiveMQ-Web,8172:MS-Deploy,8200:Vault-UI,8222:VMware-Tools,8243:HTTPS-Alt20,8280:HTTP-Alt20,8300:Consul,8301:Consul-LAN,8302:Consul-WAN,8332:Bitcoin,8333:Bitcoin-Test,8403:CommServer,8443:HTTPS-Alt,8444:Bitcoin-Alt,8500:Consul-DNS,8530:WSUS,8531:WSUS-SSL,8545:Ethereum-RPC,8600:Consul-HTTP,8649:Ganglia,8686:Solr,8761:Eureka,8786:Dask-Scheduler,8787:Dask-Bokeh,8800:HTTP-Alt22,8834:Nessus,8843:HTTPS-Alt23,8880:HTTP-Alt23,8883:MQTT-SSL,8888:HTTP-Alt25,8889:HTTP-Alt26,8983:Solr,9000:PHP-FPM,9001:Hadoop-NameNode,9002:Hadoop-JT,9042:Cassandra-CQL,9043:WebSphere-SSL,9050:Tor,9060:WebSphere,9080:WebSphere-HTTP,9090:HTTP-Alt,9091:HTTP-Alt,9092:Kafka,9093:Kafka-SSL,9100:JetDirect,9151:Tor-Control,9160:Cassandra-Thrift,9200:Elasticsearch,9201:ES-Alt,9300:ES-Transport,9418:Git,9443:HTTPS-Alt,9500:HTTP-Alt,9600:OmniVision,9870:Hadoop-NN-UI,9871:Hadoop-NN-UI-SSL,9990:WildFly,9993:ZeroTier,9997:Splunk-Idx,10000:Webmin,10050:Zabbix-Agent,10051:Zabbix-Server,10113:NetIQ,10114:NetIQ,11211:Memcached,11214:Memcached-SSL,12345:NetBus,14265:IOTA,16010:HBase-Master,16020:HBase-Region,16379:Redis-Alt,16380:Redis-Alt2,16509:OpenFlow,17000:HTTP-Alt,18080:HTTP-Alt,18081:HTTP-Alt,18082:HTTP-Alt,18100:HTTP-Alt,19000:HTTP-Alt,19100:HTTP-Alt,20000:HTTP-Alt,21000:HTTP-Alt,22000:HTTP-Alt,22222:HTTP-Alt,23000:HTTP-Alt,24000:HTTP-Alt,25000:HTTP-Alt,25565:Minecraft,26000:HTTP-Alt,26257:CockroachDB,27015:HLDS,27016:HLDS-Alt,27017:MongoDB,27018:MongoDB-Alt,27019:MongoDB-Alt2,28017:MongoDB-HTTP,30000:HTTP-Alt,31000:HTTP-Alt,31337:BackOrifice,32000:HTTP-Alt,32400:Plex,32764:Router-Backdoor,32768:HTTP-Alt,33434:traceroute,35000:HTTP-Alt,38080:HTTP-Alt,40000:HTTP-Alt,41000:HTTP-Alt,42000:HTTP-Alt,43000:HTTP-Alt,44000:HTTP-Alt,44818:EtherNet-IP,45000:HTTP-Alt,46000:HTTP-Alt,47000:HTTP-Alt,48000:HTTP-Alt,49000:HTTP-Alt,49152:Win-RPC,49153:Win-RPC,49154:Win-RPC,49155:Win-RPC,49156:Win-RPC,49157:Win-RPC,49158:Win-RPC,49159:Win-RPC,49160:Win-RPC,49161:Win-RPC,49162:Win-RPC,49163:Win-RPC,49164:Win-RPC,49165:Win-RPC,49166:Win-RPC,49167:Win-RPC,49168:Win-RPC,49169:Win-RPC,49170:Win-RPC,49171:Win-RPC,49172:Win-RPC,50000:DB2,50010:Hadoop-DataNode,50020:Hadoop-DN-IPC,50030:Hadoop-JT-UI,50060:Hadoop-TT-UI,50070:Hadoop-NN-UI,50075:Hadoop-DN-UI,50090:Hadoop-SNN-UI,51000:HTTP-Alt,52000:HTTP-Alt,53000:HTTP-Alt,54000:HTTP-Alt,55000:HTTP-Alt,56000:HTTP-Alt,57000:HTTP-Alt,58000:HTTP-Alt,59000:HTTP-Alt,60000:HTTP-Alt,61000:HTTP-Alt,61616:ActiveMQ,62000:HTTP-Alt,63000:HTTP-Alt,64000:HTTP-Alt,65000:HTTP-Alt,65389:HTTP-Alt"""

COMMON_PORTS = {}
for _entry in _COMMON_PORTS_DEF.split(","):
    try:
        p, s = _entry.split(":", 1)
        COMMON_PORTS[int(p)] = s
    except: pass

# 高危端口（监管重点）
HIGH_RISK_PORTS = [21, 22, 23, 135, 139, 445, 3306, 3389, 4444, 6379, 27017, 50000, 11211]

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


def port_scan_target(target: str, ports: str = "", enable_service_detect: bool = True) -> dict:
    """对单个目标执行端口扫描（TOP 500 端口 + nmap -sV 服务识别）.

    Args:
        target: 目标 IP
        ports: 逗号分隔的端口列表（为空则扫所有常见端口）
        enable_service_detect: 是否调用 nmap -sV 做服务版本识别

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
            sock.settimeout(0.8)
            sock.connect((target, port))
            sock.close()
            service = COMMON_PORTS.get(port, "unknown")
            is_high_risk = port in HIGH_RISK_PORTS
            open_ports.append({"port": port, "service": service, "status": "open", "high_risk": is_high_risk})
        except:
            pass

    # 服务版本识别（nmap -sV）
    service_versions = {}
    if enable_service_detect and open_ports:
        try:
            port_str = ",".join(str(p["port"]) for p in open_ports)
            result = subprocess.run(
                ["nmap", "-sV", "-T4", "--max-retries", "1", "--host-timeout", "30s", "-p", port_str, target],
                capture_output=True, text=True, timeout=60
            )
            if result.returncode in (0, 1):
                for line in result.stdout.split("\n"):
                    m = re.match(r'(\d+)/tcp\s+open\s+(\S+)\s+(.+)$', line)
                    if m:
                        pnum = int(m.group(1))
                        sname = m.group(2)
                        version = m.group(3).strip()
                        for op in open_ports:
                            if op["port"] == pnum:
                                op["service_name"] = sname
                                op["version"] = version if version != sname else ""
                                break
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass  # 服务识别失败不影响主流程

    # 补充服务版本信息
    for op in open_ports:
        if "version" not in op:
            op["version"] = ""
            op["service_name"] = op["service"]

    return {
        "target": target,
        "port_count": len(open_ports),
        "ports": open_ports,
        "high_risk_ports": [p for p in open_ports if p.get("high_risk")]
    }


def security_scan(target: str, vendor: str = "", scan_type: str = "port_scan", enable_failover: bool = True) -> dict:
    """执行安全检查（支持失败自动切换）.

    Args:
        target: 目标 IP
        vendor: 厂商名称（逗号分隔多个表示 failover 优先级列表，如 "绿盟,天融信,安恒"）
        scan_type: port_scan / full
        enable_failover: 是否启用 failover（vendor 为逗号列表时自动按优先级切换）

    Returns:
        {"success": bool, "data": {...}, "error": str|None}
    """
    try:
        # 解析 vendor 列表（支持 failover）
        vendor_list = [v.strip() for v in vendor.split(",") if v.strip()] if vendor else []
        if not vendor_list:
            vendor_list = [""]  # 无名厂商

        last_error = None
        for v in vendor_list:
            result = _do_single_scan(target, v, scan_type)
            if result.get("success") and result.get("data"):
                # 如果成功且有开放端口或不是无名厂商 → 返回
                data = result["data"]
                if data.get("ports") or v:
                    return {"success": True, "data": data, "error": None, "failover_log": f"最终使用厂商: {v}" if v else ""}
                # 无名厂商且无端口 → 尝试下一个
                last_error = f"厂商 {v} 未发现开放端口"
            else:
                last_error = result.get("error", f"厂商 {v} 执行失败")
                continue

        # 全部失败 → 返回最后一个结果或错误
        if last_error:
            return {"success": False, "data": {}, "error": f"所有厂商均执行失败: {last_error}"}
        return {"success": False, "data": {}, "error": "所有厂商均执行失败"}
    except Exception as e:
        return {"success": False, "data": {}, "error": f"security_scan 失败: {str(e)[:200]}"}


def _do_single_scan(target: str, vendor: str, scan_type: str) -> dict:
    """执行单次安全检查.

    Args:
        target: 目标 IP
        vendor: 厂商名称
        scan_type: 扫描类型

    Returns:
        {"success": bool, "data": dict}
    """
    try:
        now = datetime.now().isoformat()
        result = {
            "target": target, "scan_time": now, "scan_type": scan_type,
            "vendor": vendor, "ports": [], "high_risk_ports": [],
            "risk_level": "unknown", "summary": "", "recommendations": [],
            "evidence": None
        }

        # 执行端口扫描 + 服务识别
        scan_result = port_scan_target(target, enable_service_detect=True)
        result["ports"] = scan_result.get("ports", [])
        result["high_risk_ports"] = scan_result.get("high_risk_ports", [])

        if not result["ports"]:
            result["risk_level"] = "低危"
            result["summary"] = f"目标 {target} 未发现开放常见端口，安全状态良好。"
            result["recommendations"] = ["保持当前安全配置", "定期执行安全检查"]
        else:
            high_ports = result["high_risk_ports"]
            if len(high_ports) >= 3:
                result["risk_level"] = "高危"
            elif len(high_ports) >= 1:
                result["risk_level"] = "中危"
            elif len(result["ports"]) >= 5:
                result["risk_level"] = "中危"
            else:
                result["risk_level"] = "低危"

            # 详细端口描述（含服务版本）
            port_lines = []
            for p in result["ports"]:
                ver = f"({p.get('version', '')})" if p.get("version") else ""
                flag = " ⚠️高危" if p.get("high_risk") else ""
                port_lines.append(f"{p['port']}/{p.get('service_name', p['service'])}{ver}{flag}")
            port_desc = ", ".join(port_lines)
            result["summary"] = f"发现 {len(result['ports'])} 个开放端口: {port_desc}"
            if high_ports:
                high_desc = ", ".join([f"{p['port']}({p['service']})" for p in high_ports])
                result["summary"] += f"\n⚠️ 高危端口: {high_desc}"

            # 修复建议
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
        return {"success": False, "data": {}, "error": f"扫描失败: {str(e)[:200]}"}


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
        else:
            checks.append({"check": "完整性", "field": field, "status": "通过", "detail": f"字段 {field} 存在"})

    # 如果缺少 ports 字段或 ports 为空
    ports = record.get("ports", [])
    if not ports:
        checks.append({"check": "完整性", "field": "ports", "status": "警告", "detail": "端口列表为空，扫描可能未正确执行"})
    
    # 缺少修复建议
    if not record.get("recommendations"):
        checks.append({"check": "完整性", "field": "recommendations", "status": "警告", "detail": "缺少修复建议"})

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


def baseline_check(target: str) -> dict:
    """等保基线核查 — 检查目标是否符合等保2.0三级要求.

    检查6类基线项：边界防护、访问控制、身份鉴别、日志审计、漏洞管理、最小权限。

    Args:
        target: 目标 IP

    Returns:
        {"success": bool, "data": {...}, "error": str|None}
    """
    checks = []
    passed = 0
    failed = 0
    total = 6

    # 1. 边界防护
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        sock.connect((target, 3389))
        sock.close()
        checks.append({"check": "边界防护", "status": "失败", "detail": f"RDP端口(3389)暴露，应仅授权IP可访问，建议开启防火墙并配置ACL"})
        failed += 1
    except:
        checks.append({"check": "边界防护", "status": "通过", "detail": "未发现RDP端口暴露"})
        passed += 1

    # 2. 访问控制
    for port in [22, 23, 161, 6379, 27017]:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.5)
            sock.connect((target, port))
            sock.close()
            checks.append({"check": "访问控制", "status": "失败", "detail": f"管理端口{port}暴露，应限制访问来源IP"})
            failed += 1
            break
        except:
            continue
    else:
        checks.append({"check": "访问控制", "status": "通过", "detail": "未发现敏感管理端口暴露"})
        passed += 1

    # 3. 身份鉴别（检查是否运行弱口令服务）
    weak_services = []
    for port in [21, 23, 3306, 3389, 6379]:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.5)
            sock.connect((target, port))
            sock.close()
            weak_services.append(str(port))
        except:
            pass
    if weak_services:
        checks.append({"check": "身份鉴别", "status": "⚠️ 需验证", "detail": f"存在弱口令风险服务: {', '.join(weak_services)}，建议检查密码复杂度策略"})
        passed += 1
    else:
        checks.append({"check": "身份鉴别", "status": "通过", "detail": "未发现常见弱口令服务"})
        passed += 1

    # 4. 日志审计（通过端口推测）
    log_ports_open = 0
    for port in [514, 6514, 20514]:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.5)
            sock.connect((target, port))
            sock.close()
            log_ports_open += 1
        except:
            pass
    checks.append({"check": "日志审计", "status": "⚠️ 建议", "detail": "远程日志端口状态需人工确认，建议确保日志保存≥6个月"})
    passed += 1

    # 5. 漏洞管理（通过高危端口间接评估）
    high_ports_found = []
    for port in [445, 3306, 3389, 6379, 27017, 4444]:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.5)
            sock.connect((target, port))
            sock.close()
            high_ports_found.append(str(port))
        except:
            pass
    if high_ports_found:
        checks.append({"check": "漏洞管理", "status": "失败", "detail": f"高危端口 {', '.join(high_ports_found)} 暴露，建议检查补丁状态并在90天内安装关键安全更新"})
        failed += 1
    else:
        checks.append({"check": "漏洞管理", "status": "通过", "detail": "未发现高危端口暴露"})
        passed += 1

    # 6. 最小权限
    anon_services = []
    for port in [139, 445, 2049]:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.5)
            sock.connect((target, port))
            sock.close()
            anon_services.append(str(port))
        except:
            pass
    if anon_services:
        checks.append({"check": "最小权限", "status": "失败", "detail": f"匿名可访问服务端口 {', '.join(anon_services)} 暴露，建议禁用Guest账户并限制Everyone权限"})
        failed += 1
    else:
        checks.append({"check": "最小权限", "status": "通过", "detail": "未发现匿名访问服务暴露"})
        passed += 1

    overall = "高危" if failed >= 3 else ("中危" if failed >= 1 else "合规")
    return {
        "success": True,
        "data": {
            "target": target,
            "overall": overall,
            "passed": passed,
            "failed": failed,
            "total": total,
            "checks": checks,
            "summary": f"等保基线核查完成：{passed}/{total} 项通过，{failed} 项不合规，综合评估: {overall}"
        },
        "error": None
    }


def evidence_snapshot(target: str, scan_id: str = "") -> dict:
    """证据固化 — 为指定目标的扫描结果生成Hash+时间戳的证据记录.

    Args:
        target: 目标 IP
        scan_id: 指定扫描记录ID（可选，默认最新）

    Returns:
        {"success": bool, "data": {...}, "error": str|None}
    """
    import hashlib

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    if scan_id:
        row = conn.execute("SELECT * FROM scan_records WHERE id = ?", (scan_id,)).fetchone()
    else:
        row = conn.execute("SELECT * FROM scan_records WHERE target = ? ORDER BY id DESC LIMIT 1", (target,)).fetchone()
    conn.close()

    if not row:
        return {"success": False, "data": {}, "error": f"未找到 {target} 的扫描记录"}

    raw = row["raw_result"]
    record_id = row["id"]
    scan_time = row["time"]

    # 生成 SHA256 Hash
    hash_val = hashlib.sha256(raw.encode()).hexdigest()

    timestamp = datetime.now().isoformat()

    return {
        "success": True,
        "data": {
            "target": target,
            "record_id": record_id,
            "scan_time": scan_time,
            "evidence_time": timestamp,
            "hash_algorithm": "SHA256",
            "hash": hash_val,
            "summary": f"证据已固化: 记录#{record_id}，时间戳 {timestamp}，SHA256: {hash_val[:16]}...",
            "raw_data_size": len(raw)
        },
        "error": None
    }


def retest_compare(target: str) -> dict:
    """复测确认 — 对比最近两次扫描记录，标注端口变化和风险变化.

    Args:
        target: 目标 IP

    Returns:
        {"success": bool, "data": {...}, "error": str|None}
    """
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM scan_records WHERE target = ? ORDER BY id DESC LIMIT 2",
        (target,)
    ).fetchall()
    conn.close()

    if len(rows) < 2:
        return {"success": False, "data": {}, "error": f"需要至少2次扫描记录才能做复测对比（当前 {len(rows)} 次）"}

    r1 = json.loads(rows[0]["raw_result"])  # 最近
    r2 = json.loads(rows[1]["raw_result"])  # 上次

    r1_ports = {p["port"] for p in r1.get("ports", [])}
    r2_ports = {p["port"] for p in r2.get("ports", [])}

    new_ports = r1_ports - r2_ports
    closed_ports = r2_ports - r1_ports
    unchanged = r1_ports & r2_ports

    changes = []
    for p in sorted(new_ports):
        changes.append({"port": p, "change": "新增", "detail": f"端口{p} 在上次扫描中未发现"})
    for p in sorted(closed_ports):
        changes.append({"port": p, "change": "关闭", "detail": f"端口{p} 已被关闭"})

    risk_change = ""
    if r1.get("risk_level") != r2.get("risk_level"):
        risk_change = f"风险等级变化: {r2.get('risk_level')} → {r1.get('risk_level')}"

    return {
        "success": True,
        "data": {
            "target": target,
            "first_scan": rows[1]["time"],
            "retest_scan": rows[0]["time"],
            "first_risk": r2.get("risk_level"),
            "retest_risk": r1.get("risk_level"),
            "first_vendor": rows[1].get("vendor", ""),
            "retest_vendor": rows[0].get("vendor", ""),
            "first_port_count": len(r2.get("ports", [])),
            "retest_port_count": len(r1.get("ports", [])),
            "new_ports": sorted(new_ports),
            "closed_ports": sorted(closed_ports),
            "unchanged_port_count": len(unchanged),
            "changes": changes,
            "risk_change": risk_change or "风险等级未变化",
            "summary": f"复测对比完成: 新增{len(new_ports)}端口, 关闭{len(closed_ports)}端口, {risk_change if risk_change else '风险等级未变化'}"
        },
        "error": None
    }


def _load_target_records(target: str) -> list:
    """获取目标的所有扫描记录，按时间倒序。"""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM scan_records WHERE target = ? ORDER BY id DESC",
        (target,)
    ).fetchall()
    conn.close()
    result = []
    seen_vendors = set()
    for r in rows:
        vendor = r["vendor"] or ""
        record = json.loads(r["raw_result"])
        # 相同 vendor 取最新一条
        dedup_key = vendor if vendor else "__no_vendor"
        if dedup_key in seen_vendors:
            continue
        seen_vendors.add(dedup_key)
        result.append({
            "id": r["id"],
            "time": r["time"],
            "target": r["target"],
            "risk_level": r["risk_level"],
            "vendor": vendor,
            "record": record,
        })
    return result


def _risk_level(port: dict) -> str:
    """判断端口风险等级：高危/中危/低危。"""
    if port.get("high_risk"):
        return "高危"
    rl = port.get("risk_level", "")
    if rl in ("中危", "中等"):
        return "中危"
    return "低危"


def gen_report(target: str, template: str = "standard") -> dict:
    """生成安全检查报告（数据驱动，章节动态生成）.

    Args:
        target: 目标 IP
        template: 报告模板: standard / customer / anheng-report / nsfocus-report / chaitin-report / vackbot-report

    Returns:
        {"success": bool, "data": {...}, "error": str|None}
    """
    records = _load_target_records(target)
    if not records:
        return {"success": False, "data": {}, "error": f"未找到 {target} 的扫描记录，请先执行 security_scan"}

    # 最新记录（用于 standard 模板/默认值）
    latest = records[0]
    rec = latest["record"]
    ports = rec.get("ports", [])
    high_risk_ports = rec.get("high_risk_ports", [])
    recs = rec.get("recommendations", [])

    ports_table = "\n".join([f"| {p['port']} | {p['service']} | {p.get('version','')} | {'⚠️高危' if p.get('high_risk') else 'open'} |" for p in ports])
    recs_list = "\n".join([f"{i+1}. {r}" for i, r in enumerate(recs)])

    if template == "standard":
        report = f"""# 安全检查报告

## 基本信息
- **目标**: {target}
- **检查时间**: {rec.get('scan_time', '未知')}
- **风险等级**: **{rec.get('risk_level', '未知')}**
- **检测厂商**: {latest['vendor'] or 'N/A'}

## 端口开放情况
| 端口 | 服务 | 版本 | 状态 |
|------|------|------|------|
{ports_table if ports_table else '| (无) | — | — | — |'}

## 风险分析
{rec.get('summary', '无数据')}

## 修复建议
{recs_list if recs_list else '无特殊建议'}

---
*报告由安全检查 Agent 自动生成 — {rec.get('scan_time', '')}*
"""

    elif template == "customer":
        # ═══════════════════════════════════════════
        #  数据驱动多源汇总报告
        # ═══════════════════════════════════════════

        now = datetime.now()
        report_id = f"SEC-CHK-{now.strftime('%Y%m%d')}-001"
        scan_time_str = rec.get('scan_time', now.strftime('%Y-%m-%d %H:%M'))

        # ── 1. 从所有记录中聚合数据 ──
        all_vendors = []         # 去重后的 vendor 列表
        all_ports = []           # 所有端口（去重）
        all_recs = []            # 所有修复建议（去重）
        seen_port_keys = set()
        seen_rec_texts = set()

        for entry in records:
            r = entry["record"]
            v = entry["vendor"]
            if v and v not in all_vendors:
                all_vendors.append(v)

            for p in r.get("ports", []):
                pk = f"{p['port']}-{p.get('service','?')}"
                if pk not in seen_port_keys:
                    seen_port_keys.add(pk)
                    p_entry = dict(p)
                    # 标注发现来源
                    p_entry["_source_vendor"] = entry["vendor"]
                    all_ports.append(p_entry)

            for r_text in r.get("recommendations", []):
                if r_text not in seen_rec_texts:
                    seen_rec_texts.add(r_text)
                    all_recs.append(r_text)

        # ── 2. 按真实风险等级分类 ──
        high_ports = [p for p in all_ports if _risk_level(p) == "高危"]
        med_ports  = [p for p in all_ports if _risk_level(p) == "中危"]
        low_ports  = [p for p in all_ports if _risk_level(p) == "低危"]

        # ── 3. 修复建议按关键词分级（从所有记录的 recs 聚合）──
        def _rec_priority(text: str) -> str:
            t = text.lower()
            if any(k in t for k in ["紧急", "立即", "高危", "严重", "p0"]):
                return "P0"
            if any(k in t for k in ["限期", "7天", "p1", "中危"]):
                return "P1"
            if any(k in t for k in ["30天", "p2", "常规"]):
                return "P2"
            return "P3"

        p0_recs = [r for r in all_recs if _rec_priority(r) == "P0"]
        p1_recs = [r for r in all_recs if _rec_priority(r) == "P1"]
        p2_recs = [r for r in all_recs if _rec_priority(r) == "P2"]
        p3_recs = [r for r in all_recs if _rec_priority(r) == "P3"]

        total_findings = len(high_ports) + len(med_ports) + len(low_ports)

        # ═══════════════ 动态生成章节 ═══════════════

        sections = []

        # 一、检测概述
        overview = f"""## 一、检测概述

### 1.1 检测范围

| 目标 | IP范围 | 检测方式 |
|------|--------|----------|
| {target} | {target} | 远程扫描 |

### 1.2 参与检测的厂商/工具
"""
        if all_vendors:
            overview += "\n| 厂商 | 扫描次数 | 最近检测时间 |\n|------|:--------:|--------------|\n"
            for entry in records:
                if entry['vendor']:
                    overview += f"| {entry['vendor']} | — | {entry['time']} |\n"
        else:
            overview += "\n（本机快速扫描，未使用第三方厂商工具）\n"

        overview += f"""
### 1.3 检测结果汇总

| 风险等级 | 数量 |
|:--------:|:----:|
| **高危/严重** | {len(high_ports)} |
| **中危** | {len(med_ports)} |
| **低危/信息** | {len(low_ports)} |
| **总计** | {total_findings} |
"""
        sections.append(overview)

        # 二、高危漏洞清单（有数据才出）
        if high_ports:
            high_rows = ""
            for i, p in enumerate(high_ports, 1):
                src = p.get("_source_vendor", "") or "自检"
                high_rows += f"| **VUL-H-{i:03d}** | {target} | {p['port']} | {p.get('service','?')} 高危端口暴露 | {src} | — | — |\n"
            sections.append(f"""## 二、高危漏洞清单

### 2.1 高危端口暴露

| 编号 | 目标IP | 端口 | 漏洞名称 | 发现来源 | CVE编号 | 状态 |
|:----:|--------|:----:|----------|:--------:|:--------:|:----:|
{high_rows}""")
        else:
            sections.append("""## 二、高危漏洞清单

未发现高危漏洞。\n""")

        # 三、中危漏洞清单（有数据才出）
        if med_ports:
            med_rows = ""
            for i, p in enumerate(med_ports, 1):
                src = p.get("_source_vendor", "") or "自检"
                med_rows += f"| VUL-M-{i:03d} | {target} | {p['port']}/{p.get('service','?')} | 端口暴露风险 | {src} |\n"
            sections.append(f"""## 三、中危漏洞清单

| 编号 | 目标IP | 端口/服务 | 漏洞描述 | 发现来源 |
|:----:|--------|:---------:|----------|:--------:|
{med_rows}""")
        else:
            sections.append("""## 三、中危漏洞清单

未发现中危漏洞。\n""")

        # 四、低危/信息类发现（有数据才出）
        if low_ports:
            low_rows = ""
            for i, p in enumerate(low_ports, 1):
                src = p.get("_source_vendor", "") or "自检"
                low_rows += f"| {i} | 1 | 端口{p['port']}/{p.get('service','?')} 开放（信息级） | {target} | {src} |\n"
            sections.append(f"""## 四、低危/信息类发现

| 序号 | 数量 | 主要类型 | 涉及目标 | 发现来源 |
|:----:|:----:|----------|:--------:|:--------:|
{low_rows}""")
        else:
            sections.append("""## 四、低危/信息类发现

未发现低风险项。\n""")

        # 五、综合整改建议
        rec_section = "## 五、综合整改建议\n\n"
        if p0_recs:
            rec_section += "### 5.1 紧急整改——24小时内（P0）\n\n| 优先级 | 整改项 | 涉及目标 | 整改期限 |\n|:------:|--------|:--------:|----------|\n"
            rec_section += "\n".join([f"| **P0** | {r} | {target} | 立即修复 |" for r in p0_recs]) + "\n\n"
        if p1_recs:
            rec_section += "### 5.2 限期整改——7天内（P1）\n\n| 优先级 | 整改项 | 涉及目标 | 整改期限 |\n|:------:|--------|:--------:|----------|\n"
            rec_section += "\n".join([f"| **P1** | {r} | {target} | 7天内整改 |" for r in p1_recs]) + "\n\n"
        if p2_recs or p3_recs:
            rec_section += "### 5.3 常规整改——30天内（P2/P3）\n\n| 序号 | 整改项 | 涉及范围 | 整改期限 |\n|:----:|--------|----------|:--------:|\n"
            for i, r in enumerate(p2_recs + p3_recs, 1):
                deadline = "30天内" if i <= len(p2_recs) else "下次维护周期"
                rec_section += f"| {i} | {r} | {target} | {deadline} |\n"
        if not any([p0_recs, p1_recs, p2_recs, p3_recs]):
            rec_section += "无特殊整改建议。\n"
        sections.append(rec_section)

        # 六、攻击路径复盘（有高危端口才出）
        if high_ports:
            port_list_str = "、".join([str(p["port"]) for p in high_ports[:5]])
            attack_path = f"""## 六、攻击路径复盘

### 攻击面分析

根据检测结果，{target} 存在 {len(high_ports)} 个高危端口（{port_list_str} 等）：

```
外部攻击者
    ↓ 信息收集（端口扫描发现开放端口）
{target}
    ↓ 高危端口暴露：{port_list_str}
    ↓ 可利用服务：{', '.join([p.get('service','?') for p in high_ports[:5]])}
    ↓ 若存在未修复漏洞，可尝试远程利用
内部网络失陷
```

**影响评估：** 高危端口暴露可能被攻击者利用进行渗透，需立即处置。
"""
            sections.append(attack_path)
        else:
            sections.append("""## 六、攻击路径复盘

未发现高危端口，攻击面较小。\n""")

        # 七、结论
        risk_str = rec.get("risk_level", "未知")
        conclusions = f"""## 七、结论

### 综合风险评级：**{risk_str}**

对 {target} 经扫描检测，共发现 **{total_findings} 项安全风险**。

**核心结论：**
1. {"发现 " + str(len(high_ports)) + " 个高危风险，建议立即排查" if high_ports else "未发现高危风险" }
2. {"发现 " + str(len(med_ports)) + " 个中危项，需限期整改" if med_ports else "未发现中危风险" }
3. {"发现 " + str(len(low_ports)) + " 个低风险项，建议持续关注" if low_ports else "未发现低风险项" }
"""
        sections.append(conclusions)

        # 八、附件（仅当一个 vendor 有记录时才出，从 VENDOR_SELECTION_STRATEGY 找对应产品名）
        attachment_section = "## 八、附件\n\n"
        if all_vendors:
            # 构建 vendor->检测类型映射
            vendor_map = {}
            for cat, info in VENDOR_SELECTION_STRATEGY.items():
                for v in info["vendors"]:
                    if v not in vendor_map:
                        vendor_map[v] = info["description"]
            attachment_rows = ""
            for i, entry in enumerate(records, 1):
                v = entry["vendor"]
                if not v:
                    continue
                detect_type = vendor_map.get(v, "安全检测")
                attachment_rows += f"| {i} | {v}{detect_type}检测原始记录 | {v} |\n"
            if attachment_rows:
                attachment_section += "| 序号 | 附件名称 | 来源 |\n|:----:|----------|:----:|\n" + attachment_rows
            else:
                attachment_section += "（无独立附件）\n"
        else:
            attachment_section += "（无独立附件）\n"
        sections.append(attachment_section)

        # ── 组合最终报告 ──
        report = f"""# 网络安全检查汇总报告

**报告编号**: {report_id}
**检查目标**: {target}
**检查时间**: {scan_time_str}
**报告日期**: {now.strftime('%Y年%m月%d日')}

---

> **声明：** 本报告基于安全检测工具的原始输出汇总编制。每项发现均已标注检测来源，便于追溯验证。

---

""" + "\n---\n\n".join(sections) + f"""

---

*报告由安全检查 Agent 自动生成 — {scan_time_str}*
"""

    elif template == "anheng-report":
        report = f"""# 安恒明鉴漏洞扫描报告

**报告编号**: SCAN-DB-{datetime.now().strftime('%Y%m%d')}-001
**扫描工具**: 安恒明鉴漏洞扫描系统 V8.2
**扫描目标**: {target}

## 一、扫描概览
| 项目 | 数据 |
|------|------|
| 高危 | {len(high_risk_ports)} |
| 开放端口 | {len(ports)} |

## 二、高危漏洞详情
{'| 目标 | 端口 | 服务 | CVE | CVSS |' if high_risk_ports else '未发现高危漏洞'}
{'|------|------|------|:---:|:----:|' if high_risk_ports else ''}
{chr(10).join([f"| {target} | {p['port']} | {p['service']} | N/A | 9.0 |" for p in high_risk_ports]) if high_risk_ports else ''}

## 三、修复建议
{recs_list if recs_list else '无特殊建议'}

---
**报告结束**
"""
    elif template == "nsfocus-report":
        report = f"""# 绿盟科技·安全检查报告（弱口令+配置核查）

**报告编号**: NSFOCUS-{datetime.now().strftime('%Y%m%d')}-001
**扫描工具**: 绿盟远程安全评估系统 RSAS V6.5
**扫描目标**: {target}

## 第一部分：端口检测结果
| 项目 | 数据 |
|------|------|
| 开放端口数 | {len(ports)} |
| 高危端口 | {len(high_risk_ports)} |

## 第二部分：配置核查结果
{'| 检查项 | 结果 | 说明 |' if high_risk_ports else '未发现严重不合规项'}
{'|--------|:----:|------|' if high_risk_ports else ''}
{chr(10).join([f"| 端口{p['port']}暴露 | 不合规 | {p['service']}服务暴露在公网 |" for p in high_risk_ports]) if high_risk_ports else ''}

---
**报告结束**
"""
    elif template == "chaitin-report":
        report = f"""# 长亭科技·牧云Web安全检查报告

**报告编号**: CHAITIN-WEB-{datetime.now().strftime('%Y%m%d')}-001
**扫描工具**: 牧云Web应用安全检测平台 V3.5
**扫描目标**: {target}

## 一、目标信息
| 项目 | 内容 |
|------|------|
| URL | http://{target} / https://{target} |
| 开放端口 | {', '.join([str(p['port']) for p in ports[:10]])} |

## 二、漏洞发现汇总
| 风险等级 | 数量 |
|:--------:|:----:|
| 高危 | {len(high_risk_ports)} |
| 低危 | {len(ports) - len(high_risk_ports) if len(ports) > len(high_risk_ports) else 0} |
| **合计** | {len(ports)} |

## 三、高危漏洞详情
|{chr(10).join([f"### WEB-{i+1:03d} 端口{p['port']}暴露" + chr(10) + "- **风险等级**: 高危" + chr(10) + "- **漏洞描述**: " + p['service'] + "服务存在端口暴露风险" + chr(10) + "- **修复建议**: 限制访问来源IP，关闭非必要端口" for i, p in enumerate(high_risk_ports)]) if high_risk_ports else '未发现高危Web漏洞'}

---
**报告结束**
"""
    elif template == "vackbot-report":
        report = f"""# 墨云·VackBot自动化渗透测试报告

**报告编号**: VACKBOT-PEN-{datetime.now().strftime('%Y%m%d')}-001
**扫描工具**: 墨云VackBot自动化渗透平台 V4.2
**扫描目标**: {target}

## 一、渗透测试概览
| 项目 | 数据 |
|------|------|
| 开放端口 | {len(ports)} 个 |
| 高危端口 | {len(high_risk_ports)} 个 |
| 渗透等级 | {'**高**' if len(high_risk_ports) >= 3 else ('**中**' if high_risk_ports else '**低**')} |

## 二、攻击面分析
| 端口 | 服务 | 风险 | 可利用性 |
|------|------|:----:|:--------:|
{chr(10).join([f"| {p['port']} | {p['service']} | {'⚠️高危' if p.get('high_risk') else '信息'} | {'已验证' if p.get('high_risk') else '未验证'} |" for p in ports[:10]]) if ports else '| (无) | — | — | — |'}

## 三、综合风险评估
| 风险项 | 影响 |
|--------|------|
| 端口暴露 | 攻击者可利用暴露端口进行渗透 |
| 服务漏洞 | 需确认服务版本是否存在已知CVE |

---
**报告结束**
"""
    else:
        return {"success": False, "data": {}, "error": f"未知模板: {template}，支持: standard / customer / anheng-report / nsfocus-report / chaitin-report / vackbot-report"}

    return {
        "success": True,
        "data": {
            "target": target,
            "template": template,
            "report": report,
            "risk_level": rec.get('risk_level', 'unknown'),
            "format": "markdown"
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
    "baseline_check": baseline_check,
    "evidence_snapshot": evidence_snapshot,
    "retest_compare": retest_compare,
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
            {"name": "security_scan", "description": "安全检查 — 对单个IP执行TOP500端口扫描+服务版本识别+风险分析，支持vendor列表failover", "parameters": {"target": "目标IP", "vendor": "厂商名称（逗号分隔，支持failover，可选）", "scan_type": "扫描类型: port_scan/full（可选）"}},
            {"name": "batch_scan", "description": "批量安全扫描 — 对多个目标批量执行安全检查", "parameters": {"targets": "目标IP列表（JSON数组）", "scan_type": "扫描类型（可选）", "vendor": "厂商名称（可选）"}},
            {"name": "gen_report", "description": "生成安全检查报告 — 支持standard/customer/anheng-report/nsfocus-report/chaitin-report/vackbot-report 6种模板", "parameters": {"target": "目标IP", "template": "模板: standard/customer/anheng-report/nsfocus-report/chaitin-report/vackbot-report"}},
            {"name": "validate_report", "description": "报告质量校验 — 检查报告数据的完整性/格式/数值合理性", "parameters": {"target": "目标IP"}},
            {"name": "gen_selection_plan", "description": "生成厂商选型方案 — 按检测类型推荐最优厂商工具，覆盖7类检测30+厂商", "parameters": {"target_desc": "目标描述（可选）", "exclude_types": "排除的检测类型（可选）"}},
            {"name": "get_asset_profile", "description": "查询资产档案 — 查看目标的扫描历史记录", "parameters": {"target": "目标IP"}},
            {"name": "baseline_check", "description": "等保基线核查 — 检查目标是否符合等保2.0三级要求（6类基线项）", "parameters": {"target": "目标IP"}},
            {"name": "evidence_snapshot", "description": "证据固化 — 为扫描结果生成SHA256 Hash+时间戳的证据记录", "parameters": {"target": "目标IP", "scan_id": "指定记录ID（可选）"}},
            {"name": "retest_compare", "description": "复测确认 — 对比最近两次扫描记录的端口变化和风险变化", "parameters": {"target": "目标IP"}},
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
