# Alpha 3 → localmod2：刷机、实机验收与回退

整理日期：2026-10-31。适用设备：**大陆销售的普通 RT-AX86U**；当前版本：`386.3_2 KoolCenter Alpha 3`；目标：`localmod2-r6-experimental`，基于 ASUS `3.0.0.4.388_24437`，软件中心 `1.9.50`。

**这是一份待执行的实验方案。直升/降级是否被设备接受、真实启动、软件中心及 UU 均未在这台路由器上验证。** 已通过的模型和镜像检查见[候选版说明](官改候选版说明.md)，不能替代下列实机项目。本文没有执行任何路由器命令。

推荐顺序：**备份并验证 → 隔离旧自定义项 → 有线手动刷入 → 重新设置基础网络 → 软件中心核心验收 → UU 单独验收 → 单个插件及共存验收 → 重启与持续观察**。使用[实机验收记录模板](localmod2实机验收记录模板.md)逐项记录；留空、跳过均不算通过。

## 1. 开始前准备

- 核对机身标签，不能使用 RT-AX86U Pro、RT-AX86S 或其他型号的包。记录原 LAN 地址、管理端口和登录用户名。
- 准备备用上网设备、稳定电源、网线；电脑接路由器 LAN 口。实验期间暂停其他家庭业务。先单机验证，暂不接入 AiMesh 节点、USB 存储或启用双 WAN。
- 在 Mac 上可用浏览器刷机；**救援备用方案需要预先准备可用的 Windows 电脑及有线网卡**。华硕 Firmware Restoration 官方要求 Windows。不要把未经验证的 Mac TFTP、虚拟机网络或“必定存在的 CFE 网页”当作已经具备的回退能力。[华硕救援说明](https://www.asus.com/support/faq/1000814/)
- 将目标固件、原 Alpha 3、纯官方恢复固件及本指南保存到电脑离线可用的位置。不要等路由器出故障后再下载。
- 保存宽带账号/密码、IPTV/VLAN、静态 IP、DHCP 保留、Wi-Fi、IPv6、端口转发等必要参数；UU 账号应能接收验证码。保管好配置备份中的密码、密钥和设备标识，不上传公开仓库。

### 固件身份

| 用途 | 文件 | SHA256 |
|---|---|---|
| 本次目标，85,721,108 字节 | `RT-AX86U_388_24437_localmod2_r6_EXPERIMENTAL.w` | `d2650339ea0868c472db0f25009642fcf23a5335a40fe2c6a6c3bae1b1cc37eb` |
| 刷回原 Alpha 3 | `RT-AX86U_386.3_2_cferom_pureubi_koolcenter_alpha3.w` | `c3d01f6df5916ab5f14a2dabd9c79b6d7c28c73b44bed122fdc2636568cf6838` |
| 纯官方恢复备用，已在本地核验的固定版本 | `RT-AX86U_3.0.0.4_388_24437-g81951d7_pureubi.w` | `de1caf609347beea394ebab956bddf0b391db592d1ad5f99e9d37e4d0b876af0` |

目标下载：[localmod2 发布页](https://github.com/fanxu1218/RT-AX86U/releases/tag/localmod2-r6-experimental)。纯官方包应从 [RT-AX86U 支持页](https://www.asus.com/hk/supportonly/rt-ax86u/helpdesk_bios?model2Name=RT-AX86U)取得；上表固定版本不表示当前最新推荐版本。若另选官方版本，须单独核验来源及型号，不套用此哈希。

Mac 终端，进入存放目标固件的目录后运行：

```sh
shasum -a 256 RT-AX86U_388_24437_localmod2_r6_EXPERIMENTAL.w
```

结果须与上表完全一致。上传解压后的 `.w` 文件，不能上传 ZIP、源码包或报告，也不要为了绕过拒绝而改扩展名、改头或关闭校验。原 Alpha 3 文件名含 `cferom`，**仅考虑正常管理页接受的整包回刷，不单独写 CFE/引导区**。

## 2. 先备份 Alpha 3，并建立对照

1. 在管理页“系统管理 → 恢复/导出/上传设置”导出配置文件；截图记录固件版本、网络设置和当前软件中心插件/版本。配置导出操作见[华硕说明](https://www.asus.com.cn/support/faq/1001376/)。**该文件不应当作 JFFS/插件的完整备份。**
2. 在仍运行 Alpha 3 时，用同一台游戏主机记录 UU 能否登录、发现主机、开始/停止加速，以及同游戏/区服的延迟、丢包和 NAT 类型。原版本也失败的项目，要先记录为基线问题。
3. 在软件中心停用插件，尤其是代理、DNS、广告过滤、USB/JFFS 迁移和自动重启类插件。暂停插件更新、定时任务与 UU 加速，避免备份期间持续改配置。
4. 开启仅 LAN 可访问的 SSH。备份整个 `/jffs`，特别包括隐藏目录、`/jffs/db`、`.koolshare`、`.asusrouter`、`scripts`、`configs`；同时保存插件自带的配置导出。

以下为可选的 Mac 备份命令。先替换地址和用户名；命令是在电脑运行，文件留在电脑，不额外占用 JFFS。逻辑导出后会停止旧中心后台和数据库，直到刷机完成前软件中心暂不可用；路由器管理页仍是刷机入口：

```sh
ROUTER_HOST=192.168.50.1  # 改成当前 LAN 地址
ROUTER_USER=admin         # 改成实际管理用户名
BACKUP="$HOME/Desktop/RTAX86U-Alpha3-backup-$(date +%Y%m%d-%H%M%S)"
umask 077
mkdir -p "$BACKUP"

ssh "$ROUTER_USER@$ROUTER_HOST" '/usr/bin/dbus listall' > "$BACKUP/alpha3-dbus.txt"
ssh "$ROUTER_USER@$ROUTER_HOST" '/usr/bin/dbus list __localmod_backup_barrier__ >/dev/null && sh /koolshare/perp/perp.sh stop && service stop_skipd'
```

在路由器 SSH 中检查 `pidof skipd` 和 `pidof httpdb` 均无输出后，再在同一个 Mac 终端继续。若仍有进程，先等正常退出再复查；无法停止或自行复活时暂停升级，不强杀数据库。下条命令也会拒绝对仍运行的数据库归档：

```sh
ssh "$ROUTER_USER@$ROUTER_HOST" 'if pidof skipd >/dev/null; then echo "数据库仍运行，停止备份" >&2; exit 1; fi; sync && tar -czf - -C /jffs .' > "$BACKUP/alpha3-jffs.tar.gz"
tar -tzf "$BACKUP/alpha3-jffs.tar.gz" > "$BACKUP/alpha3-jffs-filelist.txt"
shasum -a 256 "$BACKUP/alpha3-jffs.tar.gz" > "$BACKUP/alpha3-jffs.sha256"
```

**每条都须检查退出状态**；出现 SSH、tar、空间或权限错误就停止，不把空文件当成备份。检查列表中确实有隐藏目录、数据库和脚本，并将压缩包另存一份。`alpha3-dbus.txt` 是含敏感信息的逻辑导出，不能当 shell 脚本执行。

运行中数据库的文件备份不保证事务一致，因此先导出、正常停止，再保存文件。逻辑导出和插件自身备份也要保留。若存在持续写入、停止失败或无法导出，先解决备份问题；不要仅凭压缩包可打开就宣称可完整恢复。中止此次升级时，恢复旧目录后可用 Alpha 3 的 `service start_skipd` 及 `sh /koolshare/perp/perp.sh start` 恢复后台，并检查实际运行状态。

## 3. 隔离旧脚本、DNS 配置和迁移冲突

localmod2 首次迁移的实际行为是：

| Alpha 3 内容 | localmod2 的处理与首次验收要求 |
|---|---|
| `/jffs/.koolshare` | 改名为 `.koolshare.pre-localmod`，创建新核心；旧插件不会自动迁入 |
| `/jffs/db` | 保留，但新 skipd 使用 `/jffs/.localmod/ksdb`；旧插件配置不会自动导入 |
| `/jffs/.asusrouter` | 若存在，移到 `/jffs/.localmod/asusrouter.previous` |
| `/jffs/scripts` | 保留并可能执行；刷入前隔离旧钩子 |
| `/jffs/configs` | 保留；其中 DNS 配置可能直接影响启动和解析，刷入前隔离 |

备份完成后，在 **Alpha 3 的 SSH** 中执行下列隔离操作，选择一个未占用的目录名：

```sh
Q=/jffs/alpha3-before-localmod2-20261031
if [ -e "$Q" ]; then
  echo "隔离目录已存在，请停止并人工核对"
else
  mkdir -m 700 "$Q" &&
  { [ ! -e /jffs/scripts ] || mv /jffs/scripts "$Q/scripts"; } &&
  { [ ! -e /jffs/configs ] || mv /jffs/configs "$Q/configs"; } &&
  mkdir -p /jffs/scripts /jffs/configs/dnsmasq.d && sync
fi
```

检查原文件已完整进入隔离目录，新目录为空。若有 JFFS 挂载到 USB、Entware、额外启动入口或定时任务，还要停用对应功能；不能只移动这两个目录就假定所有旧扩展已关闭。**隔离后直接进行刷机；若中止升级，人工恢复隔离内容后再恢复旧功能。不要重启 Alpha 3 或重新运行旧初始化脚本，以免它重建钩子。**

用 `df -k /jffs` 查看空间，为新核心和日志预留余量，建议此次操作至少留 20 MiB；这是操作留量，不是固件保证。初始化还会校验新核心占用加 2 MiB。旧插件归档仍占空间，不会因改名释放容量。

若已存在 `.koolshare.pre-localmod`、`.localmod/initialized`、`.localmod/asusrouter.previous` 或 `localmod-disabled`，说明可能有前次尝试残留。先核对并备份其来源，**不要删除标记、覆盖备份或反复运行初始化来强行继续**。

## 4. 有线刷入及首次启动

1. 电脑保持连接 LAN 口，暂时关闭电脑 Wi-Fi、VPN/代理及其他网络接口，使用实际 LAN IP 登录。
2. 进入“系统管理 → 固件升级 → 手动上传”，选择已核验的 localmod2 `.w`。这是正常上传入口；[华硕手动升级说明](https://www.asus.com/support/faq/1008000/)供界面操作参考，并不构成华硕对官改包的支持。
3. 若提示固件/签名/型号无效，**停止此次升级**，保存原文和截图。直升接受性尚未验证；不要尝试 `mtd`、`dd`、改包或用救援模式强刷这个候选包。救援方案用于恢复已知的同型号官方包。
4. 上传及写入期间不拔电、不拔网线、不按 RESET，不重复上传。等页面完成并自动重启；首次启动给足约 10 分钟观察时间。这是排查观察窗，不是超过时间就可以断电的指令。
5. 管理页回到稳定可登录后，检查 `/Module_Localmod.asp`。SSH 中用下面的只读检查确认镜像身份，避免只看仍显示官方版本号的页头：

```sh
cat /rom/etc/localmod-release.json
cat /jffs/.localmod/core-version
cat /rom/etc/localmod-core-id
df -k /jffs
```

`variant` 应为 `localmod2`、`revision` 应为 `r4`，状态仍是 `EXPERIMENTAL_NOT_DEVICE_TESTED`；两个 core ID 应一致。先保存首次启动日志，再通过管理页恢复默认设置并**手工重建**最小网络；这是本次跨 386→388 的验收策略。不要将 Alpha 3 配置文件或整包 JFFS 导入 localmod2。

普通恢复出厂、WPS 硬重置、JFFS 格式化不是同一件事。若界面另有清除 JFFS/全部持久数据的选项，本次不要顺手勾选；先确认电脑备份和丢失范围。不要假定恢复出厂一定保留或一定清除 JFFS；重启后重新核对隔离目录、新核心和旧归档。

先只设置管理密码、LAN、WAN、2.4/5 GHz Wi-Fi 和必要 IPTV/VLAN。确认 DHCP、DNS、网页、NTP、IPv4/实际使用的 IPv6 正常，再继续插件和 UU。记录两次管理页主动重启是否恢复网络，不能用频繁拔电代替重启测试。

## 5. 软件中心验收

### A. 核心、认证和私有接口

| 检查 | 操作与通过标准 |
|---|---|
| 页面与版本 | 正常登录后进入 `/Module_Softcenter.asp`，显示 1.9.50；无白屏、循环登录或持续错误 |
| 旧插件隔离 | 新中心不自动出现/运行旧插件；旧归档和原 `/jffs/db` 仍存在。没有旧配置自动导入属于预期 |
| 列表与资源 | 在线列表、图标、详情可以加载；若失败，分别记录 DNS、时间、TLS/下载或接口错误 |
| 登录保护 | 退出登录后用隐私窗口访问 `/_api/softcenter_`，不能得到软件中心 JSON 数据或执行操作；重新登录后 UI 功能正常。不能只根据 HTTP 200/302 判断认证成功 |
| 私有服务隔离 | SSH `netstat -lnt` 应只见 `127.0.0.1:3032`；电脑直连路由器 LAN IP 的 3032 端口应失败 |
| 规则保护 | SSH `iptables -S LOCALMOD_API` 和 `iptables -S INPUT` 可见保护链与到该链的入口；WAN/防火墙重载后仍保留。不要为排查直接清空防火墙 |

可选只读诊断，均在 **localmod2 的 SSH** 运行：

```sh
pidof skipd
pidof httpdb
cat /tmp/.localmod/eventd.pid
ps | grep '[l]ocalmod-event'
netstat -lnt | grep ':3032'
iptables -S LOCALMOD_API
iptables -S INPUT
nvram get jffs2_scripts
tail -n 60 /tmp/.localmod/bootstrap.log
tail -n 60 /tmp/.localmod/events.log
```

应只有一套数据库/后台/事件守护进程，且没有反复重启。`jffs2_scripts` 为 `0` 会抑制用户钩子及软件中心事件分派；此时先查明是否人为关闭，再在管理页启用自定义脚本并重启验收，不能据此判插件兼容。

在 **Mac** 中测试私有端口，替换 LAN 地址：

```sh
curl --noproxy '*' --connect-timeout 3 'http://192.168.50.1:3032/_api/softcenter_'
```

应连接失败。若可读出数据，停止插件验收，保存规则与监听证据，进入第 8 节停用适配。

### B. 数据保留和真实插件

在没有安装插件、没有进行设置写入时，先验证数据库快速重启。以下会短暂重启数据库，在 **localmod2 的 SSH** 运行：

```sh
/usr/bin/dbus set localmod_acceptance_probe=restart-test
service restart_skipd
/usr/bin/dbus get localmod_acceptance_probe
```

返回应为 `restart-test`。不要在重启前插入 `get`，否则会掩盖待提交数据的问题。再运行 `/usr/bin/dbus set localmod_acceptance_probe=reboot-test`，立即从管理页主动重启；重新登录读取，值应保留为 `reboot-test`，最后清理测试键：

```sh
/usr/bin/dbus get localmod_acceptance_probe
/usr/bin/dbus remove localmod_acceptance_probe
```

UU 单独验收通过后，再选**一个当前支持 ASUS HND、来源和安装脚本可核对的轻量状态类插件**。先不选代理、改 DNS、USB/JFFS 迁移或防火墙接管插件。记录包来源、版本、平台与哈希。

1. 从新软件中心在线安装，或上传该插件的正式 HND 离线包；不复制 Alpha 3 的旧二进制和整个插件目录。
2. 验证安装日志完成、模块页面能打开、保存一个非敏感设置后刷新仍在，执行状态查询/启动停止有正确反馈。
3. 主动重启路由器，确认插件配置及预期自启保留，进程不重复；卸载后确认后台退出、页面和项目消失，再检查基础网络和 UU。
4. 核心版本保持 1.9.50；不要点软件中心核心升级、上传核心覆盖包或运行网上“一键重装中心”脚本。核心随本固件更新。

离线包报错时记录准确原因和退出结果，不换成另一平台强试。上轮构建中的测试插件不是已发布给用户的安装包，不能据其通过就宣布任意第三方插件可用。

## 6. UU 重点验收

先在**没有启用第三方插件**时测试，再检查与刚安装的单个插件共存。使用同一 UU 账号、同一台游戏主机、同一游戏/区服，并记录账号是否具备对应加速权益。

按[华硕 UU 官方说明](https://www.asus.com.cn/support/faq/1039538/)，从“游戏加速 → UU → 前往设置”进入官方页面，登录后选择局域网主机开始加速。此功能限定大陆销售支持机型。页面随官方服务变化，以实际官方入口为准，不从第三方网站下载补丁。

| 层级 | 操作 | 通过标准 |
|---|---|---|
| U1 入口 | 打开 `/UUAccelerator.asp`，点击前往设置，允许该入口弹出新窗口 | 正确进入网易官方域名；无空白跳转。链接带设备标识，分享截图时打码 |
| U2 账号 | 用短信验证码登录 | 可见正确账号/权益；登录成功不能代替加速成功 |
| U3 主机 | 主机直连路由器 LAN 或主 Wi-Fi，暂不接访客网络/另一层路由 | 识别的是本次测试主机，核对本地 IP/MAC；无串设备 |
| U4 实际加速 | 选游戏与区服开始加速，进游戏联机至少 15–30 分钟，再停止加速 | 服务显示状态与实际连通一致；停止后恢复普通联网，不残留异常路由 |
| U5 重启/重连 | 主动重启路由器；再做一次管理页 WAN 断开/连接 | UU 可重新发现主机并恢复或手动重启加速；记录是否需重新登录，不预先要求自动恢复 |
| U6 共存 | 启用一个已验收插件，再复测 U3/U4，并打开软件中心保存/查询设置 | 两者同时正常，管理页和其他设备网络稳定；卸载插件后仍正常 |

性能对比采用“关闭→开启→关闭”三组、每组约 10 分钟，至少记录平均延迟、抖动/高延迟峰值、丢包、NAT 类型及掉线。游戏服务器与时段会影响结果，**不要求每次延迟都更低，也不把测速吞吐或页面的‘加速中’作为唯一证据**。

UU 页面能打开但不能加速时，依次检查 WAN/DNS、系统时间与 NTP、账号权益/大陆机型资格、主机是否同一 LAN、官方服务错误、其他插件影响。官方实现包含联网取得运行组件的流程；保留 UU 页面不等于下载、运行和路由处理成功。不要伪造地区、修改 MAC/序列号或重复安装一套 UU 插件。

可保存 `ps | grep -i '[u]u'` 及系统日志中 UU/下载错误作为线索；进程名和目录以实际设备为准，不以某一个固定名字是否存在作为唯一判据。若仅 localmod2 失败而 Alpha 3 基线成功，保留同条件对照后按回退流程恢复。

## 7. 重载、重启和接受条件

- 在管理页执行一次 WAN 断开/连接，确认网络恢复、UU 能重新使用；检查 `events.log` 的 WAN/NAT/防火墙事件及软件中心插件状态。此操作会断网，保留有线 LAN 管理。
- 在没有外部业务时，从 SSH 运行 `service restart_firewall`，复查第 5 节的私有端口、保护链、管理页和 UU。若当前固件不接受该命令，记录失败，不能手工调用 `dispatch.sh` 来冒充真实事件通过。
- 完成至少两次管理页主动重启，比较配置、单实例和日志；需要 USB 插件时，另做安全弹出/重新挂载测试。没有测试的 USB、AiMesh、AP、双 WAN 场景标记“未验证”。
- 完成上述功能后，连续观察 24 小时：无异常重启、重复进程、内存持续增长、JFFS 写满、频繁断流或管理页卡死。24 小时是本次建议的观察周期，不是稳定性保证。

基础网络、核心认证/隔离、数据库持久化、插件实际工作及 UU U1–U6 全通过后，才能写“此设备、此网络、这些插件已验收”。某个第三方插件失败也不能直接归结为所有插件不兼容；记录准确范围。无游戏主机或有效权益时，UU 只能标记部分完成。

## 8. 回退：按可访问程度处理

### A. 系统还能进，仅软件中心/钩子异常

先把日志下载到电脑，再在 **localmod2 的 SSH** 执行：

```sh
touch /jffs/localmod-disabled
service stop_softcenter
service restart_httpd
sync
```

重新登录后检查 `pidof httpdb`、`pidof skipd` 应无对应进程，3032 应不再监听；保留标记，并通过管理页主动重启，使 rc/HTTPd 启动器不加载适配库。`stop_softcenter` 报错时先保存 `bootstrap.log`，不要用 `kill -9 skipd` 处理持久化故障。

这是**停用适配**，镜像仍是 localmod2，不会撤销插件已改写的其他设置或保证 UU 正常。需重新启用时，先查明故障，再移除这一标记并重启；不要删除 `.localmod` 数据目录来尝试修复。

### B. 能进管理页，要刷回 Alpha 3

1. 导出本次实验的日志和需要保留的新配置；执行 A，确认中心已经停止。全程只保留有线管理，先不要重启。
2. **先整理 JFFS 再回刷，不能只上传 Alpha 3 就假定旧环境全部复原。** 在停用状态下，将当前 `/jffs/.koolshare`、`/jffs/.localmod`、当前 `scripts`/`configs` 分别改名归档到另一个未占用目录，保留退出路径。不要直接覆盖或删除。
3. 若当初归档完整，按下表恢复 Alpha 3 对应项；若来源、符号链接或文件完整性不明，停止手工恢复，改用 C 的纯官方恢复路线。恢复旧目录后，localmod2 不再启动软件中心；保持 `localmod-disabled` 标记，直接回刷，不重启当前系统。

| Alpha 3 目标 | 从哪里恢复 | 注意 |
|---|---|---|
| `/jffs/.koolshare` | `.koolshare.pre-localmod` 改回原名，或电脑 Alpha 3 备份 | 先归档新核心，不合并两套目录 |
| `/jffs/.asusrouter` | 本次归档的 `.localmod/asusrouter.previous`，或原始备份 | 保留原符号链接及权限，不能复制 localmod 的入口 |
| `/jffs/scripts`、`/jffs/configs` | 第 3 节隔离目录，或原始备份 | 核对原用户文件；Alpha 3 初始化仍可能改写旧 DNS 配置 |
| `/jffs/db` | 原目录若完整则保留；否则使用原备份 | 不能把 `.localmod/ksdb` 当作 Alpha 3 数据库替换 |

4. 管理页上传已核验的原 Alpha 3 `.w`。若提示不支持降级、签名无效等，立即停止；**不强刷带 CFE 的文件**，转 C 恢复同型号官方包。
5. 等待写入和重启完成，核对确实回到 Alpha 3；必要时恢复默认并手工重建基础网络。旧 `.CFG` 只作为回到同一 Alpha 3 版本后的恢复选项，不能保证跨版本兼容。
6. 原 JFFS 若丢失，先在电脑检查备份结构，再在 Alpha 3 对应服务停止的维护状态选择性恢复，保留权限及链接；不要把整包 tar 在线覆盖到正在运行的中心，也不要在 localmod2 导入 Alpha 3 全量 DBus。
7. 检查旧软件中心与 UU 基线。localmod 的标记和归档可先保留；若以后再次升级，须重新核对迁移状态，不能拿旧 `initialized` 标记继续套用。

上述 JFFS 恢复涉及用户实际目录，本指南不提供忽略现状的一键覆盖命令。**配置文件、JFFS 备份、固件包三者用途不同；回刷成功不代表插件配置已恢复。**

### C. 管理页和 SSH 均不可用、无法正常启动

先排除电脑连错网卡、IP 改变及默认设置后的地址变化。没有写入任务正在进行时，使用华硕救援恢复**同型号纯官方固件**：

1. Windows 电脑有线接 LAN，断开其他网络；将此网卡设为 `192.168.1.10`、掩码 `255.255.255.0`。
2. 路由器断电，按住 **RESET** 同时接通电源，直到电源灯**慢闪**再松开，进入救援状态。
3. 打开 ASUS Firmware Restoration，选解压后的同型号官方固件，上传并等待工具完成、设备重启；期间不断电，不以普通 ping 超时判定写入失败。
4. 完成后将电脑网卡恢复自动获取 IP/DNS，重新查找路由器、手工配置基础网络。重复失败时保留工具错误并联系支持，不尝试擦写分区或更换引导程序。

以上依据[华硕救援流程](https://www.asus.com/support/faq/1000814/)。救援上传接受性在此设备上也未实测；它是预备恢复路径，不是可救回任意故障的保证。

若固件已恢复、但配置仍异常，可按 **RT-AX86U 适用的 WPS 硬重置 Method 2**：关机→按住 WPS 开机→继续按到电源灯熄灭→松开→用电源开关重启。此操作清除配置，依据[华硕型号/方法说明](https://www.asus.com/support/faq/1039078/)。**WPS 是重置配置，RESET 按住上电慢闪是救援，两者不要混用。**

恢复官方固件或重置配置不应被当作已经清理全部 JFFS。若仍有旧扩展残留，先在可访问系统中备份、查明实际入口，再使用对应固件明确提供的持久数据清理流程；不要直接执行 `rm -rf /jffs`。完全无法进入救援、灯态异常或反复失败时停止尝试，交由硬件维修处理。

## 9. 故障取证

出错后尽量在重启/恢复默认前保存：管理页“系统记录 → 一般记录文件”、`/tmp/.localmod/bootstrap.log`、`events.log`、`skipd.log`、`/tmp/upload/soft_log.txt`（若存在），以及上述只读诊断结果。`/tmp` 内容重启会丢失。日志导出界面参见[华硕说明](https://www.asus.com.cn/support/faq/1044954/)。

报告填写：固件哈希、重现步骤、是否清洁配置、插件版本、错误时间、预期/实际、UU 单独/共存结果及回退后的同条件对照。公开前去除公网 IP、完整 MAC/序列号、手机号、SSID、Cookie/token、账号及密钥；完整 JFFS、配置和 DBus 导出只保存在本地。

## r5 插件中断恢复验收补充

在实际升级、备份及基本联网验收完成后，另按 [插件安装中断恢复说明](插件安装中断恢复说明.md) 检查软件中心配置和 UU。当前任务没有操作路由器，不建议为验收直接拔电。若真实安装异常中断，先保留日志及事务目录，正常重启后确认旧插件配置、版本、自启和 UU，再重试安装；不要删除 active 检查点或清空 JFFS 来解除锁。虚拟磁盘结果不能替代实机 UBIFS 断电验证。

## r6 损坏与低空间处理补充

遇到封存校验或恢复空间错误时先保留全部副本，停止安装和设置写入。r6 不会为未知旧数据补算封存，也不会删除 UU/历史数据来腾空间；活动的 r5 未封存记录需人工核查。按 [恢复说明](插件安装中断恢复说明.md) 私下备份并从可信副本修复，或释放已确认可清理的空间，再正常重启。不要删除 active 来跳过校验。当前任务仍未连接或刷写路由器。
