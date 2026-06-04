下面是一份可以直接交给 agent 执行的 **项目实施文档**。历史 v1 按“先跑通、再抓包、再解析、再编码、再自动化”的顺序写；2026-05-30 起以后续 v2 计划为准。

## 2026-05-30 v2 调整

阶段 0-4 已完成：baseline 环境、UE 注册/PDU Session、完整帧抓包、F1AP/NGAP/E1AP/GTP-U 解析。

阶段 4.5 已完成：

- Open5GS 镜像固定到 digest，容器内版本为 `Open5GS daemon v2.7.6-131-g782a97e`。
- XnAP 完整 inter-gNB handover 不作为运行环境目标；XnAP 改为离线解析/构造，不要求 replay。
- Handover 实验与编码/回放/完整 UE flow 测试并行推进。
- baseline 保持稳定，新增实验环境使用 compose overlay 或 scenario 脚本。

后续并行任务：

```text
阶段 5A：F1 Handover 实验线
  - 同 CU-CP 下双 cell / F1 handover
  - 抓 F1/RRC/NGAP handover 相关信令
  - 输出 pcap、normalized JSON、支持边界报告

阶段 5B：N2 Handover 实验线
  - 两套 gNB/CU-DU 接入同一 Open5GS
  - 尝试 AMF-mediated handover
  - 输出 N2/NGAP 抓包、解析结果、支持边界报告

阶段 5C：编码/回放/自动测例主线
  - JSON/template → pcap
  - GTP-U 和至少 5 类控制面消息可被 tshark/Wireshark 识别
  - F1AP/E1AP/GTP-U 必须进入对端组件验证；NGAP 用于跨层/Open5GS issue 测试
  - XnAP 仍需完成离线解析/构造和 Wireshark 识别，仅豁免 live replay
  - 两条完整 UE flow 自动化测试
  - Open5GS v2.7.6 issue-driven bug reproduction 和安全分析

阶段 6：前端展示与最终报告
  - dashboard 左侧展示信令 timeline / JSON
  - dashboard 右侧展示环境实时 log / testcase 输出
  - 整合最终报告和演示脚本
```

建议开发分支：

```text
feature/f1-handover
feature/n2-handover
feature/replay-issue-dashboard
```

协作约束见 `docs/collaboration.md`。下面的历史计划作为背景参考；若与 v2 冲突，以本节为准。

Stage 5C 的详细执行顺序、协议覆盖矩阵和验收门槛见 `docs/replay-execution-plan.md`。其中 “GTP-U 优先” 只表示编码实现起点，不能解释为只对 GTP-U 做 live replay 或省略 F1AP/E1AP 的对端验证。

---

# 5G O-RAN 协议栈解析和测试项目实施文档

## 0. 项目目标概括

本项目目标是围绕 5G RAN 内部协议栈做 **抓包、解析、结构化、重编码、回放和验证**。

课程说明要求解析并测试 5G NR 中 RAN 内部控制面与用户面协议栈，重点关注：

```text
CU ⇄ DU：F1 接口
CU-CP ⇄ CU-UP：E1 接口
gNB ⇄ gNB：Xn 接口
RAN ⇄ Core：与 NG 接口相关的跨层交互
```

需要在实验环境中抓取这些接口报文，解析成结构化 JSON，构建可回放测试用例，并验证消息能被对端正确处理。课程还要求至少完成 E1AP/F1AP/XnAP/GTP-U 报文解析、至少 5 类控制消息和 GTP-U 包的可逆编码、以及两条 UE 完整流程测试；加分项包括真实手机接入和自动生成可被网络组件接收的测试例。

本项目建议采用：

```text
OCUDU / srsRAN CU-DU split
+
Open5GS
+
Docker Compose
+
srsUE / ZMQ 或后续真实 UE
+
tshark / Pyshark / Scapy
```

---

# 1. 推荐总体路线

## 1.1 项目主线

```text
环境部署
  ↓
UE 注册与 PDU Session 跑通
  ↓
CU/DU split 抓 F1/E1/GTP-U/NGAP 报文
  ↓
tshark/Pyshark 解析 pcap
  ↓
提取关键 IE，转为规范化 JSON
  ↓
从 JSON 或模板重新编码报文
  ↓
生成 pcap
  ↓
Wireshark 验证
  ↓
回放给对端组件
  ↓
检查日志和状态机
  ↓
自动生成测试例与测试报告
```

