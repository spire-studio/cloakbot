# CloakBot 协议化协作架构设计（方案 2: Protocol Hub）

## 1. 背景与目标

当前 CloakBot 在 `privacy` 子系统内已具备分层结构（`hooks / agents / core / transparency`）和可运行主流程，但协作形态仍以“函数调用 + 局部日志”为主，尚未形成统一协议面。该状态在单路径运行时可接受，但在跨组件演进（loop、tools、gateway、webui/api）中会出现可观测字段不一致、错误语义不统一、异步任务与主链路难关联的问题。

本设计目标是构建全项目统一的“协议化协作”架构，以 `Protocol Hub` 为协作中枢，实现以下优先级目标：

1. **A 阶段（最高优先）**：单次 turn 全链路可追踪（入口→路由→agent/tool→输出）。
2. **C 阶段**：跨组件统一指标与面板（privacy、loop、tool、gateway）。
3. **B 阶段**：跨 turn / 跨会话审计回放。

执行模式采用 **混合模式**：用户主路径同步执行，重任务异步调度。

## 2. 方案选择与取舍

### 2.1 候选方案

- 方案 1：轻量协议包裹层（最小改造）
- 方案 2：协议中枢（Protocol Hub）
- 方案 3：事件总线优先（分布式优先）

### 2.2 选型结论

采用 **方案 2（Protocol Hub）**。原因：

- 相比方案 1，能避免“局部可观测、全局碎片化”回潮。
- 相比方案 3，复杂度可控，不会在当前阶段引入过度分布式成本。
- 能在不破坏现有主路径的前提下，建立稳定契约，为后续演进保留接口。

## 3. 总体架构

### 3.1 新增中枢层

在 `AgentLoop` 与具体执行单元（privacy agents / tools / hooks）之间新增 `CollaborationProtocolHub`（简称 CPH）。

CPH 仅承担四类职责：

1. **协议标准化**：统一 turn/task/tool 的 envelope 与元数据头。
2. **路由与编排**：根据契约在同步主路径与异步任务间分流。
3. **可观测性注入**：统一 trace/span/event 产出。
4. **策略执行**：超时、重试、幂等、降级、熔断。

### 3.2 分层职责映射

- `hooks/`：保留入口/出口职责，只与 CPH 交互，不直接编排细节。
- `agents/`：升级为协议化 worker（实现统一 `AgentContract`）。
- `core/`：保持纯能力层（sanitize/vault/math），不耦合调度与观测。
- `transparency/`：改为消费结构化事件生成报告，不再依赖散点日志拼接。

### 3.3 混合同步/异步策略

- **同步主路径**：意图判定、隐私预处理、主模型调用、输出后处理。
- **异步路径**：文档解析、长工具链、批量检查、二次评估任务。
- 原则：仅保留用户即时可见且必须阻塞的步骤在同步路径，其余转 `DeferredTask`。

## 4. 协议契约设计

### 4.1 统一协议头（所有契约共享）

必填字段：

- `trace_id`
- `span_id`
- `session_id`
- `turn_id`
- `intent`
- `privacy_stage`
- `idempotency_key`
- `timestamp`
- `status`
- `error_code`

### 4.2 TurnContract（主链路）

```json
{
  "meta": {
    "trace_id": "uuid",
    "span_id": "uuid",
    "session_id": "string",
    "turn_id": "uuid",
    "idempotency_key": "string",
    "timestamp": "iso8601"
  },
  "context": {
    "intent": "chat|math|doc",
    "channel": "cli|gateway|webui|api",
    "privacy_stage": "raw|sanitized|postprocessed"
  },
  "payload": {
    "user_input": "string",
    "sanitized_input": "string|null",
    "agent_hint": "string|null"
  }
}
```

### 4.3 AgentTaskContract（子任务）

```json
{
  "meta": { "trace_id": "...", "span_id": "...", "parent_span_id": "..." },
  "task": {
    "task_id": "uuid",
    "task_type": "intent_analysis|math_exec|doc_parse|tool_chain",
    "mode": "sync|async",
    "priority": "p0|p1|p2",
    "deadline_ms": 3000
  },
  "input": { "data_ref": "inline_or_pointer" }
}
```

### 4.4 ToolInvocationContract（工具调用）

```json
{
  "meta": { "trace_id": "...", "span_id": "...", "tool_span_id": "..." },
  "tool": {
    "name": "bash|web|fs|custom",
    "version": "semver",
    "timeout_ms": 5000
  },
  "input": { "args": {} },
  "privacy": {
    "sanitize_before": true,
    "sanitize_after": true
  }
}
```

## 5. Protocol Hub 组件清单

1. **ProtocolGateway**：接入统一入口，封装 `TurnEnvelope`，补全元数据。
2. **ContractRouter**：按 `intent + task_type + stage` 路由 sync/async。
3. **AgentRuntimeAdapter**：将现有 agent 适配到统一 `AgentContract`。
4. **ToolRuntimeAdapter**：统一工具执行前后事件、错误与脱敏后置链。
5. **PolicyEngine**：执行 timeout/retry/idempotency/fallback/circuit。
6. **ObservabilityEmitter**：统一发送 structured events/metrics/traces。

