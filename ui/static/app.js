// Signer-facing UI. Every state is shown on screen: the user gets no audio feedback.
const $ = (id) => document.getElementById(id);
const MODE_LABELS = { claude_code: "Claude Code", voice: "Voice", meet: "Meet" };
let socket;

function connect() {
  socket = new WebSocket(`ws://${location.host}/ws`);
  socket.onopen = () => setConnection(true);
  socket.onclose = () => {
    setConnection(false);
    setTimeout(connect, 1000);
  };
  socket.onmessage = (msg) => handle(JSON.parse(msg.data));
}

function send(message) {
  if (socket && socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify(message));
}

function setConnection(ok) {
  $("connection").textContent = ok ? "connected" : "disconnected — retrying";
  $("connection").classList.toggle("bad", !ok);
}

function handle(event) {
  switch (event.type) {
    case "snapshot": return renderSnapshot(event);
    case "ModeChanged": return setMode(event.mode);
    case "UtteranceProgress": return setGloss(event.gloss);
    case "Translation": return setText($("english"), event.english);
    case "ConfirmRequest": return showConfirm(event);
    case "ConfirmResult": return resolveConfirm(event);
    case "OutputSent": return addSent(event);
    case "OutputReply": return addLine($("reply"), event.text, event.done ? "done" : "");
    case "Caption": return addLine($("captions"), event.text);
    case "Notice": return addLine($("notices"), event.message, event.level);
  }
}

function renderSnapshot(s) {
  setMode(s.mode);
  setGloss(s.gloss);
  setText($("english"), s.translation ? s.translation.english : "");
  $("confirm").hidden = true;
  if (s.pending) showConfirm(s.pending);
  for (const id of ["reply", "spoken", "captions", "notices"]) $(id).replaceChildren();
  s.replies.forEach((r) => addLine($("reply"), r.text, r.done ? "done" : ""));
  s.sent.forEach(addSent);
  s.captions.forEach((c) => addLine($("captions"), c.text));
  s.notices.forEach((n) => addLine($("notices"), n.message, n.level));
  $("components").textContent = Object.entries(s.components)
    .map(([k, v]) => `${k}: ${v}`).join("  ·  ");
  $("panel-mock").hidden = s.components.recognizer !== "mock";
}

function setMode(mode) {
  $("mode").textContent = MODE_LABELS[mode] || mode;
  $("mode").dataset.mode = mode;
  document.querySelectorAll("[data-modes]").forEach((el) => {
    el.hidden = !el.dataset.modes.split(" ").includes(mode);
  });
}

function setGloss(gloss) {
  const el = $("gloss");
  el.replaceChildren();
  if (!gloss.length) return setText(el, "");
  for (const token of gloss) {
    const span = document.createElement("span");
    span.className = token.startsWith("fs-") ? "token fs" : "token";
    span.textContent = token.replace(/^fs-/, "");
    el.append(span);
  }
}

function setText(el, text) {
  el.replaceChildren();
  if (text) el.textContent = text;
  else el.innerHTML = '<span class="muted">—</span>';
}

function showConfirm(request) {
  $("confirm").hidden = false;
  $("confirm").dataset.requestId = request.request_id;
  $("confirm-text").textContent = request.english;
}

function resolveConfirm(result) {
  if ($("confirm").dataset.requestId !== result.request_id) return;
  $("confirm").hidden = true;
  addLine($("notices"), result.approved ? "Sent to Claude Code" : "Cancelled", "info");
}

function addSent(event) {
  if (event.output === "claude_code") return;
  const label = event.output === "tts" ? "" : `[${event.output}] `;
  addLine($("spoken"), label + event.text);
}

function addLine(el, text, cls = "") {
  const line = document.createElement("div");
  line.className = `line ${cls}`;
  line.textContent = text;
  el.append(line);
  while (el.children.length > 30) el.firstChild.remove();
  el.scrollTop = el.scrollHeight;
}

$("btn-mode").onclick = () => send({ type: "control", sign: "MODE" });
$("btn-clear").onclick = () => send({ type: "control", sign: "CLEAR" });
$("mock-form").onsubmit = (e) => {
  e.preventDefault();
  const text = $("mock-input").value.trim();
  if (text) send({ type: "mock_input", text });
  $("mock-input").value = "";
};

connect();
