# 实施进度

> 最后更新：2026-06-04

## 总览

| 阶段 | 状态 | 说明 |
|------|------|------|
| 0. 仓库和文档结构 | ✅ 完成 | GitHub 仓库、目录结构、README、协作文档 |
| 1. Docker Compose 环境部署 | ✅ 完成 | 5GC + RAN CU-DU Split + 网络拓扑 |
| 1.5. srsRAN ARM64 本地构建 | ✅ 完成 | Apple Silicon 原生运行，无 AVX 依赖 |
| 2. UE 注册与 PDU Session 跑通 | ✅ 完成 | srsUE + ZMQ，UE 拿到 IP |
| 3. 接口抓包与协议识别 | ✅ 完成 | 完整 SCTP/IP + GTP-U/UDP 帧，F1AP+NGAP+E1AP+GTP-U |
| 4. pcap → JSON 解析与 IE 提取 | ✅ 基线完成 | F1AP/NGAP/E1AP/GTP-U 自动解析 |
| 4.5. 可复现性与并行计划调整 | ✅ 完成 | 固定 Open5GS digest，重定义 XnAP，拆分 F1/N2/replay 三条线 |
| 5A. F1 Handover 实验线 | ⬜ 待开始 | 同 CU-CP 下双 cell / F1 handover 抓包和解析 |
| 5B. N2 Handover 实验线 | ⬜ 待开始 | 两套 gNB/CU-DU 接同一 Open5GS，尝试 AMF-mediated handover |
| 5C. 编码/回放/自动测例主线 | 🔄 进行中 | Replay schema、GTP-U encoder 和 tshark 自动验证 MVP 已完成 |
| 6. 前端展示与最终报告 | ⬜ 待开始 | dashboard + 最终演示脚本 |

## 阶段 0：仓库和文档结构 ✅

- [x] 创建 GitHub 仓库 `5G-O-RAN-F1AP-E1AP-GTPU-Protocol-Testing`
- [x] 建立目录结构（docker/, scripts/, captures/, json/, reports/, tests/）
- [x] 编写中文 README.md、.gitignore、协作文档；AI agent 本地指南只在本机保留
- [x] 创建环境管理脚本（start/stop/reset/check）

## 阶段 1：Docker Compose 环境部署 ✅

