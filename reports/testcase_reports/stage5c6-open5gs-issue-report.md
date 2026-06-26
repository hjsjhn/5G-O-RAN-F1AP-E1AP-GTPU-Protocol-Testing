# 阶段 5C.6：Open5GS Issue-Driven Testcase 报告

> 日期：2026-06-05

## 结论

Stage 5C.6 已完成两个稳定 crash 复现：P0 `#4263` / PR `#4333` 的 NRF
`requester-features` overflow，以及 P0b `#4532` 的 SMF empty SUPI
SM Context Create crash。P1 `#4209` / PR `#4289` 已补充自动化时序测试，但当前环境下
3 轮 deregistration/re-registration 未复现 AMF crash，分类为 `NOT_REPRODUCED`。
P2 `#4327` PFCP Session Modification robustness testcase 已实现并跑通 live：当前 digest
会进入 `Cannot find FAR-ID[7777] in PDR` 错误路径，但 UPF 未崩溃，baseline 可恢复，
分类为 `PFCP_ERROR_NO_IMPACT`。

当前固定
Open5GS 镜像：

```text
ghcr.io/herlesupreeth/docker_open5gs@sha256:68247a557ae8e2a46beca39bceb06d63d0c3daebb9f6b95312be9384461154c1
Open5GS daemon v2.7.6-131-g782a97e
```

在该 digest 上，`requester-features=ffffffffffffffffffffffffffffffffffffffff` 通过
HTTP/2 prior knowledge 打到 `NRF /nnrf-disc/v1/nf-instances` 后，会触发
`FATAL` 日志并使 `nrf` 容器退出；`supi=""` 通过 HTTP/2 prior knowledge 打到
`SMF /nsmf-pdusession/v1/sm-contexts` 后，会触发 `ogs_hash_get_debug: Assertion
\`klen\` failed` 并使 `smf` 容器退出。两者分类结论均为：

```text
VULNERABLE_CRASH
```

live 验收结束后，runner 自动恢复 baseline，并再次通过
`./scripts/env/check_core_ready.sh`。

## 新增产物

- `tests/replay/open5gs_issues/nrf_requester_features_overflow.json`
- `tests/replay/open5gs_issues/smf_empty_supi_sm_context_create.json`
- `tests/replay/open5gs_issues/amf_dereg_rereg_late_sdm_delete.json`
- `tests/replay/open5gs_issues/upf_pfcp_create_far_without_pdr_reference.json`
- `scripts/replay/run_open5gs_issue_tests.py`
- `json/replay_results/stage5c6/open5gs_issue_results.json`
- `json/replay_results/stage5c6/open5gs_issue_4532_result.json`
- `json/replay_results/stage5c6/open5gs_issue_4289_result.json`
- `json/replay_results/stage5c6/open5gs_issue_4327_result.json`

这些产物已经具备 dashboard 直接消费的基础结构：case 元数据、请求摘要、分类、
目标容器前后状态、日志摘要、baseline 恢复状态。

## 验收命令

```bash
python3 scripts/replay/run_open5gs_issue_tests.py \
  --case tests/replay/open5gs_issues/nrf_requester_features_overflow.json \
  --output json/replay_results/stage5c6/open5gs_issue_results.json

python3 scripts/replay/run_open5gs_issue_tests.py --live \
  --case tests/replay/open5gs_issues/nrf_requester_features_overflow.json \
  --output json/replay_results/stage5c6/open5gs_issue_results.json

./scripts/env/check_core_ready.sh
```

P0b `#4532` SMF empty SUPI crash 命令：

```bash
python3 scripts/replay/run_open5gs_issue_tests.py \
  --case tests/replay/open5gs_issues/smf_empty_supi_sm_context_create.json \
  --output json/replay_results/stage5c6/open5gs_issue_4532_result.json

python3 scripts/replay/run_open5gs_issue_tests.py --live \
  --case tests/replay/open5gs_issues/smf_empty_supi_sm_context_create.json \
  --output json/replay_results/stage5c6/open5gs_issue_4532_result.json
```

P1 `#4289` 边界测试命令：

