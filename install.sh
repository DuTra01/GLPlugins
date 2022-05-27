#!/usr/bin/env bash

# Usage:
#   chmod +x install.sh
#   ./install.sh

# Created by: @DuTra01

url_check_user='https://raw.githubusercontent.com/DuTra01/GLPlugins/master/user_check.py'

function download_script() {
    if [[ -e chk.py ]]; then
        service user_check stop
        rm -r chk.py
    fi

    curl -sL -o chk.py $url_check_user
    chmod +x chk.py
    clear
}

function get_version() {
    local version=$(cat chk.py | grep -Eo "__version__ = '([0-9.]+)'" | cut -d "'" -f 2)
    echo $version
}

function check_installed() {
    if [[ -e /usr/bin/checker ]]; then
        clear
        echo 'CheckUser Ja esta instalado'
        read -p 'Deseja desinstalar? [s/n]: ' -n 1 -r choice

        if [[ $choice =~ ^[Ss]$ ]]; then
            service user_check stop 1>/dev/null 2>&1
            checker --uninstall 1>/dev/null 2>&1
            rm -rf chk.py 1>/dev/null 2>&1
            echo 'CheckUser desinstalado com sucesso'
        fi
    fi
}

function install() {
    local mode=$1

    if ! [ -f /usr/bin/python3 ]; then
        echo 'Installing Python3...'
        sudo apt-get install python3
    fi

    if [[ $mode == '--flask' && ! -x "$(command -v flask)" ]]; then
        echo 'Instalando flask..'
        sudo apt-get install python3-flask
    fi

    if ! [ -x "$(command -v flask)" ]; then
        echo 'Error: flask no instalado.' >&2
        read -p 'Deseja usar no modo socket? [s/n] ' mode
        [[ $mode != 's' ]] && mode='--socket'
    fi

    read -p 'Qual porta deseja usar?:' -e -i 5000 port

    python3 chk.py --create-service --create-executable --enable-auto-start --port $port --start $mode
}

function main() {
    check_installed
    download_script

    echo 'ChecUser v'$(get_version)
    echo ''
    echo '[01] - Modo Flask (Rest)'
    echo '[02] - Modo Socket'
    echo '[00] - Sair'

    read -p 'Escolha uma opção: ' choice

    case $choice in
    '01' | '1')
        install '--flask'
        rm -rf $0
        ;;
    '02' | '2')
        install '--socket'
        rm -rf $0
        ;;
    '00' | '0')
        exit 0
        ;;
    *)
        echo 'Opção inválida.'
        main
        ;;
    esac
}

main $@
