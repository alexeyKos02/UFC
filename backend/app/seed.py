"""Демоданные. Всё создаётся через те же сервисы, что и в приложении, поэтому очки и история согласованы."""

import uuid
from datetime import datetime, timedelta

from sqlalchemy import select

from app.db import SessionLocal, utcnow
from app.models import Belt, BeltKind, FightMethod, PlannedFight, PromoType, User, UserRole
from app.schemas import (
    FightCreateIn,
    FightCorrectIn,
    FightResultIn,
    PlannedFightIn,
    PromoIn,
    TitleFightIn,
    TournamentIn,
)
from app.services import accounts, adjustments, fights, promos, title_fights, tournaments, upcoming

DEMO_PASSWORD = "demo12345"

PLAYERS = [
    ("volk", "Волк"),
    ("kraken", "Кракен"),
    ("tigr", "Тигр"),
    ("orlov", "Орлов"),
    ("bars", "Барс"),
    ("sokol", "Сокол"),
    ("medved", "Медведь"),
    ("yastreb", "Ястреб"),
    ("lis", "Лис"),
    ("gromov", "Громов"),
    ("rys", "Рысь"),
    ("zubr", "Зубр"),
]


def seed_demo() -> int:
    db = SessionLocal()
    try:
        if db.scalar(select(User.id).where(User.login == "demo_owner")) is None:
            logins = ["demo_admin", "ten", *(login for login, _ in PLAYERS)]
            if db.scalar(select(User.id).where(User.login.in_(logins))):
                print("Логины демо-аккаунтов заняты, ничего не изменено")
                return 0
            _fill(db)
        if db.scalar(select(PlannedFight.id).limit(1)) is not None:
            print("Демоданные уже загружены, ничего не изменено")
            return 0
        _fill_upcoming(db)
        print(f"Демоданные загружены. Пароль всех демо-аккаунтов: {DEMO_PASSWORD}")
        print("Владелец: demo_owner, админ: demo_admin, игроки: " + ", ".join(login for login, _ in PLAYERS))
        return 0
    finally:
        db.close()


def _fill_upcoming(db) -> None:
    """Предстоящие бои и голоса. Отдельно от основной части, чтобы дополнить уже загруженную базу."""
    users = {user.login: user for user in db.scalars(select(User))}
    now = utcnow()

    def planned(first: str, second: str, days: int, for_first: list[str], for_second: list[str]) -> PlannedFight:
        created = upcoming.create_planned_fight(
            db,
            users[first],
            PlannedFightIn(
                opponent_id=users[second].id,
                scheduled_at=now + timedelta(days=days),
                client_request_id=uuid.uuid4(),
            ),
        )
        for login in for_first:
            upcoming.cast_vote(db, users[login], "planned", created.id, users[first].id)
        for login in for_second:
            upcoming.cast_vote(db, users[login], "planned", created.id, users[second].id)
        return created

    planned("volk", "bars", 3, ["kraken", "tigr", "orlov"], ["sokol", "medved"])
    planned("orlov", "yastreb", 5, ["lis"], ["gromov", "rys", "zubr"])

    # Бой, который уже прошёл после голосования: голоса видны и в его карточке.
    finished = planned("sokol", "gromov", 1, ["volk", "kraken", "bars", "lis"], ["tigr"])
    fight = upcoming.submit_planned_result(
        db,
        users["sokol"],
        finished.id,
        FightResultIn(
            fought_at=now - timedelta(hours=3), winner_id=users["gromov"].id, method=FightMethod.DECISION, round=3
        ),
    )
    fights.confirm(db, users["gromov"], fight.id, 1)

    voters = [users[login] for login, _ in PLAYERS]
    for kind, target in upcoming.list_upcoming(db):
        if kind == "planned":
            continue
        audience = [voter for voter in voters if voter.id not in (target.player1_id, target.player2_id)]
        for index, voter in enumerate(audience[:6]):
            choice = target.player1_id if index % 3 else target.player2_id
            upcoming.cast_vote(db, voter, kind, target.id, choice)


