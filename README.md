# RT-AX86U 官方底包官改实验

基于 **ASUS 3.0.0.4.388_24437**，尝试集成 **KoolCenter 软件中心 1.9.50**，保留官方 **网易 UU** 实现。

> **开发候选版，尚未实机验收，暂不建议刷入日常主路由。**
> 离线结构校验与 ARM 仿真通过；刷入接受性、真实启动、官方 HTTPd 完整登录/TLS、插件兼容和 UU 实际加速均未验证。完整梅林事件钩子尚未移植。

## 下载与状态

- [实验预发布与固件附件](https://github.com/fanxu1218/RT-AX86U/releases/tag/localmod1-experimental)
- [修改范围、已通过验证和已知限制](output/官改候选版说明.md)
- [镜像回读验证](output/verification.json) · [卷布局](output/structure.json)
- [ARM API/数据库测试](output/runtime_tests.log) · [页面映射测试](output/filemap_tests.log)
- [原始 Alpha 3 固件分析](analysis/固件分析报告.md)

候选文件：`RT-AX86U_388_24437_localmod1_EXPERIMENTAL.w`，85,327,892 字节。

```text
SHA256: e46b7164227ed4b408f96de6207b4243a1b5c544e9d2fae730e80b2f7d7f1464
```

源码与报告保存在 Git 中；固件和源码打包文件作为预发布附件。下载的官方/第三方原始固件、GPL 压缩包、编译器、虚拟机磁盘、提取文件系统和缓存不进入 Git 历史。

## 仓库内容

| 路径 | 内容 |
|---|---|
| `sources/localmod/` | HTTPd 适配库、启动器、初始化脚本、版本说明页面 |
| `build/` | 镜像组装、回读校验、ARM 测试和临时 Linux 构建环境脚本 |
| `output/` | 当前候选镜像的修改清单、校验结果和测试记录 |
| `analysis/` | 用户提供的 386.3_2 Alpha 3 固件静态分析及校验脚本 |

官方启动卷、内核、设备树、内核模块和 UU 服务相关原文件保持一致。官方 HTTPd 原二进制保留，由新启动器加载适配库；官方 `rc` 保留，init 入口另加软件中心初始化。

## 验证边界

回读比对涵盖 3,588 个路径；651 个 UBI EC/VID 头、28 个静态卷块、256 个卷表记录、52,244 个 UBIFS 节点与整包 CRC 通过。

ARM 测试使用真实适配库及打包的 httpdb、skipd/dbus，但**官方登录认证边界是模拟程序**。这些结果不能证明实机认证、刷机或启动成功。完整 WAN/NAT/services/mount 事件桥接及防火墙更新的原子联动仍待完成；依赖梅林专用接口的插件可能不工作。

## 构建

见 [本地构建说明](sources/localmod/README.md)。当前脚本面向已准备好依赖的 macOS Apple Silicon 工作区，克隆仓库后不能直接一键生成固件；仍需下载上游输入及工具、准备 Python 环境、签名 Linux 构建器，并挂载区分大小写的构建卷。

固件采用 UBIFS 格式 4。构建必须保留大小写不同的 Linux 文件名，并排除 macOS 扩展属性。每次 mkfs 可能生成不同的文件系统信息，重新构建不保证 SHA256 相同。

## 上游

- [ASUS RT-AX86U 固件支持页](https://www.asus.com/hk/supportonly/rt-ax86u/helpdesk_bios?model2Name=RT-AX86U)
- [KoolCenter RT-AX86U 发布目录](https://fw.koolcenter.com/KoolCenter_Merlin_New_Gen_388/RT-AX86U/)
- [Koolshare rogsoft](https://github.com/koolshare/rogsoft)

第三方固件、软件中心与其他上游组件的版权和许可归各自权利人。此仓库不代表华硕、网易或 KoolCenter 官方发布。
