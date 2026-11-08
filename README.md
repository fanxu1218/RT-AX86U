# RT-AX86U 官方底包官改实验

基于 **ASUS 3.0.0.4.388_24437**，集成 **KoolCenter 软件中心 1.9.60**，保留官方 **网易 UU**。当前工作候选为 **localmod2-r9-r2**；原 r9-r1、r9、r8 及历史镜像、标签和发布附件保留。

**r9-r2 已通过完整本地门禁和最终候选握手对照，独立小时共存长测仍在运行；GitHub 推送和可选发布由用户操作，本轮未刷机或推送。** 交付回执暂记录上一轮 r9-r1，待本轮长测完成后更新：[local_delivery.json](output/local_delivery.json)，操作见 [手动推送与发布步骤](output/手动推送与发布步骤.md)。`release_delivery.json` 当前仍是历史 r8 发布回执，不能当作当前候选已发布证明。

> **实验候选版，尚未实机验收，暂不建议直接刷入日常主路由。**
> 源码适配、模型/仿真测试和镜像回读通过；刷入启动、原厂登录/TLS、无线/NAT、具体第三方插件及 UU 实际加速仍待实机验证。

## 本轮变化

r9-r2 修复原厂 HTTPS 握手被信号中断后直接放弃连接的问题：仅对 EINTR/WANT_READ 在原接收超时预算内继续同一次握手，不重放请求。最终候选通过 14 个握手/超时用例、六轮软件中心重启和 110 次正常查询；完整门禁重新绑定新镜像。小时共存长测仍在执行，发现过程、失败对照及边界见 [r9-r2 长时间共存验证](output/r9-r2长时间共存验证.md)。原 r9-r1 和历史镜像、交付包保留。

r9-r1 将软件中心升级到 1.9.60，并移植 Merlin 3004.388.12_2 的 OpenVPN 2.7.6、dnsmasq 2.93、curl 8.17.0、wget 1.25.0、Dropbear 2026.94 和 miniupnpd 2.3.11。六个原入口默认使用新版和私有依赖，保留原厂程序、全局认证/TLS 库；为原厂旧 VPN 配置和 UPnP 启动/NAT 重载增加兼容适配。范围及限制见 [软件中心升级](output/软件中心1.9.60升级说明.md) 和 [梅林组件移植](output/梅林组件移植说明.md)。本轮镜像和完整本地门禁均已通过；后文标注为历史的 r9/r7 结果属于前序版本。

r9 增加 Fancyss 3.5.29 HND v8 Full 兼容包、原厂认证安装入口及 FRPC/PushPlus 真实版本共存检查。使用固定来源、哈希校验和同一插件事务路径，保留 UU 数据；原厂底包保持 24437。已从官方底包重新组装并回读，新镜像的本地证据绑定同一 SHA256；实机仍未验收。具体状态见 [第二轮进度](output/第二轮优化进度.md) 和 [Fancyss 集成说明](output/Fancyss集成说明.md)。

r9 同时增加最多 32 条跨重启的脱敏操作/恢复记录、全部 VM 的独立输入与状态副本、有界并行/取消隔离，以及官方底包差异和 ABI 检查入口。详细验证见 [持久化记录](output/持久化操作记录说明.md)、[隔离与底包升级](output/隔离分片与底包升级说明.md) 和 [构建模型隔离](output/构建模型隔离说明.md)。

r8 集成六项后续完善：归档边界与脚本超时、事件/日志容量、原厂 TLS 会话缓存上限、UU 网络故障对照、经原厂认证的状态/恢复页及脱敏导出、统一构建与发布校验。新增分段 NVRAM 输出夹具复现并修复开关读取竞态；修复原厂 TLS 输入被信号误判为 EOF/400，保留原 5 秒接收预算，并验证 POST 仅执行一次。详细证据与验证边界见 [官改加固与优化说明](output/官改加固与优化说明.md)、[进度](output/后续完善进度.md) 和 [构建发布说明](output/构建与发布校验.md)。

下列历史改动及内存长测主要来自 r7 及前序版本，不能把旧报告直接视为 r9 长时间运行证明；当前候选以镜像回读和绑定哈希的报告为准。


