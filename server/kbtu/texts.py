"""Texts the server writes itself: share cards now, bot messages next (SPEC §7). Like the app's i18n, ru is
the source and kk/en follow it; a user's language comes from users.lang. Only server templates reach
Telegram: from the client we take ids, never text."""
from __future__ import annotations

import calendar
import csv
import html
import io
import re
import time

MONTHS = {
    "ru": ("января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря"),
    "kk": ("қаңтар", "ақпан", "наурыз", "сәуір", "мамыр", "маусым", "шілде", "тамыз", "қыркүйек", "қазан", "қараша", "желтоқсан"),
    "en": ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"),
}

SHARE_EVENT = {
    "ru": ("Пойдёшь со мной? 👀", "🎟 Открыть в KBTU App"),
    "kk": ("Менімен барасың ба? 👀", "🎟 KBTU App-та ашу"),
    "en": ("Coming with me? 👀", "🎟 Open in KBTU App"),
}


# Invites shared from the app (no bare links in chats — a line of text and our bot's button under it)
SHARE_FRIEND = {
    "ru": ("Добавляйся в друзья", "👋 <b>{name}</b> зовёт тебя в друзья в KBTU App — увидите, кто куда идёт.", "🤝 Добавиться в друзья"),
    "kk": ("Дос бол", "👋 <b>{name}</b> сені KBTU App-та досқа шақырады — кім қайда баратынын көресіңдер.", "🤝 Досқа қосылу"),
    "en": ("Be my friend", "👋 <b>{name}</b> invites you to be friends on KBTU App — you'll see where each other is going.", "🤝 Add as a friend"),
}
SHARE_REFER = {  # my invite link (referrals): it counts once they sign in with KBTU
    "ru": ("Залетай в KBTU App", "📣 <b>{name}</b> зовёт тебя в KBTU App: все события, клубы и друзья КБТУ в одном месте.", "🚀 Открыть KBTU App"),
    "kk": ("KBTU App-қа кел", "📣 <b>{name}</b> сені KBTU App-қа шақырады: ҚБТУ-дің барлық іс-шаралары, клубтары мен достары бір жерде.", "🚀 KBTU App ашу"),
    "en": ("Join KBTU App", "📣 <b>{name}</b> invites you to KBTU App: KBTU's events, clubs and friends in one place.", "🚀 Open KBTU App"),
}
SHARE_PRES = {  # the admin's one-time President link (§2): a new club's President opens it
    "ru": ("Клуб ждёт президента", "👑 Тебя назначают президентом <b>{club}</b> в KBTU App. Открой и войди через KBTU — ссылка одноразовая, работает 7 дней.", "Стать президентом"),
    "kk": ("Клуб президентін күтеді", "👑 Сені KBTU App-та <b>{club}</b> клубының президенті етіп тағайындайды. Аш та, KBTU арқылы кір — сілтеме бір реттік, 7 күн жұмыс істейді.", "Президент болу"),
    "en": ("A club awaits its President", "👑 You're becoming the President of <b>{club}</b> on KBTU App. Open it and sign in with KBTU — the link works once, for 7 days.", "Become President"),
}
SHARE_GRANT = {  # the creator's one-time award link (logic.grant_link)
    "ru": ("Тебе награда", "🏅 Создатель KBTU App выдаёт тебе награду <b>{award}</b>. Спасибо! Ссылка одноразовая, работает 7 дней.", "🏅 Забрать награду"),
    "kk": ("Саған марапат", "🏅 KBTU App авторы саған <b>{award}</b> марапатын береді. Рақмет! Сілтеме бір реттік, 7 күн жұмыс істейді.", "🏅 Марапатты алу"),
    "en": ("An award for you", "🏅 The creator of KBTU App gives you the <b>{award}</b> award. Thank you! The link works once, for 7 days.", "🏅 Claim the award"),
}
SHARE_ROUND = {  # a club's open recruitment round (casting.py)
    "ru": ("Набор в клуб", "📣 <b>{club}</b> набирает людей до {until}. Заявка — минута, всё остальное клуб уже знает из KBTU.", "📝 Подать заявку"),
    "kk": ("Клубқа қабылдау", "📣 <b>{club}</b> {until} дейін адам қабылдайды. Өтінім — бір минут, қалғанын клуб KBTU-дан біледі.", "📝 Өтінім беру"),
    "en": ("Club recruiting", "📣 <b>{club}</b> is recruiting until {until}. Applying takes a minute: the club knows the rest from KBTU.", "📝 Apply"),
}
SHARE_JOIN = {
    "ru": ("Вступай в клуб", "🎉 Тебя зовут в <b>{club}</b> в KBTU App — вступай в команду.", "Вступить в клуб"),
    "kk": ("Клубқа қосыл", "🎉 Сені KBTU App-та <b>{club}</b> клубына шақырады — командаға қосыл.", "Клубқа қосылу"),
    "en": ("Join the club", "🎉 You're invited to <b>{club}</b> on KBTU App — join the team.", "Join the club"),
}


# An achievement shared from its card (§4.11): first person (the user sends it), its name and tier as the app names them
# (web i18n ach.<code>.name / ach.tier.N), how rare it is; the button opens the reader's own progress toward it.
SHARE_AWARD = {
    "ru": ("Моя награда в KBTU App", "🏅 Моя новая награда в KBTU App: <b>{name}</b>{tier}\nТакая есть у {p}% студентов. Получится так же?", "🏅 Посмотреть награду"),
    "kk": ("KBTU App-тағы марапатым", "🏅 KBTU App-тағы жаңа марапатым: <b>{name}</b>{tier}\nОл студенттердің {p}%-ында бар. Сен де аласың ба?", "🏅 Марапатты көру"),
    "en": ("My award on KBTU App", "🏅 My new award on KBTU App: <b>{name}</b>{tier}\n{p}% of students have it. Can you get one too?", "🏅 See the award"),
}
ACH_NAMES = {
    "ru": {"regular": "Постоянный гость", "streak": "Серия", "first_in": "Первый на входе", "soul": "Душа тусовки", "season": "Сезон", "first50": "Первые 500",
           "creator_laugh": "Рассмешить создателя", "creator_found": "Привет, создатель", "bugs": "Охотник за багами", "team": "Гроза тимбилдинга", "referral": "Зазывала"},
    "kk": {"regular": "Тұрақты қонақ", "streak": "Серия", "first_in": "Бірінші келген", "soul": "Компанияның жаны", "season": "Маусым", "first50": "Алғашқы 500",
           "creator_laugh": "Авторды күлдірді", "creator_found": "Авторды тапты", "bugs": "Баг аңшысы", "team": "Тимбилдинг найзағайы", "referral": "Шақырушы"},
    "en": {"regular": "Regular", "streak": "Streak", "first_in": "First in", "soul": "Life of the party", "season": "Season", "first50": "First 500",
           "creator_laugh": "Made the creator laugh", "creator_found": "Found the creator", "bugs": "Bug hunter", "team": "Teambuilding thunder", "referral": "Recruiter"},
}
TIERS = {"ru": ("I", "II", "III", "Легенда"), "kk": ("I", "II", "III", "Аңыз"), "en": ("I", "II", "III", "Legend")}
BAN = {"ru": " с баном", "kk": " (бан)", "en": " and ban them"}


# The page between the app and the phone's calendar (/cal/<token>): it hands the feed to the calendar app at once;
# the button is there if the phone asks for a tap first.
CAL_PAGE = {
    "ru": ("Календарь KBTU App", "Все события, на которые ты идёшь, — в календаре телефона. Новые появятся сами.", "Подписаться"),
    "kk": ("KBTU App күнтізбесі", "Баратын барлық іс-шараң — телефон күнтізбесінде. Жаңалары өздігінен қосылады.", "Жазылу"),
    "en": ("KBTU App calendar", "Every event you're going to, in your phone's calendar. New ones show up on their own.", "Subscribe"),
}


def share_award(lang: str, code: str, level: int, tiers: int, rarity: float) -> tuple[str, str, str]:
    """(title, HTML text, button) for an achievement card; the tier only when the achievement has levels."""
    lang = lang if lang in SHARE_AWARD else "ru"
    title, text, button = SHARE_AWARD[lang]
    p = "<1" if 0 < rarity < 0.01 else str(round(rarity * 100))
    tier = f" · {TIERS[lang][level - 1]}" if tiers > 1 else ""
    return title, text.format(name=html.escape(ACH_NAMES[lang][code]), tier=tier, p=html.escape(p)), button


def share_invite(kind: str, lang: str, **fields: str) -> tuple[str, str, str]:
    """(title, HTML text, button) for a friend ('fr'), a club ('join') or a President ('pres') invite card."""
    title, text, button = {"fr": SHARE_FRIEND, "rf": SHARE_REFER, "join": SHARE_JOIN, "pres": SHARE_PRES, "rc": SHARE_ROUND, "gl": SHARE_GRANT}[kind][lang if lang in SHARE_FRIEND else "ru"]
    return title, text.format(**{k: html.escape(v) for k, v in fields.items()}), button


def when(ts: int, lang: str) -> str:
    """'4 октября, 18:00' in Almaty time (UTC+5, as lib/time.ts)."""
    t = time.gmtime(ts + 5 * 3600)
    month = MONTHS[lang][t.tm_mon - 1]
    day = f"{month} {t.tm_mday}" if lang == "en" else f"{t.tm_mday} {month}"
    return f"{day}, {t.tm_hour:02d}:{t.tm_min:02d}"


def share_event(lang: str, title: str, starts_at: int, place: str) -> tuple[str, str]:
    """(HTML caption, button text) for an event card."""
    ask, button = SHARE_EVENT[lang]
    where = f" · {html.escape(place)}" if place else ""  # no place yet: no dangling dot
    caption = f"<b>{html.escape(title)}</b>\n🗓 {when(starts_at, lang)}{where}\n\n{ask}"
    return caption, button


