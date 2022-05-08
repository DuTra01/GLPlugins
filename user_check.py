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


def getSystemdUnitConfig() -> str:
    config = '''
[Unit]
Description=User check
After=network.target

[Service]
Type=simple
User=root
Group=root
ExecStart=%s %s --run

[Install]
WantedBy=multi-user.target
''' % (
        sys.executable,
        os.path.abspath(__file__),
    )
    return config


def create_service():
    path = '/etc/systemd/system/user_check.service'
    if os.path.exists(path):
        return

    with open(path, 'w') as f:
        f.write(getSystemdUnitConfig())

    command = 'systemctl daemon-reload'
    os.system(command)


def check_service() -> str:
    command = 'systemctl status user_check.service'
    result = os.popen(command).readlines()
    return ''.join(result)


def service_is_running() -> bool:
    result = check_service()

    for line in result.split('\n'):
        if 'Active: active' in line:
            return True

    return False


def start_service():
    if service_is_running():
        print('Service is already running')
        return

    create_service()
    command = 'systemctl start user_check.service'
    os.system(command)


def stop_server():
    if not service_is_running():
        print('Service is not running')
        return

    command = 'systemctl stop user_check.service'
    os.system(command)


def count_connection(username: str) -> int:
    command = 'ps -u %s' % username
    result = os.popen(command).readlines()
    return len([line for line in result if 'sshd' in line])


def count_connection_openvpn(username: str):
    count = 0
    path = '/var/log/openvpn/status.log'

    if not os.path.exists(path):
        path = '/etc/openvpn/openvpn-status.log'

    if not os.path.exists(path):
        return count

    with open(path) as f:
        for line in f:
            split = line.split(',')
            if len(split) > 2 and split[1] == username:
                count += 1

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
        count = count_connection(username) + count_connection_openvpn(username)
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

    if args.start:
        start_service()
        return

    if args.stop:
        stop_server()

    if args.status:
        print(check_service())


if __name__ == '__main__':
    main()
