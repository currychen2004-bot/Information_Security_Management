from __future__ import annotations

import copy
import functools
import hashlib
import hmac
import json
import os
import random
import re
import secrets
import tempfile
import threading
from pathlib import Path
from uuid import uuid4

from flask import Flask, g, jsonify, render_template, request, session


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
STATE_FILE = DATA_DIR / "state.json"
USERS_FILE = DATA_DIR / "users.json"
USER_STATES_DIR = DATA_DIR / "user-states"
TODO_TEXT_MAX_LENGTH = 80
PET_GROWTH_PER_LEVEL = 5
MANY_PENDING_TODO_THRESHOLD = 5
DEBUG_ENV_VALUE = "1"
SECRET_KEY_ENV_NAME = "PET_TODO_SECRET_KEY"
COOKIE_SECURE_ENV_NAME = "PET_TODO_COOKIE_SECURE"
SESSION_USER_ID_KEY = "pet_todo_user_id"
SESSION_USERNAME_KEY = "pet_todo_username"
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_]{3,24}$")
PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 64
PASSWORD_HASH_ITERATIONS = 200_000

PET_LEVELS = [
    "Lv.1 小团子",
    "Lv.2 巡逻员",
    "Lv.3 助手",
    "Lv.4 专注搭子",
    "Lv.5 完成达人",
]

SPEECHES = {
    "idle": [
        "先从一个小任务开始。",
        "慢一点也没关系，先动起来就行。",
        "把最容易完成的那项先做掉吧。",
    ],
    "happy": [
        "完成一项了，做得不错。",
        "很好，进度在往前走。",
        "继续保持，今天状态不错。",
    ],
    "sleepy": [
        "任务有点多，先挑最短的一项。",
        "如果有点累，就做一个两分钟任务。",
        "先完成一点，后面会更轻松。",
    ],
    "excited": [
        "清单已经完成，休息一下吧。",
        "今天的任务做完了，干得漂亮。",
        "收工时刻到了。",
    ],
}

DEFAULT_STATE = {
    "todos": [],
    "completed_total": 0,
    "growth": 0,
}

USERS_FILE_LOCK = threading.Lock()

app = Flask(__name__)
app.secret_key = os.getenv(SECRET_KEY_ENV_NAME) or secrets.token_hex(32)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.getenv(COOKIE_SECURE_ENV_NAME) == DEBUG_ENV_VALUE,
)


def write_json_file(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        delete=False,
    ) as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
        file.write("\n")
        temp_name = file.name

    os.replace(temp_name, path)


def normalize_username(username: object) -> str:
    return str(username or "").strip()


def load_users() -> dict:
    if not USERS_FILE.exists():
        return {"users": []}

    with USERS_FILE.open("r", encoding="utf-8") as file:
        raw = json.load(file)

    users = raw.get("users", [])
    if not isinstance(users, list):
        users = []

    normalized_users = []
    for user in users:
        if not isinstance(user, dict):
            continue
        username = normalize_username(user.get("username"))
        if not username:
            continue
        normalized_users.append(
            {
                "id": str(user.get("id") or uuid4()),
                "username": username,
                "password_hash": str(user.get("password_hash") or ""),
                "salt": str(user.get("salt") or ""),
                "iterations": int(user.get("iterations") or PASSWORD_HASH_ITERATIONS),
            }
        )

    return {"users": normalized_users}


def save_users(users_data: dict) -> None:
    write_json_file(USERS_FILE, users_data)


def find_user(username: str) -> dict | None:
    target = username.casefold()
    for user in load_users()["users"]:
        if user["username"].casefold() == target:
            return user
    return None


def current_user() -> dict | None:
    user_id = session.get(SESSION_USER_ID_KEY)
    username = session.get(SESSION_USERNAME_KEY)
    if not user_id or not username:
        return None

    user = find_user(str(username))
    if not user or user["id"] != user_id:
        return None
    return user


def is_authenticated() -> bool:
    return current_user() is not None


def login_required(view):
    @functools.wraps(view)
    def wrapped_view(*args, **kwargs):
        user = current_user()
        if not user:
            return jsonify({"error": "请先登录后再访问待办数据。"}), 401
        g.current_user = user
        return view(*args, **kwargs)

    return wrapped_view


