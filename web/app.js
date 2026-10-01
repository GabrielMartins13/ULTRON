// App de voz do Ultron: escuta, manda para o servidor, toca a resposta e volta a escutar.
"use strict";

const $ = (id) => document.getElementById(id);
const SILENCIO_FIM_MS = 1100;   // pausa que encerra uma fala
const FALA_MIN_MS = 250;        // menos que isso é ruído
const ESPERA_MAX_MS = 25000;    // reinicia a gravação se ninguém falar

let senha = lerSalvo("ultron-senha");
let config = { ouvido: "servidor" };
let ligado = false;
let estado = "desligado";

// áudio
let stream, ctx, analisador, gravador, pedacos = [];
let reconhecimento; // modo "navegador"
const player = new Audio();
player.playsInline = true;
let wakeLock;

// 0,1 s de silêncio em WAV, para "destravar" o áudio no primeiro toque
function silencio() {
  const n = 800, b = new DataView(new ArrayBuffer(44 + n));
  const txt = (o, t) => [...t].forEach((c, i) => b.setUint8(o + i, c.charCodeAt(0)));
  txt(0, "RIFF"); b.setUint32(4, 36 + n, true); txt(8, "WAVEfmt ");
  b.setUint32(16, 16, true); b.setUint16(20, 1, true); b.setUint16(22, 1, true);
  b.setUint32(24, 8000, true); b.setUint32(28, 8000, true); b.setUint16(32, 1, true);
  b.setUint16(34, 8, true); txt(36, "data"); b.setUint32(40, n, true);
  for (let i = 0; i < n; i++) b.setUint8(44 + i, 128);
  return URL.createObjectURL(new Blob([b], { type: "audio/wav" }));
}

function lerSalvo(k) { try { return localStorage.getItem(k) || ""; } catch { return ""; } }
function salvar(k, v) { try { v ? localStorage.setItem(k, v) : localStorage.removeItem(k); } catch {} }

function mudarEstado(novo, texto) {
  estado = novo;
  document.body.dataset.estado = novo;
  $("estado").textContent = texto ?? {
    desligado: "Toque para ligar", ouvindo: "Ouvindo…", pensando: "Pensando…", falando: "Falando…",
  }[novo];
  $("bt-ligar").textContent = novo === "desligado" ? "Ligar" : "Desligar";
  $("orbe").setAttribute("aria-label", novo === "desligado" ? "Ligar o Ultron"
    : novo === "falando" ? "Interromper o Ultron" : "Ultron ligado");
  if (novo !== "ouvindo" && novo !== "falando") nivel(0);
}
function nivel(v) { document.documentElement.style.setProperty("--nivel", Math.min(1, v).toFixed(3)); }

async function api(rota, opcoes = {}) {
  const r = await fetch(rota, {
    ...opcoes,
    headers: { "X-Ultron-Senha": senha, ...(opcoes.headers || {}) },
  });
  const dados = await r.json().catch(() => ({}));
  if (r.status === 401) { sair(); throw new Error("Senha errada."); }
  if (!r.ok) throw new Error(dados.erro || `Erro ${r.status}`);
  return dados;
}

// ---------- entrada ----------
function sair() {
  desligar();
  salvar("ultron-senha", "");
  senha = "";
  $("tela-conversa").hidden = true;
  $("tela-entrar").hidden = false;
}

$("form-entrar").addEventListener("submit", async (e) => {
  e.preventDefault();
  senha = $("senha").value;
  $("erro-entrar").textContent = "";
  try {
    await api("/api/entrar", { method: "POST" });
    salvar("ultron-senha", senha);
    mostrarConversa();
  } catch (err) {
    $("erro-entrar").textContent = err.message;
  }
});

function mostrarConversa() {
  $("tela-entrar").hidden = true;
  $("tela-conversa").hidden = false;
  mudarEstado("desligado");
}

// ---------- ligar / desligar ----------
async function ligar() {
  // Toca um áudio vazio dentro do toque: libera o som no iPhone para as próximas respostas
  player.src = silencio();
  player.play().catch(() => {});
  ligado = true;
  mudarEstado("pensando", "Conectando…");
  try {
    if ("wakeLock" in navigator) wakeLock = await navigator.wakeLock.request("screen").catch(() => null);
    if (config.ouvido === "servidor") {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
      ctx = new (window.AudioContext || window.webkitAudioContext)();
      analisador = ctx.createAnalyser();
      analisador.fftSize = 1024;
      ctx.createMediaStreamSource(stream).connect(analisador);
    }
    escutar();
  } catch (err) {
    desligar();
    mudarEstado("desligado", err.name === "NotAllowedError"
      ? "Permita o microfone para conversar" : "Não consegui ligar o microfone");
  }
}

