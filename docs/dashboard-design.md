# Dashboard Design: 5G O-RAN Test Console

> 日期：2026-06-05
> 目标：为最终验收提供一个可操作、可解释、可复现的前端展示界面。

## 1. 设计目标

这个 dashboard 不做普通宣传页，而做实验控制台。用户打开后应能直接看到：

- 当前 5G/O-RAN/Open5GS 实验环境是否健康。
- 项目完成了哪些协议解析、编码、回放和完整流程测试。
- Open5GS issue-driven 安全测试如何构造输入、如何触发网元行为、如何自动恢复。
- 每项结果对应的结构化证据、日志摘要和报告文件在哪里。

### 1.1 界面语言

展示界面使用中文为主，关键技术名词保留英文：

- 页面标题、按钮、说明文字、状态解释使用中文。
- 协议名保留英文，例如 `F1AP`、`E1AP`、`NGAP`、`GTP-U`、`XnAP`。
- 结果分类保留英文，例如 `VULNERABLE_CRASH`、`NOT_REPRODUCED`、`PFCP_ERROR_NO_IMPACT`。
- 文件路径、脚本名、命令名、JSON key、Docker 容器名保留英文。
- 日志原文不翻译，只在旁边给中文解释。

最终验收时的叙述顺序建议：

1. 看系统总览：证明环境已搭建并可运行。
2. 看协议解析与编码回放：证明课程要求的协议解析和重新编码完成。
3. 看 UE Flow：证明两条完整流程测试完成。
4. 看安全测试：展示 Open5GS issue-driven testcase、crash 复现和恢复能力。

## 2. 信息架构

建议采用单页应用风格，左侧导航 + 中间主工作区 + 右侧日志/结果抽屉。

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│ 顶部栏：项目名 / 当前 branch / Open5GS digest / baseline 状态 / 刷新按钮       │
├───────────────┬───────────────────────────────────────────────┬─────────────┤
│ 左侧导航       │ 主内容区                                        │ 右侧抽屉     │
│               │                                               │             │
│ 系统总览       │ 当前页面的图、表、timeline、JSON viewer          │ 实时日志     │
│ 协议解析       │                                               │ 命令输出     │
│ 编码回放       │                                               │ 结果摘要     │
│ UE Flow        │                                               │ 报告链接     │
│ 安全测试       │                                               │             │
│ 报告导出       │                                               │             │
└───────────────┴───────────────────────────────────────────────┴─────────────┘
```

右侧抽屉可折叠。默认展示当前页面最近一次结果摘要；执行 live testcase 时切换成实时日志模式。

## 2.1 统一运行交互规范

所有会执行脚本的按钮都必须走统一 job 流程，避免用户点了以后不知道是否正在运行、是否已经完成、
是否需要手动恢复环境。

### 状态机

```text
idle
-> queued
-> running
-> collecting_results
-> restoring
-> completed