# Bot messages (SPEC §7): kind → (HTML text, button or None). Fields: title, when, place, org, room.
BOT = {
    "ru": {
        "exit": ("🚪 <b>Ищешь выход из КБТУ?</b>\nНажми кнопку, введи номер ближайшей аудитории — приложение доведёт до открытого выхода.", "🚪 Найти выход"),
        "welcome": ("👋 Это <b>KBTU App</b>: мероприятия и клубы КБТУ, твоё расписание и карта корпуса.\nВсё внутри приложения — открывай 👇", "🚀 Открыть KBTU App"),
        "remind_2h": ("⏰ Через 2 часа — <b>{title}</b>\n📍 {place}\nБилет уже в приложении.", "🎟 Открыть билет"),
        "remind_2h_team": ("⏰ Через 2 часа — <b>{title}</b>\n📍 {place}", "Открыть событие"),
        "seat_free_team": ("🎉 Освободилось место — ты идёшь на <b>{title}</b>!\n🗓 {when} · {place}", "Открыть событие"),
        "event_changed": ("✏️ Изменения: <b>{title}</b>\n🗓 {when} · {place}", "Посмотреть"),
        "event_cancelled": ("😔 <b>{title}</b> ({when}) отменили. В афише есть и другие события.", "Открыть афишу"),
        "new_event": ("✨ {org}: <b>{title}</b>\n🗓 {when} · {place}", "🎟 Подробнее"),
        "going_ok": ("✅ Ты записан на <b>{title}</b>\n🗓 {when} · {place}\nБилет уже в приложении.", "🎟 Открыть билет"),
        "going_ok_team": ("✅ Ты записан на <b>{title}</b>\n🗓 {when} · {place}", "Открыть событие"),
        "seat_free": ("🎉 Освободилось место — ты идёшь на <b>{title}</b>!\n🗓 {when} · {place}", "🎟 Мой билет"),
        "seat_hold": ("🎉 Освободилось место на <b>{title}</b>!\n🗓 {when} · {place}\nОплати и загрузи чек за 30 минут, иначе место уйдёт следующему.", "💳 Оплатить"),
        "receipt_rejected": ("😔 Организаторы <b>{title}</b> ({org}) отклонили твой чек, билет больше не действует. Если это ошибка, напиши им.", "Открыть событие"),
        "receipt_ok": ("🎟 Чек принят — ты идёшь на <b>{title}</b>!\nБилет уже в приложении.", "🎟 Открыть билет"),
        "round_open": ("📣 <b>{org}</b> набирает людей! Заявка — минута: всё, что клуб знает о тебе из KBTU, уже заполнено. Набор до {until}.", "📝 Подать заявку"),
        "round_interview": ("🎤 Ты прошёл первый этап набора в <b>{org}</b>! Выбери время собеседования.", "🗓 Выбрать время"),
        "round_iv_nudge": ("⏰ <b>{org}</b> ждёт: ты ещё не выбрал время собеседования.", "🗓 Выбрать время"),
        "round_iv_remind": ("🎤 Собеседование в <b>{org}</b>: {when}\n📍 {place}", "Открыть"),
        "round_yes": ("🎉 Тебя приняли в <b>{org}</b>! Добро пожаловать в команду.", "Открыть клуб"),
        "round_yes_dept": ("🎉 Тебя приняли в <b>{org}</b>, твой департамент — <b>{dept}</b>! Добро пожаловать в команду.", "Открыть клуб"),
        "round_no": ("💙 Спасибо, что подал заявку в <b>{org}</b>. В этот раз не получилось — попробуй в следующем наборе. Другие клубы набирают прямо сейчас.", "Клубы"),
        "memo_ready": ("📝 Служебка в ДМП на следующую неделю готова: «{org}», событий: {n}. ДМП принимает её сегодня до 18:00 — проверь и отправь с почты КБТУ.", "📝 Открыть служебку"),
        "saved_tomorrow": ("🔖 Ты сохранял — это уже завтра:\n{list}\nЕщё есть места, если надумаешь.", "🎟 Посмотреть"),
        "place_tba": ("📍 У события ещё нет места:\n{list}\nКогда ДМП даст аудиторию, впиши её в событие — участники увидят её в напоминании.", "Открыть событие"),
        "receipt_check": ("🎟 Билет на <b>{title}</b> уже твой.\n⚠️ Но чек не похож на оплату этого события: {why}. Если ошибся файлом, замени чек в билете — организатор увидит новый.", "🎟 Открыть билет"),
        "receipt_which": ("🧾 За какое событие этот чек?", None),
        "receipt_none": ("🧾 Не нашёл, за что этот чек. Сначала нажми «Иду» на платном событии в приложении, потом пришли чек сюда.", "🚀 Открыть KBTU App"),
        "receipt_late": ("⌛ Бронь на <b>{title}</b> истекла, и чек не к чему привязать. Если места остались, нажми «Иду» ещё раз и пришли чек снова. Если мест нет, напиши организаторам о возврате.", "Открыть событие"),
        "receipt_not": ("😕 Это не чек Kaspi. Пришли сам чек: Kaspi → платёж → «Поделиться» → Telegram, или его скриншот.", None),
        "receipt_bad": ("😕 Не получилось открыть файл. Пришли чек из Kaspi («Поделиться» → Telegram) или его скриншот.", None),
        "receipt_signin": ("🧾 Чтобы чек засчитался, сначала войди в KBTU App со своим аккаунтом КБТУ.", "🚀 Открыть KBTU App"),
        "join_request": ("🙋 Новая заявка в <b>{org}</b>: {name}", "Открыть заявки"),
        "roster_claim": ("📋 {name} говорит, что это он(а) в списке <b>{org}</b> от ДМП, но имя в списке другое. Подтвердишь?", "Открыть"),
        "join_yes": ("🎉 Тебя приняли в <b>{org}</b>! Добро пожаловать в команду.", "Открыть клуб"),
        "join_no": ("💙 <b>{org}</b> пока не может тебя принять. Загляни в другие клубы — их много.", None),
        "friend_request": ("🙋 <b>{name}</b> хочет добавить тебя в друзья в KBTU App", "Ответить"),
        "volunteer_yes": ("🙌 Ты волонтёр на <b>{title}</b> ({org})!\n🗓 {when} · {place}\nОрганизаторы напишут, что делать.", "Открыть"),
        "volunteer_no": ("🙏 На <b>{title}</b> ({org}) волонтёров уже хватает. Спасибо, что откликнулся! Приходи гостем.", "Открыть"),
        "leaders_invite": ("📣 {org} приглашает руководителей клубов: <b>{title}</b>\n🗓 {when} · {place}\nОтветь в приложении: будешь или нет.", "Ответить"),
        "meeting_invite": ("📌 {org}: обязательная встреча <b>{title}</b>\n🗓 {when} · {place}\nОтветь в приложении: будешь или нет (если нет, напиши почему).", "Ответить"),
        "friend_invite": ("🎟 <b>{name}</b> зовёт тебя на <b>{title}</b>\n🗓 {when} · {place}", "Посмотреть"),
        "friend_new": ("🤝 Вы с <b>{name}</b> теперь друзья — видно, кто куда идёт", "Открыть"),
        "broadcast": ("📣 {org}: <b>{title}</b>", "Читать"),
        "important": ("❗️ {org}: <b>{title}</b>", "Читать"),
        "event_update": ("📣 Обновление по <b>{title}</b> от {org}", "Открыть"),
        "rate": ("💬 Как прошло <b>{title}</b>? Оцени в одно касание — клуб увидит только среднюю оценку.", "Оценить"),
        "club_application": ("🆕 Заявка на новый клуб: <b>{name}</b>", "Открыть заявки"),
        "club_yes": ("🎉 Клуб <b>{name}</b> открыт, ты его президент! Зови команду и публикуй первое событие.", "Открыть клуб"),
        "club_handover": ("👑 Ты теперь президент <b>{name}</b>: прежний президент удалил аккаунт.", "Открыть клуб"),
        "club_official": ("✅ <b>{name}</b> теперь официальный клуб КБТУ. Поздравляем команду!", "Открыть клуб"),
        "club_no": ("📝 Заявку на клуб <b>{name}</b> пока не одобрили. Причина — в приложении.", "Посмотреть"),
        "achievement": ("🏅 Новое достижение: <b>{name}</b>{tier}", "Посмотреть"),
        "photo_report": ("📸 Фото с <b>{title}</b> уже в альбоме — {n} шт. Добавь свои!", "Смотреть фото"),
        "comment_question": ("💬 Новый вопрос под <b>{title}</b>", "Ответить"),
        "comment_answer": ("💬 Ответ на твой вопрос под <b>{title}</b> — от {org}", "Посмотреть"),
        "comment_reply": ("💬 Тебе ответили в комментариях под <b>{title}</b>", "Посмотреть"),
        "delete_soon": ("🗑 Твой аккаунт KBTU App удалится <b>{when}</b>: билеты, награды, друзья, клубы. Передумал — открой приложение и нажми «Оставить аккаунт».", "Оставить аккаунт"),
        "chat_pick": ("💬 Выбери канал или группу, которые стоит добавить в каталог чатов КБТУ — кнопкой ниже. Или просто пришли сюда @username.", None),
        "chat_buttons": ("📢 Выбрать канал", "👥 Выбрать группу"),
        "chat_signin": ("Чтобы предложить чат, сначала войди в KBTU App.", "🚀 Открыть KBTU App"),
        "chat_sent": ("✅ «{title}» отправлен на проверку. Как только его добавят в каталог — напишу.", None),
        "chat_exists": ("👌 Этот чат уже есть в каталоге.", None),
        "chat_org": ("👌 Этот чат уже есть в приложении — на странице своего клуба.", None),
        "chat_waiting": ("⏳ Этот канал или группа уже на проверке — скоро посмотрим.", None),
        "chat_limit": ("На сегодня хватит — завтра можно предложить ещё 🙂", None),
        "chat_private": ("Пришли @username чата или ссылку на него — подойдёт и приглашение t.me/+…", None),
        "chat_invite": ("🔒 Это закрытый чат — пришли сюда ссылку-приглашение на него (t.me/+…), и я передам его на проверку.", None),
        "chat_later": ("⏳ Telegram сейчас не ответил — попробуй через минуту.", None),
        "chat_notchat": ("🤔 Не нашёл такой канал или группу. Проверь @username.", None),
        "ask_match": ("🙋 Нужен человек со скиллом «{skill}»: {title}", "Открыть"),
        "ask_stop": ("🔕 Не присылать такие", None),
        "ask_stopped": ("🔕 Хорошо, такие запросы больше не пришлю. Включить снова можно в KBTU App.", None),
        "contact_ask": ("🤝 {name} хочет помочь с «{title}». Примешь — и вы оба получите контакты друг друга.", None),
        "contact_ask_plain": ("🤝 {name} ({skills}) хочет с тобой связаться. Примешь — и вы оба получите контакты друг друга.", None),
        "contact_buttons": ("✅ Принять", "Отклонить"),
        "contact_ok": ("✅ Ты на связи с {name}. Можно писать!", "✍️ Написать"),
        "contact_yes": ("✅ Принято — контакты отправлены вам обоим.", None),
        "contact_no": ("Отклонено. Человек об этом не узнает.", None),
        "contact_gone": ("Этот запрос уже неактуален.", None),
        "ask_hidden": ("Твой запрос «{title}» скрыт: {why}.", "Открыть"),
        "chat_whose_one": ("📢 Это канал или группа «{club}»? Тогда он появится на странице клуба.", "Нет, просто в каталог"),
        "chat_whose": ("📢 Это канал или группа одного из твоих клубов? Тогда он появится на странице клуба.", "Нет, просто в каталог"),
        "chat_bound": ("✅ Готово — чат теперь на странице «{club}». Чтобы посты канала шли и в ленту приложения, включи это в Студии.", "⚙️ Открыть в Студии"),
        "chat_bind_taken": ("🤔 Этот чат уже привязан к другому клубу. Если это ошибка — напиши в поддержку.", None),
        "chat_bind_catalog": ("👌 Этот чат уже в каталоге КБТУ. Чтобы привязать его к «{club}», напиши в поддержку — команда приложения перенесёт.", None),
        "chat_bind_limit": ("У «{club}» уже 12 чатов — больше на страницу не поместится.", None),
        "chat_bind_no": ("Привязать чат к клубу могут только его президент и вице.", None),
        "sched_signin": ("Чтобы загрузить расписание, сначала войди в KBTU App через Microsoft.", "🚀 Открыть KBTU App"),
        "sched_ok": ("🗓 Готово — занятий в неделе: {n}. Проверь их в приложении.", "🗓 Проверить в приложении"),
        "sched_not": ("🤔 В этом файле нет расписания на неделю. Открой на портале «Расписание» и сохрани именно эту страницу.", None),
        "sched_bad": ("Не получилось прочитать файл. Сохрани страницу ещё раз (iPhone: «Веб-архив», Android: «Скачать страницу») и пришли сюда.", None),
        "sched_other": ("🔒 Это расписание другого студента: имя на странице не совпадает с твоим. Загрузить можно только своё.", None),
        "sched_big": ("Файл слишком большой — сохрани только страницу расписания.", None),
        "chat_suggested": ("💬 Предложенные чаты ждут проверки: {n}", "Открыть"),
        "chat_approved": ("🎉 Твой чат «{title}» теперь в каталоге КБТУ — спасибо!", "Открыть каталог"),
        "backup_failed": ("⚠️ Вторую ночь подряд копия базы не ушла в облако (R2). Посмотри логи сервера: строки «offsite».", None),
        "id_clash": ("🪪 Номер студенческого <b>{sid}</b> указали двое:\n1. {aname}, {amail}, <a href=\"tg://user?id={aid}\">{atg}</a> — вошёл сейчас\n2. {bname}, {bmail}, <a href=\"tg://user?id={bid}\">{btg}</a> — был раньше\nСпроси обоих. Отдать номер: unlink у второго, первый вводит номер заново.", None),
        "probation_passed": ("🎉 Испытательный срок в <b>{org}</b> пройден — ты полноправный участник!", "Открыть клуб"),
        "removal_ask": ("🙋 {by} просит убрать <b>{name}</b> из {org}{ban}. Реши в приложении.", "Открыть команду"),
    },
    "kk": {
        "exit": ("🚪 <b>ҚБТУ-дан шығатын жол керек пе?</b>\nБатырманы бас, жақын аудиторияның нөмірін жаз — қосымша ашық шығуға дейін апарады.", "🚪 Шығуды табу"),
        "welcome": ("👋 Бұл — <b>KBTU App</b>: ҚБТУ іс-шаралары мен клубтары, сабақ кестең және корпус картасы.\nБәрі қосымшаның ішінде — аш 👇", "🚀 KBTU App ашу"),
        "remind_2h": ("⏰ 2 сағаттан кейін — <b>{title}</b>\n📍 {place}\nБилет қосымшада.", "🎟 Билетті ашу"),
        "remind_2h_team": ("⏰ 2 сағаттан кейін — <b>{title}</b>\n📍 {place}", "Іс-шараны ашу"),
        "seat_free_team": ("🎉 Орын босады — сен <b>{title}</b> іс-шарасына барасың!\n🗓 {when} · {place}", "Іс-шараны ашу"),
        "event_changed": ("✏️ Өзгеріс: <b>{title}</b>\n🗓 {when} · {place}", "Қарау"),
        "event_cancelled": ("😔 <b>{title}</b> ({when}) тоқтатылды. Афишада басқа да іс-шаралар бар.", "Афишаны ашу"),
        "new_event": ("✨ {org}: <b>{title}</b>\n🗓 {when} · {place}", "🎟 Толығырақ"),
        "going_ok": ("✅ Сен <b>{title}</b> іс-шарасына тіркелдің\n🗓 {when} · {place}\nБилет қосымшада.", "🎟 Билетті ашу"),
        "going_ok_team": ("✅ Сен <b>{title}</b> іс-шарасына тіркелдің\n🗓 {when} · {place}", "Іс-шараны ашу"),
        "seat_free": ("🎉 Орын босады — сен <b>{title}</b> іс-шарасына барасың!\n🗓 {when} · {place}", "🎟 Менің билетім"),
        "seat_hold": ("🎉 <b>{title}</b> іс-шарасында орын босады!\n🗓 {when} · {place}\n30 минут ішінде төлеп, чекті жүкте, әйтпесе орын келесі адамға өтеді.", "💳 Төлеу"),
        "receipt_rejected": ("😔 <b>{title}</b> ұйымдастырушылары ({org}) чегіңді қабылдамады, билет енді жарамсыз. Қате болса, оларға жаз.", "Іс-шараны ашу"),
        "receipt_ok": ("🎟 Чек қабылданды — сен <b>{title}</b> іс-шарасына барасың!\nБилет қосымшада.", "🎟 Билетті ашу"),
        "round_open": ("📣 <b>{org}</b> адам қабылдап жатыр! Өтінім — бір минут: клуб KBTU-дан сен туралы білетіннің бәрі толтырылған. Қабылдау {until} дейін.", "📝 Өтінім беру"),
        "round_interview": ("🎤 Сен <b>{org}</b> қабылдауының бірінші кезеңінен өттің! Сұхбат уақытын таңда.", "🗓 Уақыт таңдау"),
        "round_iv_nudge": ("⏰ <b>{org}</b> күтіп отыр: сен әлі сұхбат уақытын таңдамадың.", "🗓 Уақыт таңдау"),
        "round_iv_remind": ("🎤 <b>{org}</b> сұхбаты: {when}\n📍 {place}", "Ашу"),
        "round_yes": ("🎉 Сені <b>{org}</b> қабылдады! Командаға қош келдің.", "Клубты ашу"),
        "round_yes_dept": ("🎉 Сені <b>{org}</b> қабылдады, департаментің — <b>{dept}</b>! Командаға қош келдің.", "Клубты ашу"),
        "round_no": ("💙 <b>{org}</b> клубына өтінім бергенің үшін рақмет. Бұл жолы болмады — келесі қабылдауда байқап көр. Басқа клубтар дәл қазір адам қабылдап жатыр.", "Клубтар"),
        "memo_ready": ("📝 Келесі аптаға ДМП-ға қызметтік жазба дайын: «{org}», іс-шаралар: {n}. ДМП оны бүгін 18:00-ге дейін қабылдайды — тексеріп, ҚБТУ поштасынан жібер.", "📝 Жазбаны ашу"),
        "saved_tomorrow": ("🔖 Сен сақтаған — бұл ертең:\n{list}\nОйласаң, орын бар.", "🎟 Қарау"),
        "place_tba": ("📍 Іс-шараның әлі орны жоқ:\n{list}\nДМП аудитория бергенде, оны іс-шараға жаз — қатысушылар оны еске салғышта көреді.", "Іс-шараны ашу"),
        "receipt_check": ("🎟 <b>{title}</b> билеті сенікі.\n⚠️ Бірақ чек бұл іс-шараның төлеміне ұқсамайды: {why}. Файлды қате жіберсең, чекті билетте ауыстыр — ұйымдастырушы жаңасын көреді.", "🎟 Билетті ашу"),
        "receipt_which": ("🧾 Бұл чек қай іс-шара үшін?", None),
        "receipt_none": ("🧾 Бұл чек не үшін екенін таба алмадым. Алдымен қосымшада ақылы іс-шарадағы «Барамын» батырмасын бас, содан кейін чекті осында жібер.", "🚀 KBTU App ашу"),
        "receipt_late": ("⌛ <b>{title}</b> бронының мерзімі өтті, чекті байланыстыратын ештеңе жоқ. Орын қалса, «Барамын» батырмасын қайта басып, чекті тағы жібер. Орын болмаса, ақшаны қайтару үшін ұйымдастырушыларға жаз.", "Іс-шараны ашу"),
        "receipt_not": ("😕 Бұл Kaspi чегі емес. Чектің өзін жібер: Kaspi → төлем → «Бөлісу» → Telegram, немесе оның скриншотын.", None),
        "receipt_bad": ("😕 Файлды аша алмадым. Kaspi-дегі чекті («Бөлісу» → Telegram) немесе оның скриншотын жібер.", None),
        "receipt_signin": ("🧾 Чек есептелуі үшін алдымен KBTU App-қа ҚБТУ аккаунтыңмен кір.", "🚀 KBTU App ашу"),
        "join_request": ("🙋 Жаңа өтінім — <b>{org}</b>: {name}", "Өтінімдерді ашу"),
        "roster_claim": ("📋 {name} ДМП тізіміндегі <b>{org}</b> мүшесі өзі екенін айтады, бірақ тізімдегі аты басқа. Растайсың ба?", "Ашу"),
        "join_yes": ("🎉 Сен <b>{org}</b> құрамына қабылдандың! Командаға қош келдің.", "Клубты ашу"),
        "join_no": ("💙 <b>{org}</b> әзірге сені қабылдай алмайды. Басқа клубтарды қарап шық — олар көп.", None),
        "friend_request": ("🙋 <b>{name}</b> сені KBTU App-та досқа қосқысы келеді", "Жауап беру"),
        "volunteer_yes": ("🙌 Сен <b>{title}</b> ({org}) іс-шарасының волонтерісің!\n🗓 {when} · {place}\nҰйымдастырушылар не істеу керегін жазады.", "Ашу"),
        "volunteer_no": ("🙏 <b>{title}</b> ({org}) іс-шарасына волонтерлер жеткілікті. Рахмет! Қонақ болып кел.", "Ашу"),
        "leaders_invite": ("📣 {org} клуб жетекшілерін шақырады: <b>{title}</b>\n🗓 {when} · {place}\nҚосымшада жауап бер: келесің бе, жоқ па.", "Жауап беру"),
        "meeting_invite": ("📌 {org}: міндетті жиналыс <b>{title}</b>\n🗓 {when} · {place}\nҚосымшада жауап бер: келесің бе, жоқ па (келмесең, себебін жаз).", "Жауап беру"),
        "friend_invite": ("🎟 <b>{name}</b> сені <b>{title}</b> іс-шарасына шақырады\n🗓 {when} · {place}", "Қарау"),
        "friend_new": ("🤝 Сен <b>{name}</b> екеуің енді доссыңдар — кім қайда баратыны көрінеді", "Ашу"),
        "broadcast": ("📣 {org}: <b>{title}</b>", "Оқу"),
        "important": ("❗️ {org}: <b>{title}</b>", "Оқу"),
        "event_update": ("📣 <b>{title}</b> бойынша {org} жаңалығы", "Ашу"),
        "rate": ("💬 <b>{title}</b> қалай өтті? Бір түртумен бағала — клуб тек орташа бағаны көреді.", "Бағалау"),
        "club_application": ("🆕 Жаңа клубқа өтінім: <b>{name}</b>", "Өтінімдерді ашу"),
        "club_yes": ("🎉 <b>{name}</b> клубы ашылды, сен оның президентісің! Команда жина да, алғашқы іс-шараны жарияла.", "Клубты ашу"),
        "club_handover": ("👑 Енді <b>{name}</b> президенті сенсің: бұрынғы президент аккаунтын өшірді.", "Клубты ашу"),
        "club_official": ("✅ <b>{name}</b> енді ҚБТУ-дың ресми клубы. Команданы құттықтаймыз!", "Клубты ашу"),
        "club_no": ("📝 <b>{name}</b> клубына өтінім әзірге мақұлданбады. Себебі — қосымшада.", "Қарау"),
        "achievement": ("🏅 Жаңа жетістік: <b>{name}</b>{tier}", "Қарау"),
        "photo_report": ("📸 <b>{title}</b> фотолары альбомда — {n} дана. Өзіңдікін де қос!", "Фотоларды көру"),
        "comment_question": ("💬 <b>{title}</b> астында жаңа сұрақ", "Жауап беру"),
        "comment_answer": ("💬 <b>{title}</b> астындағы сұрағыңа жауап — {org}", "Қарау"),
        "comment_reply": ("💬 <b>{title}</b> астындағы пікіріңе жауап келді", "Қарау"),
        "delete_soon": ("🗑 KBTU App аккаунтың <b>{when}</b> өшіріледі: билеттер, марапаттар, достар, клубтар. Ойыңды өзгерттің бе — қосымшаны ашып, «Аккаунтты қалдыру» бас.", "Аккаунтты қалдыру"),
        "chat_pick": ("💬 ҚБТУ чаттар каталогына қосуға тұрарлық арнаны не топты төмендегі батырмамен таңда. Немесе мұнда жай ғана @username жібер.", None),
        "chat_buttons": ("📢 Арнаны таңдау", "👥 Топты таңдау"),
        "chat_signin": ("Чат ұсыну үшін алдымен KBTU App-қа кір.", "🚀 KBTU App ашу"),
        "chat_sent": ("✅ «{title}» тексеруге жіберілді. Каталогқа қосылғанда — жазамын.", None),
        "chat_exists": ("👌 Бұл чат каталогта бар.", None),
        "chat_org": ("👌 Бұл чат қосымшада бар — өз клубының бетінде.", None),
        "chat_waiting": ("⏳ Бұл арна не топ қазір тексеруде — жақында қараймыз.", None),
        "chat_limit": ("Бүгінге жетеді — ертең тағы ұсына аласың 🙂", None),
        "chat_private": ("Чаттың @username-ін не сілтемесін жібер — t.me/+… шақыру сілтемесі де жарайды.", None),
        "chat_invite": ("🔒 Бұл жабық чат — оның шақыру сілтемесін (t.me/+…) осында жібер, мен оны тексеруге беремін.", None),
        "chat_later": ("⏳ Telegram қазір жауап бермеді — бір минуттан кейін қайтала.", None),
        "chat_notchat": ("🤔 Мұндай арна не топ табылмады. @username-ді тексер.", None),
        "ask_match": ("🙋 «{skill}» дағдысы бар адам керек: {title}", "Ашу"),
        "ask_stop": ("🔕 Мұндайларды жібермеу", None),
        "ask_stopped": ("🔕 Жақсы, мұндай сұраулар енді келмейді. Қайта қосу — KBTU App-та.", None),
        "contact_ask": ("🤝 {name} «{title}» бойынша көмектескісі келеді. Қабылдасаң — екеуің де бір-біріңнің байланысын аласыңдар.", None),
        "contact_ask_plain": ("🤝 {name} ({skills}) сенімен байланысқысы келеді. Қабылдасаң — екеуің де бір-біріңнің байланысын аласыңдар.", None),
        "contact_buttons": ("✅ Қабылдау", "Бас тарту"),
        "contact_ok": ("✅ {name} екеуің байланыстасыңдар. Жаза бер!", "✍️ Жазу"),
        "contact_yes": ("✅ Қабылданды — байланыстар екеуіңе де жіберілді.", None),
        "contact_no": ("Бас тартылды. Ол адам бұл туралы білмейді.", None),
        "contact_gone": ("Бұл сұрау енді өзекті емес.", None),
        "ask_hidden": ("«{title}» сұрауың жасырылды: {why}.", "Ашу"),
        "chat_whose_one": ("📢 Бұл «{club}» арнасы не тобы ма? Онда ол клуб бетінде шығады.", "Жоқ, жай каталогқа"),
        "chat_whose": ("📢 Бұл сенің клубтарыңның бірінің арнасы не тобы ма? Онда ол клуб бетінде шығады.", "Жоқ, жай каталогқа"),
        "chat_bound": ("✅ Дайын — чат енді «{club}» бетінде. Арна посттары қосымшаның лентасында да шықсын десең, Студияда қос.", "⚙️ Студияда ашу"),
        "chat_bind_taken": ("🤔 Бұл чат басқа клубқа байланған. Қате болса — қолдауға жаз.", None),
        "chat_bind_catalog": ("👌 Бұл чат ҚБТУ каталогында бар. Оны «{club}» клубына байлау үшін қолдауға жаз — қосымша командасы ауыстырады.", None),
        "chat_bind_limit": ("«{club}» клубында 12 чат бар — бетке бұдан көп сыймайды.", None),
        "chat_bind_no": ("Чатты клубқа тек оның президенті мен вице-президенті байлай алады.", None),
        "sched_signin": ("Кестені жүктеу үшін алдымен KBTU App-қа Microsoft арқылы кір.", "🚀 KBTU App ашу"),
        "sched_ok": ("🗓 Дайын — аптадағы сабақтар: {n}. Қосымшада тексер.", "🗓 Қосымшада тексеру"),
        "sched_not": ("🤔 Бұл файлда апталық кесте жоқ. Порталда «Кестені» ашып, дәл сол бетті сақта.", None),
        "sched_bad": ("Файлды оқи алмадым. Бетті қайта сақта (iPhone: «Веб-архив», Android: «Бетті жүктеу») да, осында жібер.", None),
        "sched_other": ("🔒 Бұл басқа студенттің кестесі: беттегі аты сенікімен сәйкес емес. Тек өз кестеңді жүктей аласың.", None),
        "sched_big": ("Файл тым үлкен — тек кесте бетін сақта.", None),
        "chat_suggested": ("💬 Ұсынылған чаттар тексеруді күтуде: {n}", "Ашу"),
        "chat_approved": ("🎉 Сенің «{title}» чатың енді ҚБТУ каталогында — рахмет!", "Каталогты ашу"),
        "backup_failed": ("⚠️ Қатарынан екінші түн дерекқор көшірмесі бұлтқа (R2) жіберілмеді. Сервер логтарын қара: «offsite» жолдары.", None),
        "id_clash": ("🪪 <b>{sid}</b> студент нөмірін екі адам көрсетті:\n1. {aname}, {amail}, <a href=\"tg://user?id={aid}\">{atg}</a> — қазір кірді\n2. {bname}, {bmail}, <a href=\"tg://user?id={bid}\">{btg}</a> — бұрын болған\nЕкеуінен сұра. Нөмірді беру: екіншісіне unlink, біріншісі нөмірді қайта енгізеді.", None),
        "probation_passed": ("🎉 <b>{org}</b> клубындағы сынақ мерзімі аяқталды — сен толыққанды мүшесің!", "Клубты ашу"),
        "removal_ask": ("🙋 {by} <b>{name}</b> мүшесін {org} клубынан шығаруды сұрайды{ban}. Қосымшада шеш.", "Команданы ашу"),
    },
    "en": {
        "exit": ("🚪 <b>Looking for the way out of KBTU?</b>\nTap the button, type the nearest room number — the app leads you to an open exit.", "🚪 Find the exit"),
        "welcome": ("👋 This is <b>KBTU App</b>: KBTU's events and clubs, your class schedule and the campus map.\nIt's all inside the app — open it 👇", "🚀 Open KBTU App"),
        "remind_2h": ("⏰ In 2 hours — <b>{title}</b>\n📍 {place}\nYour ticket is in the app.", "🎟 Open ticket"),
        "remind_2h_team": ("⏰ In 2 hours — <b>{title}</b>\n📍 {place}", "Open the event"),
        "seat_free_team": ("🎉 A seat opened up — you're going to <b>{title}</b>!\n🗓 {when} · {place}", "Open the event"),
        "event_changed": ("✏️ Changed: <b>{title}</b>\n🗓 {when} · {place}", "View"),
        "event_cancelled": ("😔 <b>{title}</b> ({when}) is cancelled. There's more in the events list.", "Open events"),
        "new_event": ("✨ {org}: <b>{title}</b>\n🗓 {when} · {place}", "🎟 Details"),
        "going_ok": ("✅ You're going to <b>{title}</b>\n🗓 {when} · {place}\nYour ticket is in the app.", "🎟 Open ticket"),
        "going_ok_team": ("✅ You're going to <b>{title}</b>\n🗓 {when} · {place}", "Open the event"),
        "seat_free": ("🎉 A seat opened up — you're going to <b>{title}</b>!\n🗓 {when} · {place}", "🎟 My ticket"),
        "seat_hold": ("🎉 A seat opened up at <b>{title}</b>!\n🗓 {when} · {place}\nPay and upload the receipt within 30 minutes, or it goes to the next person.", "💳 Pay"),
        "receipt_rejected": ("😔 The organizers of <b>{title}</b> ({org}) rejected your receipt; the ticket no longer works. If it's a mistake, write to them.", "Open the event"),
        "receipt_ok": ("🎟 Receipt accepted — you're going to <b>{title}</b>!\nYour ticket is in the app.", "🎟 Open the ticket"),
        "round_open": ("📣 <b>{org}</b> is recruiting! Applying takes a minute: what the club knows about you from KBTU is filled in already. Until {until}.", "📝 Apply"),
        "round_interview": ("🎤 You passed the first stage at <b>{org}</b>! Pick a time for the interview.", "🗓 Pick a time"),
        "round_iv_nudge": ("⏰ <b>{org}</b> is waiting: you haven't picked an interview time yet.", "🗓 Pick a time"),
        "round_iv_remind": ("🎤 Interview at <b>{org}</b>: {when}\n📍 {place}", "Open"),
        "round_yes": ("🎉 You're in <b>{org}</b>! Welcome to the team.", "Open the club"),
        "round_yes_dept": ("🎉 You're in <b>{org}</b>, your department is <b>{dept}</b>! Welcome to the team.", "Open the club"),
        "round_no": ("💙 Thank you for applying to <b>{org}</b>. It didn't work out this time: try the next round. Other clubs are recruiting right now.", "Clubs"),
        "memo_ready": ("📝 Next week's memo for DMP is ready: {org}, events: {n}. DMP takes it today until 18:00: check it and send it from your KBTU mail.", "📝 Open the memo"),
        "saved_tomorrow": ("🔖 You saved it, and it's tomorrow:\n{list}\nThere's still time to sign up.", "🎟 Have a look"),
        "place_tba": ("📍 Your event still has no place:\n{list}\nWhen DMP gives you a room, put it in the event: the participants will see it in their reminder.", "Open the event"),
        "receipt_check": ("🎟 The ticket to <b>{title}</b> is yours.\n⚠️ But the receipt doesn't look like this event's payment: {why}. If you sent the wrong file, replace the receipt in the ticket: the organizer will see the new one.", "🎟 Open the ticket"),
        "receipt_which": ("🧾 Which event is this receipt for?", None),
        "receipt_none": ("🧾 I couldn't find what this receipt is for. First tap “I'm going” on a paid event in the app, then send the receipt here.", "🚀 Open KBTU App"),
        "receipt_late": ("⌛ Your hold on <b>{title}</b> has expired, so there's nothing to attach the receipt to. If seats are left, tap “I'm going” again and send the receipt again. If not, ask the organizers for a refund.", "Open the event"),
        "receipt_not": ("😕 That isn't a Kaspi receipt. Send the receipt itself: Kaspi → the payment → “Share” → Telegram, or a screenshot of it.", None),
        "receipt_bad": ("😕 I couldn't open the file. Send the receipt from Kaspi (“Share” → Telegram) or a screenshot of it.", None),
        "receipt_signin": ("🧾 To count your receipt, first sign in to KBTU App with your KBTU account.", "🚀 Open KBTU App"),
        "join_request": ("🙋 New application to <b>{org}</b>: {name}", "Open applications"),
        "roster_claim": ("📋 {name} says they're the one in the DMP list of <b>{org}</b>, but the list has another name. Confirm?", "Open"),
        "join_yes": ("🎉 You're in <b>{org}</b>! Welcome to the team.", "Open the club"),
        "join_no": ("💙 <b>{org}</b> can't take you in right now. Have a look at the other clubs — there are plenty.", None),
        "friend_request": ("🙋 <b>{name}</b> wants to be friends on KBTU App", "Reply"),
        "volunteer_yes": ("🙌 You're a volunteer at <b>{title}</b> ({org})!\n🗓 {when} · {place}\nThe organizers will tell you what to do.", "Open"),
        "volunteer_no": ("🙏 <b>{title}</b> ({org}) has enough volunteers already. Thanks for offering! Come as a guest.", "Open"),
        "leaders_invite": ("📣 {org} invites club leaders: <b>{title}</b>\n🗓 {when} · {place}\nAnswer in the app: coming or not.", "Answer"),
        "meeting_invite": ("📌 {org}: a required meeting, <b>{title}</b>\n🗓 {when} · {place}\nAnswer in the app: coming or not (if not, say why).", "Answer"),
        "friend_invite": ("🎟 <b>{name}</b> invites you to <b>{title}</b>\n🗓 {when} · {place}", "Take a look"),
        "friend_new": ("🤝 You and <b>{name}</b> are friends now — you'll see where each other is going", "Open"),
        "broadcast": ("📣 {org}: <b>{title}</b>", "Read"),
        "important": ("❗️ {org}: <b>{title}</b>", "Read"),
        "event_update": ("📣 An update on <b>{title}</b> from {org}", "Open"),
        "rate": ("💬 How was <b>{title}</b>? Rate it in one tap — the club only sees the average.", "Rate"),
        "club_application": ("🆕 An application for a new club: <b>{name}</b>", "Open applications"),
        "club_yes": ("🎉 <b>{name}</b> is open and you're its President! Gather your team and publish the first event.", "Open the club"),
        "club_handover": ("👑 You are now the president of <b>{name}</b>: the previous president deleted their account.", "Open the club"),
        "club_official": ("✅ <b>{name}</b> is now an official KBTU club. Congratulations to the team!", "Open the club"),
        "club_no": ("📝 The application for <b>{name}</b> wasn't approved for now. The reason is in the app.", "See"),
        "achievement": ("🏅 A new achievement: <b>{name}</b>{tier}", "See it"),
        "photo_report": ("📸 Photos from <b>{title}</b> are in the album: {n} so far. Add yours!", "See the photos"),
        "comment_question": ("💬 A new question under <b>{title}</b>", "Answer"),
        "comment_answer": ("💬 {org} answered your question under <b>{title}</b>", "See"),
        "comment_reply": ("💬 Someone replied to your comment under <b>{title}</b>", "View"),
        "delete_soon": ("🗑 Your KBTU App account will be deleted on <b>{when}</b>: tickets, awards, friends, clubs. Changed your mind? Open the app and tap “Keep my account”.", "Keep my account"),
        "chat_pick": ("💬 Pick a channel or group worth adding to KBTU's chats catalog with the buttons below. Or just send its @username here.", None),
        "chat_buttons": ("📢 Pick a channel", "👥 Pick a group"),
        "chat_signin": ("To suggest a chat, sign in to KBTU App first.", "🚀 Open KBTU App"),
        "chat_sent": ("✅ “{title}” is sent for review. I'll write once it's in the catalog.", None),
        "chat_exists": ("👌 This chat is already in the catalog.", None),
        "chat_org": ("👌 This chat is already in the app, on its club's page.", None),
        "chat_waiting": ("⏳ This channel or group is already waiting for review — we'll look soon.", None),
        "chat_limit": ("That's enough for today — you can suggest more tomorrow 🙂", None),
        "chat_private": ("Send the chat's @username or a link to it — an invite link t.me/+… works too.", None),
        "chat_invite": ("🔒 That's a closed chat — send its invite link here (t.me/+…) and I'll pass it on for review.", None),
        "chat_later": ("⏳ Telegram didn't answer just now — try again in a minute.", None),
        "chat_notchat": ("🤔 Couldn't find such a channel or group. Check the @username.", None),
        "ask_match": ("🙋 Someone needs {skill}: {title}", "Open"),
        "ask_stop": ("🔕 Don't send these", None),
        "ask_stopped": ("🔕 Got it, no more requests like this. You can turn them back on in KBTU App.", None),
        "contact_ask": ("🤝 {name} wants to help with “{title}”. Accept, and you both get each other's contact.", None),
        "contact_ask_plain": ("🤝 {name} ({skills}) wants to get in touch. Accept, and you both get each other's contact.", None),
        "contact_buttons": ("✅ Accept", "Decline"),
        "contact_ok": ("✅ You're in touch with {name}. Go ahead and write!", "✍️ Write"),
        "contact_yes": ("✅ Accepted: you both have each other's contact now.", None),
        "contact_no": ("Declined. They won't be told.", None),
        "contact_gone": ("This one isn't open any more.", None),
        "ask_hidden": ("Your request “{title}” is hidden: {why}.", "Open"),
        "chat_whose_one": ("📢 Is this {club}'s channel or group? Then it shows on the club's page.", "No, just the catalog"),
        "chat_whose": ("📢 Is this one of your clubs' channels or groups? Then it shows on the club's page.", "No, just the catalog"),
        "chat_bound": ("✅ Done: the chat is on {club}'s page now. To show the channel's posts in the app's feed too, turn it on in Studio.", "⚙️ Open in Studio"),
        "chat_bind_taken": ("🤔 This chat is already linked to another club. If that's a mistake, write to support.", None),
        "chat_bind_catalog": ("👌 This chat is already in KBTU's catalog. To link it to {club}, write to support: the app's team moves it.", None),
        "chat_bind_limit": ("{club} already has 12 chats: no more fit on its page.", None),
        "chat_bind_no": ("Only a club's President and Vice can link a chat to it.", None),
        "sched_signin": ("To load your schedule, sign in to KBTU App with Microsoft first.", "🚀 Open KBTU App"),
        "sched_ok": ("🗓 Done: {n} classes in your week. Check them in the app.", "🗓 Check in the app"),
        "sched_not": ("🤔 There's no week's schedule in this file. Open Schedule on the portal and save that page.", None),
        "sched_bad": ("Couldn't read the file. Save the page again (iPhone: Web Archive, Android: Download page) and send it here.", None),
        "sched_other": ("🔒 This is another student's schedule: the name on the page isn't yours. Only your own can be loaded.", None),
        "sched_big": ("The file is too big: save just the schedule page.", None),
        "chat_suggested": ("💬 Suggested chats waiting for review: {n}", "Open"),
        "chat_approved": ("🎉 Your chat “{title}” is now in KBTU's catalog — thanks!", "Open the catalog"),
        "backup_failed": ("⚠️ For the second night in a row the database copy didn't reach the cloud (R2). Check the server logs: the \"offsite\" lines.", None),
        "id_clash": ("🪪 Two people gave student ID <b>{sid}</b>:\n1. {aname}, {amail}, <a href=\"tg://user?id={aid}\">{atg}</a> — signing in now\n2. {bname}, {bmail}, <a href=\"tg://user?id={bid}\">{btg}</a> — had it before\nAsk both. To move the ID: unlink the second, the first types it again.", None),
        "probation_passed": ("🎉 You passed probation in <b>{org}</b>: you're a full member now!", "Open the club"),
        "removal_ask": ("🙋 {by} asks to remove <b>{name}</b> from {org}{ban}. Decide in the app.", "Open the team"),
    },
}


