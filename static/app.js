const container = document.getElementById("server-list");
let hasRendered = false;
const cards = new Map();

function createElement(tag, className, text) {
  const el = document.createElement(tag);
  if (className) el.className = className;
  if (text !== undefined) el.textContent = text;
  return el;
}

function formatLatency(ms) {
  if (ms === null || ms === undefined) return "-";
  return `${ms} ms`;
}

function formatCheckedAt(iso) {
  if (!iso) return "-";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString();
}

function ensureCard(server) {
  let entry = cards.get(server.id);
  if (entry) return entry;

  const card = createElement("article", "card");
  const header = createElement("div", "card-header");
  const title = createElement("h3", null, "");
  const badge = createElement("span", "status", "");
  header.appendChild(title);
  header.appendChild(badge);

  const meta = createElement("div", "meta");
  const address = createElement("div", "meta-item", "");
  const latency = createElement("div", "meta-item", "");
  meta.appendChild(address);
  meta.appendChild(latency);

  const stats = createElement("div", "stats");
  const count = createElement("div", "stat", "");
  const checked = createElement("div", "stat", "");
  stats.appendChild(count);
  stats.appendChild(checked);

  const playersTitle = createElement("div", "players-title", "玩家列表");
  const playersList = createElement("div", "players");

  card.appendChild(header);
  card.appendChild(meta);
  card.appendChild(stats);
  card.appendChild(playersTitle);
  card.appendChild(playersList);

  entry = {
    card,
    title,
    badge,
    address,
    latency,
    count,
    checked,
    playersList,
    lastPlayersKey: "",
  };
  cards.set(server.id, entry);
  return entry;
}

function updatePlayers(entry, server) {
  const displayPlayers =
    server.players_display && server.players_display.length
      ? server.players_display
      : server.players;

  let key = "unknown";
  if (server.players_known === false) {
    key = "unknown";
  } else if (displayPlayers && displayPlayers.length) {
    key = displayPlayers.join("|");
  } else {
    key = "empty";
  }

  if (key === entry.lastPlayersKey) return;
  entry.lastPlayersKey = key;
  entry.playersList.innerHTML = "";

  if (server.players_known === false) {
    entry.playersList.appendChild(createElement("span", "muted", "列表不可用"));
  } else if (displayPlayers && displayPlayers.length) {
    displayPlayers.forEach((name) => {
      entry.playersList.appendChild(createElement("span", "chip", name));
    });
  } else {
    entry.playersList.appendChild(createElement("span", "muted", "无"));
  }
}

function updateCard(entry, server) {
  entry.card.className = `card ${server.online ? "online" : "offline"}`;
  entry.badge.className = `status ${server.online ? "online" : "offline"}`;
  entry.badge.textContent = server.online ? "在线" : "离线";
  entry.title.textContent = server.name;
  entry.address.textContent = `地址：${server.address}`;
  entry.latency.textContent = `延迟：${formatLatency(server.latency_ms)}`;
  entry.count.textContent = `在线人数：${server.players_online}/${server.players_max}`;
  entry.checked.textContent = `检测时间：${formatCheckedAt(server.checked_at)}`;
  updatePlayers(entry, server);
}

function renderServers(servers) {
  if (servers.length === 1) {
    container.classList.add("single");
  } else {
    container.classList.remove("single");
  }

  if (!servers.length) {
    container.classList.remove("single");
    container.replaceChildren(createElement("div", "empty", "暂无服务器，请先登录添加。"));
    cards.clear();
    return;
  }

  const fragment = document.createDocumentFragment();
  const seen = new Set();
  servers.forEach((server) => {
    const entry = ensureCard(server);
    updateCard(entry, server);
    fragment.appendChild(entry.card);
    seen.add(server.id);
  });
  container.replaceChildren(fragment);

  for (const id of cards.keys()) {
    if (!seen.has(id)) cards.delete(id);
  }

  if (!hasRendered) {
    hasRendered = true;
  } else {
    container.classList.add("no-anim");
  }
}

async function loadServers() {
  try {
    const res = await fetch("/api/servers", { cache: "no-store" });
    const data = await res.json();
    renderServers(data);
  } catch (err) {
    console.error(err);
  }
}

loadServers();
setInterval(loadServers, 5000);
