<p align="center">
  <img src="logo+cloakbot.png" alt="CloakBot" width="420" />
</p>

<h1 align="center">Cloakbot：隐私保护 AI Agent</h1>

<p align="center">在你的数据与任何远程 LLM 之间，加上一层本地多智能体隐私保护层。</p>

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

<p align="center"><sub>基于 <a href="https://github.com/HKUDS/nanobot">nanobot</a> 构建 · 提交至 <strong>Gemma 4 Good Hackathon</strong>（Kaggle，2026 年 5 月）</sub></p>

CloakBot 在你的会话与任何远程 LLM 之间加入了一条**本地隐私处理流水线**。消息发送到上游之前，会先由一个可信的、通过 vLLM 提供服务的 Gemma 4 模型运行两个本地 JSON 检测器：一个负责识别通用敏感实体，另一个负责识别敏感数值或时间类实体。命中的文本片段会被改写成带类型、可逆的占位符，并保存到会话级 Vault 中。对于数学类对话，远程 LLM 只负责生成结构，真实计算会在本地基于 Vault 中的原始值完成。

远程 LLM 返回结果后，CloakBot 会在本地恢复占位符，并附加逐轮隐私报告。流式输出会先被缓冲，等后处理完成后再统一输出，因此用户不会看到原始占位符。

---

## 目录

- 工作原理
- 检测范围
- 多智能体系统设计
- 架构
- 路线图
- 安装与配置
- 运行测试
- 设计决策
- Hackathon 赛道
- 致谢与许可证

---

## 工作原理

```
用户消息
  └─► [pre_llm_hook → PrivacyOrchestrator]
        • 通过 vLLM 在本地运行 GeneralPrivacyDetector + DigitPrivacyDetector
        • 用类型化 token 替换敏感片段，例如 "Alice" → <<PERSON_1>>
        • 持久化会话 Vault（token ↔ 原始值映射，必要时也保存数值）
        • 在本地判定意图（chat / math / doc）
        • 将本轮路由给 ChatAgent 或 MathAgent
  └─► [远程 LLM — Claude / GPT / Gemini]
        • 只接收脱敏后的提示词
        • 对数学类对话，额外接收一份要求输出 <python_snippet_N> 的约束
        • 使用占位符而不是真实值来生成响应
  └─► [post_llm_hook → 本地后处理]
        • 使用 Vault 中的真实值执行仅限算术的数学片段
        • 恢复 <<PERSON_1>> → "Alice"
        • 渲染逐轮隐私报告
  └─► 用户看到恢复后的最终答案
```

**示例 — 对话**

```
你：        我叫 Alice Chen，邮箱是 alice@acme.com。我的名字是什么？
🔒 脱敏：    "Alice Chen" [PERSON, high] → <<PERSON_1>>
            "alice@acme.com" [EMAIL, high] → <<EMAIL_1>>
CloakBot：  你的名字是 Alice Chen。
📋 报告：    输入中遮蔽 2 个实体 · 已全部恢复 ✓
```

**示例 — 数学**

```
你：        我的工资是 $142,500。18% 是多少？
🔒 脱敏：    "$142,500" [FINANCE, high] → <<FINANCE_1>> · "18%" 保留
发送：      "What is 18% of <<FINANCE_1>>?" + 隐私数学片段指令
远程：      "<python_snippet_1>result = FINANCE_1 * 0.18</python_snippet_1>"
本地执行：  result = 142500 * 0.18 = 25650
CloakBot：  $142,500 的 18% 是 $25,650.00
📋 报告：    遮蔽 1 个实体 · 已在本地完成计算 · 已全部恢复 ✓
```

---

## 检测范围

| 类别 | 示例 | 默认敏感级别 |
|---|---|---|
| 个人与联系方式数据 | 姓名、电话号码、邮箱、住址 | 高 |
| 唯一或私密标识符 | SSN、护照号、账号、车牌号 | 高 |
| 密钥与访问类数据 | 密码、API Key、私有 Token、敏感 URL | 高 |
| 组织与网络上下文 | 公司名、学校名、IP 地址 | 高 |
| 医疗与私密叙述数据 | PHI、治疗信息、保密计划、项目代号、其他敏感自由文本 | 高 |
| 敏感数值与时间数据 | 金额、日期、百分比、计数、测量值、评分、坐标 | 高 |