```bash
python3 scripts/replay/run_open5gs_issue_tests.py \
  --case tests/replay/open5gs_issues/amf_dereg_rereg_late_sdm_delete.json \
  --output json/replay_results/stage5c6/open5gs_issue_4289_result.json

python3 scripts/replay/run_open5gs_issue_tests.py --live \
  --case tests/replay/open5gs_issues/amf_dereg_rereg_late_sdm_delete.json \
  --output json/replay_results/stage5c6/open5gs_issue_4289_result.json
```

P2 `#4327` PFCP robustness 测试命令：

```bash
python3 scripts/replay/run_open5gs_issue_tests.py \
  --case tests/replay/open5gs_issues/upf_pfcp_create_far_without_pdr_reference.json \
  --output json/replay_results/stage5c6/open5gs_issue_4327_result.json

python3 scripts/replay/run_open5gs_issue_tests.py --live \
  --case tests/replay/open5gs_issues/upf_pfcp_create_far_without_pdr_reference.json \
  --output json/replay_results/stage5c6/open5gs_issue_4327_result.json
```

## Dry-Run 结果

| 项 | 结果 |
|---|---|
| 模式 | `dry-run` |
| 是否实际发送请求 | 否 |
| 结果文件 | `json/replay_results/stage5c6/open5gs_issue_results.json` |
| baseline 当时状态 | `baseline_ready_now=true` |
| 目标容器初始状态 | `nrf running` |

dry-run 只做 testcase 解析、请求摘要生成、目标容器状态采样和 baseline 可用性检查；
默认不向 Open5GS 发送任何流量。

## Live 结果

| 项 | 结果 |
|---|---|
| 模式 | `live` |
| 发送端 | `amf` 容器内 `curl --http2-prior-knowledge` |
| 目标 | `http://nrf:7777/nnrf-disc/v1/nf-instances` |
| HTTP 观测 | `curl exit 56`，`Connection reset by peer`，`http_status=0` |
| 容器状态变化 | `nrf: running -> exited` |
| 容器退出码 | `134` |
| Restart count 变化 | `0` |
| 日志命中 | `FATAL`、`Numerical result out of range`、`ogs_uint64_from_string` |
| 分类 | `VULNERABLE_CRASH` |

关键日志摘要：

```text
06/05 02:50:21.004: [core] FATAL: strtoll()) failed [9223372036854775807] (34:Numerical result out of range)
06/05 02:50:21.004: [core] FATAL: ogs_uint64_from_string: should not be reached.
06/05 02:50:21.017: [core] FATAL: backtrace() returned 9 addresses
```

这与 Issue `#4263` 描述和 PR `#4333` 修复目标一致：当前 digest 仍会在
`requester-features` 解析阶段触发 overflow/abort，而不是返回安全拒绝。

## Baseline 恢复

live 执行完成后，runner 自动调用 `scripts/env/restore_baseline.sh`，再执行
`./scripts/env/check_core_ready.sh`。

恢复结果：

- `restore_exit_code=0`
- `core_ready_exit_code=0`
- `baseline_restore.restored=true`
- 验收后关键容器再次处于运行状态，`nrf` 已重新启动

因此本次 live 验收后 baseline 已成功恢复。

## P0b `#4532` SMF Empty SUPI Crash

Issue `#4532` 报告 `POST /nsmf-pdusession/v1/sm-contexts` 中 `supi` 为空字符串时，
SMF 会把空 SUPI 传入 hash lookup 路径并触发 `klen` assertion。该 issue 报告版本为
`v2.7.7`，当前固定 digest 早于该版本和后续修复边界，因此适合作为当前镜像的
issue-driven crash testcase。

当前 testcase 从 `amf` 容器内发送 HTTP/2 prior knowledge 请求：

```text
POST http://smf:7777/nsmf-pdusession/v1/sm-contexts
Content-Type: application/json
```

核心 mutation：

```json
{
  "supi": "",
  "pduSessionId": 1,
  "dnn": "internet",
  "requestType": "INITIAL_REQUEST",
  "anType": "3GPP_ACCESS",
  "ratType": "NR"
}
```

live 结果：

| 项 | 结果 |
|---|---|
| 分类 | `VULNERABLE_CRASH` |
| HTTP 观测 | `curl exit 56`，`Connection reset by peer`，`http_status=0` |
| 容器状态变化 | `smf: running -> exited` |
| 容器退出码 | `134` |
| fatal/assert 命中 | 3 |
| baseline 恢复 | 成功 |

关键日志摘要：

