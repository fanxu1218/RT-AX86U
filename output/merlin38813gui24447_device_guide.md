# GUI24447：备份、升级、实机验收与回退步骤

整理日期：2026-11-10。适用目标：**大陆销售的普通 RT-AX86U，Merlin 3004.388.13 / P7 + GUI24447 语言数据修补**；不适用于 AX86U Pro、AX86S 或其他型号。

**当前仅整理方案，未连接路由器、未执行设备备份、未停用服务、未刷机、未实机/视觉验收。固件仍为 NOT_FLASH_READY / 实验预发布。** 下文设备操作均留待另行确认设备、维护窗口及执行授权后进行；“备份已完成”“可以回刷”都不能从本地回归或本文推定。

配套：[实机验收记录模板](merlin38813gui24447_device_acceptance.md)。实际填写副本放在项目之外的私有备份目录；模板所有项目初始为“未验证”。

离线文档包 `merlin38813gui24447_device_preparation.zip` 含本文、空白模板、阅读说明和 `GUI24447-GUIDE-SHA256SUMS`。解压后可按该清单核验包内文档；另附 `GUI24447-DOCS-SHA256SUMS` 校验本次文档附件（含 ZIP），两者与第 2 节固件附件清单用途不同。

## 1. 先确定升级来源与恢复目标（P1–P3）

先核对机身标签、管理页型号/当前版本、LAN 地址、SSH 指纹和销售区域。**本次没有读取现机信息，不假定仍在 Alpha 3，也不假定任何固定 IP 就是这台 AX86U。** 区域/模式不符时先界定支持范围，不修改地区、MAC 或型号伪造 UU 条件。

| 当前实际固件 | 本次准备路径 | 设置及 JFFS 策略 | 对应回退目标 |
| --- | --- | --- | --- |
| 已核验的原 P7 | 同底座单文件修补；新旧镜像内身份及 core ID 相同 | 先完整备份，保留当前设置、插件、用户钩子；不例行恢复默认或隔离本来有效的 localmod 核心 | 原 P7 固件及此次升级前的 P7 数据 |
| localmod P6 | 388.12_2 → 388.13 底座升级，不能只做语言菜单验收 | 备份全部配置/密钥和自定义启动项；原生设置先保留、逐项验证，异常时另行决定清洁配置；不自动套用 Alpha 3 的首次迁移 | 升级前的 P6 固件/数据；原 P7 不是原状态 |
| 386.3_2 KoolCenter Alpha 3 | 386 → 388 跨版本及旧中心首次迁移 | 备份后隔离旧脚本/扩展；目标首次稳定启动后，单独安排恢复默认与手工最小配置；不导入 Alpha 3 CFG/整份 JFFS/DBus | 核验过的原 Alpha 3 固件/数据；带 CFE-ROM 包另有前置条件，见 R3 |
| 纯官方 / 其他 Merlin / 其他官改 | 先记录确切版本、中心来源和钩子，审查实际升级/回退接受性 | 不套用未核实的中心停止命令或迁移策略；跨版本恢复默认按实际来源单独决定 | 同型号、升级前的确切版本；纯官方救援只恢复基础网络 |

