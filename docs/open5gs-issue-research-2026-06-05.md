# Open5GS Issue 调研与 testcase 候选筛选

> 日期：2026-06-05
> 分支关注：`feature/replay-issue-dashboard`
> 调研目标：为“包修改 / 回放 / 验证网元行为”筛选适合课程项目的 Open5GS issue

## 调研范围

本次调研针对 Open5GS GitHub 上与 `v2.7.3` 到 `v2.7.6` 附近版本相关的 bug / security issue，重点筛选以下范围：

- 组件：`AMF`、`SMF`、`UPF`
- 协议入口：`NGAP`、`NAS`、`GTP-U`、`PFCP`、`SBI`
- 目标形式：构造或修改协议输入，回放到 Open5GS 网元，观察是否：
  - crash
  - assert
  - 输出安全拒绝
  - 导致健康检查失败
  - 能否自动恢复 baseline

排除项：

- 纯安装问题
- WebUI 问题
- 普通运营配置问题
- 明显依赖真实手机或复杂无线 handover 才能稳定复现的问题

## 当前项目环境

- Open5GS 容器内版本：`Open5GS daemon v2.7.6-131-g782a97e`
- Core 来源：`herlesupreeth/docker_open5gs`
- 运行环境：Docker / OrbStack
- RAN：`srsRAN CU-CP / CU-UP / DU split`
- 已具备能力：
  - `GTP-U JSON -> pcap -> live replay`
  - `F1AP / E1AP JSON-driven peer validation`
  - 两条完整 `UE flow` 自动测试
- 明确边界：
  - `XnAP` 只做离线解析 / 构造
  - 不把复杂 live handover 当作当前主展示路径

## 说明

- 下表中的“版本”以 issue 报告版本为主，不代表当前项目中的 `v2.7.6-131-g782a97e` 一定仍然受影响。
- 对于已经在后续 release notes 中出现修复项的 issue，更适合作为：
  - “当前版本是否仍会 crash”的回归测试
  - “当前版本是否安全拒绝 malformed input”的边界测试
- “协议入口”有少量条目是根据 issue 描述、日志和修复说明推断出来的。

## 候选 issue 一览