def validate_credentials(username: str, password: str) -> str | None:
    if not USERNAME_PATTERN.fullmatch(username):
        return "用户名需为 3-24 位字母、数字或下划线。"
    if not (PASSWORD_MIN_LENGTH <= len(password) <= PASSWORD_MAX_LENGTH):
        return f"密码长度需为 {PASSWORD_MIN_LENGTH}-{PASSWORD_MAX_LENGTH} 位。"
    return None


def hash_password(password: str, salt: str | None = None) -> dict:
    password_salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        bytes.fromhex(password_salt),
        PASSWORD_HASH_ITERATIONS,
    ).hex()
    return {
        "password_hash": digest,
        "salt": password_salt,
        "iterations": PASSWORD_HASH_ITERATIONS,
    }


def verify_password(password: str, user: dict) -> bool:
    try:
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes.fromhex(user["salt"]),
            int(user["iterations"]),
        ).hex()
    except (KeyError, TypeError, ValueError):
        return False
    return hmac.compare_digest(digest, user.get("password_hash", ""))


def user_state_file(user_id: str) -> Path:
    return USER_STATES_DIR / f"{user_id}.json"


def create_default_state() -> dict:
    return copy.deepcopy(DEFAULT_STATE)


def load_state(user_id: str) -> dict:
    state_file = user_state_file(user_id)
    if not state_file.exists():
        return create_default_state()

    with state_file.open("r", encoding="utf-8") as file:
        raw = json.load(file)

    todos = raw.get("todos", [])
    if not isinstance(todos, list):
        todos = []

    normalized_todos = []
    for item in todos:
        if not isinstance(item, dict):
            continue
        normalized_todos.append(
            {
                "id": str(item.get("id") or uuid4()),
                "text": str(item.get("text") or "").strip(),
                "done": bool(item.get("done")),
            }
        )

    return {
        "todos": [item for item in normalized_todos if item["text"]],
        "completed_total": max(0, int(raw.get("completed_total", 0))),
        "growth": max(0, int(raw.get("growth", 0))),
    }


def save_state(user_id: str, state: dict) -> None:
    write_json_file(user_state_file(user_id), state)


