# BorderGroup — моніторинг виконання антикорупційної програми

Команда **BorderGroup** · [Завдання 2: цифрова система моніторингу виконання антикорупційної програми](https://hack.bitec.com.ua/zavdannia-2/)
Cклад команди:
- `@demid21cher - капітан`;
- `@Morphess`;
- `@kaschenko179`;
- `@bzena434-collab`.

## Проблема і користувачі

Виконавці заходів, уповноважені особи та керівники працюють з даними антикорупційної програми, розкиданими між таблицями, документами й окремими звітами. Через це важко швидко побачити відповідального, строк, стан виконання та підтвердження результату. BorderGroup розробляє єдиний простір для ведення програми й заходів, щоб зменшити ручне зведення даних і зробити історію змін простежуваною. Прототип використовує лише синтетичні дані організаторів.

## Що робить рішення

Поточна реалізація у гілці `main`:

- Зберігає структуру програми, її розділи, заходи та пов’язані сутності в PostgreSQL.
- Надає API для входу, користувачів, програм, розділів і заходів.
- Перевіряє права доступу для частини операцій за ролями користувачів.
- Застосовує версійні міграції схеми БД через Alembic.
- Перевіряє HTTP-сценарії API та міграції в GitHub Actions.

## Демонстрація
-----
-----
##  Розгортання

Потрібні Git, Docker і Docker Compose v2+. Команди виконуються в корені репо. Для локального запуску потрібні окремий користувач застосунку в PostgreSQL і синтетичні дані; секрети не додавайте до Git.

1. Клонуйте репозиторій:

   ```sh
   git clone https://github.com/Morphess/Anticor_monitor.git
   cd Anticor_monitor
   ```

2. Створіть локальний `.env` з `.env.example`, задайте власні `POSTGRES_PASSWORD`, `DATABASE_URL` і `JWT_SECRET_KEY` та перевірте конфігурацію:

   ```sh
   cp .env.example .env
   chmod 600 .env
   # Заповніть .env у редакторі: DATABASE_URL має вказувати на db:5432.
   docker compose config --quiet
   ```

3. Запустіть PostgreSQL і створіть у ньому окремого користувача для застосунку. `POSTGRES_USER=postgres` потрібен лише для адміністрування; порядок створення ролі та права описані в [документації БД](docs/database.md):

   ```sh
   docker compose up -d --wait db
   ```

4. Застосуйте міграції:

   ```sh
   docker compose run --rm api alembic -c /app/alembic.ini upgrade head
   ```

5. Запустіть API та перевірте його на комп’ютері, де працює Docker:

   ```sh
   docker compose up --build -d api
   curl --fail http://127.0.0.1:8001/
   curl --fail http://127.0.0.1:8001/db
   ```
## Побудова

**Стек:** Python 3.13, FastAPI, Jinja2, HTML/CSS/JavaScript, PostgreSQL 17, SQLAlchemy, Alembic, Docker Compose, GitHub Actions.

```text
Клієнт → FastAPI (backend/app/api) → бізнес-логіка (services)
                                 → доступ до даних (repositories) → PostgreSQL
         HTML-шаблони й статичні файли (frontend/)
         Міграції схеми (alembic/)
```

Маршрути API підключено в `backend/app/main.py`; моделі даних лежать у `backend/app/models/`, автоматичні перевірки — у `tests/` та `.github/workflows/ci.yml`. 


## Документація

- [Використання ШІ](docs/ai.md) — інструменти, застосування та перевірка командою; записка доповнюється під час розробки.
- [PostgreSQL і розгортання](docs/database.md) — конфігурація БД, Docker Compose і доступ через Tailscale.
- [Правила внеску](CONTRIBUTING.md) — робота з гілками, PR і рев’ю.

## Що використали

- Бібліотеки й інструменти: FastAPI, Starlette, Pydantic, SQLAlchemy, Alembic, psycopg, Jinja2, Uvicorn, PyJWT, pwdlib/Argon2, Docker Compose і GitHub Actions. Точні версії Python-залежностей наведено в [`requirements.txt`](requirements.txt).
- [Синтетичний набір даних BITEC](https://hack.bitec.com.ua/wp-content/uploads/2026/11/zavdannia-2-syntetychnyi-nabir-1811daff.zip) — демонстраційні відомості; реальні персональні дані та службова інформація не використовуються.
- Інструменти ШІ та спосіб їх застосування описано в [`docs/ai.md`](docs/ai.md).

Проєкт поширюється за [ліцензією MIT](LICENSE).