| Issue | 版本 | 组件 | 协议入口 | 问题摘要 | 触发思路 | 我们环境可行性 | 难度 | 展示价值 | 推荐程度 | URL |
|---|---|---|---|---|---|---|---|---|---|---|
| `#3727` Invalid `pdn_type=0` crashes UPF | 报告: `v2.7.2` | UPF | PFCP | PFCP Session Establishment 中将 `PDN Type` 设为 `0`，UPF 在 UE IP/session 处理路径崩溃 | 伪造或修改 `PFCP Session Establishment Request`，把 `PDN Type` 置为 0 | 很高；直接对 `UPF:8805/UDP` 发包即可 | 低 | 高 | 高 | [#3727](https://github.com/open5gs/open5gs/issues/3727) |
| `#3622` Malformed registration causes NAS heap overflow | 报告: `v2.7.2` | AMF | NGAP + NAS | 恶意 `InitialUEMessage / Registration Request` 可触发 NAS 5GS IE 解码越界 | 变异 `InitialUEMessage` 内 NAS Registration Request，重点改 UE security capability 等长度字段 | 很高；不依赖真实 UE 和 handover | 中 | 高 | 高 | [#3622](https://github.com/open5gs/open5gs/issues/3622) |
| `#3497` Crafted PFCP flood breaks PFCP association / session handling | 报告: `v2.7.1` | SMF / UPF | PFCP | 恶意 PFCP 包洪泛后，PFCP 关联或 session 处理异常，影响后续 PDU 建立/恢复 | 对 N4 注入伪造 PFCP 包，观察 association、error log、恢复行为 | 很高；适合做 baseline 恢复与稳健性验证 | 低-中 | 高 | 高 | [#3497](https://github.com/open5gs/open5gs/issues/3497) |
| `#3608` Stale `nausf-auth` response crashes AMF in `gmm_state_exception` | 报告: `v2.7.2` | AMF | NGAP + NAS + SBI | 多次注册 / 竞态时，旧认证流程的 SBI 响应落入异常状态，AMF 进入 fatal 路径 | 重放一段重复 Registration 的时序，制造旧上下文与新 AKA 交叉 | 中；偏序列竞态，不是单包 | 中 | 高 | 中高 | [#3608](https://github.com/open5gs/open5gs/issues/3608) |
| `#3613` Malformed registration triggers `namf-comm` crash in REGISTERED state | 报告: `v2.7.2` | AMF | NGAP + NAS + SBI | 变异注册诱发 UE context transfer，`namf-comm` 失败后状态机 fatal | 改 PLMN / NR CGI / 位置相关字段，诱发 `namf-comm` transfer 失败 | 中；最好先有 UE context | 中 | 高 | 中高 | [#3613](https://github.com/open5gs/open5gs/issues/3613) |
| `#3689` PFCP fragmentation attack | 报告: `v2.7.1` | UPF | PFCP | 分片 PFCP 包不应被接受，issue 反映 UPF 至少会记录异常甚至进入错误处理 | 构造 IP fragmentation，让 PFCP IE 跨片 | 中；需要额外实现分片生成 | 中高 | 高 | 中高 | [#3689](https://github.com/open5gs/open5gs/issues/3689) |
| `#4012` Release SM Context during security mode crashes AMF | 报告: `v2.7.5` | AMF | NAS + SBI | 安全模式中触发 `Release SM Context`，AMF 在 `nsmf-handler` fatal | 复用 issue seed 或重放带竞态的注册 / 安全过程 / SM context release 流 | 中；依赖完整 seed 更稳 | 高 | 高 | 中 | [#4012](https://github.com/open5gs/open5gs/issues/4012) |
| `#3910` Stale `ran_ue` after abnormal handover + re-registration | 报告: `v2.7.3` | AMF | NGAP + NAS | 异常 handover required 后旧 `ran_ue` 指针残留，后续重复注册触发断言 | 需先制造异常 handover，再用相同 IMSI 快速重注册 | 低；与当前项目主路径冲突 | 高 | 高 | 低 | [#3910](https://github.com/open5gs/open5gs/issues/3910) |
| `#3671` `npcf-am-policy-control` response in authentication state crashes AMF | 报告: `v2.7.2` | AMF | NGAP + SBI | handover 相关流程中 `npcf-am-policy-control` 响应进入错误状态机，AMF fatal | 两 gNB + handover + 特定注册时序 | 低；明显偏 handover | 高 | 高 | 低 | [#3671](https://github.com/open5gs/open5gs/issues/3671) |
| `#3707` `nudm-sdm` response in authentication state crashes AMF | 报告: `v2.7.2` | AMF | NGAP + SBI | handover / 重注册过程中 `nudm-sdm` 响应进入错误状态机，AMF fatal | 两 gNB + handover + 认证时序交叉 | 低；明显偏 handover | 高 | 高 | 低 | [#3707](https://github.com/open5gs/open5gs/issues/3707) |

## Top 3 推荐

当前最适合课程项目主线的 3 个 issue：

1. `#3727`
2. `#3622`
3. `#3497`

选择原因：

- 都能比较直接映射到现有“包修改 / 回放 / 网元行为验证”能力
- 不强依赖 live handover
- 能覆盖 `UPF` 与 `AMF` 两类核心网元
- 既可展示 crash，也可展示“当前版本已修复 / 安全拒绝 / 可自动恢复”

## Codex 核验修正（2026-06-05）

> 重要：以下核验基于 GitHub issue、release note、PR 合入时间和当前镜像 commit
> `782a97efe9e3acb1251e318bd3738ced4044dac8`。当前容器版本虽然显示为
> `v2.7.6-131-g782a97e`，但它已经包含 `v2.7.6` 之后的 131 个提交。

原 Top 3 更适合作为“回归验证 / 已修复边界测试”，不适合作为当前 digest 的主复现目标：

| Issue | 原判断 | 核验结果 | 当前用途 |
|---|---|---|---|
| `#3727` | 高优先级 UPF crash | `v2.7.5` release note 明确包含 `[UPF] Fixes: Crash in upf_sess_set_ue_ip when PDN type is invalid (#3727)` / PR `#3739`；当前 `782a97e` 晚于 `v2.7.5` | 只作为回归测试：证明当前版本不 crash 或安全拒绝 |
| `#3622` | 高优先级 AMF/NAS heap overflow | `v2.7.5` release note 明确包含 `[NAS] Fix heap-buffer-overflow vulnerability in NAS message decoding (#3622)` / PR `#3623`；当前 `782a97e` 晚于 `v2.7.5` | 只作为回归测试：证明 malformed NAS 不再打崩 AMF |
| `#3497` | 高优先级 PFCP flood | `v2.7.5` release note 明确包含 `[PFCP] Fix memory free issue causing crash (#3497)` / PR `#3515`；当前 `782a97e` 晚于 `v2.7.5` | 不建议主打，结果偏泛；可作为稳健性边界测试 |
| `#4179` | 备选 UPF/GTP-U crash | 修复 commit `93a9fd98a8` 于 2025-12-05 合入；当前 `782a97e` 是 2025-12-06，并且 compare 显示当前 commit 包含该修复 | 只作为回归测试 |
| `#4180` | 备选 UPF IPv6/GTP-U crash | 修复 commit `b72d834998` 于 2025-12-05 合入；当前 `782a97e` 是 2025-12-06，并且 compare 显示当前 commit 包含该修复 | 只作为回归测试 |

因此，5C.6 的主复现目标应改为：选择 `v2.7.7` release 中修复、但修复 commit 晚于
`782a97e` 的问题。当前初步筛选如下：

| 候选 | 修复来源 | 是否晚于当前 digest | 组件 | 协议入口 | 落地判断 |
|---|---|---|---|---|---|
| PR `#4333` `core/sbi: Prevent DoS in requester-features parsing (uint64 overflow)` | `v2.7.7` release | 是，2026-02-28 | SBI core / NRF/SCP 等 | HTTP SBI query/header 字段 | 优先候选。触发方式可能是畸形 `requester-features`，自动化和健康检查最容易，但课程协议贴合度较弱 |
| PR `#4365` `gtp: harden parsers against malformed IE lengths and remove assert-based crashes` | `v2.7.7` release | 是，2026-03-13 | SMF / GTP parser | GTPv1/v2 控制面 malformed IE | 已做最小 GTPv1-C Create PDP Context 探测；当前 5GC baseline 缺少完整 Gn/Gx 侧上下文，SMF 停在 Selection Mode/MSISDN/Gx Peer 检查，未触发 crash；不作为当前主展示 testcase |
| PR `#4202` `AMF : Prevent null session reference at sending partial-handover error` | `v2.7.7` release | 是，2025-12-09 | AMF | NGAP + SBI / partial handover state | 展示价值高但工程风险大，依赖 handover/异常状态，不建议作为首个 testcase |

阶段 5C.6 建议分层执行：

1. 主目标：`#4333` 已做成当前 digest 的 issue-driven crash testcase；`#4365` 需要额外 Gn/Gx seed 或 EPC 侧上下文，暂不进入正式测试集。
2. 回归目标：`#3727`、`#3622` 中选一个证明“旧 issue 在当前 digest 已安全处理”，作为版本边界分析。
3. 暂缓：`#3497/#4179/#4180/#4202` 不作为第一批主复现目标，除非前两个主目标不可落地。

## Top 3 详细判断

### `#3727` Invalid `pdn_type=0` crashes UPF

- 是否能在当前 Docker Open5GS 环境中独立复现：
  - 能。最像标准 `N4 PFCP mutation testcase`
- 是否需要已有 UE / PDU Session 状态：
  - 不需要
- 是否适合用包 mutation / replay 触发：
  - 非常适合
- 预期观察指标：
  - `UPF crash`
  - `assert log`
  - 容器健康检查失败
  - 进程退出 / 自动重启
- 若复现失败，如何展示：
  - 作为“当前版本对非法 `PDN Type` 已修复或已安全处理”的边界报告
  - 重点看是否：
    - 返回 PFCP error
    - 输出 warning / error 但不崩溃
    - 不影响 baseline 业务

### `#3622` Malformed registration causes NAS heap overflow

- 是否能在当前 Docker Open5GS 环境中独立复现：
  - 大概率能。AMF N2 暴露明确，且不依赖真实 UE
- 是否需要已有 UE / PDU Session 状态：
  - 不需要
- 是否适合用包 mutation / replay 触发：
  - 非常适合
- 预期观察指标：
  - `AMF crash`
  - `heap / decode error`
  - 异常日志
  - 健康检查失败
- 若复现失败，如何展示：
  - 作为“当前版本对 malformed NAS / NGAP 已不再 crash”的回归验证
  - 同时记录是否：
    - 安全拒绝
    - 正确清理临时 UE context
    - baseline 是否可立即恢复

### `#3497` Crafted PFCP flood breaks PFCP association / session handling

- 是否能在当前 Docker Open5GS 环境中独立复现：
  - 能
- 是否需要已有 UE / PDU Session 状态：
  - 最好有一个已建立 PDU Session，便于观察攻击前后业务影响
  - 但做 PFCP 稳健性测试并不绝对依赖已有业务流
- 是否适合用包 mutation / replay 触发：
  - 适合，尤其适合做伪造 PFCP 包 / 错误 TLV / 洪泛输入
- 预期观察指标：
  - `error log`
  - PFCP de-association / restoration
  - 后续 PDU session reject
  - 业务中断后是否自动恢复
- 若复现失败，如何展示：
  - 作为“当前版本是否能安全丢弃恶意 PFCP 包”的边界报告
  - 即使不 crash，也能展示：
    - PFCP association 是否保持稳定
    - baseline 是否仍可恢复
    - 是否出现资源泄露或异常重连

## 分组建议

### 容易先做

- `#3727`
- `#3622`
- `#3497`
- `#3689`

这组的共同特点：

- 可以通过较直接的协议输入构造触发
- 与当前 Docker baseline 和 replay 能力兼容
- 更容易形成自动化 testcase

### 有展示价值但工程风险高

- `#3608`
- `#3613`
- `#4012`

这组的共同特点：

- 展示价值高
- 更偏“状态机竞态”或“SBI 回调时序异常”
- 往往更依赖 seed、上下文和时序窗口
- 自动化难度明显高于单包 mutation

### 当前不建议作为主打

- `#3910`
- `#3671`
- `#3707`

原因：

- 三者都明显依赖 handover 或多 gNB 异常流程
- 与当前项目“XnAP 不做 live replay、handover 不作为当前主线”的约束冲突
- 更适合保留为后续扩展或边界说明，而不是当前 2-3 个主 testcase

## 对当前版本的判断

当前环境是：

```text
Open5GS daemon v2.7.6-131-g782a97e
```

这比许多 issue 的报告版本更晚，因此实现时要明确区分两种结果：

1. 当前版本仍然存在 crash / assert / 不安全行为
2. 当前版本已不再 crash，但能通过 testcase 证明其：
   - 安全拒绝 malformed input
   - 不破坏现有 baseline
   - 能维持或恢复健康状态

对课程展示来说，第二类结果仍然有价值，因为它可以作为：

- 回归验证
- 版本边界分析
- 安全稳健性证明

## 后续落地方向

若按当前优先级推进，建议先把 issue-driven testcase 分成两类：

### A 类：单报文或单事务 mutation

- `#3727`
- `#3622`
- `#3689`

适合先完成最小可运行 testcase。

### B 类：时序 / 状态机 / SBI 竞态

- `#3497`
- `#3608`
- `#3613`
- `#4012`

适合在已有自动化框架上逐步扩展，用于后续“高展示价值”案例。

## 参考来源

- [Open5GS Issues](https://github.com/open5gs/open5gs/issues)
- [Open5GS Releases](https://github.com/open5gs/open5gs/releases)
- [Issue #3727](https://github.com/open5gs/open5gs/issues/3727)
- [Issue #3622](https://github.com/open5gs/open5gs/issues/3622)
- [Issue #3497](https://github.com/open5gs/open5gs/issues/3497)
- [Issue #3608](https://github.com/open5gs/open5gs/issues/3608)
- [Issue #3613](https://github.com/open5gs/open5gs/issues/3613)
- [Issue #3689](https://github.com/open5gs/open5gs/issues/3689)
- [Issue #4012](https://github.com/open5gs/open5gs/issues/4012)
- [Issue #3910](https://github.com/open5gs/open5gs/issues/3910)
- [Issue #3671](https://github.com/open5gs/open5gs/issues/3671)
- [Issue #3707](https://github.com/open5gs/open5gs/issues/3707)