检测器分为两个本地阶段：`GeneralPrivacyDetector` 负责非可计算文本片段，`DigitPrivacyDetector` 负责后续可能参与本地计算的数值或时间值。当前内置 registry 中的实体类型默认都标记为 `high`。

### Token 方案

所有实体都会被替换成 `<<ENTITY_TYPE_INDEX>>` 这种形式的 token，保证一致且可读：

| 原始值 | Token | 敏感级别 |
|---|---|---|
| `Alice Chen` | `<<PERSON_1>>` | 高 |
| `alice@acme.com` | `<<EMAIL_1>>` | 高 |
| `555-123-4567` | `<<PHONE_1>>` | 高 |
| `123-45-6789` | `<<ID_1>>` | 高 |
| `$142,500` | `<<FINANCE_1>>` | 高 |
| `December 15, 2026` | `<<DATE_1>>` | 高 |
| `15%` | `<<PERCENTAGE_1>>` | 高 |
| `Stanford Hospital` | `<<ORG_1>>` | 高 |
| `Metformin 500mg` | `<<MEDICAL_1>>` | 高 |

按类型分别编号后，远程 LLM 仍然可以理解实体之间的关系，例如 `PERSON_1` 和 `PERSON_2` 是两个不同的人，但无法知道他们分别是谁。

---

## 多智能体系统设计

CloakBot 在隐私层内部使用**混合式多智能体架构**：本地 Orchestrator 在远程 LLM 调用前后协调检测、路由、聊天和数学处理逻辑。远程 LLM 被视为不可信的计算资源，只能接触脱敏后的文本。

### 信任边界

```
┌─────────────────────────────────────────────────────────────────────┐
│                        本地可信区域                                 │
│                                                                     │
│   User ──► [ pre_llm_hook ]                                         │
│                  │                                                  │
│                  ▼                                                  │
│         [ PrivacyOrchestrator ]                                     │
│            /         |         \                                    │
│           ▼          ▼          ▼                                   │
│  [PiiDetector] [IntentAnalyzer] [TurnContext/Vault]                 │
│      /    \             │             │                             │
│     ▼      ▼            ▼             ▼                             │
│ [General] [Digit]   [TaskRouter]   [Handler]                        │
│    via      via        /   \           │                            │
│  Gemma 4  Gemma 4     ▼     ▼          ▼                            │
│   vLLM     vLLM   [Chat] [Math]   [Session Vault]                   │
│                          │        （JSON 持久化占位符映射）          │
│                          ▼                                           │
│                 [Local Math Executor]                                │
│                                                                     │
└──────────────────┬──────────────────────────────────────────────────┘
                   │  只传递脱敏后的载荷
   ────────────────┼──────────── 远程边界 ────────────────────────────
                   ▼
            [ Remote LLM ]  (Claude / GPT / Gemini APIs)
                   │
   ────────────────┼─────────────────────────────────────────────────
                   │  响应重新进入本地可信区域
                   ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    响应后的本地处理管线                              │
│                                                                      │
│   [ MathAgent ]      ← 在本地执行 <python_snippet_N> 代码块          │
│           │                                                          │
│   [ Restorer ]       ← 使用 Vault 还原 token                         │
│           │                                                          │
│   [ Transparency Report ]  ← 汇总输入 / 工具输出中的遮蔽信息         │
│           │                                                          │
└───────────┼──────────────────────────────────────────────────────────┘
            ▼
         Output → User ✓
```

`Intent.DOC` 已经存在于路由器中，但当前还没有 `DocAgent`。文档类请求目前会回退到 `ChatAgent`。

### 智能体分工

