// All chat data is fetched from the server; the browser keeps only the selected chat ID.
const chatList = document.querySelector("#chat-list");
const messages = document.querySelector("#messages");
const title = document.querySelector("#chat-title");
const statusLine = document.querySelector("#status");
const input = document.querySelector("#message-input");
const sendButton = document.querySelector("#send-button");
const renameButton = document.querySelector("#rename-chat");
let selectedChat = null;

async function api(url, options = {}) {
  const response = await fetch(url, {
    ...options,
    headers: { "Content-Type": "application/json", ...options.headers },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.error || `Error HTTP ${response.status}`);
  }
  return response.status === 204 ? null : response.json();
}

function showMessage(role, text) {
  const article = document.createElement("article");
  article.className = `message ${role}`;
  const label = document.createElement("strong");
  label.textContent = role === "user" ? "Tú" : "Gemini";
  const content = document.createElement("p");
  content.textContent = text;
  article.append(label, content);
  messages.append(article);
}

async function loadChats() {
  const result = await api("/api/chats");
  chatList.replaceChildren();
  for (const chat of result.chats) {
    const item = document.createElement("li");
    const row = document.createElement("div");
    row.className = "chat-row";
    const button = document.createElement("button");
    button.textContent = chat.title;
    button.className = chat.id === selectedChat ? "selected" : "";
    button.addEventListener("click", () => selectChat(chat.id, chat.title));
    button.addEventListener("dblclick", (event) => {
      event.preventDefault();
      event.stopPropagation();
      renameChat(chat.id, chat.title);
    });
    const deleteButton = document.createElement("button");
    deleteButton.type = "button";
    deleteButton.className = "delete-chat";
    deleteButton.textContent = "Eliminar";
    deleteButton.setAttribute("aria-label", `Eliminar ${chat.title}`);
    deleteButton.addEventListener("click", async () => {
      if (!window.confirm(`¿Eliminar "${chat.title}" y sus mensajes?`)) return;
      try {
        await api(`/api/chats/${chat.id}`, { method: "DELETE" });
        if (selectedChat === chat.id) {
          selectedChat = null;
          title.textContent = "Selecciona o crea un chat";
          renameButton.disabled = true;
          messages.replaceChildren();
        }
        await loadChats();
      } catch (error) {
        statusLine.textContent = error.message;
      }
    });
    row.append(button, deleteButton);
    item.append(row);
    chatList.append(item);
  }
}

async function selectChat(id, chatTitle) {
  selectedChat = id;
  title.textContent = chatTitle;
  renameButton.disabled = false;
  messages.replaceChildren();
  statusLine.textContent = "";
  const result = await api(`/api/chats/${id}/messages`);
  for (const message of result.messages) showMessage(message.role, message.text);
  await loadChats();
}

document.querySelector("#new-chat").addEventListener("click", async () => {
  try {
    const chat = await api("/api/chats", { method: "POST" });
    await selectChat(chat.id, chat.title);
  } catch (error) {
    statusLine.textContent = error.message;
  }
});

async function renameChat(chatId, currentTitle) {
  const newTitle = window.prompt("Nuevo título", currentTitle);
  if (newTitle === null) return;
  try {
    const result = await api(`/api/chats/${chatId}`, {
      method: "PATCH",
      body: JSON.stringify({ title: newTitle }),
    });
    if (selectedChat === chatId) title.textContent = result.title;
    await loadChats();
  } catch (error) {
    statusLine.textContent = error.message;
  }
}

renameButton.addEventListener("click", () => {
  if (selectedChat) renameChat(selectedChat, title.textContent);
});

title.addEventListener("dblclick", () => {
  if (selectedChat) renameChat(selectedChat, title.textContent);
});

input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    document.querySelector("#message-form").requestSubmit();
  }
});

document.querySelector("#message-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const text = input.value.trim();
  if (!selectedChat || !text || sendButton.disabled) return;
  showMessage("user", text);
  input.value = "";
  sendButton.disabled = true;
  statusLine.textContent = "Esperando respuesta...";
  try {
    const result = await api(`/api/chats/${selectedChat}/messages`, {
      method: "POST",
      body: JSON.stringify({ text }),
    });
    showMessage("model", result.reply);
    statusLine.textContent = "";
  } catch (error) {
    statusLine.textContent = error.message;
    await selectChat(selectedChat, title.textContent);
  } finally {
    sendButton.disabled = false;
    messages.scrollTop = messages.scrollHeight;
  }
});

loadChats().catch((error) => { statusLine.textContent = error.message; });
