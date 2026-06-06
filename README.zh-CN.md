<p align="center">
  <img src=".github/assets/cloakbot-logo.png" alt="CloakBot" width="420" />
</p>

<h1 align="center">CloakBot —— 给前沿 LLM 加一层本地隐私内核</h1>

<p align="center">用 Claude / GPT / Gemini，但数据不离开本机。</p>

<p align="center">
  <img src="https://img.shields.io/badge/Privacy-Pre--wire%20Enforcement-0F172A?style=flat-square" alt="Pre-wire Enforcement" />
  <img src="https://img.shields.io/badge/Gemma%204-Local%20Trust%20Layer-0F9D58?style=flat-square" alt="Gemma 4 Trust Layer" />
  <img src="https://img.shields.io/badge/Remote%20LLM-Claude%20%7C%20GPT%20%7C%20Gemini-8B5CF6?style=flat-square" alt="Remote LLM Claude GPT Gemini" />
  <img src="https://img.shields.io/badge/Python-3.11%2B-3776AB?style=flat-square" alt="Python 3.11+" />
  <img src="https://img.shields.io/badge/License-MIT-16A34A?style=flat-square" alt="MIT License" />
</p>

<p align="center"><a href="README.md">English</a> | <strong>简体中文</strong></p>

<p align="center"><sub>基于 <a href="https://github.com/HKUDS/nanobot">nanobot</a> 构建 · 已提交至 <strong>Gemma 4 Good Hackathon</strong>（Kaggle，2026 年 5 月）</sub></p>

---

## 📋 TL;DR

前沿 LLM 已经成了承重的生产力工具，但发出去的数据一旦上线就无法收回。CloakBot 把执行点前移到「上线之前」：基于 **Gemma 4 E2B** 的本地隐私内核负责识别敏感片段、分配稳定的带类型占位符、给图像打码、把长文档分片处理，并在本地通过会话级 Vault 把响应还原。远端 LLM 可以随意替换——Claude、GPT、Gemini 都能直接消费脱敏后的请求流。

> **2,872 条实体级回归测试作为存证**，分布在三层泄漏 eval —— `7.98%` 配对泄漏（文本）· `1.11%` 跨度泄漏（图像）· `6.26%` 配对泄漏（长文档）· `97.14%` 跨轮占位符一致性。

---

## 🔍 运行流程

```
用户消息（文本 + 可选的图像 / 文档）
  └─► [ pre_llm_hook → PrivacyRuntime ]
        • 本地 Gemma 4 E2B 检测器并发跑（general + digit）
        • 图像 → OCR + bbox 涂黑 + 占位符叠加
        • 长文档 → 内容感知 chunker + 分块检测 + Vault 合流
        • 工具 I/O → 非本地工具按敏感度走审批
        • 敏感片段改写为 <<TYPE_N>> 占位符，写入会话级 Vault
  └─► [ 远端 LLM ]   (Claude / GPT / Gemini —— 只看脱敏后的 payload)
        • 数学轮：远端输出 <python_snippet_N>，真正的算术在本地跑
        • 工具调用：参数本地还原，结果在复用前再脱敏一次
  └─► [ post_llm_hook → 本地还原 ]
        • 用 Vault map 把占位符还原回原值
        • 生成每轮透明度报告
  └─► 最终回复里用户看到的是原始值
```

流式输出会先缓冲，等还原完成才放出去——用户不会看到任何裸的占位符。

---

## 检测范围

| 类别 | 示例 | 默认等级 |
|---|---|:---:|
| 个人与联系 | 姓名、电话、邮箱、住址 | High |
| 唯一标识 | SSN、护照号、账号、车牌 | High |
| 密钥与凭据 | 密码、API key、token、私有 URL | High |
| 组织与网络 | 公司名、学校名、IP | High |
| 医疗与叙事 | PHI、治疗、诊断、代号 | High |
| 数字与时间 | 金额、日期、百分比、计数、量值、坐标 | High |

