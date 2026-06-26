# 阶段 5C.5：两条完整 UE Flow 最终验收报告

> 日期：2026-06-05

## 结论

Stage 5C.5 最终独立验收通过。两条 flow 均使用公开默认命令独立运行，不启用
5C.4 live GTP-U hook：

```bash
./scripts/flows/run_ue_flow.sh registration_pdu_session
./scripts/flows/run_ue_flow.sh registration_release
```

每条命令均自动检查 baseline、执行 UE 行为、抓取 F1AP/E1AP/NGAP/GTP-U、
生成跨协议 timeline、检查 UE/CU/DU/Open5GS 日志并输出结构化 PASS/FAIL。

## 最终运行

| Flow | Run ID | 控制消息 | GTP-U | Timeline | 结果 | 结束后 baseline |
|---|---|---:|---:|---:|---|---|
| Registration + PDU Session | `registration_pdu_session_20260605_005309` | 38 | 1 | 39 | PASS | HEALTHY |
| Registration + Release | `registration_release_20260605_005543` | 46 | 3 | 49 | PASS | HEALTHY |

运行时结构化结果位于各自的
`json/flow_results/<run-id>/result.json` 和 `result.md`；这些可再生成产物未提交。

## PDU Session 状态机证据

| 组件 | 实际检查 |
|---|---|
| UE | 处理 Registration Accept；PDU Session Establishment successful |
| CU-CP | 收到 BearerContextSetupResponse 和 UEContextModificationResponse |
| CU-UP | 配置 NG-U/NR-U tunnel；返回 BearerContextSetupResponse |
| DU | 收到/完成 UE context setup/modification；配置 NR-U tunnel |
| Open5GS | AMF session 数量变为 1 |
| 跨协议 | 捕获 InitialUEMessage、PDU Session Resource Setup、F1AP/E1AP setup/modification 和 GTP-U |

## Release 状态机证据

Release flow 在 srsUE 继续运行时等待 CU-UP inactivity timer 触发合法释放，未用
停止 UE 容器冒充 Deregistration。

| 组件 | 实际检查 |
|---|---|
| UE | 收到 `rrcRelease` |
| CU-CP | 收到 BearerContextReleaseComplete 和 UEContextReleaseComplete |
| CU-UP | 收到 BearerContextReleaseCommand，断开 PDU session，并返回 Complete |
| DU | 收到 UEContextReleaseCommand；抓包独立要求 UEContextReleaseComplete |
| Open5GS | AMF 日志记录 UE Context Release |
| 跨协议 | F1AP、E1AP、NGAP Release Request/Command/Complete 全部存在 |

## 边界与产物规则

- 两条 flow 都达到 L4：状态机推进并产生预期响应/完成消息。
- Release 是课程允许的 `Deregistration / Release` 路径，不声明为 NAS
  Deregistration。
- raw pcap、raw tshark JSON 和日志未提交；提交本报告和可复现命令。
- 两条 flow 结束后均实际运行 `scripts/env/check_core_ready.sh` 并通过。
- 额外强制失败验收确认：测试失败保留原始退出码 `96` 并恢复 baseline；模拟
  恢复失败时 live runner 返回非零 `97`，不会误报 PASS。
