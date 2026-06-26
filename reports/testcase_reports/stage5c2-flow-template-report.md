# 阶段 5C.2：自动化 UE Flow 与模板提取报告

> 日期：2026-06-04

## 结论

Stage 5C.2 验收通过。两条 flow 均由一条命令真实运行、生成结构化结果与跨协议 timeline，并在退出前恢复默认 baseline：

```bash
./scripts/flows/run_ue_flow.sh registration_pdu_session
./scripts/flows/run_ue_flow.sh registration_release
```

第二条 flow 是注册后由 CU-UP 不活跃定时器触发的合法 Release，不是 Deregistration，也没有用停止 UE 容器冒充注销。UE 在收到 `rrcRelease` 前始终运行。

## 验收结果

| Flow | Run | 控制消息 | GTP-U | Timeline | 结果 |
|---|---|---:|---:|---:|---|
| 注册 + PDU Session | `registration_pdu_session_20260604_151300` | 42 | 3 | 45 | PASS |
| 注册 + Release | `registration_release_20260604_151613` | 50 | 1 | 51 | PASS |

Release run 同时验证：

- F1AP `UEContextReleaseCommand` / `UEContextReleaseComplete`
- E1AP `BearerContextReleaseCommand` / `BearerContextReleaseComplete`
- NGAP `UEContextReleaseRequest` / `Command` / `Complete`
- UE 日志中的 `rrcRelease`
- CU-CP、CU-UP、DU、Open5GS 日志中的状态机推进证据

这是完整 flow 的 L4 状态机证据，不代表单消息 replay 已达到 L3/L4。

## 模板覆盖

已提取并提交 10 类合法控制面 ASN.1 APER payload，其中包含计划要求的 6 类 F1AP/E1AP 控制消息：

1. F1AP UE Context Setup Request
2. F1AP UE Context Modification Request
3. F1AP UE Context Release Command
4. E1AP Bearer Context Setup Request
5. E1AP Bearer Context Modification Request
6. E1AP Bearer Context Release Command

另有 4 类 NGAP 模板：InitialUEMessage、PDU Session Resource Setup Request、UE Context Release Request、UE Context Release Command。

每个模板都包含 protocol、procedure、方向、SCTP stream/PPID、payload hex、关键 IE 以及 source run/frame。提交位置：

```text
tests/replay/templates/stage5c2/
```

## 当前 GTP-U Tunnel

从 PDU Session run 提取：

| 接口 | 方向 | TEID | 扩展信息 |
|---|---|---|---|
| F1-U | `172.18.10.3 -> 172.18.10.2` | `0x00000001` | NR RAN Container |
| N3 | `10.53.1.5 -> 10.53.1.3` | `0x00006f52` | PDU Session Container, QFI `1` |

TEID 是本次运行动态值，后续 live replay 必须重新从当前 session 获取，不能硬编码该报告中的值。

## 实现边界与问题修复

- srsUE 收到 `SIGINT` 只会执行 switching off，不会发送 NAS Deregistration；因此第二条课程允许的替代 flow 使用合法 inactivity-triggered Release。
- srsRAN 文件日志由用户态缓冲，直接读取 `/tmp/cu_cp.log` 和 `/tmp/cu_up.log` 会漏掉最新 Release 行。新增 opt-in `docker-compose.flow-evidence.yml` 仅在 flow 验收时将 CU 日志写到 stdout；baseline 配置不变。
- raw pcap、raw tshark JSON 和日志均未提交。

## Baseline

两条命令完成后均恢复默认：

```text
docker/compose/docker-compose.yml + docker/compose/docker-compose.split.yml
```

最终 `scripts/env/check_core_ready.sh` 通过。