检测器拆成两路：`GeneralPrivacyDetector` 负责非可计算的文本片段，`DigitPrivacyDetector` 负责数字 / 时间值并做归一化，方便后续在本地做数学执行。每个片段会变成带索引的 token —— `<<ENTITY_TYPE_INDEX>>` —— 远端 LLM 仍能识别关系（`PERSON_1` ≠ `PERSON_2`），但不知道他们是谁：例如 `Alice Chen → <<PERSON_1>>`、`555-123-4567 → <<PHONE_1>>`、`$142,500 → <<FINANCE_1>>`、`Metformin 500mg → <<MEDICAL_1>>`。

---

## 为什么用小型 LLM，而不是正则或 BERT-NER？

**一句话——正则只能搞定容易的那 20%，剩下 80% 必须看上下文。** CloakBot 两条路都走：正则跑快速通道（邮箱、发票号、交易号、文件路径——手写在 [`privacy/core/detection/`](cloakbot/privacy/core/detection/) 里），剩下所有正则和 BERT-NER 搞不定的事情，全部交给 Gemma 4 E2B。

| 失败场景 | 正则 | BERT-NER (Presidio, spaCy) | **Gemma 4 E2B** |
|---|:---:|:---:|:---:|
| 已知格式——邮箱、SSN、信用卡 | ✓ | ✓ | ✓ |
| 区分 `"John"` 是占位符还是真实客户 | ✗ | ✗ | ✓ |
| 指示性数字——*「给我 3 条关于 Q4 财报的要点」* | 把 `3` 也 token 化（请求被破坏） | 视标签集而定 | ✓ 识别为任务结构，保留 |
| 组合标识——*「住在 90210 邮编的 67 岁糖尿病男性」* | ✗ | ✗ | ✓ |
| 跨轮实体消歧——*「另一个姓 Lin 的人」* ≠ 已有 `<<PERSON_1>>` Lin Zhiyuan | 不适用 | 不适用 | ✓ 输出 `new` |
| 间接标识——*「上次提到的那个病人」* | ✗ | ✗ | ✓ |
| 用户自定义实体——*「项目代号 Falcon 也要脱敏」* | 改正则 | 重训模型 | 改 prompt |
| 领域漂移——chat 日志 vs NER 训练用的新闻语料 | 不适用 | 召回降 20–40% | 鲁棒 |
| 多语言（中 / 日 / 韩 / 英）在一个模型里 | 每个语种一套正则 | 每种语言 600 MB+ | 一个 2B 模型 |
| 可计算性归一化——`$1,200.50` → `1200.5`（可供本地数学执行） | 仅字符串 | 仅字符串 | ✓ 类型化数值 |

只能拦住简单情况的 PII 代理**比完全没有代理更糟糕**——因为用户会信任它。真正的门槛是判断**在这次具体对话里**这个 token 到底该不该被遮蔽，这是一个生成式 LLM 形状的问题。Gemma 4 E2B 是唯一同时满足这些条件的可商用再分发模型：能塞进消费级硬件（量化后约 5 GB，MacBook 通过 Ollama 就能跑）、T=0 下稳出可解析 JSON、同一套权重原生多模态且多语言——**信任层就是这个模型**，而不是在 Presidio 上挂一个 chat 改写器。老实交代代价：单次检测约 50–200 ms，正则不到 1 ms；靠 general + digit 并发、已知格式走正则快通道、长文档分块并发来抵消。完整理由、延迟与方法学见 [hackathon writeup](docs/HACKATHON_WRITEUP.md)。

---

## 多智能体架构

