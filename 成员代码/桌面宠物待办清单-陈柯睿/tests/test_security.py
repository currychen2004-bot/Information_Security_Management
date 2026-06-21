import importlib
import json
import sys
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
pet_app = importlib.import_module("app")


@pytest.fixture()
def client(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    monkeypatch.setattr(pet_app, "DATA_DIR", data_dir)
    monkeypatch.setattr(pet_app, "USERS_FILE", data_dir / "users.json")
    monkeypatch.setattr(pet_app, "USER_STATES_DIR", data_dir / "user-states")
    pet_app.app.config.update(TESTING=True, SECRET_KEY="test-secret")
    with pet_app.app.test_client() as test_client:
        yield test_client


def register(client, username, password="Password123"):
    return client.post(
        "/api/register",
        json={"username": username, "password": password},
    )


def login(client, username, password="Password123"):
    return client.post(
        "/api/login",
        json={"username": username, "password": password},
    )


@pytest.mark.parametrize(
    ("method", "url", "body"),
    [
        ("get", "/api/state", None),
        ("get", "/api/account/summary", None),
        ("post", "/api/todos", {"text": "unauthorized"}),
        ("patch", "/api/todos/missing-id", {"done": True}),
        ("delete", "/api/todos/missing-id", None),
        ("post", "/api/todos/clear-done", {}),
        ("post", "/api/pet/pat", {}),
    ],
)
def test_protected_apis_return_401_without_login(client, method, url, body):
    request = getattr(client, method)
    response = request(url, json=body) if body is not None else request(url)

    assert response.status_code == 401
    assert "error" in response.get_json()


def test_register_stores_salted_password_hashes(client):
    assert register(client, "alice").status_code == 201
    client.post("/api/logout", json={})
    assert register(client, "bob").status_code == 201

    users = json.loads(pet_app.USERS_FILE.read_text(encoding="utf-8"))["users"]
    alice, bob = users

    assert alice["password_hash"] != "Password123"
    assert bob["password_hash"] != "Password123"
    assert alice["salt"] != bob["salt"]
    assert alice["password_hash"] != bob["password_hash"]
    assert alice["iterations"] >= 200_000


def test_login_failure_uses_generic_message(client):
    register(client, "alice")
    client.post("/api/logout", json={})

    wrong_password = login(client, "alice", "WrongPassword123")
    missing_user = login(client, "missing_user", "WrongPassword123")

    assert wrong_password.status_code == 401
    assert missing_user.status_code == 401
    assert wrong_password.get_json() == missing_user.get_json()


def test_todos_are_isolated_between_users(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    monkeypatch.setattr(pet_app, "DATA_DIR", data_dir)
    monkeypatch.setattr(pet_app, "USERS_FILE", data_dir / "users.json")
    monkeypatch.setattr(pet_app, "USER_STATES_DIR", data_dir / "user-states")
    pet_app.app.config.update(TESTING=True, SECRET_KEY="test-secret")

    test_client = pet_app.app.test_client()

    assert register(test_client, "alice").status_code == 201
    assert test_client.post("/api/todos", json={"text": "Alice private task"}).status_code == 201
    assert test_client.post("/api/logout", json={}).status_code == 200

    assert register(test_client, "bob").status_code == 201
    bob_state = test_client.get("/api/state")

    assert bob_state.status_code == 200
    assert bob_state.get_json()["todos"] == []

    assert test_client.post("/api/todos", json={"text": "Bob private task"}).status_code == 201
    bob_state_after_create = test_client.get("/api/state")
    assert [todo["text"] for todo in bob_state_after_create.get_json()["todos"]] == ["Bob private task"]

    assert test_client.post("/api/logout", json={}).status_code == 200
    assert login(test_client, "alice").status_code == 200
    alice_state = test_client.get("/api/state")

    assert alice_state.status_code == 200
    assert [todo["text"] for todo in alice_state.get_json()["todos"]] == ["Alice private task"]


def test_default_state_factory_returns_independent_mutables():
    first_state = pet_app.create_default_state()
    second_state = pet_app.create_default_state()

    first_state["todos"].append({"id": "one", "text": "private", "done": False})

    assert second_state["todos"] == []
    assert first_state["todos"] is not second_state["todos"]


def test_login_required_account_summary_interface(client):
    register(client, "alice")
    client.post("/api/todos", json={"text": "review summary"})

    response = client.get("/api/account/summary")

    assert response.status_code == 200
    assert response.get_json()["username"] == "alice"
    assert response.get_json()["todoTotal"] == 1


def test_frontend_does_not_store_passwords_in_web_storage():
    script = Path(pet_app.BASE_DIR / "static" / "script.js").read_text(encoding="utf-8")

    assert "localStorage" not in script
    assert "sessionStorage" not in script