def level_index(growth: int) -> int:
    return min(growth // PET_GROWTH_PER_LEVEL, len(PET_LEVELS) - 1)


def build_payload(state: dict, mood: str | None = None, speech: str | None = None) -> dict:
    todos = state["todos"]
    pending = sum(1 for todo in todos if not todo["done"])

    if mood is None:
        if todos and pending == 0:
            mood = "excited"
        elif pending >= MANY_PENDING_TODO_THRESHOLD:
            mood = "sleepy"
        else:
            mood = "idle"

    if speech is None:
        speech = random.choice(SPEECHES.get(mood, SPEECHES["idle"]))

    if todos and pending == 0:
        mood_label = "任务清空中"
    elif mood == "excited":
        mood_label = "兴奋到转圈"
    elif mood == "happy":
        mood_label = "心满意足"
    elif mood == "sleepy":
        mood_label = "低功耗省电"
    else:
        mood_label = "悠闲巡逻"

    growth = state["growth"]
    return {
        "todos": todos,
        "completedTotal": state["completed_total"],
        "growth": growth,
        "pet": {
            "mood": mood,
            "moodLabel": mood_label,
            "levelLabel": PET_LEVELS[level_index(growth)],
            "progressLabel": f"{growth % PET_GROWTH_PER_LEVEL} / {PET_GROWTH_PER_LEVEL}",
            "speech": speech,
        },
    }


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/session")
def get_session():
    user = current_user()
    return jsonify(
        {
            "authenticated": user is not None,
            "username": user["username"] if user else None,
        }
    )


@app.post("/api/register")
def register():
    payload = request.get_json(silent=True) or {}
    username = normalize_username(payload.get("username"))
    password = str(payload.get("password") or "")

    validation_error = validate_credentials(username, password)
    if validation_error:
        return jsonify({"error": validation_error}), 400

    password_data = hash_password(password)
    with USERS_FILE_LOCK:
        users_data = load_users()
        if any(user["username"].casefold() == username.casefold() for user in users_data["users"]):
            return jsonify({"error": "用户名已存在。"}), 409

        user = {
            "id": str(uuid4()),
            "username": username,
            **password_data,
        }
        users_data["users"].append(user)
        save_users(users_data)

    session.clear()
    session[SESSION_USER_ID_KEY] = user["id"]
    session[SESSION_USERNAME_KEY] = user["username"]
    return jsonify({"authenticated": True, "username": user["username"]}), 201


@app.post("/api/login")
def login():
    payload = request.get_json(silent=True) or {}
    username = normalize_username(payload.get("username"))
    submitted_password = str(payload.get("password") or "")
    user = find_user(username)

    # Return a generic message to avoid revealing whether the username exists.
    if not user or not verify_password(submitted_password, user):
        return jsonify({"error": "用户名或密码不正确。"}), 401

    session.clear()
    session[SESSION_USER_ID_KEY] = user["id"]
    session[SESSION_USERNAME_KEY] = user["username"]
    return jsonify({"authenticated": True, "username": user["username"]})


@app.post("/api/logout")
def logout():
    session.clear()
    return jsonify({"authenticated": False})


@app.get("/api/state")
@login_required
def get_state():
    state = load_state(g.current_user["id"])
    return jsonify(build_payload(state))


@app.get("/api/account/summary")
@login_required
def account_summary():
    state = load_state(g.current_user["id"])
    pending = sum(1 for todo in state["todos"] if not todo["done"])
    return jsonify(
        {
            "username": g.current_user["username"],
            "todoTotal": len(state["todos"]),
            "pending": pending,
            "completedTotal": state["completed_total"],
            "growth": state["growth"],
            "levelLabel": PET_LEVELS[level_index(state["growth"])],
        }
    )


@app.post("/api/todos")
@login_required
def create_todo():
    payload = request.get_json(silent=True) or {}
    text = str(payload.get("text") or "").strip()

    if not text:
        return jsonify({"error": "任务内容不能为空。"}), 400

    state = load_state(g.current_user["id"])
    state["todos"].insert(
        0,
        {
            "id": str(uuid4()),
            "text": text[:TODO_TEXT_MAX_LENGTH],
            "done": False,
        },
    )
    save_state(g.current_user["id"], state)
    return jsonify(build_payload(state, mood="idle", speech="任务已加入清单。")), 201


@app.patch("/api/todos/<todo_id>")
@login_required
def update_todo(todo_id: str):
    payload = request.get_json(silent=True) or {}
    state = load_state(g.current_user["id"])

    for todo in state["todos"]:
        if todo["id"] != todo_id:
            continue

        new_done = bool(payload.get("done"))
        if todo["done"] != new_done:
            todo["done"] = new_done
            if new_done:
                state["completed_total"] += 1
                state["growth"] += 1
                speech = "完成一项了，做得不错。"
                mood = "happy"
            else:
                state["completed_total"] = max(0, state["completed_total"] - 1)
                state["growth"] = max(0, state["growth"] - 1)
                speech = "这项任务重新放回清单了。"
                mood = "sleepy"
        else:
            speech = None
            mood = None

        save_state(g.current_user["id"], state)
        return jsonify(build_payload(state, mood=mood, speech=speech))

    return jsonify({"error": "没有找到对应的任务。"}), 404


@app.delete("/api/todos/<todo_id>")
@login_required
def delete_todo(todo_id: str):
    state = load_state(g.current_user["id"])
    original_count = len(state["todos"])
    state["todos"] = [todo for todo in state["todos"] if todo["id"] != todo_id]

    if len(state["todos"]) == original_count:
        return jsonify({"error": "没有找到对应的任务。"}), 404

    save_state(g.current_user["id"], state)
    return jsonify(build_payload(state))


@app.post("/api/todos/clear-done")
@login_required
def clear_done():
    state = load_state(g.current_user["id"])
    state["todos"] = [todo for todo in state["todos"] if not todo["done"]]
    save_state(g.current_user["id"], state)
    return jsonify(build_payload(state, mood="idle", speech="已完成的任务已经清掉了。"))


@app.post("/api/pet/pat")
@login_required
def pet_pat():
    state = load_state(g.current_user["id"])
    pending = sum(1 for todo in state["todos"] if not todo["done"])

    if pending == 0:
        speech = "今天的进度已经不错了。"
        mood = "happy"
    else:
        speech = f"还有 {pending} 项任务，慢慢做就行。"
        mood = "idle"

    return jsonify(build_payload(state, mood=mood, speech=speech))


if __name__ == "__main__":
    # Flask debug mode exposes an interactive debugger. Keep it off by default,
    # and only enable it explicitly in a local development environment.
    app.run(debug=os.getenv("FLASK_DEBUG") == DEBUG_ENV_VALUE)
