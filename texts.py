BTN_BUY = "🚀 Купить VPN"
BTN_MY_KEY = "🔗 Моя подписка"
LEGACY_BTN_MY_KEY = "🔑 Мой ключ"
BTN_PROFILE = "👤 Профиль"
BTN_INSTRUCTION = "📲 Инструкция"
BTN_SUPPORT = "💬 Поддержка"
BTN_MENU = "🏠 Главное меню"
BTN_ADMIN = "🛠 Админка"

WELCOME_TEXT = (
    "👋 <b>Karipuza VPN — быстрый доступ к свободному интернету</b>\n\n"
    "Подключение занимает пару минут: выберите тариф, получите ссылку подписки "
    "и добавьте её в Hiddify.\n\n"
    "Без сложных настроек, лишних действий и ожидания — всё можно сделать прямо через бота.\n\n"
    "Выберите действие в меню ниже:"
)

INSTRUCTION_TEXT = (
    "📲 <b>Инструкция подключения</b>\n\n"
    "1. Установите <b>Hiddify</b> из официального источника:\n"
    "• <a href=\"https://apps.apple.com/us/app/hiddify-proxy-vpn/id6596777532\">App Store</a> — iPhone / iPad\n"
    "• <a href=\"https://play.google.com/store/apps/details?id=app.hiddify.com\">Google Play</a> — Android\n"
    "• <a href=\"https://github.com/hiddify/hiddify-app\">Windows</a> — ПК\n"
    "2. В боте нажмите <b>🔗 Моя подписка</b>.\n"
    "3. Нажмите кнопку <b>📋 Скопировать подписку</b> или <b>📄 Показать подписку</b>.\n"
    "4. Откройте Hiddify.\n"
    "5. Нажмите <b>+</b>.\n"
    "6. Выберите импорт из буфера обмена.\n"
    "7. Подключитесь к профилю Karipuza.\n\n"
    "Если профиль уже добавлен, просто обновите его в Hiddify — новая подписка подтянет актуальные настройки.\n\n"
    "Если не подключается:\n"
    "• выключите другой VPN;\n"
    "• попробуйте мобильную сеть;\n"
    "• попробуйте другой Wi-Fi;\n"
    "• напишите в поддержку."
)

TARIFFS = {
    "trial_1d": {
        "title": "🧪 Тест 1 день",
        "days": 1,
        "price": "Бесплатно",
        "data_limit_gb": 0,
        "is_trial": True,
    },
    "month_1": {
        "title": "🚀 1 месяц",
        "days": 30,
        "price": "299 ₽",
        "data_limit_gb": 0,
        "is_trial": False,
    },
    "month_3": {
        "title": "🔥 3 месяца",
        "days": 90,
        "price": "799 ₽",
        "data_limit_gb": 0,
        "is_trial": False,
    },
    "month_6": {
        "title": "⭐ 6 месяцев",
        "days": 180,
        "price": "1499 ₽",
        "data_limit_gb": 0,
        "is_trial": False,
    },
    "year_1": {
        "title": "👑 1 год",
        "days": 365,
        "price": "2799 ₽",
        "data_limit_gb": 0,
        "is_trial": False,
    },
}