- [x] 5GC 核心网部署（Open5GS SA）
  - 基于 [herlesupreeth/docker_open5gs](https://github.com/herlesupreeth/docker_open5gs) 预构建镜像
  - 14 个 NF 容器：AMF、SMF、UPF、NRF、SCP、AUSF、UDM、UDR、PCF、BSF、NSSF、WebUI、MongoDB
  - AMF 和 UPF 同时挂载 5GC 内部网和 RAN 网
  - AMF NGAP 已改为 0.0.0.0 监听（支持 RAN 网络访问）
- [x] RAN CU-DU Split 配置
  - docker-compose.split.yml：CU-CP、CU-UP、DU 三个服务
  - 组件配置文件（cu_cp.yml、cu_up.yml、du_zmq.yml）已启用 pcap 输出
  - DU 使用 ZeroMQ RF 前端（无 SDR 硬件依赖）
- [x] 网络拓扑
  - 5gc_net (172.22.0.0/24)：5GC NF 内部通信
  - ran_net (10.53.1.0/24)：AMF(.2) UPF(.3) CU-CP(.4) CU-UP(.5) DU(.6)
  - f1u_net (172.18.10.0/24)：CU-UP(.2) ↔ DU(.3) 用户面

**遇到的问题及解决：**
- herlesupreeth 镜像只有 amd64 → 加 `platform: linux/amd64` + Rosetta 模拟运行
- UPF/SMF 启动崩溃 (exit 255) → 缺少 `UE_IPV4_IMS` 和 `PCSCF_IP` 环境变量，补上后解决
- AMF NGAP 只绑定内部 IP → 修改 amf.yaml 模板 ngap address 为 0.0.0.0
- `.env` 变量名不能以数字开头 → `5GC_NETWORK` 改为 `CORE_NETWORK`

## 阶段 1.5：srsRAN ARM64 本地构建 ✅

- [x] 调研确认 srsRAN 官方无 ARM64 预构建镜像
- [x] 调研确认 herlesupreeth/docker_srsran 只有 amd64（AVX 依赖，Rosetta 不支持）
- [x] 编写 Dockerfile.srsran 本地 ARM64 构建脚本
- [x] 克隆 srsRAN_Project 源码到 docker/srsran-src/
- [x] 成功构建 srsran/gnb:local-arm64 镜像（srscucp/srscuup/srsdu/gnb）

**构建问题记录：**
- Docker build 中 git clone 归档仓库失败 → 改为先本地 clone 再 COPY 进容器
- 缺少 yaml-cpp 依赖导致 cmake 失败 → 补充 `libyaml-cpp-dev`

## 阶段 2：UE 注册与 PDU Session 跑通 ✅

- [x] 启动 CU-CP / CU-UP / DU 容器（本地 ARM64 镜像）
- [x] 确认 CU-CP 与 AMF 建立 NGAP SCTP 连接（10.53.1.4 → 10.53.1.2:38412）
- [x] 确认 CU-CP 与 CU-UP 建立 E1AP SCTP 连接（10.53.1.4:38462 → 10.53.1.5）
- [x] 确认 DU 与 CU-CP 建立 F1AP SCTP 连接（10.53.1.4:38472 → 10.53.1.6）
- [x] 构建 srsUE Docker 镜像（srsRAN_4G + FFTW_ESTIMATE 修复）
- [x] 自动 provision UE 订阅到 MongoDB
- [x] srsUE 通过 ZMQ 空口完成注册
- [x] PDU Session 建立，UE 拿到 IP 10.45.0.9
- [x] 组件 pcap 输出已启用

**DU ZMQ 配置要点：**
- band 3 / 10MHz / common_scs=15 / srate=11.52e6
- coreset0_index=0 / time_alignment_calibration=0
- ZMQ 端口绑定实际 IP（非 localhost）

**新增脚本：**
- `scripts/env/run_srsue_zmq_smoke.sh`：一键 srsUE smoke test（构建/注册/验证）
- `scripts/env/check_core_ready.sh`：验证 5GC+RAN 所有链路就绪
- `scripts/env/provision_subscriber.sh`：自动注入 UE 订阅
- `docker/compose/.env.example`：完整环境变量模板

## 抓包与协议识别实操报告

### 背景

srsRAN 的 CU-CP/CU-UP/DU 组件内置了 pcap 输出功能，通过配置文件的 `pcap:` 段启用。这是最方便的抓包方式——不需要在宿主机装 tcpdump，不需要找 Docker bridge 接口，组件会自动把经过它的协议消息写成本地 pcap 文件。

### 抓包前的配置

各组件的配置文件（`docker/configs/*.yml`）中已经开启了 pcap：

```yaml
# cu_cp.yml
pcap:
  ngap_enable: true
  ngap_filename: /tmp/cu_cp_ngap.pcap
  f1ap_enable: true
  f1ap_filename: /tmp/cu_cp_f1ap.pcap
  e1ap_enable: true
  e1ap_filename: /tmp/cu_cp_e1ap.pcap
```

pcap 文件写在容器的 `/tmp/` 目录下，因为 compose 里挂了 volume（`cu_cp_pcap:/tmp`），即使容器销毁数据也不会丢。

### 怎么触发流量

需要一次完整的 UE 注册 + PDU Session 流程才能产生各接口的信令消息。用已有的脚本：

```bash
# 确保环境在跑
./scripts/env/check_core_ready.sh

# 跑 srsUE smoke test（会自动重建 DU、注册 UE、等 PDU Session 建立）
./scripts/env/run_srsue_zmq_smoke.sh run
```

`run_srsue_zmq_smoke.sh` 内部会：
1. 检查 5GC + RAN 所有容器和链路就绪
2. 自动注入 UE 订阅到 MongoDB（IMSI/Ki/OPc）
3. 强制重建 DU（`SRSUE_RECREATE_DU=1`），触发新的 F1Setup 握手
4. 启动 srsUE 容器，等待 `tun_srsue` 拿到 IPv4 地址

如果需要多次抓包，先 `down` 再 `run`：

```bash
./scripts/env/run_srsue_zmq_smoke.sh down   # 清理旧 UE 容器
./scripts/env/run_srsue_zmq_smoke.sh run     # 重新跑
```

### 怎么提取 pcap

pcap 在容器的 `/tmp/` 里，用 `docker cp` 拷出来：

```bash
RUN=captures/raw/run_002
mkdir -p $RUN/{cu_cp,cu_up,du}

docker cp srsran_cu_cp:/tmp/. $RUN/cu_cp/
docker cp srsran_cu_up:/tmp/. $RUN/cu_up/
docker cp srsran_du:/tmp/.    $RUN/du/

ls -lh $RUN/cu_cp/*.pcap
ls -lh $RUN/cu_up/*.pcap
ls -lh $RUN/du/*.pcap
```

注意：`docker cp` 会把 `/tmp/` 下所有东西都拷出来（包括日志、socket 文件等），只看 `.pcap` 就行。

### 怎么分析 pcap

用 tshark 直接看消息列表：

```bash
# NGAP 消息列表
tshark -r $RUN/cu_cp/cu_cp_ngap.pcap

# F1AP 消息列表
tshark -r $RUN/cu_cp/cu_cp_f1ap.pcap

# 查看某一条消息的完整字段（verbose 模式）
tshark -r $RUN/cu_cp/cu_cp_f1ap.pcap -V | head -80

# 只看某个 procedureCode 的消息
tshark -r $RUN/cu_cp/cu_cp_ngap.pcap -T fields -e ngap.procedureCode | sort | uniq -c | sort -rn
```

也可以直接用 Wireshark GUI 打开 pcap 文件看。

### 这次抓到的内容

**NGAP（CU-CP ↔ AMF）：87 帧，8 种消息**

| 消息 | Procedure Code | 帧数 | 说明 |
|------|---------------|------|------|
| NGSetup | 21 | 5 | CU-CP 启动时与 AMF 建立连接 |
| InitialUEMessage | 20 | 10 | UE 发起注册，每个 UE 流程一条 |
| DownlinkNASTransport | 29 (含上行) | 10+10 | Auth/Security Mode/NAS 信令 |
| InitialContextSetup | 4 | 10 | AMF 要求 CU-CP 建立 UE 上下文 |
| PDUSessionResourceSetup | 15 | 10 | 建立 PDU Session（分配 TEID） |
| PDUSessionResourceModify | 46 | 27 | QoS 修改（最频繁的消息） |
| UERadioCapabilityInfoIndication | 14 | 10 | UE 能力上报 |
| NGReset | 44 | 5 | DU 重建时触发的重置 |

**F1AP（CU-CP ↔ DU）：128 帧，7 种消息**

| 消息 | Procedure Code | 帧数 | 说明 |
|------|---------------|------|------|
| F1Setup | 1 | 12 | DU 启动时与 CU-CP 建立 F1 连接 |
| InitialULRRCMessageTransfer | 11 | 10 | UE 的 RRC 消息通过 DU 转给 CU-CP |
| ULRRCMessageTransfer | 12 | 35 | 上行 RRC/NAS 消息 |
| DLRRCMessageTransfer | 13 | 45 | 下行 RRC/NAS 消息（最多的消息） |
| UEContextSetup | 5 | 10 | CU-CP 要求 DU 建立 UE 上下文（含 SRB/DRB 配置） |
| UEContextModification | 7 | 10 | 修改 UE 上下文（触发 RRC Reconfiguration） |
| F1Removal | 26 | 6 | DU 重建时断开 F1 连接 |

### 踩过的坑

**坑 1：DU 被重建后 DU 侧 pcap 清零**

`run_srsue_zmq_smoke.sh` 会 `--force-recreate` DU 容器来确保干净的 F1Setup 握手。重建后 DU 的新 pcap 是空的（因为 pcap 文件是在 DU 启动瞬间创建的，而 F1Setup 已经在 smoke test 的 `wait_for_log` 期间完成了）。

实际影响：DU 侧的 pcap（`du_f1ap.pcap`、`du_f1u.pcap`）始终为 0B。但 CU-CP 侧的 pcap 完整记录了所有 F1AP 消息（因为 CU-CP 没有被重建），所以不影响分析。

**坑 2：E1AP pcap 为空**

CU-CP 和 CU-UP 的 `e1ap_*.pcap` 都是 0B。虽然 `ss -A sctp` 确认 E1AP SCTP 连接已建立（CU-CP:38462 ↔ CU-UP），但 srsRAN 没有往 pcap 文件里写数据。可能原因：
- srsRAN 的 E1AP pcap 功能在当前版本有 bug 或未实装
- E1AP 消息在 CU-CP/CU-UP 内部走的是内存通道而非 SCTP socket（尽管 SCTP 连接建立了）

解决方案：需要在 Docker 网络上用 tcpdump 直接抓 SCTP 流量（过滤 port 38462/38472），或者用 Wireshark 在宿主机抓 Docker bridge。

**坑 3：GTP-U pcap 为空**

CU-UP 的 `f1u_*.pcap` 和 `n3_*.pcap` 都是 0B。原因类似：srsRAN CU-UP 的用户面 pcap 功能可能未正确写入文件。GTP-U 是 UDP 流量（port 2152），需要在 f1u_net bridge 或 CU-UP 容器内用 tcpdump 抓取。

**坑 4：pcap 格式是 Wireshark Upper PDU（非原始 SCTP 帧）**

srsRAN 的内置 pcap 输出的是 `exported_pdu` 格式——只有协议层内容（如 F1AP ASN.1 编码），没有 SCTP/IP/Ethernet 头。这意味着：
- tshark 可以正常解析协议字段
- 但看不到实际的 SCTP 流和 IP 地址
- 如果需要完整的 SCTP/IP 层 pcap（用于协议栈分析或回放），必须用 tcpdump 在网络层抓取

**坑 5：pcap 文件太大不能推到 GitHub**

DU 的日志文件 `/tmp/du.log` 有 145MB，GitHub 拒绝推送。已在 `.gitignore` 中排除了 `captures/raw/` 下的所有 `.log` 和 `.pcap` 文件。pcap 数据只保存在本地。

### 尚未解决的问题

- ~~**E1AP 抓包**~~：✅ 已通过容器内 tcpdump 解决（见下方完整帧抓包）
- ~~**GTP-U 抓包**~~：✅ 已通过 CU-UP 容器内 tcpdump 解决
- ~~**原始 SCTP/IP 帧**~~：✅ 已通过容器内 tcpdump 获取完整帧

---

## 完整帧抓包实操（容器内 tcpdump 方式）

> 2026-05-21

阶段 3 完成报告：`reports/testcase_reports/stage3-capture-report.md`

### 背景

srsRAN 的内置 pcap 输出是 `exported_pdu` 格式（只有协议层内容，没有 SCTP/IP/Ethernet 头），不适合做协议栈分析和回放。需要抓取带完整网络头的原始帧。

### 方案

在 RAN 容器内直接安装 tcpdump，抓取经过容器网络接口的原始流量：

1. **CU-CP 容器**：抓 `any` 接口的 SCTP 流量 → 覆盖 NGAP（port 38412）、E1AP（port 38462）、F1AP（port 38472）
2. **CU-UP 容器**：抓 `any` 接口的 GTP-U 流量（UDP port 2152）

### 为什么不在 Docker 网络上抓

OrbStack 的 Docker 网络实现不允许 sidecar 容器看到其他容器间的流量。尝试过的方案：

- **Sidecar alpine+tcpdump 容器**：加入同一 Docker 网络，但抓到的 pcap 为空（24B）
- **宿主机 tcpdump**：OrbStack 的虚拟网络接口对宿主机不完全可见

最终选择在目标容器内直接安装 tcpdump——最简单、最可靠。

### 自动化操作

```bash
./scripts/capture/capture_traffic.sh run
```

这个脚本会自动：
1. 在 CU-CP/CU-UP 容器内安装 tcpdump（如果缺失）
2. 在 CU-CP 内抓 SCTP，输出 `ran_sctp_full.pcap`
3. 在 CU-UP 内抓 UDP/2152，输出 `gtpu_full.pcap`
4. 触发 `run_srsue_zmq_smoke.sh run`
5. 尝试从 UE 的 `tun_srsue` 生成 ping 流量
6. 停止 tcpdump 并把 pcap 拷到 `captures/raw/run_YYYYMMDD_HHMMSS/`

也可以分步执行：

```bash
./scripts/capture/capture_traffic.sh start captures/raw/my_run
./scripts/env/run_srsue_zmq_smoke.sh run
docker exec srsue_5g_zmq ping -I tun_srsue -c 3 -W 2 8.8.8.8 || true
./scripts/capture/capture_traffic.sh stop
```

### 抓到的内容

#### SCTP（ran_sctp_full.pcap）— 265 帧

| 协议 | 消息类型 | Procedure Code | 帧数 | 方向 |
|------|---------|---------------|------|------|
| **F1AP** | F1Setup | 1 | 2 | DU → CU-CP |
| | InitialULRRCMessageTransfer | 11 | 1 | DU → CU-CP |
| | ULRRCMessageTransfer | 12 | 7 | DU → CU-CP |
| | DLRRCMessageTransfer | 13 | 9 | CU-CP → DU |
| | UEContextSetup | 5 | 2 | CU-CP → DU |
| | UEContextModification | 7 | 2 | CU-CP → DU |
| | F1Removal | 26 | 2 | DU → CU-CP |
| **NGAP** | InitialUEMessage | 20 | 2 | CU-CP → AMF |
| | DownlinkNASTransport | 29 | 2 | AMF → CU-CP |
| | InitialContextSetup | 4 | 3 | AMF → CU-CP |
| | PDUSessionResourceSetup | 15 | 1 | AMF → CU-CP |
| | PDUSessionResourceModify | 46 | 4 | AMF → CU-CP |
| | UERadioCapabilityInfoIndication | 14 | 2 | CU-CP → AMF |
| | NGReset | 44 | 1 | CU-CP → AMF |
| **E1AP** | Reset | 8/9 | 2 | CU-CP ↔ CU-UP |
| | ResetAcknowledge | 8/9 | 2 | CU-UP ↔ CU-CP |
| | ErrorIndication | 0 | 2 | — |

**关键发现**：E1AP 消息现在可以抓到了！之前 srsRAN 内置 pcap 输出 E1AP 为空，但通过容器内 tcpdump 在 SCTP 层面抓取，E1AP 消息（Reset/ResetAcknowledge）完整可见。

**IP 地址可见**：
- F1AP：10.53.1.4 (CU-CP) ↔ 10.53.1.6 (DU)
- NGAP：10.53.1.4 (CU-CP) ↔ 10.53.1.2 (AMF)
- E1AP：10.53.1.4 (CU-CP) ↔ 10.53.1.5 (CU-UP)

#### GTP-U（gtpu_full.pcap）— 少量帧

| 帧 | 源 → 目的 | TEID | 内容 |
|----|----------|------|------|
| 1 | 172.18.10.3 → 172.18.10.2 | 9 | GTP-U T-PDU + NRUP DL Data Delivery Status |
| 2 | 172.18.10.3 → 172.18.10.2 | — | GTP-U T-PDU（ICMPv6 Router Solicitation） |
| 3+ | 10.53.1.5 → 10.53.1.3 | 动态 TEID | N3 GTP-U（常见为 IPv6 Router Solicitation 或 ping 触发包） |

完整的 IP/UDP/GTP 头部信息：
- 源：172.18.10.3 (DU F1-U)，目的：172.18.10.2 (CU-UP F1-U)
- UDP port 2152
- GTP-U TEID=9，含 NR RAN Container 扩展头（NRUP PDU Type 1 = DL Data Delivery Status）

### 注意事项

1. **OrbStack 下 sidecar 抓包不可靠**：加入同一 Docker 网络的 alpine/tcpdump sidecar 经常只能得到 24B 空 pcap。目标容器内 tcpdump 已验证可抓到 SCTP 和 UDP/2152。
2. **容器重建后 tcpdump 会丢失**：tcpdump 是临时安装在运行容器中的，如果容器被 `docker compose up --force-recreate` 重建，需要重新安装；`capture_traffic.sh` 已自动处理。
3. **GTP-U 包数较少**：注册/PDU Session 默认只会产生少量 GTP-U。可以通过 `docker exec srsue_5g_zmq ping -I tun_srsue -c 5 8.8.8.8` 尝试生成更多用户数据。
4. **pcap 格式是 Linux cooked-mode capture**：因为用了 `-i any`，链路层头是 SLL2 而非 Ethernet。对协议分析无影响，但回放时需要注意。
5. **SCTP HEARTBEAT 较多**：大部分 SCTP 帧是心跳包，过滤方式：`tshark -r file.pcap -Y 'sctp.data_str'` 只看含数据的帧。

### 验证方法

#### 验证 srsRAN 内置 pcap（exported_pdu 格式）

```bash
# 1. 确认环境正常
./scripts/env/check_core_ready.sh

# 2. 跑一次 UE 流程
./scripts/env/run_srsue_zmq_smoke.sh run

# 3. 提取 pcap
mkdir -p /tmp/pcap_check && docker cp srsran_cu_cp:/tmp/. /tmp/pcap_check/

# 4. 验证 F1AP / NGAP
tshark -r /tmp/pcap_check/cu_cp_f1ap.pcap 2>&1 | head -5
tshark -r /tmp/pcap_check/cu_cp_ngap.pcap 2>&1 | head -5
```

#### 验证完整帧 pcap（SCTP/IP + GTP-U/UDP 格式）

```bash
./scripts/capture/capture_traffic.sh run captures/raw/verify_full_pcap
RUN=captures/raw/verify_full_pcap

# 5. 验证 SCTP 完整帧（应看到 IP 地址 + 协议消息）
tshark -r $RUN/ran_sctp_full.pcap | grep -v HEARTBEAT | head -20
# 应看到：F1Setup, NGAP InitialUEMessage, E1AP Reset, UEContextSetup 等

# 6. 验证 GTP-U（应看到 UDP 2152 + GTP 头）
tshark -r $RUN/gtpu_full.pcap
# 应看到：GTP T-PDU，TEID=9

# 7. 按 protocolCode 统计
tshark -r $RUN/ran_sctp_full.pcap -Y f1ap -T fields -e f1ap.procedureCode | sort | uniq -c
tshark -r $RUN/ran_sctp_full.pcap -Y ngap -T fields -e ngap.procedureCode | sort | uniq -c
tshark -r $RUN/ran_sctp_full.pcap -Y e1ap -T fields -e e1ap.procedureCode | sort | uniq -c
```

## 阶段 4：pcap → JSON 解析与 IE 提取 ✅

阶段 4 完成报告：`reports/testcase_reports/stage4-parse-report.md`

### 自动化操作

```bash
./scripts/parse/run_stage4_parse.sh captures/raw/run_capture_ping_20260522_110820
```

不传目录时，脚本会自动选择 `captures/raw/` 下最新的、同时包含 `ran_sctp_full.pcap` 和 `gtpu_full.pcap` 的抓包目录：

```bash
./scripts/parse/run_stage4_parse.sh
```

这个脚本会自动：
1. 调用 `tshark -T json` 生成原始 JSON 到 `json/tshark_raw/`
2. 调用 `tshark -T fields` 抽取稳定字段
3. 输出控制面归一化 JSON：`json/normalized/<run>_control_plane_packets.json`
4. 输出用户面归一化 JSON：`json/normalized/<run>_gtpu_packets.json`
5. 输出汇总 JSON：`json/normalized/<run>_summary.json`

### 当前解析结果

基于 `captures/raw/run_capture_ping_20260522_110820/`：

| 输出 | 结果 |
|------|------|
| 控制面消息 | 42 条 |
| F1AP | 25 条 |
| NGAP | 13 条 |
| E1AP | 4 条 |
| GTP-U | 12 条 |
| GTP-U TEID | `0x00000003`、`0x00007cd5` |
| N3 inner ICMP | 6 条 |

控制面已提取：
- frame/time、protocol stack、info
- IP endpoints、SCTP ports
- procedureCode、procedure name
- 常见 UE / session / DRB / QoS IE 字段（存在时）

GTP-U 已提取：
- outer IP、UDP ports
- TEID、message type、extension headers
- NR-U PDU type / buffer status
- PDU session container type、QFI
- inner IPv4 / ICMP 字段

### 产物

```bash
json/tshark_raw/run_capture_ping_20260522_110820_ran_sctp_full.tshark.json
json/tshark_raw/run_capture_ping_20260522_110820_gtpu_full.tshark.json
json/normalized/run_capture_ping_20260522_110820_control_plane_packets.json
json/normalized/run_capture_ping_20260522_110820_gtpu_packets.json
json/normalized/run_capture_ping_20260522_110820_summary.json
```

说明：`json/tshark_raw/*.json` 是可再生成的大文件，按 `.gitignore` 不入库；`json/normalized/*.json` 是当前阶段的结构化交付物。

### 边界

XnAP 暂未覆盖：当前稳定 baseline 不产生 XnAP。阶段 4.5 后，XnAP 改为离线解析/构造展示，不要求当前运行环境产生 XnAP 或执行 XnAP replay。

## 阶段 4.5：可复现性与并行计划调整 ✅

阶段 4.5 完成报告：`reports/testcase_reports/stage4.5-plan-report.md`

### 已调整内容

- Open5GS 镜像从滚动 `master` 固定到 digest：

```text
ghcr.io/herlesupreeth/docker_open5gs@sha256:68247a557ae8e2a46beca39bceb06d63d0c3daebb9f6b95312be9384461154c1
```

容器内版本：

```text
Open5GS daemon v2.7.6-131-g782a97e
```

- XnAP 完整 inter-gNB handover 不再作为当前运行环境目标。
- XnAP 改为离线解析/构造展示：可使用样例 pcap 或构造消息，不要求 replay。
- Handover 实验不阻塞编码/回放/完整 UE flow 测试。
- 后续拆成三条并行任务线：F1 Handover、N2 Handover、Replay/Issue/Dashboard。

### Git 协作

建议从 `main` 切三条分支：

```text
feature/f1-handover
feature/n2-handover
feature/replay-issue-dashboard
```

分支只用于开发隔离。最终交付仍合并回 `main`，通过 compose overlay 或 scenario 脚本运行不同环境。

协作约束见：`docs/collaboration.md`

### Compose 规划

baseline 保持当前结构：

```bash
docker compose -f docker/compose/docker-compose.yml -f docker/compose/docker-compose.split.yml up -d
```

新增实验环境使用 overlay，不直接破坏 baseline：

```text
docker/compose/docker-compose.f1-ho.yml
docker/compose/docker-compose.n2-ho.yml
```

后续目标命令：

```bash
./scripts/env/start_env.sh baseline
./scripts/env/start_env.sh f1-ho
./scripts/env/start_env.sh n2-ho
```

## 阶段 5A：F1 Handover 实验线 ⬜

目标：

- 优先尝试同一个 CU-CP 下双 cell，减少 baseline 改动。
- 抓 F1/RRC/NGAP handover 相关信令。
- 若双 cell 不足以触发目标流程，再评估同 CU-CP 下多 DU。

交付：

- F1 handover 实验配置。
- pcap 和 normalized JSON。
- 支持边界报告。

## 阶段 5B：N2 Handover 实验线 ⬜

目标：

- 两套 gNB/CU-DU 接入同一个 Open5GS。
- 尝试通过 AMF/NGAP 观察 N2 handover 相关流程。
- 若完整流程不可行，记录支持边界和可观察到的 NGAP 消息。

交付：

- N2 handover overlay 配置。
- N2/NGAP 抓包和解析报告。
- 支持边界报告。

## 阶段 5C：编码/回放/自动测例主线 🔄

目标：

- 基于现有 baseline pcap 做 JSON/template → pcap。
- GTP-U 和至少 5 类控制面消息可被 tshark/Wireshark 识别。
- 两条完整 UE flow 自动化测试不依赖 handover。
- 调研 Open5GS v2.7.6 相关 issue，设计重放/变异测试做 bug reproduction 和安全分析。

XnAP 范围：

- 只做离线解析/构造。
- 不要求当前环境产生 XnAP。
- 不要求 XnAP replay。

当前进展：

- [x] 定义 replay testcase v1 schema 和目录结构。
- [x] 实现零第三方 Python 依赖的 GTP-U pcap 编码器。
- [x] 实现一键 tshark 验证 runner 和结构化结果 JSON。
- [x] 添加 N3 上行 ICMP Echo Request、下行 Echo Reply 两个 testcase。
- [x] 验证生成 pcap 可以进入现有 Stage 4 normalizer。
- [ ] 扩展控制面消息构造/编码。
- [ ] 增加 live replay、变异测试和 Open5GS issue reproduction。
- [ ] 将完整 UE flow 封装为自动 testcase。

阶段 5C.1/MVP 报告：`reports/testcase_reports/stage5c1-replay-mvp-report.md`

## 阶段 6：前端展示与最终报告 ⬜

目标：

- 前端 dashboard 展示项目能力。
- 左侧展示信令 timeline、解析结果和 normalized JSON。
- 右侧展示实验环境实时日志、testcase 输出和 issue reproduction 结果。
- 输出最终报告和演示脚本。

---

## 当前运行环境快照（2026-05-21）

### 容器状态

```
5GC (12 containers):
  mongo / nrf / scp / ausf / udr / udm / pcf / bsf / nssf / smf / amf / upf / webui

RAN (3 containers):
  srsran_cu_cp (healthy) / srsran_cu_up / srsran_du

UE (1 container):
  srsue_5g_zmq (IP: 10.45.0.9)
```

### SCTP 连接

```
CU-CP (10.53.1.4) → AMF  (10.53.1.2:38412)  NGAP
CU-CP (10.53.1.4:38462) ← CU-UP (10.53.1.5)  E1AP
CU-CP (10.53.1.4:38472) ← DU    (10.53.1.6)  F1AP
```

### 网络拓扑

```
5gc_net  172.22.0.0/24   5GC NF 内部 SBI 通信
ran_net  10.53.1.0/24    AMF(.2) UPF(.3) CU-CP(.4) CU-UP(.5) DU(.6) UE(.7)
f1u_net  172.18.10.0/24  CU-UP(.2) ↔ DU(.3) F1-U 用户面
```

### Docker 镜像

```
ghcr.io/herlesupreeth/docker_open5gs@sha256:68247a557ae8e2a46beca39bceb06d63d0c3daebb9f6b95312be9384461154c1  (amd64, Rosetta; Open5GS v2.7.6-131-g782a97e)  5GC NF
mongo:6.0                                     (multi-arch)      MongoDB
srsran/gnb:local-arm64                        (arm64 native)    CU-CP/CU-UP/DU
srsue-5g-zmq:local                            (arm64 native)    srsUE
```
