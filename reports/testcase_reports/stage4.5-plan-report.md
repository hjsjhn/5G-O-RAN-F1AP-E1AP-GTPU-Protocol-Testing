# 阶段 4.5：可复现性与并行计划调整报告

> 日期：2026-05-30

## 结论

阶段 4.5 完成。项目从单线推进调整为三条并行工作线：

- F1 Handover 实验线
- N2 Handover 实验线
- 编码/回放/完整 UE flow / Open5GS issue reproduction / 前端展示主线

baseline 环境保持稳定，不在 `main` 上直接改成 handover 专用拓扑。

## 环境可复现性

Open5GS 镜像已固定 digest：

```text
ghcr.io/herlesupreeth/docker_open5gs@sha256:68247a557ae8e2a46beca39bceb06d63d0c3daebb9f6b95312be9384461154c1
```

容器内版本：

```text
Open5GS daemon v2.7.6-131-g782a97e
```

## 新任务边界

### XnAP

XnAP 完整 inter-gNB handover 不作为当前运行环境目标。XnAP 只做离线解析/构造展示，可使用样例 pcap 或构造消息，不要求 replay。

### F1 Handover

优先尝试同一个 CU-CP 下双 cell，尽量减少对 baseline 的改动。目标是抓取并解析 F1/RRC/NGAP handover 相关信令。

### N2 Handover

目标是两套 gNB/CU-DU 接入同一个 Open5GS，尝试观察 AMF-mediated handover。该线风险较高，若完整流程不可行，需要输出支持边界报告。

### 编码/回放/自动测例

这条线不依赖 handover 跑通。目标是完成 JSON/template → pcap、两条完整 UE flow 自动化测试、Open5GS issue-driven bug reproduction，并服务最终 dashboard 展示。

## 协作方式

从 `main` 切三条工作线：

```text
feature/f1-handover
feature/n2-handover
feature/replay-issue-dashboard
```

分支只用于开发隔离。最终交付应合并回 `main`，并通过 compose overlay 或 scenario 脚本选择运行环境。

共享协作约束见：

```text
docs/collaboration.md
```

## 验证

已验证 baseline compose 配置可解析：

```bash
docker compose -f docker/compose/docker-compose.yml -f docker/compose/docker-compose.split.yml --env-file docker/compose/.env config
```
