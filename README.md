# RT-AX86U 官方底包官改实验

基于 **ASUS 3.0.0.4.388_24437**，集成 **KoolCenter 软件中心 1.9.50**，保留官方 **网易 UU**。当前开发版本为 **localmod2**。

> **实验候选版，尚未实机验收，暂不建议直接刷入日常主路由。**
> 源码适配、模型/仿真测试和镜像回读通过；刷入启动、原厂登录/TLS、无线/NAT、具体第三方插件及 UU 实际加速仍待实机验证。

## 本轮变化

- 接入启动、服务启停及事件前后回调、WAN、NAT/防火墙、存储挂载/卸载事件，并支持 DNS 配置扩展。
- 保留用户钩子，避免重复启动；处理 WAN fork 重放、卸载重试、带空格路径、脚本超时及 HALT 停机。
- 补充软件中心服务入口、受管理核心迁移和安装回调；修复离线安装失败状态及临时目录冲突，阻止覆盖核心；停止数据库前提交待写数据，避免快速重启丢配置。
- 规则重载与 API 隔离在同一次 filter COMMIT 中完成，并覆盖原厂非路由清空路径。
- 原厂 rc、HTTPd、xtables-multi、启动区、内核模块和 UU 原文件保留，新增启动器负责适配。

## 下载与说明

- [localmod2 实验预发布与固件附件](https://github.com/fanxu1218/RT-AX86U/releases/tag/localmod2-experimental)
- [完整适配范围与验证边界](output/官改候选版说明.md)
- [Alpha 3 升级、实机验收与回退步骤](output/Alpha3升级localmod2与实机验收.md) · [验收记录模板](output/localmod2实机验收记录模板.md)
- [事件测试](output/hooks_tests.json) · [兼容测试](output/compatibility_tests.json) · [原厂接口清单](output/vendor_contracts.json)
- [镜像回读](output/verification.json) · [卷布局](output/structure.json) · [原始 Alpha 3 分析](analysis/固件分析报告.md)
- [上一版 localmod1](https://github.com/fanxu1218/RT-AX86U/releases/tag/localmod1-experimental)

固件 `RT-AX86U_388_24437_localmod2_EXPERIMENTAL.w`，85,327,892 字节。

```text
SHA256: f305a3b405c732ba0c6277f4bd41db2e4e7a8a944bbdd633e930d63562c65b18
```

## 验证摘要

19 项事件模型检查与 14 项兼容检查通过；回读 3,596 个路径和 52,288 个 UBIFS 节点。实时规则测试中，65,086 次普通源端口探测在 24 次表重载和 5 次非路由清空期间均被拒绝。

受控插件使用实际打包的 httpdb、skipd/dbus 完成安装和回调。**官方 rc 硬件动作及登录边界为模型；网络测试采用 Alpine 内核/xtables/curl/启动 helper，不能替代目标设备验证。** 未联网安装第三方插件，也未移植所有 Merlin Addons、VPN/QoS/DDNS 等扩展。

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
