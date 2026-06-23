# 安全扫描报告

| 项目 | 内容 |
|------|------|
| **任务名称** | {{TASK_TITLE}} |
| **扫描目标** | {{TARGET}} |
| **扫描时间** | {{SCAN_TIME}} |
| **扫描类型** | {{SCAN_TYPE}} |
| **状态** | {{STATUS}} |

---

## 1. 端口扫描结果

**命令**: `{{PORT_SCAN_CMD}}`

| 端口 | 协议 | 服务 | 状态 |
|------|------|------|------|
{{PORT_TABLE}}

**摘要**: {{PORT_SUMMARY}}

---

## 2. 漏洞扫描结果

**命令**: `{{VULN_SCAN_CMD}}`

**总计发现**: {{VULN_TOTAL}} 个漏洞

### 漏洞详情

{{VULN_DETAILS}}

---

## 3. 风险分析与建议

| 风险级别 | 数量 |
|---------|------|
| 🔴 严重 (Critical) | {{CRITICAL_COUNT}} |
| 🟠 高危 (High) | {{HIGH_COUNT}} |
| 🟡 中危 (Medium) | {{MEDIUM_COUNT}} |
| 🟢 低危 (Low) | {{LOW_COUNT}} |

### 建议措施

{{RECOMMENDATIONS}}

---

## 4. 相关漏洞知识

{{CVE_KNOWLEDGE}}

---

*报告由 EvoGen 安全扫描引擎自动生成*
*生成时间: {{GENERATED_TIME}}*