```
┌─────────────────────────────── LOCAL TRUST ZONE ─────────────────────────────┐
│                                                                              │
│   User input  ──►  [ pre_llm_hook ]  ──►  [ PrivacyRuntime ]                 │
│                                                  │                           │
│           ┌──────────────────┬───────────────────┼─────────────────┐         │
│           ▼                  ▼                   ▼                 ▼         │
│      PiiDetector       ToolPrivacy        VisualPrivacy        DocChunker    │
│   (general + digit)    Interceptor          Pipeline          (long docs)    │
│           │            (tool I/O)        (OCR + bbox)              │         │
│           └──────────────────┬───────────────────────┬─────────────┘         │
│                              ▼                       ▼                       │
│                  [ Session Vault ]         [ Local Math Executor ]           │
│              (placeholder ↔ raw map,         (arithmetic-only AST,           │
│               per-session, on disk)            sandboxed)                    │
│                                                                              │
└──────────────────────────────────┬───────────────────────────────────────────┘
                                   │  sanitised payload only
   ────────────────────────────────┼─────────── REMOTE BOUNDARY ───────────────
                                   ▼
                          [ Remote LLM ]   (Claude / GPT / Gemini)
                                   │  response re-enters local zone
   ────────────────────────────────┼───────────────────────────────────────────
                                   ▼
                         [ post_llm_hook ]  →  restore + per-turn report  →  User
```

| 组件 | 职责 | 后端 |
|---|---|---|
| `PrivacyRuntime` | 每轮的协调器：脱敏、路由、还原、审计 | Python |
| `PiiDetector` | general + digit + intent 检测器并发跑，再去重 | Gemma 4 E2B |
| `ToolPrivacyInterceptor`（+ `chunking/`） | 工具 I/O 还原、按敏感度审批、输出脱敏；长文档内容感知 chunker + 跨块 Vault 合流 | Gemma 4 E2B + 规则 |
| `VisualPrivacyPipeline` | OCR + bbox 涂黑 + 占位符叠加 + 跨模态召回桥 | Gemma 4 E2B + Pillow + Tesseract |
| `Session Vault` | 可审计的「占位符 ↔ 原值」映射，跨轮复用别名 | JSON 落盘 |
| `Math Executor` | 本地执行远端生成的 `<python_snippet_N>` 块；AST 校验、仅算术 | Python AST 沙箱 |

完整组件清单与文件结构见 [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)。

---

## 📊 Evals —— 以测量建立信任

我们不接受「靠声明赢得信任」。三层端到端泄漏 eval 直接跑在**生产代码路径**上，每轮只回答一个问题：*这一轮里，有没有任何一个 ground-truth 的可识别 token 出现在上传 payload 里？*

| 层 | 覆盖 | 关键指标 | 跨轮别名 |
|---|---|---|---:|
| **A1 —— 文本输入** | 4 个领域 × 20 个会话 × 902 个实体-轮 pair | **7.98%** pair 泄漏 · **5.88%** token 泄漏 | **97.14%** |
| **A2 —— 视觉** | 10 个发票种子 × 180 个 PII 跨度 × 197 个涂黑框 | **1.11%** 跨度泄漏 · **1.01%** token 泄漏 | 不适用 |
| **A3 —— 长文档** | 3 个领域 × 20 个会话 × 1,790 个 pair（走 chunker） | **6.26%** pair 泄漏 · **6.63%** token 泄漏 | **93.86%** |

- **跨领域 100% pair 召回**——`EMAIL · PHONE · FINANCE · IP · URL`
- **MEDICAL 召回：20% → 95%**——靠类型驱动的 prompt 迭代（规则 → 类型相邻示例）
- **226 个 A3 seam 泄漏中 0 个**落在 chunker 300 字符的重叠带里——剩下的长文档泄漏全部是块内检测漏召，而不是 seam 处掉链子

完整的逐模板拆分、方法学，以及我们自己抓出来的 eval bug 见 [`docs/HACKATHON_WRITEUP.md`](docs/HACKATHON_WRITEUP.md)。复现方式：每层一条命令，runner 都在 `tests/eval/runners/` 下。

> *所有 p95 延迟数字都是用 Gemma 4 E2B 经 vLLM 部署在 RTX 5090 上实测得到的。MacBook（Ollama）部署路径端到端能跑通，但延迟更慢 —— MacBook 是目标部署硬件，不是测量平台。*

