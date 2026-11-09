# P7 / 388.13 一小时隔离共存验证

**实验预发布 / NOT_FLASH_READY / 未实机验收；本次没有刷机。**

本报告补充 P7 首次发布时的 321.6 秒检查。P6 的一小时数据属于 388.12_2，未复用为本轮结果。P7 原发布固件、源码包及九个原附件保持原字节；原始 `merlin38813_local_gate.json` 与 `P7-VALIDATION.md` 保留封存时状态。本次完整一小时结果单独记录在 [小时门禁](merlin38813_hour_gate.json)、[原始数据](merlin38813_native_coexist_60m_tests.json) 和 [运行日志](merlin38813_native_coexist_60m.log)。

## 本轮结果与绑定

- 固件：`output/RT-AX86U_3004_388.13_0_localmod_native_P7_3c7521ae_NOT_FLASH_READY.w`。
- SHA256：`9f4b392a9a2575d7fbbf32e1efb747386199e7fb1babe502590c8cb6ef31ea8b`。
- 固件来源提交：`147032c384732124f3dd2f2f47bdea3a30edf5a8`；上游：`3004.388.13` / `d1a59dcffbe0402c7ac8ac3090cb7c928510fbcd`。
- 测量区间（客体 UTC）：2026-11-09T13:23:11Z → 2026-11-09T14:23:15Z。
- 实际连续测量 **3603.9 秒**；宿主执行耗时 3737.9 秒（含系统与插件准备）。
- **1024 次正常查询、35 次计划异常/重启、127 次资源采样；计划外失败为 0。**
- 16 类事件均至少执行两次；软件中心登记、DDNS-Go 配置、Fancyss 配置与节点记录、HTTPS 证书和 UU 合成测试数据均保留。
- 未复现需要修改生产固件的问题，保留已发布 P7 固件字节；本次新增证据复核和安全清理入口。

软件中心 1.9.60、DDNS-Go、Fancyss 3.5.29 HND v8 Full 和原生 UU 适配同时运行。六个原生组件包括 OpenVPN、dnsmasq、curl、wget、Dropbear、miniupnpd。实际服务检查次数如下；这些检查与正常查询计数含不同层级的操作，不能相加视作用户请求总数。

| 检查 | 次数 |
| --- | ---: |
| `core_page_queries` | 94 |
| `curl_wget_https_pairs` | 95 |
| `dns_queries` | 1934 |
| `proxy_queries` | 972 |
| `ssh_queries` | 95 |
| `tun_traffic` | 94 |
| `upnp_cycles` | 99 |

## 重启与故障恢复

| 计划事件 | 次数 |
| --- | ---: |
| `abort` | 3 |
| `backend` | 3 |
| `center` | 2 |
| `ddns` | 2 |
| `dns` | 2 |
| `fancy-client` | 2 |
| `nat` | 2 |
| `partial` | 3 |
| `proxy-upstream` | 2 |
| `signals` | 2 |
| `ssh` | 2 |
| `tls` | 2 |
| `upnp` | 2 |
| `uu` | 2 |
| `vpn-client` | 2 |
| `vpn-upstream` | 2 |

客户端主动中断、部分响应、后端退出、软件中心/DDNS-Go/UU/HTTPS 重启、信号干扰、六组件相关服务重启及代理/VPN 上游中断均由测试主动触发。计划维护窗口内的不可用单列，不能混入正常查询的“零计划外失败”。UU 受控启动通过原生 NTP 回调、下载、校验和启动路径。下表统计维护期并发的 DDNS-Go 状态查询；不表示被停止的代理/VPN 业务在停机期间仍可用。测试另确认上游停止时业务失败、恢复后流量成功。

| 维护窗口 | 查询数 | 维护期不可用数 |
| --- | ---: | ---: |
| center_restart | 21 | 20 |
| ddns_restart | 3 | 0 |
| uu_restart | 15 | 0 |
| dns_restart | 1 | 0 |
| ssh_restart | 11 | 0 |
| upnp_restart | 1 | 0 |
| vpn-client_restart | 4 | 0 |
| fancy-client_restart | 11 | 0 |
| nat_restart | 1 | 0 |
| proxy-upstream_restart | 16 | 0 |
| vpn-upstream_restart | 20 | 0 |
| center_restart | 22 | 21 |
| ddns_restart | 3 | 0 |
| uu_restart | 15 | 0 |
| dns_restart | 1 | 0 |
| ssh_restart | 11 | 0 |
| upnp_restart | 1 | 0 |
| vpn-client_restart | 3 | 0 |
| fancy-client_restart | 11 | 0 |
| nat_restart | 1 | 0 |
| proxy-upstream_restart | 15 | 0 |
| vpn-upstream_restart | 25 | 0 |