---

# 2. 技术选型

## 2.1 RAN：OCUDU / srsRAN Project

优先使用 **OCUDU / srsRAN 的 CU-DU split Docker Compose**。

理由：

1. srsRAN 官方文档明确支持 `srsCU` 和 `srsDU` 配置运行，用于构建带 CU-DU split 的端到端 O-RAN compliant network。([srsRAN Documentation][1])
2. srsRAN Docker README 中提供了多 Compose 文件部署方式，其中 `docker-compose.split.yml` 包含 `cu-cp`、`cu-up`、`du` 服务，用来替代单体 gNB；组合命令可以启动 `cu-cp + cu-up + du + core`。([GitHub][2])
3. srsRAN Project 旧仓库已在 2026-02-17 归档只读，后续更应关注 OCUDU 路线；但旧仓库的 Docker split 结构仍可作为重要参考。([GitHub][2])

## 2.2 Core：Open5GS

优先使用 Open5GS，原因是：

```text
srsRAN 官方文档和示例大量使用 Open5GS
Open5GS 配置相对成熟
课程项目不要求深入修改核心网
Open5GS 足够支持 UE 注册、PDU Session、N2/N3 抓包
```

## 2.3 UE：优先 srsUE + ZMQ，后续再考虑真实手机

srsRAN Project 本身不包含 UE application，但 srsRAN 4G 中提供 prototype 5G UE，即 srsUE，可用于测试 srsRAN Project gNB 和 Open5GS；官方教程覆盖 over-the-air、ZeroMQ 和 multi-UE emulation。([srsRAN Documentation][3])

但需要注意：srsUE 的 5G 扩展已经不活跃开发，官方定位是 proof-of-concept 和 initial testing，不是 deployment-ready 方案；并且 5G SA 模式下有功能限制，例如不支持 handover。([srsRAN Documentation][3])

所以：

```text
第一阶段：srsUE + ZMQ
第二阶段：如时间允许，再考虑真实 UE + SDR
不建议第一阶段直接做真实手机
```

---

# 3. 项目阶段划分

建议分成 6 个阶段：

```text
阶段 0：代码仓库和文档结构准备
阶段 1：Docker Compose 环境部署
阶段 2：UE 基础流程跑通
阶段 3：接口抓包与协议识别
阶段 4：pcap → JSON 解析与 IE 提取
阶段 5：JSON/template → pcap 重编码与验证
阶段 6：自动化测试生成与报告
```

---

# 4. 阶段 0：仓库结构准备

建议建立如下项目目录：

```text
oran-protocol-test/
├── README.md
├── docs/
│   ├── 00_project_requirement.md
│   ├── 01_environment_setup.md
│   ├── 02_protocol_background.md
│   ├── 03_packet_capture_plan.md
│   ├── 04_json_schema.md
│   ├── 05_replay_validation.md
│   └── 06_final_report_notes.md
│
├── docker/
│   ├── README.md
│   ├── compose/
│   │   ├── docker-compose.yml
│   │   ├── docker-compose.split.yml
│   │   └── .env
│   └── configs/
│       ├── open5gs/
│       ├── cu_cp.yml
│       ├── cu_up.yml
│       ├── du.yml
│       └── ue.conf
│
├── scripts/
│   ├── env/
│   │   ├── start_env.sh
│   │   ├── stop_env.sh
│   │   ├── reset_env.sh
│   │   └── check_env.sh
│   │
│   ├── capture/
│   │   ├── start_capture.sh
│   │   ├── stop_capture.sh
│   │   └── list_interfaces.sh
│   │
│   ├── parse/
│   │   ├── pcap_to_tshark_json.py
│   │   ├── normalize_f1ap.py
│   │   ├── normalize_e1ap.py
│   │   ├── normalize_xnap.py
│   │   ├── normalize_gtpu.py
│   │   └── extract_flow.py
│   │
│   ├── encode/
│   │   ├── encode_gtpu.py
│   │   ├── encode_f1ap_template.py
│   │   ├── encode_e1ap_template.py
│   │   └── build_pcap.py
│   │
│   ├── replay/
│   │   ├── replay_pcap.py
│   │   ├── inject_packet.py
│   │   └── replay_flow.py
│   │
│   └── validate/
│       ├── validate_wireshark_decode.py
│       ├── validate_logs.py
│       ├── validate_flow_state.py
│       └── generate_report.py
│
├── captures/
│   ├── raw/
│   ├── processed/
│   └── generated/
│
├── json/
│   ├── tshark_raw/
│   ├── normalized/
│   └── templates/
│
├── logs/
│   ├── open5gs/
│   ├── cu_cp/
│   ├── cu_up/
│   ├── du/
│   └── ue/
│
├── reports/
│   ├── testcase_reports/
│   └── final/
│
└── tests/
    ├── test_parse.py
    ├── test_encode_gtpu.py
    └── test_validate.py
```

