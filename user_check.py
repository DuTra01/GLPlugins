#!/usr/bin/env python3

import os
import sys
import typing as t
import argparse
import json

from datetime import datetime
from flask import Flask, jsonify

__author__ = '@DuTra01'
__version__ = '0.0.2'

app = Flask(__name__)
app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
app.config['JSON_SORT_KEYS'] = False


class OpenVPNManager:
    def __init__(self, port: int = 7505):
        self.port = port
        self.config_path = '/etc/openvpn/'
        self.config_file = 'server.conf'
        self.log_file = 'openvpn.log'
        self.log_path = '/var/log/openvpn/'

    @property
    def config(self) -> str:
        return os.path.join(self.config_path, self.config_file)

    @property
    def log(self) -> str:
        path = os.path.join(self.log_path, self.log_file)
        if os.path.exists(path):
            return path

        self.log_path = 'openvpn-status.log'
        return os.path.join(self.config_path, self.log_file)

    def start_manager(self) -> None:
        if os.path.exists(self.config):
            with open(self.config, 'r') as f:
                data = f.readlines()

                management = 'management localhost %d\n' % self.port
                if management in data:
                    return

                data.insert(1, management)

            with open(self.config, 'w') as f:
                f.writelines(data)

            os.system('service openvpn restart')

    def count_connection_from_manager(self, username: str) -> int:
        self.start_manager()
        try:
            import socket as s

            soc = s.create_connection(('localhost', self.port), timeout=1)
            soc.send(b'status\n')
            data = soc.recv(8192 * 8).decode('utf-8')
            soc.close()

            count = data.count(username)

            return count // 2 if count > 0 else 0
        except Exception:
            return -1

    def count_connection_from_log(self, username: str) -> int:
        if os.path.exists(self.log):
            with open(self.log, 'r') as f:
                data = f.read()
                count = data.count(username)
                return count // 2 if count > 0 else 0
        return 0

    def count_connections(self, username: str) -> int:
        count = self.count_connection_from_manager(username)
        if count == -1:
            count = self.count_connection_from_log(username)
        return count


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
        if 'Active: active' not in status:
            os.system('systemctl start %s' % self.CONFIG_SYSTEMD)
            return True

        print('Service is already running')
        return False

    def stop(self):
        status = self.status()
        if 'Active: inactive' not in status:
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


class CheckerUserManager:
    def __init__(self, username: str):
        self.username = username
        self.ssh_manager = SSHManager()
        self.openvpn_manager = OpenVPNManager()

    def get_expiration_date(self) -> t.Optional[str]:
        command = 'chage -l %s' % self.username
        result = os.popen(command).readlines()

        for line in result:
            line = list(map(str.strip, line.split(':')))
            if line[0].lower() == 'account expires' and line[1] != 'never':
                return datetime.strptime(line[1], '%b %d, %Y').strftime('%d/%m/%Y')

        return None

    def get_expiration_days(self, date: str) -> int:
        if not isinstance(date, str) or date.lower() == 'never' or not isinstance(date, str):
            return -1

        return (datetime.strptime(date, '%d/%m/%Y') - datetime.now()).days

    def get_connections(self) -> int:
        return self.ssh_manager.count_connections(
            self.username
        ) + self.openvpn_manager.count_connections(self.username)

    def get_time_online(self) -> t.Optional[str]:
        command = 'ps -u %s -o etime --no-headers' % self.username
        result = os.popen(command).readlines()
        return result[0].strip() if result else None

    def get_limiter_connection(self) -> int:
        path = '/root/usuarios.db'

        if os.path.exists(path):
            with open(path) as f:
                for line in f:
                    split = line.strip().split()
                    if len(split) == 2 and split[0] == self.username:
                        return int(split[1].strip())

        return -1