失败路径：
running -> failed -> restoring -> completed_with_failure
running -> failed -> restoring -> restore_failed
restoring -> restore_failed
```

### UI 显示

| 状态 | 页面显示 | 按钮状态 | 右侧抽屉 |
|---|---|---|---|
| `idle` | 显示最近一次结果 | 可点击 Run | 最近结果摘要 |
| `queued` | 显示排队中 | Run 禁用 | job 元数据 |
| `running` | 顶部显示 “Running...” 和计时器 | 其他 live 按钮全部禁用 | stdout/stderr tail |
| `collecting_results` | 显示 “Collecting result...” | Run 禁用 | 结果文件路径 |
| `restoring` | 显示 “Restoring baseline...” | Run 禁用 | restore 日志 |
| `completed` | 显示 PASS / 分类结果 / 完成时间 | Run 恢复可用 | 结构化结果摘要 |
| `completed_with_failure` | 显示 FAIL，但 baseline 已恢复 | Run 恢复可用 | 错误原因 + restore OK |
| `restore_failed` | 顶部红色告警 “Baseline restore failed” | 只允许 Restore baseline | restore 错误日志 |

### 是否需要 Stop / Abort 按钮

MVP 不建议提供普通 “Stop” 按钮。原因：

- `run_ue_flow.sh`、`run_open5gs_issue_tests.py --live` 都有清理/恢复逻辑。
- 强行中断可能让容器停在半恢复状态，反而不利于验收。
- issue live 测试本来就可能故意打崩 NF，用户看到 crash 后也必须等 restore 完成。

MVP 只提供：

- `Run`
- `Dry-run`
- `Restore baseline`
- `Refresh status`

高级版可以增加 `Abort and restore`，但不能只是 kill 进程。它必须：

1. 终止当前 job 进程组。
2. 立即运行 `scripts/env/restore_baseline.sh`。
3. 再运行 `scripts/env/check_core_ready.sh`。
4. 只有恢复成功才把全局状态切回可运行。

### 并发规则

- 同一时间只允许一个 mutating job：包括 live issue test、UE flow、live peer validation、restore baseline。
- 只读操作可以并行：读取报告、查看 JSON、查看历史结果。
- 当存在 `running/restoring` job 时，所有 live 按钮禁用，顶部显示当前 job。
- 如果 `restore_failed`，除了 `Restore baseline` 和查看日志外，其他 live 操作全部禁用。

### 完成反馈

每个运行按钮执行完必须显示：

- job status
- classification 或 PASS/FAIL
- result JSON 路径
- startedAt / finishedAt / duration
- baseline 是否 restored
- “View result” 和 “Open report” 操作

### 长任务进度展示

不能让用户在 30 秒以上的任务里只看到一个静态 spinner。所有可能超过 10 秒的 job 都必须显示：

- 当前阶段名
- 阶段序号，例如 `Step 3 / 7`
- 已运行时间
- 最近 10-30 行日志 tail
- 已产生的中间证据，例如已创建的 result 目录、pcap 路径、已观察到的关键日志
- 如果超过该任务的常见耗时，显示 “Still running, waiting for ...”，而不是卡住

推荐展示形式：

```text
Running registration_release
Step 4 / 7: Waiting for inactivity-triggered RRC Release
Elapsed: 01:42
Last event: CU-CP logged UEContextReleaseCommand
Output: json/flow_results/registration_release_20260605_151500/result.json
```

### 任务阶段模板

| Job 类型 | 典型耗时 | 阶段展示 |
|---|---:|---|
| Health check | 1-5 秒 | `checking containers` -> `checking PFCP/SCTP links` -> `done` |
| Restore baseline | 30-90 秒 | `removing transient UE containers` -> `starting core` -> `recreating CU/DU` -> `waiting healthy` -> `check_core_ready` |
| Issue dry-run | 1-5 秒 | `loading testcase` -> `sampling target state` -> `checking baseline` -> `writing result` |
| Issue live | 30-90 秒 | `checking baseline` -> `sending mutation` -> `sampling target state` -> `collecting logs` -> `restoring baseline` -> `checking baseline` |
| UE PDU Session flow | 1-3 分钟 | `preparing evidence environment` -> `starting capture` -> `starting UE` -> `waiting registration` -> `waiting PDU session` -> `generating traffic` -> `parsing pcaps` -> `analyzing flow` |
| UE Release flow | 2-5 分钟 | `preparing evidence environment` -> `starting capture` -> `starting UE` -> `waiting registration` -> `waiting PDU session` -> `waiting inactivity release` -> `parsing pcaps` -> `analyzing flow` |
| Live peer validation | 30-120 秒 | `checking baseline` -> `generating payload` -> `sending to peer` -> `waiting response/log` -> `restoring baseline` -> `writing result` |

### 超时和“看起来卡住”的处理

- 每个阶段应有软超时提示，不一定立即失败。
- 如果日志 20 秒没有变化，显示 “No new log yet; still waiting for <stage>”。
- 如果超过脚本内部超时，显示失败阶段和 stderr tail。
- 失败后仍进入 `restoring`，不要直接停在 failed。
- 对 release flow，等待 inactivity release 本来可能较久，要显示倒计时或预计等待窗口，例如 `expected up to 240s`。

## 3. 页面一：系统总览

### 3.1 Layout

主区域分为三块：

1. 拓扑图
   - UE / srsUE
   - srsRAN DU
   - srsRAN CU-CP
   - srsRAN CU-UP
   - Open5GS AMF / SMF / UPF / NRF
   - 主要接口标注：F1-C、F1-U、NGAP、N3/GTP-U、SBI、PFCP

2. 环境状态卡片
   - Baseline：READY / FAIL
   - Open5GS digest：当前 pinned image digest
   - CU/DU split：healthy / running
   - Last restore：成功 / 失败 / 未运行

3. 快捷验收入口
   - Run health check
   - Restore baseline
   - Open latest progress report

### 3.2 操作

| 操作 | 前端行为 | 后端动作 | 输出 |
|---|---|---|---|
| 刷新状态 | 更新容器状态和健康状态 | 运行 `./scripts/env/check_core_ready.sh`；读取 `docker ps`/容器 inspect | baseline 是否可用 |
| 恢复 baseline | 弹出确认，执行恢复 | 运行 `./scripts/env/restore_baseline.sh`，随后运行 `check_core_ready.sh` | 恢复日志、最终状态 |
| 查看 digest | 展示当前 Open5GS target | 读取 compose image 或 `docker inspect nrf --format '{{.Config.Image}}'` | image digest/version |

### 3.3 对应验收项

- 证明 Open5GS + srsRAN CU/DU split + UE 环境实际可运行。
- 证明后续 live testcase 后可以自动恢复 baseline。
- 解释为什么后续安全测试不会把环境永久破坏。

## 4. 页面二：协议解析

### 4.1 Layout

这一页不能做成报告入口。最终演示时，用户必须能直接在页面内点击协议、消息和 testcase，
看到“真实抓包解析出了什么”和“这些字段如何进入后续编码/回放链路”。报告只能作为辅助入口。

建议将当前导航里的 `协议 / 回放` 合并页拆成三个可切换 tab：

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│ 协议 / 回放                                                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│ [解析浏览器] [编码 Testcase] [回放验证]                                      │
├───────────────┬───────────────────────────────────────────┬─────────────────┤
│ 协议/消息列表   │ 选中消息或 testcase 的结构化详情             │ 证据/JSON 预览   │
│ F1AP           │ 关键 IE / TEID / 方向 / procedure code      │ normalized JSON │
│ E1AP           │ 编码链路状态 / hash / tshark fields         │ testcase JSON   │
│ NGAP           │ 对端验证 L1-L4 / response / peer log        │ result JSON     │
│ GTP-U          │                                           │                 │
│ XnAP offline   │                                           │                 │
└───────────────┴───────────────────────────────────────────┴─────────────────┘
```

