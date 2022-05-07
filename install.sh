#!/usr/bin/env bash

url='https://raw.githubusercontent.com/DuTra01/GLPlugins/master/user_check.py'

if ! [ -x "$(command -v pip3)" ]; then
    echo 'Error: pip3 não está instalado.' >&2
    echo 'Instale pip3 e execute o script novamente.' >&2
    
    if ! apt-get install -y python3-pip; then
        echo 'Erro ao instalar pip3' >&2
        exit 1
    else
        echo 'Instalado pip3 com sucesso'
    fi
fi

if ! [ -x "$(command -v flask)" ]; then
    echo 'Instalando flask'
    pip3 install flask
fi

curl -sL -o chk.py $url

read -p "Porta: " -e -i 5000 port

python3 chk.py --port $port --start