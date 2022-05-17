#!/usr/bin/env bash

# Usage:
#   chmod +x install.sh
#   ./install.sh

# Created by: @DuTra01

url='https://raw.githubusercontent.com/DuTra01/GLPlugins/master/user_check.py'

if ! [ -x "$(command -v pip3)" ]; then
    echo 'Error: pip3 não está instalado.' >&2
    echo 'Instalando pip3...'

    sed -i '/mlocate/d' /var/lib/dpkg/statoverride
    sed -i '/ssl-cert/d' /var/lib/dpkg/statoverride
    apt-get update
    
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

if [[ -e chk.py ]]; then
    service user_check stop
    rm -r chk.py
fi

curl -sL -o chk.py $url
chmod +x chk.py
clear
read -p "Porta: " -e -i 5000 port

python3 chk.py --port $port --start
echo 'URL: http://'$(curl -s icanhazip.com)':'$port'/check/'
echo ''
echo 'Aplicativo na versão: 3.3+'
echo 'URL: http://'$(curl -s icanhazip.com)':'$port