---

# 5. 阶段 1：Docker Compose 环境部署

## 5.1 目标

搭建一个可以运行的本机 Docker Compose 环境，至少包含：

```text
Open5GS / 5GC
CU-CP
CU-UP
DU
UE / srsUE 或后续外部 UE
```

优先尝试官方或 OCUDU 继承的 split compose：

```bash
docker compose -f docker/docker-compose.yml -f docker/docker-compose.split.yml up
```

srsRAN Docker README 中给出的 split 组合部署命令正是这种形式：`docker-compose.yml` 提供 core，`docker-compose.split.yml` 提供 `cu-cp`、`cu-up`、`du`，组合后可以运行 split architecture with core。([GitHub][2])

## 5.2 重要原则

不要在 Dockerfile 里配置网络。
应在 `docker-compose.yml` 里配置 network、固定 IP 和服务连接关系。

建议固定关键组件 IP：

```text
10.53.1.2   Open5GS AMF / Core side
10.53.1.4   CU-CP
10.53.1.5   CU-UP
10.53.1.6   DU

172.18.10.2 CU-UP F1-U
172.18.10.3 DU F1-U
```

可以根据实际 compose 调整，但必须保证：

```text
cu_cp.yml 中 AMF 地址 = Open5GS AMF 实际地址
cu_cp.yml 中 E1/F1 地址 = compose 里的 CU-UP/DU 地址
cu_up.yml 中 F1-U / N3 地址 = 实际 Docker network 地址
du.yml 中 CU 地址 = CU-CP/CU-UP 实际地址
Open5GS amf.yaml / upf.yaml 与 RAN 地址一致
```

## 5.3 Compose 网络建议

如果所有服务在一个 compose 项目里：

```yaml
networks:
  ran_net:
    ipam:
      config:
        - subnet: 10.53.1.0/24

  f1u_net:
    ipam:
      config:
        - subnet: 172.18.10.0/24
```

如果 Open5GS 和 OCUDU 是两个独立 compose 项目，则创建 external network：

```bash
docker network create --subnet 10.53.1.0/24 ran_net
docker network create --subnet 172.18.10.0/24 f1u_net
```

然后两个 compose 文件里都引用：

```yaml
networks:
  ran_net:
    external: true
    name: ran_net
```

srsRAN Docker README 也说明，如果使用已有 core network，可以把 srsRAN 容器连接到已有 AMF N2/N3 subnet，并通过 `external: true` 引用已有 Docker network。([GitHub][2])

---

# 6. 阶段 2：基础流程跑通

## 6.1 第一目标：容器全部启动

执行：

```bash
docker compose ps
docker compose logs -f
```

确认：

```text
Open5GS AMF/SMF/UPF 正常
CU-CP 正常
CU-UP 正常
DU 正常
UE 程序正常
```

## 6.2 第二目标：组件间连通性

进入容器测试：

```bash
docker exec -it <cu-cp-container> bash
ping 10.53.1.2   # AMF
ping 10.53.1.5   # CU-UP
ping 10.53.1.6   # DU
```

检查 Docker network：

```bash
docker network inspect ran_net
docker network inspect f1u_net
```

## 6.3 第三目标：UE 注册

观察日志中是否出现：

```text
UE registered
Registration complete
Initial UE Message
NG Setup
PDU Session Establishment
```

同时保存日志：