#### Tab A: 解析浏览器

左侧为协议和消息列表：

- F1AP
- E1AP
- NGAP
- GTP-U
- XnAP offline

中间为消息详情：

- 消息类型
- 来源 pcap / flow run
- 关键 IE 表格
- normalized JSON viewer
- Wireshark/tshark 识别状态

底部为 “验收映射”：

- 结构化 JSON：PASS/FAIL
- 关键 IE 提取：PASS/FAIL
- XnAP 离线构造/识别：PASS/FAIL

#### Tab B: 编码 Testcase

左侧为 testcase 列表，按协议分组：

- `tests/replay/cases/*.json`
- `tests/replay/templates/stage5c2/control/*.json`
- `tests/replay/templates/stage5c3/xnap/*.json`
- `tests/replay/live_cases/control/*.json`

中间展示选中 testcase 的编码链路：

```text
JSON testcase
-> mutable fields / structured IEs
-> encoded payload
-> generated pcap
-> tshark decode
-> normalized round-trip
```

必须直接显示：

- `protocol`
- `message` / `procedure_name`
- `description`
- `display_filter`
- `structured_ies` 或 `mutable_ies`
- 预期字段，例如 `procedureCode`、UE ID、TEID、QFI、SCTP PPID
- testcase JSON 路径
- 可打开 testcase JSON 的操作

#### Tab C: 回放验证

左侧为 replay / peer validation case 列表，来源包括：

- `json/replay_results/stage5c4/peer_validation.json`
- `json/replay_results/stage5c4/control_peer_validation.json`
- `json/replay_results/stage5c4/ngap_open5gs.json`
- GTP-U live replay result JSON

中间展示验证证据链：

```text
L1 JSON generated payload
-> L2 pcap/tshark recognized
-> L3 sent payload hash matches
-> L4 peer received / response captured
```

每个 case 必须直接显示：

- `protocol`
- `message`
- `peer`
- `expected_response`
- `levels.L1` / `levels.L2` / `levels.L3` / `levels.L4`
- `payload_hashes.all_equal`
- `pcap_payload_matches_generated`
- `protocol_recognized`
- `peer_rx_log` / `initiator_rx_response_log` / `response_captured`
- response message 和 transaction/procedure match 结果

### 4.1.1 交互式展示硬性要求

协议 / 回放页不能只显示这些内容：

- 阶段报告卡片
- “打开报告”按钮
- 单纯 Markdown viewer
- 静态文字说明

至少要有以下交互：

