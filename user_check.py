#!/usr/bin/env python3

import os
import sys
import typing as t
import argparse
import json
import socket

from datetime import datetime
from flask import Flask, jsonify

__author__ = '@DuTra01'
__version__ = '1.1.5'

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

        self.start_manager()

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

    def create_connection(self) -> socket.socket:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect(('localhost', self.port))
        return sock

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
        try:
            soc = self.create_connection()
            soc.send(b'status\n')

            data = b''
            buf = data

            while b'\r\nEND\r\n' not in buf:
                buf = soc.recv(1024)
                data += buf

            soc.close()
            count = data.count(username.encode())
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
        return count if count > -1 else self.count_connection_from_log(username)

    def kill_connection(self, username: str) -> None:
        soc = self.create_connection()
        soc.send(b'kill %s\n' % username.encode())
        soc.close()


class SSHManager:
    def count_connections(self, username: str) -> int:
        command = 'ps -u %s' % username
        result = os.popen(command).readlines()
        return len([line for line in result if 'sshd' in line])

    def get_pids(self, username: str) -> t.List[int]:
        command = 'ps -u %s' % username
        result = os.popen(command).readlines()
        return [int(line.split()[0]) for line in result if 'sshd' in line]

    def kill_connection(self, username: str) -> None:
        pids = self.get_pids(username)
        for pid in pids:
            os.kill(pid, 9)


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

    def kill_connection(self) -> None:
        self.ssh_manager.kill_connection(self.username)
        self.openvpn_manager.kill_connection(self.username)


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

    def include(self, name: str) -> bool:
        if name in self.exclude:
            self.exclude.remove(name)
            self.save_config()
            return True

        return False

    @property
    def port(self) -> int:
        return self.config.get('port', 5000)

    @port.setter
    def port(self, value: int):
        self.config['port'] = value
        self.save_config()

    def load_config(self) -> dict:
        default_config = {
            'exclude': [],
            'port': 5000,
        }
        try:
            if os.path.exists(self.path_config):
                with open(self.path_config, 'r') as f:
                    data = json.load(f)
                    return data if isinstance(data, dict) else default_config

        except Exception:
            pass

        return default_config

    def save_config(self, config: dict = None):
        self.config = config or self.config

        with open(self.path_config, 'w') as f:
            f.write(json.dumps(self.config, indent=4))

    @staticmethod
    def remove_config() -> None:
        if os.path.exists(CheckerUserConfig.PATH_CONFIG):
            os.system('rm -rf %s' % CheckerUserConfig.PATH_CONFIG)


class CheckerManager:
    RAW_URL_DATA = 'https://raw.githubusercontent.com/DuTra01/GLPlugins/master/user_check.py'

    EXECUTABLE_PATH = '/usr/bin/'
    EXECUTABLE_NAME = 'checker'
    EXECUTABLE_FILE = EXECUTABLE_PATH + EXECUTABLE_NAME

    @staticmethod
    def create_executable() -> None:
        of_path = os.path.join(os.path.expanduser('~'), 'chk.py')
        to_path = CheckerManager.EXECUTABLE_FILE

        if os.path.exists(to_path):
            os.unlink(to_path)

        print('Creating executable file...')
        print('From: %s' % of_path)
        print('To: %s' % to_path)

        os.chmod(of_path, 0o755)
        os.symlink(of_path, to_path)

    @staticmethod
    def get_data() -> str:
        import requests

        response = requests.get(CheckerManager.RAW_URL_DATA)
        return response.text

    @staticmethod
    def check_update() -> t.Union[bool, str]:
        data = CheckerManager.get_data()

        if data:
            version = data.split('__version__ = ')[1].split('\n')[0].strip('\'')
            return version != __version__, version

        return False, __version__

    @staticmethod
    def update() -> bool:
        if not CheckerManager.check_update():
            return False

        data = CheckerManager.get_data()
        if not data:
            return False

        with open(__file__, 'w') as f:
            f.write(data)

        CheckerManager.create_executable()
        return True

    @staticmethod
    def remove_executable() -> None:
        os.remove(CheckerManager.EXECUTABLE_FILE)


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

    def remove_service(self):
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
            os.system('systemctl enable %s' % self.CONFIG_SYSTEMD)


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


def kill_user(username: str) -> bool:
    try:
        checker = CheckerUserManager(username)
        checker.kill_connection()
        return True
    except Exception:
        return False


@app.route('/check/<string:username>')
def check_user_route(username):
    try:
        config = CheckerUserConfig()
        check = check_user(username)

        for name in config.exclude:
            if name in check:
                print('Exclude: %s' % name)
                del check[name]

        return jsonify(check)
    except Exception as e:
        return jsonify({'error': str(e)})


@app.route('/kill/<string:username>')
def kill_user_route(username):
    try:
        return jsonify({'success': kill_user(username)})
    except Exception as e:
        return jsonify({'error': str(e)})


def main():
    parser = argparse.ArgumentParser(
        description='Check user v%s' % __version__,
        prog=CheckerManager.EXECUTABLE_NAME,
    )
    parser.add_argument('-u', '--username', type=str)
    parser.add_argument('-p', '--port', type=int, help='Port to run server')
    parser.add_argument('--json', action='store_true', help='Output in json format')
    parser.add_argument('--run', action='store_true', help='Run server')
    parser.add_argument('--start', action='store_true', help='Start server')
    parser.add_argument('--stop', action='store_true', help='Stop server')
    parser.add_argument('--status', action='store_true', help='Check server status')
    parser.add_argument('--remove', action='store_true', help='Remove server')
    parser.add_argument('--restart', action='store_true', help='Restart server')

    parser.add_argument('--kill', action='store_true', help='Kill user')

    parser.add_argument('--update', action='store_true', help='Update server')
    parser.add_argument('--check-update', action='store_true', help='Check update')

    parser.add_argument('--exclude', type=str, nargs='+', help='Exclude fields')
    parser.add_argument('--include', type=str, nargs='+', help='Include fields')

    parser.add_argument('--uninstall', action='store_true', help='Uninstall server')
    parser.add_argument('--version', action='version', version='%(prog)s v' + str(__version__))

    args = parser.parse_args()
    config = CheckerUserConfig()
    service = ServiceManager()

    if not os.path.exists(CheckerManager.EXECUTABLE_FILE):
        CheckerManager.create_executable()
        print('Create executable success')
        print('Run: {} --help'.format(os.path.basename(CheckerManager.EXECUTABLE_FILE)))

    if args.username:
        if args.kill:
            if kill_user(args.username):
                print('Kill user success')
            else:
                print('Kill user failed')

        if args.json:
            print(json.dumps(check_user(args.username), indent=4))
            return

        print(check_user(args.username))

    if args.port:
        config.port = args.port

    if args.exclude:
        config.exclude = args.exclude

    if args.include:
        for name in args.include:
            config.include(name)

    if args.uninstall:
        service.remove_service()
        CheckerManager.remove_executable()
        CheckerUserConfig.remove_config()
        os.remove(__file__)

    if args.run:
        print('Run server...')
        print('Config: %s' % json.dumps(config.config, indent=4))
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
        service.remove_executable()
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
        is_update, version = CheckerManager.check_update()
        print('Have new version: {}'.format('Yes' if is_update else 'No'))
        print('Version: {}'.format(version))

        while is_update:
            response = input('Do you want to update? (Y/n) ')

            if response.lower() == 'y':
                CheckerManager.update()
                break

            if response.lower() == 'n':
                break

            print('Invalid response')

        return

    if len(sys.argv) == 1:
        parser.print_help()


if __name__ == '__main__':
    main()
