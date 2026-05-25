# 阶段 4：pcap → JSON 解析与 IE 提取报告

> 日期：2026-05-22

## 结论

阶段 4 基线解析管线已跑通。当前自动化脚本可以从阶段 3 的完整帧 pcap 生成：

- 原始 tshark JSON：`json/tshark_raw/`
- 归一化控制面 JSON：F1AP / NGAP / E1AP
- 归一化用户面 JSON：GTP-U / NR-U / inner ICMP
- 汇总 JSON：协议计数、procedure 计数、TEID、外层 GTP-U flow

XnAP 当前未覆盖，因为现有环境只有单 gNB，未建立 Xn 接口；该项按计划后续用多 gNB 或样例 pcap 补齐。

## 输入

```bash
captures/raw/run_capture_ping_20260522_110820/ran_sctp_full.pcap
captures/raw/run_capture_ping_20260522_110820/gtpu_full.pcap
```

## 自动化命令

```bash
./scripts/parse/run_stage4_parse.sh captures/raw/run_capture_ping_20260522_110820
```

脚本会执行两步：

```bash
python3 scripts/parse/pcap_to_tshark_json.py \
  captures/raw/run_capture_ping_20260522_110820/ran_sctp_full.pcap \
  captures/raw/run_capture_ping_20260522_110820/gtpu_full.pcap \
  --prefix run_capture_ping_20260522_110820 \
  -o json/tshark_raw

python3 scripts/parse/normalize_pcaps.py \
  --sctp-pcap captures/raw/run_capture_ping_20260522_110820/ran_sctp_full.pcap \
  --gtpu-pcap captures/raw/run_capture_ping_20260522_110820/gtpu_full.pcap \
  --prefix run_capture_ping_20260522_110820 \
  -o json/normalized
```

## 输出

```bash
json/tshark_raw/run_capture_ping_20260522_110820_ran_sctp_full.tshark.json
json/tshark_raw/run_capture_ping_20260522_110820_gtpu_full.tshark.json
json/normalized/run_capture_ping_20260522_110820_control_plane_packets.json
json/normalized/run_capture_ping_20260522_110820_gtpu_packets.json
json/normalized/run_capture_ping_20260522_110820_summary.json
```

说明：`json/tshark_raw/*.json` 是可再生成的大文件，按 `.gitignore` 不入库；`json/normalized/*.json` 是阶段 4 的结构化交付物。

## 解析结果

### 控制面

总计 42 条控制面消息：

| 协议 | 条数 |
|------|------|
| F1AP | 25 |
| NGAP | 13 |
| E1AP | 4 |

主要 procedure：

| 协议 | Procedure | 条数 |
|------|-----------|------|
| F1AP | F1SetupRequest / F1SetupResponse | 2 |
| F1AP | InitialULRRCMessageTransfer | 1 |
| F1AP | DLRRCMessageTransfer | 7 |
| F1AP | ULRRCMessageTransfer | 9 |
| F1AP | UEContextSetupRequest / Response | 2 |
| F1AP | UEContextModificationRequest / Response | 2 |
| F1AP | F1RemovalRequest / Response | 2 |
| NGAP | InitialUEMessage | 1 |
| NGAP | DownlinkNASTransport | 3 |
| NGAP | UplinkNASTransport | 4 |
| NGAP | InitialContextSetupRequest / Response | 2 |
| NGAP | PDUSessionResourceSetupRequest / Response | 2 |
| NGAP | UERadioCapabilityInfoIndication | 1 |
| E1AP | BearerContextSetupRequest / Response | 2 |
| E1AP | BearerContextModificationRequest / Response | 2 |

已提取字段包括：

- frame number / time
- protocol stack / info
- outer IP endpoints
- SCTP ports
- procedureCode / procedure name
- F1AP C-RNTI、F1AP UE IDs（存在时）
- NGAP AMF/RAN UE NGAP IDs、PDU session ID（存在时）
- E1AP CU-CP/CU-UP UE E1AP IDs、DRB/QoS 字段（存在时）

### 用户面

总计 12 条 GTP-U 消息：

| 外层 flow | 条数 |
|-----------|------|
| 172.18.10.3 → 172.18.10.2 | 6 |
| 10.53.1.5 → 10.53.1.3 | 6 |

| TEID | 条数 | 说明 |
|------|------|------|
| 0x00000003 | 6 | F1-U，DU → CU-UP，NR-U DL Data Delivery Status |
| 0x00007cd5 | 6 | N3，CU-UP → UPF，承载 UE ping |

N3 GTP-U 中提取到 6 条 inner ICMP echo request：

- inner src：10.45.0.16
- inner dst：8.8.8.8
- GTP message type：0xff
- PDU session container type：1
- QFI：1

## 验证

已执行：

```bash
python3 -m py_compile scripts/parse/pcap_to_tshark_json.py scripts/parse/normalize_pcaps.py
./scripts/parse/run_stage4_parse.sh captures/raw/run_capture_ping_20260522_110820
python3 -m json.tool json/normalized/run_capture_ping_20260522_110820_summary.json
```

验证结果：

- Python 脚本语法检查通过
- 原始 tshark JSON 生成成功
- 归一化 JSON 生成成功
- summary JSON 可被标准 JSON parser 解析
- 协议计数与阶段 3 抓包验证结果一致

## 自动化边界

阶段 4 不依赖手工 Wireshark 操作。后续二次启动或新抓包后，只需要：

```bash
./scripts/capture/capture_traffic.sh run
./scripts/parse/run_stage4_parse.sh
```

如果传入指定抓包目录：

```bash
./scripts/parse/run_stage4_parse.sh captures/raw/<run_dir>
```
