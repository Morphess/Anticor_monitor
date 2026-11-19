#!/usr/bin/env bash
set -euo pipefail

repo_root="${1:?Вкажіть шлях до робочого каталогу репозиторію}"
env_file="${2:?Вкажіть шлях до env-файлу}"
backup_dir="${3:?Вкажіть каталог резервних копій}"
compose_project="${4:?Вкажіть назву Compose-проєкту}"

request="${SSH_ORIGINAL_COMMAND:-}"

if [[ ! "$request" =~ ^deploy\ ([0-9a-f]{40})$ ]]; then
    echo "Очікується команда: deploy <повний SHA коміту>" >&2
    exit 1
fi

commit="${BASH_REMATCH[1]}"

if [[ ! -d "$repo_root" || ! -f "$env_file" || ! -d "$backup_dir" ]]; then
    echo "Репозиторій, env-файл або каталог резервних копій не знайдено." >&2
    exit 1
fi

if [[ "$repo_root" != /* || "$env_file" != /* || "$backup_dir" != /* ]]; then
    echo "Потрібні абсолютні шляхи." >&2
    exit 1
fi

cd "$repo_root"

umask 077
exec 8>"$backup_dir/.cd-gate.lock"

if ! flock -n 8; then
    echo "Інший запуск CD вже виконується." >&2
    exit 1
fi

if ! git diff --quiet || ! git diff --cached --quiet; then
    echo "У відстежуваних файлах є незакомічені зміни." >&2
    exit 1
fi

echo "Оновлення локального посилання origin/main..."

GIT_TERMINAL_PROMPT=0 \
GIT_SSH_COMMAND='ssh -o BatchMode=yes' \
git fetch origin main

main_commit="$(git rev-parse --verify refs/remotes/origin/main)"

if [[ "$commit" != "$main_commit" ]]; then
    echo "SHA має збігатися з актуальною origin/main." >&2
    exit 1
fi

stage_dir="$(mktemp -d /tmp/bordergroup-cd-stage.XXXXXX)"

echo "Створення worktree: $stage_dir"

(
    umask 022
    git worktree add --detach "$stage_dir" "$commit"
)

echo "Запуск контрольованого розгортання..."

(
    cd "$stage_dir"

    env -i \
        HOME="$HOME" \
        PATH="$PATH" \
        COMPOSE_PROJECT_NAME="$compose_project" \
        bash scripts/deploy.sh "$env_file" "$backup_dir" "$commit"
)

echo "Прибирання тимчасового worktree..."

if git worktree remove "$stage_dir"; then
    echo "Тимчасовий worktree видалено."
else
    echo "Не вдалося видалити worktree: $stage_dir" >&2
    echo "Розгортання пройшло, але каталог потрібно перевірити." >&2
    exit 1
fi
