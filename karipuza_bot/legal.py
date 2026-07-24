from __future__ import annotations

import html
from collections.abc import Iterable

from .config import TARIFFS, Settings

SERVICE_NAME = "Karipaza Froxy"
OPERATOR_NAME = "Администрация сервиса Karipaza Froxy"


def _escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def _support_contact(settings: Settings) -> tuple[str, str]:
    if settings.legal_support_contact:
        contact = settings.legal_support_contact
        if contact.startswith("@"):
            username = contact.lstrip("@")
            return contact, f"https://t.me/{username}"
        if "@" in contact and " " not in contact:
            return contact, f"mailto:{contact}"
        return contact, ""
    if settings.bot_username:
        username = settings.bot_username.lstrip("@")
        return f"тикет-система в Telegram-боте @{username}", f"https://t.me/{username}"
    return "тикет-система в разделе «Поддержка» Telegram-бота", ""


def _tariff_rows() -> str:
    return "".join(
        (
            "<tr>"
            f"<td>{_escape(tariff.title)}</td>"
            f"<td>{tariff.days} дней</td>"
            f"<td>{tariff.price_rub} ₽</td>"
            "<td>без ограничения трафика</td>"
            "</tr>"
        )
        for tariff in TARIFFS
    )


def _navigation(active: str) -> str:
    links = (
        ("documents", "/documents", "Документы"),
        ("privacy", "/privacy", "Конфиденциальность"),
        ("terms", "/terms", "Соглашение"),
    )
    return "".join(
        f'<a class="{"active" if key == active else ""}" href="{url}">{label}</a>'
        for key, url, label in links
    )


def _section(title: str, paragraphs: Iterable[str], list_items: Iterable[str] = ()) -> str:
    body = "".join(f"<p>{paragraph}</p>" for paragraph in paragraphs)
    items = list(list_items)
    if items:
        body += "<ul>" + "".join(f"<li>{item}</li>" for item in items) + "</ul>"
    return f"<section><h2>{title}</h2>{body}</section>"


def _page(
    settings: Settings,
    *,
    title: str,
    active: str,
    description: str,
    body: str,
) -> str:
    operator = _escape(OPERATOR_NAME)
    effective_date = _escape(settings.legal_effective_date)
    support_text, support_url = _support_contact(settings)
    support = _escape(support_text)
    support_action = (
        f'<a class="button" href="{_escape(support_url)}">Открыть поддержку</a>'
        if support_url
        else ""
    )
    return f"""<!doctype html>
<html lang="ru">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <meta name="theme-color" content="#101419" />
    <meta name="description" content="{_escape(description)}" />
    <title>{_escape(title)} — {SERVICE_NAME}</title>
    <style>
      :root {{
        color-scheme: light;
        font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont,
          "Segoe UI", sans-serif;
        color: #17202a;
        background: #eef2f5;
      }}
      * {{ box-sizing: border-box; }}
      body {{ margin: 0; min-width: 280px; line-height: 1.6; }}
      header {{ color: #f7fafb; background: #101419; border-bottom: 3px solid #178e93; }}
      .header-inner, main, footer {{ width: min(880px, calc(100% - 32px)); margin: 0 auto; }}
      .header-inner {{ padding: 24px 0 20px; }}
      .brand {{ display: flex; align-items: center; gap: 12px; }}
      .brand img {{ width: 48px; height: 48px; object-fit: cover; border-radius: 8px; }}
      .brand strong {{ display: block; font-size: 20px; }}
      .brand span {{ display: block; color: #afbbc5; font-size: 13px; }}
      nav {{ display: flex; gap: 6px; margin-top: 18px; overflow-x: auto; }}
      nav a {{ color: #cbd4db; text-decoration: none; padding: 7px 9px; border-radius: 6px; white-space: nowrap; }}
      nav a.active {{ color: #fff; background: #1f6368; }}
      main {{ padding: 32px 0 44px; }}
      .intro {{ padding-bottom: 24px; border-bottom: 1px solid #cbd4db; }}
      .eyebrow {{ margin: 0 0 6px; color: #13777c; font-size: 13px; font-weight: 800; }}
      h1 {{ margin: 0; font-size: clamp(28px, 6vw, 42px); line-height: 1.15; letter-spacing: 0; }}
      .lead {{ max-width: 720px; margin: 12px 0 0; color: #52616d; }}
      section {{ padding: 24px 0; border-bottom: 1px solid #d4dce2; }}
      h2 {{ margin: 0 0 10px; font-size: 21px; line-height: 1.3; letter-spacing: 0; }}
      p {{ margin: 8px 0; }}
      ul {{ margin: 10px 0 0; padding-left: 22px; }}
      li + li {{ margin-top: 5px; }}
      a {{ color: #086b70; }}
      .notice {{ margin-top: 24px; padding: 14px; border: 1px solid #9bb8ba; border-radius: 8px; background: #f7fbfb; }}
      .button {{ display: inline-flex; margin-top: 10px; padding: 9px 12px; border-radius: 6px; color: #fff; background: #13777c; text-decoration: none; font-weight: 700; }}
      .table-wrap {{ margin-top: 14px; overflow-x: auto; border: 1px solid #ccd5dc; border-radius: 8px; }}
      table {{ width: 100%; min-width: 580px; border-collapse: collapse; background: #f8fafb; }}
      th, td {{ padding: 11px 12px; text-align: left; border-bottom: 1px solid #dbe2e7; }}
      th {{ color: #40505d; background: #e5ebef; font-size: 13px; }}
      tr:last-child td {{ border-bottom: 0; }}
      footer {{ padding: 22px 0 34px; color: #667581; font-size: 13px; border-top: 1px solid #cbd4db; }}
      @media (max-width: 520px) {{
        .header-inner, main, footer {{ width: min(100% - 24px, 880px); }}
        .header-inner {{ padding-top: 18px; }}
        main {{ padding-top: 24px; }}
      }}
    </style>
  </head>
  <body>
    <header>
      <div class="header-inner">
        <div class="brand">
          <img src="/assets/logo.png?v=20260723-brand2" alt="" />
          <div><strong>{SERVICE_NAME}</strong><span>Официальная информация сервиса</span></div>
        </div>
        <nav aria-label="Документы">{_navigation(active)}</nav>
      </div>
    </header>
    <main>
      <div class="intro">
        <p class="eyebrow">Редакция от {effective_date}</p>
        <h1>{_escape(title)}</h1>
        <p class="lead">{_escape(description)}</p>
      </div>
      {body}
      <div class="notice">
        <strong>Поддержка</strong>
        <p>{support}. Обращение регистрируется в системе, ответ приходит пользователю в Telegram.</p>
        {support_action}
      </div>
    </main>
    <footer>
      {operator}. {SERVICE_NAME}. Актуальная редакция от {effective_date}.
    </footer>
  </body>
</html>"""


