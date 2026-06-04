# Stage 5C 编码、回放、自动测例与展示执行计划

> 更新日期：2026-06-04
> 工作分支：`feature/replay-issue-dashboard`

## 上层依据

本计划是 `IMPLEMENTATION.md` 的 Stage 5C 细化执行计划，不替代完整实施文档。范围和验收标准必须同时符合：

1. `5G-ORAN 协议解析和测试 - 课程project.pdf`
2. `IMPLEMENTATION.md`
3. `reports/testcase_reports/stage4.5-plan-report.md`

若本计划与课程要求或 `IMPLEMENTATION.md` 冲突，优先修正本计划，不能通过缩小协议范围规避课程基本要求。

## 课程要求对应关系

| 课程基本功能 | 必须覆盖 | 当前状态 | Stage 5C 责任 |
|---|---|---|---|
| 结构化 JSON 解析 | E1AP、F1AP、XnAP、GTP-U 常用 IE | F1AP/E1AP/GTP-U 已完成；XnAP 离线样例已完成 | 继续扩展对端验证结果 |
| 可逆编码与验证 | 至少 5 类控制消息 + GTP-U；生成 pcap；Wireshark 和对端正确识别 | 6 类 F1AP/E1AP 已完成结构化关键 IE mutation、强类型 APER 重新编码和 L1/L2；5 类生成控制 testcase 达到真实对端 L3 | 继续扩展更多 IE/issue testcase |
| 两个完整 UE 流程 | 例如注册 + PDU Session、注册 + 注销；推进状态机并输出日志 | 5C.2 已完成注册 + PDU Session、注册 + Release 的结构化自动测试 | 自动化两条 flow 并验证状态机 |
| 跨协议层分析 | 分析与 NG 接口关联的交互 | NGAP 已抓包/解析 | 将 NGAP 纳入 flow timeline、Open5GS issue 测试和回放验证 |
| 加分项 2 | 自动生成网络组件可正确接收的测试例 | 部分完成 | 完成生成、回放、日志/响应检查和报告闭环 |

## 协议能力范围

不能把 replay 范围缩减为 GTP-U。Stage 5C 最终协议范围如下：

| 协议 | JSON 解析 | JSON/template → pcap | Wireshark 验证 | 对端组件验证/回放 |
|---|---|---|---|---|
| F1AP | 已完成 | 3 类关键 IE mutation + 强类型 ASN.1 APER 重新编码 | 3 类目标消息完成 L2 | 生成 GNBDUConfigurationUpdate/Reset 达到 L3，Configuration Update 达到 L4 |
| E1AP | 已完成 | 3 类关键 IE mutation + 强类型 ASN.1 APER 重新编码 | 3 类目标消息完成 L2 | 生成 Setup/ConfigurationUpdate/Reset 达到 L3，Setup 达到 L4 |
| GTP-U | 已完成 | MVP 已完成，继续补扩展头、mutation | 已完成基础验证 | 必须完成 UDP/2152 live replay 和接收证据 |
| XnAP | Handover Request/Acknowledge 离线样例已完成 | srsRAN ASN.1 构造器已完成 | 两类消息已完成 L2 | 根据 Stage 4.5 约定，不要求当前环境 live replay |
| NGAP | 已完成 | 普通 smoke 与显式 testcase/mutation 入口已分离 | mutation 场景由协议感知 UERANSIM 生成 | Open5GS TAC mismatch testcase 已运行；payload replay/issue reproduction 后续扩展 |

## 控制消息覆盖目标

课程要求至少 5 类控制消息。优先实现以下 6 类，避免刚好达到最低数量后因单个消息失败而无法交付：

1. F1AP UE Context Setup Request
2. F1AP UE Context Modification Request
3. F1AP UE Context Release Command
4. E1AP Bearer Context Setup Request
5. E1AP Bearer Context Modification Request
6. E1AP Bearer Context Release Command

补充展示：

- XnAP Handover Request / Request Acknowledge：离线解析、构造和 Wireshark 识别，不要求 live replay。
- NGAP InitialUEMessage、InitialContextSetup、PDUSessionResourceSetup 或 issue 相关消息：跨层分析和 Open5GS 测试。

如果当前 srsRAN 版本无法产生某类 Release 消息，必须记录证据并使用同协议的可验证替代消息，不能直接减少控制消息总数。

