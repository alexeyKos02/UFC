import io

from PIL import Image

from tests.conftest import Api, PASSWORD, create_fight, play, register


def test_registration_gives_active_player_with_100_points():
    api = register("newcomer")
    assert api.user["role"] == "player"
    assert api.user["status"] == "active"
    assert api.user["rating_points"] == 1000


def test_registration_ignores_client_supplied_role():
    api = Api("sneaky")
    response = api.post(
        "/auth/register", {"login": "sneaky", "password": PASSWORD, "role": "owner", "status": "blocked"}
    )
    assert response.status_code == 201
    assert response.json()["role"] == "player"
    assert response.json()["status"] == "active"


def test_login_is_unique_case_insensitive():
    register("fighter")
    response = Api("x").post("/auth/register", {"login": "FIGHTER", "password": PASSWORD})
    assert response.status_code == 409


def test_nickname_collision_at_registration_gets_suffix(players):
    first = register("alpha")
    assert first.patch("/me/profile", {"nickname": "bravo"}).status_code == 200
    second = register("bravo")
    assert second.user["nickname"] == "bravo_2"


def test_password_is_hashed_and_wrong_password_rejected():
    register("hashed")
    bad = Api("x").post("/auth/login", {"login": "hashed", "password": "not-the-password"})
    assert bad.status_code == 401
    from app.db import SessionLocal
    from app.models import User
    from sqlalchemy import select

    db = SessionLocal()
    stored = db.scalar(select(User).where(User.login == "hashed")).password_hash
    db.close()
    assert stored.startswith("$argon2")
    assert PASSWORD not in stored


def test_anonymous_cannot_read_league():
    assert Api("anon").get("/players").status_code == 401
    assert Api("anon").get("/home").status_code == 401


def test_logout_ends_session():
    api = register("leaver")
    assert api.post("/auth/logout").status_code == 204
    assert api.get("/auth/me").status_code == 401


def test_player_is_denied_all_admin_actions(players):
    player = players(1)[0]
    attempts = [
        ("post", "/admin/tournaments", {"title": "x", "capacity": 2, "belt_id": 1}),
        ("post", "/admin/belts", {"name": "x"}),
        ("post", "/admin/title-fights", {"player1_id": 1, "player2_id": 2}),
        ("put", "/admin/rating/special-places/1", {"place": 1}),
        ("put", "/admin/rating/adjustments/1", {"player_id": 1, "points": 1, "reason": "abc", "expected_version": 0}),
        ("post", "/admin/promos", {"type": "fight_announcement", "title": "x"}),
        ("post", "/admin/users/1/block", None),
        ("post", "/admin/users/1/role", {"role": "admin"}),
    ]
    for method, url, body in attempts:
        response = getattr(player, method)(url, body)
        assert response.status_code == 403, f"{url}: {response.status_code}"
    assert player.get("/admin/users").status_code == 403


def test_admin_cannot_manage_roles_or_blocks(admin, players):
    target = players(1)[0]
    assert admin.post(f"/admin/users/{target.id}/block").status_code == 403
    assert admin.post(f"/admin/users/{target.id}/role", {"role": "admin"}).status_code == 403
    assert admin.get("/admin/users").status_code == 403


def test_owner_grants_and_revokes_admin(owner, players):
    target = players(1)[0]
    assert target.get("/admin/promos").status_code == 403
    assert owner.post(f"/admin/users/{target.id}/role", {"role": "admin"}).json()["role"] == "admin"
    assert target.get("/admin/promos").status_code == 200
    assert owner.post(f"/admin/users/{target.id}/role", {"role": "player"}).json()["role"] == "player"
    assert target.get("/admin/promos").status_code == 403


def test_owner_role_is_not_assignable_through_admin(owner, players):
    target = players(1)[0]
    assert owner.post(f"/admin/users/{target.id}/role", {"role": "owner"}).status_code == 400