def documents_page(settings: Settings) -> str:
    body = (
        _section(
            "Информация для пользователя",
            (
                "Перед оформлением подписки ознакомьтесь с условиями сервиса, "
                "правилами обработки данных и действующими тарифами.",
            ),
            (
                '<a href="/privacy">Политика конфиденциальности</a> — какие данные '
                "обрабатываются и для чего.",
                '<a href="/terms">Пользовательское соглашение</a> — условия услуги, '
                "оплаты, использования и возврата.",
            ),
        )
        + _section(
            "Тарифы",
            (
                "Стоимость фиксируется до оформления заказа. Один тариф предоставляет "
                "доступ на указанный срок без ограничения объёма трафика.",
            ),
        )
        + f'<div class="table-wrap"><table><thead><tr><th>Тариф</th><th>Срок</th><th>Цена</th><th>Трафик</th></tr></thead><tbody>{_tariff_rows()}</tbody></table></div>'
    )
    return _page(
        settings,
        title="Документы и тарифы",
        active="documents",
        description="Постоянный раздел с условиями сервиса Karipaza Froxy.",
        body=body,
    )


def privacy_page(settings: Settings) -> str:
    operator = _escape(OPERATOR_NAME)
    body = "".join(
        (
            _section(
                "1. Общие положения",
                (
                    f"Настоящая Политика определяет порядок обработки информации "
                    f"пользователей сервиса {SERVICE_NAME}, включая Telegram-бота и Mini App.",
                    f"Ответственным за обработку данных является {operator}. Используя "
                    "сервис, пользователь подтверждает ознакомление с Политикой.",
                ),
            ),
            _section(
                "2. Какие данные обрабатываются",
                (
                    "Сервис обрабатывает только сведения, необходимые для работы подписки, "
                    "поддержки и оплаты.",
                ),
                (
                    "Telegram ID, имя, username и сведения, переданные Telegram;",
                    "выбранный тариф, срок и состояние подписки, история заказов;",
                    "сумма, статус и идентификатор платежа, переданные платёжным провайдером;",
                    "сообщения и вложения, отправленные в поддержку;",
                    "технические журналы: IP-адрес, время запроса, тип устройства, браузер и ошибки.",
                ),
            ),
            _section(
                "3. Цели обработки",
                (),
                (
                    "создание, продление и обслуживание подписки;",
                    "проведение и подтверждение платежей;",
                    "обработка обращений и связь с пользователем;",
                    "обеспечение безопасности, предотвращение злоупотреблений и диагностика сбоев;",
                    "исполнение требований применимого законодательства.",
                ),
            ),
            _section(
                "4. Передача данных",
                (
                    "Данные могут передаваться Telegram, платёжному провайдеру Platega, "
                    "поставщику серверной инфраструктуры и иным обработчикам только в объёме, "
                    "необходимом для оказания услуги. Передача также возможна по законному "
                    "требованию уполномоченных органов.",
                    "Полные реквизиты банковской карты и данные банковского счёта сервисом "
                    "не запрашиваются. Их обработка выполняется на стороне платёжного провайдера.",
                ),
            ),
            _section(
                "5. Хранение и защита",
                (
                    "Информация хранится не дольше, чем это необходимо для указанных целей, "
                    "рассмотрения обращений и выполнения обязательных требований. Применяются "
                    "разумные организационные и технические меры защиты, но абсолютная "
                    "безопасность передачи данных через интернет не может быть гарантирована.",
                ),
            ),
            _section(
                "6. Права пользователя",
                (
                    "Пользователь может запросить сведения об обработке, исправление или "
                    "удаление своих данных через тикет-систему поддержки. Удаление может быть "
                    "ограничено, если хранение требуется законом или необходимо для разрешения "
                    "спора и подтверждения платежа.",
                ),
            ),
            _section(
                "7. Изменения Политики",
                (
                    "Актуальная редакция постоянно размещена на этой странице. Существенные "
                    "изменения применяются с даты публикации новой редакции.",
                ),
            ),
        )
    )
    return _page(
        settings,
        title="Политика конфиденциальности",
        active="privacy",
        description="Правила обработки и защиты данных пользователей Karipaza Froxy.",
        body=body,
    )