```bash
mkdir -p logs/run_001
docker compose logs cu-cp > logs/run_001/cu_cp.log
docker compose logs cu-up > logs/run_001/cu_up.log
docker compose logs du > logs/run_001/du.log
docker compose logs 5gc > logs/run_001/open5gs.log
```

## 6.4 第四目标：PDU Session 建立

检查：

```text
UE 是否拿到 IP
PDU Session 是否建立
UPF 是否创建 tunnel
是否有 GTP-U / UDP 2152 流量
```

如需 UE 出网，还要检查 host NAT 和路由。OCUDU split 部署实践中也提到，端到端 UE 到 Internet 可能需要处理 CU-UP NG-U bind 地址、路由和 NAT 等问题。([Nuradio Concepts][4])

---

# 7. 阶段 3：接口抓包

## 7.1 目标

抓取并保存如下接口流量：

```text
F1-C：CU-CP ⇄ DU，F1AP / SCTP / IP
F1-U：CU-UP ⇄ DU，GTP-U / UDP / IP
E1：CU-CP ⇄ CU-UP，E1AP / SCTP / IP
NG-C/N2：CU-CP ⇄ AMF，NGAP / SCTP / IP
NG-U/N3：CU-UP ⇄ UPF，GTP-U / UDP / IP
Xn：gNB ⇄ gNB，XnAP / SCTP / IP，如环境支持
```

课程要求覆盖 F1、E1、Xn、GTP-U，并分析与 NG 接口关联的跨层交互。

## 7.2 抓包方式

优先三种抓法并行尝试：

### 方式 A：容器内部抓包

```bash
docker exec -it <cu-cp-container> tcpdump -i any -w /tmp/cu_cp_any.pcap
docker cp <cu-cp-container>:/tmp/cu_cp_any.pcap captures/raw/cu_cp_any.pcap
```

### 方式 B：Docker bridge 上抓包

先找 interface：

```bash
ip link
docker network inspect ran_net
```

然后：

```bash
sudo tcpdump -i <bridge-iface> -w captures/raw/ran_net.pcap
```

### 方式 C：全接口抓包

```bash
sudo tcpdump -i any -w captures/raw/all_any.pcap
```

## 7.3 抓包过滤器

常见端口：

```text
SCTP：F1AP / E1AP / NGAP / XnAP 常见承载方式
UDP 2152：GTP-U
```

抓 GTP-U：

```bash
sudo tcpdump -i any udp port 2152 -w captures/raw/gtpu.pcap
```

抓 SCTP：

```bash
sudo tcpdump -i any sctp -w captures/raw/sctp.pcap
```

## 7.4 每次实验必须保存元数据

为每次抓包建立目录：

```text
captures/raw/run_001/
├── metadata.md
├── all_any.pcap
├── sctp.pcap
├── gtpu.pcap
├── cu_cp.log
├── cu_up.log
├── du.log
├── open5gs.log
└── ue.log
```

`metadata.md` 记录：

```text
实验时间
代码 commit
compose 文件版本
配置文件版本
UE IMSI/K/OPC/APN
是否 CU/DU split
是否 ZMQ
执行的流程：注册 / PDU Session / 注销
预期抓取协议
实际抓取协议
```

---

# 8. 阶段 4：pcap 解析为 JSON

## 8.1 第一层：tshark 原始 JSON

先不要自己手写 ASN.1 解码器。优先用 tshark：

```bash
tshark -r captures/raw/run_001/sctp.pcap -T json > json/tshark_raw/run_001_sctp.json
tshark -r captures/raw/run_001/gtpu.pcap -T json > json/tshark_raw/run_001_gtpu.json
```

课程说明也明确允许基于 tshark 导出 JSON，或用 Pyshark/Scapy 读取 pcap 并抽取关键 IE。

## 8.2 第二层：规范化 JSON

不要直接把 tshark JSON 当最终成果。需要转换成你们自己的 normalized JSON。

建议格式：

