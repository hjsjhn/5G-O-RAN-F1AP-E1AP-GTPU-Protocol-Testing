# 实施进度

> 最后更新：2026-05-21

## 总览

| 阶段 | 状态 | 说明 |
|------|------|------|
| 0. 仓库和文档结构 | ✅ 完成 | GitHub 仓库、目录结构、CLAUDE.md |
| 1. Docker Compose 环境部署 | ✅ 完成 | 5GC + RAN CU-DU Split + 网络拓扑 |
| 1.5. srsRAN ARM64 本地构建 | ✅ 完成 | Apple Silicon 原生运行，无 AVX 依赖 |
| 2. UE 注册与 PDU Session 跑通 | ✅ 完成 | srsUE + ZMQ，UE 拿到 IP |
| 3. 接口抓包与协议识别 | ⬜ 待开始 | |
| 4. pcap → JSON 解析与 IE 提取 | ⬜ 待开始 | |
| 5. JSON/template → pcap 重编码与验证 | ⬜ 待开始 | |
| 6. 自动化测试生成与报告 | ⬜ 待开始 | |

## 阶段 0：仓库和文档结构 ✅

- [x] 创建 GitHub 仓库 `5G-O-RAN-F1AP-E1AP-GTPU-Protocol-Testing`
- [x] 建立目录结构（docker/, scripts/, captures/, json/, reports/, tests/）
- [x] 编写 CLAUDE.md、中文 README.md、.gitignore
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

- **E1AP 抓包**：需要在容器内装 tcpdump 或在 Docker 网络层面抓 SCTP port 38462
- **GTP-U 抓包**：需要在 f1u_net bridge 上抓 UDP port 2152
- **原始 SCTP/IP 帧**：srsRAN 内置 pcap 没有 IP 头，如果要做完整的协议栈分析或回放测试，需要额外抓取

### 验证方法

```bash
# 1. 确认环境正常
./scripts/env/check_core_ready.sh
# 期望输出: OK: 5G Core is up; SMF/UPF PFCP is associated; NGAP/E1AP/F1AP SCTP links are established.

# 2. 跑一次 UE 流程
./scripts/env/run_srsue_zmq_smoke.sh run
# 期望输出: OK: srsUE reached the DU over ZMQ and produced attach/session progress logs.

# 3. 提取 pcap
mkdir -p /tmp/pcap_check && docker cp srsran_cu_cp:/tmp/. /tmp/pcap_check/

# 4. 验证 F1AP
tshark -r /tmp/pcap_check/cu_cp_f1ap.pcap 2>&1 | head -5
# 应该看到 F1SetupRequest, F1SetupResponse, InitialULRRCMessageTransfer 等

# 5. 验证 NGAP
tshark -r /tmp/pcap_check/cu_cp_ngap.pcap 2>&1 | head -5
# 应该看到 NGSetupRequest, NGSetupResponse, InitialUEMessage 等

# 6. 确认无 Malformed Packet
tshark -r /tmp/pcap_check/cu_cp_f1ap.pcap -T fields -e f1ap.procedureCode 2>&1 | grep -c .
# 应该返回帧数（如 128），且 tshark 没有 malformed 警告
```

## 阶段 4：pcap → JSON 解析与 IE 提取 ⬜

待开始。

## 阶段 5：JSON/template → pcap 重编码与验证 ⬜

待开始。

## 阶段 6：自动化测试生成与报告 ⬜

待开始。

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
ghcr.io/herlesupreeth/docker_open5gs:master  (amd64, Rosetta)  5GC NF
mongo:6.0                                     (multi-arch)      MongoDB
srsran/gnb:local-arm64                        (arm64 native)    CU-CP/CU-UP/DU
srsue-5g-zmq:local                            (arm64 native)    srsUE
```
