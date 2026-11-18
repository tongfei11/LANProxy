"""English copy for the UI and for safe backend error messages."""
import re

EN = {
    '协议': 'Protocol',
    '代理地址': 'Proxy address',
    '端口': 'Port',
    '用户名（可选）': 'Username (optional)',
    '密码（可选）': 'Password (optional)',
    '局域网代理': 'LAN Proxy',
    '代理运行中': 'Proxy running',
    '读取状态…': 'Checking status…',
    '未连接': 'Disconnected',
    '未设置': 'Not set',
    '请先编辑配置': 'Set up the proxy first',
    '处理中…': 'Working…',
    'Enter 断开连接': 'Enter  Disconnect',
    'Enter 连接代理': 'Enter  Connect',
    'Enter 完成输入   Esc 保存返回': 'Enter Done    Esc Save & back',
    'F/X 上下   左右/Enter 切换   Esc 返回': 'F/X Move    Left/Right/Enter Toggle    Esc Back',
    'F/X 上下   Enter 编辑   Esc 保存返回': 'F/X Move    Enter Edit    Esc Save & back',
    'Esc 返回（保持连接）': 'Esc Back (keep connected)',
    'E 编辑配置    Esc 返回': 'E Edit settings    Esc Back',
    '连接失败': 'Connect failed',
    '断开失败': 'Disconnect failed',
    '保存失败': 'Save failed',
    '状态读取失败': 'Could not read status',
    '配置已保存': 'Settings saved',
    '代理继续在后台运行': 'Proxy stays active',
    '代理已断开': 'Proxy disconnected',
    '正在保存…': 'Saving…',
    '正在断开…': 'Disconnecting…',
    '正在连接…': 'Connecting…',
    '请先断开，再修改配置': 'Disconnect before editing settings',
    '无法保存语言设置': 'Could not save language preference',
    '无法写入配置，请检查存储空间或权限': 'Cannot write settings. Check storage and permissions.',
    '无法读取或控制代理服务': 'Cannot read or control the proxy service.',
    '设备操作超时，请稍后重试': 'The operation timed out. Try again.',
    '无法启动代理控制程序': 'Could not start the proxy controller.',
    '无法控制代理服务，请检查设备权限': 'Cannot control the proxy service. Check permissions.',
    '代理网络规则清理失败': 'Could not clear proxy firewall rules.',
    '代理网络规则已存在，无法启动': 'Proxy firewall rules already exist.',
    '代理 DNS 查询失败，请检查代理是否允许 HTTPS DNS': 'DNS failed. Check that the proxy allows DNS over HTTPS or TCP.',
    '代理已响应，但系统转发测试失败': 'Proxy responded, but the device traffic test failed.',
    '代理认证失败，请检查用户名和密码': 'Authentication failed. Check username and password.',
    '代理拒绝 HTTPS 转发，请检查服务端权限': 'Proxy refused HTTPS forwarding. Check its permissions.',
    '无法连接代理，请检查局域网、地址和端口': 'Cannot reach the proxy. Check the LAN, address and port.',
    '代理测试超时，请检查局域网和代理服务': 'Proxy test timed out. Check the LAN and proxy server.',
    'HTTPS 验证失败，请检查设备时间和代理服务': 'HTTPS verification failed. Check device time and proxy.',
    '代理握手失败，请核对 HTTP / SOCKS5 和端口': 'Proxy handshake failed. Check protocol and port.',
    '代理访问测试网站失败，请检查代理出口': 'The proxy could not reach the test site.',
    '需要系统权限': 'Administrator privileges are required.',
    '无效操作': 'Invalid operation.',
    '缺少 redsocks，请检查应用安装': 'redsocks is missing. Check the installation.',
    '代理服务已退出，请检查设备日志': 'Proxy service exited. Check device logs.',
    '代理服务启动失败，请检查设备日志': 'Could not start the proxy service. Check device logs.',
    '系统操作失败，请检查 lan-proxy 服务日志': 'System operation failed. Check the lan-proxy service logs.',
    '配置格式错误': 'Invalid settings format.',
    '请选择 HTTP 或 SOCKS5': 'Select HTTP or SOCKS5.',
    '请先填写代理地址': 'Enter the proxy address first.',
    '请填写局域网代理地址，不含协议或端口': 'Enter a LAN address without a protocol or port.',
    '端口须为 1–65535': 'Port must be between 1 and 65535.',
    '账号或密码格式错误': 'Invalid username or password format.',
    '无法解析代理地址，请检查域名或改填局域网 IP': 'Cannot resolve the proxy. Check its name or use a LAN IP.',
    '代理地址必须位于局域网 IPv4 网段': 'Proxy must have a private IPv4 address.',
}


def translate(message, language):
    if language != 'en':
        return message
    if message in EN:
        return EN[message]
    tunnel = re.fullmatch(r'代理无法建立 HTTPS 隧道（HTTP ([0-9]{3})）', message)
    if tunnel:
        return f'Proxy could not establish an HTTPS tunnel (HTTP {tunnel[1]}).'
    return message