# why a receipt looks wrong, as the student reads it (the flags of logic._receipt_flags)
RECEIPT_WHY = {
    "ru": {"duplicate": "этот чек уже присылали", "unreadable": "не похоже на чек Kaspi", "amount_short": "сумма меньше цены",
           "amount_over": "сумма не совпадает с ценой", "recipient_mismatch": "другой получатель", "too_early": "чек старше самого события"},
    "kk": {"duplicate": "бұл чекті бұрын жіберген", "unreadable": "Kaspi чегіне ұқсамайды", "amount_short": "сома бағадан аз",
           "amount_over": "сома бағаға сай емес", "recipient_mismatch": "алушы басқа", "too_early": "чек іс-шарадан ескі"},
    "en": {"duplicate": "this receipt was sent before", "unreadable": "it doesn't look like a Kaspi receipt", "amount_short": "the sum is less than the price",
           "amount_over": "the sum doesn't match the price", "recipient_mismatch": "another recipient", "too_early": "it's older than the event itself"},
}


# why a forum request was hidden, said to its author (forum.hide_ask)
ASK_WHY = {
    "ru": {"reports": "на него пожаловались, и проверка это подтвердила", "moderator": "так решил модератор"},
    "kk": {"reports": "оған шағымданды, тексеру мұны растады", "moderator": "модератор осылай шешті"},
    "en": {"reports": "people reported it and the check agreed", "moderator": "a moderator decided so"},
}


