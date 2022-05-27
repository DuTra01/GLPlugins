#!/usr/bin/env bash

# Usage:
#   chmod +x install.sh
#   ./install.sh

# Created by: @DuTra01


function install(){
    local mode=$1
    local url='https://raw.githubusercontent.com/DuTra01/GLPlugins/master/user_check.py'

    if [[ -e chk.py ]]; then
        service user_check stop
        rm -r chk.py
    fi

    curl -sL -o chk.py $url
    chmod +x chk.py
    clear

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

function main(){
    clear

    echo '[01] - Modo Flask (Rest)'
    echo '[02] - Modo Socket'
    echo '[00] - Sair'

    read -p 'Escolha uma opção: ' choice

    case $choice in
        '01'|'1')
            install '--flask'
            rm -rf $0
            ;;
        '02'|'2')
            install '--socket'
            rm -rf $0
            ;;
        '00'|'0')
            exit 0
            ;;
        *)
            echo 'Opção inválida.'
            main
            ;;
    esac
}

main $@