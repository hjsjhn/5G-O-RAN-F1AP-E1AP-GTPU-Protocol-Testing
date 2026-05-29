# 5G O-RAN F1AP/E1AP/GTPU 协议测试

5G O-RAN 协议栈抓包、解析、重编码、回放与自动化测试项目，当前实验环境聚焦 F1AP、E1AP、NGAP 和 GTP-U；XnAP 需要多 gNB / Xn 场景或样例 pcap 另行补齐。

## 项目目标

在实验环境中抓取 5G RAN 内部接口（F1/E1/Xn/NG）的控制面和用户面报文，解析为结构化 JSON，构建可逆编码和自动回放测试框架，验证消息能被对端组件正确处理。

**课程要求三项基本交付：**
1. E1AP/F1AP/XnAP/GTP-U 报文解析为结构化 JSON
2. ≥5 类控制消息 + GTP-U 的可逆编码（JSON → pcap，Wireshark 可识别）
3. 两条完整 UE 流程测试（注册+PDU Session / 注册+注销）

**加分项：** 真实手机接入（加分项1）、自动生成可被网络组件接收的测试例（加分项2）

## 技术架构

```
UE (srsUE)            RAN (srsRAN CU-DU Split)                5GC (Open5GS)

                    +---------+   E1AP   +---------+        +---------+
              F1AP  |  CU-CP  |<------->|  CU-UP  |  N3    |  AMF    |
srsUE <--ZMQ--> DU  |  (NGAP) |         | (GTP-U) |<------>|  SMF    |
                    +---------+         +---------+        |  UPF    |
                       |                 |    |             |  UDM    |
                       | F1-C            | F1-U  N3        |  UDR    |
                       |                 |    |             |  AUSF   |
                    +--+-----------------+--+--+            |  NRF    |
                    |         DU (ZMQ RF)     |             |  PCF    |
                    +-------------------------+             |  WebUI  |
                                                            | MongoDB |
                                                            +---------+
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
  capture/              容器内 tcpdump 抓包脚本
  parse/                pcap → tshark JSON → 规范化 JSON
  encode/               JSON/模板 → 二进制 → pcap（待实现）
  replay/               报文回放/注入（待实现）
  validate/             Wireshark 解码验证、日志分析、报告生成（待实现）
json/                   tshark 原始 JSON / 规范化 JSON / 消息模板
captures/               原始抓包 / 处理后 / 生成的 pcap
reports/                测试用例报告 / 最终报告
tests/                  pytest 测试
docs/                   项目文档和实施进度
```

## 快速开始

### 0. 首次准备

本仓库没有 `scripts/setup.sh`。当前启动脚本会自动创建 `docker/compose/.env`，也会在本地镜像缺失时构建 `srsran/gnb:local-arm64`。

如果本机还没有 `docker/srsran-src/`，先克隆 srsRAN Project 源码，因为 `docker/Dockerfile.srsran` 会从这个目录构建本地 ARM64 CU/DU/gNB 镜像：

```bash
git clone https://github.com/srsran/srsRAN_Project.git docker/srsran-src
```

`docker/compose/.env` 会由 `scripts/env/start_env.sh` 从 `docker/compose/.env.example` 自动生成；需要改 IMSI/Ki/OPc 或 IP 拓扑时再手动编辑。

### 1. 启动 5GC + srsRAN split CU/DU

```bash
./scripts/env/start_env.sh
./scripts/env/check_env.sh
./scripts/env/check_core_ready.sh
```

`check_core_ready.sh` 成功时会确认：

- Open5GS 5GC 容器已运行
- SMF/UPF PFCP 已关联
- CU-CP ↔ AMF 的 NGAP SCTP 已建立
- CU-CP ↔ CU-UP 的 E1AP SCTP 已建立
- DU ↔ CU-CP 的 F1AP SCTP 已建立

### 2. 跑 srsUE 注册 + PDU Session

```bash
./scripts/env/run_srsue_zmq_smoke.sh run
```

这个脚本会自动：

1. 检查 5GC + RAN 链路是否就绪
2. 调用 `scripts/env/provision_subscriber.sh` 注入 UE 订阅
3. 构建 `srsue-5g-zmq:local` 镜像（如果缺失）
4. 重建 DU 以触发干净的 F1Setup
5. 启动 srsUE over ZMQ
6. 等待 `tun_srsue` 拿到 IPv4 地址

常用辅助命令：

```bash
./scripts/env/run_srsue_zmq_smoke.sh logs
./scripts/env/run_srsue_zmq_smoke.sh debug
./scripts/env/run_srsue_zmq_smoke.sh down
```

### 3. 自动抓包

```bash
./scripts/capture/capture_traffic.sh run
```

该脚本会在目标容器内安装/启动 tcpdump：

- CU-CP 容器抓 SCTP：F1AP / NGAP / E1AP
- CU-UP 容器抓 UDP/2152：F1-U / N3 GTP-U
- 自动运行 srsUE smoke test
- 尝试从 UE 的 `tun_srsue` 生成 ping 流量
- 输出到 `captures/raw/run_YYYYMMDD_HHMMSS/`

也可以指定输出目录：

```bash
./scripts/capture/capture_traffic.sh run captures/raw/my_run
```

### 4. 自动解析为 JSON

```bash
./scripts/parse/run_stage4_parse.sh captures/raw/my_run
```

不传目录时会自动选择 `captures/raw/` 下最新的、同时包含 `ran_sctp_full.pcap` 和 `gtpu_full.pcap` 的抓包目录：

```bash
./scripts/parse/run_stage4_parse.sh
```

输出：

- `json/tshark_raw/<run>_*.tshark.json`：原始 tshark JSON，可再生成，默认不提交
- `json/normalized/<run>_control_plane_packets.json`：F1AP / NGAP / E1AP 归一化 JSON
- `json/normalized/<run>_gtpu_packets.json`：GTP-U 归一化 JSON
- `json/normalized/<run>_summary.json`：协议、procedure、TEID、flow 统计

### 5. 停止环境

```bash
./scripts/env/stop_env.sh
```

该脚本会收集容器 pcap/log 后停止 compose 环境。完整帧抓包优先使用 `scripts/capture/capture_traffic.sh`，因为 OrbStack 下 sidecar 抓 UDP 不可靠。

## 协议接口

| 接口 | 协议 | 协议栈 | 说明 |
|------|------|--------|------|
| F1-C | F1AP | F1AP/SCTP/IP | CU-CP ↔ DU 控制面 |
| F1-U | GTP-U | GTP-U/UDP/IP | CU-UP ↔ DU 用户面 |
| E1 | E1AP | E1AP/SCTP/IP | CU-CP ↔ CU-UP 控制面 |
| Xn | XnAP | XnAP/SCTP/IP | gNB ↔ gNB（当前环境未产生，需多 gNB/Xn 场景或样例 pcap） |
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
- tcpdump（抓包脚本会在 CU-CP/CU-UP 容器内按需安装）

## 当前进度

已完成：

- 5GC + srsRAN CU/DU split 环境
- srsUE over ZMQ 注册与 PDU Session
- 容器内 tcpdump 完整帧抓包
- F1AP / NGAP / E1AP / GTP-U 解析为结构化 JSON

待完成：

- XnAP 覆盖方案
- JSON/template → pcap 重编码
- 回放与验证
- 两条完整 UE flow 的最终自动化测试报告

## 实施进度

见 [docs/progress.md](docs/progress.md)。
