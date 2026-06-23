#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# EvoGen 安全扫描全流程演示脚本
# 用法: bash demo.sh [target] [ports]
# 默认: bash demo.sh 127.0.0.1 22,80,443
# ═══════════════════════════════════════════════════════════════
set -e

TARGET="${1:-127.0.0.1}"
PORTS="${2:-22,80,443}"
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
PASS=0
FAIL=0

green() { echo -e "\033[32m$1\033[0m"; }
red() { echo -e "\033[31m$1\033[0m"; }
blue() { echo -e "\033[34m$1\033[0m"; }
bold() { echo -e "\033[1m$1\033[0m"; }

check() {
    if [ $? -eq 0 ]; then
        green "  ✅ $1"
        PASS=$((PASS + 1))
    else
        red "  ❌ $1"
        FAIL=$((FAIL + 1))
    fi
}

bold "══════════════════════════════════════════════"
bold "  EvoGen 安全扫描全流程演示"
bold "  目标: $TARGET  端口: $PORTS"
bold "══════════════════════════════════════════════"
echo ""

# ──────────────────────────────────────
# 1. 测试 MCP nmap 端口扫描
# ──────────────────────────────────────
blue "[1/6] MCP nmap 端口扫描"
echo "命令: python3 $PROJECT_DIR/scripts/mcp_nmap_server.py --cli --target $TARGET --ports $PORTS"
RESULT=$(python3 "$PROJECT_DIR/scripts/mcp_nmap_server.py" --cli --target "$TARGET" --ports "$PORTS" 2>&1)
echo "$RESULT" | head -5
echo "$RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['success'], '扫描失败'; print(f'  -> 扫描成功, 目标: {d[\"data\"][\"target\"]}')" 2>/dev/null
check "MCP nmap 端口扫描"

# ──────────────────────────────────────
# 2. 测试 MCP Nuclei 漏洞扫描（如果安装）
# ──────────────────────────────────────
blue "[2/6] MCP Nuclei 漏洞扫描"
if command -v nuclei &>/dev/null; then
    echo "命令: python3 $PROJECT_DIR/scripts/mcp_nuclei_server.py --cli --target http://$TARGET"
    python3 "$PROJECT_DIR/scripts/mcp_nuclei_server.py" --cli --target "http://$TARGET" 2>&1 | head -5
    check "MCP Nuclei 漏洞扫描"
else
    echo "  (Nuclei 未安装, 测试 fallback 检测)"
    python3 -c "
import sys
sys.path.insert(0, '$PROJECT_DIR')
from scripts.mcp_nuclei_server import vuln_scan
r = vuln_scan('http://$TARGET')
print(f'  -> Nuclei fallback 正确: {r.get(\"fallback\", False)}')
" 2>&1
    check "Nuclei fallback 检测"
fi

# ──────────────────────────────────────
# 3. 测试漏洞知识库
# ──────────────────────────────────────
blue "[3/6] 漏洞知识库检索"
echo "命令: python3 $PROJECT_DIR/scripts/import_cve_knowledge.py --search 'Log4j'"
python3 "$PROJECT_DIR/scripts/import_cve_knowledge.py" --search "Log4j" 2>&1 | head -5
check "漏洞知识库检索 Log4j"

echo ""
python3 "$PROJECT_DIR/scripts/import_cve_knowledge.py" --search "$TARGET" 2>&1 | head -5
check "漏洞知识库按目标搜索"

# ──────────────────────────────────────
# 4. 测试报告模板存在
# ──────────────────────────────────────
blue "[4/6] 报告模板"
if [ -f "$PROJECT_DIR/templates/report_template.md" ]; then
    LINES=$(wc -l < "$PROJECT_DIR/templates/report_template.md")
    echo "  -> 报告模板存在: $(wc -c < "$PROJECT_DIR/templates/report_template.md") bytes, $LINES 行"
    check "报告模板文件"
else
    red "  (报告模板不存在)"
    FAIL=$((FAIL + 1))
fi

