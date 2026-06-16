const tg = window.Telegram?.WebApp;

if (tg) {
  tg.ready();
  tg.expand();
  tg.setHeaderColor("#101419");
  tg.setBackgroundColor("#101419");
}

const app = document.querySelector("#app");
const state = {
  tab: "home",
  me: null,
  plans: [],
  activeOrder: null,
  admin: {
    summary: null,
    users: [],
    orders: [],
    tickets: [],
  },
  busy: false,
  toast: "",
};

const NEWS = [
  {
    title: "🚀 Mini App обновлён",
    text: "Главная стала проще: новости, быстрые действия и ничего лишнего.",
  },
  {
    title: "🌍 Новые страны появятся в подписке",
    text: "Когда добавим дополнительные серверы, они появятся после обновления профиля в Happ.",
  },
  {
    title: "💳 Онлайн-оплата готовится",
    text: "Готовим ЮKassa. Пока платежи проходят через ручную проверку админом.",
  },
];

function authHeaders() {
  const headers = { "Content-Type": "application/json" };
  if (tg?.initData) {
    headers["X-Telegram-Init-Data"] = tg.initData;
  } else if (["127.0.0.1", "localhost"].includes(location.hostname)) {
    const params = new URLSearchParams(location.search);
    headers["X-Karipuza-Dev-User"] = params.get("devUser") || "123456789";
  }
  return headers;
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      ...authHeaders(),
      ...(options.headers || {}),
    },
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.error || "Ошибка, обратитесь к админу");
  }
  return data;
}

function money(value) {
  return `${Number(value || 0).toLocaleString("ru-RU")} ₽`;
}

function formatDate(timestamp) {
  if (!timestamp) return "не указано";
  return new Date(timestamp * 1000).toLocaleDateString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
}

function formatTraffic(bytes) {
  let value = Number(bytes || 0);
  const units = ["Б", "КБ", "МБ", "ГБ", "ТБ"];
  let index = 0;
  while (value >= 1024 && index < units.length - 1) {
    value /= 1024;
    index += 1;
  }
  return `${value.toFixed(value >= 10 ? 0 : 1)} ${units[index]}`;
}

function statusDetails(status, isActive = false) {
  if (status === "ACTIVE" && isActive) {
    return {
      text: "активна",
      title: "Доступ активен",
      tone: "ok",
      note: "Скопируйте ссылку и добавьте её в Happ.",
    };
  }
  if (status === "DISABLED") {
    return {
      text: "на паузе",
      title: "Доступ поставлен на паузу",
      tone: "warn",
      note: "Подписка сохранена, но подключение временно выключено админом.",
    };
  }
  if (status === "LIMITED") {
    return {
      text: "лимит",
      title: "Лимит исчерпан",
      tone: "warn",
      note: "Доступ ограничен. Напишите в поддержку, если это выглядит странно.",
    };
  }
  if (status === "EXPIRED") {
    return {
      text: "истекла",
      title: "Подписка закончилась",
      tone: "bad",
      note: "Продлите доступ, чтобы снова подключиться.",
    };
  }
  return {
    text: "нет подписки",
    title: "VPN ещё не подключён",
    tone: "muted",
    note: "Выберите тариф, отправьте оплату на проверку, и после подтверждения появится ссылка для Happ.",
  };
}

function statusText(status, isActive = false) {
  return statusDetails(status, isActive).text;
}

function orderStatusText(status) {
  const map = {
    WAITING_PAYMENT: "ждёт оплату",
    REVIEW: "на проверке",
    PROCESSING: "обработка",
    APPROVED: "подтверждён",
    REJECTED: "отклонён",
  };
  return map[status] || status;
}

