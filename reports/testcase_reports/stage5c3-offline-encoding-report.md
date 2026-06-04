# 阶段 5C.3：多协议离线可逆编码验收报告

> 日期：2026-06-04

## 结论

Stage 5C.3 验收通过。统一 runner 实际运行 10 个案例并全部通过：

```bash
./scripts/replay/run_replay_tests.sh
./scripts/replay/check_xnap_template_generation.sh
```

其中 6 类 F1AP/E1AP 不再复制模板 payload。testcase 提供结构化源 IE 和
mutation；固定版本的 srsRAN ASN.1 代码先解码模板、修改强类型 IE、重新 APER
编码，再构造 SCTP/IP/Ethernet pcap。runner 比较关键 IE、payload hash 和
Stage 4 normalized JSON。

## 覆盖与等级

| 协议/消息 | 数量 | L1 | L2 | L3/L4 |
|---|---:|---|---|---|
| F1AP UE Context Setup/Modification/Release | 3 | PASS：结构化 IE mutation 后重新 APER 编码 | PASS：tshark 正确识别、非 malformed、关键 IE 一致 | 本阶段不声明 |
| E1AP Bearer Context Setup/Modification/Release | 3 | PASS：结构化 IE mutation 后重新 APER 编码 | PASS：tshark 正确识别、非 malformed、关键 IE 一致 | 本阶段不声明 |
| GTP-U N3 uplink/downlink T-PDU | 2 | PASS | PASS | 本阶段不声明 |
| XnAP Handover Request/Request Acknowledge | 2 | PASS | PASS | 按约定豁免 live replay |

## F1AP/E1AP Mutation 证据

| Case | 结构化 mutation | Source SHA-256 前缀 | Generated SHA-256 前缀 |
|---|---|---|---|
| F1 UEContextSetupRequest | `GNB_CU_UE_F1AP_ID: 0 -> 101` | `62c703ac0835` | `d2d2df3ef412` |
| F1 UEContextModificationRequest | `GNB_CU_UE_F1AP_ID: 0 -> 102` | `b6c239fb3fb4` | `d103a0921f10` |
| F1 UEContextReleaseCommand | `GNB_CU_UE_F1AP_ID: 0 -> 103` | `0cc1bbdca037` | `3571d1d30e52` |
| E1 BearerContextSetupRequest | `GNB_CU_CP_UE_E1AP_ID: 0 -> 201` | `825065b74626` | `f4513350178b` |
| E1 BearerContextModificationRequest | `GNB_CU_CP_UE_E1AP_ID: 0 -> 202` | `f4fa7a8ba3a6` | `8b3621298368` |
| E1 BearerContextReleaseCommand | `GNB_CU_CP_UE_E1AP_ID: 0 -> 203` | `bc53ef30c1f6` | `026e35f42fff` |

六个 case 均同时通过：

1. ASN.1 解码后的源 IE 与 `structured_ies` 一致；
2. mutation 值写入强类型 ASN.1 对象；
3. 重新编码后的 APER payload 与源 payload 不同；
4. pcap 中生成 payload 可精确读回；
5. tshark 识别目标消息和修改后的关键 IE，`_ws.malformed=0`；
6. Stage 4 normalized JSON 中的关键 IE 与 testcase 一致。

## 可复现依赖

- srsRAN source commit：
  `4bf1543936d062686d64c10724d2f27a9854f065`
- ASN.1 builder image：
  `pavonis/srs-gnb-dev@sha256:820ba5ed9056ba8f913ef6b749bf24cd72127ceadf040d60fbc56193368bb344`

控制面 mutation 工具和 XnAP 构造检查都会在执行前验证源码 commit，并使用固定
image digest；不再使用 `latest`。

## 边界

- 模板保存完整合法 APER 上下文；JSON 当前结构化暴露并 mutation 关键 UE ID，
  不是把所有 ASN.1 IE 从零重建。
- 本报告只声明离线 L1/L2。生成 pcap 被 Wireshark 识别不等于 live replay。
- raw pcap、raw tshark JSON、日志和本地 srsRAN 源码未提交。