def pick(table: dict, lang: str):
    """A table's entry for the language, Russian when it has none."""
    return table[lang if lang in table else "ru"]


def receipt_why(lang: str, flags: list[str]) -> str:
    words = pick(RECEIPT_WHY, lang)
    return ", ".join(words[f] for f in flags if f in words)


def bot_message(lang: str, kind: str, **fields: object) -> tuple[str, str | None]:
    text, button = pick(BOT, lang)[kind]
    return text.format(**{k: html.escape(str(v)) for k, v in fields.items()}), button


# The attendee list as a CSV (SPEC §6): headers and statuses in the organizer's language.
# "Year of study", not "course", in what DMP reads (their rule for forms: KBTU has years of study, not courses).
CSV_HEAD = {
    "ru": ("Фамилия", "Имя", "Telegram", "ID студента", "Год обучения", "Школа", "Почта", "Телефон", "Статус", "Записался", "Пришёл", "Записан у входа", "Отмечен вручную"),
    "kk": ("Тегі", "Аты", "Telegram", "Студент ID", "Курс", "Мектеп", "Пошта", "Телефон", "Мәртебе", "Жазылды", "Келді", "Кіре берісте тіркелді", "Қолмен белгіленді"),
    "en": ("Last name", "First name", "Telegram", "Student ID", "Year of study", "School", "Email", "Phone", "Status", "Registered", "Came", "At the door", "Checked in by hand"),
}
CSV_STATUS = {
    "ru": {"going": "идёт", "hold": "ждёт оплату", "waitlist": "лист ожидания", "yes": "да"},
    "kk": {"going": "барады", "hold": "төлемді күтуде", "waitlist": "күту тізімі", "yes": "иә"},
    "en": {"going": "going", "hold": "awaiting payment", "waitlist": "waitlist", "yes": "yes"},
}
CSV_CAPTION = {"ru": "Участники: {title}", "kk": "Қатысушылар: {title}", "en": "Attendees: {title}"}


