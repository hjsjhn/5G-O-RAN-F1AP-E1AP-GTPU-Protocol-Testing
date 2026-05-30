# 协作和分支约定

> 2026-05-30

## 原则

当前 `main` 分支只承载稳定 baseline 和共享工具。F1 Handover、N2 Handover、重放/前端/issue 分析三条线并行推进，不能在未验证前破坏 baseline。

所有改动优先满足：

1. baseline 可以继续运行现有 `1 CU-CP + 1 CU-UP + 1 DU + Open5GS + srsUE` 流程。
2. 新实验环境用 compose overlay 或独立配置文件叠加，不直接改坏现有 `docker-compose.split.yml`、`cu_cp.yml`、`cu_up.yml`、`du_zmq.yml`。
3. 公共脚本要保持向后兼容；新增参数必须有默认值，默认行为仍跑 baseline。
4. raw pcap、raw tshark JSON、logs 不提交，只提交脚本、配置、normalized JSON 示例和报告。
5. 改动公共文件前先确认影响范围，尤其是 `.env.example`、`docker/compose/docker-compose.yml`、`scripts/env/start_env.sh`、解析器公共代码。

## 分支

建议从阶段 4.5 的 `main` 提交切三条工作线：

```text
feature/f1-handover
feature/n2-handover
feature/replay-issue-dashboard
```

分支职责：

| 分支 | 目标 | 不应做的事 |
|------|------|------------|
| `feature/f1-handover` | 同 CU-CP 下双 cell / F1 handover 实验、抓包、报告 | 不修改 N2 环境，不破坏 baseline |
| `feature/n2-handover` | 两套 gNB/CU-DU 接入同一 Open5GS，尝试 AMF-mediated handover | 不把 2CU+2DU 设为默认 baseline |
| `feature/replay-issue-dashboard` | 编码/回放、完整 UE flow 自动测例、Open5GS issue reproduction、前端 dashboard | 不依赖 F1/N2 handover 跑通 |

分支只用于开发隔离。最终交付仍应合回 `main`，并通过 scenario/overlay 选择运行环境，而不是要求用户 checkout 不同分支才能运行不同实验。

## Compose 组织

保留当前 baseline：

```bash
docker compose -f docker/compose/docker-compose.yml -f docker/compose/docker-compose.split.yml up -d
```

新增实验环境应使用 overlay：

```text
docker/compose/docker-compose.f1-ho.yml
docker/compose/docker-compose.n2-ho.yml
```

建议最终运行方式：

```bash
./scripts/env/start_env.sh baseline
./scripts/env/start_env.sh f1-ho
./scripts/env/start_env.sh n2-ho
```

在脚本改造完成前，也可以直接使用 compose 文件组合运行。

## 任务边界

### F1 Handover

优先尝试同一个 CU-CP 下双 cell，减少环境改动。若双 cell 不足以触发目标流程，再评估同 CU-CP 下多 DU。

交付目标：

- F1/RRC/NGAP handover 相关抓包。
- 解析结果和报告。
- 是否可完整跑通要如实记录。

### N2 Handover

目标是两套 gNB/CU-DU 接入同一个 Open5GS，通过 AMF/NGAP 观察 handover 相关流程。

交付目标：

- N2/NGAP handover 相关信令抓包或支持边界报告。
- 2CU+2DU overlay 配置。
- 不要求修改 baseline 为 2CU+2DU。

### Replay / Issue / Dashboard

这条线是最终展示主线，不依赖 handover 跑通。

交付目标：

- JSON/template 到 pcap 的编码。
- GTP-U 和至少 5 类控制面消息可被 tshark/Wireshark 识别。
- 两条完整 UE flow 自动化测试。
- 基于 Open5GS v2.7.6 issue 的重放/变异测试和安全分析。
- 前端 dashboard：左侧信令解析/JSON，右侧实时日志/testcase 输出。
