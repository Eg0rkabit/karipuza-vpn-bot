# Karipaza Froxy

Telegram-бот, Mini App и Android-клиент для управления подписками Karipaza
Froxy через Remnawave.

## Возможности

- единое inline-меню без лишних сообщений;
- тарифы на 1, 3, 6 и 12 месяцев;
- подготовленные тарифы; онлайн-оплата через Platega будет добавлена позже;
- автоматическое создание и продление подписки в Remnawave;
- ссылка и QR-код подписки для Happ;
- встроенная поддержка с обращениями и ответами администратора;
- админ-панель с платежами, пользователями и состоянием Remnawave;
- Telegram Mini App с главной страницей, новостями, тарифами и админскими действиями;
- Android-приложение с входом через Telegram и системным VPN;
- защита от частого нажатия кнопок;
- подробные ошибки отправляются администраторам, пользователю показывается простой текст.

## Структура

```text
bot.py                    точка запуска
karipuza_bot/config.py    настройки и тарифы
karipuza_bot/database.py  SQLite: пользователи, заказы, тикеты
karipuza_bot/remnawave.py клиент API Remnawave
karipuza_bot/handlers.py  сценарии Telegram-бота
karipuza_bot/ui.py        тексты и клавиатуры
karipuza_bot/webapp.py    backend Telegram Mini App
karipuza_bot/web_static/  интерфейс Mini App
android-app/              нативный Android-клиент
```

## Настройка

```bash
cd /opt/karipuza-bot
cp .env.example .env
nano .env
```

Обязательные значения:

```env
BOT_TOKEN=токен_от_BotFather
ADMIN_IDS=ваш_telegram_id
REMNAWAVE_API_TOKEN=api_токен_из_Remnawave
REMNAWAVE_SQUAD_UUIDS=uuid_внутренней_группы
PAYMENT_DETAILS=реквизиты_для_оплаты
BOT_USERNAME=имя_бота_без_собаки
```

Несколько администраторов и групп указываются через запятую.

Онлайн-оплата сейчас намеренно выключена. Platega будет подключена после
получения тестовых ключей, точной API-документации и адресов webhook от
менеджера. Секретный ключ платёжной системы будет храниться только на VPS.

## Запуск

```bash
cd /opt/karipuza-bot
python3 -m venv venv
venv/bin/pip install -r requirements.txt
venv/bin/python bot.py
```

## systemd

```bash
cp systemd/karipuza-bot.service /etc/systemd/system/karipuza-bot.service
systemctl daemon-reload
systemctl enable --now karipuza-bot
systemctl status karipuza-bot --no-pager
```

Логи:

```bash
journalctl -u karipuza-bot -f
```

## Telegram Mini App

Для Mini App нужен отдельный HTTPS-поддомен:

```text
app.karipuza.ru -> A -> IP вашего VPS
```

После того как DNS-запись появилась:

```bash
cd /opt/karipuza-bot
git pull
bash scripts/deploy-mini-app.sh app.karipuza.ru
```

Скрипт поднимает сервис `karipuza-webapp`, получает TLS-сертификат через
Let's Encrypt, настраивает nginx и добавляет кнопку Mini App в меню Telegram-бота.

Логи Mini App:

```bash
journalctl -u karipuza-webapp -f
```

## Android

Приложение находится в `android-app/`. Оно не содержит API-токен Remnawave и не
получает открытую ссылку подписки. Пользователь подтверждает новое устройство в
Telegram, после чего backend выдаёт отдельный отзывной токен и проксирует только
его личную sing-box-конфигурацию.

APK собирается workflow `Android APK` в GitHub Actions. Первая версия использует
debug-подпись только для закрытого тестирования; перед публичной раздачей нужен
постоянный release-ключ.

Администратор может отвечать на обращения двумя способами:

- в боте: `/admin` -> `Поддержка` -> нужное обращение -> `Ответить`;
- в Mini App: вкладка `Админ` -> блок открытых обращений -> написать ответ.

## Безопасный переход

Старый Marzban не удаляется до полной проверки новой схемы. Перед изменениями
нужна резервная копия, затем отдельно поднимаются Remnawave Panel и Node.
Переключение порта `443` выполняется только после успешного теста нового узла.