## 6. 事件语义（Event Taxonomy）

### 6.1 Turn 生命周期事件（必须）

- `turn.received`
- `turn.intent.classified`
- `turn.sanitize.started|succeeded|failed`
- `turn.agent.dispatch.started|completed|failed`
- `turn.restore.started|completed|failed`
- `turn.completed`

### 6.2 任务事件

- `task.created`
- `task.queued`（async）
- `task.started`
- `task.retried`
- `task.timed_out`
- `task.completed`
- `task.failed`

### 6.3 工具事件

- `tool.invocation.started`
- `tool.invocation.completed`
- `tool.output.sanitized`
- `tool.invocation.failed`

### 6.4 策略事件

- `policy.retry.applied`
- `policy.fallback.applied`
- `policy.idempotency.hit`
- `policy.circuit.opened`

### 6.5 事件约束

- 任何节点不得仅输出自由文本日志；必须发结构化事件。
- 事件需带 `event_version`，保证下游消费者升级兼容。
- 异步任务必须回写同一 `trace_id`。

## 7. 错误处理与可靠性

### 7.1 统一错误模型

所有异常在协议层统一映射为 `ProtocolError`，最少包含：

- `error_code`
- `retryable`
- `stage`
- `origin`（agent/tool/core）

建议错误码示例：

- `PRIVACY_SANITIZE_FAIL`
- `INTENT_CLASSIFY_FAIL`
- `TOOL_TIMEOUT`
- `ASYNC_QUEUE_OVERFLOW`

### 7.2 幂等与重试

建议幂等键：

`idempotency_key = session_id + turn_id + stage + hash(payload)`

规则：

- 仅 `retryable=true` 的阶段允许自动重试。
- 重试需发 `task.retried` 并记录 `attempt/backoff_ms`。
- 有副作用的工具调用必须显式声明“不自动重试”。

### 7.3 超时与降级

- 每个同步阶段定义 `deadline_ms`。
- 超时触发显式降级（如 intent fallback=chat）。
- 降级必须发 `policy.fallback.applied`，不可静默。

### 7.4 失败隔离

- 异步任务失败不阻塞主回复。
- 失败结果必须可追踪且可查询（同 trace 下可见）。
- 连续失败触发熔断并事件化。

## 8. 测试与验收

### 8.1 契约测试（优先级最高）

- schema 必填字段与类型校验
- 版本兼容校验
- adapter 一致性校验

### 8.2 可观测性回归测试

验证每个 turn 均可获得关键事件链：

`received -> sanitize -> dispatch -> restore -> completed`

并校验字段：`trace_id/turn_id/stage/status/duration`。

### 8.3 混合集成测试

- 同步链路 + 异步任务并发
- trace 关联正确性
- 主路径时延不被异步污染

### 8.4 故障注入

注入 timeout、invalid json、tool failure、vault io failure，验证重试/降级/熔断行为和事件一致。

## 9. 分阶段实施路线（A -> C -> B）

### Phase A（单 turn 可追踪）

交付：

- TurnContract 与最小事件 taxonomy
- ObservabilityEmitter 接入主链路
- privacy 主流程关键节点全部事件化

验收：

- 任意 turn 可重建时序与耗时分解

### Phase C（统一指标面板）

交付：

- 标准指标：阶段时延、错误率、重试率、降级率、工具成功率
- 跨组件 dashboard

验收：

- 可按 stage/agent/tool 直接定位瓶颈

### Phase B（会话审计回放）

交付：

- SessionTraceIndex
- 事件持久化查询层
- session 级回放视图

验收：

- 给定 `session_id` 可回放关键协作路径与策略动作

## 10. 与现有目录的映射建议

建议新增目录（示意）：

- `cloakbot/protocol/`
  - `hub.py`
  - `contracts.py`
  - `router.py`
  - `policy.py`
  - `observability.py`
  - `errors.py`
  - `adapters/agent_adapter.py`
  - `adapters/tool_adapter.py`

现有目录职责保持不变：

- `privacy/core` 保持纯能力
- `privacy/agents` 聚焦业务 agent 逻辑
- `privacy/hooks` 仅做入口桥接
- `privacy/transparency` 改为消费标准事件

## 11. 非目标（当前阶段不做）

- 不强制引入外部消息队列作为必需依赖
- 不拆分为跨进程微服务
- 不在本轮变更中重写全部历史日志系统

## 12. 风险与缓解

1. **风险：协议字段扩张失控**
   - 缓解：字段最小集 + 版本化 + 兼容规则。
2. **风险：事件量增加影响性能**
   - 缓解：异步批量发送、采样、分级日志。
3. **风险：迁移期双通道（旧日志+新事件）造成认知负担**
   - 缓解：设定阶段性切换点，逐步收敛到事件单一事实源。

## 13. 结论

该设计将 CloakBot 从“可运行的编排式 agent 实现”升级为“可治理的协议化协作系统”：

- 保持当前工程复杂度可控
- 优先满足单 turn 可追踪能力
- 为统一指标与审计回放提供稳定基础
- 兼容后续向更强事件驱动架构演进
