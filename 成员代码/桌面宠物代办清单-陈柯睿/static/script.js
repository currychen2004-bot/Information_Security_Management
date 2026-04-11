const moodLabel = document.querySelector("#moodLabel");
const levelLabel = document.querySelector("#levelLabel");
const progressLabel = document.querySelector("#progressLabel");
const petSpeech = document.querySelector("#petSpeech");
const doneCount = document.querySelector("#doneCount");
const pet = document.querySelector("#pet");
const todoForm = document.querySelector("#todoForm");
const todoInput = document.querySelector("#todoInput");
const todoList = document.querySelector("#todoList");
const clearDoneButton = document.querySelector("#clearDone");
const petActionButton = document.querySelector("#petAction");

let state = null;

function setPet(petState) {
  pet.className = `pet mood-${petState.mood}`;
  moodLabel.textContent = petState.moodLabel;
  levelLabel.textContent = petState.levelLabel;
  progressLabel.textContent = petState.progressLabel;
  petSpeech.textContent = petState.speech;
}

function renderTodos(todos) {
  todoList.innerHTML = "";

  if (!todos.length) {
    const empty = document.createElement("li");
    empty.className = "todo-item";
    empty.innerHTML = `
      <div class="todo-main">
        <div class="todo-text">还没有任务，先加一条今天想完成的事。</div>
      </div>
    `;
    todoList.append(empty);
    return;
  }

  todos.forEach((todo) => {
    const item = document.createElement("li");
    item.className = `todo-item ${todo.done ? "done" : ""}`;
    item.innerHTML = `
      <label class="todo-main">
        <input type="checkbox" ${todo.done ? "checked" : ""} data-id="${todo.id}" />
        <span class="todo-text"></span>
      </label>
      <button class="todo-delete" type="button" data-delete-id="${todo.id}">删除</button>
    `;
    item.querySelector(".todo-text").textContent = todo.text;
    todoList.append(item);
  });
}

function render(payload) {
  state = payload;
  doneCount.textContent = String(payload.completedTotal);
  setPet(payload.pet);
  renderTodos(payload.todos);
}

async function request(url, options = {}) {
  const response = await fetch(url, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });

  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || "请求失败");
  }

  return payload;
}

async function loadState() {
  const payload = await request("/api/state");
  render(payload);
}

todoForm.addEventListener("submit", async (event) => {
  event.preventDefault();

  const text = todoInput.value.trim();
  if (!text) {
    if (state) {
      setPet({
        ...state.pet,
        mood: "sleepy",
        moodLabel: "低功耗省电",
        speech: "先输入任务内容。",
      });
    }
    return;
  }

  try {
    const payload = await request("/api/todos", {
      method: "POST",
      body: JSON.stringify({ text }),
    });
    todoInput.value = "";
    render(payload);
  } catch (error) {
    console.error(error);
  }
});

todoList.addEventListener("click", async (event) => {
  const target = event.target;

  if (target instanceof HTMLInputElement && target.dataset.id) {
    try {
      const payload = await request(`/api/todos/${target.dataset.id}`, {
        method: "PATCH",
        body: JSON.stringify({ done: target.checked }),
      });
      render(payload);
    } catch (error) {
      console.error(error);
      target.checked = !target.checked;
    }
  }

  if (target instanceof HTMLButtonElement && target.dataset.deleteId) {
    try {
      const payload = await request(`/api/todos/${target.dataset.deleteId}`, {
        method: "DELETE",
      });
      render(payload);
    } catch (error) {
      console.error(error);
    }
  }
});

clearDoneButton.addEventListener("click", async () => {
  try {
    const payload = await request("/api/todos/clear-done", {
      method: "POST",
      body: JSON.stringify({}),
    });
    render(payload);
  } catch (error) {
    console.error(error);
  }
});

petActionButton.addEventListener("click", async () => {
  try {
    const payload = await request("/api/pet/pat", {
      method: "POST",
      body: JSON.stringify({}),
    });
    render(payload);
  } catch (error) {
    console.error(error);
  }
});

loadState().catch((error) => {
  console.error(error);
});