| 交互 | 必须看到的变化 |
|---|---|
| 点击协议 | 左侧消息列表过滤到该协议 |
| 点击消息 | 中间显示 procedure/message、方向、关键 IE 或 TEID，右侧显示 normalized JSON |
| 点击 testcase | 中间显示 JSON 输入、mutation/structured fields、预期 tshark 字段 |
| 点击 replay case | 中间显示 L1-L4 验证链、hash 一致性、对端响应、peer log 证据 |
| 点击 JSON / result | 右侧抽屉显示对应文件内容 |

验收时应能不打开任何 Markdown 报告，仅通过这一页说明：

1. 我们从真实抓包中解析出 F1AP/E1AP/NGAP/GTP-U。
2. 我们能把关键字段结构化成 normalized JSON。
3. 我们能从 JSON testcase 重新编码控制面和 GTP-U 报文。
4. 生成 payload 与 pcap 读回 payload hash 一致。
5. tshark/Wireshark 能识别生成报文。
6. 部分 F1AP/E1AP payload 能进入真实 srsRAN 对端并获得响应。
7. XnAP 按当前项目范围做 offline construct / parse / identify，不声称完整 Xn handover。

### 4.2 操作

| 操作 | 前端行为 | 后端动作 | 输出 |
|---|---|---|---|
| 选择协议 | 加载该协议消息列表 | 读取 `json/flow_results/**/normalized/*.json` 和相关报告 | 消息列表 |
| 点击消息 | 展示关键 IE 和 JSON | 读取 normalized JSON | JSON viewer、IE 表 |
| 筛选消息类型 | 更新列表 | 前端过滤或后端 query | 过滤后的消息 |
| 选择编码 testcase | 展示 JSON 输入、可变字段、预期 tshark 字段 | 读取 `tests/replay/**.json` | testcase 详情 |
| 选择 replay case | 展示 L1-L4、hash、对端响应和日志证据 | 读取 `json/replay_results/stage5c4/*.json` | replay 证据链 |
| 查看 JSON | 右侧抽屉展示文件内容 | 读取白名单文件 | JSON viewer |
| 打开报告 | 跳转报告文件 | 打开 `reports/testcase_reports/stage4-parse-report.md` 等 | Markdown 报告 |

### 4.3 对应验收项

课程要求中明确包括：

- E1AP/F1AP/XnAP/GTP-U 解析为结构化 JSON。
- 分析与 NG 接口关联的跨层交互。

该页面负责展示：

- F1AP / E1AP / NGAP / GTP-U 来自真实 baseline capture。
- XnAP 按调整后的范围做离线 Handover Request / Acknowledge 构造和识别。
- 每条消息不是只写在报告里，而是能在前端点开看到结构化字段。
- 编码和回放不是“报告声称完成”，而是在页面内逐 case 显示 JSON 输入、payload/pcap/hash、tshark 和对端验证证据。

## 5. 页面三：编码回放

### 5.1 Layout

页面分为三层：

1. Testcase 列表
   - F1AP/E1AP control peer validation cases
   - GTP-U replay cases
   - XnAP offline encoding cases

2. 编码链路视图

   ```text
   JSON testcase -> encoded payload -> generated pcap -> tshark validation -> live peer validation
   ```

3. 结果详情
   - payload hash
   - pcap read-back hash
   - tshark protocol decode result
   - peer validation result
   - 对端日志摘要

### 5.1.1 当前已有数据来源

实现交互式 `协议 / 回放` 页面时，优先复用已有结构化文件，不要重新跑 live 实验作为首选。

解析浏览器可读取：

| 用途 | 文件 |
|---|---|
| baseline control-plane summary | `json/normalized/run_capture_ping_20260522_110820_summary.json` |
| baseline F1AP/E1AP/NGAP messages | `json/normalized/run_capture_ping_20260522_110820_control_plane_packets.json` |
| baseline GTP-U messages | `json/normalized/run_capture_ping_20260522_110820_gtpu_packets.json` |
| flow normalized messages | `json/flow_results/**/normalized/*_control_plane_packets.json` |
| flow normalized GTP-U | `json/flow_results/**/normalized/*_gtpu_packets.json` |

编码 testcase 浏览器可读取：

| 用途 | 文件 |
|---|---|
| F1AP/E1AP/GTP-U/XnAP replay cases | `tests/replay/cases/*.json` |
| Stage 5C.2 extracted templates | `tests/replay/templates/stage5c2/**/*.json` |
| Stage 5C.3 XnAP offline templates | `tests/replay/templates/stage5c3/**/*.json` |
| Live peer JSON inputs | `tests/replay/live_cases/control/*.json` |

