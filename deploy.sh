#!/bin/bash
set -e

cd /opt/karipuza-bot

git pull

if [ ! -d "venv" ]; then
  python3 -m venv venv
fi

source venv/bin/activate
pip install -r requirements.txt

systemctl restart karipuza-bot
systemctl status karipuza-bot --no-pager
