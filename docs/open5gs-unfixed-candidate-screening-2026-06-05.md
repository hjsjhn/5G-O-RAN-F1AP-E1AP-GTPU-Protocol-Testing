# Open5GS 当前 Digest 未修候选筛选

> 日期：2026-06-05
> 分支关注：`feature/replay-issue-dashboard`
> 目标版本：`Open5GS daemon v2.7.6-131-g782a97e`
> 目标 commit：`782a97efe9e3acb1251e318bd3738ced4044dac8`
> 目标 commit 时间：`2025-12-06T13:23:34Z`

## 文档目的

这份文档只回答一个问题：

> 对当前课程项目固定的 Open5GS digest 来说，哪些 issue/PR/commit 的修复晚于
> `782a97e`，因此“当前测试镜像可能仍未修”，适合做协议输入构造、回放、自动验证？

筛选原则：

- 主候选只收录修复时间晚于 `2025-12-06` 的条目。
- 早于该时间、且按 `main` 合并时序已包含在 `782a97e` 之前的条目，统一归为 regression。
- 优先 5G SA 主线相关组件和入口：
  - 组件：`AMF`、`SMF`、`UPF`、`NRF`、`SCP`
  - 入口：`NGAP`、`NAS`、`SBI`、`PFCP`、`GTP-U`、`GTP-C`
- 排除：
  - 安装、WebUI、纯配置问题
  - 明显只影响 LTE 且与当前 5G 主线无关的问题
  - 必须依赖真实手机、复杂无线条件、完整 handover 才能落地的问题

## 当前项目环境

- Open5GS Docker / OrbStack
- RAN：`srsRAN CU-CP / CU-UP / DU split`
- 已具备：
  - `GTP-U JSON -> pcap -> live replay`
  - `F1AP / E1AP JSON-driven peer validation`
  - `NGAP / Open5GS mutation` 入口
  - 两条完整 UE flow 自动测试
- 明确边界：
  - `XnAP` 只做离线解析 / 构造
  - 不依赖完整 handover、多 gNB、真实手机、复杂无线条件作为首批 testcase 前提

## 结论摘要

- `#3727`、`#3622`、`#3497` 不应再作为主候选；它们已在更早版本修复，更适合作 regression。
- `#4179`、`#4180` 不列为主候选。结合已知修复时间在 `2025-12-05` 左右，而当前 digest 时间是 `2025-12-06`，它们更接近“已修或应按回归边界对待”。
- 当前最适合优先工程化的主候选是：
  - `#4333` SBI `requester-features` 解析 DoS
  - `#4289` AMF deregistration 后立刻 re-registration 的晚到 SBI 响应 crash
  - `#4327` PFCP Session Modification 中 `Create FAR/QER/URR` 互通/健壮性问题

## 表 1：当前 digest 可能未修的主候选