def terms_page(settings: Settings) -> str:
    operator = _escape(OPERATOR_NAME)
    tariffs = (
        '<div class="table-wrap"><table><thead><tr><th>Тариф</th><th>Срок</th>'
        f"<th>Цена</th><th>Трафик</th></tr></thead><tbody>{_tariff_rows()}</tbody></table></div>"
    )
    body = "".join(
        (
            _section(
                "1. Предмет соглашения",
                (
                    f"Настоящее Соглашение регулирует использование сервиса {SERVICE_NAME}, "
                    "который предоставляет пользователю ограниченный по сроку доступ к "
                    "технической инфраструктуре защищённого сетевого подключения.",
                    f"Исполнителем является {operator}. Нажатие кнопки подтверждения заказа, "
                    "оплата или использование подписки означает принятие Соглашения.",
                ),
            ),
            _section(
                "2. Тарифы и состав услуги",
                (
                    "Цена и срок показываются до оформления заказа. Подписка начинает "
                    "действовать после подтверждения оплаты и активации доступа. Она может "
                    "использоваться на личных устройствах пользователя и не предназначена "
                    "для передачи или перепродажи третьим лицам.",
                ),
            ),
            tariffs,
            _section(
                "3. Оплата и активация",
                (
                    "Оплата производится доступным в интерфейсе способом через платёжного "
                    "провайдера Platega. Перед подтверждением платежа пользователь видит "
                    "итоговую сумму, тариф и срок.",
                    "После получения успешного статуса платежа сервис активирует или продлевает "
                    "подписку. При задержке активации пользователь обращается в поддержку и "
                    "указывает сведения, позволяющие найти платёж.",
                ),
            ),
            _section(
                "4. Правила использования",
                (
                    "Пользователь обязан соблюдать применимое законодательство и правила "
                    "сторонних сервисов.",
                ),
                (
                    "не использовать сервис для сетевых атак, спама, мошенничества и иной противоправной деятельности;",
                    "не распространять запрещённые материалы;",
                    "не передавать подписку третьим лицам и не перепродавать доступ;",
                    "не вмешиваться в работу серверов, бота, Mini App и платёжной системы.",
                ),
            ),
            _section(
                "5. Доступность и ответственность",
                (
                    "Скорость и доступность зависят от устройства пользователя, его сети, "
                    "маршрутов связи и работы сторонней инфраструктуры. Сервис не гарантирует "
                    "непрерывную доступность каждого стороннего ресурса или постоянную скорость.",
                    "При плановых работах, угрозе безопасности, нарушении Соглашения или "
                    "законном требовании доступ может быть временно ограничен. Администрация "
                    "стремится устранять технические неисправности в разумный срок.",
                ),
            ),
            _section(
                "6. Отказ от услуги и возврат",
                (
                    "Пользователь вправе отказаться от услуги и обратиться за возвратом через "
                    "тикет-систему поддержки. Возврат рассчитывается с учётом уже оказанной "
                    "части услуги и документально подтверждённых фактических расходов "
                    "исполнителя в соответствии с применимым законодательством.",
                    "Если доступ не был предоставлен по технической вине сервиса, пользователь "
                    "вправе потребовать повторную активацию либо возврат соответствующей суммы. "
                    "Для проверки обращения необходимо указать дату, сумму и идентификатор платежа.",
                ),
            ),
            _section(
                "7. Пользователи без полной дееспособности",
                (
                    "Пользователь, не обладающий полной дееспособностью, использует платные "
                    "функции только с согласия законного представителя.",
                ),
            ),
            _section(
                "8. Изменение условий",
                (
                    "Актуальная редакция постоянно размещена на этой странице. Новые условия "
                    "не уменьшают уже оплаченный срок подписки. Продолжение использования "
                    "сервиса после публикации новой редакции означает её принятие.",
                ),
            ),
        )
    )
    return _page(
        settings,
        title="Пользовательское соглашение",
        active="terms",
        description="Условия использования, оплаты и предоставления доступа Karipaza Froxy.",
        body=body,
    )
