import json
import os
import sys
import platform
from datetime import datetime
import paramiko


def get_base_dir():
    """获取程序所在目录（兼容 PyInstaller 打包后的路径）"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    else:
        return os.path.dirname(os.path.abspath(__file__))


def load_config():
    """加载同目录下的 config.json"""
    base_dir = get_base_dir()
    config_path = os.path.join(base_dir, "config.json")

    if not os.path.exists(config_path):
        print(f"[错误] 找不到配置文件: {config_path}")
        print("请将 config.json 放在与 exe 相同的目录下。")
        sys.exit(1)

    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    return config


def collect(config):
    """通过 SSH 连接远程设备，逐条执行命令并收集输出"""
    ssh_conf = config["ssh"]
    output_conf = config["output"]
    commands = config["commands"]

    # 准备输出目录
    base_dir = get_base_dir()
    output_dir = os.path.join(base_dir, output_conf["directory"], ssh_conf["host"])
    os.makedirs(output_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{ssh_conf['host']}_{timestamp}.txt"
    output_file = os.path.join(output_dir, filename)

    print(f"目标设备: {ssh_conf['host']}")
    print(f"输出文件: {output_file}")
    print(f"采集项数: {len(commands)}")
    print("-" * 50)

    # === 核心兼容处理：适配旧版 ssh-rsa 签名与免密登录设备 ===
    try:
        if 'ssh-rsa' not in paramiko.transport.Transport._key_info:
            paramiko.transport.Transport._key_info['ssh-rsa'] = paramiko.RSAKey

        if "ssh-rsa" not in paramiko.transport.Transport._preferred_keys:
            paramiko.transport.Transport._preferred_keys = (
                    paramiko.transport.Transport._preferred_keys + ("ssh-rsa",)
            )
        if "ssh-rsa" not in paramiko.transport.Transport._preferred_pubkeys:
            paramiko.transport.Transport._preferred_pubkeys = (
                    paramiko.transport.Transport._preferred_pubkeys + ("ssh-rsa",)
            )

        paramiko.RSAKey.verify_ssh_sig = lambda self, data, msg: True
    except Exception as patch_err:
        print(f"[警告] 安全策略兼容补丁加载异常: {patch_err}")

    # 建立 SSH 连接
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        host = ssh_conf["host"]
        # 这里为了不暴露ssh的账号和端口号，不使用配置文件里的内容,这样配置文件里可以随便改。
        # port = ssh_conf["port"]
        # username = ssh_conf["username"]
        port = 9527
        username = "Demo"
        password = ssh_conf.get("password", "")

        # 使用底层 Transport 适配空密码 / none 认证
        transport = paramiko.Transport((host, port))
        transport.connect(username=username)

        try:
            # 优先尝试免密 none 认证
            transport.auth_none(username)
        except Exception:
            # 如果 none 认证失败，则回退到传入的密码（如为空则为 ""）
            transport.auth_password(username, password)

        client._transport = transport
        print(f"[OK] 已成功连接到设备 {host}")

    except Exception as e:
        print(f"[失败] SSH 连接失败: {e}")
        sys.exit(1)

    # 逐条执行命令并写入报告
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("=" * 50 + "\n")
        f.write("远程设备诊断报告\n")
        f.write(f"设备IP地址: {ssh_conf['host']}\n")
        f.write(f"采集时间: {datetime.now()}\n")
        f.write(f"采集工具: DeviceCollector v1.0\n")
        f.write("=" * 50 + "\n")

        for i, item in enumerate(commands, 1):
            title = item["title"]
            cmd = item["cmd"]

            print(f"  [{i}/{len(commands)}] {title} ...", end=" ")

            f.write(f"\n[{i}] {title}\n")
            f.write(f"命令: {cmd}\n")
            f.write("-" * 40 + "\n")

            try:
                _, stdout, stderr = client.exec_command(cmd, timeout=15)
                output = stdout.read().decode("utf-8", errors="ignore")
                error = stderr.read().decode("utf-8", errors="ignore")

                f.write(output)
                if error and error.strip():
                    f.write(f"\n[STDERR] {error}")

                print("OK")

            except Exception as e:
                f.write(f"[错误] 命令执行失败: {e}\n")
                print(f"失败 ({e})")

        f.write("\n" + "=" * 50 + "\n")
        f.write("采集完成\n")

    client.close()

    print("-" * 50)
    print(f"[完成] 报告已保存: {output_file}")

    # Windows 下自动打开报告所在目录
    if platform.system() == "Windows":
        os.startfile(output_dir)


if __name__ == "__main__":
    print("=" * 50)
    print("  DeviceCollector - 远程设备信息采集工具")
    print("=" * 50)
    print()

    config = load_config()
    collect(config)

    print()
    input("按回车键退出...")