def test_block_ends_open_sessions_but_keeps_history(owner, players):
    first, second, witness = players(3)
    fight = play(first, second, first)
    assert owner.post(f"/admin/users/{first.id}/block").status_code == 200

    assert first.get("/auth/me").status_code in (401, 403)
    assert Api("x").post("/auth/login", {"login": first.login, "password": PASSWORD}).status_code == 403

    profile = witness.get(f"/players/{first.id}").json()
    assert profile["player"]["status"] == "blocked"
    assert profile["stats"]["wins"] == 1
    assert profile["rating"]["display_place"] is None
    assert witness.get(f"/fights/{fight['id']}").status_code == 200
    league_ids = [row["player"]["id"] for row in witness.get("/players").json()]
    assert first.id not in league_ids


def test_unblock_restores_place_and_access(owner, players):
    first, second = players(2)
    play(first, second, first)
    owner.post(f"/admin/users/{first.id}/block")
    owner.post(f"/admin/users/{first.id}/unblock")
    relogin = Api(first.login)
    response = relogin.post("/auth/login", {"login": first.login, "password": PASSWORD})
    assert response.status_code == 200
    assert response.json()["rating_points"] == 1020
    assert relogin.get(f"/players/{first.id}").json()["rating"]["display_place"] == 1


def test_fight_with_blocked_player_rejected(owner, players):
    first, second = players(2)
    owner.post(f"/admin/users/{second.id}/block")
    assert create_fight(first, second, first).status_code == 409


def test_confirmation_rejected_when_other_participant_blocked(owner, players):
    first, second = players(2)
    fight = create_fight(first, second, first).json()
    owner.post(f"/admin/users/{first.id}/block")
    response = second.post(f"/fights/{fight['id']}/confirm", {"version_no": 1})
    assert response.status_code == 409
    assert second.points() == 1000


def _png_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (32, 32), (200, 10, 10)).save(buffer, format="PNG")
    return buffer.getvalue()


def test_avatar_and_full_body_upload_independently(players):
    player = players(1)[0]
    avatar = player.post("/me/avatar", files={"file": ("a.png", _png_bytes(), "image/png")})
    assert avatar.status_code == 200
    assert avatar.json()["avatar_url"]
    assert avatar.json()["full_body_url"] is None
    full = player.post("/me/full-body", files={"file": ("b.png", _png_bytes(), "image/png")})
    assert full.json()["full_body_url"]
    assert full.json()["avatar_url"] == avatar.json()["avatar_url"]
    assert player.client.get(full.json()["full_body_url"]).status_code == 200


def test_upload_rejects_non_image_with_image_content_type(players):
    player = players(1)[0]
    response = player.post("/me/avatar", files={"file": ("a.png", b"<script>alert(1)</script>", "image/png")})
    assert response.status_code == 415


def test_upload_rejects_disallowed_type(players):
    player = players(1)[0]
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8)).save(buffer, format="GIF")
    response = player.post("/me/avatar", files={"file": ("a.gif", buffer.getvalue(), "image/gif")})
    assert response.status_code == 415
    disguised = player.post("/me/avatar", files={"file": ("a.png", buffer.getvalue(), "image/png")})
    assert disguised.status_code == 415


def test_upload_rejects_oversized_file(players):
    from app.config import settings

    player = players(1)[0]
    payload = _png_bytes() + b"0" * (settings.max_upload_bytes + 1)
    response = player.post("/me/avatar", files={"file": ("a.png", payload, "image/png")})
    assert response.status_code == 413


def test_onboarding_is_shown_once(players):
    (player,) = players(1)
    assert player.user["onboarded"] is False
    assert player.get("/auth/me").json()["onboarded"] is False

    first = player.post("/me/onboarding")
    assert first.status_code == 200
    assert first.json()["onboarded"] is True
    assert player.post("/me/onboarding").json()["onboarded"] is True
    assert player.get("/auth/me").json()["onboarded"] is True


def test_onboarding_needs_login():
    assert Api("guest").post("/me/onboarding").status_code == 401
