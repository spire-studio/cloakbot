<p align="center">
  <img src="logo+cloakbot-readme.png" alt="CloakBot" width="420" />
</p>

<h1 align="center">Cloakbot：隐私保护 AI Agent</h1>

<p align="center">在你的数据与任意远端 LLM 之间，加一层本地多智能体隐私防护。</p>

<p align="center">
  <img src="https://img.shields.io/badge/Privacy-First-0F172A?style=flat-square" alt="Privacy First" />
  <img src="https://img.shields.io/badge/Gemma%204-Local%20Detection-0F9D58?style=flat-square" alt="Gemma 4 Local Detection" />
  <img src="https://img.shields.io/badge/vLLM-OpenAI%20Compatible-1F6FEB?style=flat-square" alt="vLLM OpenAI Compatible" />
  <img src="https://img.shields.io/badge/Multi--Agent-Hybrid-7C3AED?style=flat-square" alt="Hybrid Multi-Agent" />
  <img src="https://img.shields.io/badge/Remote%20LLM-Claude%20%7C%20GPT%20%7C%20Gemini-8B5CF6?style=flat-square" alt="Remote LLM Claude GPT Gemini" />
  <img src="https://img.shields.io/badge/Python-3.11%2B-3776AB?style=flat-square" alt="Python 3.11+" />
  <img src="https://img.shields.io/badge/License-MIT-16A34A?style=flat-square" alt="MIT License" />
</p>

<p align="center"><a href="README.md">English</a> | <strong>简体中文</strong></p>

<p align="center"><sub>基于 <a href="https://github.com/HKUDS/nanobot">nanobot</a> 构建 · 已提交至 <strong>Gemma 4 Good Hackathon</strong>（Kaggle，2026 年 5 月）</sub></p>

CloakBot 在会话与远端 LLM 之间加入一条**本地隐私流水线**。消息发往上游之前，会先经过由受信任本地模型（通过 vLLM/Ollama 提供）驱动的多智能体系统，执行两类仅输出 JSON 的本地检测：一类识别通用敏感实体，另一类识别敏感数字与时间信息。命中的文本片段会被替换为可逆、带类型的占位符，并保存到会话级 Vault。遇到数学任务时，远端 LLM 只负责给出结构，真实计算在本地基于 Vault 原值完成。

远端 LLM 返回后，CloakBot 会在本地恢复占位符，并追加每轮隐私报告。流式输出会先缓冲，等后处理结束再展示，避免用户看到未恢复的占位符。

---

## 目录

