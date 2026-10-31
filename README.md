# RT-AX86U 官方底包官改实验

基于 **ASUS 3.0.0.4.388_24437**，集成 **KoolCenter 软件中心 1.9.50**，保留官方 **网易 UU**。当前开发版本为 **localmod2-r5**。

> **实验候选版，尚未实机验收，暂不建议直接刷入日常主路由。**
> 源码适配、模型/仿真测试和镜像回读通过；刷入启动、原厂登录/TLS、无线/NAT、具体第三方插件及 UU 实际加速仍待实机验证。

## 本轮变化

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

- [localmod2-r5 实验预发布与固件附件](https://github.com/fanxu1218/RT-AX86U/releases/tag/localmod2-r5-experimental)
- [完整适配范围与验证边界](output/官改候选版说明.md)
- [Alpha 3 升级、实机验收与回退步骤](output/Alpha3升级localmod2与实机验收.md) · [验收记录模板](output/localmod2实机验收记录模板.md)
- [事件测试](output/hooks_tests.json) · [兼容测试](output/compatibility_tests.json) · [原厂接口清单](output/vendor_contracts.json) · [UU 静态及模型检查](output/uu_compatibility_tests.json) · [原厂登录/TLS/UU 本地运行检查](output/native_runtime_tests.json)
- [安装中断恢复说明](output/插件安装中断恢复说明.md) · [中断恢复检查](output/interruption_tests.json) · [r4 中断问题复现](output/interrupt_r4_reproductions.log)
- [真实 HND 插件检查](output/real_plugin_tests.json) · [r3 完整根目录缺陷复现](output/real_plugins_r3_reproductions.log)
- [在线插件检查](output/online_plugin_tests.json) · [r2 缺陷复现](output/online_r2_reproductions.log) · [证书生命周期与共存复核](output/lifecycle_tests.json)：报告绑定当前候选镜像哈希。
- [镜像回读](output/verification.json) · [卷布局](output/structure.json) · [原始 Alpha 3 分析](analysis/固件分析报告.md)
- [localmod2-r4](https://github.com/fanxu1218/RT-AX86U/releases/tag/localmod2-r4-experimental) · [localmod2-r3](https://github.com/fanxu1218/RT-AX86U/releases/tag/localmod2-r3-experimental) · [localmod2-r2](https://github.com/fanxu1218/RT-AX86U/releases/tag/localmod2-r2-experimental) · [localmod2-r1](https://github.com/fanxu1218/RT-AX86U/releases/tag/localmod2-r1-experimental) · [原 localmod2](https://github.com/fanxu1218/RT-AX86U/releases/tag/localmod2-experimental) · [上一版 localmod1](https://github.com/fanxu1218/RT-AX86U/releases/tag/localmod1-experimental)

固件 `RT-AX86U_388_24437_localmod2_r5_EXPERIMENTAL.w`，85,721,108 字节。

```text
SHA256: e55a5178bc4d11a9bc90772362753ee9cc73d644d870a8c572ab5b9376768841
```

## 验证摘要

本轮 11 类中断场景、69 项检查通过，使用独立虚拟磁盘连续启动 24 次新虚拟机；包括恢复中再次中断、同一次启动重复恢复拒绝，以及在线、离线、新插件和真实 DDNS-Go 的恢复后重试。配置文件/数据库、UU 合成数据和证书存档保持预期状态。详见中断恢复报告；实机 UBIFS 断电和真实 UU 账号/加速仍未验证。

21 项事件模型检查、19 项兼容检查、7 项 UU 静态/模型检查及 24 项原程序运行与配套检查通过；回读 3,601 个路径和 52,456 个 UBIFS 节点。实时规则测试中，63,214 次普通源端口探测在 24 次表重载和 5 次非路由清空期间均被拒绝。

本次 32 项真实插件检查、28 项受控在线管理回归通过，并回归 8 项证书、9 项共存及 24 项原程序运行及配套检查。真实插件分两台全新虚拟机执行：22 项旧版升级、运行/监督、事件、中心重启及卸载检查，10 项当前版从零安装、默认配置及卸载检查。证书由原厂 `gencert.sh`/OpenSSL 生成；全新虚拟机只恢复上一台的自有 `cert.tgz`，证书指纹和 8 个文件保持一致。共存使用实际软件中心服务、原厂 HTTPS/rc 和自有 UU 测试进程；不代表实机断电恢复或真实 UU 加速已验证。

受控插件使用实际打包的 httpdb、skipd/dbus 经认证适配层完成真实 multipart 上传、安装、回调及自定义卸载。**新增原程序检查实际运行厂商登录/会话/TLS 和 UU 启动代码；NVRAM/账号/证书输入为合成数据，UU 下载为本地受控响应和自有脚本。原有夹具的内核、xtables/curl/部分启动 helper 来自 Alpine；新增真实插件组使用原厂 curl 和打包的启动工具，内核/xtables 仍是测试边界；不能替代目标设备及外部 UU 服务验证。** 新增三个真实 HND 插件的本地隔离验证；公网下载、外部账号服务及其目标设备行为仍未验证。未移植所有 Merlin Addons、VPN/QoS/DDNS 等扩展。

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