回放验证浏览器可读取：

| 用途 | 文件 |
|---|---|
| integrated peer validation summary | `json/replay_results/stage5c4/peer_validation.json` |
| generated control peer validation | `json/replay_results/stage5c4/control_peer_validation.json` |
| NGAP/Open5GS validation | `json/replay_results/stage5c4/ngap_open5gs.json` |
| normalized replay output | `json/replay_results/normalized/**/**/*_summary.json` |
| GTP-U live replay results | `json/flow_results/**/live_gtpu_result.json` |

这些文件都属于只读证据，适合直接在 dashboard 中加载。页面默认应先展示最近或最完整的一组结果；
如果文件不存在，则显示 `missing`，不要让用户以为协议未完成。

### 5.2 操作

| 操作 | 前端行为 | 后端动作 | 输出 |
|---|---|---|---|
| 查看 testcase | 展示 JSON testcase | 读取 `tests/replay/live_cases/control/*.json` 等 | testcase JSON |
| Run offline encoding | 创建 job，显示运行中和计时器 | 运行 `./scripts/replay/run_replay_tests.sh` 或细分脚本 | pcap/tshark 验证结果；完成后显示 PASS/FAIL |
| Run live peer validation | 创建 mutating job，禁用其他 live 按钮 | 运行 `python3 scripts/replay/run_control_peer_validation.py --live` 或 `./scripts/replay/run_live_peer_validation.sh --live` | live result JSON；完成后显示 peer validation 分类和 restore 状态 |
| 查看 GTP-U replay | 展示 GTP-U live replay | 读取 `json/replay_results/**` 或运行对应脚本 | GTP-U 结果 |

### 5.2.1 运行完成后的显示

编码回放类任务完成后，页面必须显示：

- `PASS` / `FAIL`
- 输出 result JSON 路径
- 生成 pcap 路径
- tshark 是否识别为目标协议
- live peer validation 是否到达目标组件
- 若失败，显示失败阶段：`encode` / `pcap` / `tshark` / `live_peer` / `restore`

### 5.3 对应验收项

该页面用于证明：

- 至少 5 类控制消息可以从 JSON 重新编码。
- 生成的 pcap 能被 tshark/Wireshark 识别。
- F1AP/E1AP 不只是离线识别，还能进入真实对端组件验证。
- GTP-U packet 支持 JSON/template 到 pcap，并完成 live replay。

验收时可以强调：

- 同一个 APER payload 同时进入 pcap/tshark 和 SCTP endpoint。
- 校验 JSON 生成 hash、pcap 读回 hash、实际发送 hash 一致。
- 避免“报告写了能编码，但实际 replay 不是同一个输入”的问题。

## 6. 页面四：完整 UE Flow

### 6.1 Layout

左侧选择 flow：

- Registration + PDU Session
- Registration + Inactivity-triggered Release

中间展示 timeline：

```text
NG Setup
-> Registration
-> PDU Session Establishment
-> GTP-U Traffic
-> Inactivity Release / UEContextRelease
```

右侧展示：

- UE 日志摘要
- CU-CP / CU-UP / DU 日志摘要
- AMF / SMF / UPF 日志摘要
- normalized control-plane JSON
- GTP-U packet 摘要

### 6.2 操作

| 操作 | 前端行为 | 后端动作 | 输出 |
|---|---|---|---|
| Run PDU Session flow | 创建 mutating job，timeline 进入 running 状态 | 运行 `./scripts/flows/run_ue_flow.sh registration_pdu_session` | flow result JSON；完成后显示 PASS/FAIL 和结果路径 |
| Run Release flow | 创建 mutating job，timeline 进入 running 状态 | 运行 `./scripts/flows/run_ue_flow.sh registration_release` | flow result JSON；完成后显示 PASS/FAIL 和结果路径 |
| 查看 timeline | 加载最近一次 flow | 读取 `json/flow_results/**/result.json` | timeline + PASS/FAIL |
| 查看报文 | 跳到协议解析页 | 读取对应 normalized JSON | 相关消息详情 |

### 6.2.1 运行中和完成显示

运行中：

- timeline 当前步骤高亮，例如 `Registration running`。
- 右侧抽屉显示当前脚本 stdout/stderr tail。
- 顶部显示运行时间。
- 对当前步骤显示预计耗时。例如 release flow 的 `Waiting for inactivity-triggered release` 显示 `expected up to 240s`。
- 如果中间已经产生日志目录或 capture 目录，立即显示路径，让用户知道不是卡死。
- 禁用其他 live / flow / restore 按钮。