| 智能体 | 角色 | 模型 |
|---|---|---|
| **PrivacyOrchestrator** | 负责一轮完整流程：脱敏、意图分类、路由、恢复与报告 | Python orchestrator |
| **PiiDetector** | 并发运行 general detector 和 digit detector，并对结果去重 | Gemma 4 via vLLM |
| **GeneralPrivacyDetector** | 提取不可计算的敏感片段，如姓名、ID、密钥、组织名 | Gemma 4 via vLLM |
| **DigitPrivacyDetector** | 提取敏感数值 / 时间片段，并归一化以供后续本地计算 | Gemma 4 via vLLM |
| **IntentAnalyzer** | 将一轮对话分类为 `chat`、`math` 或 `doc` | Gemma 4 via vLLM |
| **Handler + Vault** | 应用 `<<TAG_N>>` 占位符并持久化会话映射 | 规则驱动 + JSON 文件 |
| **ChatAgent** | 将脱敏后的文本发往远程，并在恢复前原样返回响应 | 规则驱动 |
| **MathAgent** | 在远程调用前加入片段约束，在远程调用后于本地执行受限代码 | 远程 LLM + 本地执行器 |
| **Restorer** | 通过单次正则替换恢复占位符 | 规则驱动 |
| **Transparency Report** | 生成逐轮 Markdown 隐私报告 | 规则驱动 |
| **Tool Interceptor** | 为未来的工具输出隐私约束预留；目前仍是占位文件 | 尚未实现 |

### Detector 扫描阶段（纵深防御）

当前运行时只会在远程 LLM 调用前执行**一次强制 detector 扫描**：

```
Pass 1  用户输入        → 防止原始 PII 离开设备
Pass 2  LLM 响应        → 已规划，但尚未接入
Pass 3  工具调用输出    → helper 已存在，interceptor 尚未接入
```

代码里已经有 `sanitize_tool_output()` 和 `tool_output_entities` 这些扩展点。当前真正已经落地的是：输入侧脱敏、响应后恢复，以及数学片段的本地执行。

### 数学隐私（Goal 2）

对于计算任务，远程 LLM 只扮演**推理引擎**，它不会看到真实数字：

```
输入：    "My salary is $142,500. What is 18% of it?"
脱敏：    "What is 18% of <<FINANCE_1>>?" + 片段约束
远程：    "<python_snippet_1>result = FINANCE_1 * 0.18</python_snippet_1>"
本地：    result = 142500 * 0.18          # 从 Vault 中替换回真实值
输出：    "$25,650.00"
```

本地执行器刻意保持很窄的能力边界：它会把片段解析为 Python AST，只允许赋值给 `result` 的算术表达式，只暴露少量安全数值函数（`abs`、`round`、`min`、`max`、`pow`），并拒绝未知变量或链式幂运算。

### 文档与数据集隐私（Goal 3）

这一部分之前的 README 写得比代码实现更超前。当前实现**并没有**真正提供文档或数据集隐私处理管线。

目前已经有的只有：
1. Intent analyzer 可以把一轮请求识别成 `doc`。
2. 路由器会保留这个意图。
3. `get_agent()` 会记录 warning，并因为 `DocAgent` 尚未实现而回退到 `ChatAgent`。

所以文档隐私现在仍然只是 roadmap 项目，而不是已完成特性。

### 工具调用隐私（Goal 4）

工具隐私现在也只是**部分脚手架已就位**：

```
当前已实现：
  sanitize_tool_output(text, session_key)  → 可复用 helper
  TurnContext.tool_output_entities         → 报告字段预留

尚未接入：
  agents/tool_interceptor.py               → 占位文件
  主循环中的 pass 3 强制执行               → 待实现
```

也就是说，CloakBot 已经有了用于处理工具结果的核心脱敏入口，但主 agent loop 还没有把每个工具输出都纳入这条链路。

---

## 架构