```json
{
  "packet_no": 42,
  "timestamp": "2026-05-18T12:00:00.123",
  "src_ip": "10.53.1.4",
  "dst_ip": "10.53.1.6",
  "transport": "SCTP",
  "protocol": "F1AP",
  "interface": "F1-C",
  "direction": "CU_TO_DU",
  "message": "UEContextSetupRequest",
  "procedure_code": "...",
  "ies": {
    "gnb_cu_ue_f1ap_id": "...",
    "gnb_du_ue_f1ap_id": "...",
    "serving_cell": "...",
    "drb_list": [],
    "srb_list": [],
    "rrc_container": "..."
  },
  "raw_refs": {
    "pcap": "captures/raw/run_001/sctp.pcap",
    "frame_no": 42
  }
}
```

## 8.3 需要覆盖的协议

最低要做：

```text
F1AP
E1AP，如果当前部署能抓到
GTP-U
NGAP，作为跨层分析辅助
XnAP，如果后续能搭多 gNB 或 handover 环境
```

课程要求中明确写了 E1AP/F1AP/XnAP/GTP-U 解析为结构化 JSON。

---

# 9. 阶段 5：关键 IE 提取

## 9.1 F1AP 常用 IE

重点提取：

```text
gNB-CU UE F1AP ID
gNB-DU UE F1AP ID
NR CGI / Cell ID
SRB 配置
DRB 配置
RRC Container
Cause
UL/DL RRC Message Transfer 相关字段
UE Context Setup / Release 相关字段
```

## 9.2 E1AP 常用 IE

重点提取：

```text
gNB-CU-CP UE E1AP ID
gNB-CU-UP UE E1AP ID
Bearer Context ID
PDU Session Resource
DRB ID
QoS Flow ID
GTP Tunnel 信息
TEID
Transport Layer Address
Cause
```

## 9.3 GTP-U 常用字段

重点提取：

```text
Outer src/dst IP
UDP src/dst port
GTP-U message type
TEID
Sequence number，如存在
Inner IP src/dst
Inner protocol
Payload length
```

## 9.4 NGAP 常用字段

用于跨层分析：

```text
RAN UE NGAP ID
AMF UE NGAP ID
Registration 相关消息
PDU Session Resource Setup 相关消息
Cause
NAS PDU
```

---

# 10. 阶段 6：流程级关联分析

## 10.1 注册 + PDU Session 建立流程

至少要能输出类似时间线：

```text
T1  UE → RAN：RRC / NAS Registration Request
T2  CU-CP → AMF：NGAP Initial UE Message
T3  AMF → CU-CP：NGAP Downlink NAS Transport
T4  CU-CP ⇄ DU：F1AP UE Context Setup / RRC Transfer
T5  AMF/SMF → CU-CP：PDU Session Resource Setup Request
T6  CU-CP ⇄ CU-UP：E1AP Bearer Context Setup，如可见
T7  CU-CP ⇄ DU：F1AP UE Context Modification / DRB setup
T8  CU-UP ⇄ DU / UPF：GTP-U tunnel 出现
```

## 10.2 注册 + 注销流程

至少要能输出：

```text
T1  UE 已注册
T2  UE 发起 Deregistration
T3  RAN/Core 释放上下文
T4  CU/DU 出现 UE Context Release
T5  用户面 tunnel 清理
```

## 10.3 输出格式

建议生成：

```text
reports/testcase_reports/run_001_flow.md
reports/testcase_reports/run_001_flow.json
```

JSON 示例：

```json
{
  "flow": "registration_pdu_session",
  "result": "PASS",
  "events": [
    {
      "time": "T1",
      "protocol": "NGAP",
      "message": "InitialUEMessage",
      "frame": 12
    },
    {
      "time": "T2",
      "protocol": "F1AP",
      "message": "UEContextSetupRequest",
      "frame": 25
    },
    {
      "time": "T3",
      "protocol": "GTP-U",
      "message": "GPDU",
      "frame": 91
    }
  ]
}
```

---

# 11. 阶段 7：重编码与 pcap 生成

这是核心难点。课程要求根据 JSON 重新编码至少 5 类控制消息和 GTP-U 包，生成 pcap，并能被 Wireshark 和对端正确识别。

## 11.1 推荐先做 GTP-U

GTP-U 结构相对简单，优先完成：

```text
JSON → GTP-U packet → pcap → Wireshark 识别
```

示例 JSON：

