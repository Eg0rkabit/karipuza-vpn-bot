# Karipaza Froxy

Telegram-бот и Mini App для продажи и управления подписками Karipaza Froxy
через Remnawave.

## Возможности

- единое inline-меню без лишних сообщений;
- тарифы на 1, 3, 6 и 12 месяцев;
- оплата через ЮKassa в Mini App с запасным ручным режимом;
- автоматическое создание и продление подписки в Remnawave;
- ссылка и QR-код подписки для Happ;
- встроенная поддержка с обращениями и ответами администратора;
- админ-панель с платежами, пользователями и состоянием Remnawave;
- Telegram Mini App с главной страницей, новостями, тарифами и админскими действиями;
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
```

Несколько администраторов и групп указываются через запятую.

Поля для онлайн-оплаты через ЮKassa:

```env
YOOKASSA_SHOP_ID=
YOOKASSA_SECRET_KEY=
YOOKASSA_RETURN_URL=https://app.karipuza.ru
```

Пока эти значения пустые, оплата остаётся ручной: пользователь отправляет данные
платежа, администратор подтверждает заказ.

### Как подключить ЮKassa

Mini App создаёт платеж в ЮKassa, отправляет пользователя на страницу оплаты и
после webhook `payment.succeeded` автоматически выдаёт подписку в Remnawave.
Для включения нужны:

1. `shopId` магазина ЮKassa.
2. Секретный ключ API из личного кабинета ЮKassa.
3. HTTPS-адрес Mini App, обычно `https://app.karipuza.ru`.

В `.env`:

```env
YOOKASSA_SHOP_ID=ваш_shopId
YOOKASSA_SECRET_KEY=секретный_ключ
YOOKASSA_RETURN_URL=https://app.karipuza.ru
```

В личном кабинете ЮKassa в разделе HTTP-уведомлений добавьте:

```text
URL: https://app.karipuza.ru/api/yookassa/webhook
Событие: payment.succeeded
```

После изменения `.env` перезапустите сервис:

```bash
systemctl restart karipuza-bot
systemctl restart karipuza-webapp
```

Webhook для ЮKassa должен быть на HTTPS. У ЮKassa для HTTP-уведомлений подходят
порты `443` или `8443`, поэтому текущий домен Mini App на HTTPS подходит.

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

Администратор может отвечать на обращения двумя способами:

- в боте: `/admin` -> `Поддержка` -> нужное обращение -> `Ответить`;
- в Mini App: вкладка `Админ` -> блок открытых обращений -> написать ответ.

## Безопасный переход

Старый Marzban не удаляется до полной проверки новой схемы. Перед изменениями
нужна резервная копия, затем отдельно поднимаются Remnawave Panel и Node.
Переключение порта `443` выполняется только после успешного теста нового узла.
