# Alpha 3 → P7：备份、刷机、实机验收与回退

整理日期：2026-11-09。适用：**大陆销售的普通 RT-AX86U**，当前 `386.3_2 KoolCenter Alpha 3`，目标 `3004.388.13 / localmod-native-P7`。不适用于 AX86U Pro、AX86S 或其他型号。

**状态：待执行方案；本次未连接路由器、未备份设备、未刷机、未做实机验收。** 此前备份任务已按用户要求略过，不能视为已经有可用备份。P7 虽已发布，仍是 **实验预发布 / NOT_FLASH_READY / 未实机验收**；Alpha 3 直升接受性、回刷接受性及实机启动均未确认。

本方案顺序：**确认设备与回退条件 → 备份并校验 → 停用旧扩展与隔离配置 → 有线手动上传 → 核对 P7 身份 → 恢复默认并手工设置最小网络 → 软件中心 → 原厂 UU → Fancyss → VPN → 共存及持续观察**。每阶段通过再继续，使用配套 [P7 实机验收记录模板](P7实机验收记录模板.md)。

本次从 Alpha 3 直接以 P7 为目标，**不要求先刷 localmod2、r9 或 P6**；这只说明准备的目标版本，不代表直升路径已经实机证实。开始前先读第 11 节：原 Alpha 3 包含 CFE-ROM，不能把“保留了原包”当成已验证可直接回刷。任何阶段失败都停在该阶段，记录原始错误，不继续叠加插件。

### P7 升级中特别需要核对的变化

