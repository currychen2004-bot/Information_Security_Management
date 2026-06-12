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
const logoutButton = document.querySelector("#logoutButton");
const loginPanel = document.querySelector("#loginPanel");
const appShell = document.querySelector("#appShell");
const loginForm = document.querySelector("#loginForm");
const passwordInput = document.querySelector("#passwordInput");
const loginMessage = document.querySelector("#loginMessage");

let state = null;

function showLogin(message = "") {
  appShell.hidden = true;
  loginPanel.hidden = false;
  loginMessage.textContent = message;
  passwordInput.focus();
}

function showApp() {
  loginPanel.hidden = true;
  appShell.hidden = false;
}

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
    if (response.status === 401) {
      showLogin(payload.error || "请先登录。");
    }
    throw new Error(payload.error || "请求失败");
  }

  return payload;
}

async function loadState() {
  const payload = await request("/api/state");
  showApp();
  render(payload);
}

async function loadSession() {
  const payload = await request("/api/session");
  if (!payload.loginEnabled) {
    showLogin("服务端未设置 PET_TODO_PASSWORD，暂时无法登录。");
    return;
  }

  if (payload.authenticated) {
    await loadState();
    return;
  }

  showLogin();
}

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();

  const password = passwordInput.value;
  if (!password) {
    showLogin("请输入访问密码。");
    return;
  }

  try {
    await request("/api/login", {
      method: "POST",
      body: JSON.stringify({ password }),
    });
    passwordInput.value = "";
    await loadState();
  } catch (error) {
    console.error(error);
    loginMessage.textContent = error.message;
  }
});

logoutButton.addEventListener("click", async () => {
  try {
    await request("/api/logout", {
      method: "POST",
      body: JSON.stringify({}),
    });
    state = null;
    showLogin("已退出登录。");
  } catch (error) {
    console.error(error);
  }
});

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

loadSession().catch((error) => {
  console.error(error);
  showLogin(error.message);
});
