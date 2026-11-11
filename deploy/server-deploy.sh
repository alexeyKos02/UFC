#!/usr/bin/env bash
# Выкладка новой версии на сервере.
#
# Запускается из GitHub Actions по SSH: ключ деплоя в authorized_keys привязан
# к этому скрипту (command="..."), поэтому ничего другого этим ключом сделать нельзя.
# Хеш коммита приходит в SSH_ORIGINAL_COMMAND.
#
# Вручную на сервере: /opt/ufc/deploy/server-deploy.sh [хеш]   (без хеша — свежий main)
#
# Весь код внутри функции: git reset ниже перезаписывает и этот файл,
# а bash к тому моменту уже прочитал функцию целиком.

set -euo pipefail

main() {
  local app_dir=/opt/ufc
  local sha="${1:-${SSH_ORIGINAL_COMMAND:-}}"

  cd "$app_dir"

  # Две выкладки одновременно не идут.
  exec 9>/var/lock/ufc-deploy.lock
  flock -w 900 9 || { echo "Другая выкладка не закончилась за 15 минут" >&2; exit 1; }

  git fetch --quiet origin main
  [ -n "$sha" ] || sha=$(git rev-parse origin/main)

  if ! [[ "$sha" =~ ^[0-9a-f]{40}$ ]]; then
    echo "Ожидался полный хеш коммита, получено: $sha" >&2
    exit 2
  fi
  if ! git merge-base --is-ancestor "$sha" origin/main; then
    echo "Коммит $sha не входит в origin/main, выкладывать его нельзя" >&2
    exit 2
  fi

  local prev
  prev=$(git rev-parse --short HEAD)
  echo "==> Выкладка ${sha:0:7} (было $prev)"

  # Миграции применяются при старте бэкенда, поэтому сначала копия базы.
  # Старые копии удаляет общий backup.sh (хранит 14 дней).
  if [ -n "$(docker compose ps --status running -q db)" ]; then
    local dump="backups/pre-deploy-$(date +%F-%H%M%S)-${sha:0:7}.sql.gz"
    echo "==> Копия базы: $dump"
    docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB"' | gzip > "$dump"
  fi

  git reset --hard --quiet "$sha"

  echo "==> Сборка и перезапуск"
  if ! docker compose up --build -d --wait --wait-timeout 300; then
    docker compose ps
    docker compose logs --tail 80 backend frontend
    echo "Новая версия не поднялась. Откат: git revert и push в main" >&2
    exit 1
  fi

  # APP_PORT бывает просто портом (80) или адресом с портом (127.0.0.1:8080, когда впереди Caddy).
  local addr
  addr=$(sed -n 's/^APP_PORT=//p' .env | tail -n 1)
  addr=${addr:-80}
  [[ "$addr" == *:* ]] || addr="127.0.0.1:$addr"
  if ! curl -fsS --retry 10 --retry-delay 2 --retry-all-errors -o /dev/null "http://$addr/api/health"; then
    docker compose logs --tail 80 backend frontend
    echo "Сайт не отвечает на /api/health" >&2
    exit 1
  fi

  # Старые образы и кэш сборки быстро съедают 20 ГБ диска.
  docker image prune -f >/dev/null
  docker builder prune -f --filter until=72h >/dev/null

  echo "==> Готово: $(git log -1 --format='%h %s')"
}

main "$@"; exit $?
