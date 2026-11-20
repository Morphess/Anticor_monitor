#!/usr/bin/env bash
set -euo pipefail

# Запускати з кореня worktree, який використовується для розгортання.
# Перший аргумент — шлях до серверного .env.
env_file="${1:?Вкажіть шлях до серверного .env}"
backup_dir="${2:?Вкажіть шлях до каталогу резервних копій}"
expected_commit="${3:?Вкажіть повний SHA коміту для розгортання}"

if [[ ! -f "$env_file" ]]; then
    echo "Файл налаштувань не знайдено."
    exit 1
fi

if [[ ! -f compose.yaml ]] || ! git rev-parse --show-toplevel >/dev/null 2>&1; then
    echo "Запустіть скрипт із кореня worktree проєкту."
    exit 1
fi

repo_root="$(git rev-parse --show-toplevel)"
if [[ "$PWD" != "$repo_root" ]]; then
    echo "Запустіть скрипт із кореня worktree: $repo_root"
    exit 1
fi

if ! git diff --quiet || ! git diff --cached --quiet; then
    echo "Є незакомічені зміни у відстежуваних файлах. Зупиняємося."
    exit 1
fi

untracked_build_files="$(
    git ls-files --others --exclude-standard -- \
        backend/app frontend/templates frontend/static alembic
)"

if [[ -n "$untracked_build_files" ]]; then
    echo "У файлах для збірки є неіндексовані файли. Зупиняємося."
    printf '%s\n' "$untracked_build_files"
    exit 1
fi

ignored_build_files="$(
    git ls-files --others --ignored --exclude-standard -- \
        backend/app frontend/templates frontend/static alembic
)"

if [[ -n "$ignored_build_files" ]]; then
    echo "У каталогах збірки є ігноровані Git файли. Зупиняємося."
    printf '%s\n' "$ignored_build_files"
    exit 1
fi

if [[ ! "$expected_commit" =~ ^[0-9a-f]{40}$ ]]; then
    echo "Потрібен повний SHA-1 коміту: 40 малих шістнадцяткових символів."
    exit 1
fi

actual_commit="$(git rev-parse HEAD)"

if [[ "$actual_commit" != "$expected_commit" ]]; then
    echo "Поточний коміт не збігається з обраним. Зупиняємося."
    exit 1
fi

if ! git merge-base --is-ancestor "$expected_commit" refs/remotes/origin/main; then
    echo "Обраний коміт не входить до локально відомої origin/main."
    exit 1
fi

echo "Перевірка блокування розгортання..."

umask 077
mkdir -p "$backup_dir"

exec 9>"$backup_dir/.deploy.lock"

if ! flock -n 9; then
    echo "Інше розгортання вже виконується. Зупиняємося."
    exit 1
fi

echo "Коміт для розгортання:"
git log -1 --oneline

echo "Перевірка Compose-конфігурації..."
docker compose --env-file "$env_file" config --quiet

echo "Перевірка PostgreSQL..."
db_container="$(docker compose --env-file "$env_file" ps -q db)"

if [[ -z "$db_container" ]]; then
    echo "Контейнер db не запущений."
    exit 1
fi

db_health="$(docker inspect --format '{{.State.Health.Status}}' "$db_container")"

if [[ "$db_health" != "healthy" ]]; then
    echo "PostgreSQL не готова: $db_health"
    exit 1
fi

echo "Перевірка підключення до БД..."

docker compose --env-file "$env_file" exec -T db sh -c \
    'PGPASSWORD="$POSTGRES_PASSWORD" psql \
        -h 127.0.0.1 \
        -U "$POSTGRES_USER" \
        -d "$POSTGRES_DB" \
        -v ON_ERROR_STOP=1 \
        -c "SELECT 1;"' > /dev/null

echo "Створення резервної копії БД..."

umask 077
mkdir -p "$backup_dir"

backup_file="$(mktemp "$backup_dir/bordergroup-$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX.dump")"

# Якщо створення чи перевірка архіву не вдалися, прибрати неповний файл.
trap 'rm -f -- "$backup_file"' EXIT

docker compose --env-file "$env_file" exec -T db sh -c \
    'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump \
        -h 127.0.0.1 \
        -U "$POSTGRES_USER" \
        -d "$POSTGRES_DB" \
        -Fc' > "$backup_file"