function desligar() {
  ligado = false;
  pararGravacao(true);
  try { reconhecimento?.abort(); } catch {}
  player.pause();
  speechSynthesis?.cancel();
  stream?.getTracks().forEach((t) => t.stop());
  ctx?.close().catch(() => {});
  stream = ctx = analisador = null;
  wakeLock?.release().catch(() => {});
  wakeLock = null;
  mudarEstado("desligado");
}

// ---------- escutar (modo servidor: grava e detecta o fim da fala) ----------
function volume() {
  const dados = new Float32Array(analisador.fftSize);
  analisador.getFloatTimeDomainData(dados);
  let soma = 0;
  for (const v of dados) soma += v * v;
  return Math.sqrt(soma / dados.length);
}

function escutar() {
  if (!ligado) return;
  mudarEstado("ouvindo");
  if (config.ouvido === "navegador") return escutarNavegador();
  if (ctx.state === "suspended") ctx.resume();

  const tipo = ["audio/webm;codecs=opus", "audio/mp4", "audio/webm"]
    .find((t) => window.MediaRecorder?.isTypeSupported?.(t)) || "";
  gravador = new MediaRecorder(stream, tipo ? { mimeType: tipo } : undefined);
  pedacos = [];
  gravador.ondataavailable = (e) => e.data.size && pedacos.push(e.data);
  gravador.start(250);

  const inicio = performance.now();
  let ruido = 0.01, falouDesde = 0, ultimaVoz = 0, falou = false;
  const g = gravador;

  const passo = () => {
    if (!ligado || gravador !== g || estado !== "ouvindo") return;
    const agora = performance.now();
    const v = volume();
    // aprende o ruído do ambiente quando ninguém está falando
    if (!falou) ruido = ruido * 0.95 + v * 0.05;
    const limiar = Math.max(0.012, ruido * 2.8);
    nivel(v * 9);

    if (v > limiar) {
      if (!falouDesde) falouDesde = agora;
      ultimaVoz = agora;
      if (agora - falouDesde > FALA_MIN_MS) falou = true;
    } else if (!falou && agora - ultimaVoz > 400) {
      falouDesde = 0; // foi só um estalo
    }

    if (falou && agora - ultimaVoz > SILENCIO_FIM_MS) return enviarGravacao();
    if (!falou && agora - inicio > ESPERA_MAX_MS) { // evita arquivo gigante de silêncio
      pararGravacao(true);
      return escutar();
    }
    setTimeout(passo, 50);
  };
  setTimeout(passo, 300); // ignora o "clique" do começo
}

function pararGravacao(descartar) {
  if (gravador && gravador.state !== "inactive") {
    if (descartar) gravador.ondataavailable = null;
    gravador.stop();
  }
  if (descartar) gravador = null;
}

function enviarGravacao() {
  const g = gravador;
  mudarEstado("pensando");
  g.onstop = async () => {
    const blob = new Blob(pedacos, { type: (g.mimeType || "audio/webm").split(";")[0] });
    gravador = null;
    await conversar(() => api("/api/falar", {
      method: "POST", body: blob, headers: { "Content-Type": blob.type },
    }));
  };
  g.stop();
}

// ---------- escutar (modo navegador: reconhecimento de voz do próprio aparelho) ----------
function escutarNavegador() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) {
    desligar();
    return mudarEstado("desligado", "Este navegador não reconhece voz. Use o Chrome ou configure o Whisper.");
  }
  reconhecimento = new SR();
  reconhecimento.lang = "pt-BR";
  reconhecimento.interimResults = true;
  let final = "";
  reconhecimento.onresult = (e) => {
    const r = e.results[e.results.length - 1];
    $("ouvi").textContent = r[0].transcript;
    nivel(0.5);
    if (r.isFinal) final = r[0].transcript;
  };
  reconhecimento.onend = () => {
    if (!ligado || estado !== "ouvindo") return;
    if (final.trim()) enviarTexto(final.trim());
    else escutar();
  };
  reconhecimento.onerror = (e) => {
    if (e.error === "not-allowed") { desligar(); mudarEstado("desligado", "Permita o microfone para conversar"); }
  };
  reconhecimento.start();
}

