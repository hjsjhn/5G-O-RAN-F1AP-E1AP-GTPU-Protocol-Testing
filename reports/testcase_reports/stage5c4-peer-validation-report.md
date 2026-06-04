# 阶段 5C.4：多协议真实对端验收报告

> 日期：2026-06-04

## 结论

Stage 5C.4 验收通过。以下默认 dry-run、显式 live 的统一入口已实际运行：

```bash
./scripts/replay/run_live_peer_validation.sh --dry-run
./scripts/replay/run_live_peer_validation.sh --live
```

最终 live run 完成两条受控 UE flow、动态 GTP-U replay 和 NGAP/Open5GS
协议测试，结束后 baseline 健康检查通过。

## 严格等级结果

| 协议/消息 | 真实接收对端 | L3 | L4 证据 |
|---|---|---|---|
| F1AP UEContextSetupRequest | DU | PASS | UEContextSetupResponse 被 CU-CP 接收 |
| F1AP UEContextModificationRequest | DU | PASS | UEContextModificationResponse 被 CU-CP 接收 |
| F1AP UEContextReleaseCommand | DU | PASS | UEContextReleaseComplete 被 CU-CP 接收 |
| E1AP BearerContextSetupRequest | CU-UP | PASS | BearerContextSetupResponse 被 CU-CP 接收 |
| E1AP BearerContextModificationRequest | CU-UP | PASS | BearerContextModificationResponse 被 CU-CP 接收 |
| E1AP BearerContextReleaseCommand | CU-UP | PASS | BearerContextReleaseComplete 被 CU-CP 接收 |
| GTP-U downlink T-PDU | CU-UP | PASS | CU-UP `RX SDU` 后推进 PDCP/F1-U，UE 收到 PDU |
| NGAP InitialUEMessage / NG Setup | Open5GS AMF / UERANSIM gNB | PASS | NG Setup 响应、UE 注册和 PDU Session 均成功 |

F1AP/E1AP 共 6 类目标消息达到 L3/L4，超过课程要求的至少 5 类；不是用发送
动作或生成 pcap 代替对端识别。

## 可追溯运行

统一 live 验收使用：

- PDU flow：`registration_pdu_session_20260604_162322`
  - 38 条控制消息、7 条 GTP-U、45 个 timeline event，PASS
- Release flow：`registration_release_20260604_162553`
  - 46 条控制消息、3 条 GTP-U、49 个 timeline event，PASS
- structured peer result：`json/replay_results/stage5c4/peer_validation.json`
- structured NGAP result：`json/replay_results/stage5c4/ngap_open5gs.json`

这些运行产物和原始日志/pcap 可再生成且按规则不提交；本报告提交验收结论。

## GTP-U 动态 replay

最终 run 从当前 session 自动提取并使用：

- UPF endpoint：`10.53.1.3`
- CU-UP endpoint：`10.53.1.5`
- 当前下行 TEID：`0x000001`
- 当前上行 TEID：`0x003fcf`
- 当前 UE 地址：`10.45.0.16`
- QFI：`1`

live packet 只从本地 UPF network namespace 发往当前 CU-UP endpoint/TEID。
L3 要求 CU-UP 日志出现目标 TEID 的 `RX SDU`；L4 还要求 CU-UP 推进
PDCP/F1-U 并且 UE 日志出现 `RX PDU`。

## 安全与边界

- 默认模式是 dry-run；只有显式 `--live` 才运行受控场景或发送 GTP-U。
- live GTP-U 只允许当前本地容器的私有地址，并拒绝已移除的 tunnel。
- 每个 live 入口前后执行 baseline 健康检查；flow 异常时恢复默认 baseline。
- 控制面使用真实协议栈和已有 SCTP association 的受控 flow，不做原始 SCTP
  pcap 注入。
- XnAP 按既定范围唯一豁免 live replay，5C.3 已完成离线构造和 L2。
- raw pcap、raw tshark JSON 和日志未提交。