test -s "$backup_file"

docker compose --env-file "$env_file" exec -T db \
    pg_restore --list < "$backup_file" > /dev/null

trap - EXIT

stat -c 'Резервна копія: %n, %s байт, права %a' "$backup_file"

echo "Попередні перевірки пройдено. PostgreSQL: $db_health"

echo "Збереження попереднього образу API..."

api_container="$(docker compose --env-file "$env_file" ps -q api)"

if [[ -z "$api_container" ]]; then
    echo "Контейнер api не запущений. Зупиняємося."
    exit 1
fi

old_image="$(docker inspect --format '{{.Image}}' "$api_container")"
rollback_image="bordergroup-api:rollback-$(date -u +%Y%m%dT%H%M%SZ)"

docker image tag "$old_image" "$rollback_image"

echo "Попередній образ збережено як $rollback_image"

echo "Збірка образу API..."
docker compose --env-file "$env_file" build api

echo "Образ API зібрано. Контейнер ще не оновлено."

echo "Резервна копія документів і файлових звітів..."
files_backup="${backup_file%.dump}-files.tar.gz"
if ! docker compose --env-file "$env_file" run --rm --no-deps -T api \
    tar -C /app/storage -czf - orders reports > "$files_backup"; then
    rm -f -- "$files_backup"
    echo "Не вдалося створити копію файлового сховища." >&2
    exit 1
fi
test -s "$files_backup"
sha256sum "$files_backup"

echo "Звірка БД застосунку з резервною копією..."

backup_database="$(
    docker compose --env-file "$env_file" exec -T db sh -c \
        'PGPASSWORD="$POSTGRES_PASSWORD" psql \
            -h 127.0.0.1 \
            -U "$POSTGRES_USER" \
            -d "$POSTGRES_DB" \
            -v ON_ERROR_STOP=1 -At \
            -c "SELECT current_database();"'
)"

docker compose --env-file "$env_file" \
    run --rm --no-deps -T \
    -e "EXPECTED_DB_NAME=$backup_database" api python - <<'PY'
import os
from sqlalchemy.engine import make_url

try:
    url = make_url(os.environ["DATABASE_URL"])
    expected = os.environ["EXPECTED_DB_NAME"]
except Exception:
    raise SystemExit("Не вдалося перевірити DATABASE_URL")

if (
    url.get_backend_name() != "postgresql"
    or url.host != "db"
    or url.port not in (None, 5432)
    or url.database != expected
    or url.query
):
    raise SystemExit(
        "DATABASE_URL не відповідає БД сервісу db; розгортання зупинено"
    )

print("БД застосунку відповідає БД резервної копії")
PY

echo "Поточна ревізія БД:"
docker compose --env-file "$env_file" \
    run --rm --no-deps -T api \
    alembic -c /app/alembic.ini current

echo "Доступна остання ревізія:"
docker compose --env-file "$env_file" \
    run --rm --no-deps -T api \
    alembic -c /app/alembic.ini heads

echo "Застосування міграцій..."
docker compose --env-file "$env_file" \
    run --rm --no-deps -T api \
    alembic -c /app/alembic.ini upgrade head

echo "Перевірка ревізії після міграції..."
docker compose --env-file "$env_file" \
    run --rm --no-deps -T api \
    alembic -c /app/alembic.ini current --check-heads

echo "Зупинка старого API перед перенесенням висновків..."
docker compose --env-file "$env_file" stop api

echo "Перенесення наявних висновків у файлове сховище..."
docker compose --env-file "$env_file" run --rm --no-deps -T api python -m app.services.migrate_analysis_files

echo "Оновлення контейнера API..."
docker compose --env-file "$env_file" \
    up -d --no-deps --no-build --force-recreate api

echo "Перевірка API..."
curl -fsS --retry 10 --retry-delay 2 --retry-all-errors \
    --retry-max-time 120 --max-time 10 \
    http://127.0.0.1:8001/health
echo

echo "Перевірка з'єднання API з БД..."
curl -fsS --retry 10 --retry-delay 2 --retry-all-errors \
    --retry-max-time 120 --max-time 10 \
    http://127.0.0.1:8001/db
echo

echo "Розгортання завершено."