class CheckerUserConfig:
    CONFIG_FILE = 'config.json'
    PATH_CONFIG = '/etc/checker/'

    def __init__(self):
        self.config = self.load_config()

    @property
    def path_config(self) -> str:
        path = os.path.join(self.PATH_CONFIG, self.CONFIG_FILE)

        if not os.path.exists(path):
            os.makedirs(self.PATH_CONFIG, exist_ok=True)

        return path

    @property
    def exclude(self) -> t.List[str]:
        return self.config.get('exclude', [])

    @exclude.setter
    def exclude(self, value: t.List[str]):
        self.config['exclude'] = value
        self.save_config()

    @property
    def port(self) -> int:
        return self.config.get('port', 5000)

    @port.setter
    def port(self, value: int):
        self.config['port'] = value
        self.save_config()

    def load_config(self) -> dict:
        try:
            if os.path.exists(self.path_config):
                with open(self.path_config, 'r') as f:
                    data = json.load(f)
                    return data if isinstance(data, dict) else {}

        except Exception:
            pass

        return {}

    def save_config(self, config: dict = None):
        self.config = config or self.config

        with open(self.path_config, 'w') as f:
            f.write(json.dumps(self.config, indent=4))


class CheckerManager:
    RAW_URL_DATA = 'https://raw.githubusercontent.com/DuTra01/GLPlugins/master/user_check.py'

    @staticmethod
    def create_executable() -> None:
        if not os.path.exists(__file__):
            return False
        
        of_path = os.path.join(os.path.dirname(__file__), __file__)
        to_path = os.path.join('/usr/bin', 'checker')

        if os.path.exists(to_path):
            os.unlink(to_path)
        
        os.chmod(of_path, 0o755)
        os.symlink(of_path, to_path)

    @staticmethod
    def get_data() -> str:
        import requests

        response = requests.get(CheckerManager.RAW_URL_DATA)
        return response.text

    @staticmethod
    def check_update() -> bool:
        data = CheckerManager.get_data()

        if data:
            version = data.split('__version__ = ')[1].split('\n')[0].strip('\'')
            return version != __version__

        return False

    @staticmethod
    def update() -> bool:
        if not CheckerManager.check_update():
            print('Not found new version')
            return False

        data = CheckerManager.get_data()
        if not data:
            print('Not found new version')
            return False

        with open(__file__, 'w') as f:
            f.write(data)

        print('Update success')
        CheckerManager.create_executable()
        return True

def check_user(username: str) -> t.Dict[str, t.Any]:
    try:
        checker = CheckerUserManager(username)

        count = checker.get_connections()
        expiration_date = checker.get_expiration_date()
        expiration_days = checker.get_expiration_days(expiration_date)
        limit_connection = checker.get_limiter_connection()
        time_online = checker.get_time_online()

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


@app.route('/check/<string:username>')
def check_user_route(username):
    try:
        config = CheckerUserConfig()
        check = check_user(username)

        for name in config.exclude:
            if check.get(name):
                del check[name]

        return jsonify(check)
    except Exception as e:
        return jsonify({'error': str(e)})


def main():
    parser = argparse.ArgumentParser(description='Check user')
    parser.add_argument('-u', '--username', type=str)
    parser.add_argument('-p', '--port', type=int, help='Port to run server')
    parser.add_argument('--json', action='store_true', help='Output in json format')
    parser.add_argument('--run', action='store_true', help='Run server')
    parser.add_argument('--start', action='store_true', help='Start server')
    parser.add_argument('--stop', action='store_true', help='Stop server')
    parser.add_argument('--status', action='store_true', help='Check server status')
    parser.add_argument('--remove', action='store_true', help='Remove server')
    parser.add_argument('--restart', action='store_true', help='Restart server')

    parser.add_argument('--update', action='store_true', help='Update server')
    parser.add_argument('--check-update', action='store_true', help='Check update')

    args = parser.parse_args()
    config = CheckerUserConfig()
    service = ServiceManager()

    if args.username:
        if args.json:
            print(json.dumps(check_user(args.username), indent=4))
            return

        print(check_user(args.username))

    if args.port:
        config.port = args.port

    if args.run:
        server = app.run(host='0.0.0.0', port=config.port)
        return server

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

    if args.restart:
        service.restart()
        return

    if args.update:
        is_update = CheckerManager.update()
        
        if is_update:
            print('Update success')
            return

        print('Not found new version')
        return

    if args.check_update:
        is_update = CheckerManager.check_update()
        print('Have new version: {}'.format('Yes' if is_update else 'No'))
        return


if __name__ == '__main__':
    main()