def _cell(v) -> str:
    """A cell a spreadsheet would run as a formula (= + - @, or a tab or CR before one) gets a leading quote; a phone
    number shows the same."""
    s = "" if v is None else str(v)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s


REGISTRY_HEAD = {
    "ru": ("Клуб", "Роль", "Фамилия", "Имя", "ID студента", "Год обучения", "Школа", "В клубе с", "Telegram", "Почта", "Телефон"),
    "kk": ("Клуб", "Рөл", "Тегі", "Аты", "Студент ID", "Курс", "Мектеп", "Клубта", "Telegram", "Пошта", "Телефон"),
    "en": ("Club", "Role", "Last name", "First name", "Student ID", "Year of study", "School", "Member since", "Telegram", "Email", "Phone"),
}
REGISTRY_CAPTION = {"ru": "Реестр клубов KBTU App", "kk": "KBTU App клубтар тізілімі", "en": "KBTU App clubs registry"}


def registry_csv(lang: str, people) -> tuple[str, bytes, str]:
    """Every roster (DMP, §4.13): the same rules as on screen — contacts only of Presidents and Vices."""
    lang = lang if lang in REGISTRY_HEAD else "ru"
    out = io.StringIO()
    w = csv.writer(out, delimiter=";")
    w.writerow(REGISTRY_HEAD[lang])
    day = lambda ts: time.strftime("%Y-%m-%d", time.gmtime(ts + 5 * 3600)) if ts else ""  # noqa: E731
    roles = {"president": "President", "vice": "Vice", "head": "Head", "member": "Member"}  # English in every language, as in the app
    for p in people:
        lead = p["role"] in ("president", "vice")
        w.writerow([_cell(x) for x in (p["club"], roles[p["role"]], p["last_name"], p["first_name"], p["student_id"], p["course"], p["school"],
                                       day(p["joined_at"]), p["tg_username"] if lead else "", p["email"] if lead else "", p["phone"] if lead else "")])
    return "kbtu-clubs.csv", ("\ufeff" + out.getvalue()).encode(), REGISTRY_CAPTION[lang]


