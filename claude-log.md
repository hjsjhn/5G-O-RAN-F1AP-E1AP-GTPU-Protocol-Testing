⏺ DU 报错了——ZMQ 配置有问题。CU-UP 看起来正常（只有权限警告）。修 DU 的 ZMQ 配置。

⏺ Bash(docker logs srsran_du 2>&1)
  ⎿  --== srsRAN DU (commit 4bf1543) ==--

     Lower PHY in executor sequential baseband mode.
     … +3 lines (ctrl+o to expand)

  Read 1 file (ctrl+o to expand)

⏺ 问题可能是 otw_format: sc12 和 ZMQ 不兼容。ZMQ 模式下 srsRAN 只支持默认 OTW 格式。另外 ZMQ 的端口配置也需要配对（TX/RX 各一对）。

⏺ Write(~/code/5G O-RAN Test/docker/configs/du_zmq.yml)
  ⎿  Removed 1 line
      12    device_driver: zmq
      13    device_args: tx_port=tcp://*:2000,rx_port=tcp://localhost:2001
      14    srate: 23.04
      15 -  otw_format: sc12
      15    tx_gain: 80
      16    rx_gain: 40
      17

⏺ Bash(cd "/Users/hjsjhn/code/5G O-RAN Test/docker/compose" && docker-compose -f docker-compose.yml -f docker-compose.split.yml up -d
      du 2>&1)
  ⎿  time="2026-05-18T20:14:58+08:00" level=warning msg="The \"p\" variable is not set. Defaulting to a blank string."
      Container nrf  Running
      Container mongo  Running
     … +12 lines (ctrl+o to expand)

⏺ Bash(sleep 5 && docker logs srsran_du 2>&1)
  ⎿  --== srsRAN DU (commit 4bf1543) ==--

     Lower PHY in executor sequential baseband mode.
     … +3 lines (ctrl+o to expand)

❯ ZMQ是啥项目？可以解释一下吗？以及你把架构图修好了吗

⏺ 还是报错。错误信息说 ZMQ 只支持默认 OTW 格式，但我已经去掉了 otw_format。问题可能在别处。让我看看 srsRAN 官方的 ZMQ DU 配置。

  Read 1 file, listed 1 directory (ctrl+o to expand)

⏺ 找到关键差异了。官方 ZMQ 配置：
  1. device_args 要带 base_srate=23.04e6
  2. ZMQ 端口要指向实际 IP（不是 localhost）
  3. 这是单体 gNB 配置，DU split 配置可能不同

  但 DU 报 "Invalid radio configuration" 而不是 ZMQ 连接错误，说明是配置解析阶段就失败了。可能是 srsRAN 版本差异——我们编译的版本和
  herlesupreeth 镜像版本不同。让我先回答你的问题，同时继续排查。

  ---
  关于 ZMQ： ZeroMQ 是一个高性能异步消息库，在 srsRAN 里用它来模拟射频前端。正常情况下 DU 需要通过 USRP 等 SDR 硬件收发射频信号，ZMQ
  模式用 TCP socket 传递 IQ 采样数据来替代，这样不需要真实硬件就能跑端到端测试。

  架构图我还没修好，现在修：

⏺ Update(~/code/5G O-RAN Test/README.md)
  ⎿  Added 13 lines, removed 10 lines
      16  ## 技术架构
      17
      18  ```
      19 -5GC (Open5GS)              RAN (srsRAN CU-DU Split)             UE (srsUE)
      19 +UE (srsUE)            RAN (srsRAN CU-DU Split)                5GC (Open5GS)
      20
      21 -+----------+    NGAP    +---------+   E1AP   +---------+
      22 -| AMF      |<---------->| CU-CP   |<------->| CU-UP   |<-- N3 --> UPF
      23 -| SMF/UPF  |            | (F1AP)  |         | (GTP-U) |
      24 -| UDM/UDR  |            +----+----+         +----+----+
      25 -| AUSF/PCF |                 | F1AP              | F1-U
      26 -| NRF/WebUI|            +----+----+              |
      27 -| MongoDB  |            |   DU    |<-------------+
      28 -+----------+            | (ZMQ)   |
      29 -                        +---------+     srsUE <--> DU (ZMQ空口)
      21 +                    +---------+   E1AP   +---------+        +---------+
      22 +              F1AP  |  CU-CP  |<------->|  CU-UP  |  N3    |  AMF    |
      23 +srsUE <--ZMQ--> DU  |  (NGAP) |         | (GTP-U) |<------>|  SMF    |
      24 +                    +---------+         +---------+        |  UPF    |
      25 +                       |                 |    |             |  UDM    |
      26 +                       | F1-C            | F1-U  N3        |  UDR    |
      27 +                       |                 |    |             |  AUSF   |
      28 +                    +--+-----------------+--+--+            |  NRF    |
      29 +                    |         DU (ZMQ RF)     |             |  PCF    |
      30 +                    +-------------------------+             |  WebUI  |
      31 +                                                            | MongoDB |
      32 +                                                            +---------+
      33  ```
      34
      35  所有组件基于 Docker Compose 部署，DU 使用 ZeroMQ 模拟空口（无需 SDR 硬件）。

⏺ 现在继续排查 DU 错误。srsRAN 编译版本是 4bf1543，看看 herlesupreeth 镜像里的版本。

⏺ Bash(docker run --rm ghcr.io/herlesupreeth/docker_srsran:master srsdu --version 2>&1 | head -3)
  ⎿  WARNING: The requested image's platform (linux/amd64) does not match the detected host platform (linux/arm64/v8) and no speci
     fic platform was requested

     --== srsRAN DU (commit 11c9bbabb6) ==--

⏺ herlesupreeth 是 11c9bbabb6，我们编译的是 4bf1543（更新）。看看官方 DU ZMQ 配置需要什么。

  Searched for 2 patterns (ctrl+o to expand)

⏺ 源码仓库里没有 ZMQ 的 DU 配置。让我看看这个版本 DU 需要什么 RU 配置。

  Searched for 1 pattern (ctrl+o to expand)
      16 +  rx_gain: 75
      17
      18  cell_cfg:
      19    dl_arfcn: 650000

⏺ Bash(cd "/Users/hjsjhn/code/5G O-RAN Test/docker/compose" && docker-compose -f docker-compose.yml -f docker-compose.split.yml up -d
      du 2>&1 && sleep 5 && docker logs…)
  ⎿  time="2026-05-18T20:19:48+08:00" level=warning msg="The \"p\" variable is not set. Defaulting to a blank string."
      Container mongo  Running
      Container nrf  Running
     … +18 lines (ctrl+o to expand)

⏺ 还是一样的错误。"Invalid radio configuration" 可能跟 cell_cfg 有关，不只是 ZMQ 部分。让我试一下最简配置——去掉 band 78 相关参数，用
  band 3（herlesupreeth 的 ZMQ 配置用的就是 band 3）。