## 验证层次

每个编码 testcase 都必须明确记录验证层次：

| Level | 验证内容 | 是否基本要求 |
|---|---|---|
| L1 | JSON/template 可以生成二进制和 pcap | 是 |
| L2 | tshark/Wireshark 正确识别协议、procedure、关键 IE，且非 malformed | 是 |
| L3 | 对端组件收到并在日志中识别消息 | 选定的至少 5 类 F1AP/E1AP 控制消息和 GTP-U 必须；XnAP 按约定豁免 |
| L4 | 对端状态机推进并产生预期响应 | 两条完整 UE flow 必须；单消息回放尽量完成 |

控制面协议使用 SCTP 且具有 association、stream、TSN 和状态机约束，不能把原始 pcap 直接发送当作有效对端回放。F1AP/E1AP/NGAP 的 live replay 必须通过协议感知的 SCTP 测试端或受控场景完成。

## 执行顺序

### 5C.2：新鲜 Flow 抓包与模板提取

目的：

- 为控制面编码提供真实 ASN.1 payload 模板。
- 为 Release 类消息补充注册 + 注销流程抓包。
- 为 live replay 提供当前 session 的 endpoint、UE ID 和 TEID，禁止硬编码旧 session 值。

实现：

1. 将注册 + PDU Session 流程封装为结构化 testcase。
2. 实现注册 + 注销流程，抓取释放相关 F1AP/E1AP/NGAP 消息。
3. 从完整 SCTP pcap 中提取 DATA chunk 的协议 payload、方向、stream、procedure 和关键 IE。
4. 从 GTP-U pcap 中提取当前 endpoint、TEID、扩展头和内层 payload。
5. 输出可提交的小型模板元数据；raw pcap 继续忽略。

验收条件：

- 两条 flow 均有结构化结果、日志和状态检查。
- 至少获得上述 6 类目标消息中的 5 类合法 payload 模板；缺失项有明确报告。
- 模板来源能追溯到 capture run 和 frame。

### 5C.3：多协议离线可逆编码与 Wireshark 验证

目的：

- 完成课程要求中的至少 5 类控制消息 + GTP-U 可逆编码。
- 补齐 XnAP 离线解析/构造。

实现：

1. 扩展 testcase schema，使其支持：
   - 协议、消息类型、procedure、方向
   - 原始 payload/template
   - 可修改字段和 mutation
   - 预期 tshark 字段
   - 预期对端行为
2. 实现完整 pcap 构造：
   - F1AP/E1AP/NGAP/XnAP：IP/SCTP/DATA + ASN.1 payload
   - GTP-U：IP/UDP/GTP-U + 扩展头/内层 payload
3. 对每个 testcase 自动执行 tshark 验证。
4. 自动执行 round-trip 检查：
   - template/JSON → pcap → Stage 4 parser → normalized JSON
   - 比较协议、procedure 和关键 IE。

验收条件：

- 至少 5 类控制消息和 GTP-U 全部达到 L1/L2。
- XnAP 至少有 Handover Request/Request Acknowledge 离线样例可解析和构造。
- 所有生成包非 malformed，关键字段与 testcase 一致。

### 5C.4：多协议对端组件验证与回放

目的：

- 验证生成的测试例不只被 Wireshark 识别，也能被实际网络组件接收和处理。

子任务：

#### F1AP 对端验证

- 在隔离场景中建立合法 SCTP association。
- 以 DU 或 CU 测试端身份重放必要前置序列和目标消息。
- 检查对端日志、解码错误、response 和 UE ID。

#### E1AP 对端验证

- 在隔离场景中建立合法 SCTP association。
- 重放必要 E1 setup/UE context 前置序列和目标 bearer context 消息。
- 检查 CU-CP/CU-UP 日志、response、tunnel/TEID 字段。

#### GTP-U 对端验证

- 在 CU-UP/UPF/DU 网络命名空间中发送 UDP/2152 测试包。
- 动态使用当前有效 endpoint 和 TEID。
- 自动抓取发送包、接收证据和组件健康状态。

#### NGAP / Open5GS 对端验证

- 使用协议感知 SCTP 测试端或隔离 gNB 场景连接 AMF。
- 用于正常消息验证以及后续 Open5GS issue reproduction。

#### XnAP