完成后：

- timeline 每个关键步骤显示 `PASS` / `MISS`。
- 显示 result JSON 路径，例如 `json/flow_results/<run_id>/result.json`。
- 显示 pcap / normalized JSON / log 目录链接。
- 如果脚本失败但 baseline 恢复成功，显示 `completed_with_failure`，并说明失败阶段。
- 如果 restore 失败，顶部进入 `restore_failed`，只允许再次恢复 baseline。

### 6.3 对应验收项

该页面用于证明：

- 两条完整 UE flow 已自动化。
- UE、CU/DU、Open5GS 状态机确实推进。
- NGAP 控制面、PDU Session、GTP-U 用户面可以串起来解释。
- release flow 不是简单停 UE 容器，而是 inactivity-triggered release。

## 7. 页面五：Open5GS Issue Tests

### 7.1 Layout

左侧 testcase 列表：

| Case | 组件 | 当前分类 |
|---|---|---|
| `#4333` NRF requester-features overflow | NRF | `VULNERABLE_CRASH` |
| `#4532` SMF empty SUPI | SMF | `VULNERABLE_CRASH` |
| `#4327` PFCP Create FAR | UPF | `PFCP_ERROR_NO_IMPACT` |
| `#4289` AMF dereg/rereg race | AMF | `NOT_REPRODUCED` |

中间展示选中 testcase：

- issue URL
- Open5GS target digest
- 输入 mutation
- 请求摘要
- 预期 vulnerable / fixed behavior

右侧展示 live 证据：

- curl / UDP / nr-cli 输出摘要
- 目标容器 before/after
- restart count
- fatal/assert/error 日志
- baseline_restore

### 7.2 操作

| 操作 | 前端行为 | 后端动作 | 输出 |
|---|---|---|---|
| 选择 testcase | 展示 testcase JSON 和上次结果 | 读取 `tests/replay/open5gs_issues/*.json` 和 `json/replay_results/stage5c6/*.json` | testcase + result |
| Dry-run | 创建只读 job，不弹危险确认 | 运行 `python3 scripts/replay/run_open5gs_issue_tests.py --case ... --output ...` | `DRY_RUN`，显示 testcase 是否可解析、baseline 当前是否可用 |
| Live run | 弹危险确认，创建 mutating job，显示 running/restoring | 运行 `python3 scripts/replay/run_open5gs_issue_tests.py --live --case ... --output ...` | 分类结果；显示目标容器前后状态、fatal 日志、恢复状态 |
| 查看恢复 | 展示 restore 结果 | 读取 result JSON 中 `baseline_restore` | restored true/false |
| 查看报告 | 打开阶段报告 | 打开 `reports/testcase_reports/stage5c6-open5gs-issue-report.md` | Markdown |

### 7.2.1 Live run 确认文案

点击 Live run 时必须弹确认：

```text
This testcase may intentionally crash an Open5GS network function.
The runner will restore the baseline after execution.

Target: SMF
Case: #4532 empty SUPI
Expected: VULNERABLE_CRASH or SAFE_REJECT

Run live testcase?
```

确认后才执行。

### 7.2.2 完成后的显示

Issue live 完成后，页面必须显示：

- `classification`
- `request_summary`
- `request` 或对应协议发送摘要
- `target_before`
- `target_after`
- `restart_count_delta`
- `<component>_log_delta`
- `baseline_restore.restored`
- result JSON 路径

对 `#4532`，完成后应能直接看到：

```text
classification: VULNERABLE_CRASH
curl: exit 56, Connection reset by peer
smf: running -> exited
exit_code: 134
fatal: ogs_hash_get_debug: Assertion `klen` failed
baseline_restore.restored: true
```

### 7.2.3 Issue live 中间进度

Issue live 虽然通常只要几十秒，但因为它会等待恢复 baseline，仍然必须显示中间阶段：

```text
Step 1 / 6: Checking baseline
Step 2 / 6: Sending mutation
Step 3 / 6: Sampling SMF state
Step 4 / 6: Collecting SMF log delta
Step 5 / 6: Restoring baseline
Step 6 / 6: Running check_core_ready
```

对 crash 类 testcase，`Step 3` 可以先显示中间证据：

```text
SMF status changed: running -> exited
curl exit 56: Connection reset by peer
```

