# Stage 5C Replay / Issue / Dashboard 执行计划

> 更新日期：2026-06-04
> 工作分支：`feature/replay-issue-dashboard`

## 当前状态

已完成：

- baseline 自动启动、核心链路检查和 srsUE smoke 脚本。
- Stage 4 真实流量抓包与 normalized JSON。
- replay testcase v1 schema。
- GTP-U JSON testcase 到 pcap 的离线编码。
- tshark 自动验证和结构化 replay result JSON。

当前尚未完成：

- 将完整 UE 注册/PDU Session/capture 流程封装为结构化 testcase。
- GTP-U live replay/injection。
- 控制面合法 payload 模板、构造和变异。
- Open5GS issue reproduction。
- dashboard。

## 执行顺序

后续严格按以下顺序推进。每一步必须满足验收条件后再进入下一步，避免同时开展多个未闭环功能。

### Step 1：完整 Baseline Flow 自动测例

目的：

- 把目前分散的环境启动、链路检查、UE 注册、PDU Session、ping、抓包和解析串成一个命令。
- 为后续 live replay、issue reproduction 和 dashboard 提供统一结构化输入。

实现：

- 新增 `scripts/test/run_baseline_flow.sh`。
- 自动执行：
  1. `scripts/env/start_env.sh`
  2. `scripts/env/check_core_ready.sh`
  3. srsUE 注册和 PDU Session
  4. UE ping 流量
  5. SCTP/GTP-U 抓包
  6. Stage 4 parser
- 输出 `json/test_results/<run>.json`，至少包含：
  - 环境和组件状态
  - UE IP
  - NGAP/F1AP/E1AP/GTP-U 包数量
  - procedure 和 TEID 摘要
  - 每个检查项的 pass/fail

验收条件：

- 从已停止的项目环境开始，一条命令可以完成测试。
- UE 获得 IPv4 地址。
- NGAP、F1AP、E1AP、GTP-U 均存在可解析数据。
- 失败时返回非零退出码并在结果 JSON 中说明失败检查项。

### Step 2：GTP-U Live Replay

目的：

- 从“生成后离线识别”升级到“向实际运行环境发送并抓到重放包”。

实现：

- 从当前 baseline flow 抓包动态提取 N3 endpoint 和当前有效 TEID，禁止硬编码旧 session TEID。
- replay sender 默认 dry-run；只有显式 `--live` 才向环境发送。
- sender 在 CU-UP 或 UPF 的网络命名空间中发送，避免修改默认 compose 网络。
- 先实现无害的单包 GTP-U/ICMP replay，再增加重复包和字段 mutation。
- replay 前后自动抓包并记录组件健康状态。

验收条件：

- live replay 包能够在 N3 抓包中被 tshark 识别。
- 实际发送字段与 testcase 字段一致。
- replay 后 Open5GS、CU-UP、UE 状态可检查且结果写入 JSON。
- 默认运行不会发送 live 包。

### Step 3：控制面离线构造和识别

目的：

- 满足控制面消息能够由 JSON/template 构造并被 tshark/Wireshark 识别的要求。

实现：

- 从 baseline flow 的真实 SCTP pcap 提取合法 ASN.1 payload template。
- template 保存协议、procedure、方向、关键 IE 元数据和 payload。
- 构造完整 SCTP/IP pcap，复用合法 ASN.1 payload。
- 先覆盖至少五类消息，优先选择：
  - NGAP InitialUEMessage
  - NGAP InitialContextSetup
  - NGAP PDUSessionResourceSetup
  - F1AP F1Setup
  - E1AP BearerContextSetup
- mutation 首先只修改安全、长度不变且能验证的字段。

验收条件：

- 五类控制面消息均可由 testcase 生成 pcap。
- tshark 能正确识别协议、procedure 和目标关键 IE。
- 构造结果可进入现有 Stage 4 normalizer。

### Step 4：Open5GS Issue-Driven 测试

目的：

- 把 replay/mutation 能力用于复现 Open5GS v2.7.6 相关实现问题。

实现：

- 调研并筛选 2-3 个与当前 Open5GS 版本、NGAP/NAS/GTP-U 输入相关的 issue。
- 每个 issue 建立独立 testcase，记录：
  - issue 链接和影响组件
  - 前置环境
  - 原始消息与 mutation
  - 预期行为
  - 实际行为
  - 是否复现及证据
- 每个 live testcase 前后执行健康检查；必要时自动 reset baseline。

验收条件：

- 至少一个 issue 被复现，或以明确实验结果证明当前镜像不受影响。
- 测试可重复运行，不依赖手工修改容器。
- 测试不会永久破坏 baseline。

### Step 5：Dashboard

目的：

- 将前面产生的真实结构化结果用于最终展示，而不是制作独立演示假数据。

实现：

- 左侧展示信令 timeline、解析 JSON、procedure 和关键 IE。
- 右侧展示环境状态、testcase 日志、pass/fail 和 issue reproduction 结果。
- dashboard 只读取统一 result JSON 和 normalized JSON。
- 提供一条命令启动本地展示。

验收条件：

- 能选择并展示 baseline flow、offline replay、live replay 和 issue testcase。
- 页面内容来自真实运行结果。
- 演示流程无需手工复制日志或 JSON。

## 立即执行项

下一项只做 **Step 1：完整 Baseline Flow 自动测例**。

原因：

- 当前环境和 UE flow 已验证可运行。
- live replay 需要动态获取当前 TEID 和 endpoint。
- 控制面模板需要稳定、自动生成的新鲜抓包。
- dashboard 和 issue 测试都依赖统一 testcase result JSON。

Step 1 完成前，不开始 dashboard，也不直接向 Open5GS 注入控制面变异消息。