---

## 🛠️ 安装与启动

### 安装

**从 PyPI 安装（推荐）** —— WebUI 已打包内置，无需构建前端：

```bash
pip install --pre cloakbot      # 0.2.1 beta（隐私内核）；0.2.1 正式版发布后去掉 --pre
```

想要隔离的 CLI 安装？用 `uv tool install --prerelease allow cloakbot` 或 `pipx install --pip-args=--pre cloakbot`。可选聊天渠道：`pip install --pre 'cloakbot[matrix,discord,msteams]'`。

**从源码安装**（最新 `main` / 开发）—— 需 Node ≥24 构建 WebUI：

```bash
git clone https://github.com/spire-studio/cloakbot.git && cd cloakbot
uv sync
cd webui && npm install && npm run build && cd ..
```

> 源码安装时，下面的 `cloakbot` 命令前请加 `uv run`。

### 1. 自带本地 Gemma 4 检测器

CloakBot 的隐私保证依赖于 PII 检测器跑在**你自己掌控的机器**上。任何 OpenAI 兼容服务都行（vLLM、Ollama、llama.cpp……），推荐 **Gemma 4 E2B**。把检测器指向**远端**端点（例如 OpenRouter）会把未脱敏的原始输入发过去做检测 —— 那是**仅供测试**、会破坏边界。