随后继续显示恢复阶段。这样用户能看到 crash 已经发生，而不是误以为页面卡住。

### 7.3 后端输出格式

前端主要消费：

```text
json/replay_results/stage5c6/open5gs_issue_results.json
json/replay_results/stage5c6/open5gs_issue_4532_result.json
json/replay_results/stage5c6/open5gs_issue_4289_result.json
json/replay_results/stage5c6/open5gs_issue_4327_result.json
```

关键字段：

```json
{
  "case_id": "open5gs_4532_smf_empty_supi_sm_context_create",
  "classification": "VULNERABLE_CRASH",
  "component": "smf",
  "request_summary": {},
  "request": {},
  "target_before": {},
  "target_after": {},
  "restart_count_delta": 0,
  "smf_log_delta": {},
  "baseline_restore": {
    "restored": true
  }
}
```

### 7.4 对应验收项

该页面体现项目的安全测试和自动化能力：

- 根据 Open5GS issue 构造协议输入。
- 修改/回放后观察真实网元行为。
- `#4333` 和 `#4532` 是明显 crash 展示。
- `#4327` 是 PFCP 真实错误路径展示。
- `#4289` 如实标记为未复现，不虚报。
- 每次 live 后自动恢复 baseline，避免演示环境被打坏。

## 8. 页面六：报告导出

### 8.1 Layout

展示所有关键报告和进度文件：

- `docs/progress.md`
- `IMPLEMENTATION.md`
- `reports/testcase_reports/stage4-parse-report.md`
- `reports/testcase_reports/stage5c1-replay-mvp-report.md`
- `reports/testcase_reports/stage5c3-offline-encoding-report.md`
- `reports/testcase_reports/stage5c4-peer-validation-report.md`
- `reports/testcase_reports/stage5c5-complete-flow-report.md`
- `reports/testcase_reports/stage5c6-open5gs-issue-report.md`

### 8.2 操作

| 操作 | 前端行为 | 后端动作 | 输出 |
|---|---|---|---|
| 打开报告 | 显示 markdown | 读取文件 | Markdown viewer |
| 导出摘要 | 生成汇报摘要 | 汇总 result JSON + progress | 可复制文本 |
| 下载 JSON | 下载结构化结果 | 读取 JSON 文件 | JSON artifact |

## 9. 后端设计

建议后端做一个很薄的本地 API，不需要复杂数据库。

### 9.1 API 草案

```text
GET  /api/status
POST /api/restore-baseline

GET  /api/reports
GET  /api/reports/:id

GET  /api/protocol/messages
GET  /api/protocol/messages/:id

GET  /api/replay/cases
POST /api/replay/cases/:id/dry-run
POST /api/replay/cases/:id/live

GET  /api/flows
POST /api/flows/registration-pdu-session/run
POST /api/flows/registration-release/run

GET  /api/issues
GET  /api/issues/:id/result
POST /api/issues/:id/dry-run
POST /api/issues/:id/live

GET  /api/jobs/:jobId
GET  /api/jobs/:jobId/logs
POST /api/jobs/:jobId/abort-and-restore   # 高级版；MVP 可不实现
```

### 9.2 Job 模型

所有长任务都作为 job 执行：

```json
{
  "jobId": "stage5c6-4532-20260605-151500",
  "kind": "issue-live",
  "status": "running",
  "stepIndex": 2,
  "stepTotal": 6,
  "stepName": "sending mutation",
  "progressLabel": "Sending SMF empty SUPI request",
  "startedAt": "2026-06-05T15:15:00+08:00",
  "elapsedSeconds": 18,
  "command": "python3 scripts/replay/run_open5gs_issue_tests.py --live ...",
  "stdoutTail": [],
  "stderrTail": [],
  "events": [
    {
      "time": "2026-06-05T15:15:05+08:00",
      "level": "info",
      "message": "Baseline check passed"
    }
  ],
  "resultPath": "json/replay_results/stage5c6/open5gs_issue_4532_result.json"
}
```

前端轮询 job 状态，或者后续用 Server-Sent Events 推送日志。

### 9.2.0 Job 进度字段

后端每个 job 至少维护这些字段：

| 字段 | 说明 |
|---|---|
| `status` | `queued/running/collecting_results/restoring/completed/...` |
| `stepIndex` / `stepTotal` | 当前阶段序号 |
| `stepName` | 机器可读阶段名 |
| `progressLabel` | 前端可直接显示的人类可读状态 |
| `elapsedSeconds` | 总耗时 |
| `stageElapsedSeconds` | 当前阶段耗时 |
| `stdoutTail` / `stderrTail` | 最近日志 |
| `events` | 关键事件，如 baseline passed、mutation sent、container exited、restore passed |
| `resultPath` | 结果 JSON 路径 |

