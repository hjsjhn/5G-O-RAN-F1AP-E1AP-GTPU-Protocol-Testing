# 阶段 5C.4：JSON-Driven 同一 Payload 真实对端验证报告

> 日期：2026-06-05

## 结论

Stage 5C.4 控制面闭环验收通过。六类管理消息现在分别由独立结构化 JSON
testcase 驱动固定版本 srsRAN ASN.1 generator，生成唯一 APER payload。runner
使用完全相同的 payload：

```text
JSON testcase
→ ASN.1 generator
→ pcap
→ tshark L2
→ 外部 payload SCTP endpoint
→ CU-CP 接收日志
→ response procedure/outcome/message/transaction ID
```

endpoint 已移除消息构造逻辑，只负责在本地隔离网络中建立合法 SCTP association、
解码并发送外部 payload、接收和解码 response。正常 UE flow 中自然产生的消息未
计入本报告的控制面 L3/L4。

统一入口保持默认 dry-run：

```bash
./scripts/replay/run_live_peer_validation.sh --dry-run
./scripts/replay/run_live_peer_validation.sh --live
```

## F1AP/E1AP 同一 Payload 结果

真实对端为 srsRAN CU-CP。六个 JSON-generated payload 均达到 L1/L2，且
JSON-generated、从已写入 pcap 读回提取、实际 sent SHA-256 三者一致。五个
case 达到 L3；F1AP GNBDUConfigurationUpdate 和 E1AP
GNB-CU-UP-E1SetupRequest 达到严格 L4。

| Case / JSON 输入 | Payload SHA-256 | L2 | L3 | L4 / Response TID |
|---|---|---|---|---|
| F1SetupRequest<br>`tests/replay/live_cases/control/f1ap_f1_setup_request.json` | `3d85d75ded3e788acd1ca3cb721a42864240f1c8caf8d3aa589bba6e947388e9` | PASS | 未计入：缺匹配 CU-CP `Rx PDU` 日志 | 未计入；F1SetupFailure TID `41` 匹配但不绕过 L3 |
| GNBDUConfigurationUpdate<br>`tests/replay/live_cases/control/f1ap_gnb_du_configuration_update.json` | `d05ca7dc13d39dfbabfb1368d53f62747cb557ed0d6b3d86ccdc093570ebaf11` | PASS | PASS，`tid=42` | PASS，GNBDUConfigurationUpdateAcknowledge，TID `42` |
| F1 Reset<br>`tests/replay/live_cases/control/f1ap_reset.json` | `47925651ae82f7b08a59c61d583c79ba530d09f3ba802d1e4d1bbf64c51ad44a` | PASS | PASS，`tid=43` | 未收到响应 |
| GNB-CU-UP-E1SetupRequest<br>`tests/replay/live_cases/control/e1ap_gnb_cu_up_e1_setup_request.json` | `90027e96937716350a8f99a89ad349aba3cf4efa66ab37ae82d3500588334136` | PASS | PASS，`tid=51` | PASS，GNB-CU-UP-E1SetupResponse，TID `51` |
| GNB-CU-UP-ConfigurationUpdate<br>`tests/replay/live_cases/control/e1ap_gnb_cu_up_configuration_update.json` | `6bd2fff54a047e40067cfc9fea043cba91baa20294bd72a9a8d49321ff2b733e` | PASS | PASS，`tid=52` | 未收到响应 |
| E1 Reset<br>`tests/replay/live_cases/control/e1ap_reset.json` | `1a947fe50dca9a36f7b12c3be0a91238ef780e9559c40e6d07ded87baa26f8e5` | PASS | PASS，`tid=53` | 未收到响应 |

每个 L2 均检查目标协议、procedure、TransactionID、case 中声明的关键 ID 和
`_ws.malformed=0`。每个 L3 必须同时满足三份 payload hash 一致、endpoint
解码出的 request message/procedure/TID 与 JSON 一致，以及 CU-CP 带相同 TID 的
`Rx PDU` 日志。L4 额外同时要求 response 存在且 procedure、outcome、消息名和
transaction ID 全部匹配；TID 不匹配时不会计为 L4。

结构化运行结果位于可再生成的
`json/replay_results/stage5c4/control_peer_validation.json`，未提交。

## GTP-U Live Replay

GTP-U 继续动态提取当前 session endpoint/TEID，使用同一生成 payload 完成
tshark L2、实际发送、CU-UP `RX SDU`、PDCP/F1-U 推进和 UE `RX PDU`，达到
L1-L4。它与控制面 JSON 闭环分开记录。

## NGAP/Open5GS Testcase 入口

NGAP 入口接受显式 testcase/mutation。验收继续使用 TAC mismatch：

```bash
python3 scripts/replay/run_ngap_open5gs_test.py --live \
  --case tests/replay/ngap_cases/tac_mismatch.json
```

该能力仍准确分类为协议感知配置 mutation，不是 payload replay，因此不声明
NGAP replay L1-L4。普通 UERANSIM registration/PDU Session smoke 继续单独保留。

## 可复现依赖

```bash
./scripts/replay/prepare_replay_dependencies.sh --prepare
./scripts/replay/prepare_replay_dependencies.sh --check
```

- srsRAN source commit：
  `4bf1543936d062686d64c10724d2f27a9854f065`
- builder image：
  `pavonis/srs-gnb-dev@sha256:820ba5ed9056ba8f913ef6b749bf24cd72127ceadf040d60fbc56193368bb344`

## 恢复、安全与边界

- 默认 `--dry-run` 不创建 SCTP association；它只生成 JSON payload 并执行 L2。
- live 场景只作用于本地私有 Docker 网络，结束或失败后严格恢复 baseline。
- 强制 flow 失败保留原始退出码 `96` 并恢复健康；模拟恢复失败时 live runner
  返回非零 `97`，不会误报 PASS。
- F1 Setup 缺少可关联 CU-CP 接收日志，因此不计 L3/L4。
- F1 Reset、E1 Configuration Update、E1 Reset 达到 L3，但没有预期响应，不计 L4。
- XnAP 是唯一豁免 live replay 的协议。
- raw pcap、raw tshark JSON、日志、运行结果和本地 srsRAN 源码未提交。
