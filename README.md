# 5G O-RAN F1AP/E1AP/GTPU 协议测试

5G O-RAN 协议栈抓包、解析、重编码、回放与自动化测试项目，聚焦 F1AP、E1AP、XnAP 和 GTP-U。

## 项目目标

在实验环境中抓取 5G RAN 内部接口（F1/E1/Xn/NG）的控制面和用户面报文，解析为结构化 JSON，构建可逆编码和自动回放测试框架，验证消息能被对端组件正确处理。

**课程要求三项基本交付：**
1. E1AP/F1AP/XnAP/GTP-U 报文解析为结构化 JSON
2. ≥5 类控制消息 + GTP-U 的可逆编码（JSON → pcap，Wireshark 可识别）
3. 两条完整 UE 流程测试（注册+PDU Session / 注册+注销）

**加分项：** 真实手机接入（加分项1）、自动生成可被网络组件接收的测试例（加分项2）

## 技术架构

```
5GC (Open5GS)          RAN (srsRAN CU-DU Split)         UE
┌──────────┐     ┌──────────┬──────────┐          ┌─────┐
│ AMF/SMF  │NGAP │  CU-CP   │  E1AP    │          │     │
│ UPF/UDM  │────→│ (F1AP)   │←────────→│ CU-UP   │  UE │
│ UDR/AUSF │     │          │          │ (GTP-U) │     │
│ NRF/PCF  │     └────┬─────┘          └────┬─────┘     │
│ WebUI    │          │ F1AP                │ F1-U      │
│ MongoDB  │     ┌────┴─────┐              │           │
└──────────┘     │   DU     │←─────────────┘           │
                 │ (ZMQ RF) │                           │
                 └──────────┘                           └─────┘
```

所有组件基于 Docker Compose 部署，DU 使用 ZeroMQ 模拟空口（无需 SDR 硬件）。

- **核心网：** Open5GS（[herlesupreeth/docker_open5gs](https://github.com/herlesupreeth/docker_open5gs) 预构建镜像）
- **RAN：** srsRAN Project CU-DU Split（本地 ARM64 构建 / amd64 预构建镜像）
- **UE：** srsUE + ZMQ

## 目录结构

```
docker/
  compose/              Docker Compose 文件（5GC + RAN split）
  configs/              CU-CP/CU-UP/DU 组件配置（YAML），启用 pcap 输出
  open5gs-5gc/          herlesupreeth/docker_open5gs 克隆（配置模板）
  srsran-src/           srsRAN Project 源码（用于本地 ARM64 构建）
  Dockerfile.srsran     srsRAN ARM64 构建文件
scripts/
  env/                  环境启动/停止/重置/检查脚本
  capture/              抓包脚本
  parse/                pcap → tshark JSON → 规范化 JSON
  encode/               JSON/模板 → 二进制 → pcap
  replay/               报文回放/注入
  validate/             Wireshark 解码验证、日志分析、报告生成
json/                   tshark 原始 JSON / 规范化 JSON / 消息模板
captures/               原始抓包 / 处理后 / 生成的 pcap
reports/                测试用例报告 / 最终报告
tests/                  pytest 测试
docs/                   项目文档和实施进度
```

## 快速开始

```bash
# 1. 准备环境（首次需要）
./scripts/setup.sh          # 克隆依赖仓库、构建 ARM64 镜像、创建 .env

# 2. 启动环境
./scripts/env/start_env.sh  # 启动 5GC + CU-CP + CU-UP + DU

# 3. 检查状态
./scripts/env/check_env.sh

# 4. 在 WebUI 添加 UE 订阅：http://localhost:9999 (admin/1423)

# 5. 停止并收集 pcap 和日志
./scripts/env/stop_env.sh
```

## 协议接口

| 接口 | 协议 | 协议栈 | 说明 |
|------|------|--------|------|
| F1-C | F1AP | F1AP/SCTP/IP | CU-CP ↔ DU 控制面 |
| F1-U | GTP-U | GTP-U/UDP/IP | CU-UP ↔ DU 用户面 |
| E1 | E1AP | E1AP/SCTP/IP | CU-CP ↔ CU-UP 控制面 |
| Xn | XnAP | XnAP/SCTP/IP | gNB ↔ gNB（需多基站） |
| NG-C | NGAP | NGAP/SCTP/IP | CU-CP ↔ AMF |
| NG-U | GTP-U | GTP-U/UDP/IP | CU-UP ↔ UPF |

## 网络拓扑

```
5gc_net  172.22.0.0/24   → 所有 5GC NF 内部通信
ran_net  10.53.1.0/24    → AMF(.2) UPF(.3) CU-CP(.4) CU-UP(.5) DU(.6)
f1u_net  172.18.10.0/24  → CU-UP(.2) ↔ DU(.3) 用户面
```

## 环境要求

- macOS Apple Silicon / Linux x86_64
- Docker（OrbStack / Docker Desktop 均可）
- Docker Compose
- Python 3.10+
- tshark / Wireshark
- tcpdump（容器内抓包不需要）

## 实施进度

见 [docs/progress.md](docs/progress.md)。
