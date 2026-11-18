# LAN Proxy · 局域网代理

Cardputer Zero 的单配置 HTTP CONNECT / SOCKS5 客户端。界面默认英文，按右上角标示的 L 键可切换 English / 简体中文，应用会记住选择。

- Enter 连接或断开，E 编辑配置，Esc 返回启动器并保留连接。返回前会短暂提示后台运行或已断开。
- 配置页用 F/X 上下选项。协议用左右或 Enter 切换。其他字段用 Enter 开始或完成输入，输入时 F/X 是普通字母。Esc 保存并返回。
- 应用内显示后台运行状态。管理员版还会在启动器卡片上显示绿点，表示后台转发已开启。开机后需手动连接。
- 公网 IPv4 TCP 流量由 nftables 重定向给 redsocks。系统 DNS 通过代理发送到 Cloudflare DoH，失败时改用同一代理承载 TCP DNS。
- 局域网连接、广播和组播保持直连。连接期间拒绝公网普通 UDP 和 IPv6 TCP/UDP，浏览器可从 QUIC 回退到 TCP。此版本没有 SOCKS5 UDP 转发。连接前已建立的 TCP 会话沿用原路径，重开应用即可让新连接走代理。
- 连接时会测试上游和实际转发。重新打开应用时会检查公网 HTTPS 是否仍可通过代理访问。检查失败时可以手动断开恢复直连。

## 安装与维护

在 [GitHub Releases](https://github.com/tongfei11/LANProxy/releases/latest) 下载其中一个 ARM64 安装包：

| 版本 | Debian 包名 | 用途 |
| --- | --- | --- |
| 商店版 | `lan-proxy` | 非 root 后台，应用内显示状态，可提交商店预检。 |
| 管理员版 | `lan-proxy-admin` | 在启动器显示运行绿点。一个独立的 root 服务只更新本应用的 .desktop 图标，代理转发仍由非 root 后台处理。用于手动安装。 |

在 Cardputer Zero 的安装包目录运行 `sudo apt install ./lan-proxy_0.1.3_arm64.deb`，或替换成管理员版的文件名 `lan-proxy-admin_0.1.3_arm64.deb`。两个包互斥，切换版本时 APT 会替换旧包，并保留用户配置。也可以用同样方式从旧包 `zero-proxy` 迁移。

需要 Debian 13、Cardputer Zero 启动器，以及属于 `netdev` 组的启动器账户。两个版本均由 APT 安装 redsocks 等依赖。代理控制服务以非 root 用户运行，使用 `CAP_NET_ADMIN` 配置防火墙，回环端口为 TCP 42145 和 TCP/UDP 42153。

卸载当前版本使用 `sudo apt remove lan-proxy` 或 `sudo apt remove lan-proxy-admin`。卸载会停止代理并恢复直连，用户配置保留。

用户配置保存在 `~/.config/lan-proxy/config.json`。系统运行配置在 `/run/lan-proxy/redsocks.conf`，配置文件权限为 0600。断开或后台退出时删除本应用拥有的 `inet zproxy_lite` 防火墙表。

维护命令为 `sudo systemctl stop lan-proxy.service`，查看日志用 `sudo journalctl -u lan-proxy.service`。运行单元测试使用 `python3 -m unittest discover -v`。

在装有 dpkg 的 Linux 环境运行 `sh packaging/build-deb.sh store` 或 `sh packaging/build-deb.sh admin` 可重新构建安装包。设备上的源码安装脚本 `install.sh` 仅用于开发。