def attendees_csv(lang: str, title: str, people) -> tuple[str, bytes, str]:
    """(file name, the file, caption): UTF-8 with a BOM and ';' so Excel opens it right in Russian and Kazakh."""
    st, out = CSV_STATUS[lang], io.StringIO()
    w = csv.writer(out, delimiter=";")
    w.writerow(CSV_HEAD[lang])
    stamp = lambda ts: time.strftime("%Y-%m-%d %H:%M", time.gmtime(ts + 5 * 3600)) if ts else ""
    for p in people:
        w.writerow([_cell(x) for x in (p["last_name"], p["first_name"], p["tg_username"], p["student_id"], p["course"], p["school"], p["email"],
                                       p["phone"], st[p["status"]], stamp(p["created_at"]), stamp(p["checked_in_at"]), st["yes"] if p["walk_in"] else "",
                                       st["yes"] if p["checkin_manual"] else "")])
    return "attendees.csv", ("\ufeff" + out.getvalue()).encode(), CSV_CAPTION[lang].format(title=title)[:1000]


# ---- DMP's memo (служебная записка), from their template "ШАБЛОН СЛУЖЕБНЫЕ ЗАПИСКИ" and a year of StudEx's
# real memos: in Russian, one memo for the week's events, every request numbered, the signature in kk, ru, en;
# one email to youth_policy@kbtu.kz, sent on Wednesday 9:00-18:00 from the sender's KBTU address.
MEMO_TO = "youth_policy@kbtu.kz"
WEEKDAYS_RU = ("понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье")
MEMO_SIDES = {"tole": "Толе би", "kazybek": "Казыбек би", "abylai": "Абылай хана"}

# ---- Memo v2 (PLAN stage 2): one memo for the week, the events' requests grouped under each event, numbered through,
# the sender's signature once in kk, ru and en.
MEMO2_TO = "Департаменту по Молодежной Политике"
MEMO2_TITLE = ("Служебная записка", "Комплексная служебная записка")  # one event / two or more
MEMO2_INTRO = ("Студенческая организация «{org}» планирует проведение мероприятия {events}. В связи с этим просим Вас:",
               "Студенческая организация «{org}» планирует проведение мероприятий: {events}. В связи с этим просим Вас:")
MEMO2_EVENT = "«{title}» {day} г."                       # in the intro, joined by ", "; day = '20 октября 2026'
MEMO2_FOR = {"event": "В целях проведения мероприятия «{title}» ({when}) просим Вас:",
             "meeting": "В целях проведения собрания «{title}» ({when}) просим Вас:"}  # only with two or more events
MEMO2_SIGN = {"kk": ("Ізгі құрметпен,", "«{org}» студенттік ұйымының {pos}"),
              "ru": ("С уважением,", "{pos} студенческой организации «{org}»"),
              "en": ("Regards and best wishes,", "{pos} of Student Organization «{org}»")}  # each block: these, name, phone
