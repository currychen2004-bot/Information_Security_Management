from __future__ import annotations

import json
import random
from pathlib import Path
from uuid import uuid4

from flask import Flask, jsonify, render_template, request


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
STATE_FILE = DATA_DIR / "state.json"

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


app = Flask(__name__)


def load_state() -> dict:
    if not STATE_FILE.exists():
        return DEFAULT_STATE.copy()

    with STATE_FILE.open("r", encoding="utf-8") as file:
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


def save_state(state: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with STATE_FILE.open("w", encoding="utf-8") as file:
        json.dump(state, file, ensure_ascii=False, indent=2)


def level_index(growth: int) -> int:
    return min(growth // 5, len(PET_LEVELS) - 1)


def build_payload(state: dict, mood: str | None = None, speech: str | None = None) -> dict:
    todos = state["todos"]
    pending = sum(1 for todo in todos if not todo["done"])

    if mood is None:
        if todos and pending == 0:
            mood = "excited"
        elif pending >= 5:
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
            "progressLabel": f"{growth % 5} / 5",
            "speech": speech,
        },
    }


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/state")
def get_state():
    state = load_state()
    return jsonify(build_payload(state))


@app.post("/api/todos")
def create_todo():
    payload = request.get_json(silent=True) or {}
    text = str(payload.get("text") or "").strip()

    if not text:
        return jsonify({"error": "任务内容不能为空。"}), 400

    state = load_state()
    state["todos"].insert(
        0,
        {
            "id": str(uuid4()),
            "text": text[:80],
            "done": False,
        },
    )
    save_state(state)
    return jsonify(build_payload(state, mood="idle", speech="任务已加入清单。")), 201


@app.patch("/api/todos/<todo_id>")
def update_todo(todo_id: str):
    payload = request.get_json(silent=True) or {}
    state = load_state()

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

        save_state(state)
        return jsonify(build_payload(state, mood=mood, speech=speech))

    return jsonify({"error": "没有找到对应的任务。"}), 404


@app.delete("/api/todos/<todo_id>")
def delete_todo(todo_id: str):
    state = load_state()
    original_count = len(state["todos"])
    state["todos"] = [todo for todo in state["todos"] if todo["id"] != todo_id]

    if len(state["todos"]) == original_count:
        return jsonify({"error": "没有找到对应的任务。"}), 404

    save_state(state)
    return jsonify(build_payload(state))


@app.post("/api/todos/clear-done")
def clear_done():
    state = load_state()
    state["todos"] = [todo for todo in state["todos"] if not todo["done"]]
    save_state(state)
    return jsonify(build_payload(state, mood="idle", speech="已完成的任务已经清掉了。"))


@app.post("/api/pet/pat")
def pet_pat():
    state = load_state()
    pending = sum(1 for todo in state["todos"] if not todo["done"])

    if pending == 0:
        speech = "今天的进度已经不错了。"
        mood = "happy"
    else:
        speech = f"还有 {pending} 项任务，慢慢做就行。"
        mood = "idle"

    return jsonify(build_payload(state, mood=mood, speech=speech))


if __name__ == "__main__":
    app.run(debug=True)
