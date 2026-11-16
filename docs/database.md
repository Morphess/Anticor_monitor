# PostgreSQL і FastAPI — Issue #5

[Issue #5](https://github.com/Morphess/Anticor_monitor/issues/5).
Окремий сервіс `db`: PostgreSQL `17.12-bookworm`, перевірка готовності
через `pg_isready`, іменований volume `bordergroup_postgres_data` у Compose-проєкті
`bordergroup`. Порт 5432 не публікується на хості; доступ — усередині мережі Compose.
Контейнери, мережі та дані Zabbix не використовуються.

## Підготовка та перевірка без запуску

Потрібен Docker із Compose v2+; команди виконуються з кореня репозиторію.
Якщо `.env` ще немає:

```sh
cp .env.example .env
chmod 600 .env
```

У локальному `.env` задайте непорожній унікальний `POSTGRES_PASSWORD`.
Приклад навмисно не містить пароля; без нього Compose відхиляє конфігурацію.
`POSTGRES_USER=postgres` — обліковий запис лише для адміністрування та початкової
перевірки БД, не для застосунку.
Для FastAPI заповніть `DATABASE_URL` окремого користувача застосунку, а також
`APP_NAME`, `DEBUG`, `SQL_ECHO` за прикладом `.env.example`. Створення користувача
та його права потрібно узгодити з бекенд-розробником; ця конфігурація не створює
його автоматично. Compose перевіряє ці змінні навіть для команди запуску лише `db`.
Не додавайте `.env` чи файли секретів у Git. Не виводьте повний результат
`docker compose config`: він містить підставлений пароль. Безпечна перевірка:

```sh
docker compose config --quiet
```

## Запуск і перевірка БД

Наведені нижче команди запускають сервіс: виконуйте лише після погодження
з відповідальним за сервер. Під час підготовки цієї конфігурації їх не запускали.

```sh
docker compose up -d --wait db
docker compose ps db
docker compose exec -T db sh -c 'PGPASSWORD="$POSTGRES_PASSWORD" psql -h 127.0.0.1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -c "SELECT 1;"'
```

Очікується статус `healthy` і результат `1` від SQL-запиту.
Healthcheck перевіряє готовність TCP-сервера, SQL-запит — також автентифікацію.
Пароль передається всередині контейнера та не друкується командою.

Дані зберігаються в іменованому volume. `POSTGRES_*` ініціалізують лише порожній
volume: зміна `.env` не змінює пароль чи назву вже створеної БД.
Не використовуйте `docker compose down -v`: це видаляє дані проєкту.
Не підключайте наявні volumes або каталоги Zabbix.

## FastAPI: збірка та запуск після рев’ю

```sh
docker compose build api
# Лише після рев’ю, узгодження користувача БД та способу VPN-доступу:
docker compose up -d api
docker compose ps api
docker compose exec -T api python -c 'import urllib.request; print(urllib.request.urlopen("http://127.0.0.1:8000/").read().decode()); print(urllib.request.urlopen("http://127.0.0.1:8000/db").read().decode())'
```

Очікується `{"Hello":"World"}` і `{"status":"ok","database":"connected"}`.
До появи користувача БД та правильного `DATABASE_URL` `/db` повертає 503.
Сервіс `api` чекає на `db` через `depends_on.db.condition: service_healthy`;
готовність PostgreSQL не гарантує правильних облікових даних застосунку.

Контейнеру передаються лише `DATABASE_URL`, `APP_NAME`, `DEBUG`, `SQL_ECHO`;
`env_file` не використовується, адміністративний `POSTGRES_PASSWORD` не передається.
Для поточного SQLAlchemy/psycopg потрібен формат:
`postgresql+psycopg://<app_user>:<URL-encoded-password>@db:5432/<POSTGRES_DB>`.
FastAPI не використовує `POSTGRES_USER`. Спеціальні символи облікових даних
потрібно percent-encode; справжній URL — лише в локальному `.env`.

Dockerfile використовує кореневий `requirements.txt`, зберігає `/app/backend/app`
і `/app/frontend`, запускає `uvicorn app.main:app` із `/app/backend` без root.
Поточний `main.py` шукає ресурси в `/app/frontend`. Dockerfile створює
`/app/frontend/static`, який вимагає `StaticFiles`. Код `backend/app/**` не змінюється.
`.dockerignore` допускає лише залежності, код застосунку та ресурси фронтенду;
локальні `.env` і файли секретів не потрапляють у build context чи образ.

## Доступ команди через Tailscale

`api` публікує порт контейнера `8000` тільки на `127.0.0.1:8001` сервера.
Порт БД на хості не публікується. Portainer на порту `8000` не зачіпається.

Після злиття PR, оновлення `main` на сервері та запуску `api` перевірте
`http://127.0.0.1:8001/` і `http://127.0.0.1:8001/db` на самому сервері.
Потім увімкніть доступ для учасників tailnet:

    tailscale serve --bg 8001
    tailscale serve status

Serve надрукує HTTPS-адресу сервера в tailnet. Передайте її учасникам,
які мають доступ за правилами Tailscale. Якщо Tailscale попросить
увімкнути HTTPS-сертифікати, виконайте його підказки.
Не використовуйте Tailscale Funnel: він публікує сервіс в інтернеті.