**Ollama（macOS / Linux / WSL，无需 GPU）：**

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull gemma4:e2b        # 一条命令同时拉起模型和 OpenAI 兼容接口
# → base URL http://127.0.0.1:11434/v1 · API key "ollama"（随便填）· model gemma4:e2b
```

**vLLM（GPU 机器 —— 快、可复现，A1/A2/A3 eval 路径）：**

```bash
uv sync --extra vllm
uv run huggingface-cli login   # 在 hf.co/google/gemma-4-E2B-it 接受 Gemma 协议
vllm serve google/gemma-4-E2B-it --port 8000 --dtype bfloat16 --api-key <你的-token>
# → base URL http://127.0.0.1:8000/v1 · API key <你的-token> · model google/gemma-4-E2B-it
```

### 2. 配置与启动

```bash
cloakbot onboard      # 配置远端 LLM + [D] Privacy Detector
cloakbot gateway      # 启动后打开它打印的 WebUI 地址（默认 http://127.0.0.1:8765/）
```

在 `onboard` → **[D] Privacy Detector** 里填检测器的 **base URL / API key / model**（或之后在 WebUI 的 **Settings → Privacy** 里配），远端 LLM（Claude / GPT / Gemini）在同一流程里配（或 **Settings → Models**）。检测器暴露的 OpenAI 兼容接口**只**用于本地 PII 检测 —— 远端 LLM 调用完全是另一条路径。

然后把 [`docs/demo/demo_onboarding_memo.md`](docs/demo/demo_onboarding_memo.md) 拖进 Composer，就能看到 20 条 PII 实体从头到尾被脱敏；点任意气泡上的 **Diff** 看「本地 ↔ 远端」对比。

---

## 🗺️ 路线图

### ✅ 已发货（2026 年 4 月 – 5 月）

**核心隐私运行时（v0.1）** —— 4 月
- 基于 Gemma 4 E2B 的拆分本地检测器（general + digit）
- JSON 落盘的 Session Vault + 跨轮别名复用
- 数学片段契约 + 本地 AST 校验的算术执行器
- IntentAnalyzer + chat / math 路由
- `ToolPrivacyInterceptor`：工具 I/O 脱敏 + 按敏感度审批

**信任边界扩展（v0.2）** —— 5 月
- ✓ 长文档 chunker 通道（`ToolPrivacyDetector` + 4 个内容感知 chunker：纯文本 / JSON / HTML / Markdown）
- ✓ 视觉流水线：OCR + bbox 涂黑 + 占位符叠加 + 跨模态召回桥
- ✓ WebUI 文档上传（text/plain、text/markdown ≤ 64 KB）走同一条 chunker 脱敏路径
- ✓ 「本地 ↔ 远端」diff 对话框，每个文档独立高亮实体
- ✓ Ollama 升级为一等公民后端（无需 GPU）—— `ollama pull gemma4:e2b` 一条命令拉起模型 + 接口

**以测量建立信任（v0.3）** —— 5 月
- ✓ 端到端泄漏 eval 框架（`tests/eval/runners/`）
- ✓ A1 / A2 / A3 三层 —— **2,872 条实体级回归测试**作为存证
- ✓ 类型驱动的检测器 prompt（MEDICAL 召回 20% → 95%）
- ✓ 自己抓出来并修掉的 eval bug（token 级打分；全值出现匹配收紧）

### 🚀 接下来

- **领域专用 LoRA adapter** —— 在垂直语料（医疗、法律、金融）上微调 Gemma 4 E2B，提升领域短语的召回，解锁带策略的垂直部署。一套内核 + 三个 adapter：按租户挑。
- **短 ORG / 连字符名召回**（71.67% → 90% 目标）—— A1 当前最大缺口，可借上面的 LoRA 路径修
- **双语覆盖** —— 中文 eval 模板 + zh-CN 检测器 prompt 迭代
- **流式 + 每轮 batch** —— 目标把医疗 p95 从 6.2 秒压到 2 秒以下
- **Vault 加密落盘** —— 面向共享设备部署
- **策略驱动的敏感度分级** —— 超越当前注册表默认值（目前全部 `high`）
- **面向数据集 / 表格的结构化 chunker**（CSV / Parquet）—— 用于分析工具输出

---

## Hackathon 赛道

- **主赛道 —— Gemma 4 Good（Safety & Trust 方向）** —— Gemma 4 E2B 作为本地隐私内核，在任何字节抵达远端 LLM 之前就执行一道「上线前」边界。背后是 A1（文本）、A2（视觉）、A3（长文档）三层泄漏 eval、共 2,872 条实体级回归测试作为存证 —— 详见 [`docs/HACKATHON_WRITEUP.md`](docs/HACKATHON_WRITEUP.md)。
- **Ollama 特别技术赛道** —— `ollama pull gemma4:e2b` 一条命令同时拉起模型和 OpenAI 兼容接口，再把检测器指向 `http://127.0.0.1:11434/v1` —— 不用折腾 GGUF，也不用按操作系统分叉 Metal / CUDA。**Gemma 4 是信任层，Ollama 是部署层。**

---

## ⭐ Star History

<a href="https://www.star-history.com/?repos=spire-studio%2Fcloakbot&type=date&logscale=&legend=top-left">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/chart?repos=spire-studio/cloakbot&type=date&theme=dark&legend=top-left" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/chart?repos=spire-studio/cloakbot&type=date&legend=top-left" />
   <img alt="Star History Chart" src="https://api.star-history.com/chart?repos=spire-studio/cloakbot&type=date&legend=top-left" />
 </picture>
</a>

---

## 致谢与许可证

CloakBot 基于 HKUDS 的 [nanobot](https://github.com/HKUDS/nanobot)（MIT License）构建。频道接入、会话管理、记忆系统和 CLI 都来自上游框架。本仓库里 CloakBot 的隐私相关实现主要集中在 [`cloakbot/privacy/`](cloakbot/privacy/)、[`cloakbot/providers/vllm.py`](cloakbot/providers/vllm.py)，以及 [`cloakbot/agent/loop.py`](cloakbot/agent/loop.py) 中的 hook 接入点。

面向 agent 的架构、可靠性、安全、隐私域备注与[设计取舍](docs/design-docs/design-decisions.md)都在 [`docs/`](docs/) 下 —— 先看 [`AGENTS.md`](AGENTS.md)。

MIT License —— 见 [`LICENSE`](LICENSE)。
