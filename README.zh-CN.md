<p align="center">
  <img src="logo+cloakbot-readme.png" alt="CloakBot" width="420" />
</p>

<h1 align="center">CloakBot —— 给前沿 LLM 加一层本地隐私内核</h1>

<p align="center">用 Claude / GPT / Gemini，但数据不离开本机。</p>

<p align="center">
  <img src="https://img.shields.io/badge/Privacy-Pre--wire%20Enforcement-0F172A?style=flat-square" alt="Pre-wire Enforcement" />
  <img src="https://img.shields.io/badge/Gemma%204-Local%20Trust%20Layer-0F9D58?style=flat-square" alt="Gemma 4 Trust Layer" />
  <img src="https://img.shields.io/badge/vLLM%20%2F%20Ollama-OpenAI%20Compatible-1F6FEB?style=flat-square" alt="vLLM / Ollama OpenAI Compatible" />
  <img src="https://img.shields.io/badge/Multi--Agent-6%20local%20components-7C3AED?style=flat-square" alt="Multi-Agent 6 local components" />
  <img src="https://img.shields.io/badge/Remote%20LLM-Claude%20%7C%20GPT%20%7C%20Gemini-8B5CF6?style=flat-square" alt="Remote LLM Claude GPT Gemini" />
  <img src="https://img.shields.io/badge/Python-3.11%2B-3776AB?style=flat-square" alt="Python 3.11+" />
  <img src="https://img.shields.io/badge/License-MIT-16A34A?style=flat-square" alt="MIT License" />
</p>

<p align="center"><a href="README.md">English</a> | <strong>简体中文</strong></p>

<p align="center"><sub>基于 <a href="https://github.com/HKUDS/nanobot">nanobot</a> 构建 · 已提交至 <strong>Gemma 4 Good Hackathon</strong>（Kaggle，2026 年 5 月）</sub></p>

---

## TL;DR

前沿 LLM 已经成了承重的生产力工具，但发出去的数据一旦上线就无法收回。CloakBot 把执行点前移到「上线之前」：基于 **Gemma 4 E2B** 的本地隐私内核负责识别敏感片段、分配稳定的带类型占位符、给图像打码、把长文档分片处理，并在本地通过会话级 Vault 把响应还原。远端 LLM 可以随意替换——Claude、GPT、Gemini 都能直接消费脱敏后的请求流。

> **2,872 条实体级回归测试作为存证**，分布在三层泄漏 eval —— `7.98%` 配对泄漏（文本）· `1.11%` 跨度泄漏（图像）· `6.26%` 配对泄漏（长文档）· `97.14%` 跨轮占位符一致性。

---

## 60 秒上手

```bash
# 一次性: curl -fsSL https://ollama.com/install.sh | sh
# 一次性: WebUI 前端要 Node ≥24  (nvm install 24  或  brew install node@24)
# 一次性: uv sync && cd webui && npm install && cd ..

bash scripts/quickstart_demo.sh
```

这条脚本会拉起 `gemma4:e2b` 的 Ollama 实例、生成 `.env`、启动 WebUI（网关 `:8000`、前端 `:5173`），并自动打开浏览器。把 [`docs/demo/demo_onboarding_memo.md`](docs/demo/demo_onboarding_memo.md) 拖进 Composer，就能看到 20 条 PII 实体从头到尾被替换为带类型的占位符；点任意气泡上的 **Diff** 按钮可以对比「本地 ↔ 远端」两种视图。