MEMO2_SIGN_SPLIT = "-------"
# the sender's position in the three blocks: a level, or a club role whose name has one of the words (any language)
MEMO2_POS = {"president": {"kk": "президенті", "ru": "Президент", "en": "President"},
             "vice": {"kk": "вице-президенті", "ru": "Вице-президент", "en": "Vice President"},
             "secretary": {"kk": "хатшысы", "ru": "Секретарь", "en": "Secretary"},
             "manager": {"kk": "менеджері", "ru": "Менеджер", "en": "Manager"},
             "head": {"kk": "бағыт жетекшісі", "ru": "Руководитель направления", "en": "Head of Department"},
             "member": {"kk": "мүшесі", "ru": "Член", "en": "Member"}}
MEMO2_POS_WORDS = {"secretary": ("secretar", "секретар", "хатшы"), "vice": ("vice", "вице"), "president": ("president", "президент"),
                   "manager": ("manager", "менеджер"), "head": ("head", "руковод", "жетекші", "басшы")}  # checked in this order
# new and changed requests
MEMO2_ROOM_EXTRA = {"projector": "проектором", "board": "доской"}  # "... с проектором и доской вместимостью N человек"
MEMO2_DORM = "Разрешить проведение мероприятия в студенческом общежитии KBTU Jastar City"  # + "\nЛокация: ..." if given
MEMO2_DORM_SIDES = {"turgut": "Тургут Озала", "karimov": "Ислама Каримова"}  # the dorm's gates, "со стороны улицы ..."
MEMO2_GUESTS_DORM = "Разрешить вход гостям (по списку) в студенческое общежитие KBTU Jastar City со стороны улицы {side}:"
MEMO2_PROVIDE = {"jbl": "колонку JBL PartyBox", "tables": "столы: {n} шт.", "chairs": "стулья: {n} шт.", "mixer": "микшер",
                 "cooler": "кулер и стаканы: {n} шт."}   # "Предоставить: a; b; c." then the event's date, time and place
MEMO2_PROVIDE_HEAD = "Предоставить: {items}."
MEMO2_QUIET = "Студенты проинструктированы, мешать проведению занятий не будут."  # after a request with the speaker
MEMO2_DENSITY = ("70-100", "110-150", "200-250")   # "Плотность бумаги: {d} г/м2"
MEMO2_FILM = "Разрешить съёмку в студии КБТУ:"     # then "Дата:", "Время:", "Примечание:" as the other requests
MEMO2_BLANK = "Студенческая организация «{org}» просит Вас:"  # the memo with nothing from the events: the sender writes it
MEMO2_DATES = "Даты: {dates}"
def channel_post(title: str, org: str, starts: int, place: str, price: int | None, cancelled: bool, link: str = "",
                 also: list[str] = ()) -> str:
    """A public event's post in the events channel (HTML), in Russian: the channel's language; `also`: the title in the
    other languages (ai.py), in italics under it. Signing up is a link in
    the text, not a button: Telegram hides a post's comments under a button."""
    lines = [f"<b>{html.escape(title)}</b>", *(f"<i>{html.escape(x)}</i>" for x in dict.fromkeys(also)), html.escape(org), "", f"🗓 {when(starts, 'ru')}", f"📍 {html.escape(place_or_tba(place, 'ru'))}",
             f"💸 {price} ₸" if price else "🆓 Бесплатно"]
    if link and not cancelled:
        lines += ["", f'👉 <a href="{html.escape(link)}">Записаться в KBTU App</a>']
    return ("❌ <b>ОТМЕНЕНО</b>\n\n" if cancelled else "") + "\n".join(lines)


CHANNEL_BUTTON = "Записаться"
# the bot's first comment under each event's post in the channel's discussion group: the rules, and the sign-up again
CHANNEL_RULES = ("💬 Здесь обсуждаем событие: вопросы организаторам, кто идёт, впечатления после.\n\n"
                 "Правила: без оскорблений, спама и рекламы. Такие сообщения удаляются, авторы получают бан.")
# an event's Telegram group (bot.py _group): what the bot says there, in Russian (a group has no one language)
CHAT_LINKED = "✅ Чат привязан к событию «{title}». Записавшиеся найдут ссылку в приложении, бот пускает только их."
CHAT_BAD = "Эта ссылка устарела или не твоя. Нажми «Создать чат» в приложении ещё раз."
CHAT_NO_RIGHTS = "Мне нужны права админа «Пригласительные ссылки». Дай их и нажми «Создать чат» в приложении ещё раз."                      # promo over several days: "13, 14, 15 октября и 3 ноября 2026 г."


def memo_day(ts: int) -> str:
    """'20 ноября 2026 (пятница)' in Almaty time."""
    t = time.gmtime(ts + 5 * 3600)
    return f"{t.tm_mday} {MONTHS['ru'][t.tm_mon - 1]} {t.tm_year} ({WEEKDAYS_RU[t.tm_wday]})"


def _hm(ts: int) -> str:
    t = time.gmtime(ts + 5 * 3600)
    return f"{t.tm_hour:02d}:{t.tm_min:02d}"


def _lines(s: object) -> list[str]:
    return [x.strip() for x in str(s or "").splitlines() if x.strip()]


def _day_of(date: object, fallback: int) -> str:
    """A form's 'YYYY-MM-DD' as the memo writes it (its own day), else the event's."""
    try:
        y, m, d = (int(x) for x in str(date).split("-"))
        return memo_day(calendar.timegm((y, m, d, 12, 0, 0)) - 5 * 3600)
    except (ValueError, OverflowError):
        return memo_day(fallback)


def _num(x: object) -> int | None:
    try:
        n = int(x)  # type: ignore[call-overload]
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def _dates(days: list[str]) -> str:
    """'13, 14, 15 октября и 3 ноября 2026' from 'YYYY-MM-DD' days, grouped by month (a promo over several days)."""
    got = sorted({(int(y), int(m), int(d)) for y, m, d in (x.split("-") for x in days if re.fullmatch(r"\d{4}-\d{2}-\d{2}", x))})
    months: list[tuple[int, int, list[int]]] = []
    for y, m, d in got:
        if months and months[-1][:2] == (y, m):
            months[-1][2].append(d)
        else:
            months.append((y, m, [d]))
    parts = [f"{', '.join(map(str, ds))} {MONTHS['ru'][m - 1]}" for _, m, ds in months]
    return (", ".join(parts[:-1]) + " и " + parts[-1] if len(parts) > 1 else parts[0] if parts else "") + (f" {got[-1][0]}" if got else "")


def memo_asks(e: dict, memo: dict) -> list[str]:
    """One event's requests to DMP, each a numbered item's text (the numbers are the caller's: they run through the
    week's memo). e has title, starts_at, ends_at, place ('' while to be confirmed), room (the number in the place, or
    None), off (an off-campus place: no room to book there), seats."""
    start, end = e["starts_at"], e["ends_at"] or e["starts_at"] + 3 * 3600
    when, hours = memo_day(start), f"{_hm(start)}-{_hm(end)}"
    place = e["place"] or "уточняется"
    asks: list[str] = []
    if (r := memo.get("room")) is not None and not e.get("off"):  # off campus: no room of KBTU's to book
        slots = f"Дата: {when}\nВремя: {hours}" + "".join(
            f"\nДата: {_day_of(x.get('date'), start)}\nВремя: {x.get('from') or _hm(start)}-{x.get('to') or _hm(end)}"
            for x in r.get("slots") or [] if isinstance(x, dict) and x.get("date"))
        if r.get("dorm"):
            where = " ".join(str(r.get("dormPlace") or "").split())
            asks.append(MEMO2_DORM + (f"\nЛокация: {where}" if where else "") + "\n" + slots)
        else:
            cap = _num(r.get("capacity")) or e["seats"]
            kit = [MEMO2_ROOM_EXTRA[k] for k in MEMO2_ROOM_EXTRA if r.get(k)]
            extra = (" с " + " и ".join(kit) if kit else "") + (f" вместимостью {cap} человек" if cap else "")
            named = f"аудиторию №{e['room']}" if e["room"] else f"«{e['place']}»" if e["place"] else ""
            what = named + (f" (или любую другую аудиторию{extra})" if r.get("any", True) else extra) if named else f"любую аудиторию{extra}"
            asks.append(f"Забронировать {what}:\n{slots}")
    if (g := memo.get("guests")) is not None:
        names = "\n".join(_lines(g.get("list"))) or "(список гостей)"
        head = MEMO2_GUESTS_DORM.format(side=MEMO2_DORM_SIDES[g["side"]]) if g.get("side") in MEMO2_DORM_SIDES else \
            f"Разрешить вход гостям (по списку) со стороны {MEMO_SIDES.get(str(g.get('side')), MEMO_SIDES['tole'])}:"
        asks.append(f"{head}\nФИО гостей, университет/компания:\n{names}\nДата: {when}\nВремя: {hours}\nАудитория: {place}")
    if (p := memo.get("provide")) is not None:
        items = [MEMO2_PROVIDE[k].format(n=_num(p.get(k)) or 1) for k in MEMO2_PROVIDE if p.get(k)]
        items += [" ".join(str(p.get("other") or "").split())] if str(p.get("other") or "").strip() else []
        asks.append(MEMO2_PROVIDE_HEAD.format(items="; ".join(items).rstrip(".") or "(что предоставить)") + f"\nДата: {when}\nВремя: {hours}\nЛокация: {place}"
                    + ("\n" + MEMO2_QUIET if p.get("jbl") else ""))
    if (p := memo.get("promo")) is not None:
        spot = " ".join(str(p.get("place") or "").split()) or "(место)"
        also = f" Также просим предоставить {' '.join(str(p['extras']).split())}." if str(p.get("extras") or "").strip() else ""
        days = [str(x) for x in p.get("dates") or [] if x] or ([str(p["date"])] if p.get("date") else [])
        day = MEMO2_DATES.format(dates=_dates(days)) if len(days) > 1 else f"Дата: {_day_of(days[0] if days else None, start)}"
        asks.append(f"Разрешить проведение промо-акции: {spot}.{also} Студенты проинструктированы, чистота и порядок будут обеспечены.\n"
                    f"{day}\nВремя: {p.get('from') or _hm(start)}-{p.get('to') or _hm(end)}\nЛокация: {spot}")
    if (q := memo.get("gear")) is not None:
        out, back = bool(q.get("outDate")), bool(q.get("inDate"))
        verb = "вывоз и последующий ввоз" if out and back else "вывоз" if out else "ввоз"
        side = MEMO_SIDES.get(str(q.get("side")), MEMO_SIDES["kazybek"])
        items = "\n".join(f"{i}) {x}" for i, x in enumerate(_lines(q.get("items")), 1)) or "(список оборудования)"
        dates = (f"\nДата вывоза: {_day_of(q['outDate'], start)}\nВремя вывоза: {q.get('outTime') or ''}" if out else "") + \
                (f"\nДата ввоза: {_day_of(q['inDate'], start)}\nВремя ввоза: {q.get('inTime') or ''}" if back else "")
        where = " ".join(str(q.get("location") or "").split())
        asks.append(f"Разрешить {verb} оборудования (по списку) со стороны улицы {side}.\nСписок оборудования:\n{items}{dates}"
                    + (f"\nЛокация: {where}" if where else ""))
    # printing is not DMP's: it goes in its own letter to the Publishing Center (print_letter)
    if (f := memo.get("film")) is not None:
        note = " ".join(str(f.get("note") or "").split())
        asks.append(f"{MEMO2_FILM}\nДата: {_day_of(f.get('date'), start)}\nВремя: {f.get('from') or _hm(start)}-{f.get('to') or _hm(end)}"
                    + (f"\nПримечание: {note}" if note else ""))
    return asks