P7 使用完整梅林 388.13 底座，软件中心为 1.9.60；OpenSSL 升到 3.5，OpenVPN 为 2.7.8。旧 OpenVPN 的静态密钥认证已移除，服务端压缩选项及部分过时参数也有变化。旧配置应先导出保存，再按服务商或自有服务端要求重新核对证书、认证及加密参数；不在升级前覆盖唯一旧配置，也不为连接成功关闭证书验证。具体上游变化见[固定提交的更新日志](https://github.com/RMerl/asuswrt-merlin.ng/blob/d1a59dcffbe0402c7ac8ac3090cb7c928510fbcd/Changelog-NG.txt)。

## 1. 维护窗口与开始条件

- 准备备用网络、稳定电源、网线和有线电脑。暂停家庭关键业务；P7 首次试验不接入 AiMesh、USB/Entware、双 WAN 或其他扩展。已有 USB 数据先完成下文备份和安全卸载，不能为“清洁环境”先拔掉尚未备份的存储。
- 核对机身型号、管理页型号/Alpha 3 版本、LAN 地址和 SSH 主机指纹。过去的 `192.168.2.1` 曾指向另一台华为路由，**本文不假定任何地址就是目标设备**。
- 将下表文件、指南、校验文件保存到电脑，离线也能访问。原 Alpha 3 静态分析确认含 CFE-ROM 启动区域；回刷前还需核实该设备升级器及发布方对这种整包的处理要求，不能只凭 GUI 接受就保证写入范围安全。本方案不写 CFE、不裁掉头部、不执行裸分区写入；未能确认原包回刷要求时，保守回退采用同型号纯官方恢复。
- 备用恢复准备一台能运行 ASUS Firmware Restoration 的 Windows 电脑及有线网卡。华硕官方救援工具面向 Windows；先确认工具已安装、网卡可用，不能把尚未验证的 Mac/虚拟机救援当作已具备的条件。[华硕救援说明](https://www.asus.com/support/faq/1000814/)
- 保存 WAN/PPPoE、IPTV/VLAN、LAN/DHCP、Wi-Fi、IPv6、转发与 VPN 必要参数；私下保管密码、证书/私钥、Fancyss 节点和订阅、UU 账号。首次测试保留有线 LAN 管理通道。

**任一条件未满足就停在准备阶段：** 型号/哈希不符；没有校验过的电脑端备份；外置插件数据未覆盖；数据库不能停止；没有恢复设备/固件；当前已有不明迁移或恢复残留。

## 2. 本批文件和校验

下载：[P7 实验预发布](https://github.com/fanxu1218/RT-AX86U/releases/tag/localmod-native-38813-p7-experimental)。只使用本批兼容包，不把其他平台包或上游原包改名代替。

| 用途 | 文件、字节数 | SHA256 |
|---|---|---|
| P7 固件 | `RT-AX86U_3004_388.13_0_localmod_native_P7_3c7521ae_NOT_FLASH_READY.w`；87,949,332 | `9f4b392a9a2575d7fbbf32e1efb747386199e7fb1babe502590c8cb6ef31ea8b` |
| Fancyss 兼容包 | `fancyss_hnd_v8_full_3.5.29_localmod2.tar.gz`；19,790,810 | `b45d1294022b7914f6ffa6ae67c688e4870ef7aa07f3556657feec37a034d592` |
| 回原 Alpha 3 | `RT-AX86U_386.3_2_cferom_pureubi_koolcenter_alpha3.w`；90,570,772 | `c3d01f6df5916ab5f14a2dabd9c79b6d7c28c73b44bed122fdc2636568cf6838` |
| 纯官方恢复备用，固定本地版本 | `RT-AX86U_3.0.0.4_388_24437-g81951d7_pureubi.w`；83,361,812 | `de1caf609347beea394ebab956bddf0b391db592d1ad5f99e9d37e4d0b876af0` |

后两项不是本次 Release 附件。原 Alpha 3 已在本地保留；官方恢复包应从 [RT-AX86U 官方支持页](https://www.asus.com.cn/supportonly/rt-ax86u/helpdesk_bios/?model2Name=RT-AX86-Series-RT-AX86U-RT-AX86S)核对来源。固定备用版本不表示当前最新版本，也不保证设备允许降级；另选版本须重新核验型号和哈希。官网校验值须先确认对应 ZIP 还是解压后的镜像，本表对比的是列明的 `.w` 文件，不能混用不同文件的哈希。

**电脑端，只校验下载文件：** 同时下载 Release 的独立 `.sha256` 文件，在对应附件目录执行：

```sh
shasum -a 256 -c RT-AX86U_3004_388.13_0_localmod_native_P7_3c7521ae_NOT_FLASH_READY.w.sha256
shasum -a 256 -c fancyss_hnd_v8_full_3.5.29_localmod2.tar.gz.sha256
```

须均为 `OK`。原始发布的 9 个附件下载齐全时才执行 `shasum -a 256 -c SHA256SUMS`；只下载两个包时，全清单提示其他文件缺失不能当成这两个包已校验。后补的 8 份小时验证附件使用独立的 `P7-HOUR-SHA256SUMS`，两份清单分别对应各自文件。固件上传选 `.w`，Fancyss 安装选 `.tar.gz`，两者入口不同。

## 3. Alpha 3 备份与基线

### 3.1 备份覆盖范围

| 项目 | 操作与用途 |
|---|---|
| 原版本 CFG | 在 Alpha 3 管理页“系统管理 → 恢复/导出/上传设置”保存。用于回到同一 Alpha 3 后恢复；不导入 P7。不要选择移除密码/敏感信息的诊断导出作为唯一还原备份。[华硕配置备份说明](https://www.asus.com/support/faq/1001376/) |
| 整个 JFFS | 包括隐藏目录、数据库、用户脚本、DNS 配置、证书和 SSH 密钥。若界面确有“备份 JFFS”也保存一份；停止写入后再做文件归档。[Merlin JFFS 说明](https://github.com/RMerl/asuswrt-merlin.ng/wiki/Jffs) |
| 软件中心和插件 | 记录插件/版本，使用插件自身导出；另存 DBus 逻辑输出及原 `/jffs/db`。全量 DBus 文本只供核对，不是可执行的恢复脚本。 |
| 外置数据 | 检查 `/koolshare`、`/jffs/.koolshare`、`/opt` 的链接与挂载。JFFS tar 默认保留链接，不包含链接指向的 USB 数据；对实际外置插件目录、配置和必要文件另行备份。未覆盖则不能判完整。 |
| UU / Fancyss / VPN | UU 记录账号权益和原版本实测，账号仍可能需要重新登录；Fancyss 私下导出节点/配置；VPN 保存配置、证书/密钥、自定义参数和策略。截图不能代替私钥备份。 |

先在原 Alpha 3、同一主机/游戏/区服测一轮 UU 开/关及实际联机；若已使用 Fancyss/VPN，也分别记录原状态、出口、DNS 和重连。原版本已有故障单列为基线问题。USB 目标备份完成、停止应用并经固件安全卸载后，再断开存储；不要把失去挂载后的空目录当成已经备份的数据。

### 3.2 可选 Mac 备份命令——未来在正确设备上执行

**本次只编写以下命令，没有执行。** 它们不刷机，但停止中心会短暂影响插件。先在界面停用插件/代理/VPN、暂停更新与定时任务，停止 UU 加速；确认没有插件安装或配置写入。SSH 仅开放 LAN，密码在终端输入，不发到聊天。

在同一个 Mac 终端填写实际地址和用户名；备份放在项目目录之外：

```sh
RTAX86U_HOST='替换为已核对的AX86U地址'
RTAX86U_USER='admin'
RTAX86U_BACKUP_DIR="$HOME/Desktop/RTAX86U-Alpha3-backup-$(date +%Y%m%d-%H%M%S)"
umask 077
mkdir -p "$RTAX86U_BACKUP_DIR"
ssh "$RTAX86U_USER@$RTAX86U_HOST" 'test "$(nvram get productid)" = RT-AX86U || exit 40; nvram get firmver; nvram get buildno; nvram get extendno; df -k /jffs; mount; ls -ld /koolshare /jffs/.koolshare /opt'
```

将输出和 GUI 截图保存在私有备份目录；`/opt` 原本不存在须记录，不能据此忽略其他命令错误。确认输出确为当前 Alpha 3，再继续。主机密钥警告先核对设备，不能直接关闭校验。

将 GUI 导出的原 CFG 另存为该目录内的 `alpha3-settings.CFG`。导出旧数据库：

```sh
if ssh "$RTAX86U_USER@$RTAX86U_HOST" '/usr/bin/dbus listall' > "$RTAX86U_BACKUP_DIR/alpha3-dbus.txt.part"; then
  if [ -s "$RTAX86U_BACKUP_DIR/alpha3-dbus.txt.part" ]; then
    mv "$RTAX86U_BACKUP_DIR/alpha3-dbus.txt.part" "$RTAX86U_BACKUP_DIR/alpha3-dbus.txt"
  else
    echo '导出为空：停止，核查旧数据库' >&2
    false
  fi
else
  echo '导出失败：保留 part 文件排查，停止升级' >&2
  false
fi
```

确认逻辑导出成功后，停止旧中心。Alpha 3 原文件含 `perp.sh stop` 和 `stop_skipd` 入口；**实际停止效果必须在设备确认**：

```sh
ssh "$RTAX86U_USER@$RTAX86U_HOST" '/bin/sh -s' <<'ALPHA3_STOP'
set -e
[ "$(nvram get productid)" = RT-AX86U ]
/usr/bin/dbus list __alpha3_backup_barrier__ >/dev/null
/bin/sh /koolshare/perp/perp.sh stop || :
service stop_skipd
tries=10
while pidof skipd httpdb perpd perpboot >/dev/null 2>&1; do
  tries=$((tries-1))
  [ "$tries" -gt 0 ] || { echo '旧中心未停止：拒绝静态备份' >&2; exit 1; }
  sleep 1
done
sync
ALPHA3_STOP
```

必须检查 SSH 退出码为 0。上游 perp 脚本的返回码不足以证明停止，因此另核对进程；不强杀数据库。若进程复活、停止失败或仍有其他插件写入，暂停升级，先查明原因。

停止成功后归档整个 JFFS；使用 `.part` 避免把失败文件误当有效备份：

```sh
if ssh "$RTAX86U_USER@$RTAX86U_HOST" 'if pidof skipd httpdb perpd perpboot >/dev/null 2>&1; then echo "中心仍在运行" >&2; exit 1; fi; sync && tar -czf - -C /jffs .' > "$RTAX86U_BACKUP_DIR/alpha3-jffs.tar.gz.part"; then
  if gzip -t "$RTAX86U_BACKUP_DIR/alpha3-jffs.tar.gz.part" && tar -tzf "$RTAX86U_BACKUP_DIR/alpha3-jffs.tar.gz.part" > "$RTAX86U_BACKUP_DIR/alpha3-jffs-filelist.txt"; then
    mv "$RTAX86U_BACKUP_DIR/alpha3-jffs.tar.gz.part" "$RTAX86U_BACKUP_DIR/alpha3-jffs.tar.gz"
  else
    echo '归档校验失败：停止升级' >&2
    false
  fi
else
  echo 'SSH/tar 失败：停止升级，part 文件不是有效备份' >&2
  false
fi
```

### 3.3 备份完整性放行条件

逐项填写模板 B1–B5，**全部通过才进入下一阶段**：

1. CFG、DBus 和 JFFS 归档非空，SSH/tar/gzip 均成功。查看文件清单及 `tar -tvzf`，确认隐藏目录、旧数据库、插件配置、用户钩子、DNS、证书/密钥确实在内；与设备原有目录逐项对照，原本不存在的单独记录。
2. 若有 USB/外置插件，单独备份其目标数据；只有符号链接不是完整外置备份。确认电脑及第二份存储都空间足够。
3. 在备份目录生成校验，再在第二份独立副本中复核：

```sh
(cd "$RTAX86U_BACKUP_DIR" && test -s alpha3-settings.CFG && test -s alpha3-dbus.txt && test -s alpha3-jffs.tar.gz && shasum -a 256 alpha3-settings.CFG alpha3-dbus.txt alpha3-jffs.tar.gz > BACKUP_SHA256SUMS && shasum -a 256 -c BACKUP_SHA256SUMS)
```

该命令只列最低三项；实际插件导出、VPN 配置/密钥及外置归档也须加入校验清单，在第二份独立副本里重新核对。外置数据没有覆盖或校验项遗漏时，备份仍未放行。

4. 插件节点、VPN 私钥/配置和网络参数可在私有副本中核对。备份压缩包、CFG、DBus、订阅、证书和原始日志不上传公开仓库或 Release。
5. 写明“备份覆盖/可读性/双副本校验完成；整机还原演练尚未执行”。仅能打开压缩包，不能保证账号可迁移或整机可恢复。

若中止本次维护，在仍为 Alpha 3 且未隔离旧目录时，可通过 `service start_skipd`、`/bin/sh /koolshare/perp/perp.sh start` 恢复旧后台，核对服务和业务；已隔离时先按记录恢复原目录。不要让停用状态被误认为固件故障。

## 4. 停用与隔离旧扩展

备份放行后，在 Alpha 3 GUI 停用 VPN 自启、代理、DNS/广告过滤、自动重启、USB/JFFS 迁移等扩展；保存停用前截图。为首次启动隔离旧 `/jffs/scripts`、`/jffs/configs`，也检查 `.asusrouter`、额外启动命令、计划任务和 `/opt`。隔离目录名必须未占用，记录每个源与目的路径；不删除、不合并、不覆盖。

本指南不提供忽略实际目录状态的一键移动脚本。确认后将旧 `scripts/configs` 改名保存，再准备空的 `/jffs/scripts`、`/jffs/configs/dnsmasq.d`。**隔离后直接进行后续刷写；中止时先恢复原目录，不重启旧 Alpha 3 让初始化重新生成钩子。** 若需要先重启释放内存，应在隔离之前做，并在重启后重新停用服务、校验备份和隔离状态。

P7 的实际初始化策略如下，属于代码行为，尚非这台设备的实测结果：

| 原有内容 | P7 处理 / 验收要求 |
|---|---|
| `/jffs/.koolshare` | 首次迁移改名为 `.koolshare.pre-localmod`，复制新核心；不会自动移植旧插件 |
| `/jffs/.asusrouter` | 移到 `/jffs/.localmod/asusrouter.previous`，保留原链接或文件 |
| `/jffs/db` | 保留；P7 数据库另用 `/jffs/.localmod/ksdb`，不自动导入原配置 |
| `scripts/configs` | 不自动隔离；旧内容可能仍被执行或影响 DNS，须事前处理 |
| 旧归档、USB/Entware | 不因改名释放空间；不假设自动兼容或自动备份 |

若已有 `.koolshare.pre-localmod`、`.localmod/initialized`、`asusrouter.previous`、`plugin-txn/active` 或 `localmod-disabled`，先私下备份并查明来源，不删除标记强行重试。检查 JFFS 空间：初始化需要核心占用加 2 MiB；Fancyss 压缩包约 19 MiB、解压约 26 MiB，还需下载/事务检查点和现有数据余量，**不能把 20 MiB 空闲当作足够安装保证**。空间不足就暂停，不靠删 UU/旧备份腾空间。

## 5. 有线刷入与首次启动——未来维护窗口执行

1. 电脑接 LAN，关闭其他网络/VPN/代理，按已核对的实际 IP 登录。保持备用恢复工具可用。
2. Alpha 3 管理页“系统管理 → 固件升级 → 手动上传”，选择本批已校验的 P7 `.w`。[华硕手动升级界面说明](https://www.asus.com/support/faq/1008000/)只作操作参考，不表示官方支持本实验包。
3. **型号、签名、固件无效或降级拒绝即停止**，保存原提示。不要改后缀/头部、关闭校验、用 `mtd/dd` 或救援模式强刷 P7；未验证的直升路径不靠强制方式补齐。
4. 等待写入和自动重启，不断电、不按键、不重复提交。首次启动可预留约 10 分钟观察；超过时间先排查 LAN/IP/灯态，不能据此认定可以切断正在写入的电源。
5. 能稳定登录后先保存首次日志，再核对下面身份。管理页页头只显示梅林基础版本时，不以页头代替本地元数据。

**P7 SSH，只读：**

```sh
cat /rom/etc/localmod-release.json
cat /rom/etc/localmod-core-id
cat /jffs/.localmod/core-version
df -k /jffs
```

预期 `base=3004.388.13`、`variant=localmod-native-preview`、`revision=P7`、`software_center=1.9.60`、`status=NOT_FLASH_READY`。`/rom/etc/localmod-core-id` 和 `/jffs/.localmod/core-version` 均应为 `95b2436bb2ebc635f946a60517972119dd92ea44b201a8b2b424cfd33380180d`。身份或 core ID 不符就停止插件验收。`native-preview` 是这批构建的真实标识；不要套用旧 r4/r9 身份检查。P7 也不使用旧 r9 的六组件回退标记或旧 OpenVPN 自动兜底方案。

6. 核对备份后，通过 P7 GUI 执行恢复默认，再**手工**建立最小 LAN/WAN/Wi-Fi。不要上传 Alpha 3 `.CFG`、整份 JFFS、整份 DBus 或旧启动脚本。跨版本设置还原无兼容保证，这是本次跨 386→388 实验的清洁配置策略。[Merlin 安装说明](https://github.com/RMerl/asuswrt-merlin.ng/wiki/Installation)
7. 恢复默认/Initialize/JFFS 格式化清除范围不同；此轮默认不选格式化 JFFS、全部持久数据或附带数据清除选项，先核对实际界面与备份。恢复后重新检查旧归档和新核心是否仍在；如已丢失或状态不明，停止插件验收，先恢复基础联网和确认备份。[华硕重置范围说明](https://www.asus.com/support/faq/1035717/)
8. 建立强管理密码、所需管理端口/LAN SSH，核对时间/NTP、WAN、DHCP、DNS、2.4/5 GHz、必要 IPTV/IPv6。HTTPS 新证书/SSH 指纹改变时先核对正确设备与证书来源，不直接忽略告警。基础网络不通过就不安装插件。

首次验收固定本批 P7 固件；若界面有自动固件升级则停用，不从上游一键升级覆盖实验包。插件、内核程序和规则的定时更新也先暂停并记录版本，后续更新另做对应验收，避免一次测试中输入不断变化。

### 5.1 P7 HTTPS 与证书验收 H1–H3

在恢复默认、完成最小设置之后再记录本轮证书基线，不能要求证书与 Alpha 3 完全相同。

| 编号 | 操作与通过标准 |
|---|---|
| H1 首次 HTTPS | 时间/NTP 正确；浏览器用实际 LAN 主机名/IP 和端口登录。记录证书 SHA256 指纹、主体/SAN、签发者、有效期和证书来源。自签证书先核对设备与指纹；登录、页面脚本、软件中心查询均完整，无挂起或正文截断 |
| H2 保存和服务重启 | 若有正式使用的自有证书，通过原生界面导入并私下保存证书/私钥备份；否则记录本次自动生成证书。维护窗口从 SSH 执行一次 `service restart_httpd`，重新登录；未主动换证时指纹应与保存后的基线一致，管理页面与查询正常 |
| H3 整机重启恢复 | 正常 GUI 重启后重新核对证书指纹、设置、时间、登录和软件中心查询。若固件按所选证书模式有预期更新则核对来源和有效期；无配置变化却每次异常重建、证书丢失或 TLS 反复失败记失败 |

不删除现有证书或私钥来制造失败，不使用跳过证书验证的结果代替验收。错误时先保存时间、浏览器错误和系统日志，再区分时间/名称不匹配、旧密钥不兼容与服务异常。

## 6. 软件中心验收 S1–S7

| 检查 | 操作与通过标准 |
|---|---|
| S1 核心与迁移 | 登录后 `/Module_Softcenter.asp` 显示 1.9.60；新中心正常，旧插件未自动运行，旧归档与 `/jffs/db` 状态符合记录 |
| S2 登录与隔离 | 退出后隐私窗口访问 `/_localmod/status` 和 `/_api/softcenter_`，不能得到业务 JSON/执行写入。LAN 直接连 3032 失败；登录后正常。不能只看 HTTP 200/302 |
| S3 后台与事件 | 只存在预期单实例；3032 仅 loopback，保护规则存在，自定义脚本开关按预期启用。原生用户钩子与中心 helper 各一次，不用旧事件模拟命令冒充验证 |
| S4 配置持久化 | 无安装/设置写入时，测试键写入后立即 `restart_skipd`；另一次写入后立即 GUI 重启，值均保留；最后删除测试键 |
| S5 安装/更新 | 一个来源明确的 HND 轻量插件：安装、页面、实际功能、配置保存及重启通过；有可信两版本时再验证真实更新和配置保留 |
| S6 卸载 | 卸载后项目/页面/自有后台清理，其他插件、基础网络与 UU 正常；故障卸载保留现场，不假定配置必须全部删除 |
| S7 异常恢复 | 若自然发生安装/更新异常或 HTTP 423，保存日志/检查点，停止写入；正常重启后核对版本、配置和 UU 再重试，不删除 active、不拔电造故障 |

这里的“更新”指插件更新。首次验收保持软件中心核心为 1.9.60，不用通用仓库覆盖本批适配核心；软件中心自身升级需要另外核对兼容性，不与 S5 混作一项通过。

只读诊断：

```sh
pidof skipd
pidof httpdb
ps | grep '[l]ocalmod-event'
netstat -lnt | grep ':3032'
iptables -S LOCALMOD_API
iptables -S INPUT
nvram get jffs2_scripts
tail -n 60 /tmp/.localmod/bootstrap.log
```

`jffs2_scripts=0` 会抑制原生用户脚本和中心事件；先确认 GUI 设置及原意，再启用并重启复验。不要为测试覆盖用户脚本。电脑上可用 `curl --noproxy '*' --connect-timeout 3 'http://实际路由器LAN地址:3032/_api/softcenter_'` 检查直连应失败。

**以下会写一个测试键并重启数据库，只在空闲 P7 上执行：** 先确认测试键原本不存在；已占用则另选未使用的唯一键名，不覆盖已有值。每次写入与重启之间不读取测试键。

```sh
/usr/bin/dbus set localmod_p7_acceptance_probe=restart-test
service restart_skipd
/usr/bin/dbus get localmod_p7_acceptance_probe
```

预期 `restart-test`。另写 `localmod_p7_acceptance_probe=reboot-test` 后立即从 GUI 重启，不提前 `get`；重启读取须为 `reboot-test`，再 `/usr/bin/dbus remove localmod_p7_acceptance_probe`。同版/降级被正确跳过可单独记通过，但**不是完成真实版本更新**；没有可信适配更新包时标“更新未验证”。

## 7. 原厂 UU 优先验收 U1–U6

先不安装 Fancyss、不启用 VPN。使用与 Alpha 3 相同的账号权益、主机、游戏/区服和连接方式，比较“关闭 → 开启 → 再关闭”。[华硕 UU 说明](https://www.asus.com.cn/support/faq/1039538/)提供游戏加速页入口、登录、发现主机和加速流程；P7 本地只验证过自有测试工作进程。

| 检查 | 操作与通过标准 |
|---|---|
| U1 页面与官方跳转 | `/UUAccelerator.asp` 可打开，从前往设置进入网易官方服务；不泄露带设备标识的完整链接 |
| U2 登录与权益 | 能完成账号认证、识别有效权益；登录成功单独记录 |
| U3 主机识别 | 主机直连 LAN/主 Wi-Fi，核对 IP/MAC，无误识别；访客网、二级路由另作场景 |
| U4 真实加速 | 开启后实际联机 15–30 分钟，记录延迟/抖动、丢包、掉线和 NAT；停止后正常联网。页面“加速中”不是唯一证据，也不要求每次延迟都更低 |
| U5 重启/重连 | GUI 主动重启、另一次 WAN 断开/连接后，主机可重新发现并重新启用加速；是否需重新登录/手动启动如实记录 |
| U6 共存与回退 | 后续安装/重启/卸载插件及启停 VPN 后，按同条件重测 U3/U4；回退 Alpha 3 时再复测基线 |

入口缺失时只读查看 `nvram get productid`、`nvram get territory_code`、`nvram get sw_mode`、`nvram get rc_support` 和时间/NTP；P7 只给匹配大陆区域、路由模式的普通 AX86U 补充 UU 能力。**不改地区/MAC/型号伪造支持条件，不从第三方下载 UU 修补脚本。** 有进程不能证明账号/实际加速通过；无有效权益或游戏主机就标“未验证”，不能宣称原厂 UU 已完整验收。

## 8. Fancyss 安装、功能及卸载 F1–F6

1. **F1 安装且关闭**：从 `/Module_FancyssLocalmod.asp` 安装，或软件中心离线上传本批 `3.5.29_localmod2` 包。页面超时先看安装日志，不重复点击。安装结束保持代理关闭，核对中心、UU、JFFS 空间、共享 JQ 和基线网络。
2. **F2 配置与基本流量**：手工加入一个自有/授权测试节点，或经插件支持的导入路径逐项导入；先备份。用一个非游戏测试终端验证连通、预期出口和 DNS；IPv6、UDP、订阅更新等只在实际使用时分别测试并记录。不要直接覆盖旧 core/DBus。
3. **F3 关闭与恢复**：关闭 Fancyss 后，该测试终端恢复直连；原有 DNS、路由及 UU 正常。节点停用/上游不可用时验证所选模式是否按设定阻断或直连，不把故障时直连误认为代理正常。
4. **F4 重启与更新**：保存节点/策略后 GUI 重启，核对配置、预期自启、进程不重复。Release 只提供一个当前版本；没有另一批已验证适配包时，真实更新记未验证，不用上游自更新绕过事务/兼容检查。
5. **F5 卸载**：私下导出节点/配置后，在中心正常卸载；核对后台和页面、自有规则清理，以及 `/koolshare/bin/jq` 的共享链接/文件仍可服务其他依赖插件。可读 `ls -l /koolshare/bin/jq`、`/usr/bin/jq --version`，再测 UU、DNS 和中心。
6. **F6 重装及共存**：重装本批包，默认关闭，逐项恢复所需配置；完成下一节矩阵。卸载是否保留节点以实际插件行为为准，不能把“卸载”当作配置备份。

重点日志：`/tmp/upload/soft_install_log.txt`、`/tmp/upload/soft_log.txt` 以实际存在项为准；页面可从 `/_temp/soft_install_log.txt` 查看。不要把“请求已接受”当作安装已完成；校验/平台/低空间拒绝时停止，保留原因与副本。

## 9. 原生 VPN 与策略验收 V0–V5

P7 是完整原生框架，不能套用旧官方底包组件兼容开关。先单独验证一个实际会使用的 VPN 配置；页面存在、版本命令成功或显示“已连接”均不能替代真实流量。OpenVPN 2.7.8 / OpenSSL 3.5 的旧证书、静态密钥及压缩配置兼容性先按开头清单核对；若服务商暂不支持新配置，记录为兼容性失败，不通过降低全局 TLS 安全级别掩盖问题。

| 检查 | 操作与通过标准 |
|---|---|
| V0 旧配置兼容 | 确认 OpenVPN 2.7.8 / OpenSSL 3.5 可接受所用认证、证书/私钥与加密参数；旧静态密钥及已移除参数单独迁移，保留原配置 |
| V1 页面/配置/密钥 | 打开 OpenVPN 客户端、服务端、VPN Director、DNS Director 和状态页；保存非敏感标记、刷新回读。通过原生 UI 导入兼容配置和密钥；旧参数/加密不兼容时保留日志，按服务端能力调整，不盲目降低安全设置 |
| V2 客户端隧道 | 对自有/授权服务端验证认证、隧道地址、真实业务、预期出口、DNS/IPv6；断开恢复所选策略。拒绝错误凭据后能正常重试 |
| V3 VPN Director / DNS Director | 为一个测试终端和一个对照终端分配明确规则；分别核对出口、DNS、规则优先级及断线策略。保存后刷新、重启、WAN 重连复核 |
| V4 服务端 | 若实际使用服务端，从独立移动网络连接，验证认证、所需 LAN 资源、允许范围及断开清理；LAN 内自测不足以判定公网可达。运营商/上游入站限制单独记录 |
| V5 恢复与持久化 | 使用原生 UI 启停、一次 WAN 重连和一次主动重启；页面/日志、实际流量、预期自启、配置/证书保留一致；停用后无残留错误路由 |

只承诺已测试的协议/配置/服务商范围。共享资源目录含某协议页面，不表示 AX86U 实际启用了该协议；不把其他机型的专属功能写成已验收。无需使用的服务端或协议填“不适用”，并限制最终结论范围。

## 10. 四者共存与连续观察 C1–C7

准备 **游戏主机 G、Fancyss 测试终端 F、VPN 测试终端 V**。首轮将 G 从 Fancyss 代理和 VPN Director 路由匹配中明确排除，记录 DNS 策略；F、V 先分开，核对每台设备实际出口后再测试业务。不要默认 UU 会自动绕过代理/隧道。同一终端的叠加路由另作专门场景。

| 编号 | 组合 | 验收重点 |
|---|---|---|
| C1 | 基础 + 中心，无代理/VPN | 中心、查询、DNS/网络基线 |
| C2 | 中心 + UU | G 真实加速，中心状态与页面查询 |
| C3 | 中心 + Fancyss | F 流量、开关恢复、配置和 DNS |
| C4 | 中心 + VPN | V 流量、策略、断开恢复 |
| C5 | 中心 + UU + Fancyss | G 加速与 F 代理均符合各自预期，无出口/解析串线 |
| C6 | 中心 + UU + VPN | G 加速与 V 隧道分别正常 |
| C7 | 中心 + UU + Fancyss + VPN | G/F/V 出口与 DNS 正确，反复查询不截断；逐个服务启停、一次 WAN 重连后仍正确 |

组合通过后，在无关键业务的维护窗口正常执行一次 `service restart_softcenter`、原生 UI VPN/Fancyss 启停，再做一次 GUI WAN 重连；每项之后重测 UU 和业务。若需要验证防火墙重载，可在有线 LAN 管理下执行一次 `service restart_firewall`，随即检查 3032 隔离、`LOCALMOD_API`、UPnP 及实际业务；不清空防火墙、不手工运行测试 dispatch 冒充原生事件。

完成两次 GUI 主动重启，并在写入、安装、恢复均已结束且配置已保存后，执行一次正常冷启动 T4：先 `sync`，用设备电源键关机，待灯熄灭后再上电。重新核对 P7 身份、中心、证书、网络及 UU/Fancyss/VPN 的配置和预期自启。不在刷写或插件事务中断电造故障；未做冷启动时，该项记未验证。

随后观察至少 24 小时。建议在 0/5/15/30/60 分钟、6/24 小时记录时间、uptime、PID、RSS、FD、剩余 JFFS、掉线/重启次数和错误日志。比较同一进程生命周期；启动缓存和进程更换不能直接判泄漏。P7 已有一小时隔离共存结果，无需为阅读本指南或同步文档重跑 VM；首次实机观察是不同验证层级，不能由该报告替代，24 小时也不代表长期保证。

若计划使用 DDNS-Go，把它作为固定版本插件纳入 C7，并记录实际域名更新、只读查询和服务重启。P7 隔离长测中两个较长进程周期的 RSS 高点均为 18,032 KiB，期间有回落；这不是实机阈值，也不能证明无泄漏。实机保持配置与负载可比，按 PID/运行时长对照；不要用定时重启掩盖持续增长。此前 r7/r9 的不同环境结果不替代 P7 观测。

可选的 P7 只读采样示例，终端输出另存到电脑；未安装的服务不会列出，进程退出时读取报错需连同时间记录：

```sh
date
uptime
df -k /jffs
for RTAX86U_PID in $(pidof httpd skipd httpdb ddnsgo xray openvpn uuplugin uuplugin_monitor.sh); do
  echo "PID=$RTAX86U_PID"
  grep -E '^(Name|VmRSS|Threads):' "/proc/$RTAX86U_PID/status"
  ls "/proc/$RTAX86U_PID/fd" | wc -l
done
```

UU 的实际进程名和插件监督进程以设备 `ps` 输出为准；`pidof` 未命中不能代替运行/停止确认。只读采样按需补充真实 PID，不启动额外守护程序。

出现下列任一情况停止追加功能，保存证据并进入回退：私有 API 可从 LAN 读写；反复重启/配置丢失；JFFS 写满或检查点损坏；UU 明确在 Alpha 3 正常而 P7 同条件不可用；基础 DNS/路由持续异常。

## 11. 回退：先保数据，再按可访问程度处理

### R0 尚未刷机，只做了备份/隔离

保留电脑备份，按隔离记录恢复 Alpha 3 原目录（禁止合并覆盖）；恢复需要的插件/计划任务和原生服务，再核对中心及 UU 基线。恢复前后都记录，不能在目录来源不明时开机自启旧脚本。

### R1 P7 可登录，先停用中心适配止损

先停用 Fancyss、VPN 和其他插件，导出本次新配置与日志。空闲维护窗口在 **P7 SSH** 执行：

```sh
touch /jffs/localmod-disabled
service stop_softcenter
sync
```

确认数据库/中心停止，无安装任务，再执行 `service restart_httpd` 并重新登录；通过 GUI 正常重启使新进程不加载适配库。停止失败先查日志，不强杀 skipd。保留标记及全部数据，复核原生管理和网络。

**这不是回刷固件，也不保证撤销插件已改写的路由/DNS或所有用户脚本。** UU 必须重新实测。重新启用需查清故障后再移除标记并重启，不删除 `.localmod`、检查点、旧归档来“修复”。

### R2 P7 可管理，回到原 Alpha 3

1. 保存 P7 新数据/日志，停用插件、VPN、UU 加速，执行 R1；核对电脑端 Alpha 3 双副本和原固件哈希。
2. 记录当前 JFFS 实际目录，将 P7 活动核心、`.localmod`、当前 scripts/configs 及启动入口**分别改名归档到未占用目录**，不删原 Alpha 3 归档和 `/jffs/db`。不要保留会让 Alpha 3 执行 P7 核心的活动启动路径，也不把 Alpha 3 全量数据回灌到仍运行的 P7。目录状态不清楚就暂停，按 R3 恢复纯官方基础网络。
3. 只有已确认该设备及原包回刷要求时，才考虑正常管理页上传原 Alpha 3 整包 `.w`；此包含 CFE-ROM，不能仅以 GUI 未报错替代写入范围确认。如果要求不明或签名/型号/降级被拒绝，停止，不强刷带 CFE 的包；转 R3。不要假定曾能直升就必能直降。
4. 回到 Alpha 3 并核对版本后，先手工恢复最小联网，再在旧中心停止、无写入的维护状态恢复 Alpha 3 对应数据。软件中心暂未就绪可作为中间状态，不能因此在 P7 中先启动旧核心。
5. 恢复对应表如下：新目录先归档，再恢复，保留链接/权限；用户脚本和自启最后恢复。不要直接 `tar` 全量覆盖在线运行的 JFFS。

| Alpha 3 目标 | 正确来源 |
|---|---|
| `/jffs/.koolshare` | 已核验原 Alpha 3 电脑备份，或确认未变动的 `.koolshare.pre-localmod` |
| `/jffs/.asusrouter` | 原 Alpha 3 备份或归档的 `asusrouter.previous`；若归档被移动，按记录定位 |
| `/jffs/db` | 原 Alpha 3 数据库；不是 P7 的 `.localmod/ksdb` |
| `scripts/configs`、外置目录 | 对应原版本隔离/备份，逐项检查后恢复；USB 挂载和链接目标一并核对 |
| CFG / 节点 / VPN | CFG 仅作为回到同一 Alpha 3 后的恢复选项；节点、密钥按旧插件支持的路径恢复。需要重新登录 UU 时正常认证 |

6. 重启 Alpha 3，核对基础网络、旧中心、插件配置、自启及原 UU 游戏基线。P7 归档和原电脑备份保留到恢复确认；回刷成功不等于配置已还原。

### R3 管理页/SSH 不可用，救援回同型号纯官方

先排除连错网卡、DHCP/LAN 地址改变，确认没有写入仍在进行。按 [华硕救援流程](https://www.asus.com/support/faq/1000814/)准备的 Windows 电脑有线接 LAN：

1. 仅保留救援网卡，设 IPv4 `192.168.1.10`、掩码 `255.255.255.0`。
2. 关机后按住 **RESET** 上电，按该机型指示灯说明进入救援；普通 AX86U 观察电源灯闪烁。不同型号灯态可能不同，不把 WPS 按键当作救援键。
3. Firmware Restoration 选择解压后的同型号纯官方固件，等待上传、写入、设备重启完成，期间不断电。**救援用于回已知官方包，不用于绕过 P7/Alpha 3 的拒绝。**
4. 恢复电脑自动获取 IP/DNS，手工设置基础网络。工具反复拒绝、无救援灯态或无法恢复时保存错误并联系支持，不继续擦写分区/引导程序。

若需清除异常配置，RT-AX86U 在 [ASUS WPS 硬重置 Method 2](https://www.asus.com/support/faq/1039078/)适用列表：关机，按住 WPS 开机，电源灯熄灭后松开，再用电源键重启。**此项清配置；与 RESET 上电救援不同，只在写入已结束后考虑。** 不假定重置清除了全部 JFFS。官方包恢复后先保持纯净联网；再装回 Alpha 3 和还原旧数据是另一阶段，仍须通过型号/签名/备份检查。

## 12. 证据、验收结论与已验证边界

故障后在重启前导出系统日志，以及实际存在的 `/tmp/.localmod/bootstrap.log`、`events.log`、`skipd.log`、插件安装日志、VPN 原生日志和只读诊断。记录第一失败时间、此前动作、原始错误、PID/配置/路由变化；`/tmp` 日志重启会丢失。公开材料先去除账号、完整公网 IP/MAC、手机号、Cookie/token、节点/订阅、密钥；完整备份只私下保存。

P7 已有本地证据：[首次发布验证](https://github.com/fanxu1218/RT-AX86U/releases/download/localmod-native-38813-p7-experimental/P7-VALIDATION.md)、[首次门禁](merlin38813_local_gate.json)、[小时门禁](merlin38813_hour_gate.json)、[小时验证说明](merlin38813_hour_validation.md)及[原始长测数据](merlin38813_native_coexist_60m_tests.json)。同一 P7 镜像完成 3,603.9 秒、1,024 次正常查询、35 次计划异常/重启、127 次资源采样，零计划外失败，配置和 UU 合成数据保留。首次发布的五分钟门禁保留原字节，后补一小时报告单独记录；不复用 P6 的一小时作为 P7 证据。受控 UU 工作进程及隔离系统测试不等于实机原厂 UU 加速。

最终只可写“这台设备、这套网络、这些配置和协议在列明场景中通过”。备份未验证、UU 缺真实联机、Fancyss/VPN 未测或回退条件不具备时，不能写全部验收完成。**本文全部设备项目当前均为未执行。**