- 按 Stage 4.5 约定只做离线解析/构造和 Wireshark 验证，不要求 live replay。

通用要求：

- 默认 dry-run；只有显式 `--live` 才发送到组件。
- 每个 live testcase 前后执行环境健康检查。
- 失败后可以自动恢复 baseline。
- 结果记录 L3/L4 是否通过，不能只记录“包已发送”。

验收条件：

- GTP-U 有实际发送和接收/抓包证据。
- 选定的至少 5 类 F1AP/E1AP 控制消息达到 L3；无法达到 L3 的消息不能计入课程要求数量，必须换用可验证消息。
- F1AP、E1AP 至少各有一个消息达到 L4；若无法达到，必须输出可复现实验和支持边界，但该边界报告不等于完成课程基本要求。
- NGAP/Open5GS 测试端能够支撑 issue-driven 测试。

### 5C.5：两条完整 UE Flow 自动测试

必须实现：

1. 注册 + PDU Session Establishment
2. 注册 + Deregistration / Release

每条 flow 自动完成：

- 启动/检查 baseline
- 执行 UE 行为
- 抓取 F1AP/E1AP/NGAP/GTP-U
- 生成跨协议 timeline
- 检查 UE、CU、DU、Open5GS 状态机日志
- 输出结构化 PASS/FAIL JSON 和报告

验收条件：

- 两条 flow 均可一条命令运行。
- UE 与 CU/DU/5GC 日志证明状态机推进。
- 结果包含跨协议关联字段和失败原因。

### 5C.6：Open5GS Issue-Driven 测试

实现：

- 筛选 2-3 个与固定 Open5GS v2.7.6 镜像相关、能通过 NGAP/NAS/GTP-U 输入触发或分析的 issue。
- 每个 issue 建立 testcase，记录 issue、影响组件、原始消息、mutation、预期、实际、健康检查和恢复结果。

验收条件：

- 至少一个 issue 被复现，或以可重复实验证明当前镜像不受影响。
- 测试不依赖手工修改容器，且不会永久破坏 baseline。

### 5C.7：Dashboard 与最终展示

Dashboard 使用前面产生的真实结果：

- 左侧：跨协议信令 timeline、解析 JSON、procedure、关键 IE、原始/变异字段。
- 右侧：环境状态、实时日志、L1-L4 验证结果、flow 和 issue testcase 结果。

验收条件：

- 能展示 F1AP、E1AP、XnAP、GTP-U，以及 NGAP 跨层信息。
- 能选择 offline encoding、对端回放、完整 flow、issue 测试结果。
- 不依赖手工复制日志或伪造演示数据。

## 当前完成状态

- [x] GTP-U testcase schema MVP。
- [x] GTP-U JSON → pcap 离线编码。
- [x] GTP-U tshark 和 Stage 4 round-trip 基础验证。
- [x] 两条完整 UE flow 的结构化自动测试。
- [x] F1AP/E1AP/NGAP 合法模板与当前 GTP-U endpoint/TEID 提取。
- [x] 6 类 F1AP/E1AP 控制消息完成结构化关键 IE mutation、强类型 APER 重新编码和 L1/L2。
- [x] XnAP 离线解析/构造样例。
- [x] F1AP/E1AP 生成 testcase 使用隔离协议感知 SCTP 测试端验证；5 类达到 L3，F1AP/E1AP 各一类达到 L4。
- [x] GTP-U 生成 testcase live replay。
- [x] NGAP/Open5GS testcase/mutation 入口；普通 UERANSIM smoke 已单独保留。
- [ ] Open5GS issue-driven 测试。
- [ ] Dashboard。

## 当前阶段结论

5C.2、5C.3、5C.4、5C.5 已按本计划实际运行并通过各自验收。自然 UE flow
证据仍只计入 5C.5；5C.4 控制面等级只来自本次生成 testcase、独立 association、
CU-CP 接收日志和响应。后续工作是 5C.6 Open5GS issue-driven 测试与 5C.7
dashboard，不反向扩大已声明的 L1-L4。

报告见
`reports/testcase_reports/stage5c2-flow-template-report.md` 和
`reports/testcase_reports/stage5c3-offline-encoding-report.md`、
`reports/testcase_reports/stage5c4-peer-validation-report.md`、
`reports/testcase_reports/stage5c5-complete-flow-report.md`。