- 自然复现并修复 DDNS-Go 只读查询收到 HTTP 200 后正文断连：接收循环不再把 `EINTR` 当成连接结束，继续读取同一后端连接，不重新提交请求。
- 保留原厂 TLS、登录、UU 和回调程序；单次接收的 120 秒空闲预算使用单调时钟，连续信号不重置预算。新增 UU 查询期停止/运行两组验证，以及响应头前后中断、真实定时信号和超时边界检查。
- 修复检查点损坏后仍被恢复、缺失封存标记或无效提交标记导致检查点被误清理的问题。新检查点使用 SHA256 清单，恢复前核对文件、链接、权限、归属和完整数据库结构。
- 恢复前预留数据库及元数据空间；运行中写满磁盘时保留可用副本，停止软件中心和本次新建的重放数据库，不清除 UU 或历史记录来腾空间。
- 原数据库重放提交后先关闭、重新打开并核对完整键值集合，再声明恢复成功；失败和同次启动重试都保持写入门禁。
- 未封存的 r5 旧检查点保留并要求人工核查，避免给未知字节补算校验后自动采用。已损坏的内容仍需要可信备份。
- 新增持久化安装检查点：安装、更新中断后阻止软件中心继续写入，在下次启动时恢复原配置；中断现场单独保留。
- 在线与离线安装共用检查点和操作锁；离线安装不再批量清除 UU 临时下载包。准备失败或备份空间不足时不执行安装脚本。
- 数据库使用逐条长度记录恢复，保留换行、引号等配置内容；提交完成后先持久化撤下事务目录，再清理副本。
- 新增独立虚拟磁盘的异常中断检查，覆盖安装进程被杀、恢复再次中断、提交前后重启、真实 DDNS-Go 更新及配置/UU 数据保留；不代表实机断电或真实 UU 加速已验收。
- 在完整原厂根目录中复现并修复 PATH 选错 `sh`、原厂 curl 拒绝数字地址回调、缺少 `tee`/`xargs`，以及已登记插件的空运行目录阻止更新四类问题。
- 新增 32 项阿里 DDNS、DDNSTO、DDNS-Go 的真实旧版/当前版安装、升级、卸载检查；DDNS-Go 执行真实 ARM 程序、本地网页及监督/事件流程。
- 真实插件脚本只在无外网网卡的临时虚拟机内执行，宿主目录只读，插件状态写入内存 JFFS；UU 继续使用原厂启动代码和受控工作进程。
- 修复在线安装清理范围过大：保留 UU 缓存和无关临时目录，仅清理本次拥有的下载与新建插件目录。
- 失败更新保留旧卸载器；自定义卸载失败保留登记/配置，默认卸载使用模块边界以保留相似名称插件。
- 在线安装、更新和卸载使用互斥锁并传递最终结果；同版/降级跳过、低空间失败与核心覆盖限制均有回归。
- 软件中心停止时确认监督进程和后台退出，再执行数据库提交屏障，处理快速重启/停用时的后台残留。
- 在线管理回归增至 28 项，覆盖原厂 HTTPS、实际 wget、受控仓库、目录保留及自有插件/UU 工作进程；回归 17 项证书与共存检查。
- 修复原厂程序拒绝 `/tmp` 执行路径的问题；HTTPd 原文件在只读 `/usr/libexec/localmod/httpd` 直接运行。
- 修复适配库初始化前的 stdio 调用崩溃、HTTPS 的 `asus_s_token` 会话兼容和 POST 请求体被页面输入处理预读的问题。
- 新增运行原厂 HTTPd/libpasswd/mssl/OpenSSL 的 HTTP/TLS 登录、会话及读写回调检查；运行原厂 rc 的 NTP→UU 受控启动流程。
- 修复 Alpha 3 迁移时旧 `.asusrouter` 链接漏归档；备份冲突会在移动旧核心前拒绝。
- 修复 `插件名_uninstall.sh` 文件判断错误，避免未执行自带卸载脚本却显示卸载成功。
- 接入启动、服务启停及事件前后回调、WAN、NAT/防火墙、存储挂载/卸载事件，并支持 DNS 配置扩展。
- 保留用户钩子，避免重复启动；处理 WAN fork 重放、卸载重试、带空格路径、脚本超时及 HALT 停机。
- 补充软件中心服务入口、受管理核心迁移和安装回调；修复离线安装失败状态及临时目录冲突，阻止覆盖核心；停止数据库前提交待写数据，避免快速重启丢配置。
- 规则重载与 API 隔离在同一次 filter COMMIT 中完成，并覆盖原厂非路由清空路径。
- 原厂 rc、HTTPd、xtables-multi、启动区、内核模块和 UU 原文件保留，新增启动器负责适配。

