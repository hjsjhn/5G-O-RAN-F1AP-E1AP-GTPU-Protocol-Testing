# 阶段 5C.4：多协议真实对端验证报告

> 日期：2026-06-04

## 结论

Stage 5C.4 验收通过。统一入口默认 dry-run，显式 live 模式实际完成：

```bash
./scripts/replay/run_live_peer_validation.sh --dry-run
./scripts/replay/run_live_peer_validation.sh --live
```

live 模式使用独立协议感知 SCTP 测试端，在隔离场景中临时替代 DU/CU-UP，
发送本次生成的 F1AP/E1AP testcase。结果按 case ID 关联 payload SHA-256、
发送时间、CU-CP 接收日志和响应；正常 UE flow 中自然产生的消息未计入控制面
replay L3/L4。

## F1AP/E1AP 真实对端结果

真实对端：srsRAN CU-CP。验收 run 中 6 个生成 case 有 5 个达到 L3；F1AP 和
E1AP 各有一个达到 L4。六个 live 生成 payload 还分别构造临时 pcap，经 tshark
确认协议/procedure 正确且非 malformed，因此均达到 L2。

| Case | Payload SHA-256 前缀 | L3：CU-CP `Rx PDU` | L4：响应 |
|---|---|---|---|
| F1SetupRequest | `3d85d75ded3e` | 未计入：当前结果缺匹配接收日志 | 未计入；虽收到 procedure 1 unsuccessful outcome，但不绕过 L3 |
| GNBDUConfigurationUpdate | `d05ca7dc13d3` | PASS，`tid=42` | PASS，`GNBDUConfigurationUpdateAcknowledge`，response hash `0ae04cd683d4` |
| F1 Reset | `47925651ae82` | PASS，`tid=43` | 未收到响应 |
| GNB-CU-UP-E1SetupRequest | `90027e969377` | PASS，`tid=51` | PASS，`GNB-CU-UP-E1SetupResponse`，response hash `41f18d00c88f` |
| GNB-CU-UP-ConfigurationUpdate | `6bd2fff54a04` | PASS，`tid=52` | 未收到响应 |
| E1 Reset | `1a947fe50dca` | PASS，`tid=53` | 未收到响应 |

每个通过 L3 的 case 均由唯一 transaction ID、同一隔离 association 和带时间戳
的 CU-CP `Rx PDU` 行关联到本次生成 payload。结构化运行结果位于可再生成的
`json/replay_results/stage5c4/control_peer_validation.json`，未作为静态证据提交。

## GTP-U Live Replay

验收 run `registration_pdu_session_20260604_205956` 动态提取并使用：

- UPF endpoint：`10.53.1.3:2152`
- CU-UP endpoint：`10.53.1.5`
- 当前下行 TEID：`0x000001`
- 当前上行 TEID：`0x00e276`
- 当前 UE 地址：`10.45.0.27`
- QFI：`1`
- Case ID：`gtpu_generated_current_session_downlink`
- 生成 payload SHA-256：`5a83c5203d75ab18784ee4672adc5f8ef1901a44a140b0802392c0b0e6f834a3`

生成 testcase 从本地 UPF namespace 发往当前 CU-UP endpoint/TEID。CU-UP
在发送前，同一 payload 的临时 pcap 已由 tshark 正确识别目标 TEID 且非
malformed；发送时间之后 CU-UP 记录目标 TEID 的 `RX SDU`，随后推进
PDCP/F1-U，UE 收到 PDU，因此 GTP-U 达到 L1-L4。

## NGAP/Open5GS Testcase 入口

入口现在接受显式 `--case`。验收使用：

```bash
python3 scripts/replay/run_ngap_open5gs_test.py --live \
  --case tests/replay/ngap_cases/tac_mismatch.json
```

UERANSIM gNB-only 测试端实际应用 `tracking_area_code: 999`，Open5GS 场景按预期
未完成 NG Setup，baseline 随后健康。该能力分类为协议感知配置 mutation，
不是 payload replay，因此报告中的 NGAP replay L1-L4 保持未声明。普通
UERANSIM registration/PDU Session smoke 继续单独保留。

## 恢复与安全验收

- 默认 `--dry-run` 不创建新 SCTP association、不发送 live packet。
- live 场景只作用于本地私有 Docker 网络，并使用 opt-in overlay。
- flow 中途强制失败时保留原始退出码 `96`，随后 baseline 恢复并通过健康检查。
- 模拟恢复函数失败时 live runner 返回非零 `97` 并明确报告恢复失败。
- 所有真实验收结束后 `scripts/env/check_core_ready.sh` 通过。
- XnAP 是唯一豁免 live replay 的协议。

## 边界

- F1 Setup 缺少可关联的 CU-CP 接收日志，因此不计 L3/L4，尽管收到了失败响应。
- F1 Reset、E1 Configuration Update、E1 Reset 达到 L3，但未收到预期响应，
  因此不计 L4。
- raw pcap、raw tshark JSON 和原始日志未提交。