## 内存与文件描述符

按连续存活的进程生命周期分组，避免合并重启前后进程及循环复用的 PID。下表列 DDNS-Go 两个最长观测周期，以及其余主要角色的最长周期；RSS 单位 KiB，增量使用末三次与首三次采样中位数之差。完整进程列表保留在小时门禁中。

| 角色 / PID | 同进程观测秒数 | RSS 范围 KiB | 首尾中位数差 KiB | FD 范围 |
| --- | ---: | ---: | ---: | ---: |
| ddnsgo / 499 | 1489.9 | 13188–18032 | +4824 | 7–7 |
| ddnsgo / 18506 | 1449.8 | 13204–18032 | +4816 | 7–7 |
| httpd / 24331 | 1570.5 | 9880–10100 | +200 | 5–5 |
| xray-client / 9183 | 1562.4 | 33916–37728 | +2260 | 6–6 |
| openvpn-client / 6196 | 1575.5 | 7868–7884 | +16 | 6–6 |
| uu / 21929 | 1564.4 | 1636–1636 | +0 | 4–5 |

DDNS-Go 两个最长周期的 RSS 高点均为 18,032 KiB，首尾中位数增加约 4.7 MiB；同一进程 PID 18506 内曾从 17,744 KiB 回落到 14,744 KiB，不能把增长理解成全程单调累积。RSS 增长仍作为观测项保留。本轮没有采集 Go 存活堆、GC 及映射分解，不能仅凭 RSS 断言存在真实泄漏，也不能把增长全部归因于 QEMU。客体 `/proc` RSS 不含外层 QEMU-system 宿主内存；可执行文件为 `qemu-arm` 的服务包含用户态仿真器开销。有限一小时及期间多次重启，不能证明跨天稳定或无泄漏。

## 验证边界

- 实际服务和流量运行于 Cortex-A53 / Linux 6.12 隔离系统，宿主输入只读、无外网网卡；不是目标 Broadcom 4.1 内核/PID1、硬件驱动或路由器实机启动。
- UU 使用自有监控工作进程和合成数据，未验证真实 UU 账号、云端登录、游戏加速或业务重连。
- Fancyss 使用实际安装包和 Xray SOCKS/VLESS 流量，VPN 使用实际 TUN 与自有证书/端点；未验证真实订阅、运营商线路、透明/全局代理、Wi-Fi、硬件 NAT 或 AiMesh。
- 未访问或刷写路由器；当前 Alpha 3 的配置/JFFS/插件数据备份仍未执行。

## 复核与后续测试范围

同一固件 SHA256、源文件、插件输入和测试条件已有完整报告时，先复核证据，**不因提交、推送、上传或文档修改重复执行一小时**：

```sh
analysis/.venv/bin/python analysis/merlin_vpn_38813/check_hour_gate.py --verify-only
```

该命令只核验现存结果、固件、源文件、日志及生成输入归档，不启动 VM，不改写历史报告。缺失或变更会拒绝复用。常规文档/发布更改做静态与摘要校验；单个插件或局部逻辑更改做相应安装/升级/卸载、共存及恢复回归；底包、TLS/认证、服务框架、VPN/网络栈或与长期稳定性有关的更改，再按影响范围追加长测。该分级不会把不同固件的旧动态结果直接算作新版本结果。

重跑完整一小时的入口（仅在确有必要时）：

```sh
analysis/.venv/bin/python analysis/merlin_vpn_38813/check_native_soak.py
analysis/.venv/bin/python analysis/merlin_vpn_38813/check_hour_gate.py
```

## 临时缓存清理

成功的隔离 VM 工作区已由原有生命周期管理删除。本次另外删除 26,780,960 字节的已核验临时目录，并压缩项目自有稀疏磁盘镜像，实际回收 418,381,824 字节（399 MiB），重新挂载后复核通过。保留固件、依赖、原始数据、日志及 47,635 字节的[生成输入源码审计包](merlin38813_hour_generated_inputs.tar.gz)。逐文件摘要匹配后才清理；详见[清理回执](merlin38813_hour_cleanup.json)。清理后重新执行 `--verify-only`。

```sh
analysis/.venv/bin/python analysis/merlin_vpn_38813/cleanup_hour_cache.py
analysis/.venv/bin/python analysis/merlin_vpn_38813/cleanup_hour_cache.py --apply
```

GitHub 历史 Release 和原先发布的九个 P7 附件继续保留。后续发布回执单独记录，实验预发布与未实机验收标识不变。
