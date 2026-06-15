# Переход на Remnawave

Переход разбит на этапы. До последнего этапа старый Marzban и VPN на порту
`443` продолжают работать.

Официальная документация рекомендует держать Remnawave Panel и Node на разных
серверах. Здесь используется временная схема на одном VPS, потому что сейчас
доступен только один сервер. Для неё добавляется swap, но при росте числа
пользователей панель лучше перенести на отдельный VPS.

## 1. Подготовить панель

На VPS:

```bash
cd /opt/karipuza-bot
git pull
bash scripts/prepare-remnawave-panel.sh sub.karipuza.ru
```

Скрипт поднимает Remnawave только на `127.0.0.1:3000`, добавляет swap при его
отсутствии и не меняет старый VPN.

На Windows открыть отдельное окно PowerShell:

```powershell
C:\Windows\System32\OpenSSH\ssh.exe -L 3000:127.0.0.1:3000 root@176.124.220.50
```

Пока это окно открыто, панель доступна по адресу:

```text
http://127.0.0.1:3000
```

## 2. Создать основу в панели

В Remnawave нужно создать:

1. администратора;
2. внутреннюю группу `Karipuza`;
3. профиль конфигурации;
4. узел на порту `2222`;
5. API-токен для бота.

На этом этапе нужен экран панели: названия полей могут отличаться между
версиями. Не переключайте порт `443`, пока узел не отображается как
подключённый.

## 3. Установить Node

После создания узла панель покажет `SECRET_KEY`. На VPS:

```bash
cd /opt/karipuza-bot
bash scripts/install-remnanode.sh 2222 'SECRET_KEY_ИЗ_ПАНЕЛИ'
```

В форме узла следует указать:

```text
address: remnanode
port: 2222
```

Порт управления Node доступен только внутри общей Docker-сети и не публикуется
в интернет.

## 4. Профиль VPN

Готовый профиль находится в:

```text
/opt/karipuza-bot/configs/remnawave-xray-profile.json
```

Его содержимое можно вставить в профиль конфигурации Remnawave. Новый Xray
inbound должен слушать только локально:

```text
listen inside Node: 0.0.0.0
port: 10000
protocol: VLESS
transport: WebSocket
path: /karipuza
security inside Xray: none
```

Docker публикует этот порт только как `127.0.0.1:10000` на VPS. TLS завершает
nginx на публичном порту `443`. В клиентской конфигурации хост должен быть
`sub.karipuza.ru`, порт `443`, transport `WebSocket`, security `TLS`, path
`/karipuza`.

## 5. Переключить порт 443

Только после того, как Node подключён и `127.0.0.1:10000` слушается:

```bash
cd /opt/karipuza-bot
CONFIRM_CUTOVER=YES bash scripts/cutover-remnawave.sh sub.karipuza.ru
```

При ошибке скрипт возвращает старый Marzban. При успехе старый контейнер
останавливается, но его файлы не удаляются.

## 6. Подключить бота

В `/opt/karipuza-bot/.env`:

```env
REMNAWAVE_URL=http://127.0.0.1:3000
REMNAWAVE_API_TOKEN=токен_из_панели
REMNAWAVE_SQUAD_UUIDS=uuid_группы_Karipuza
PAYMENT_DETAILS=реквизиты
```

Затем:

```bash
bash scripts/deploy-bot-v2.sh
```