| Issue/PR/Commit | 修复时间 | 是否晚于 782a97e | 组件 | 协议入口 | 问题摘要 | 触发思路 | 当前环境可行性 | 难度 | 展示价值 | 风险 | URL |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `#4333` / commit `234da30` | 2026-02-28 | 是 | NRF / core SBI | SBI HTTP/2 | `requester-features` 解析时整型溢出可导致 `FATAL`/abort，PR 明确为 remote DoS | 直接向 `nrfd` 发 `nnrf-disc` 请求，给超长十六进制 `requester-features` | 很高；不依赖 UE、不依赖 PDU Session，Docker 单点即可 | 低 | 很高 | 低 | [Issue #4263](https://github.com/open5gs/open5gs/issues/4263), [PR #4333](https://github.com/open5gs/open5gs/pull/4333) |
| `#4532` | open as of 2026-06-05 | 是 | SMF | SBI HTTP/2 | `POST /nsmf-pdusession/v1/sm-contexts` 中 `supi=""` 会触发 hash key 长度为 0 的 fatal assertion | 直接向 `smfd` 发 SM Context Create JSON，`supi` 置为空字符串 | 很高；不依赖 UE、不依赖 PDU Session，Docker 单点即可 | 低 | 很高 | 低 | [Issue #4532](https://github.com/open5gs/open5gs/issues/4532) |
| `#4289` / commit `73676a7` | 2026-01-23 | 是 | AMF | NAS + NGAP + SBI | UE 发起 deregistration 后立即重新 registration，晚到的 `SDM_SUBSCRIPTIONS DELETE` 响应会进入错误状态并触发 crash | 用现有 UE flow：注册后发起 deregistration，立刻二次 registration，并延迟 UDM/SMF 相关 SBI 回包 | 高；现有 UE flow 与 Open5GS mutation 能支撑 | 中 | 很高 | 中 | [PR #4289](https://github.com/open5gs/open5gs/pull/4289) |
| `#4327` / commit `c42d7b7` | 2026-03-10 | 是 | UPF / PFCP | PFCP Session Modification | 旧实现对 `Create FAR/QER/URR` 只 `find()` 不 `find_or_add()`，会导致 PFCP error、GTP-U Error Indication、会话 teardown | 先建立最小 session，再发只带 `CreateFAR/CreateQER/CreateURR` 的 Session Modification，或发重复 remove | 很高；和现有 PFCP/GTP-U 工具链贴合 | 中 | 高 | 低 | [PR #4327](https://github.com/open5gs/open5gs/pull/4327) |
| `#4346` / commit `dd7c518` | 2026-03-05 | 是 | AMF | NGAP + SBI | `SM Context Update` 与 NG context release / 新 registration 交叠时，异步 SBI 响应可能关联到错误 `RAN-UE` 并触发 assert | 在 `UEContextReleaseRequest`、重新注册、PDU update 之间人为引入 SBI 延迟/乱序 | 中 | 中高 | 高 | 中高 | [PR #4346](https://github.com/open5gs/open5gs/pull/4346) |

### 已试但暂不主打：PR `#4365`

PR `#4365` 修复时间晚于当前 digest，表面上适合做 GTP malformed IE crash testcase。但在当前 5GC
baseline 中，SMF 虽然监听 GTP-C `2123/udp`，实际 Gn/Gx 侧上下文不完整。用最小
GTPv1-C `CreatePDPContextRequest` 逐步补齐 TEID Data I、SGSN address、QoS profile、RAT type
后，SMF 仍停在 `No Selection Mode`、`No MSISDN`、`No Gx Diameter Peer`，未触发目标 malformed IE
crash 路径。结论：`#4365` 仍可作为后续 EPC/Gn/Gx 扩展候选，但不适合作为当前 Docker
baseline 的第二个明显 crash 展示。

## 表 2：已修复，只适合 regression 的候选

| Issue/PR/Commit | 修复版本/时间 | 为什么当前 digest 已包含修复 | 组件 | 协议入口 | 可做的 regression 测试 | URL |
|---|---|---|---|---|---|---|
| `#3727` / `#3739` | `v2.7.5` | `v2.7.5` release 已包含该修复，当前 digest 晚于该 release 很多提交 | UPF | PFCP | 发送非法 `PDN Type=0` 的 PFCP Session Establishment，验证不 crash，只返回错误或安全拒绝 | [Issue #3727](https://github.com/open5gs/open5gs/issues/3727) |
| `#3622` / `#3623` | `v2.7.5` | `v2.7.5` release 已包含该修复，当前 digest 已在其后 | AMF | NGAP + NAS | 构造 malformed Registration / InitialUEMessage，验证不再 heap overflow 或 crash | [Issue #3622](https://github.com/open5gs/open5gs/issues/3622) |
| `#3497` / `#3515` | `v2.7.5` | `v2.7.5` release 已包含 `[PFCP] Fix memory free issue causing crash` | SMF / UPF | PFCP | 发异常 PFCP 序列或洪泛，验证 association、session 和 baseline 恢复性 | [Issue #3497](https://github.com/open5gs/open5gs/issues/3497) |
| `#4081` | 2025-09-17 | PR merged 时间早于 `2025-12-06`，按主分支时序推断已包含在当前 digest | AMF / SBI | SBI HTTP methods + timer callback | 对 AMF 注入异常 `PATCH/DELETE` SBI 请求、连接超时、定时器回调乱序，验证不 crash | [PR #4081](https://github.com/open5gs/open5gs/pull/4081) |
| `#4091` | 2025-09-24 | PR merged 时间早于当前 digest | AMF/MME | NGAP/S1AP IE 长度 | 构造 NGAP IE 长度畸形包，验证 Error Indication / 拒绝，而不是 crash | [PR #4091](https://github.com/open5gs/open5gs/pull/4091) |
| `#4178` | 2025-11-26 | PR merged 时间早于当前 digest | AMF | SBI 异步响应 + RAN-UE 关联 | 做 RAN-UE 关联 race regression，验证旧类问题不再触发 | [PR #4178](https://github.com/open5gs/open5gs/pull/4178) |
| `#4191` | 2025-12-03 | PR merged 时间早于当前 digest，距离 `782a97e` 仅 3 天 | AMF | NAS Deregistration + SBI timeout | 大量 deregistration / timeout 场景下验证 AMF 仍存活 | [PR #4191](https://github.com/open5gs/open5gs/pull/4191) |

## Top 3 主推荐

### 1. `#4333` NRF `requester-features` 溢出 DoS

为什么它可能影响当前 `v2.7.6-131-g782a97e`：

- 修复 PR `#4333` 于 `2026-02-28` 合入，明显晚于 `782a97e`。

是否能在 Docker/Open5GS 环境独立触发：

- 能。
- 直接打 `NRF` 的 SBI 接口，不需要 UE、RAN、handover。

是否需要已有 UE/PDU Session 状态：

- 不需要。

需要构造哪类输入：

- `SBI HTTP`
- 最直接是：
  - `GET /nnrf-disc/v1/nf-instances`
  - 携带超长十六进制 `requester-features`

预期观察指标：

- `nrfd` 进程 crash
- `FATAL` 日志
- 容器重启
- 健康检查失败
- 修复后应表现为 `400` 或安全拒绝

若复现失败，如何作为边界报告展示：

- 可写成“当前镜像疑似已有 backport 或已具备修复后行为”
- 展示同一输入下：
  - HTTP 返回码
  - 日志差异
  - 进程是否继续存活

工程化建议：

- 写一个最小 `sbi-http-runner`
- 支持：
  - HTTP/2 prior knowledge
  - query 参数模板
  - 单请求后抓取容器健康状态
- testcase JSON 建议字段：
  - 目标 NF
  - path
  - query 参数
  - 预期结果：`crash` / `safe_reject`
- 健康检查：
  - `nrfd` 进程存活
  - 端口探活
  - 日志 grep `FATAL|assert|SIGABRT`

### 2. `#4289` deregistration 后立刻 re-registration 的 AMF crash

为什么它可能影响当前 `v2.7.6-131-g782a97e`：

- 修复 PR `#4289` 于 `2026-01-23` 合入，晚于当前 digest。

是否能在 Docker/Open5GS 环境独立触发：

- 能，但依赖现有 UE 自动流程。
- 不需要真实手机。

是否需要已有 UE/PDU Session 状态：

- 不一定。
- PR 说明修复覆盖了“有/无 active PDU session”两种情况。
- 建议先做无 PDU session 版，再做有 PDU session 版。

需要构造哪类输入：

- `NAS + NGAP`
- 同时对 `SBI` 响应做延迟控制
- 核心时序：
  - 注册
  - UE 发 `Deregistration`
  - 立即再次 `Registration`

预期观察指标：

- `amfd` crash
- assert / fatal log
- 未 crash 时也要观察：
  - 异常状态日志
  - 重复 UE context
  - 注册失败

若复现失败，如何作为边界报告展示：

- 可以展示“race window 存在，但当前环境未稳定击中”
- 记录每次：
  - 时序参数
  - SBI 延迟
  - AMF 状态日志
- 作为“时序敏感缺陷”的边界矩阵展示

工程化建议：

- 写一个 `amf-race-runner`
- 编排：
  - 运行现有 UE flow
  - 注入 deregistration
  - 对 UDM/SMF 的 DELETE/Release 响应做人为延迟
  - 立即发第二次 registration
- testcase JSON 建议描述：
  - 步骤序列
  - 相对时间
  - 每条 SBI 响应延迟
- 健康检查：
  - `amfd` 存活
  - UE 是否重新注册成功
  - 日志中是否出现 stale SBI response / assert

### 3. `#4327` PFCP Session Modification 中 `Create FAR/QER/URR` 互通失败

为什么它可能影响当前 `v2.7.6-131-g782a97e`：

- 修复 PR `#4327` 于 `2026-03-10` 合入，当前 digest 不包含。

是否能在 Docker/Open5GS 环境独立触发：

- 能。
- 主要依赖 PFCP，不需要真实空口。

是否需要已有 UE/PDU Session 状态：

- 需要一个已有 PFCP session 或最小 PDU session 状态。

需要构造哪类输入：

- `PFCP`
- 重点是 `Session Modification Request`
- 子场景：
  - 只带 `CreateFAR/CreateQER/CreateURR`
  - 这些 ID 之前未由 PDR 预建
  - 重复 remove 同一对象

预期观察指标：

- 不一定 crash
- 更可能出现：
  - PFCP error
  - `GTP-U Error Indication`
  - 会话 teardown
  - 用户面中断
- 修复后应更偏向接受或幂等处理

若复现失败，如何作为边界报告展示：

- 如果当前镜像已能容忍这些输入，可展示为“与上游修复后行为一致”
- 如果只是拒绝但不 crash，也可以作为“协议互通负例”展示

工程化建议：

- 写一个 `pfcp-session-mod-runner`
- 支持：
  - 建立最小 session
  - 注入 modification
  - 断言 PFCP cause、UPF/SMF 日志、GTP-U 连通性
- testcase JSON 建议字段：
  - `create_qer_ids`
  - `create_far_ids`
  - `create_urr_ids`
  - `remove_ops`
- 健康检查：
  - UPF/SMF 存活
  - PFCP association 保持
  - 既有 UE ping 或业务流是否中断

## 备选但不作为首批主推

### `#4346` AMF `SM Context Update` / `RAN-UE` race

- 价值高，且修复时间晚于当前 digest
- 但比 `#4289` 更依赖时序窗口
- 更适合在 AMF race runner 初版跑通后追加

## 执行建议

首批 2 到 3 个自动 testcase 建议按这个顺序推进：

1. `#4333`
   - 单请求
   - 单网元
   - 最容易形成 crash / safe reject 演示
2. `#4289`
   - 覆盖 5G SA 主线 AMF 控制面 race
   - 能体现 UE flow + SBI 时序编排能力
3. `#4327`
   - 覆盖 PFCP 互通与健壮性
   - 能与现有 GTP-U / PFCP 能力直接结合

## 参考来源

- [Open5GS Releases](https://github.com/open5gs/open5gs/releases)
- [Commit `782a97e`](https://github.com/open5gs/open5gs/commit/782a97efe9e3acb1251e318bd3738ced4044dac8)
- [PR #4333](https://github.com/open5gs/open5gs/pull/4333)
- [Issue #4263](https://github.com/open5gs/open5gs/issues/4263)
- [PR #4289](https://github.com/open5gs/open5gs/pull/4289)
- [PR #4327](https://github.com/open5gs/open5gs/pull/4327)
- [PR #4346](https://github.com/open5gs/open5gs/pull/4346)
- [PR #4081](https://github.com/open5gs/open5gs/pull/4081)
- [PR #4091](https://github.com/open5gs/open5gs/pull/4091)
- [PR #4178](https://github.com/open5gs/open5gs/pull/4178)
- [PR #4191](https://github.com/open5gs/open5gs/pull/4191)