# ──────────────────────────────────────
# 5. 测试工具列表注册（后端 API）
# ──────────────────────────────────────
blue "[5/6] 工具注册验证"
python3 -c "
import sys
sys.path.insert(0, '$PROJECT_DIR')
from backend.api.tools_routes import _static_tool_list
tools = _static_tool_list()
names = {t['name'] for t in tools}
assert 'port_scan' in names, 'port_scan not registered'
assert 'vuln_scan' in names, 'vuln_scan not registered'
assert 'browser_navigate' in names, 'browser_navigate not registered'
port = [t for t in tools if t['name'] == 'port_scan'][0]
assert port.get('priority') == 1, f'priority wrong: {port.get(\"priority\")}'
assert port.get('fallback') == 'vuln_scan', f'fallback wrong: {port.get(\"fallback\")}'
print(f'  -> {len(tools)} tools registered')
print(f'  -> port_scan: priority={port[\"priority\"]}, fallback={port[\"fallback\"]}')
" 2>&1
check "工具注册完整性"

# ──────────────────────────────────────
# 6. 测试报告生成 + 质量校验
# ──────────────────────────────────────
blue "[6/6] 报告生成 + 质量校验（模拟数据）"
python3 -c "
import os, sys
sys.path.insert(0, '$PROJECT_DIR')
os.chdir('$PROJECT_DIR')

# mock scan data
mock_data = {
    'port_scan': {
        'tool': 'port_scan',
        'open_ports': [
            {'port': 22, 'protocol': 'tcp', 'service': 'ssh'},
            {'port': 80, 'protocol': 'tcp', 'service': 'http'},
        ],
        'total_ports': 2,
        'command': 'nmap -T4 -oX - -p 22,80 127.0.0.1',
        'target': '127.0.0.1',
    },
    'vuln_scan': {
        'tool': 'vuln_scan',
        'findings': [
            {'severity': 'HIGH', 'name': 'Apache Log4j RCE', 'matched_at': '127.0.0.1:8080'},
            {'severity': 'MEDIUM', 'name': 'TLS 1.0 Supported', 'matched_at': '127.0.0.1:443'},
        ],
        'total_findings': 2,
        'command': 'nuclei -severity critical,high -u http://127.0.0.1',
        'target': '127.0.0.1',
    },
}

from backend.api.chat_routes import _generate_security_report, _validate_report_quality
report = _generate_security_report(mock_data, 'demo-session', user_id='demo')
assert report is not None, 'report generation failed'
print(f'  -> 报告长度: {len(report)} bytes')

quality = _validate_report_quality(report)
print(f'  -> 质量校验: {\"PASS\" if quality[\"pass\"] else \"FAIL\"} ({quality[\"passed_checks\"]}/{quality[\"total_checks\"]})')
for issue in quality['issues']:
    print(f'    * {issue}')
assert quality['pass'], 'report quality check failed'
print(report[:300])
" 2>&1
check "报告生成 + 质量校验"

# ──────────────────────────────────────
# 汇总
# ──────────────────────────────────────
echo ""
bold "══════════════════════════════════════════════"
bold "  演示结果"
bold "══════════════════════════════════════════════"
green "  通过: $PASS"
if [ $FAIL -gt 0 ]; then
    red "  失败: $FAIL"
    exit 1
else
    green " 全部通过! ✅"
fi
echo ""
echo "全流程说明:"
echo "  一句话触发: '扫描 $TARGET 的端口和漏洞'"
echo "  -> Agent 自动调用 port_scan (nmap)"
echo "  -> Agent 自动调用 vuln_scan (nuclei)"
echo "  -> 知识库自动检索相关 CVE"
echo "  -> 自动生成安全报告 (Markdown 制品)"
echo "  -> 报告质量自动校验"
echo "  -> 工具失败自动切换 fallback"
echo ""
echo "命令参考:"
echo "  # 端口扫描:"
echo "  python3 $PROJECT_DIR/scripts/mcp_nmap_server.py --cli --target $TARGET --ports $PORTS"
echo ""
echo "  # 漏洞扫描:"
echo "  python3 $PROJECT_DIR/scripts/mcp_nuclei_server.py --cli --target http://$TARGET"
echo ""
echo "  # 知识库搜索:"
echo "  python3 $PROJECT_DIR/scripts/import_cve_knowledge.py --search 'CVE-2021-44228'"
echo ""