function badgeClass(status, isActive = false) {
  return statusDetails(status, isActive).tone;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function userDisplayName() {
  const user = state.me?.user;
  return user?.firstName || user?.username || "личный кабинет";
}

function setToast(text) {
  state.toast = text;
  render();
  window.clearTimeout(setToast.timer);
  setToast.timer = window.setTimeout(() => {
    state.toast = "";
    render();
  }, 2600);
}

async function loadBase() {
  const [me, plans] = await Promise.all([api("/api/me"), api("/api/plans")]);
  state.me = me;
  state.plans = plans.plans || [];
  if (!state.activeOrder) {
    state.activeOrder = (me.orders || []).find(
      (order) => order.status === "WAITING_PAYMENT",
    );
  }
}

async function refresh() {
  try {
    state.busy = true;
    render();
    await loadBase();
    if (state.me?.user?.isAdmin && state.tab === "admin") {
      await loadAdmin();
    }
  } catch (error) {
    setToast(error.message);
  } finally {
    state.busy = false;
    render();
  }
}

async function loadAdmin() {
  const [summary, users, orders, tickets] = await Promise.all([
    api("/api/admin/summary"),
    api("/api/admin/users"),
    api("/api/admin/orders?status=REVIEW"),
    api("/api/admin/tickets?status=OPEN"),
  ]);
  state.admin.summary = summary;
  state.admin.users = users.users || [];
  state.admin.orders = orders.orders || [];
  state.admin.tickets = tickets.tickets || [];
}

function header() {
  return `
    <header class="topbar">
      <div class="brand">
        <div class="mini-mark" aria-hidden="true">
          <img class="brand-logo" src="/assets/logo.png" alt="" />
        </div>
        <div>
          <h1>Karipuza VPN</h1>
          <p>${escapeHtml(userDisplayName())}</p>
        </div>
      </div>
    </header>
  `;
}

function nav() {
  const isAdmin = Boolean(state.me?.user?.isAdmin);
  const tabs = [
    ["home", "🏠 Главная"],
    ["plans", "💳 Тарифы"],
    ["subscription", "🔑 Подписка"],
    ["support", "💬 Помощь"],
    ["profile", "👤 Профиль"],
  ];
  if (isAdmin) tabs.push(["admin", "🛠 Админ"]);
  return `
    <nav class="bottom-nav ${isAdmin ? "admin" : ""}">
      <div class="bottom-nav-inner">
        ${tabs
          .map(
            ([id, label]) => `
              <button class="nav-btn ${state.tab === id ? "active" : ""}" data-tab="${id}">
                ${label}
              </button>
            `,
          )
          .join("")}
      </div>
    </nav>
  `;
}

function homeIntro() {
  const sub = state.me?.subscription;
  const active = sub?.status === "ACTIVE" && sub?.isActive;
  return `
    <section class="panel home-hero">
      <p class="eyebrow">👋 Главная</p>
      <h2 class="title">${active ? "Всё в порядке, VPN активен" : "Добро пожаловать в Karipuza"}</h2>
      <p class="subtitle">Новости сервиса, быстрые действия и важные уведомления будут здесь.</p>
      <div class="quick-actions compact-actions">
        <button class="btn primary" data-tab="${sub ? "subscription" : "plans"}">${sub ? "🔑 Подписка" : "💳 Купить"}</button>
        <button class="btn ghost" data-tab="support">💬 Поддержка</button>
      </div>
    </section>
  `;
}

function newsSection() {
  return `
    <div class="section-title">
      <h2>🔔 Новости</h2>
    </div>
    <div class="news-grid">
      ${NEWS.map(
        (item) => `
          <article class="news-card">
            <strong>${escapeHtml(item.title)}</strong>
            <div class="row-meta">${escapeHtml(item.text)}</div>
          </article>
        `,
      ).join("")}
    </div>
  `;
}

function homeStatusCard() {
  const sub = state.me?.subscription;
  const details = statusDetails(sub?.status, sub?.isActive);
  return `
    <section class="status-card ${details.tone}">
      <div>
        <span>${sub ? "Состояние доступа" : "Старт"}</span>
        <strong>${sub ? details.title : "Оформите подписку"}</strong>
      </div>
      <button class="btn small" data-tab="${sub ? "subscription" : "plans"}">${sub ? "К подписке" : "Выбрать"}</button>
    </section>
  `;
}

function homeView() {
  return `
    <main class="view">
      ${homeIntro()}
      ${homeStatusCard()}
      ${newsSection()}
    </main>
  `;
}

function subscriptionPanel() {
  const sub = state.me?.subscription;
  const details = statusDetails(sub?.status, sub?.isActive);
  if (!sub) {
    return `
      <section class="panel">
        <p class="eyebrow">🔑 Подписка</p>
        <h2 class="title">${details.title}</h2>
        <p class="subtitle">${details.note}</p>
        <div class="actions compact-actions">
          <button class="btn primary" data-tab="plans">💳 Выбрать тариф</button>
          <button class="btn ghost" data-tab="support">💬 Поддержка</button>
        </div>
      </section>
    `;
  }
  return `
    <section class="panel">
      <div class="split">
        <div>
          <p class="eyebrow">🔑 Моя подписка</p>
          <h2 class="title">${details.title}</h2>
          <p class="subtitle">Действует до ${formatDate(sub.expireAt)}. Осталось ${sub.daysLeft} дн.</p>
        </div>
        <span class="badge ${details.tone}">${details.text}</span>
      </div>
      <p class="hint">${details.note}</p>
      <div class="metric-grid">
        <div class="metric"><span>📊 Использовано</span><strong>${formatTraffic(sub.trafficUsed)}</strong></div>
        <div class="metric"><span>∞ Трафик</span><strong>${sub.trafficLimit ? formatTraffic(sub.trafficLimit) : "безлимит"}</strong></div>
      </div>
      <div class="actions compact-actions three">
        <button class="btn primary" data-copy-sub>📋 Скопировать</button>
        <button class="btn" data-tab="plans">💳 Продлить</button>
        <button class="btn ghost" data-refresh>🔄 Обновить</button>
      </div>
    </section>
  `;
}

function connectionPanel() {
  const sub = state.me?.subscription;
  return `
    <section class="panel">
      <p class="eyebrow">📲 Подключение</p>
      <h2 class="title">${sub ? "Одна подписка для всех устройств" : "Подключение появится после оплаты"}</h2>
      <p class="subtitle">Добавьте профиль в Happ на телефоне или компьютере. Когда появятся новые страны, они подтянутся после обновления профиля.</p>
      <div class="steps">
        <div class="step"><div class="step-num">1</div><div>Установите Happ для своего устройства.</div></div>
        <div class="step"><div class="step-num">2</div><div>Нажмите «Скопировать» в блоке подписки выше.</div></div>
        <div class="step"><div class="step-num">3</div><div>Добавьте ссылку в Happ и выберите нужный сервер.</div></div>
      </div>
      <div class="actions compact-actions">
        <button class="btn" data-link="https://play.google.com/store/apps/details?id=com.happproxy">Android</button>
        <button class="btn" data-link="https://apps.apple.com/us/app/happ-proxy-utility/id6504287215">iPhone</button>
        <button class="btn" data-link="https://github.com/Happ-proxy/happ-desktop/releases">ПК</button>
        <button class="btn ghost" data-refresh>Обновить</button>
      </div>
    </section>
  `;
}

function subscriptionView() {
  return `
    <main class="view">
      ${subscriptionPanel()}
      ${connectionPanel()}
    </main>
  `;
}

function planCard(plan) {
  const daily = Math.max(1, Math.round(plan.priceRub / plan.days));
  return `
    <article class="plan-card">
      <div class="row-head">
        <div>
          <p class="eyebrow">${escapeHtml(plan.badge)}</p>
          <h2 class="title">${escapeHtml(plan.title)}</h2>
        </div>
        <span class="badge">${plan.days} дн.</span>
      </div>
      <div class="price">${money(plan.priceRub)} <small>около ${money(daily)} в день</small></div>
      <button class="btn primary" data-buy="${plan.code}">💳 Оформить</button>
    </article>
  `;
}

function paymentPanel() {
  const order = state.activeOrder;
  if (!order) return "";
  const details =
    state.me?.paymentDetails ||
    "Реквизиты ещё не настроены. Напишите в поддержку.";
  const yookassaReady = Boolean(state.me?.payment?.yookassaReady);
  return `
    <section class="panel payment-box">
      <div class="row-head">
        <div>
          <p class="eyebrow">🧾 Заказ #${order.id}</p>
          <h2 class="title">${escapeHtml(order.title)}</h2>
        </div>
        <span class="badge warn">${money(order.amount_rub)}</span>
      </div>
      <div class="subtle-card">
        <strong>${yookassaReady ? "💳 ЮKassa почти готова" : "💳 Онлайн-оплата готовится"}</strong>
        <div class="row-meta">
          ${
            yookassaReady
              ? "Данные магазина добавлены. Осталось подключить создание платежей и webhook."
              : "Пока оплата проходит через ручную проверку. Поля ЮKassa уже подготовлены в настройках сервера."
          }
        </div>
      </div>
      <div class="copy-box">${escapeHtml(details).replaceAll("\n", "<br />")}</div>
      <div class="field">
        <label for="proofText">Данные платежа или комментарий</label>
        <textarea id="proofText" placeholder="Например: оплатил с карты **** 1234, время 18:40"></textarea>
      </div>
      <div class="actions compact-actions">
        <button class="btn primary" data-submit-proof="${order.id}">✅ Отправить</button>
        <button class="btn ghost" data-clear-order>Закрыть</button>
      </div>
    </section>
  `;
}

function plansView() {
  return `
    <main class="view">
      ${paymentPanel()}
      <section class="panel tight">
        <p class="eyebrow">💳 Тарифы</p>
        <h2 class="title">Выберите срок доступа</h2>
        <p class="subtitle">После оплаты админ подтвердит платёж, и Mini App покажет подписку для подключения.</p>
      </section>
      <div class="plan-grid">
        ${state.plans.map(planCard).join("")}
      </div>
    </main>
  `;
}

function supportView() {
  const tickets = state.me?.tickets || [];
  return `
    <main class="view">
      <section class="panel">
        <p class="eyebrow">💬 Поддержка</p>
        <h2 class="title">Напишите, что случилось</h2>
        <p class="subtitle">Лучше сразу указать устройство, сеть и что пишет приложение. Ответ придёт в Telegram.</p>
        <div class="field">
          <label for="supportText">Сообщение</label>
          <textarea id="supportText" placeholder="Например: на Wi-Fi не подключается, Happ пишет timeout"></textarea>
        </div>
        <button class="btn primary" data-support-send>📨 Отправить</button>
      </section>
      <div class="section-title"><h2>💬 Мои обращения</h2></div>
      <div class="list">
        ${
          tickets.length
            ? tickets
                .map(
                  (ticket) => `
                    <div class="row">
                      <div class="row-head">
                        <div>
                          <div class="row-title">Обращение #${ticket.id}</div>
                          <div class="row-meta">${formatDate(ticket.created_at)}</div>
                        </div>
                        <span class="badge ${ticket.status === "OPEN" ? "warn" : "ok"}">${ticket.status === "OPEN" ? "открыто" : "закрыто"}</span>
                      </div>
                    </div>
                  `,
                )
                .join("")
            : `<div class="empty">Обращений пока нет</div>`
        }
      </div>
    </main>
  `;
}

function profileView() {
  const user = state.me?.user || {};
  const sub = state.me?.subscription;
  const details = statusDetails(sub?.status, sub?.isActive);
  const paymentMode = state.me?.payment?.yookassaReady
    ? "ЮKassa подключается"
    : "ручная проверка";
  return `
    <main class="view">
      <section class="panel profile-card">
        <div class="profile-head">
          <div class="mini-mark large" aria-hidden="true">
            <img class="brand-logo" src="/assets/logo.png" alt="" />
          </div>
          <div>
            <p class="eyebrow">👤 Профиль</p>
            <h2 class="title">${escapeHtml(user.firstName || user.username || "Пользователь")}</h2>
            <p class="subtitle">TG ID ${escapeHtml(user.tgId)}</p>
          </div>
        </div>
        <div class="profile-grid">
          <div class="profile-row"><span>Статус</span><strong>${details.text}</strong></div>
          <div class="profile-row"><span>Подписка до</span><strong>${formatDate(sub?.expireAt)}</strong></div>
          <div class="profile-row"><span>Осталось</span><strong>${sub ? `${sub.daysLeft} дн.` : "нет"}</strong></div>
          <div class="profile-row"><span>Оплата</span><strong>${paymentMode}</strong></div>
        </div>
        <div class="actions compact-actions">
          <button class="btn primary" data-tab="subscription">🔑 Подписка</button>
          <button class="btn ghost" data-tab="support">💬 Поддержка</button>
        </div>
      </section>
      <section class="panel tight">
        <p class="eyebrow">🧭 Полезно</p>
        <h2 class="title">Одна ссылка, несколько устройств</h2>
        <p class="subtitle">Добавьте подписку в Happ один раз. Новые серверы и изменения будут появляться после обновления профиля.</p>
      </section>
    </main>
  `;
}

function adminView() {
  if (!state.me?.user?.isAdmin) {
    return `<main class="view"><div class="empty">Недостаточно прав</div></main>`;
  }
  const stats = state.admin.summary?.stats || {};
  const orders = state.admin.orders || [];
  const tickets = state.admin.tickets || [];
  const users = state.admin.users || [];
  return `
    <main class="view">
      <section class="panel">
        <div class="row-head">
          <div>
            <p class="eyebrow">🛠 Админ-панель</p>
            <h2 class="title">Управление Karipuza</h2>
          </div>
          <button class="btn ghost small" data-admin-refresh>🔄 Обновить</button>
        </div>
        <div class="admin-grid">
          <div class="metric"><span>👥 Пользователи</span><strong>${stats.users ?? 0}</strong></div>
          <div class="metric"><span>⚡ Активные</span><strong>${stats.active ?? 0}</strong></div>
          <div class="metric"><span>💳 Платежи</span><strong>${stats.orders ?? 0}</strong></div>
          <div class="metric"><span>💬 Поддержка</span><strong>${stats.tickets ?? 0}</strong></div>
        </div>
      </section>
      <div class="section-title"><h2>💳 Платежи на проверке</h2></div>
      <div class="list">
        ${
          orders.length
            ? orders
                .map(
                  (order) => `
                    <div class="row">
                      <div class="row-head">
                        <div>
                          <div class="row-title">#${order.id} · ${escapeHtml(order.title)}</div>
                          <div class="row-meta">TG ${order.tg_id} · ${money(order.amount_rub)}</div>
                        </div>
                        <span class="badge warn">проверка</span>
                      </div>
                      <div class="copy-box">${escapeHtml(order.proof_text || "без текста")}</div>
                      <div class="actions compact-actions">
                        <button class="btn green" data-approve="${order.id}">✅ Подтвердить</button>
                        <button class="btn red" data-reject="${order.id}">✕ Отклонить</button>
                      </div>
                    </div>
                  `,
                )
                .join("")
            : `<div class="empty">Новых платежей нет</div>`
        }
      </div>
      <div class="section-title"><h2>💬 Открытые обращения</h2></div>
      <div class="list">
        ${
          tickets.length
            ? tickets
                .map(
                  (ticket) => `
                    <div class="row">
                      <div class="row-head">
                        <div>
                          <div class="row-title">Обращение #${ticket.id}</div>
                          <div class="row-meta">${escapeHtml(ticket.first_name || ticket.username || `TG ${ticket.tg_id}`)} · ${formatDate(ticket.updated_at)}</div>
                        </div>
                        <span class="badge warn">открыто</span>
                      </div>
                      <div class="message-stack">
                        ${(ticket.messages || [])
                          .map(
                            (message) => `
                              <div class="message-bubble">
                                <strong>${message.sender_role === "ADMIN" ? "Админ" : "Пользователь"}:</strong>
                                ${escapeHtml(message.text)}
                              </div>
                            `,
                          )
                          .join("")}
                      </div>
                      <div class="reply-box">
                        <div class="field">
                          <label for="ticketReply${ticket.id}">Ответ</label>
                          <textarea id="ticketReply${ticket.id}" placeholder="Напишите ответ пользователю"></textarea>
                        </div>
                        <div class="actions compact-actions">
                          <button class="btn primary" data-reply-ticket="${ticket.id}">📨 Ответить</button>
                          <button class="btn ghost" data-close-ticket="${ticket.id}">Закрыть</button>
                        </div>
                      </div>
                    </div>
                  `,
                )
                .join("")
            : `<div class="empty">Открытых обращений нет</div>`
        }
      </div>
      <div class="section-title"><h2>👥 Пользователи</h2></div>
      <div class="list">
        ${
          users.length
            ? users
                .map(
                  (user) => `
                    <div class="row">
                      <div class="row-head">
                        <div>
                          <div class="row-title">${escapeHtml(user.first_name || user.username || `TG ${user.tg_id}`)}</div>
                          <div class="row-meta">TG ${user.tg_id} · до ${formatDate(user.expire_at)}</div>
                        </div>
                        <span class="badge ${badgeClass(user.vpn_status, user.vpn_status === "ACTIVE")}">${statusText(user.vpn_status, user.vpn_status === "ACTIVE")}</span>
                      </div>
                      <div class="actions compact-actions three">
                        <button class="btn green" data-grant="${user.tg_id}">+30 дней</button>
                        <button class="btn" data-enable="${user.tg_id}">✅ Включить</button>
                        <button class="btn red" data-disable="${user.tg_id}">⏸ Пауза</button>
                      </div>
                    </div>
                  `,
                )
                .join("")
            : `<div class="empty">Пользователей пока нет</div>`
        }
      </div>
    </main>
  `;
}

function currentView() {
  if (!state.me) {
    return `<div class="loading"><img class="loading-logo" src="/assets/logo.png" alt="" /><p>Загрузка</p></div>`;
  }
  const views = {
    home: homeView,
    plans: plansView,
    subscription: subscriptionView,
    support: supportView,
    profile: profileView,
    admin: adminView,
  };
  return (views[state.tab] || homeView)();
}

function render() {
  app.innerHTML = `
    ${state.me ? header() : ""}
    ${currentView()}
    ${state.me ? nav() : ""}
    ${state.toast ? `<div class="toast">${escapeHtml(state.toast)}</div>` : ""}
  `;
}

async function copyText(text) {
  await navigator.clipboard.writeText(text);
  setToast("Скопировано");
}

function openLink(url) {
  if (tg?.openLink) tg.openLink(url);
  else window.open(url, "_blank", "noopener");
}

async function handleClick(event) {
  const target = event.target.closest("button");
  if (!target || state.busy) return;

  const tab = target.dataset.tab;
  if (tab) {
    state.tab = tab;
    if (tab === "admin") await loadAdmin();
    render();
    return;
  }

  try {
    if (target.dataset.refresh !== undefined) {
      await refresh();
      setToast("Обновлено");
    } else if (target.dataset.copySub !== undefined) {
      const url = state.me?.subscription?.subscriptionUrl;
      if (url) await copyText(url);
    } else if (target.dataset.link) {
      openLink(target.dataset.link);
    } else if (target.dataset.buy) {
      const result = await api("/api/orders", {
        method: "POST",
        body: JSON.stringify({ tariffCode: target.dataset.buy }),
      });
      state.activeOrder = result.order;
      state.tab = "plans";
      await refresh();
      setToast(result.created ? "Заказ создан" : "Заказ уже был создан");
    } else if (target.dataset.clearOrder !== undefined) {
      state.activeOrder = null;
      render();
    } else if (target.dataset.submitProof) {
      const textarea = document.querySelector("#proofText");
      const text = textarea?.value.trim();
      if (!text) {
        setToast("Напишите данные платежа");
        return;
      }
      await api(`/api/orders/${target.dataset.submitProof}/proof`, {
        method: "POST",
        body: JSON.stringify({ text }),
      });
      state.activeOrder = null;
      await refresh();
      setToast("Платёж отправлен на проверку");
    } else if (target.dataset.supportSend !== undefined) {
      const textarea = document.querySelector("#supportText");
      const text = textarea?.value.trim();
      if (!text) {
        setToast("Напишите сообщение");
        return;
      }
      await api("/api/support", {
        method: "POST",
        body: JSON.stringify({ text }),
      });
      await refresh();
      setToast("Обращение создано");
    } else if (target.dataset.adminRefresh !== undefined) {
      await loadAdmin();
      render();
      setToast("Админка обновлена");
    } else if (target.dataset.approve) {
      await api(`/api/admin/orders/${target.dataset.approve}/approve`, { method: "POST" });
      await loadAdmin();
      await refresh();
      setToast("Платёж подтверждён");
    } else if (target.dataset.reject) {
      await api(`/api/admin/orders/${target.dataset.reject}/reject`, { method: "POST" });
      await loadAdmin();
      await refresh();
      setToast("Платёж отклонён");
    } else if (target.dataset.replyTicket) {
      const textarea = document.querySelector(`#ticketReply${target.dataset.replyTicket}`);
      const text = textarea?.value.trim();
      if (!text) {
        setToast("Напишите ответ");
        return;
      }
      await api(`/api/admin/tickets/${target.dataset.replyTicket}/reply`, {
        method: "POST",
        body: JSON.stringify({ text }),
      });
      await loadAdmin();
      render();
      setToast("Ответ отправлен");
    } else if (target.dataset.closeTicket) {
      await api(`/api/admin/tickets/${target.dataset.closeTicket}/close`, { method: "POST" });
      await loadAdmin();
      render();
      setToast("Обращение закрыто");
    } else if (target.dataset.grant) {
      await api(`/api/admin/users/${target.dataset.grant}/grant`, {
        method: "POST",
        body: JSON.stringify({ days: 30 }),
      });
      await loadAdmin();
      await refresh();
      setToast("Добавлено 30 дней");
    } else if (target.dataset.enable) {
      await api(`/api/admin/users/${target.dataset.enable}/enable`, { method: "POST" });
      await loadAdmin();
      await refresh();
      setToast("Доступ снова включён");
    } else if (target.dataset.disable) {
      await api(`/api/admin/users/${target.dataset.disable}/disable`, { method: "POST" });
      await loadAdmin();
      await refresh();
      setToast("Доступ поставлен на паузу");
    }
  } catch (error) {
    setToast(error.message);
  }
}

app.addEventListener("click", handleClick);

render();
refresh();