```json
{
  "protocol": "GTP-U",
  "outer_ip": {
    "src": "172.18.10.2",
    "dst": "172.18.10.3"
  },
  "udp": {
    "src_port": 2152,
    "dst_port": 2152
  },
  "gtpu": {
    "message_type": "GPDU",
    "teid": "0x12345678"
  },
  "inner_ip": {
    "src": "10.45.1.2",
    "dst": "8.8.8.8",
    "protocol": "ICMP"
  }
}
```

## 11.2 控制面消息建议选择

至少 5 类，建议选：

```text
1. F1AP UE Context Setup Request
2. F1AP UE Context Release Command
3. E1AP Bearer Context Setup Request
4. E1AP Bearer Context Modification Request
5. E1AP Bearer Context Release Command
```

如果 XnAP 环境能跑，再替换/增加：

```text
XnAP Handover Request
XnAP Handover Request Acknowledge
```

课程说明中举例包括 F1AP UE Context Setup/Release、E1AP Bearer Context Setup/Mod、XnAP Handover Prep/Req Ack。

## 11.3 编码实现策略

从易到难：

```text
策略 A：模板重放
从真实 pcap 中提取原始 bytes，只替换少量字段。

策略 B：模板化 ASN.1 编码
用固定消息模板 + 参数填充。

策略 C：调用 srsRAN / OCUDU 内部编码函数
复用已有 C/C++ 编码逻辑。

策略 D：完整 ASN.1 编码器
工作量最大，不建议第一阶段做。
```

建议第一阶段采用：

```text
GTP-U：Scapy 或自写简单编码
F1AP/E1AP：模板化重放 + 少量字段替换
```

---

# 12. 阶段 8：Wireshark 验证

每一个生成 pcap 都必须通过：

```bash
tshark -r captures/generated/testcase_001.pcap
```

并检查：

```text
是否识别为 F1AP / E1AP / GTP-U
是否出现 Malformed Packet
关键 IE 是否与 JSON 一致
```

建议生成验证报告：

```json
{
  "testcase": "f1ap_ue_context_setup_001",
  "wireshark_decode": "PASS",
  "protocol": "F1AP",
  "message": "UEContextSetupRequest",
  "malformed": false,
  "checked_fields": {
    "gnb_cu_ue_f1ap_id": "PASS",
    "gnb_du_ue_f1ap_id": "PASS"
  }
}
```

---

# 13. 阶段 9：对端组件验证

## 13.1 验证层次

对端验证分三级：

```text
Level 1：对端收到包
Level 2：对端日志显示识别了消息
Level 3：对端状态机推进，并产生预期响应
```

## 13.2 示例：F1AP UE Context Setup

输入：

```text
CU-CP → DU：UE Context Setup Request
```

成功条件：

```text
DU 日志出现 received UE Context Setup Request
DU 未报 decoding error
DU 返回 UE Context Setup Response
response 中 UE ID 与 request 匹配
Wireshark 可解析 response
```

## 13.3 示例：E1AP Bearer Context Setup

输入：

```text
CU-CP → CU-UP：Bearer Context Setup Request
```

成功条件：

```text
CU-UP 日志出现 Bearer Context Setup
CU-UP 返回 Bearer Context Setup Response
Response 中出现 tunnel / TEID 信息
后续 GTP-U 流量 TEID 与控制面配置可关联
```

---

# 14. 阶段 10：自动化测试生成，加分项 2

加分项 2 的本质不是“多生成几个包”，而是建立自动化闭环：

```text
真实抓包
  ↓
解析为 normalized JSON
  ↓
抽取模板
  ↓
自动填充合法字段
  ↓
生成 pcap
  ↓
自动验证 Wireshark 解析
  ↓
自动回放
  ↓
自动检查日志和响应
  ↓
输出 PASS/FAIL 报告
```

## 14.1 自动生成器输入

```text
json/templates/*.json
json/normalized/*.json
testcase_config.yml
```

`testcase_config.yml` 示例：

```yaml
testcases:
  - name: f1ap_ue_context_setup_basic
    protocol: F1AP
    message: UEContextSetupRequest
    template: templates/f1ap_ue_context_setup.json
    mutations:
      - field: gnb_cu_ue_f1ap_id
        values: [1, 2, 3]
      - field: drb_id
        values: [1]
    expected:
      peer: du
      response: UEContextSetupResponse

  - name: gtpu_basic_ping
    protocol: GTP-U
    template: templates/gtpu_gpdu.json
    mutations:
      - field: teid
        values: ["0x1001", "0x1002"]
    expected:
      wireshark_decode: true
```

