# 实施进度

## 阶段 0：仓库和文档结构 ✅

- [x] 创建 GitHub 仓库 `5G-O-RAN-F1AP-E1AP-GTPU-Protocol-Testing`
- [x] 建立目录结构（docker/, scripts/, captures/, json/, reports/, tests/）
- [x] 编写 CLAUDE.md、README.md、.gitignore
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

## 阶段 1.5：srsRAN ARM64 本地构建 🔄（进行中）

- [x] 调研确认 srsRAN 官方无 ARM64 预构建镜像
- [x] 调研确认 herlesupreeth/docker_srsran 只有 amd64（AVX 依赖，Rosetta 不支持）
- [x] 编写 Dockerfile.srsran 本地 ARM64 构建脚本
- [x] 克隆 srsRAN_Project 源码到 docker/srsran-src/
- [ ] **正在构建** srsRAN ARM64 Docker 镜像（srscucp/srscuup/srsdu）

**构建问题记录：**
- Docker build 中 git clone 归档仓库失败 → 改为先本地 clone 再 COPY 进容器
- 缺少 yaml-cpp 依赖导致 cmake 失败 → 补充 `libyaml-cpp-dev`

## 阶段 2：UE 注册与 PDU Session 跑通 ⬜

- [ ] 启动 CU-CP / CU-UP / DU 容器
- [ ] 确认 CU-CP 与 AMF 建立 NGAP 连接
- [ ] 确认 CU-CP 与 CU-UP 建立 E1AP 连接
- [ ] 确认 DU 与 CU-CP 建立 F1AP 连接
- [ ] 在 WebUI 添加 UE 订阅记录
- [ ] 部署 srsUE 并完成注册
- [ ] 完成 PDU Session 建立
- [ ] 收集各接口 pcap 和日志

## 阶段 3：接口抓包与协议识别 ⬜

## 阶段 4：pcap → JSON 解析与 IE 提取 ⬜

## 阶段 5：JSON/template → pcap 重编码与验证 ⬜

## 阶段 6：自动化测试生成与报告 ⬜

---

*最后更新：2026-05-18*