上表是准备分支，**各来源的实际 GUI 接受性、启动、保留升级和回刷均未实机验证**。Merlin 文档不保证跨版本 CFG 兼容；本方案对 Alpha 3 选择手工清洁配置，对已核验原 P7 的单文件修补保留设置，属于按改动范围制定的验收策略。[Merlin 安装说明](https://github.com/RMerl/asuswrt-merlin.ng/wiki/Installation)

维护窗口准备：备用网络、稳定电源、有线 LAN 电脑，以及可用的 Windows 有线网卡和 ASUS Firmware Restoration。首次试验不叠加新 AiMesh、双 WAN、USB/Entware 等变更；原有扩展先备份，再按记录停用及安全卸载。官方救援工具支持 Windows；未测试的 Mac/虚拟机救援不算恢复条件已具备。[ASUS 救援说明](https://www.asus.com/support/faq/1000814/)

**开始条件：** 型号/来源明确、文件哈希正确、备份双副本校验完成、业务数据库已冻结、外置目标已覆盖、回退包和救援工具就绪。缺一项就停在准备阶段。

## 2. 文件身份与离线校验（P2）

目标附件来自 [GUI24447 独立实验预发布](https://github.com/fanxu1218/RT-AX86U/releases/tag/localmod-native-38813-p7-gui24447-experimental)，测试源码固定于 `ece5df372e2c4d01264758e9ecd5598faa69efe3`。底座为 **Merlin 388.13/P7**，不是完整官方 24447 底包。

| 用途 | 文件、字节数 | SHA256 |
| --- | --- | --- |
| 目标修补镜像 | `RT-AX86U_3004_388.13_0_localmod_native_P7_GUI24447_2e395d86_NOT_FLASH_READY.w`；87,949,332 | `2e395d86ed6c9fae6797a426bca72ea4b7c59a39e81c7a6e366b5fe1b6e95115` |
| Fancyss 兼容包，与 P7 相同 | `fancyss_hnd_v8_full_3.5.29_localmod2.tar.gz`；19,790,810 | `b45d1294022b7914f6ffa6ae67c688e4870ef7aa07f3556657feec37a034d592` |
| 原 P7，供同源回退 | `RT-AX86U_3004_388.13_0_localmod_native_P7_3c7521ae_NOT_FLASH_READY.w`；87,949,332 | `9f4b392a9a2575d7fbbf32e1efb747386199e7fb1babe502590c8cb6ef31ea8b` |
| 原 P6，仅从该版升级时准备 | `RT-AX86U_3004_388.12_2_localmod_native_P6_32bd61b0_NOT_FLASH_READY.w`；86,769,684 | `fc7af429b6b9824dab8a06882e36b940ea69eb9e54617e8d89c770c6c194d3ab` |
| 原 Alpha 3，仅当前确为该包时适用 | `RT-AX86U_386.3_2_cferom_pureubi_koolcenter_alpha3.w`；90,570,772 | `c3d01f6df5916ab5f14a2dabd9c79b6d7c28c73b44bed122fdc2636568cf6838` |
| 同型号纯官方恢复备用，固定版本 24447 | `RT-AX86U_3.0.0.4_388_24447-g81951d7_pureubi.w`；83,492,884 | `e133b645f1a656530805ee86ff363198f54117fa0fab74b85e00f6d5049deffa` |

原 P7 从 [原 P7 发布](https://github.com/fanxu1218/RT-AX86U/releases/tag/localmod-native-38813-p7-experimental)下载；仍为实验固件，并非已实机证明可恢复的救援包。官方备用从 [ASUS RT-AX86U 支持页](https://www.asus.com/uk/supportonly/rt-ax86u/helpdesk_bios/)核对来源；本地固定 [ZIP 来源及摘要](https://github.com/fanxu1218/RT-AX86U/blob/ece5df372e2c4d01264758e9ecd5598faa69efe3/build/asus24447_sources.json)另存，以上哈希对应解压的 `.w`，不是 ZIP。它不包含 localmod 中心，也不承诺接受降级或保留 JFFS。P6/Alpha 3/其他来源还必须准备自己升级前的原包和对应数据，不能以 P7 替代。

P6 包从 [P6 历史发布](https://github.com/fanxu1218/RT-AX86U/releases/tag/localmod-native-38812-p6-experimental)获取。P6/Alpha 3 两行引用已有封存记录，本轮没有重读这两个旧包，执行前必须实测哈希；Alpha 3 包的来源仍须与自己原包核对，不能仅凭同名下载。带 CFE-ROM 包还必须满足 R3 的回刷前置条件，准备好文件不代表允许回刷。

在电脑下载目录执行，仅检查文件，不连接设备：

```sh
shasum -a 256 -c RT-AX86U_3004_388.13_0_localmod_native_P7_GUI24447_2e395d86_NOT_FLASH_READY.w.sha256
shasum -a 256 -c fancyss_hnd_v8_full_3.5.29_localmod2.tar.gz.sha256
```

两项应为 `OK`。只有下载齐本 Release **首批 14 个固件/验证附件**时才使用 `shasum -a 256 -c GUI24447-SHA256SUMS`；缺少其他文件不等于已完成首批附件校验。后补文档另用 `GUI24447-DOCS-SHA256SUMS`，不改写首批清单。原 P7 独立校验文件在原发布中。官方备用可用 `shasum -a 256 '实际解压后的文件名.w'` 与表中哈希逐字核对。全部原文件、校验、本文和记录表保存到离线目录；指南 ZIP 只含文档，不含固件、工具或设备备份。

## 3. 备份覆盖与原版本基线（B1–B6）

| 备份内容 | 必须保留的范围和用途 |
| --- | --- |
| 当前版本 CFG 与网络参数 | GUI“系统管理 → 恢复/导出/上传设置”保存完整 CFG；另记 WAN/PPPoE、LAN/DHCP、Wi-Fi、IPv6、IPTV/VLAN、端口转发、路由和管理端口。去密码诊断导出不能作为唯一还原副本。[ASUS 配置备份说明](https://www.asus.com/support/faq/1001376/) |
| 整个 JFFS | 包含隐藏目录、用户 scripts/configs、`.asusrouter`、证书和 SSH 密钥；P6/P7 还包括 `.localmod/ksdb`、`.koolshare`、旧归档、停用标记及事务目录。不是只备份 `/jffs/db`。JFFS 跨刷写可能丢失，须复制到电脑。[Merlin JFFS 说明](https://github.com/RMerl/asuswrt-merlin.ng/wiki/Jffs) |
| 中心/插件 | 插件和版本清单、自身导出、DBus 逻辑输出、静态数据库；DBus 文本只供核对，不是可直接执行的恢复脚本 |
| USB/Entware/外置迁移 | 实际挂载点和数据、链接目标、权限与启动方式；JFFS tar 保留符号链接，不包含其指向的外置数据 |
| UU/Fancyss/VPN | 原账号权益/主机/游戏基线；私下保存节点、订阅、策略、VPN 配置及证书私钥；不假定 UU 登录态可迁移 |

先在原版本记录 LAN/WAN/DNS/Wi-Fi、中心、UU 开→关及真实游戏、实际使用的 Fancyss/VPN 出口和重连。原有故障单列，不能算本次新回归。备份含凭据和私钥，实际文件与原始日志均不进入 Git/Release。

### 3.1 可选 SSH 备份流程：未来设备维护窗口执行

**以下命令本轮没有执行。** 每段成功、人工核对后再进入下一段；停止服务会影响业务。地址与用户名填写实际值，SSH 只开放 LAN，正常核对主机密钥，不关闭校验。备份目录位于项目之外。

```sh
RTAX86U_HOST='替换为已核对的AX86U地址'
RTAX86U_USER='替换为实际管理员用户名'
RTAX86U_BACKUP_DIR="$HOME/Desktop/RTAX86U-before-GUI24447-$(date +%Y%m%d-%H%M%S)"
umask 077
mkdir "$RTAX86U_BACKUP_DIR"
ssh "$RTAX86U_USER@$RTAX86U_HOST" 'test "$(nvram get productid)" = RT-AX86U || exit 40; nvram get firmver; nvram get buildno; nvram get extendno; df -k /jffs; mount; for p in /koolshare /jffs/.koolshare /jffs/.localmod /opt; do if [ -e "$p" ] || [ -L "$p" ]; then ls -ld "$p"; fi; done'
```

核对 GUI/SSH 确为目标、当前版本及目录来源，输出私下保存。GUI 导出的 CFG 保存为 `before-settings.CFG`。先用界面停用插件、代理、VPN、UU 加速和定时写入，等待安装/更新完成。存在 `plugin-txn/active` 或恢复失败时先保留现场排查，不强行“备份后继续”。

**存在正常运行的软件中心时**先逻辑导出；纯官方无中心则记录不适用，不能制造空文件冒充导出：

```sh
if ssh "$RTAX86U_USER@$RTAX86U_HOST" '/usr/bin/dbus listall' > "$RTAX86U_BACKUP_DIR/before-dbus.txt.part"; then
  if [ -s "$RTAX86U_BACKUP_DIR/before-dbus.txt.part" ]; then
    mv "$RTAX86U_BACKUP_DIR/before-dbus.txt.part" "$RTAX86U_BACKUP_DIR/before-dbus.txt"
  else
    echo 'DBus 导出为空：停止准备，保留 part 排查' >&2
    false
  fi
else
  echo 'DBus 导出失败：停止准备，保留 part 排查' >&2
  false
fi
```

随后按已确认版本停止中心，**只执行对应的一种入口**，检查返回码：

| 来源 | 停止方式 | 必须观察 |
| --- | --- | --- |
| 已核验 localmod P6/P7 | 在设备 SSH 执行 `service stop_softcenter` | `skipd/httpdb/perpd/perpboot` 均退出；bootstrap 中的数据库提交屏障成功，不能强杀 skipd |
| 确为原 Alpha 3，且入口已核实 | 设备 SSH 先 `/bin/sh /koolshare/perp/perp.sh stop`，再 `service stop_skipd` | 不以 perp 脚本返回码单独判断成功，另查上述进程确已退出 |
| 其他来源 / 纯官方 | 使用其已核实的停止方式；无中心记录不适用 | 无插件、迁移、配置更新等业务写入；不尝试套用不属于当前固件的命令 |

有后台复活、数据库屏障失败或无法冻结的业务写入就停止，不用强杀/删锁继续。其他系统日志可能仍有写入，另记快照限制；不能把这份归档称为原子整机镜像。对仍在写入的其他业务数据库，需先采用其支持的导出或静态备份方法。

P6/P7 的停止屏障及迁移目录行为依据本批 [bootstrap 源码](https://github.com/fanxu1218/RT-AX86U/blob/ece5df372e2c4d01264758e9ecd5598faa69efe3/sources/localmod/bootstrap.sh)和 [原生服务入口](https://github.com/fanxu1218/RT-AX86U/blob/ece5df372e2c4d01264758e9ecd5598faa69efe3/analysis/merlin_vpn_38813/native_launcher.c)，不等于已经在现机完成停止验证。

确认静态业务数据可归档后，在 Mac 导出 JFFS；失败文件保留 `.part`：

```sh
if ssh "$RTAX86U_USER@$RTAX86U_HOST" 'test "$(nvram get productid)" = RT-AX86U || exit 40; if pidof skipd httpdb perpd perpboot >/dev/null 2>&1; then echo "中心仍在运行" >&2; exit 41; fi; sync && tar -czf - -C /jffs .' > "$RTAX86U_BACKUP_DIR/before-jffs.tar.gz.part"; then
  if gzip -t "$RTAX86U_BACKUP_DIR/before-jffs.tar.gz.part" && tar -tzf "$RTAX86U_BACKUP_DIR/before-jffs.tar.gz.part" > "$RTAX86U_BACKUP_DIR/before-jffs-filelist.txt"; then
    mv "$RTAX86U_BACKUP_DIR/before-jffs.tar.gz.part" "$RTAX86U_BACKUP_DIR/before-jffs.tar.gz"
  else
    echo '归档校验失败：停止准备' >&2
    false
  fi
else
  echo 'SSH/tar 失败：停止准备，part 不是有效备份' >&2
  false
fi
```

查看 `tar -tvzf`，对照源目录确认数据库、隐藏目录、脚本、证书/密钥和链接/权限均在；额外备份 USB 实际目标。电脑文件非空、gzip/tar 成功不等于还原演练完成。

### 3.2 双副本放行

在私有备份目录确认 CFG/JFFS 非空并生成校验；存在中心时将成功的 `before-dbus.txt` 加入同一清单，其他插件导出、密钥和外置归档也逐项追加：

```sh
(cd "$RTAX86U_BACKUP_DIR" && test -s before-settings.CFG && test -s before-jffs.tar.gz && shasum -a 256 before-settings.CFG before-jffs.tar.gz > BACKUP_SHA256SUMS && shasum -a 256 -c BACKUP_SHA256SUMS)
```

把完整私有目录复制到第二份独立存储，在第二副本中再执行 `shasum -a 256 -c BACKUP_SHA256SUMS`。模板 B1–B6 全部放行才准备升级；结论写“覆盖/可读性/双副本校验完成，整机还原演练未执行”。若仅做备份后中止，按当前固件恢复中心、插件及计划任务并核对业务；不要把人为停止的服务当成故障。

## 4. 升级前的目录、事务和空间检查（Q1–Q2）

只读记录 `/jffs/.localmod/initialized`、`core-version`、`plugin-txn/active`、`/jffs/localmod-disabled`、`.koolshare.pre-localmod`、`.localmod/asusrouter.previous` 及 scripts/configs/USB 链接。已有冲突、来源不明或恢复残留时保留证据，不删除标记强行继续。

- **原 P7：** 确认运行 core ID 与第 5 节预期一致，保留原插件/数据库/用户钩子；同 core ID 不代表新语言修补已生效，不期待核心重装。若需为释放内存先正常重启，在备份/停服务之前做，随后重查状态。
- **P6：** 管理核心版本变化会走现有 localmod 更新分支，代码设计保留插件/数据库/用户钩子；仍需实机核对。自定义脚本或 USB 依赖逐项审查，不将当前有效的中心目录当作旧 Alpha 3 核心隔离。
- **Alpha 3/陌生旧扩展：** 备份放行后按实际状态将旧 `scripts/configs` 等自启来源改名保存到未占用路径，记录原位置/归档位置；不覆盖、不合并。首次迁移会归档旧 `.koolshare` 与 `.asusrouter`，保留旧 `/jffs/db`，新数据库使用 `.localmod/ksdb`，不会自动迁移旧插件。隔离后若中止，先按记录恢复目录，不让旧初始化在重启时重新生成活动钩子。

空间检查以实际 `df -k /jffs` 和目录占用为准。首次核心复制要求核心占用加 2 MiB，这是代码下限而非整次操作预算；Fancyss 压缩包约 19 MiB、解压约 26 MiB，还要下载/检查点/现有插件及备份余量。空间不足就停，不删除 UU、旧备份或事务目录腾空间。插件包已经同版本时，不为证明“更新”重复安装。

## 5. 未来有线手动升级与镜像身份（A1–A2）

1. 获得本次执行授权且准备放行后，电脑有线接已核对设备 LAN；保持备用网络/救援可用，避免电脑代理/VPN/多网卡误路由。
2. 通过当前 GUI“系统管理 → 固件升级 → 手动上传”选择本批已校验 `.w`，不使用自动更新入口。`.tar.gz` 只供插件安装，不能作为固件上传。[ASUS 手动升级说明](https://www.asus.com/support/faq/1008000/)
3. 签名、型号、版本/降级或无效固件拒绝时保存首个提示并停止；不改头部/后缀、不关闭校验、不裸写分区，不用救援来绕过对实验包的拒绝。
4. 等待写入和自动重启，不重复提交、断电或按键。首次启动可预留约 10 分钟观察，这不是允许断电的超时阈值；久未可达先查 LAN 地址/网卡/灯态并确认是否仍在写入。
5. 稳定登录后保存首次日志，先做下面身份/L1，再按来源分支决定设置策略。Alpha 3 跨版本按计划恢复默认并手工建立最小网络；已核验原 P7 不例行重置。任何需要清除设置的动作先再次核对完整备份和清除范围，不选择未经计划的 JFFS 格式化/全量清除。Restore/Initialize 的范围不同，不能假定旧归档会保留。[ASUS 重置范围说明](https://www.asus.com/support/faq/1035717/)

**目标 GUI24447 设备 SSH，只读，未来执行：**

```sh
cat /rom/etc/localmod-release.json
cat /rom/etc/localmod-core-id
cat /jffs/.localmod/core-version
cat /rom/etc/koolshare/.soft_ver
sha256sum /www/Lang_Hdr.txt
grep -E '^LANG_(CN|TW|JP)=' /www/Lang_Hdr.txt
df -k /jffs
```

预期如下，逐项填入 A2/L1；若没有 `sha256sum`，可用原生 `openssl dgst -sha256 /www/Lang_Hdr.txt`，不能跳过摘要验证：

| 身份 | 本批实际预期 |
| --- | --- |
| 元数据 | `base=3004.388.13`，`variant=localmod-native-preview`，`revision=P7`，`software_center=1.9.60`，`status=NOT_FLASH_READY` |
| 内部 release_tag | 仍为 `localmod-native-38813-p7-experimental`；下载页面内原 P7 链接同样保留，这本身不是刷错证据 |
| 两个 core ID | `/rom/etc/localmod-core-id` 与 `/jffs/.localmod/core-version` 均为 `95b2436bb2ebc635f946a60517972119dd92ea44b201a8b2b424cfd33380180d`；不一致时先停止插件验收 |
| 语言文件 SHA256 | `1e2e75c17ef60586a278cc77c6a4a780fa257441b15f1cfb44ef1b3a44cbe946` |
| 关键标签 | `LANG_CN=简体中文`、`LANG_TW=繁體中文`、`LANG_JP=日本語`；全部 25 键及顺序保留 |

电脑端整包 SHA256 证明选用的文件，设备只读文件摘要证明该数据已经生效；**版本页头/P7 core ID 相同不能区分原 P7 和本修补版**。原 P7 语言文件摘要为 `1cf2b327d508253947c6c97887ed182fb88140c1457fbb85c380b7d620ed9f93`。

## 6. 语言菜单与基础网络验收（L1–L3、N1–N3）

1. L1 核对上述只读文件摘要、关键标签及身份，保存输出；不要在可写目录临时覆盖语言文件制造通过。
2. L2 使用正常认证的原生管理页，刷新缓存或重新登录，展开语言菜单；对当前区域实际提供的简中/繁中/日文选项截图，确认名称无问号/乱码、选择可用且页面正常。区域限制导致未提供的选项单独记范围，不改区域强行测试。只修复名称数据，不据此宣称所有正文翻译已验证。
3. L3 记录原语言，切换一个受支持语言后重新登录；正常 GUI 重启后复查摘要、菜单和已保存语言，再按需要恢复原语言。记录浏览器/版本及前后截图，不能以文件正确代替视觉验收。
4. N1–N3 分别检查有线 LAN/管理 HTTPS、WAN、DHCP/DNS/NTP、2.4/5 GHz 的实际终端联网；使用中的 IPv6、IPTV/VLAN/端口转发另测。HTTPS/SSH 指纹变化先核对设备与证书，不直接绕过警告。基础网络失败时停止插件测试。

## 7. 软件中心、UU、Fancyss、VPN 的分阶段验收

所有项目均需真实设备证据。既有插件先保持关闭并保存配置，再逐个启用；未安装时从可信适配包开始。没有第二个可信版本时，真实更新记“未验证”，同版跳过不能充当升级通过。

| 项目 | 操作和通过标准 |
| --- | --- |
| S1 核心/数据 | `/Module_Softcenter.asp` 为 1.9.60，进程/数据库/用户钩子与选定来源分支一致；原 P7 插件配置保留，Alpha 3 旧插件不被自动启动 |
| S2 认证/隔离 | 登录后正常；退出后隐私窗口访问 `/_localmod/status`、`/_api/softcenter_` 不得返回业务数据/执行写入；LAN 直连 3032 失败。不只凭 HTTP 状态码判定 |
| S3 实例/事件 | 中心/数据库/事件守护为预期单实例，3032 仅 loopback，`LOCALMOD_API` 保护存在；原生钩子与中心 helper 各一次，不覆盖用户脚本，不用测试 dispatch 冒充真实事件 |
| S4 持久化 | 空闲维护状态选用确认不存在的唯一测试键，写入后立即 `service restart_skipd` 再读；另一次写入后立即 GUI 重启再读，均保留后删除自有测试键。两次写入与重启之间不提前读取 |
| S5 安装/更新 | 一个可信 HND 轻量插件完成安装、真实功能、配置保存及重启；有可信两版时再做真实更新和配置保留 |
| S6 卸载/重装 | 自有测试插件卸载和重装后，基础网络、其他插件、共享 JQ、UU 不受损；已有业务插件不作为随意卸载样本 |
| S7 自然异常 | 若出现 423/事务恢复异常，保存日志/检查点，停止继续写入并排查；没有异常则记未触发，不拔电或删除 active 造测试 |
| U1–U5 原厂 UU | 先无代理/VPN：`/UUAccelerator.asp`、官方登录/权益、正确发现主机、同账号/主机/游戏区服开→关真实联机 15–30 分钟；再分别验证 GUI 重启、WAN 重连和共存。页面“加速中”/存在进程不足以证明真实加速；无权益/主机记未验证 |
| F1–F5 Fancyss | 本批兼容包安装且先关闭；授权节点的实际流量/出口/DNS；开关后恢复直连，上游不可用时按所选策略阻断或直连；保存/重启/自启、同条件 UU 保留；使用自有测试配置完成卸载/重装，共享 JQ 和其他插件不受损。订阅、IPv6、UDP、透明/全局模式按实际用法逐项记录 |
| V1–V4 原生 VPN | 实际使用的协议页面/配置/密钥保存，外部真实隧道及目标流量、出口/DNS/IPv6；Director 的目标与对照终端；启停/断线/WAN重连/重启保留。使用服务端时从独立外网测试；弱旧证书不兼容时看日志更新合法配置，不降低安全策略 |

UU 若缺页或不可用，先只读核对 `productid/territory_code/sw_mode/rc_support`、时间与 NTP；不替换第三方 UU 脚本。有账号登录、发现主机、真实游戏三层证据才填对应通过；加速不要求每次延迟都更低。Fancyss/VPN 对同一终端叠加路由需要另列场景，不能默认 UU 自动绕过。

只读排查入口，输出私下保留：

```sh
pidof skipd httpdb
ps | grep '[l]ocalmod-event'
netstat -lnt | grep ':3032'
iptables -S LOCALMOD_API
nvram get jffs2_scripts
tail -n 60 /tmp/.localmod/bootstrap.log
```

## 8. 共存矩阵与持续观察（C1–C7、T1–T3）

准备游戏 G、代理测试 F、VPN 测试 V，先分离策略和 DNS。G 明确排除于 Fancyss/VPN 路由，F/V 分别验证预期出口；这不保证用户原有策略天然相容。

| ID | 组合 | 每轮必须记录 |
| --- | --- | --- |
| C1 | 中心，无 UU/代理/VPN | 基础网络、认证查询和配置 |
| C2 | 中心 + UU | G 实际游戏、UU 开关与停止后直连 |
| C3 | 中心 + Fancyss | F 实际代理出口、DNS与关闭恢复 |
| C4 | 中心 + VPN | V 真实隧道、出口、DNS与断开恢复 |
| C5 | 中心 + UU + Fancyss | G/F 同时使用，出口/解析无串线 |
| C6 | 中心 + UU + VPN | G/V 同时使用，游戏与隧道均正常 |
| C7 | 四者并行 | G/F/V 实际流量、中心查询及逐项停止后的恢复 |

T1：无关键业务时，一次正常中心重启、VPN/Fancyss 启停、WAN 重连，每次重测基础网络、3032 隔离和业务；确需防火墙重载时，仅在有线管理下正常重载后复核，不清空规则。T2：两次正常 GUI 重启后检查身份/语言、配置/证书、单实例、自启与实际流量。T3：观察至少 24 小时，记录 0/5/15/30/60 分钟及 6/24 小时的 uptime、服务/PID、RSS/FD、JFFS 余量、掉线和重启。PID 变化分开记录，一小时或 24 小时均不证明长期无泄漏。

私有 API 暴露、持续网络异常、反复重启/配置丢失、JFFS 不足/检查点失败，或原版本正常的 UU 同条件失效时，停止追加功能，保存首个错误及此前动作，按下节选择恢复路径。

## 9. 回退步骤：按当前可访问状态选择

### R0：尚未刷机，只做了备份/停用/隔离

仍在原版本时按记录恢复所需中心、插件和定时任务；改名隔离过的目录先核对源/目的是否冲突，逐项恢复，不合并覆盖。复查原版本网络与 UU 基线。不能把“未刷机”当作“服务没被停止”；本轮实际没有执行这些动作。

### R1：GUI24447 可管理，先停用适配止损

保存新数据/日志，停用 Fancyss/VPN/插件和 UU 加速。仅在确认运行本批 localmod 且空闲时，未来设备 SSH 执行：

```sh
touch /jffs/localmod-disabled &&
service stop_softcenter &&
sync
```

检查返回码、中心/数据库退出且无安装任务后，通过 GUI 正常重启，让新进程不再加载适配库。停止失败保留现场，不强杀数据库。标记不会擦除配置，也不撤销插件曾改写的所有路由/DNS/用户脚本；复查原生网络及 UU。**这是停用中心适配，不是回刷，也不会撤销只读语言修补或变成纯官方。** 查清故障前保留标记，不删除 `.localmod`/事务目录“重装”；重新启用另行安排并复验。

### R2：可管理，回到原 P7

1. 此路径只恢复到原 P7；若升级前为 P6/Alpha 3/官方，继续看 R3。保存升级后的新配置/日志，明确哪些新增数据尚未备份，按 R1 停用服务。
2. 核对原 P7 `.w` 哈希及升级前 P7 双副本；在正常升级页上传原 P7。拒绝时保留错误并停止，不绕过签名/型号/版本校验。
3. 写入完成稳定启动后，元数据/core ID 仍与第 5 节相同；`/www/Lang_Hdr.txt` 应回到原 P7 哈希 `1cf2b327d508253947c6c97887ed182fb88140c1457fbb85c380b7d620ed9f93`，语言名称缺陷随之恢复，这是此回刷的预期结果。
4. 同 core ID 的中心数据原则上由原位置继续使用，但实际保留性须核对；R1 留下的停用标记也可能仍在。先确认故障原因和目录/数据库一致，决定启用时仅移除本次新建、用途明确的标记并正常重启；若标记原来就存在，保持原状态。
5. 不先整份覆盖 JFFS；确需恢复时在对应固件、服务静止且目录映射明确后按升级前 P7 备份逐项恢复。核对基础网络、配置/证书、插件、UU 和原基线，分别记录“固件已回到 P7”“数据/业务恢复”，不能互相替代。

### R3：可管理，恢复到升级前确切版本

P6 使用 P6 原包及对应 P6 备份；纯官方使用同型号确切原包及其配置，先手工建立基础网络。不同版本 CFG/JFFS/DBus 不直接灌入当前 GUI24447，也不把新版 `.localmod/ksdb` 当旧 Alpha 3 `/jffs/db`。

Alpha 3 原整包 `RT-AX86U_386.3_2_cferom_pureubi_koolcenter_alpha3.w` **带 CFE-ROM 区域**。若选此路，必须另外核对原包来源/哈希、该设备升级器及发布方对整包回刷写入范围的要求；要求不明或被拒绝就停止，不能因过去能直升而推断能直降。本指南不写 CFE、不裁包或裸写分区；必要时先用 R4 恢复纯官方基础网络，再单独评估原官改安装。

回刷前保存当前数据并停止扩展；对于会启动旧中心的来源，按实际目录映射将新版活动核心、`.localmod` 和 scripts/configs 等分别归档到未占用目录，防止旧系统启动新版核心，不删除旧归档/旧数据库。目录状态不明时暂停，不能盲目执行通用移动/解包命令。只有旧固件已确认启动、旧中心静止后，才逐项恢复其对应核心、数据库、启动入口、脚本、外置挂载及插件导出，最后恢复自启。CFG 也仅在对应型号/原版本作为恢复选项；重新登录账号和游戏对照另行记录。

### R4：管理页/SSH 不可用，救援到同型号纯官方

确认升级写入已结束，再排除电脑网卡、DHCP/LAN 地址变化和连错设备。以下是未来救援动作，不在本轮执行；使用准备好的 Windows 电脑及已核验纯官方 `.w`，不以救援强刷实验包。[ASUS 官方救援流程](https://www.asus.com/support/faq/1000814/)

1. 有线接 LAN，避免其他网卡误路由；按官方工具流程把救援网卡设为 `192.168.1.10/255.255.255.0`。这是隔离救援网络的设置，不是对日常管理地址的推断。
2. 关闭路由器，按住 **RESET** 上电，待电源灯进入救援闪烁后释放，具体依同型号说明；RESET 救援与 WPS 清配置不同。
3. Firmware Restoration 选择解压后的同型号纯官方镜像并上传，等待写入和自动重启，期间不断电。失败时保存首个提示，核对型号/网卡/网线/灯态；持续失败联系支持，不继续擦写分区或引导程序。
4. 完成后恢复电脑自动获取 IP/DNS，核对官方版本，手工恢复最小网络，不直接导入 localmod/Alpha 3 整份数据。官方联网恢复与重新安装原固件/中心及还原业务分开记录。

如写入结束后确需清除异常配置，ASUS 将 RT-AX86U 列在 [WPS 硬重置 Method 2](https://www.asus.com/support/faq/1039078/)：关机，按住 WPS 上电，电源灯熄灭后释放，再通过电源键重启。这会清配置，不能代替固件回退或备份，也不保证删除所有 JFFS 内容；只有备份及清除范围确认后才安排。

## 10. 当前证据与最终交付边界

已有证据：本批镜像组装/全量回读、6 个适配程序重编译、39 份绑定报告的完整本地运行回归和 3,605.8 秒共存通过；14 个发布附件公开回读 SHA256 一致。见 [完整门禁](https://github.com/fanxu1218/RT-AX86U/blob/ece5df372e2c4d01264758e9ecd5598faa69efe3/output/merlin38813gui24447_full_gate.json)及 [发布回执](https://github.com/fanxu1218/RT-AX86U/blob/a1a2a1a8a4b1adb070bde85a35b2e4e0c4996369/output/merlin38813gui24447_release_delivery.json)。这些不替代目标 Broadcom 内核/PID1、物理刷写/断电、WAN/Wi-Fi/NAT/AiMesh、真实 UU/外部 VPN/代理或视觉验收。

设备执行后的结论按模板列明型号、来源、网络、插件/协议版本、测试时长与失败/未验证项；没有设备证据仍保持“未实机验收”。本文、空白模板和离线包作为独立文档附件，提交/线上发布状态以 GUI24447 预发布及单独文档发布回执为准；发布文档不改变设备验收状态，也不修改原 P7 或本修补版的冻结固件/证据。