## 下载与说明

- r9-r2 本地候选：见 [本地交付状态](output/local_delivery.json)；[计划预发布地址](https://github.com/fanxu1218/RT-AX86U/releases/tag/localmod2-r9-r2-experimental) 仅在后续手动发布成功后可用。
- [localmod2-r8 历史实验预发布与固件附件](https://github.com/fanxu1218/RT-AX86U/releases/tag/localmod2-r8-experimental)
- [localmod2-r7 历史实验预发布与固件附件](https://github.com/fanxu1218/RT-AX86U/releases/tag/localmod2-r7-experimental)
- [完整适配范围与验证边界](output/官改候选版说明.md)
- [Alpha 3 升级、实机验收与回退步骤](output/Alpha3升级localmod2与实机验收.md) · [验收记录模板](output/localmod2实机验收记录模板.md)
- [事件测试](output/hooks_tests.json) · [兼容测试](output/compatibility_tests.json) · [原厂接口清单](output/vendor_contracts.json) · [UU 静态及模型检查](output/uu_compatibility_tests.json) · [原厂登录/TLS/UU 本地运行检查](output/native_runtime_tests.json)
- [30 分钟持续运行说明](output/持续运行验证说明.md) · [实测报告](output/soak-30m_tests.json)
- [DDNS-Go RSS 分层排查](output/DDNS-Go内存排查说明.md) · [连续采样](output/ddnsgo_memory_continuous_tests.json) · [重复负载](output/ddnsgo_memory_reuse_tests.json) · [禁用大页对照](output/ddnsgo_memory_no-thp_tests.json)
- [DDNS-Go 一小时八轮负载/空闲验证](output/DDNS-Go多轮持续内存验证.md) · [专项数据与逐轮基线](output/ddnsgo_memory_cycles-no-thp_tests.json)
- [原厂 HTTPS 与 DDNS-Go 共存稳定性](output/https_stability_tests.json) · [r6 自然复现](output/https_r6_reproduction.json)
- [损坏与低空间安全检查](output/recovery_safety_tests.json) · [r5 复现对照](output/recovery_r5_baseline.json)
- [安装中断恢复说明](output/插件安装中断恢复说明.md) · [中断恢复检查](output/interruption_tests.json) · [r4 中断问题复现](output/interrupt_r4_reproductions.log)
- [真实 HND 插件检查](output/real_plugin_tests.json) · [r3 完整根目录缺陷复现](output/real_plugins_r3_reproductions.log)
- [在线插件检查](output/online_plugin_tests.json) · [r2 缺陷复现](output/online_r2_reproductions.log) · [证书生命周期与共存复核](output/lifecycle_tests.json)：报告绑定当前候选镜像哈希。
- [镜像回读](output/verification.json) · [卷布局](output/structure.json) · [原始 Alpha 3 分析](analysis/固件分析报告.md)
- [localmod2-r6](https://github.com/fanxu1218/RT-AX86U/releases/tag/localmod2-r6-experimental) · [localmod2-r5](https://github.com/fanxu1218/RT-AX86U/releases/tag/localmod2-r5-experimental) · [localmod2-r4](https://github.com/fanxu1218/RT-AX86U/releases/tag/localmod2-r4-experimental) · [localmod2-r3](https://github.com/fanxu1218/RT-AX86U/releases/tag/localmod2-r3-experimental) · [localmod2-r2](https://github.com/fanxu1218/RT-AX86U/releases/tag/localmod2-r2-experimental) · [localmod2-r1](https://github.com/fanxu1218/RT-AX86U/releases/tag/localmod2-r1-experimental) · [原 localmod2](https://github.com/fanxu1218/RT-AX86U/releases/tag/localmod2-experimental) · [上一版 localmod1](https://github.com/fanxu1218/RT-AX86U/releases/tag/localmod1-experimental)

当前 r9-r2 固件 `RT-AX86U_388_24437_localmod2_r9_r2_EXPERIMENTAL.w`，90,177,556 字节。

```text
SHA256: 9ed280d8966b7a88e03f66ae74d87f7dacc760b2a173f50309b2c20372ef27a9
```

保留的 r9 固件 `RT-AX86U_388_24437_localmod2_r9_EXPERIMENTAL.w`，85,852,180 字节。

```text
SHA256: 02ae38a3c0a4fc0942a0608512dd0ab2a9609d2dcf97641e486d9741febd1e50
```

## 验证摘要

当前 r9-r2 候选验证（170 项源码输入、93 个依赖文件、17 份绑定/关联报告）：[完整 gate](output/release_gates.json) · [最终镜像组合回归](output/hardening_tests.json) · [本地交付状态](output/local_delivery.json)。[发布回执](output/release_delivery.json) 仍记录历史 r8，后续实际发布新候选后才更新。早期源码覆盖层报告明确标注未重建镜像，最终组合回归使用组装/回读后的字节。

历史 r9 的 Fancyss/FRPC/PushPlus 26 项、原有三个真实 HND 插件 32 项、在线插件 28 项、证书/共存 17 项、持久化记录 85 次阶段断言、HTTPS 18 项、安装中断 69 项、损坏/低空间 94 项检查使用同一 r9 候选；另有 12 项封存/并行与 13 项官方底包审计。构建模型及其负面对照单独记录在 [模型隔离报告](output/model_isolation_tests.json)。

当前 r9-r2 已完成软件中心迁移九项、发布前端函数七项、Fancyss/FRPC/PushPlus 组合 35 项、六个梅林组件服务 19 项、真实 HND 插件 32 项、在线管理 28 项、证书/共存 17 项、持久化记录 85 项、HTTPS 18 项、中断恢复 69 项、损坏/低空间 94 项、模型隔离 16 项、分片隔离 12 项及六组组合加固/TLS 输入回归。本轮从头运行完整门禁，无沿用前序候选的动态服务结果；生产程序重编译与回读一致。浏览器界面另为模拟服务验证，实机与真实 UU/外网服务尚未验收。

以下长时间采样属于 r7：


DDNS-Go 同一常驻进程追加一小时、8 轮负载/空闲：3522 次 HTTPS 查询、4640 次额外网页读取完成，55 次 GC 存活堆读数均不足 1 MiB。最终静置基线比第一轮空闲末值低 8 KiB；约 1.3 MiB 留存未随轮次持续放大，趋势更符合首次扩容及容量复用。数据与 UU 测试进程保留，未据此修改固件内存策略；有限观测不等于长期或实机无泄漏证明。

追加同一虚拟机 30 分钟实测：1,798 次正常查询无计划外失败，19 次计划重启/断连恢复通过，配置、证书及 UU 测试数据保留。当时 DDNS-Go 进程总 RSS 最大单生命周期样本增幅约 6.9 MiB，未采集映射与 GC，不能逐阶回溯原因。后续专项已分离目标程序与 QEMU 映射，观测到透明大页台阶和 GC 后内存回收，详见 RSS 排查报告；这仍不能证明长期无泄漏。r7 固件及原发布附件不变。

原厂 HTTPS 定向验证 18 项通过，两台全新虚拟机共完成 104 个独立 DDNS-Go 状态/版本请求；查询期间分别停止和运行自有 UU 工作进程，结果全部完整。包含响应头前后中断、重复真实 SIGALRM、空闲超时边界、后端每个 ID 只完成一次及配置/UU 数据保留。r6 自然对照的 64 次查询出现 1 次同类断连。

新增 11 类损坏/空间不足场景、94 项检查通过，覆盖 23 次独立虚拟机启动；核对约 1 MiB 的插件键值、配置文件、保留的原数据库及 UU 测试数据。损坏或空间不足时中心停止且写接口返回 423，可信修复/释放空间后新启动恢复与重试通过。

本轮 11 类中断场景、69 项检查通过，验收记录覆盖独立虚拟磁盘的 24 个启动阶段；包括恢复中再次中断、同一次启动重复恢复拒绝，以及在线、离线、新插件和真实 DDNS-Go 的恢复后重试。配置文件/数据库、UU 合成数据和证书存档保持预期状态。详见中断恢复报告；实机 UBIFS 断电和真实 UU 账号/加速仍未验证。

21 项事件模型检查、19 项兼容检查、7 项 UU 静态/模型检查及 24 项原程序运行与配套检查通过；回读 3,601 个路径和 52,462 个 UBIFS 节点。实时规则测试中，62,601 次普通源端口探测在 24 次表重载和 5 次非路由清空期间均被拒绝。

前序 r4/r7 的 32 项真实插件检查、28 项受控在线管理回归通过，并回归 8 项证书、9 项共存及 24 项原程序运行及配套检查。真实插件分两台全新虚拟机执行：22 项旧版升级、运行/监督、事件、中心重启及卸载检查，10 项当前版从零安装、默认配置及卸载检查。证书由原厂 `gencert.sh`/OpenSSL 生成；全新虚拟机只恢复上一台的自有 `cert.tgz`，证书指纹和 8 个文件保持一致。共存使用实际软件中心服务、原厂 HTTPS/rc 和自有 UU 测试进程；不代表实机断电恢复或真实 UU 加速已验证。

前序受控插件使用实际打包的 httpdb、skipd/dbus 经认证适配层完成真实 multipart 上传、安装、回调及自定义卸载。**新增原程序检查实际运行厂商登录/会话/TLS 和 UU 启动代码；NVRAM/账号/证书输入为合成数据，UU 下载为本地受控响应和自有脚本。原有夹具的内核、xtables/curl/部分启动 helper 来自 Alpine；新增真实插件组使用原厂 curl 和打包的启动工具，内核/xtables 仍是测试边界；不能替代目标设备及外部 UU 服务验证。** 新增三个真实 HND 插件的本地隔离验证；公网下载、外部账号服务及其目标设备行为仍未验证。未移植所有 Merlin Addons、VPN/QoS/DDNS 等扩展。

## 后续官方固件升级

无需重新开发整套官改功能。`sources/localmod/` 的适配代码、固定来源的兼容包及构建/回归脚本可以复用；新官方底包仍须执行差异/接口审计、适配、重新构建与回读，再跑完整门禁和实机验收。同分支更新与更换内核/认证/分区结构的更新，工作量可能明显不同，不能保证自动合并成功。

直接刷纯官方会覆盖固件内适配；JFFS 中保留了配置也不等于软件中心、UU 或插件在新底包上兼容。后续使用针对该官方版本验证的新官改包升级，并先保留可读备份和回退包。当前工具不会自动切换官方版本或刷机，见 [底包迁移检查](output/隔离分片与底包升级说明.md)。

## 仓库与构建

| 路径 | 内容 |
|---|---|
| `sources/localmod/` | 启动器、事件/HTTPd 适配、规则事务、核心初始化与兼容入口 |
| `build/` | 组装、回读、接口清单、ARM 模型与隔离 Linux 环境测试 |
| `output/` | 修改清单、校验结果、测试记录和已知限制 |
| `analysis/` | 原始固件静态分析与校验脚本 |

见 [本地构建说明](sources/localmod/README.md)。脚本面向已准备好依赖的 macOS Apple Silicon 工作区；克隆后仍需准备上游输入、工具链和区分大小写的构建卷。原始固件、工具和缓存留在本地，固件及源码包放在预发布附件。

## 上游

[ASUS 固件支持](https://www.asus.com/hk/supportonly/rt-ax86u/helpdesk_bios?model2Name=RT-AX86U) · [KoolCenter 发布目录](https://fw.koolcenter.com/KoolCenter_Merlin_New_Gen_388/RT-AX86U/) · [Koolshare rogsoft](https://github.com/koolshare/rogsoft) · [Merlin 用户脚本接口](https://github.com/RMerl/asuswrt-merlin.ng/wiki/User-scripts)

第三方组件的版权和许可归各自权利人。此仓库不代表华硕、网易或 KoolCenter 官方发布。
