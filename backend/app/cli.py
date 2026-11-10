"""Команды обслуживания: python -m app.cli create-owner | seed-demo."""

import argparse
import getpass
import sys

from sqlalchemy import select

from app.db import SessionLocal
from app.errors import AppError
from app.models import User, UserRole, UserStatus
from app.schemas import CredentialsIn
from app.security import hash_password
from app.seed import seed_demo
from app.services.accounts import create_user
from app.services.rating import acquire_rating_lock


def create_owner(login: str, password: str | None) -> int:
    if password is None:
        password = getpass.getpass("Пароль владельца: ")
        if password != getpass.getpass("Повторите пароль: "):
            print("Пароли не совпадают", file=sys.stderr)
            return 1
    try:
        CredentialsIn(login=login, password=password)
    except ValueError:
        print("Логин: 3–32 символа (латиница, цифры, _ . -). Пароль: от 8 символов", file=sys.stderr)
        return 1

    db = SessionLocal()
    try:
        acquire_rating_lock(db)
        existing = db.scalar(select(User).where(User.login == login.lower()))
        if existing is not None:
            existing.role = UserRole.OWNER
            existing.status = UserStatus.ACTIVE
            existing.password_hash = hash_password(password)
            db.commit()
            print(f"Пользователь {login} теперь владелец, пароль обновлён")
            return 0
        create_user(db, login, password, role=UserRole.OWNER)
        db.commit()
        print(f"Владелец {login} создан")
        return 0
    except AppError as error:
        print(error.detail, file=sys.stderr)
        return 1
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    owner = commands.add_parser("create-owner", help="Создать первого владельца")
    owner.add_argument("--login", required=True)
    owner.add_argument("--password", help="Если не указан, будет запрошен в терминале")
    commands.add_parser("seed-demo", help="Загрузить демоданные")
    args = parser.parse_args()

    if args.command == "create-owner":
        return create_owner(args.login, args.password)
    return seed_demo()


if __name__ == "__main__":
    sys.exit(main())