更完整的配置（GPU 上跑 vLLM、模型下载、自定义参数）见下文 [§ 安装与启动](#安装与启动)。

---

## 目录

- [运行流程](#运行流程)
- [检测范围](#检测范围)
- [为什么用小型 LLM，而不是正则或 BERT-NER？](#为什么用小型-llm而不是正则或-bert-ner)
- [多智能体架构](#多智能体架构)
- [Evals —— 以测量建立信任](#evals--以测量建立信任)
- [安装与启动](#安装与启动)
- [路线图](#路线图)
- [设计取舍](#设计取舍)
- [Hackathon 赛道](#hackathon-赛道)
- [致谢与许可证](#致谢与许可证)

---

## 运行流程

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

检测器拆成两路：`GeneralPrivacyDetector` 负责非可计算的文本片段，`DigitPrivacyDetector` 负责数字 / 时间值并做归一化，方便后续在本地做数学执行。

### Token 规则

格式为 `<<ENTITY_TYPE_INDEX>>`，按类型独立编号——远端 LLM 仍能识别关系（比如 `PERSON_1` 和 `PERSON_2` 是两个不同的人），但不会知道这两个人到底是谁。

| 原始值 | Token |
|---|---|
| `Alice Chen` | `<<PERSON_1>>` |
| `alice@acme.com` | `<<EMAIL_1>>` |
| `555-123-4567` | `<<PHONE_1>>` |
| `123-45-6789` | `<<ID_1>>` |
| `$142,500` | `<<FINANCE_1>>` |
| `December 15, 2026` | `<<DATE_1>>` |
| `Metformin 500mg` | `<<MEDICAL_1>>` |

---

## 为什么用小型 LLM，而不是正则或 BERT-NER？

**一句话——正则只能搞定容易的那 20%，剩下 80% 必须看上下文。** CloakBot 两条路都走：正则跑快速通道（邮箱、发票号、交易号、文件路径——手写在 [`privacy/core/detection/`](cloakbot/privacy/core/detection/) 和 [`visual_redaction.py`](cloakbot/privacy/visual_redaction.py) 里），剩下所有正则和 BERT-NER 搞不定的事情，全部交给 Gemma 4 E2B。

### 正则和 BERT-NER 做不到的事情

| 失败场景 | 正则 | BERT-NER (Presidio, spaCy) | **Gemma 4 E2B** |
|---|:---:|:---:|:---:|
| 已知格式——邮箱、SSN、信用卡 | ✓ | ✓ | ✓ |
| 区分 `"John"` 是占位符还是真实客户 | ✗ | ✗ | ✓ |
| 组合标识——*「住在 90210 邮编的 67 岁糖尿病男性」* | ✗ | ✗ | ✓ |
| 用户自定义实体——*「项目代号 Falcon 也要脱敏」* | 改正则 | 重训模型 | 改 prompt |
| 领域漂移——chat 日志 vs NER 训练用的新闻语料 | 不适用 | 召回降 20–40% | 鲁棒 |
| 多语言（中 / 日 / 韩 / 英）在一个模型里 | 每个语种一套正则 | 每种语言 600 MB+ | 一个 2B 模型 |
| 间接标识——*「上次提到的那个病人」* | ✗ | ✗ | ✓ |

### 这些失败场景为什么要紧

Presidio 那一套出来的是「只能拦住简单情况的 PII 代理」——这种东西**比完全没有代理更糟糕**，因为用户会信任它。把执行点前移到「上线之前」，门槛不是模式匹配，而是要判断**在这次具体对话里**这个 token 到底该不该被遮蔽。这是一个生成式 LLM 形状的问题。

### 为什么偏偏是 Gemma 4 E2B

同时满足以下五条的可商用再分发模型，只有 Gemma 4 E2B：

1. **能塞进消费级硬件**——2B 参数、量化后约 5 GB，一台 MacBook 通过 Ollama 就能跑。
2. **T=0 下能稳出可解析 JSON**——无需微调就能做跨度级实体抽取。
3. **同一套权重原生多模态**——OCR 抽出来的文本和直接对图像做推理用的是同一个模型。
4. **覆盖 CloakBot 用户的语言**——Gemma 4 开箱多语言，不用按 locale 换模型。
5. **有商业许可**——诊所、银行、律所部署不用付按席位费。

> **这也是一个 Gemma 4 hackathon。** 如果让 Presidio + BERT 顶上主流程、Gemma 只当一个 chat 改写器，那其实没真正展示 Gemma 的能力。CloakBot 把 Gemma 放在「信任决策实际发生的地方」——**信任层就是这个模型**。

### 老实交代代价

Gemma 单次检测调用约 50–200 ms（在 RTX 5090 上经 vLLM 实测），正则不到 1 ms。CloakBot 用三件事来抵消差距：(a) general + digit 检测器并发跑、(b) 已知格式留给正则走快通道、(c) 长文档分块并发。最终效果：HR 类 p95 约 0.9 秒，医疗类（实体密度高）p95 约 6 秒（详见 [Evals](#evals--以测量建立信任)）。MacBook（Ollama）部署路径端到端能跑通但更慢。流式 + 每轮 batch 是下一个里程碑。

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

### 组件清单

| 组件 | 职责 | 后端 |
|---|---|---|
| `PrivacyRuntime` | 每轮的协调器：脱敏、路由、还原、审计 | Python |
| `PiiDetector` | General + digit + intent 三个检测器并发跑，再去重 | Gemma 4 E2B |
| `IntentAnalyzer` | 把每轮分类成 `chat` 或 `math` | Gemma 4 E2B |
| `ToolPrivacyInterceptor` | 工具 I/O 还原；按敏感度走审批；输出脱敏（含 `read_file` / web_fetch / MCP） | 规则 + 检测器 |
| `ToolPrivacyDetector` + `chunking/` | 长文档通道：内容感知 chunker（纯文本 / JSON / HTML / Markdown）、分块并发 + 超时、跨块 Vault 合流、fail-closed | Gemma 4 E2B |
| `VisualPrivacyPipeline` | OCR + bbox 涂黑 + 在每条黑条**内部**渲染占位符文本 + 跨模态召回桥（文本端实体作为视觉 needle 喂入） | Gemma 4 E2B + Pillow + Tesseract |
| `process_user_document` | WebUI 文档上传（text/plain、text/markdown ≤ 64 KB）走同一条 chunker 脱敏路径 | Gemma 4 E2B |
| `Session Vault` | 可审计的「占位符 ↔ 原值」映射，跨轮复用别名（PERSON + ORG 子串、NFKC 归一化） | JSON 落盘 |
| `Math Executor` | 本地执行远端生成的 `<python_snippet_N>` 块；AST 校验、仅允许算术 | Python AST 沙箱 |
| `Transparency Report` | 每轮一份 markdown 脱敏摘要 | 规则 |

完整文件结构见 [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)。

---

## Evals —— 以测量建立信任

我们不接受「靠声明赢得信任」。三层端到端泄漏 eval 直接跑在**生产代码路径**上，每轮只回答一个问题：*这一轮里，有没有任何一个 ground-truth 的可识别 token 出现在上传 payload 里？*

| 层 | 覆盖 | 关键指标 | 跨轮别名 |
|---|---|---|---:|
| **A1 —— 文本输入** | 4 个领域 × 20 个会话 × 902 个实体-轮 pair | **7.98%** pair 泄漏 · **5.88%** token 泄漏 | **97.14%** |
| **A2 —— 视觉** | 10 个发票种子 × 180 个 PII 跨度 × 197 个涂黑框 | **1.11%** 跨度泄漏 · **1.01%** token 泄漏 | 不适用 |
| **A3 —— 长文档** | 3 个领域 × 20 个会话 × 1,790 个 pair（走 chunker） | **6.26%** pair 泄漏 · **6.63%** token 泄漏 | **93.86%** |

- **跨领域 100% pair 召回**——`EMAIL · PHONE · FINANCE · IP · URL`
- **MEDICAL 召回：20% → 95%**——靠类型驱动的 prompt 迭代（规则 → 类型相邻示例）
- **226 个 A3 seam 泄漏中 0 个**落在 chunker 300 字符的重叠带里——边界启发式覆盖率 100%；剩下的长文档泄漏全部是块内检测漏召，而不是 seam 处掉链子

完整的逐模板拆分、方法学，以及我们自己抓出来的 eval bug 见 [`docs/HACKATHON_WRITEUP_DRAFT.md`](docs/HACKATHON_WRITEUP_DRAFT.md)。复现方式：每层一条命令，runner 都在 `tests/eval/runners/` 下。

> *所有 p95 延迟数字都是用 Gemma 4 E2B 经 vLLM 部署在 RTX 5090 上实测得到的。MacBook（Ollama）部署路径端到端能跑通，但延迟更慢 —— MacBook 是目标部署硬件，不是测量平台。*

---

## 安装与启动

### 1. 克隆并安装

```bash
git clone https://github.com/spire-studio/cloakbot.git && cd cloakbot
uv sync
# WebUI 前端要 Node ≥24 —— `nvm install 24` 或 `brew install node@24`
cd webui && npm install && cd ..
```

### 2. 配置

```bash
cp .env.example .env
# .env.example 里写了两个 profile —— 二选一:
#   Profile A —— GPU 机器上的 vLLM
#   Profile B —— Ollama (不需要 GPU)
```

把远端 LLM（Claude、GPT、Gemini 等）写入 `~/.cloakbot/config.json`，或者直接跑：

```bash
uv run python -m cloakbot onboard
```

### 3. 启动本地 Gemma 4 后端 —— 二选一

两个后端 CloakBot 都用同一个 OpenAI 兼容客户端，所以 `.env` 里那三个 `GEMMA_*` 变量（`GEMMA_BASE_URL` / `GEMMA_API_KEY` / `GEMMA_MODEL`）对两个 profile 都生效。

#### 方案 A：vLLM（Ubuntu / GPU 机器）—— 快、可复现

```bash
uv sync --extra vllm
uv run huggingface-cli login          # 在 hf.co/google/gemma-4-E2B-it 接受 Gemma 协议
bash scripts/start_vllm.sh             # 从 .env 读取 GEMMA_API_KEY / GEMMA_MODEL
```

A1 / A2 / A3 三份 eval 报告就是用这条路径跑出来的。

#### 方案 B：Ollama（macOS / Linux / WSL）—— 无需 GPU

```bash
# 一次性: curl -fsSL https://ollama.com/install.sh | sh
bash scripts/start_ollama.sh
```

脚本会拉取 `gemma4:e2b`（约 5 GB）、启动 daemon、预热模型。然后在 `.env` 里：

```
GEMMA_BASE_URL=http://127.0.0.1:11434/v1
GEMMA_API_KEY=ollama        # Ollama 不强制鉴权，随便填什么都行
GEMMA_MODEL=gemma4:e2b
```

面向真实场景部署，我们推荐这条路径——隐私内核能在 MacBook 上跑。

> 两个后端暴露的都是同样的 OpenAI 兼容接口。CloakBot 的脱敏器只把它用于 PII 检测；远端 LLM 调用（Claude / GPT / Gemini）完全是另一条路径。

### 4. 启动 WebUI

```bash
uv run python -m cloakbot webui
# 网关    http://127.0.0.1:8000
# 前端    http://127.0.0.1:5173
```

也可以直接用 `bash scripts/quickstart_demo.sh` 一步到位。

---

## 路线图

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
- ✓ Ollama 升级为一等公民后端（无需 GPU）+ 一键 demo 启动器

**以测量建立信任（v0.3）** —— 5 月
- ✓ 端到端泄漏 eval 框架（`tests/eval/runners/`）
- ✓ A1 / A2 / A3 三层 —— **2,872 条实体级回归测试**作为存证
- ✓ 类型驱动的检测器 prompt（MEDICAL 召回 20% → 95%）
- ✓ 自己抓出来并修掉的 eval bug（token 级打分；全值出现匹配收紧）

### 🚀 接下来

- **领域专用 LoRA adapter** —— 在垂直语料（医疗、法律、金融）上微调 Gemma 4 E2B，提升领域短语（如 `stage 2 chronic kidney disease`、`Turner Ltd` 这种短 ORG 名）的召回，解锁带策略的垂直部署。一套内核 + 三个 adapter：按租户挑。
- **短 ORG / 连字符名召回**（71.67% → 90% 目标）—— A1 当前最大缺口，可借上面的 LoRA 路径修
- **双语覆盖** —— 中文 eval 模板 + zh-CN 检测器 prompt 迭代
- **流式 + 每轮 batch** —— 把检测器并发和 token 流式叠在一起，目标把医疗 p95 从 6.2 秒压到 2 秒以下
- **Vault 加密落盘** —— 面向共享设备部署
- **策略驱动的敏感度分级** —— 超越当前注册表默认值（目前全部 `high`）
- **面向数据集 / 表格的结构化 chunker**（CSV / Parquet）—— 用于分析工具输出

---

## 设计取舍

**遮蔽 + Token 化，而不是假名化** —— `<<PERSON_1>>` 比「换成一个看起来像真人的假名字」既简单又安全。远端 LLM 仍能看出 `PERSON_1` 和 `PERSON_2` 之间的关系，但不会知道他们是谁。

**两个本地检测器、一个 Vault** —— CloakBot 把非可计算的文本片段和数字 / 时间片段分开处理，这样既能保住任务结构，又能在本地留下足够的归一化数据给后续的数学执行用。

**数学任务里，远端 LLM 只负责推理结构** —— 数学轮里要求远端模型用 `<python_snippet_N>` 块给出结构；最终的数值答案在本地基于 Vault 的原值算出来。

**基于 hook 的低侵入接入** —— 隐私层基本上隔离在 `cloakbot/privacy/` 下，通过 `pre_llm_hook` 和 `post_llm_hook` 接入主运行时，上游 nanobot loop 完全不用动。

**文档是工具来源的隐私数据** —— 没有独立的文档 worker；`read_file`、`web_fetch`、MCP 工具结果、WebUI 文档上传，全部走同一条 chunker 脱敏路径。一道信任边界，一个 Vault。

---

## Hackathon 赛道

- **主赛道 —— Gemma 4 Good（Safety & Trust 方向）** —— Gemma 4 E2B 作为本地隐私内核，在任何字节抵达远端 LLM 之前就执行一道「上线前」边界。背后是 A1（文本）、A2（视觉）、A3（长文档）三层泄漏 eval、共 2,872 条实体级回归测试作为存证 —— 详见 [`docs/HACKATHON_WRITEUP_DRAFT.md`](docs/HACKATHON_WRITEUP_DRAFT.md)。
- **Ollama 特别技术赛道** —— `bash scripts/start_ollama.sh` 一条命令同时拉起模型和 OpenAI 兼容接口 —— 不用折腾 GGUF，也不用按操作系统分叉 Metal / CUDA。**Gemma 4 是信任层，Ollama 是部署层。** 试一下：`bash scripts/quickstart_demo.sh`。

---

## 致谢与许可证

CloakBot 基于 HKUDS 的 [nanobot](https://github.com/HKUDS/nanobot)（MIT License）构建。频道接入、会话管理、记忆系统和 CLI 都来自上游框架。本仓库里 CloakBot 的隐私相关实现主要集中在 [`cloakbot/privacy/`](cloakbot/privacy/)、[`cloakbot/providers/vllm.py`](cloakbot/providers/vllm.py)，以及 [`cloakbot/agent/loop.py`](cloakbot/agent/loop.py) 中的 hook 接入点。

面向 agent 的架构、可靠性、安全与隐私域备注都在 [`docs/`](docs/) 下 —— 先看 [`AGENTS.md`](AGENTS.md)。

MIT License —— 见 [`LICENSE`](LICENSE)。