// ---------- conversar ----------
function enviarTexto(texto) {
  mudarEstado("pensando");
  return conversar(() => api("/api/escrever", {
    method: "POST", body: JSON.stringify({ texto }), headers: { "Content-Type": "application/json" },
  }));
}

async function conversar(chamada) {
  try {
    const r = await chamada();
    if (r.ouvi) $("ouvi").textContent = r.ouvi;
    if (!r.resposta) return escutar(); // não entendeu nada: volta a ouvir em silêncio
    $("resposta").textContent = r.resposta;
    if (ligado) await falar(r);
  } catch (err) {
    $("resposta").textContent = "⚠ " + err.message;
    await new Promise((ok) => setTimeout(ok, 1500));
  }
  escutar();
}

function falar({ resposta, audio }) {
  mudarEstado("falando");
  return new Promise((pronto) => {
    let pulso;
    const fim = () => { clearInterval(pulso); nivel(0); pronto(); };
    pulso = setInterval(() => nivel(0.25 + Math.random() * 0.5), 110);
    if (audio) {
      player.src = "data:audio/mpeg;base64," + audio;
      player.onended = player.onpause = player.onerror = fim;
      player.play().catch(() => falarNoAparelho(resposta, fim));
    } else {
      falarNoAparelho(resposta, fim);
    }
  });
}

function falarNoAparelho(texto, fim) {
  if (!window.speechSynthesis) return fim();
  const u = new SpeechSynthesisUtterance(texto);
  u.lang = "pt-BR";
  u.voice = speechSynthesis.getVoices().find((v) => v.lang?.replace("_", "-") === "pt-BR") || null;
  u.onend = u.onerror = fim;
  speechSynthesis.speak(u);
}

function interromper() {
  player.pause();
  speechSynthesis?.cancel();
}

// ---------- botões ----------
$("bt-ligar").addEventListener("click", () => (ligado ? desligar() : ligar()));
$("orbe").addEventListener("click", () => {
  if (!ligado) ligar();
  else if (estado === "falando") interromper();
});

$("bt-teclado").addEventListener("click", () => {
  $("form-texto").hidden = !$("form-texto").hidden;
  if (!$("form-texto").hidden) $("texto").focus();
});
$("form-texto").addEventListener("submit", async (e) => {
  e.preventDefault();
  const texto = $("texto").value.trim();
  if (!texto || estado === "pensando") return;
  $("texto").value = "";
  $("ouvi").textContent = texto;
  pararGravacao(true);
  try { reconhecimento?.abort(); } catch {}
  if (!ligado) { // sem conversa por voz: só responde e toca
    player.src = silencio();
    player.play().catch(() => {});
    mudarEstado("pensando");
    try {
      const r = await api("/api/escrever", {
        method: "POST", body: JSON.stringify({ texto }), headers: { "Content-Type": "application/json" },
      });
      $("resposta").textContent = r.resposta;
      await falar(r);
    } catch (err) { $("resposta").textContent = "⚠ " + err.message; }
    return mudarEstado("desligado");
  }
  enviarTexto(texto);
});

$("bt-nova").addEventListener("click", async () => {
  if (!confirm("Começar uma conversa nova? (O que o Ultron guardou na memória continua.)")) return;
  await api("/api/nova-conversa", { method: "POST" }).catch(() => {});
  $("ouvi").textContent = $("resposta").textContent = "";
});

$("bt-memoria").addEventListener("click", async () => {
  const lista = $("lista-memoria");
  lista.replaceChildren();
  try {
    const { fatos } = await api("/api/memoria");
    for (const f of fatos.length ? fatos : [{ fato: "Ainda não guardei nada." }]) {
      const li = document.createElement("li");
      li.textContent = f.fato;
      lista.append(li);
    }
  } catch (err) { lista.textContent = err.message; }
  $("dlg-memoria").showModal();
});

// Se a tela apagar, o navegador corta o microfone: desliga para não ficar num estado quebrado
document.addEventListener("visibilitychange", () => {
  if (document.hidden && ligado && config.ouvido === "servidor") desligar();
});

// ---------- início ----------
(async () => {
  config = await fetch("/api/config").then((r) => r.json()).catch(() => config);
  if (!window.isSecureContext) {
    $("estado").textContent = "Abra pelo endereço https para usar o microfone";
  }
  if (!senha) { $("tela-entrar").hidden = false; return; }
  try {
    await api("/api/entrar", { method: "POST" });
    mostrarConversa();
  } catch { /* api() já mostrou a tela de senha */ }
})();
