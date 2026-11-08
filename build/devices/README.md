# 机型配置

当前唯一正式配置是 `rt-ax86u.json`。它描述普通 RT-AX86U 的现有官改输入和格式，不表示其他型号已经兼容或完成实机验收。

`build/release_config.json` 用 `device` 选择机型，保留发布修订号、标签、输出文件和软件中心版本。底包身份从机型配置合并到 `release_config.CONFIG`，现有构建命令不变：

```sh
python3 build/check.py quick
python3 build/check.py dependencies
python3 build/check.py release
```

机型配置集中包含：

| 字段 | 用途 |
|---|---|
| `model`、`adapter` | 原厂机型标识和适配器系列 |
| `base` | 底包版本、路径、输出前缀和原厂接口/哈希基线 |
| `abi` | 编译目标、CPU、ELF 位数及 NVRAM 元组布局 |
| `image` | UBI/UBIFS 几何、卷位置、机型尾部、容量和 mkfs 参数 |
| `plugins` | 安装包平台标识、机型和动态加载器限制 |
| `sources` | 软件中心、Fancyss、Merlin 的固定来源清单 |

这些值实际用于编译、打包、底包检查、镜像回读、页面及安装器生成。脚本和页面在构建时渲染；路由器不增加配置解析服务。RT-AX86U 渲染后保持原有字节。仓库 URL 和历史版本/许可证说明仍属于来源记录，不随机型改名。

## 新增型号

1. 取得准确型号和硬件版本对应的官方固件，检查真实架构、固件格式、分区容量及原厂登录/启动/UU 接口。
2. 新建独立 JSON，设置实际底包、几何和 ABI；该型号的 `base.contracts` 及来源清单可放在同名子目录，例如 `build/devices/新机型/base_contracts.json`，登记真实下载输入的 SHA256。不能只复制旧型号基线或修改固件尾部机型名。
3. 在发布配置选择新 `device`，并设置与该型号 `image_prefix` 一致的输出路径。一次工作区只构建一个选定目标；切换目标时重新准备底包提取、生成目录、依赖锁及验证报告，不能复用旧目标的 stage 或报告。
4. 执行底包审计、构建回读和完整门禁，随后对对应设备做刷入、启动、无线/NAT、HTTPS、插件、UU 及升级回退验收。

当前适配器明确只支持 ASUS HND ARM32 小端用户空间和 ASUS pure-UBI/UBIFS 4。新架构、认证协议、其他品牌或镜像格式还需要实现对应适配器。配置加载器会拒绝未知型号配置、不支持的 ABI 和不一致的输出身份，打包和检查会拒绝不同机型尾部及不同 UBI 几何。

`python3 build/check_device_profiles.py` 不需要原厂镜像即可验证配置边界、合成第二机型的参数传播、插件机型/加载器限制及打包布局。它纳入 quick/CI。合成机型只存在于测试临时目录，不登记为支持型号。

本次 RT-AX86U 回归见 [验证报告](../../output/device_profile_tests.json)：13 项配置测试、19 个生产程序重编译字节对比、完整 stage 对比，以及四个隔离 VM 作业和新 UBIFS 完整回读通过。新旧打包器对原输入生成相同的 r9-r2 镜像；现有镜像未替换。本次未重跑完整发布门禁，也未连接或刷写实机。