```
cloakbot/
├── cloakbot/
│   ├── privacy/                 ← CloakBot 的隐私层
│   │   ├── core/
│   │   │   ├── detector.py          general + digit detector facade
│   │   │   ├── general_detector.py  本地 vLLM 驱动的非可计算实体提取
│   │   │   ├── digit_detector.py    本地 vLLM 驱动的数值 / 时间实体提取
│   │   │   ├── handler.py           占位符安全的 token 应用逻辑
│   │   │   ├── vault.py             持久化到磁盘的会话 token / value 映射
│   │   │   ├── restorer.py          反查与恢复
│   │   │   ├── sanitize.py          公共 sanitize / remap 入口
│   │   │   ├── math_executer.py     远程片段约束 + 本地执行
│   │   │   └── math_helpers.py      仅算术片段的 AST 校验
│   │   ├── agents/
│   │   │   ├── orchestrator.py      顶层隐私协调器
│   │   │   ├── intent_analyzer.py   本地意图分类
│   │   │   ├── task_router.py       chat/math/doc 路由
│   │   │   ├── chat_agent.py        标准脱敏对话流程
│   │   │   ├── math_agent.py        在本地执行远程生成的数学片段
│   │   │   └── tool_interceptor.py  未来工具输出约束的占位实现
│   │   ├── hooks/
│   │   │   ├── pre_llm.py           在远程 LLM 调用前脱敏
│   │   │   ├── post_llm.py          在远程 LLM 调用后恢复
│   │   │   └── context.py           每轮隐私上下文
│   │   └── transparency/
│   │       └── report.py            逐轮隐私报告渲染
│   ├── providers/
│   │   └── vllm.py                  OpenAI 兼容客户端 → 可信 vLLM 服务
│   └── agent/
│       └── loop.py                  脱敏中间件（2 个 hook）
├── tests/
│   ├── privacy/                     隐私层单元测试
│   └── sanitizer/                   旧 sanitizer 兼容 / 集成测试
└── scripts/
    ├── start_vllm.sh                启动 vLLM 服务
    └── test_sanitizer.py            冒烟测试
```

会话级占位符映射会以 JSON 形式持久化到 `~/.cloakbot/sanitizer_maps/` 下，因此 Vault 可以在同一 session 的多轮中复用同一个占位符映射。不过，当前端到端隐私边界仍然是**单轮**：恢复后的对话历史会被重新写回 session，因此完整的多轮对话隐私保护仍然是 roadmap 项目。可计算占位符也会保存归一化后的数值，以便后续在本地执行数学片段。

---

## 路线图

### ✅ v0.1 — 隐私运行时基础（当前，2026 年 4 月）
- [x] 将 detector 拆分为通用实体检测与数值 / 时间检测
- [x] 使用 `<<ENTITY_TYPE_N>>` 占位符方案进行 Redact+Tokenize
- [x] 带 JSON 持久化的 Session Vault
- [x] 基于占位符 remap 的最终输出恢复
- [x] Web UI 聊天界面
- [x] 在 `cloakbot/agent/loop.py` 中接入 `pre_llm_hook` 和 `post_llm_hook`
- [x] 具备逐轮上下文的 PrivacyOrchestrator
- [x] 本地意图分析与 chat/math/doc 路由
- [x] MathAgent 片段约束与本地算术执行
- [ ] Web UI 细节打磨与可用性完善

### 🔨 v0.2 — 信任边界扩展
- [ ] 多轮对话隐私保护
- [ ] Tool-use Detector：在主循环中强制执行工具使用结果脱敏
- [ ] 真正实现 `ToolInterceptor`
- [ ] 具体可用的 `DocAgent`
- [ ] 带共享 Vault 的 chunk-map-aggregate 文档处理流程
- [ ] 数据集 schema 与列级脱敏

### 🚀 v0.3 — 生产可用性强化
- [ ] 加密 Vault 持久化选项
- [ ] 更快的 detector 路径 / 更小的本地模型
- [ ] 更好的中英双语与准标识符覆盖
- [ ] 超出当前 registry 默认行为的策略驱动处理
- [ ] 完整的端到端隐私集成测试

---

## 安装与配置

### 1. 克隆并安装

```bash
git clone https://github.com/spire-studio/cloakbot.git && cd cloakbot
uv sync                                           # 安装 cloakbot 依赖
```

### 2. 配置

