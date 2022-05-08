import os
import sys
import typing as t
import argparse
import json

from datetime import datetime
from flask import Flask, jsonify

__author__ = '@DuTra01'
__version__ = '0.0.1'

app = Flask(__name__)
app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
app.config['JSON_SORT_KEYS'] = False


class OpenVPNManager:
    def __init__(self, port: int = 7505):
        self.port = port
        self.config_path = '/etc/openvpn/'
        self.config_file = 'openvpn.conf'
        self.log_file = 'openvpn.log'
        self.log_path = '/var/log/openvpn/'

    @property
    def config(self) -> str:
        return os.path.join(self.config_path, self.config_file)

    @property
    def log(self) -> str:
        return os.path.join(self.log_path, self.log_file)

    def count_connections(self, username: str) -> int:
        import socket as s

        try:
            soc = s.create_connection(('localhost', self.port), timeout=1)
            soc.send(b'status\n')
            data = soc.recv(8192 * 8).decode('utf-8')
            soc.close()
        except:
            if os.path.exists(self.config):
                with open(self.config, 'r') as f:
                    data = f.read()

        if data:
            count = data.count(username)
            return count // 2 if count > 0 else 0
        return 0


class SSHManager:
    def count_connections(self, username: str) -> int:
        command = 'ps -u %s' % username
        result = os.popen(command).readlines()
        return len([line for line in result if 'sshd' in line])


class ServiceManager:
    CONFIG_SYSTEMD_PATH = '/etc/systemd/system/'
    CONFIG_SYSTEMD = 'user_check.service'

    def __init__(self):
        self.create_systemd_config()

    @property
    def config(self) -> str:
        return os.path.join(self.CONFIG_SYSTEMD_PATH, self.CONFIG_SYSTEMD)

    def status(self) -> str:
        command = 'systemctl status %s' % self.CONFIG_SYSTEMD
        result = os.popen(command).readlines()
        return ''.join(result)

    def start(self):
        status = self.status()
        if 'Active: inactive' in status:
            os.system('systemctl start %s' % self.CONFIG_SYSTEMD)
            return True

        print('Service is already running')
        return False

    def stop(self):
        status = self.status()
        if 'Active: active' in status:
            os.system('systemctl stop %s' % self.CONFIG_SYSTEMD)
            return True

        print('Service is already stopped')
        return False

    def restart(self) -> bool:
        command = 'systemctl restart %s' % self.CONFIG_SYSTEMD
        return os.system(command) == 0

    def remove(self):
        os.system('systemctl stop %s' % self.CONFIG_SYSTEMD)
        os.system('systemctl disable %s' % self.CONFIG_SYSTEMD)
        os.system('rm %s' % self.config)
        os.system('systemctl daemon-reload')

    def create_systemd_config(self):
        config_template = ''.join(
            [
                '[Unit]\n',
                'Description=User check service\n',
                'After=network.target\n\n',
                '[Service]\n',
                'Type=simple\n',
                'ExecStart=%s %s --run\n' % (sys.executable, os.path.abspath(__file__)),
                'Restart=always\n',
                'User=root\n',
                'Group=root\n\n',
                '[Install]\n',
                'WantedBy=multi-user.target\n',
            ]
        )

        config_path = os.path.join(self.CONFIG_SYSTEMD_PATH, self.CONFIG_SYSTEMD)
        if not os.path.exists(config_path):
            with open(config_path, 'w') as f:
                f.write(config_template)

            os.system('systemctl daemon-reload')


def count_connection(username: str) -> int:
    count = SSHManager().count_connections(username)
    count += OpenVPNManager().count_connections(username)
    return count


def get_expiration_date(username: str) -> t.Optional[str]:
    command = 'chage -l %s' % username
    result = os.popen(command).readlines()

    for line in result:
        line = list(map(str.strip, line.split(':')))
        if line[0].lower() == 'account expires' and line[1] != 'never':
            return datetime.strptime(line[1], '%b %d, %Y').strftime('%d/%m/%Y')

    return None


def get_expiration_days(date: str) -> int:
    if not isinstance(date, str) or date.lower() == 'never' or not isinstance(date, str):
        return -1

    return (datetime.strptime(date, '%d/%m/%Y') - datetime.now()).days


def get_time_online(username: str) -> t.Optional[str]:
    command = 'ps -u %s -o etime --no-headers' % username
    result = os.popen(command).readlines()
    return result[0].strip() if result else None


def get_limiter_connection(username: str) -> int:
    path = '/root/usuarios.db'

    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                split = line.strip().split()
                if len(split) == 2 and split[0] == username:
                    return int(split[1].strip())

    return -1


def check_user(username: str) -> t.Dict[str, t.Any]:
    try:
        count = count_connection(username)
        expiration_date = get_expiration_date(username)
        limit_connection = get_limiter_connection(username)
        expiration_days = get_expiration_days(expiration_date)
        time_online = get_time_online(username)
        return {
            'username': username,
            'count_connection': count,
            'limit_connection': limit_connection,
            'expiration_date': expiration_date,
            'expiration_days': expiration_days,
            'time_online': time_online,
        }
    except Exception as e:
        return {'error': str(e)}


def create_config_file(port: int = 5000):
    path = os.path.join(os.path.expanduser('~'), 'config.json')
    exclude = []

    try:
        if os.path.exists(path):
            with open(path) as f:
                config = json.load(f)
                exclude = config.get('exclude', [])
    except:
        pass

    with open(path, 'w') as f:
        f.write(
            json.dumps(
                {
                    'port': port,
                    'exclude': exclude,
                },
                indent=4,
            )
        )


def load_config():
    path = os.path.join(os.path.expanduser('~'), 'config.json')
    with open(path) as f:
        return json.load(f)


def start_with_config(config: str):
    if not os.path.exists(config):
        raise Exception('Config file not found')

    config = load_config()
    app.run(host='0.0.0.0', port=config['port'])


@app.route('/check/<string:username>')
def check_user_route(username):
    try:
        config = load_config()
        exclude = config.get('exclude', [])

        check = check_user(username)

        for name in exclude:
            if check.get(name):
                del check[name]

        return jsonify(check)
    except Exception as e:
        return jsonify({'error': str(e)})


def main():
    parser = argparse.ArgumentParser(description='Check user')
    parser.add_argument('--username', type=str)
    parser.add_argument('--port', type=int, help='Port to run server')
    parser.add_argument('--json', action='store_true', help='Output in json format')
    parser.add_argument('--run', action='store_true', help='Run server')
    parser.add_argument('--start', action='store_true', help='Start server')
    parser.add_argument('--stop', action='store_true', help='Stop server')
    parser.add_argument('--status', action='store_true', help='Check server status')
    parser.add_argument('--remove', action='store_true', help='Remove server')

    args = parser.parse_args()

    if args.username:
        if args.json:
            print(json.dumps(check_user(args.username), indent=4))
            return

        print(check_user(args.username))

    if args.port:
        create_config_file(args.port)

    if args.run:
        start_with_config(os.path.join(os.path.expanduser('~'), 'config.json'))

    service = ServiceManager()

    if args.start:
        service.start()
        return

    if args.stop:
        service.stop()
        return

    if args.status:
        print(service.status())
        return

    if args.remove:
        service.remove()
        return


if __name__ == '__main__':
    main()
