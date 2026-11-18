# LAN Proxy · 局域网代理

Cardputer Zero 的单配置 HTTP CONNECT / SOCKS5 客户端。界面默认英文，按右上角标示的 L 键可切换 English / 简体中文，应用会记住选择。

- Enter 连接或断开，E 编辑配置，Esc 返回启动器并保留连接。返回前会短暂提示后台运行或已断开。
- 配置页用 F/X 上下选项。协议用左右或 Enter 切换。其他字段用 Enter 开始或完成输入，输入时 F/X 是普通字母。Esc 保存并返回。
- 启动器卡片用绿色角标表示后台运行。开机后需手动连接。
- 公网 IPv4 TCP 流量由 nftables 重定向给 redsocks。系统 DNS 通过代理发送到 Cloudflare DoH，失败时改用同一代理承载 TCP DNS。
- 局域网连接、广播和组播保持直连。连接期间拒绝公网普通 UDP 和 IPv6 TCP/UDP，浏览器可从 QUIC 回退到 TCP。此版本没有 SOCKS5 UDP 转发。连接前已建立的 TCP 会话沿用原路径，重开应用即可让新连接走代理。
- “代理运行中”表示后台服务存活。连接时会先测试上游，然后验证实际转发。此后上游掉线时可手动断开恢复直连。

## 安装与维护

在 Cardputer Zero 上下载 [最新 ARM64 .deb](https://github.com/tongfei11/LANProxy/releases/latest)，在安装包所在目录执行：

```sh
sudo apt install ./lan-proxy_0.1.1_arm64.deb
```

需要 Debian 13、Cardputer Zero 启动器和设备已有的免密 sudo。APT 安装 Debian 提供的 redsocks 等依赖。LAN Proxy 使用自己的 systemd 服务和配置，回环端口为 TCP 42145 和 TCP/UDP 42153。

卸载使用 `sudo apt remove lan-proxy`，会先停止代理并恢复直连。用户配置保留，便于重新安装时使用。

从旧包 `zero-proxy` 迁移时，用上面的 APT 命令安装新包，APT 会替换旧包。新版会读取原代理配置。

用户配置保存在 `~/.config/lan-proxy/config.json`。系统运行配置在 `/var/lib/lan-proxy/redsocks.conf`，配置文件权限为 0600。断开或后台退出时删除本应用拥有的 `inet zproxy_lite` 防火墙表。

维护命令为 `sudo systemctl stop lan-proxy.service`，查看日志用 `sudo journalctl -u lan-proxy.service`。运行单元测试使用 `python3 -m unittest discover -v`。

在装有 dpkg 的 Linux 环境运行 `sh packaging/build-deb.sh` 可重新构建安装包。设备上的源码安装脚本 `install.sh` 仅用于开发。