## 14.2 自动生成器输出

```text
captures/generated/
├── f1ap_ue_context_setup_basic_001.pcap
├── f1ap_ue_context_setup_basic_002.pcap
└── gtpu_basic_ping_001.pcap

reports/testcase_reports/
├── f1ap_ue_context_setup_basic_001.json
├── f1ap_ue_context_setup_basic_002.json
└── summary.md
```

## 14.3 自动化报告格式

```json
{
  "summary": {
    "total": 10,
    "passed": 7,
    "failed": 3
  },
  "results": [
    {
      "testcase": "f1ap_ue_context_setup_basic_001",
      "protocol": "F1AP",
      "message": "UEContextSetupRequest",
      "wireshark_decode": "PASS",
      "peer_received": "PASS",
      "state_advanced": "PASS",
      "result": "PASS"
    }
  ]
}
```

---

# 15. 风险和降级方案

## 15.1 F1AP 优先级最高

F1 是课程核心之一，而且 CU/DU split 环境最容易自然产生 F1AP。必须优先保证：

```text
F1AP 能抓到
F1AP 能解析
F1AP 能提取 IE
至少 F1AP UE Context Setup / Release 能做模板化重编码
```

## 15.2 E1AP 需要实际确认

理论上 CU-CP 和 CU-UP 之间应有 E1 接口，但要确认当前 OCUDU/srsRAN Docker split 是否真的把 E1AP 以可抓包的 SCTP/IP 形式暴露出来。

如果抓不到：

```text
报告中说明当前实现中 E1 可能在内部模块间处理或未暴露为独立可抓接口
降级为重点分析 F1AP + GTP-U + NGAP
保留 E1AP 模板解析或理论分析
```

## 15.3 XnAP 不作为第一阶段承诺

Xn 需要多 gNB 或 handover 环境。srsUE 当前不支持 handover，这会影响 Xn/切换类流程验证。([srsRAN Documentation][3])

建议：

```text
第一阶段不承诺 XnAP 完整跑通
如时间足够，再尝试多 gNB 或查找已有 XnAP pcap
最终报告中说明 XnAP 的环境限制
```

## 15.4 重编码控制面消息是最大难点

如果完整 ASN.1 编码困难，则降级为：

```text
真实 pcap 中提取原始 payload
模板化替换少数字段
保持消息结构不变
生成 pcap
Wireshark 验证
```

---

# 16. 每周任务安排建议

## Week 1：环境和基础流程

目标：

```text
Docker Compose 环境启动
Open5GS + CU/DU + UE 基础流程跑通
UE 注册和 PDU Session 建立
```

产物：

```text
docs/01_environment_setup.md
captures/raw/run_001/
logs/run_001/
```

## Week 2：抓包和解析

目标：

```text
抓 F1AP / GTP-U / NGAP
尝试抓 E1AP
tshark 导出 JSON
完成 normalized JSON schema
```

产物：

```text
scripts/parse/
json/tshark_raw/
json/normalized/
docs/04_json_schema.md
```

## Week 3：流程分析和 IE 提取

目标：

```text
完成注册 + PDU Session 流程时间线
完成注册 + 注销流程时间线
提取关键 IE
```

产物：

```text
reports/testcase_reports/flow_registration_pdu.md
reports/testcase_reports/flow_deregistration.md
```

## Week 4：重编码和 pcap 生成

目标：

```text
完成 GTP-U 重编码
完成至少 2 类 F1AP 模板化重编码
尝试 E1AP 模板化重编码
```

产物：

```text
captures/generated/
scripts/encode/
reports/testcase_reports/wireshark_validation.md
```

## Week 5：回放和自动化

目标：

```text
完成 replay 脚本
完成 validate 脚本
完成自动测试生成器初版
```

产物：

```text
scripts/replay/
scripts/validate/
reports/testcase_reports/summary.md
```

## Week 6：整理报告和展示

目标：

```text
补实验截图
补流程图
整理最终报告
准备答辩 demo
```

产物：

```text
reports/final/
demo/
```

---