前端不需要猜测脚本卡在哪里，直接展示 `progressLabel` 和 `events`。

### 9.2.1 Job 完成判定

后端不能只看脚本进程退出码，还需要读取对应 result JSON：

- issue tests：读取 `classification` 和 `baseline_restore.restored`
- UE flow：读取 flow `result.json` 的 PASS/FAIL
- replay tests：读取 validation result JSON 的 PASS/FAIL

只有同时满足 “脚本结束 + 结果文件可解析 + baseline 状态明确” 才能显示 completed。

### 9.2.2 Abort and restore

MVP 可不实现 `Abort and restore`。如果实现，语义必须是：

```text
abort current process group
-> run scripts/env/restore_baseline.sh
-> run scripts/env/check_core_ready.sh
-> mark job aborted_with_restore_success or restore_failed
```

不能提供只 kill 当前进程的 Stop 按钮。

### 9.3 安全和误操作控制

Live run 会真实打 crash，所以必须：

- 默认只显示 dry-run 按钮。
- live run 前弹确认。
- live run 结束后强制执行 restore baseline。
- 如果 restore 失败，页面顶部进入红色状态，提示先恢复环境。
- 禁止同时运行多个 live job。

## 10. 前端实现建议

如果时间有限，先做静态读取 + 手动刷新：

1. React / Vite 或 Next.js 都可以。
2. 后端可用 Node/Express 或 Python/FastAPI。
3. 首版只读取现有 JSON/Markdown，不先做 live run 按钮。
4. 第二版再接脚本执行 API。

### MVP 范围

MVP 必须包含：

- 系统总览页
- 协议解析/编码页至少能展示已有 JSON 和报告链接
- UE Flow 页能展示两条 flow 结果
- Issue Tests 页能展示四个 testcase 结果，特别是 `#4333` 和 `#4532`

暂缓：

- 实时图表动画
- 多用户权限
- WebSocket
- 在线编辑 testcase
- 复杂拓扑拖拽

## 11. 验收讲解脚本

建议演示时这样讲：

1. “这里是系统总览。我们固定了 Open5GS digest，baseline 是健康的，CU/DU split 和核心网链路都正常。”
2. “这里是协议解析。我们从真实抓包里解析 F1AP/E1AP/NGAP/GTP-U，XnAP 按调整后的范围做离线构造和识别。”
3. “这里是编码回放。JSON testcase 会重新编码成 APER 或 GTP-U packet，生成 pcap 后能被 tshark 识别，并且部分控制面消息进入真实对端验证。”
4. “这里是完整 UE flow。两条流程都可以一条命令运行，分别覆盖注册 + PDU Session 和注册 + release。”
5. “这里是 Open5GS issue-driven 测试。我们根据上游 issue 构造输入，在当前 digest 上复现了 NRF 和 SMF 的 crash，也展示了 PFCP 错误路径和 AMF race 的边界测试。”
6. “每个 live 测试结束都会自动恢复 baseline，并重新做健康检查，所以这些 testcase 是可重复运行的。”

## 12. 当前数据来源清单

重点结果文件：

```text
json/replay_results/stage5c6/open5gs_issue_results.json
json/replay_results/stage5c6/open5gs_issue_4532_result.json
json/replay_results/stage5c6/open5gs_issue_4289_result.json
json/replay_results/stage5c6/open5gs_issue_4327_result.json
```

重点 testcase：

```text
tests/replay/open5gs_issues/nrf_requester_features_overflow.json
tests/replay/open5gs_issues/smf_empty_supi_sm_context_create.json
tests/replay/open5gs_issues/amf_dereg_rereg_late_sdm_delete.json
tests/replay/open5gs_issues/upf_pfcp_create_far_without_pdr_reference.json
```

重点脚本：

```text
scripts/replay/run_open5gs_issue_tests.py
scripts/flows/run_ue_flow.sh
scripts/replay/run_control_peer_validation.py
scripts/replay/run_live_peer_validation.sh
scripts/env/check_core_ready.sh
scripts/env/restore_baseline.sh
```

重点报告：

```text
docs/progress.md
IMPLEMENTATION.md
reports/testcase_reports/stage5c6-open5gs-issue-report.md
```
