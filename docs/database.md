# PostgreSQL, дані та файлове сховище

Для першого локального запуску використовуйте **5 кроків [README](../README.md)**:
окремий проєкт `bordergroup-demo`, `.env.demo`, випадкові секрети,
міграції та `demo_admin`. Нижче — опис конфігурації, не альтернативний
шлях початкового наповнення. Команди production — у [release.md](release.md).

## Compose і облікові записи

`db` використовує PostgreSQL 17.12-bookworm з приватним портом 5432,
healthcheck `pg_isready` та volume `postgres_data`. Типові production-назви
volumes: `bordergroup_postgres_data`, `bordergroup_order_documents`,
`bordergroup_report_exports`; префікс залежить від Compose-проєкту.
Не підключайте сторонні volumes й не виконуйте `down -v` на production.

`POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` потрібні контейнеру БД.
API отримує `DATABASE_URL` окремо; також APP_NAME, DEBUG, SQL_ECHO,
JWT_SECRET_KEY, CORS_ORIGINS, налаштування Ollama та шляхи сховищ.
Адміністративний POSTGRES_PASSWORD не передається API.

Для production потрібні окремі адміністративна й прикладна ролі БД
з погодженими правами міграцій. Demo використовує власного demo_user
в окремій порожній БД; це спрощення для відтворюваної демонстрації.
URL: `postgresql+psycopg://<user>:<percent-encoded-password>@db:5432/<db>`.
Зміна POSTGRES_* не переініціалізує вже наявний volume і не змінює пароль.

Кореневий `.env`/`.env.demo` підставляє змінні Compose. Сам застосунок
також підтримує `DB_ENV=local|server` і env-файл у backend через Settings;
у Docker джерелом значень є передані environment. Секрети не комітити
й не друкувати повним `docker compose config`; перевірка — `config --quiet`.

## Міграції й початкові ролі

Канонічний шлях — кореневий `alembic.ini` та `alembic/`, у контейнері
`alembic -c /app/alembic.ini upgrade head`. Окрему історію
`backend/alembic/` не змішувати з нею й не підміняти ревізію через stamp.

Ревізія d2511200abcd гарантує ADMIN, MAIN_KOORD, KOORD, VYK, KER.
Історична ANAL лишається в БД, але нові призначення й вхід заборонено.
`bootstrap_demo` створює адміністратора тільки в названій демо-БД і
відмовляє при вже наявних користувачах. Для оновлення існуючого demo
достатньо rebuild api та upgrade head, повторний bootstrap не потрібен.

## Що зберігається де

| Дані | Сховище |
|---|---|
| Програми, заходи, подання, ролі, показники, журнал, метадані звітів | PostgreSQL |
| Версії наказів | Приватний volume, `/app/storage/orders` |
| JSON-снапшоти піврічних звітів | Приватний volume, `/app/storage/reports` |
| Тексти аналізів ШІ | Там само, підкаталог `analyses` |
| Ваги моделі | `ollama_data` |

Файли доступні через авторизовані API, не через StaticFiles. Для
висновків з БД залишається можливість читання legacy-тексту до завершення
перевіреного перенесення; нові записи містять файлове посилання.
Раніше створені AnalyticsReport вилученого кабінету не видаляються
автоматично — це історичний архів, а не активний модуль звітності.

## Перевірка і доступ

`/health` повертає status=ok; `/db` — status=connected, database=PostgreSQL,
result=1. Готовність healthcheck БД не доводить правильності DATABASE_URL.
Кореневий `/` відкриває сторінку входу, не стару JSON-відповідь Hello World.

API типово публікує `127.0.0.1:8001`, PostgreSQL — без host port.
Для командного доступу сервер використовує Tailscale Serve; локальний
demo не потребує VPN. Якщо потрібен SSH-тунель до БД, не фіксуйте
мінливу IP-адресу контейнера без повторної перевірки стану мережі.

Резервна копія БД без документів/звітів неповна: зберігайте погоджену
пару дамп+архів сховищ і перевіряйте відновлення в окремому контурі.