```bash
cp .env.example .env
# 编辑 .env：
#   VLLM_BASE_URL=http://<your-vllm-server>:8000/v1
#   VLLM_API_KEY=your-secret-token
#   VLLM_MODEL=google/gemma-4-E2B-it
```

像普通 cloakbot 一样，在 `~/.cloakbot/config.json` 中配置远程 LLM（Claude、GPT、Gemini 等）。

### 3. 启动 vLLM 服务（Ubuntu / GPU 机器）

```bash
# 首次运行：安装 vllm 并登录 HuggingFace
uv sync --extra vllm
uv run huggingface-cli login          # 先在 hf.co/google/gemma-4-E2B-it 接受 Gemma 协议

# 启动服务（会自动读取 .env 里的 VLLM_API_KEY 和 VLLM_MODEL）
bash scripts/start_vllm.sh
```

> vLLM 服务暴露的是 OpenAI 兼容 API。CloakBot 的 sanitizer 只用它来做 PII 检测；远程 LLM 调用是另一条完全独立的链路。

### 4. 验证 sanitizer

```bash
uv run python scripts/test_sanitizer.py
```

### 5. 开始对话

```bash
uv run python -m cloakbot agent --config ~/.cloakbot/config.json
```

---

## 运行测试

```bash
# 隐私层单元测试（mocked vLLM + Vault）
uv run --extra dev pytest tests/privacy/ -v

# sanitizer 兼容 / 往返测试
uv run --extra dev pytest tests/sanitizer/ -v

# 集成测试（需要先启动 vLLM 服务）
uv run --extra dev pytest tests/ -m integration -v
```

---

## 设计决策

**使用 Redact + Tokenize，而不是 Pseudonymize** —— `<<PERSON_1>>` 比伪造一个“看起来像真人”的名字更简单，也更安全。远程 LLM 仍然可以理解 `PERSON_1` 与 `PERSON_2` 的关系，但不知道它们分别是谁。

**两个本地 detector，共享一个 Vault** —— CloakBot 将不可计算片段与数值 / 时间片段分开处理，这样既能保留任务结构，又能在本地保留足够的归一化数据，供后续数学执行使用。

**远程 LLM 只在数学任务中充当推理引擎** —— 数学类对话会要求远程模型输出 `<python_snippet_N>` 结构；最终数值答案由本地基于 Vault 中的真实值计算得出。

**默认 fail-open** —— 如果本地 vLLM 服务不可用，当前默认行为是消息原样通过，而不是阻塞本轮请求。sanitizer API 也支持严格的 fail-closed 模式。

**流式输出的安全后处理** —— CLI 会先缓冲流式输出，等数学执行、token 恢复和报告渲染完成后，再向用户展示最终版本，而不是中间态的占位符文本。

**基于 hook 的集成方式** —— 隐私层大部分代码都隔离在 `cloakbot/privacy/` 下，并通过 [loop.py](/Users/laurieluo/Documents/github/my-repos/cloakbot/cloakbot/agent/loop.py:574) 中的 `pre_llm_hook` 与 `post_llm_hook` 接入主运行时。

**roadmap 在代码中已有脚手架** —— 文档意图、工具输出脱敏 helper、以及 tool-interceptor 占位实现都已经存在，但还没有完整接入主运行时。

---

## Hackathon 赛道

- **主赛道** — Gemma 4 Good：使用本地 Gemma 4 构建隐私保护 AI
- **Ollama 特别赛道** — 本地模型推理（vLLM，与 Ollama API 兼容）

---

## 致谢与许可证

CloakBot 基于 HKUDS 的 [nanobot](https://github.com/HKUDS/nanobot)（MIT License）构建。频道接入、会话管理、记忆系统和 CLI 来自上游框架。这个仓库中与隐私相关的主要工作集中在 `cloakbot/privacy/`、[vllm.py](/Users/laurieluo/Documents/github/my-repos/cloakbot/cloakbot/providers/vllm.py:1)，以及 [loop.py](/Users/laurieluo/Documents/github/my-repos/cloakbot/cloakbot/agent/loop.py:574) 中的 hook 接入点。