def _fill(db) -> None:
    owner = accounts.create_user(db, "demo_owner", DEMO_PASSWORD, UserRole.OWNER, "Промоутер")
    admin = accounts.create_user(db, "demo_admin", DEMO_PASSWORD, UserRole.ADMIN, "Рефери")
    db.commit()
    p: dict[str, User] = {}
    for login, nickname in PLAYERS:
        p[login] = accounts.create_user(db, login, DEMO_PASSWORD, nickname=nickname)
    shadow = accounts.create_user(db, "ten", DEMO_PASSWORD, nickname="Тень")
    db.commit()

    now = utcnow()

    def days_ago(days: int, hour: int = 20) -> datetime:
        return (now - timedelta(days=days)).replace(hour=hour, minute=0, second=0, microsecond=0)

    def regular(first, second, winner, when, method=None, round_no=None):
        fight = fights.create_regular_fight(
            db,
            first,
            FightCreateIn(
                opponent_id=second.id,
                fought_at=when,
                winner_id=winner.id,
                method=method,
                round=round_no,
                client_request_id=uuid.uuid4(),
            ),
        )
        return fight

    def played(first, second, winner, when, method=None, round_no=None):
        fight = regular(first, second, winner, when, method, round_no)
        return fights.confirm(db, second, fight.id, 1)

    ko, sub, dec = FightMethod.KO_TKO, FightMethod.SUBMISSION, FightMethod.DECISION
    schedule = [
        ("volk", "kraken", "volk", 60, ko, 1),
        ("tigr", "orlov", "tigr", 58, sub, 2),
        ("bars", "sokol", "bars", 57, dec, 3),
        ("medved", "yastreb", "medved", 55, ko, 2),
        ("lis", "gromov", "gromov", 54, dec, 3),
        ("rys", "zubr", "rys", 53, sub, 1),
        ("volk", "tigr", "volk", 50, dec, 3),
        ("kraken", "orlov", "kraken", 48, ko, 1),
        ("bars", "medved", "bars", 47, sub, 2),
        ("sokol", "yastreb", "sokol", 45, ko, 3),
        ("gromov", "rys", "gromov", 44, dec, 3),
        ("lis", "zubr", "lis", 43, None, None),
        ("volk", "bars", "volk", 40, ko, 2),
        ("kraken", "tigr", "kraken", 39, dec, 3),
        ("orlov", "sokol", "orlov", 38, sub, 1),
        ("medved", "gromov", "gromov", 36, ko, 1),
        ("volk", "gromov", "volk", 35, dec, 3),
        ("kraken", "bars", "kraken", 34, sub, 3),
        ("tigr", "medved", "tigr", 33, ko, 2),
        ("yastreb", "lis", "yastreb", 32, dec, 3),
    ]
    for first, second, winner, ago, method, round_no in schedule:
        played(p[first], p[second], p[winner], days_ago(ago), method, round_no)

    played(shadow, p["zubr"], shadow, days_ago(30), ko, 1)

    # Апсет с ручной корректировкой и журналом.
    upset = played(p["zubr"], p["volk"], p["zubr"], days_ago(28), sub, 1)
    adjustments.save_adjustment(
        db, admin, upset.id, p["zubr"].id, 2, "Победа в первом раунде над лидером таблицы", 0
    )
    # Апсет без корректировки: на нём можно проверить форму.
    played(p["lis"], p["kraken"], p["lis"], days_ago(26), ko, 2)

    novice = Belt(kind=BeltKind.TOURNAMENT, name="Пояс новичков")
    iron = Belt(kind=BeltKind.TOURNAMENT, name="Железный кулак")
    silver = Belt(kind=BeltKind.TOURNAMENT, name="Серебряная перчатка")
    bronze = Belt(kind=BeltKind.TOURNAMENT, name="Бронзовый кастет")
    db.add_all([novice, iron, silver, bronze])
    db.commit()

    def tournament(title, description, capacity, belt):
        created = tournaments.create_tournament(
            db,
            admin,
            TournamentIn(title=title, description=description, capacity=capacity, win_points=20, belt_id=belt.id),
        )
        return created

    def opened(title, description, capacity, belt, members):
        created = tournament(title, description, capacity, belt)
        tournaments.publish(db, created.id)
        for member in members:
            tournaments.join(db, member, created.id)
        return created

    players_by_id = {user.id: user for user in [*p.values(), shadow]}

    def finish(created, champion, when):
        state = created
        while True:
            db.refresh(state)
            ready = [
                match
                for match in state.matches
                if match.winner_id is None and match.player1_id and match.player2_id and match.fight is None
            ]
            if not ready:
                return
            match = ready[0]
            winner_id = champion.id if champion.id in (match.player1_id, match.player2_id) else match.player1_id
            submitter = players_by_id[match.player1_id]
            fight = tournaments.submit_match_result(
                db, submitter, match.id, FightResultIn(fought_at=when, winner_id=winner_id, method=dec, round=3)
            )
            fights.confirm(db, players_by_id[match.player2_id], fight.id, 1)

    autumn = opened(
        "Осенний кубок",
        "Первый турнир лиги за пояс новичков.",
        4,
        novice,
        [p["tigr"], p["orlov"], p["sokol"], p["yastreb"]],
    )
    tournaments.start(db, autumn.id)
    finish(autumn, p["tigr"], days_ago(21))

    winter = opened(
        "Зимний кубок",
        "Второй розыгрыш пояса новичков: чемпион защищает титул.",
        4,
        novice,
        [p["tigr"], p["orlov"], p["bars"], p["medved"]],
    )
    tournaments.start(db, winter.id)
    finish(winter, p["bars"], days_ago(14))

    # Идущий турнир: число участников не степень двойки, в первом раунде есть проходы.
    iron_cup = opened(
        "Кубок железного кулака",
        "Сетка на вылет, идёт прямо сейчас.",
        8,
        iron,
        [p["volk"], p["kraken"], p["lis"], p["gromov"], p["rys"]],
    )
    tournaments.start(db, iron_cup.id)
    db.refresh(iron_cup)
    first_ready = next(
        match for match in iron_cup.matches if match.player1_id and match.player2_id and match.winner_id is None
    )
    awaiting = tournaments.submit_match_result(
        db,
        players_by_id[first_ready.player1_id],
        first_ready.id,
        FightResultIn(fought_at=days_ago(1), winner_id=first_ready.player1_id, method=ko, round=2),
    )

    grand_prix = opened(
        "Весенний гран-при",
        "Открытая регистрация: успейте занять место.",
        8,
        silver,
        [p["orlov"], p["sokol"], p["medved"]],
    )
    opened(
        "Кубок последнего места",
        "Осталось одно свободное место.",
        4,
        bronze,
        [p["bars"], p["tigr"], p["yastreb"]],
    )
    extra_belt = Belt(kind=BeltKind.TOURNAMENT, name="Золотая капа")
    db.add(extra_belt)
    db.commit()
    tournament("Летний чемпионат", "Черновик, виден только в админке.", 16, extra_belt)

    # Основной пояс: бой за вакантный титул, защита и назначенный бой.
    vacant = title_fights.schedule(db, admin, TitleFightIn(player1_id=p["kraken"].id, player2_id=p["volk"].id))
    fight = title_fights.submit_result(
        db, p["kraken"], vacant.id, FightResultIn(fought_at=days_ago(12), winner_id=p["kraken"].id, method=dec, round=5)
    )
    fights.confirm(db, p["volk"], fight.id, 1)

    defense = title_fights.schedule(db, owner, TitleFightIn(player2_id=p["gromov"].id))
    fight = title_fights.submit_result(
        db, p["gromov"], defense.id, FightResultIn(fought_at=days_ago(7), winner_id=p["kraken"].id, method=sub, round=4)
    )
    fights.confirm(db, p["kraken"], fight.id, 1)

    title_fights.schedule(
        db, admin, TitleFightIn(player2_id=p["tigr"].id, scheduled_at=now + timedelta(days=5))
    )

    # Записи в разделе «Мои бои».
    regular(p["gromov"], p["volk"], p["gromov"], days_ago(2), ko, 1)
    regular(p["sokol"], p["volk"], p["volk"], days_ago(2, 18), dec, 3)
    argued = regular(p["volk"], p["orlov"], p["volk"], days_ago(3), sub, 2)
    fights.dispute(db, p["orlov"], argued.id, 1, "Бой закончился решением, а не сабмишеном")
    corrected = regular(p["rys"], p["medved"], p["rys"], days_ago(4), ko, 1)
    fights.dispute(db, p["medved"], corrected.id, 1, "Победил я, запись перепутана")
    fights.correct(
        db,
        p["rys"],
        corrected.id,
        FightCorrectIn(expected_version=1, fought_at=days_ago(4), winner_id=p["medved"].id, method=ko, round=1),
    )

    in_a_week = now + timedelta(days=7)
    promo_tournament = promos.create_promo(
        db,
        admin,
        PromoIn(
            type=PromoType.TOURNAMENT,
            title="Весенний гран-при",
            description="Восемь мест, одна сетка и серебряная перчатка.",
            tournament_id=grand_prix.id,
            sort_order=1,
        ),
    )
    promo_fight = promos.create_promo(
        db,
        admin,
        PromoIn(
            type=PromoType.FIGHT_ANNOUNCEMENT,
            title="Битва лидеров",
            description="Волк и Барс встретятся в реванше.",
            fighter1_id=p["volk"].id,
            fighter2_id=p["bars"].id,
            fight_at=now + timedelta(days=3),
            sort_order=2,
        ),
    )
    promo_fighter = promos.create_promo(
        db,
        admin,
        PromoIn(
            type=PromoType.FIGHTER_OF_WEEK,
            title="Боец недели",
            description="Действующий чемпион лиги, недавно защитил титул.",
            player_id=p["kraken"].id,
            show_from=now - timedelta(days=1),
            show_until=in_a_week,
            sort_order=3,
        ),
    )
    for promo in (promo_tournament, promo_fight, promo_fighter):
        promos.set_published(db, promo.id, True)

    accounts.block(db, owner, shadow.id)

    print(f"В идущем турнире ждёт подтверждения бой #{awaiting.id}")
