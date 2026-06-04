# 阶段 5C.1：Replay 数据模型与 GTP-U Encoder MVP 报告

> 日期：2026-06-04

## 目标

建立 replay 主线的第一个可复现闭环：

```text
JSON testcase -> packet encoding -> generated pcap -> tshark validation -> structured result JSON
```

该阶段只做离线编码与验证，不向运行中的 Open5GS/srsRAN 注入流量，也不修改 baseline Docker Compose 环境。

## 实现内容

- 定义 replay testcase v1 JSON schema：
  - `tests/replay/schema/replay-case-v1.schema.json`
- 实现 GTP-U 编码器：
  - `scripts/replay/encode_gtpu.py`
  - 仅使用 Python 标准库，无 Scapy 等第三方依赖
  - 编码 Ethernet / outer IPv4 / UDP / GTP-U / inner IPv4 / ICMP
  - 自动计算 IPv4、UDP 和 ICMP checksum
- 实现 replay test runner：
  - `scripts/replay/run_replay_tests.py`
  - `scripts/replay/run_replay_tests.sh`
  - 自动生成 pcap、调用 tshark、按 testcase 预期字段验证并输出 JSON
- 添加两个 N3 GTP-U testcase：
  - 上行 ICMP Echo Request
  - 下行 ICMP Echo Reply

## 运行方式

```bash
./scripts/replay/run_replay_tests.sh
```

运行产物：

```text
captures/generated/replay/*.pcap
json/replay_results/latest.json
```

这些运行产物可以重新生成，已通过 `.gitignore` 排除。

## 验证结果

运行结果：

```text
[PASS] gtpu_n3_downlink_icmp_echo_reply
[PASS] gtpu_n3_uplink_icmp_echo_request
```

tshark 已正确识别：

- 协议栈：Ethernet / IPv4 / UDP / GTP-U / IPv4 / ICMP
- GTP-U message type：`0xff` T-PDU
- 上行 TEID：`0x00007cd5`
- 下行 TEID：`0x00000003`
- 外层与内层 IPv4 地址
- UDP source/destination port `2152`
- ICMP type 和 sequence

此外，生成的上行 pcap 已使用现有 `scripts/parse/normalize_pcaps.py` 解析，能够得到与 Stage 4 真实抓包一致的 normalized GTP-U JSON 结构。

## 当前边界

- 当前实现属于 offline encoding/replay validation，不是 live packet injection。
- 当前仅实现 GTP-U T-PDU；尚未支持 PDU Session Container/QFI extension header。
- NGAP/F1AP/E1AP/XnAP 控制面消息需要后续引入合法 ASN.1 payload 模板或 ASN.1 PER 编码方案。
- SCTP 控制面 live replay 需要处理 association、stream 和协议状态，不应直接把普通 pcap 注入作为第一步。

## 下一步

1. 为控制面消息设计“合法 ASN.1 payload 模板 + JSON metadata/patch/mutation”格式。
2. 先实现至少一种控制面消息的离线 pcap 构造与 tshark 识别。
3. 为 GTP-U 增加可选 PDU Session Container/QFI 和 mutation testcase。
4. 在离线验证稳定后，再增加明确隔离的 live replay/injection 模式。