PRINT_TO = "ic@kbtu.kz"  # the Publishing Center takes print requests straight, files attached


def print_items(pr: dict) -> list[str]:
    """One event's files to print, each 'Наименование: ...' with count, format, colour, paper, note."""
    out = []
    for x in [x for x in pr.get("items") or [] if isinstance(x, dict) and str(x.get("name") or "").strip()]:
        d = x.get("density") if x.get("density") in (0, 1, 2) else 0
        out.append(f"Наименование: {str(x['name']).strip()}\nКоличество: {x.get('count') or 1}\nФормат: {x.get('format') or 'А4'}\n"
                   f"Цветность: {'чёрно-белая' if x.get('bw') else 'цветная'}\nПлотность бумаги: {MEMO2_DENSITY[d]} г/м2"
                   + (f"\nПримечание: {' '.join(str(x['note']).split())}" if str(x.get("note") or "").strip() else ""))
    return out


def print_letter(org: str, events: list[tuple[dict, dict]], pos: str, name: str, phone: str | None) -> tuple[str, str]:
    """(subject, text) of the letter to the Publishing Center: the events' files numbered through, signed in Russian."""
    listed = [(e, print_items(m["print"])) for e, m in events if m.get("print")]
    day = lambda e: memo_day(e["starts_at"]).split(" (")[0] + " г."  # noqa: E731
    out = ["Здравствуйте!", "", f"Студенческая организация «{org}» просит распечатать материалы "
           + (f"к мероприятию «{listed[0][0]['title']}» ({day(listed[0][0])}):" if len(listed) == 1 else "к мероприятиям:")]
    n = 0
    for e, items in listed:
        if len(listed) > 1:
            out += ["", f"«{e['title']}» ({day(e)}):"]
        for x in items or ["(что печатать)"]:
            n += 1
            out.append(f"{n}) {x}")
    out += ["", "Файлы во вложении.", "", MEMO2_SIGN["ru"][0], MEMO2_SIGN["ru"][1].format(org=org, pos=pos), name, phone or "(номер телефона)"]
    return f"Печать для «{org}»: " + ", ".join(f"«{e['title']}»" for e, _ in listed), "\n".join(out)


def memo_text(org: str, events: list[tuple[dict, dict]], sign: str) -> str:
    """The week's one memo (PLAN stage 2): events are (e as memo_asks takes it plus `meeting`, its requests). With one
    event its requests follow the intro; with more each event's line heads its own, numbered through. With none, the
    blank: the header, "asks you:" and the signature, for the sheet's templates."""
    if not events:
        return "\n".join([MEMO2_TO, MEMO2_TITLE[0], "", MEMO2_BLANK.format(org=org)]) + "\n\n" + sign
    many = len(events) > 1
    listed = ", ".join(MEMO2_EVENT.format(title=e["title"], day=memo_day(e["starts_at"]).split(" (")[0]) for e, _ in events)
    out, n = [MEMO2_TO, MEMO2_TITLE[many], "", MEMO2_INTRO[many].format(org=org, events=listed).replace("г..", "г.")], 0
    for e, memo in events:
        if many:
            day = memo_day(e["starts_at"]).split(" (")[0] + " г."
            out += ["", MEMO2_FOR["meeting" if e.get("meeting") else "event"].format(title=e["title"], when=day)]
        for a in memo_asks(e, memo):
            n += 1
            out.append(f"{n}) {a}")
    return "\n".join(out) + "\n\n" + sign


def memo_sign(org: str, pos: dict[str, str], name: str, name_en: str, phone: str | None) -> str:
    """The signature once at the end: kk, ru and en blocks, each the formula, the position line, the name, the phone."""
    tel = phone or "(номер телефона)"
    return f"\n{MEMO2_SIGN_SPLIT}\n".join(f"{MEMO2_SIGN[lang][0]}\n{MEMO2_SIGN[lang][1].format(org=org, pos=pos[lang])}\n"
                                           f"{name_en if lang == 'en' else name}\n{tel}" for lang in ("kk", "ru", "en"))


def memo_pos(level: str, title: str | None) -> dict[str, str]:
    """The sender's position in kk, ru, en: a club role whose name has a known word (secretary first), else the role's
    name as typed in all three, else the level's."""
    if title:
        low = title.lower()
        hit = next((k for k, words in MEMO2_POS_WORDS.items() if any(w in low for w in words)), None)
        return dict(MEMO2_POS[hit]) if hit else {"kk": title, "ru": title, "en": title}
    return dict(MEMO2_POS.get(level, MEMO2_POS["member"]))


def memo_subject(org: str, monday: int) -> str:
    a, b = time.gmtime(monday + 5 * 3600), time.gmtime(monday + 6 * 86400 + 5 * 3600)
    span = f"{a.tm_mday}-{b.tm_mday} {MONTHS['ru'][b.tm_mon - 1]}" if a.tm_mon == b.tm_mon else \
        f"{a.tm_mday} {MONTHS['ru'][a.tm_mon - 1]} - {b.tm_mday} {MONTHS['ru'][b.tm_mon - 1]}"
    return f"Служебные записки «{org}» на {span}"


def phone_line(phone: str | None) -> str | None:
    """'+7 701 234 56 78' from the portal's or the editor's number (as the app's lib/phone.ts)."""
    d = "".join(c for c in str(phone or "") if c.isdigit())[-10:]
    return f"+7 {d[:3]} {d[3:6]} {d[6:8]} {d[8:]}" if len(d) == 10 else None


def place_or_tba(place: str, lang: str) -> str:
    """An event's place in a bot message; empty while it's to be confirmed (a room asked of DMP by memo)."""
    return place or {"ru": "место уточняется", "kk": "орны нақтыланады", "en": "place to be confirmed"}.get(lang, "место уточняется")


# /ms.html, where Microsoft sends a student back (msauth.py): the browser outside Telegram, its language picks the set.
# Each state: a title and a line.
MS_PAGE = {
    "ru": {"wait": ("Секунду…", "Проверяем аккаунт КБТУ"),
           "ok": ("Готово!", "Возвращаем в Telegram…"),
           "nope": ("Ничего не привязали", "Можешь просто закрыть эту страницу."),
           "fail": ("Не получилось", "Закрой страницу и попробуй ещё раз из приложения."),
           "linked": ("Аккаунт уже занят", "Этот аккаунт КБТУ привязан к другому Telegram. Напиши @Sowers, если это ошибка."),
           "otherMs": ("Уже подтверждено", "Твой профиль подтверждён другим аккаунтом КБТУ."),
           "notKbtu": ("Нужен аккаунт КБТУ", "Войди с логином вида s_familiya@kbtu.kz — личный или чужой аккаунт Microsoft не подойдёт. Вернись в приложение и попробуй снова."),
           "expired": ("Ссылка устарела", "Ссылка для входа живёт 15 минут. Вернись в приложение и нажми кнопку ещё раз."),
           "open": "Вернуться в Telegram"},
    "kk": {"wait": ("Бір сәт…", "ҚБТУ аккаунты тексерілуде"),
           "ok": ("Дайын!", "Telegram-ға қайтарамыз…"),
           "nope": ("Ештеңе байланбады", "Бұл бетті жаба бер."),
           "fail": ("Болмады", "Бетті жауып, қосымшадан қайта көр."),
           "linked": ("Аккаунт бос емес", "Бұл ҚБТУ аккаунты басқа Telegram-ға байланған. Қате болса, @Sowers-ке жаз."),
           "otherMs": ("Расталған", "Профилің басқа ҚБТУ аккаунтымен расталған."),
           "notKbtu": ("ҚБТУ аккаунты керек", "s_tegi@kbtu.kz түріндегі логинмен кір — жеке не басқа Microsoft аккаунты келмейді. Қосымшаға оралып, қайта көр."),
           "expired": ("Сілтеменің мерзімі өтті", "Кіру сілтемесі 15 минут жарамды. Қосымшаға оралып, батырманы қайта бас."),
           "open": "Telegram-ға оралу"},
    "en": {"wait": ("One moment…", "Checking your KBTU account"),
           "ok": ("Done!", "Taking you back to Telegram…"),
           "nope": ("Nothing linked", "You can just close this page."),
           "fail": ("Didn't work", "Close this page and try again from the app."),
           "linked": ("Account taken", "This KBTU account is linked to another Telegram. Write to @Sowers if that's a mistake."),
           "otherMs": ("Already confirmed", "Your profile is confirmed with another KBTU account."),
           "notKbtu": ("A KBTU account is needed", "Sign in with your login like s_lastname@kbtu.kz — a personal or another organization's Microsoft account won't work. Go back to the app and try again."),
           "expired": ("The link expired", "A sign-in link lasts 15 minutes. Go back to the app and tap the button again."),
           "open": "Back to Telegram"},
}