# 17. Agent 执行指令模板

可以给 agent 这样的任务描述：

```text
你需要按照项目实施文档逐步完成 5G O-RAN 协议栈解析和测试项目。

优先级如下：
1. 使用 OCUDU/srsRAN split Docker Compose + Open5GS 搭建实验环境。
2. 保证 CU-CP、CU-UP、DU、Open5GS 在 Docker Compose 网络中可互通。
3. 使用 srsUE/ZMQ 或项目已有 UE 方案跑通 UE 注册和 PDU Session 建立。
4. 抓取 F1AP、GTP-U、NGAP，并尝试抓取 E1AP。
5. 使用 tshark 导出 JSON。
6. 编写 Python 脚本将 tshark JSON 转换为 normalized JSON。
7. 提取 F1AP/E1AP/GTP-U/NGAP 常用 IE。
8. 建立注册+PDU Session 和注册+注销两条流程的时间线。
9. 优先实现 GTP-U 从 JSON 到 pcap 的重编码。
10. 对 F1AP/E1AP 使用模板化方式尝试重编码至少 5 类控制消息。
11. 对生成 pcap 做 Wireshark/tshark 验证。
12. 尝试回放测试例，并用组件日志判断是否被正确处理。
13. 最后实现自动化测试生成和 PASS/FAIL 报告。

如果某一步失败，不要跳过，需要记录：
- 使用的命令
- 报错日志
- 当前配置文件
- 判断失败原因
- 可选降级方案
```

---

# 18. 最终交付物清单

最终至少应提交：

```text
1. 环境部署文档
2. Docker Compose 配置和关键 YAML 配置
3. 原始 pcap
4. tshark 原始 JSON
5. normalized JSON
6. IE 提取脚本
7. 流程时间线报告
8. JSON → pcap 编码脚本
9. 生成的测试 pcap
10. Wireshark/tshark 验证结果
11. 回放测试日志
12. 自动化测试报告
13. 最终项目报告
```

---

# 19. 最低可接受成果和理想成果

## 最低可接受成果

```text
OCUDU/srsRAN + Open5GS 环境跑通
至少一条 UE 注册 + PDU Session 流程跑通
抓到 F1AP / GTP-U / NGAP
解析为 JSON
提取关键 IE
生成部分 GTP-U / F1AP 测试 pcap
Wireshark 能识别
```

## 课程基本要求目标

```text
E1AP/F1AP/XnAP/GTP-U 结构化 JSON
至少 5 类控制消息 + GTP-U 的可逆编码
两个完整 UE 流程测试
组件日志证明状态机推进
```

## 加分项 2 目标

```text
自动从真实抓包提取模板
自动生成测试例
自动重编码为 pcap
自动回放
自动检查 Wireshark 解析和组件日志
自动输出 PASS/FAIL 报告
```

---

# 20. 当前推荐的项目策略

不要一开始追求所有协议都完整覆盖。建议按这个优先级推进：

```text
第一优先级：
F1AP + GTP-U + NGAP + 注册/PDU Session

第二优先级：
E1AP 抓包与解析

第三优先级：
F1AP/E1AP 控制消息模板化重编码

第四优先级：
自动化测试生成

第五优先级：
XnAP / handover / 真实手机
```

一句话总结：

**先把 OCUDU/srsRAN CU-DU split + Open5GS 跑通，确保能抓到 F1AP 和 GTP-U；再把 pcap 解析成规范化 JSON；然后做模板化重编码和 Wireshark 验证；最后把生成、回放、日志检查串成自动化测试框架。**

[1]: https://docs.srsran.com/projects/project/en/latest/tutorials/source/cu_du_split/source/index.html "O-RAN CU-DU Split — srsRAN Project  documentation"
[2]: https://github.com/srsran/srsRAN_Project/blob/main/docker/README.md "srsRAN_Project/docker/README.md at main · srsran/srsRAN_Project · GitHub"
[3]: https://docs.srsran.com/projects/project/en/latest/tutorials/source/srsUE/source/index.html "srsRAN gNB with srsUE — srsRAN Project  documentation"
[4]: https://nuradioconcepts.io/2026/02/20/ocudu-docker-split-7-2-deployment/ "OCUDU Docker Split Deployment"
