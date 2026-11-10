# ASUS 24447 语言菜单修复 / P7 本地候选

2026-11-10；状态：**NOT_FLASH_READY，未发布、未刷机、未实机验收**。

E：对已校验的官方 24437、24447 和已发布 P7 直接解析回读，24437/P7 的 `LANG_CN`、`LANG_JP` 等显示名仍为问号；24447 恢复了 UTF-8 名称。P7 原生 httpd 保留读取 `Lang_Hdr.txt` 和生成语言菜单的入口。

R：L4 静态数据源 `www/Lang_Hdr.txt` 已损坏，构建流程把这些内容原样带入 P7。官方两版的 httpd、rc、libssl、state.js、登录页和 UU 页字节相同；其他二进制变化不能仅据此判断语义兼容。

F：只移植官方 24447 的语言名称数据，25 个语言键及顺序保留；沿用官方的具体字形，包括其俄文拼写。修补入口绑定原 P7 文件摘要，拒绝意外内容、符号链接或共享 inode，保留权限。后续构建及完整门禁已增加这一受控差异；原 P7 的镜像、发布回执和历史测试报告保持原字节。

## 对比结果

官方更新说明为 [GUI bug fixes](https://www.asus.com/uk/supportonly/rt-ax86u/helpdesk_bios/)，发布日期 2026-11-09。两个官方 ZIP 的 SHA256 与华硕接口公布值一致，ZIP CRC、内部镜像身份及整包/UBI CRC 校验通过。官方 24437 与 24447 共 1,980 个路径有差异：228 个涉及内容、类型或新增，1,752 个仅涉及元数据；`www` 下仅语言名称文件内容改变。内核 `vmlinux.lz`、部分模块/程序及大量权限也有变化，本次不移植这些未经确认的变化。

来源及摘要见 [输入清单](../build/asus24447_sources.json)，完整内容差异和权限变化计数见 [对比报告](merlin38813_gui24447_audit.json)。

## 交付与验证

固件底座仍为 **Merlin 3004.388.13 / P7**；镜像内版本身份保留 P7，独立文件名、摘要和本次报告用于区分修补包。它不包含完整官方 24447 底座，也不替换 GitHub 上的 P7 附件。

本地镜像：`RT-AX86U_3004_388.13_0_localmod_native_P7_GUI24447_2e395d86_NOT_FLASH_READY.w`，87,949,332 字节。

```text
SHA256 2e395d86ed6c9fae6797a426bca72ea4b7c59a39e81c7a6e366b5fe1b6e95115
```

| 验证层 | 本次结果 |
| --- | --- |
| 静态/源码 | 388.13 语法、ARM 目标 C 对象编译、Shell/Go 格式及发布配置检查通过；这是源码检查，不代表整个固件从源码编译 |
| 数据专项 | 25 个语言键、UTF-8、真实 P7 旧文本替换、权限及相邻文件保留、幂等和意外输入/软硬链接拒绝通过 |
| 镜像组装 | 无网卡隔离 Linux 环境中重新生成 UBIFS，保留 P7 原生程序/库/内核/驱动后打包；未重编译完整 ASUS/Merlin 源码 |
| 完整回读 | 3,560 个路径的内容、类型、权限、归属、软硬链接符合预期；相对原 P7 仅语言名称文件改变，整包/UBI CRC、启动区、型号描述和 WFI 参数通过 |
| 完整服务回归/长测 | 未执行；不引用原 P7 五分钟/一小时结果作为新镜像证据 |
| 安装、实机行为及视觉 | 未执行，未访问或刷写路由器，未验证真实 WAN/Wi-Fi/NAT/AiMesh、UU 或插件运行 |

组装/回读证据见 [候选报告](merlin38813_gui24447_candidate.json)，源码与数据专项结果见 [验证记录](merlin38813_gui24447_validation.json)，校验清单见 [SHA256SUMS](merlin38813_GUI24447_SHA256SUMS)。镜像仅在本地生成；没有执行提交、推送或线上发布。

## 复核入口

从项目根目录执行；输入镜像/ZIP 须按来源清单准备，解包环境需 UBI Reader 与 pyelftools。构建需要挂载的区分大小写构建卷、已准备的 `build/tools/LinuxBuilder`、Linux 内核及 initramfs；工具摘要见候选报告。构建入口从已校验的 P7 镜像重新解包，拒绝替换已有输出；重复构建可能因文件时间产生不同镜像摘要，应以每次完整回读和独立报告为准。

```sh
python3 analysis/merlin_vpn_38813/quick.py
python3 analysis/merlin_vpn_38813/check_gui24447.py
analysis/.venv/bin/python analysis/merlin_vpn_38813/audit_gui24447.py
analysis/.venv/bin/python analysis/merlin_vpn_38813/build_gui24447.py
```

审计入口只读处理固件，不执行固件代码；构建和审计证据各自独立。已有输出存在时应选用新的工作副本保留证据，不把原 P7 的报告改绑到修补镜像。
