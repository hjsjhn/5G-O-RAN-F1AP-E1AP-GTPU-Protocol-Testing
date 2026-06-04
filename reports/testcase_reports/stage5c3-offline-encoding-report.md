# 阶段 5C.3：多协议离线可逆编码验收报告

> 日期：2026-06-04

## 结论

Stage 5C.3 验收通过。统一 runner 已实际完成 10 个离线 testcase，结果为
`10/10 PASS`：

```bash
./scripts/replay/run_replay_tests.sh
```

该阶段只证明 L1/L2，不把生成 pcap 或本机解析称为 live replay、对端识别或
状态机推进。

## 覆盖与等级

| 协议/消息 | 数量 | L1 | L2 | L3/L4 |
|---|---:|---|---|---|
| F1AP UE Context Setup/Modification/Release | 3 | PASS | PASS | 未在本阶段声明 |
| E1AP Bearer Context Setup/Modification/Release | 3 | PASS | PASS | 未在本阶段声明 |
| GTP-U N3 uplink/downlink T-PDU | 2 | PASS | PASS | 未在本阶段声明 |
| XnAP Handover Request/Request Acknowledge | 2 | PASS | PASS | 按约定豁免 live replay |

六类 F1AP/E1AP 控制消息超过课程要求的至少 5 类控制消息。

## 实现

- `encode_sctp_template.py` 使用标准库重建 Ethernet/IPv4/SCTP/DATA，包含
  SCTP CRC32c、stream、SSN、TSN 和 PPID。
- F1AP/E1AP 使用 5C.2 实际 flow 抓包提取的可追溯合法 APER payload。
- XnAP 使用 srsRAN Project 25.10.0 生成式 ASN.1 编码器构造最小合法
  Handover Request/Acknowledge；构造器内部执行 pack→unpack 检查。
- Stage 4 normalizer 已扩展 XnAP 协议和 `xnap.procedureCode`。
- testcase schema 已支持 GTP-U packet 或 SCTP ASN.1 template。

XnAP 构造可复现检查：

```bash
./scripts/replay/check_xnap_template_generation.sh
```

## 实际验收门槛

每个控制面 testcase 均实际检查：

1. template APER payload 可精确读回；
2. tshark 命中目标 protocol/procedure/message；
3. `_ws.malformed` 数量为 `0`；
4. Stage 4 normalized JSON 的 protocol、procedure code 和 procedure name 一致。

XnAP 还校验并归一化 source/target UE XnAP ID、PDU Session ID、cause、
NR Cell Identity、PLMN、QFI 和 NG-C UE reference 等常用 IE。

使用的解析器版本：

```text
TShark (Wireshark) 4.0.7
```

## 产物与边界

- 提交 testcase、schema、编码器、XnAP 构造器、模板和报告。
- 生成 pcap、runner 结构化结果和 normalized 临时结果均可再生成，未提交。
- raw pcap、raw tshark JSON 和日志未提交。
- 5C.4 仍需对选定 F1AP/E1AP 消息完成真实对端 L3、完成 GTP-U live replay，
  并建立 NGAP/Open5GS 测试入口。