```text
06/05 06:16:36.078: [core] FATAL: ogs_hash_get_debug: Assertion `klen` failed. (../lib/core/ogs-hash.c:316)
06/05 06:16:36.081: [core] FATAL: backtrace() returned 10 addresses (../lib/core/ogs-abort.c:37)
/open5gs/install/lib/x86_64-linux-gnu/libogscore.so.2(ogs_hash_get_debug+0x143)
```

这与 Issue `#4532` 的根因一致：空 SUPI 形成长度为 0 的 hash key，当前 digest 未安全拒绝，
而是触发 SMF abort。runner live 结束后已自动恢复 baseline，并再次通过
`./scripts/env/check_core_ready.sh`。

## P1 `#4209` / PR `#4289` AMF Race 边界测试

PR `#4289` 修复的是 UE-initiated Deregistration 后立即 re-registration 时，晚到的
`SDM_SUBSCRIPTIONS DELETE` SBI response 进入异常 GMM state 并导致 AMF crash 的问题。
该修复晚于当前 digest，因此被列为 P1 候选。

当前实现使用 UERANSIM `nr-cli` 自动执行：

1. 启动 UERANSIM gNB + UE，确认 UE 注册并建立 PDU Session。
2. 对 `imsi-001010123456780` 执行 `deregister normal`。
3. 等待 UE 重新进入 `RM-REGISTERED` / `MM-REGISTERED`。
4. 连续执行 3 轮。
5. 检查 AMF 容器状态、restart count、AMF 新增日志中的 fatal/assert 关键词。
6. 自动恢复 baseline。

live 结果：

| 项 | 结果 |
|---|---|
| 分类 | `NOT_REPRODUCED` |
| 轮次 | 3 |
| 每轮是否重新注册 | 是 |
| AMF 容器状态 | `running -> running` |
| AMF restart count 变化 | `0` |
| fatal/assert 命中 | 0 |
| 必要观测 | `Deregistration request`、`InitialUEMessage`、`Registration complete` 均出现 |
| baseline 恢复 | 成功 |

该结果不能宣传为漏洞复现。它只能说明：在当前 UERANSIM 自动时序、未人为延迟 SBI response
的条件下，当前 digest 没有复现 PR `#4289` 描述的 AMF crash。若后续要继续提高复现概率，
需要在 UDM/SMF/SCP 路径注入 SBI 延迟或乱序。

## P2 `#4327` PFCP Session Modification Create FAR 测试

PR `#4327` 修复的是 PFCP Session Modification 里 `Create FAR/QER/URR` 处理过于严格的问题：
旧实现会对没有先被 PDR 引用的 FAR/QER/URR ID 执行 `find()`，从而拒绝；修复后改为
`find_or_add()`，并让 remove 更幂等。

当前 testcase 的 live 流程：

1. 确认 baseline 可用。
2. 运行一次 UERANSIM smoke，建立 PDU Session。
3. 从 UPF 日志提取最新 `UE F-SEID`，得到 UPF SEID 和 UE IPv4。
4. 构造 PFCP Session Modification Request，携带 `Create FAR`：
   - `far_id=7777`
   - `apply_action=2`
5. 从 `smf` 容器内发送 `SMF:8805 -> UPF:8805` 的 PFCP UDP 包。
6. 采样 UPF/SMF 新增日志、UPF 容器状态和 restart count。
7. 自动恢复 baseline 并再次运行 `check_core_ready.sh`。

live 结果：

| 项 | 结果 |
|---|---|
| 分类 | `PFCP_ERROR_NO_IMPACT` |
| 发送路径 | `RAW_SEND=172.22.0.7:8805>172.22.0.8:8805` |
| 命中日志 | `Cannot find FAR-ID[7777] in PDR` |
| UPF 容器状态 | `running -> running` |
| UPF restart count 变化 | `0` |
| fatal/assert 命中 | 0 |
| baseline 恢复 | 成功 |

关键日志：

```text
06/05 03:36:58.463: [pfcp] ERROR: Cannot find FAR-ID[7777] in PDR (../lib/pfcp/handler.c:1136)
```

该结果可用于展示“issue-driven PFCP mutation 能进入真实 UPF 处理路径并触发 pre-fix
错误行为”。但它不是崩溃型漏洞：当前观测没有 UPF crash、restart 或核心网失效。