- [工作流程](#工作流程)
- [检测范围](#检测范围)
- [多智能体系统设计](#多智能体系统设计)
- [项目结构](#项目结构)
- [路线图](#路线图)
- [工程知识库](#工程知识库)
- [安装与启动](#安装与启动)
- [运行测试](#运行测试)
- [关键设计取舍](#关键设计取舍)
- [Hackathon 赛道](#hackathon-赛道)
- [致谢与许可证](#致谢与许可证)

---

## 工作流程

```
用户消息
  └─► [pre_llm_hook → PrivacyRuntime]
        • 本地通过 vLLM 运行 GeneralPrivacyDetector + DigitPrivacyDetector
        • 将敏感片段替换为带类型 token  例如 "Alice" → <<PERSON_1>>
        • 持久化会话 Vault（token ↔ 原文映射，以及必要时的数值）
        • 在本地做意图分类（chat / math）
        • 将当前轮路由给 ChatAgent 或 MathAgent
  └─► [远端 LLM — Claude / GPT / Gemini]
        • 只接收脱敏后的提示词
        • math 任务会附加额外约束，要求输出 <python_snippet_N> 代码块
        • 响应中继续使用占位符，不直接暴露原始值
        • 工具结果在后续模型调用前会先脱敏
  └─► [post_llm_hook → 本地后处理]
        • 用 Vault 中的真实值执行仅算术的数学代码片段
        • 将 <<PERSON_1>> 恢复为 "Alice"
        • 生成每轮隐私报告
  └─► 用户最终看到的是已恢复原值的回复
```

---

## 检测范围

| 类别 | 示例 | 默认等级 |
|---|---|---|
| 个人与联系方式 | 姓名、手机号、邮箱、住址 | High |
| 唯一身份与隐私标识 | 身份证号、护照号、账号、车牌 | High |
| 密钥与访问凭据 | 密码、API Key、私有令牌、敏感 URL | High |
| 组织与网络上下文 | 公司名、学校名、IP 地址 | High |
| 医疗与私密叙事信息 | PHI、治疗信息、机密计划、代号等敏感文本 | High |
| 敏感数字与时间信息 | 金额、日期、百分比、计数、测量值、分数、坐标 | High |

检测器拆分为两条本地流程：`GeneralPrivacyDetector` 负责不可计算的文本实体，`DigitPrivacyDetector` 负责后续可能参与本地计算的数字/时间实体。内置注册表当前将已支持的实体家族统一标为 `high`。

### Token 规则

所有实体都按 `<<ENTITY_TYPE_INDEX>>` 格式替换，读起来直观、规则一致：

| 原始值 | Token | 等级 |
|---|---|---|
| `Alice Chen` | `<<PERSON_1>>` | High |
| `alice@acme.com` | `<<EMAIL_1>>` | High |
| `555-123-4567` | `<<PHONE_1>>` | High |
| `123-45-6789` | `<<ID_1>>` | High |
| `$142,500` | `<<FINANCE_1>>` | High |
| `December 15, 2026` | `<<DATE_1>>` | High |
| `15%` | `<<PERCENTAGE_1>>` | High |
| `Stanford Hospital` | `<<ORG_1>>` | High |
| `Metformin 500mg` | `<<MEDICAL_1>>` | High |

索引按实体类型独立递增。这样远端 LLM 仍能区分关系（例如 `PERSON_1` 和 `PERSON_2` 是两个人），但不知道具体是谁。

---

## 多智能体系统设计

CloakBot 在隐私层内部采用**混合多智能体架构**：本地 Orchestrator 负责围绕远端 LLM 调用，协调检测、路由、聊天与数学处理。远端 LLM 被视作不受信任的计算资源，只能接触脱敏文本。

### 信任边界

```
┌─────────────────────────────────────────────────────────────────────┐
│                        LOCAL TRUST ZONE                             │
│                                                                     │
│   User ──► [ pre_llm_hook ]                                         │
│                  │                                                  │
│                  ▼                                                  │
│         [ PrivacyRuntime ]                                          │
│            /         |         \                                    │
│           ▼          ▼          ▼                                   │
│  [PiiDetector] [IntentAnalyzer] [TurnContext/Vault]                 │
│      /    \             │             │                             │
│     ▼      ▼            ▼             ▼                             │
│ [General] [Digit]   [TaskRouter]   [Handler]                        │
│    via      via        /   \           │                            │
│  Gemma 4  Gemma 4     ▼     ▼          ▼                            │
│   vLLM     vLLM   [Chat] [Math]   [Session Vault]                   │
│                          │        (JSON-backed placeholder map)     │
│                          ▼                                          │
│                 [Local Math Executor]                               │
│                                                                     │
└──────────────────┬──────────────────────────────────────────────────┘
                   │  sanitized payload only
   ────────────────┼──────────── REMOTE BOUNDARY ─────────────────────
                   ▼
            [ Remote LLM ]  (Claude / GPT / Gemini APIs)
                   │
   ────────────────┼─────────────────────────────────────────────────
                   │  response re-enters local trust zone
                   ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    POST-RESPONSE LOCAL PIPELINE                      │
│                                                                      │
│   [ MathAgent ]      ← executes <python_snippet_N> blocks locally    │
│           │                                                          │
│   [ Restorer ]       ← swap tokens back using Vault                  │
│           │                                                          │
│   [ Transparency Report ]  ← summarize masked input/tool entities    │
│           │                                                          │
└───────────┼──────────────────────────────────────────────────────────┘
            ▼
         Output → User ✓
```

文档和数据集任务通过普通 chat/tool 轮次处理。本地工具可以读取原始文件，
但工具结果在被远端模型复用前必须先脱敏。

### Agent 列表

| Agent | 职责 | 模型 |
|---|---|---|
| **PrivacyRuntime** | 协调单轮全流程：脱敏、意图识别、路由、恢复、报告 | Python runtime pipeline |
| **PiiDetector** | 并行运行 general/digit 检测后做去重整合 | Gemma 4 via vLLM |
| **GeneralPrivacyDetector** | 抽取姓名、ID、密钥、组织名等不可计算敏感片段 | Gemma 4 via vLLM |
| **DigitPrivacyDetector** | 抽取敏感数字/时间片段，并为后续本地计算规范化 | Gemma 4 via vLLM |
| **IntentAnalyzer** | 将请求分类为 `chat` 或 `math` | Gemma 4 via vLLM |
| **Handler + Vault** | 应用 `<<TAG_N>>` 占位符并持久化会话映射 | 规则引擎 + JSON 文件 |
| **ChatAgent** | 将脱敏文本发往上游，响应在恢复前保持原样 | 规则引擎 |
| **MathAgent** | 远端调用前注入代码片段约束，调用后本地执行受限代码 | 远端 LLM + 本地执行器 |
| **Restorer** | 通过单次正则扫描恢复占位符 | 规则引擎 |
| **Transparency Report** | 生成每轮隐私报告（Markdown） | 规则引擎 |
| **ToolPrivacyInterceptor** | 恢复本地工具输入、拦截敏感的非本地工具调用，并在工具结果回流模型前脱敏，包括文件/文档读取结果 | 规则引擎 + 检测器 |

### 检测分层（纵深防御）

当前运行时会在远端 LLM 调用前执行输入脱敏；当工具调用经过隐私拦截器时，也会对工具结果做回流前脱敏。已恢复的远端模型响应按设计不再做二次检测。

```
Pass 1  用户输入        → 防止原始 PII 离开设备
Pass 2  工具调用输出    → 回流模型前脱敏
```

`ToolPrivacyInterceptor` 还会在本地工具执行前恢复占位符，并在敏感参数将被发送到非本地或有副作用工具时创建审批请求。

### 数学隐私（Goal 2）

在计算场景下，远端 LLM 只负责“推理结构”，不会拿到真实数值：

```
输入:   "My salary is $142,500. What is 18% of it?"
脱敏:   "What is 18% of <<FINANCE_1>>?" + snippet contract
远端:   "<python_snippet_1>result = FINANCE_1 * 0.18</python_snippet_1>"
本地:   result = 142500 * 0.18          # 用 Vault 原值替换后执行
输出:   "$25,650.00"
```

本地执行器刻意收窄能力：以 Python AST 解析，只允许给 `result` 赋值的算术表达式；仅暴露少量安全函数（`abs`、`round`、`min`、`max`、`pow`）；未知变量或链式幂运算都会拒绝。

### 文档与数据集隐私（Goal 3）

文档隐私属于工具隐私，不是独立的文档 worker 流水线。当 agent 需要文件、
文档或数据集内容时，会使用 `read_file`、`grep` 或未来的结构化读取工具。
这些工具可以在本地查看原始内容，但 `ToolPrivacyInterceptor.sanitize_tool_result()`
会先脱敏工具结果，再把结果交给远端模型。

每个工具来源文档都使用同一条信任边界：

```
本地工具读取原始文档
  → 工具结果通过会话 Vault 脱敏
  → 远端模型只接收脱敏内容
  → 用户可见最终答案可以在本地恢复
```

### 工具调用隐私（Goal 4）

工具隐私通过 `ToolPrivacyInterceptor` 和工具隐私等级实现：

```
已实现:
  sanitize_tool_output(text, session_key)
  ToolPrivacyInterceptor.prepare_tool_call(...)
  ToolPrivacyInterceptor.sanitize_tool_result(...)
  TurnContext.tool_output_entities
  敏感非本地工具输入的 ToolApprovalRequest
```

工具类会声明 `local`、`external` 或 `side_effect` 隐私等级。新增工具时应选择准确且最保守的等级。

---

## 项目结构

```
cloakbot/
├── cloakbot/
│   ├── privacy/                 ← CloakBot 隐私层
│   │   ├── core/
│   │   │   ├── detection/
│   │   │   │   ├── detector.py      General + digit 检测入口
│   │   │   │   ├── general_detector.py  本地 vLLM 非可计算实体抽取
│   │   │   │   ├── digit_detector.py    本地 vLLM 数字/时间实体抽取
│   │   │   │   └── llm_json.py      本地模型 JSON 完成辅助
│   │   │   ├── sanitization/
│   │   │   │   ├── sanitize.py      对外脱敏/恢复接口
│   │   │   │   ├── handler.py       占位符替换逻辑
│   │   │   │   ├── restorer.py      占位符恢复
│   │   │   │   └── alias_resolver.py  跨轮复用占位符
│   │   │   ├── math/
│   │   │   │   ├── math_executor.py 远端代码约束 + 本地执行
│   │   │   │   └── math_helpers.py  算术 AST 安全校验
│   │   │   └── state/
│   │   │       └── vault.py         会话级 token/value 持久化
│   │   ├── runtime/
│   │   │   ├── pipeline.py      顶层隐私协调器
│   │   │   ├── routing.py       chat/math 路由
│   │   │   ├── registry.py      Worker 注册与查找
│   │   │   └── tool_interceptor.py  工具输入/输出隐私边界
│   │   ├── agents/
│   │   │   ├── classification/
│   │   │   │   └── intent_analyzer.py   本地意图分析
│   │   │   └── workers/
│   │   │       ├── chat_agent.py    标准脱敏聊天流程
│   │   │       └── math_agent.py    远端生成、本地执行数学片段
│   │   ├── hooks/
│   │   │   ├── pre_llm.py           远端调用前脱敏
│   │   │   ├── post_llm.py          远端调用后恢复
│   │   │   └── context.py           单轮隐私上下文
│   │   └── transparency/
│   │       └── report.py            每轮隐私报告渲染
│   ├── providers/
│   │   └── vllm.py                  OpenAI 兼容客户端 → 受信任 vLLM
│   └── agent/
│       └── loop.py                  脱敏中间件（2 个 hook）
├── tests/
│   ├── privacy/                     隐私层单元测试
│   └── sanitizer/                   旧版 sanitizer 兼容/集成测试
└── scripts/
    └── start_vllm.sh                启动 vLLM 服务
```

会话级占位符映射会以 JSON 形式存到 `~/.cloakbot/workspace/privacy_vault/maps/`，同一会话跨轮可复用。CloakBot 现在已支持**多轮会话隐私保护**：占位符映射可跨轮延续，同时对用户展示仍在本地恢复。可计算占位符还会保存规范化数值，用于后续本地数学执行。

---

## 路线图

### ✅ v0.1 — 隐私运行时基础（当前，2026 年 4 月）
- [x] general 与 numeric/temporal 双检测器拆分
- [x] 使用 `<<ENTITY_TYPE_N>>` 占位符脱敏
- [x] JSON 持久化会话 Vault
- [x] 最终输出占位符恢复
- [x] Web UI 聊天界面
- [x] 带单轮上下文的 PrivacyRuntime
- [x] 本地意图分析与 chat/math 路由
- [x] MathAgent 代码片段约束 + 本地算术执行
- [x] 多轮会话隐私保护
- [x] Web UI 易用性优化
- [x] ToolPrivacyInterceptor 工具输入恢复与工具输出脱敏

### 🔨 v0.2 — 信任边界扩展
- [ ] 大型文件/文档工具输出的分块脱敏
- [ ] 面向数据集/表格工具输出的结构化脱敏

### 🚀 v0.3 — 生产可用增强
- [ ] Vault 持久化加密选项
- [ ] 更快检测路径/更小本地模型
- [ ] 更好的双语与准标识符覆盖
- [ ] 超越当前注册表默认策略的策略化处理
- [ ] 完整端到端隐私集成测试

---

## 工程知识库

面向 agent 的架构、可靠性、安全与隐私域说明已经整理到
[`docs/`](docs/README.md)。先看 [`AGENTS.md`](AGENTS.md) 这个短入口，再按任务
进入对应的深入文档。

---

## 安装与启动

### 1. 克隆并安装

```bash
git clone https://github.com/spire-studio/cloakbot.git && cd cloakbot
uv sync
```

### 2. 配置

```bash
cp .env.example .env
# 编辑 .env:
#   VLLM_BASE_URL=http://<your-vllm-server>:8000/v1
#   VLLM_API_KEY=your-secret-token
#   VLLM_MODEL=google/gemma-4-E2B-it
```

按 CloakBot 常规方式（或使用 `onboard`）在 `~/.cloakbot/config.json` 中配置远端 LLM（Claude、GPT、Gemini 等）：

```bash
uv run python -m cloakbot onboard
```

### 3. 启动 vLLM 服务（Ubuntu / GPU 机器）

```bash
# 首次使用：安装 vllm 并登录 HuggingFace
uv sync --extra vllm
uv run huggingface-cli login          # 在 hf.co/google/gemma-4-E2B-it 接受 Gemma 协议

# 启动服务（会自动读取 .env 里的 VLLM_API_KEY 与 VLLM_MODEL）
bash scripts/start_vllm.sh
```

> vLLM 服务提供 OpenAI 兼容 API。CloakBot 的 sanitizer 只把它用于本地 PII 检测；远端 LLM 调用链路是分离的。

### 4. 启动 WebUI

```bash
uv run python -m cloakbot webui
```

---

## 关键设计取舍

**脱敏 + Token 化，而不是伪名化**：`<<PERSON_1>>` 比“替换成假人名”更直接也更稳妥。远端 LLM 仍能理解 `PERSON_1` 与 `PERSON_2` 的关系，但拿不到真实身份。

**双检测器、单 Vault**：将不可计算文本与数字/时间实体拆开处理，既保留任务结构，又能在本地保留后续数学执行所需的规范化数据。

**数学场景中远端只做推理**：数学任务要求远端输出 `<python_snippet_N>` 结构，最终数值结果始终在本地结合 Vault 原值计算。

**默认 fail-open**：当本地 vLLM 不可用时，默认透传消息而非阻断对话；同时 sanitizer API 也支持严格 fail-closed。

**面向流式输出的安全后处理**：CLI 会先缓冲流式内容，等数学执行、占位符恢复与报告生成完成后再输出，避免中间态泄露。

**基于 hook 的低侵入集成**：隐私层主要代码集中在 `cloakbot/privacy/`，通过 [loop.py](/Users/laurieluo/Documents/github/my-repos/cloakbot/cloakbot/agent/loop.py:574) 中的 `pre_llm_hook` / `post_llm_hook` 接入主运行时。

**文档是工具来源的隐私数据**：没有独立文档意图或文档 worker。文档和数据集保护属于工具输出边界，因此文件读取、grep 结果和未来结构化读取器都共享同一条 sanitizer/Vault 路径。

---

## Hackathon 赛道

- **主赛道**：Gemma 4 Good（使用 Gemma 4 做本地隐私保护）
- **Ollama 特别赛道**：本地模型推理（vLLM，兼容 Ollama API）

---

## 致谢与许可证

CloakBot 基于 HKUDS 的 [nanobot](https://github.com/HKUDS/nanobot)（MIT License）构建。频道接入、会话管理、记忆系统和 CLI 来自上游框架。本仓库中 CloakBot 的隐私相关实现主要位于 `cloakbot/privacy/`、[vllm.py](/Users/laurieluo/Documents/github/my-repos/cloakbot/cloakbot/providers/vllm.py:1)，以及 [loop.py](/Users/laurieluo/Documents/github/my-repos/cloakbot/cloakbot/agent/loop.py:574) 的 hook 接入点。
