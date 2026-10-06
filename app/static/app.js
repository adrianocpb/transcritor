"use strict";
// Interface do Transcritor Local. Fala apenas com o servidor local (mesma origem).

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const DESCONHECIDO = "Outro / desconhecido";
const CORES = ["#2f5496", "#c55a11", "#548235", "#7030a0", "#bf9000", "#0e7c86", "#c00000", "#7f6000", "#3a7dda", "#a5527a"];

const estado = {
  sistema: null,
  proj: null,
  segs: [],
  visao: "blocos",
  timerSalvar: null,
  timerPoll: null,
  inicioProc: null,
  pararEm: null,
};

// ------------------------------------------------------------------ utilitários

async function api(metodo, url, corpo) {
  const opcoes = { method: metodo, headers: {} };
  if (corpo !== undefined) {
    opcoes.headers["Content-Type"] = "application/json";
    opcoes.body = JSON.stringify(corpo);
  }
  const r = await fetch(url, opcoes);
  if (!r.ok) {
    let msg = r.statusText;
    try { const j = await r.json(); msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail); } catch (_) {}
    throw new Error(msg);
  }
  return r.json();
}

function fmt(seg, decimos = false) {
  seg = Math.max(0, Number(seg) || 0);
  if (decimos) {
    const d = Math.round(seg * 10);
    const h = Math.floor(d / 36000), m = Math.floor((d % 36000) / 600), s = Math.floor((d % 600) / 10);
    return `${p2(h)}:${p2(m)}:${p2(s)}.${d % 10}`;
  }
  const t = Math.floor(seg);
  return `${p2(Math.floor(t / 3600))}:${p2(Math.floor((t % 3600) / 60))}:${p2(t % 60)}`;
}
const p2 = (n) => String(n).padStart(2, "0");

function parseTempo(txt) {
  const t = String(txt).trim().replace(",", ".");
  if (!t) return NaN;
  const partes = t.split(":");
  if (partes.length > 3) return NaN;
  let total = 0;
  for (const p of partes) {
    if (p === "" || isNaN(Number(p))) return NaN;
    total = total * 60 + Number(p);
  }
  return total;
}

function el(tag, attrs = {}, ...filhos) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") e.className = v;
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else if (v !== undefined && v !== null) e.setAttribute(k, v);
  }
  for (const f of filhos) if (f !== null && f !== undefined) e.append(f);
  return e;
}

function mostrar(tela) {
  for (const t of ["inicio", "participantes", "processamento", "trabalho"]) $(`#tela-${t}`).classList.add("oculto");
  $("#tela-speakers").classList.add("oculto");
  $("#tela-revisao").classList.add("oculto");
  if (tela === "speakers" || tela === "revisao") {
    $("#tela-trabalho").classList.remove("oculto");
    $(`#tela-${tela}`).classList.remove("oculto");
  } else {
    $(`#tela-${tela}`).classList.remove("oculto");
  }
  if (tela !== "processamento") clearInterval(estado.timerPoll);
  window.scrollTo(0, 0);
}

function nomePessoa(seg) {
  if (seg.pessoa) return seg.pessoa;
  const m = (estado.proj.speakers || {})[seg.speaker];
  return m || seg.speaker || "?";
}

function corPessoa(nome) {
  const nomes = opcoesPessoas();
  const i = nomes.indexOf(nome);
  return nome === DESCONHECIDO ? "#888" : CORES[(i < 0 ? 0 : i) % CORES.length];
}

function opcoesPessoas() {
  const lista = [];
  const add = (n) => { if (n && !lista.includes(n)) lista.push(n); };
  (estado.proj.participantes || []).forEach((p) => add(p.nome));
  Object.values(estado.proj.speakers || {}).forEach(add);
  estado.segs.forEach((s) => add(nomePessoa(s)));
  add(DESCONHECIDO);
  return lista;
}

// ------------------------------------------------------------------ início

async function carregarSistema() {
  try {
    estado.sistema = await api("GET", "/api/sistema");
  } catch (e) {
    $("#info-sistema").textContent = "Não foi possível consultar o hardware: " + e.message;
    return;
  }
  const s = estado.sistema, h = s.hardware;
  const gpus = h.gpus.length ? h.gpus.map((g) => `${g.fabricante} ${g.modelo}${g.vram_total_gb ? ` (${g.vram_total_gb} GB)` : ""}`).join("; ") : "nenhuma detectada";
  const dl = el("dl", {},
    el("dt", {}, "CPU"), el("dd", {}, `${h.cpu.modelo} — ${h.cpu.nucleos_fisicos || "?"} núcleos`),
    el("dt", {}, "RAM"), el("dd", {}, `${h.ram_gb ?? "?"} GB`),
    el("dt", {}, "GPU"), el("dd", {}, gpus),
    el("dt", {}, "Transcrição"), el("dd", {}, `${h.dispositivo_transcricao.toUpperCase()} — modelo padrão: ${h.modelo_padrao}`),
    el("dt", {}, "Diarização"), el("dd", { class: s.diarizacao.disponivel ? "ok" : "ruim" },
      s.diarizacao.disponivel ? `pronta (${h.dispositivo_diarizacao.toUpperCase()})` : s.diarizacao.detalhe),
    el("dt", {}, "Modelos baixados"), el("dd", { class: s.modelos_baixados.length ? "" : "ruim" },
      s.modelos_baixados.length ? s.modelos_baixados.join(", ") : "nenhum — execute baixar_modelos.py"),
  );
  $("#info-sistema").replaceChildren(dl, el("p", { class: "nota" }, h.comentario));
}

async function carregarLista() {
  const itens = await api("GET", "/api/projetos");
  const caixa = $("#lista-projetos");
  if (!itens.length) { caixa.replaceChildren(el("p", { class: "nota" }, "Nenhuma transcrição ainda.")); return; }
  const rotulos = { confirmar_participantes: "participantes", na_fila: "na fila", processando: "processando",
    mapear_speakers: "associar speakers", revisao: "em revisão", erro: "erro", novo: "novo" };
  caixa.replaceChildren(...itens.map((p) => el("div", { class: "item" },
    el("div", { class: "nome" }, el("strong", {}, p.entrevista || p.arquivo_video), el("br"),
      el("small", { class: "nota" }, `${p.arquivo_video} — ${p.atualizado_em || p.criado_em}`)),
    el("span", { class: "etiqueta" }, rotulos[p.status] || p.status),
    el("button", { class: "secundario", onclick: () => abrirProjeto(p.id) }, "Abrir"),
    el("button", { class: "secundario", title: "Excluir projeto e arquivos", onclick: async () => {
      if (!confirm(`Excluir "${p.entrevista || p.arquivo_video}" e todos os seus arquivos locais?`)) return;
      try { await api("DELETE", `/api/projetos/${p.id}`); carregarLista(); } catch (e) { alert(e.message); }
    } }, "🗑"),
  )));
}

function enviarArquivos() {
  const video = $("#arq-video").files[0];
  const docx = $("#arq-docx").files[0];
  if (!video) { alert("Selecione o vídeo da entrevista."); return; }
  const fd = new FormData();
  fd.append("video", video);
  if (docx) fd.append("docx", docx);
  const xhr = new XMLHttpRequest();
  xhr.open("POST", "/api/projetos");
  $("#envio-progresso").classList.remove("oculto");
  $("#btn-enviar").disabled = true;
  xhr.upload.onprogress = (e) => {
    if (!e.lengthComputable) return;
    const pct = Math.round((e.loaded / e.total) * 100);
    $("#envio-barra").style.width = pct + "%";
    $("#envio-texto").textContent = `Copiando arquivos… ${pct}%`;
  };
  xhr.onload = () => {
    $("#btn-enviar").disabled = false;
    $("#envio-progresso").classList.add("oculto");
    if (xhr.status !== 200) {
      let msg = xhr.statusText;
      try { msg = JSON.parse(xhr.responseText).detail; } catch (_) {}
      alert("Erro: " + msg);
      return;
    }
    const proj = JSON.parse(xhr.responseText);
    $("#arq-video").value = ""; $("#arq-docx").value = "";
    abrirProjeto(proj.id);
  };
  xhr.onerror = () => { $("#btn-enviar").disabled = false; alert("Falha ao enviar arquivos ao servidor local."); };
  xhr.send(fd);
}

// ------------------------------------------------------------------ projeto

async function abrirProjeto(id) {
  try {
    estado.proj = await api("GET", `/api/projetos/${id}`);
  } catch (e) {
    alert(e.message); location.hash = ""; mostrar("inicio"); return;
  }
  location.hash = "p=" + id;
  estado.segs = estado.proj.segmentos || [];
  const st = estado.proj.status;
  if (st === "na_fila" || st === "processando") telaProcessamento();
  else if (st === "mapear_speakers") telaSpeakers();
  else if (st === "revisao") telaRevisao();
  else if (st === "erro" && estado.segs.length) telaRevisao();
  else if (st === "erro") { telaProcessamento(); }
  else telaParticipantes();
}

// ------------------------------------------------------------------ participantes + configurações

function linhaParticipante(p = { nome: "", papel: "" }) {
  const tr = el("tr", {},
    el("td", {}, el("input", { type: "text", class: "p-nome", value: p.nome, placeholder: "Nome completo" })),
    el("td", {}, el("input", { type: "text", class: "p-papel", value: p.papel || "", placeholder: "Ex.: Entrevistador" })),
    el("td", {}, el("button", { class: "secundario", title: "Remover", onclick: () => tr.remove() }, "✕")),
  );
  return tr;
}

function telaParticipantes() {
  const p = estado.proj;
  $("#entrevista-id").value = p.entrevista || "";
  const corpo = $("#corpo-participantes");
  corpo.replaceChildren(...(p.participantes || []).map(linhaParticipante));
  const aviso = $("#aviso-participantes");
  if (!(p.participantes || []).length) {
    aviso.textContent = p.texto_docx
      ? "Não consegui identificar os participantes automaticamente no DOCX. Informe-os abaixo."
      : "Nenhum DOCX enviado. Informe os participantes abaixo (ou deixe em branco e associe depois).";
    aviso.classList.remove("oculto");
    corpo.append(linhaParticipante(), linhaParticipante());
  } else {
    aviso.textContent = `${p.participantes.length} participante(s) identificado(s) no DOCX. Confira e corrija se necessário.`;
    aviso.classList.remove("oculto");
  }
  $("#docx-texto-box").classList.toggle("oculto", !p.texto_docx);
  $("#docx-texto").textContent = p.texto_docx || "";

  // Configurações (padrões a partir do hardware, ou da última execução)
  const s = estado.sistema;
  const h = s ? s.hardware : { modelo_padrao: "small", dispositivo_transcricao: "cpu", dispositivo_diarizacao: "cpu" };
  const cfg = p.config || {};
  const modeloSel = cfg.modelo || h.modelo_padrao;
  const baixados = s ? s.modelos_baixados : [];
  $("#opcoes-modelo").replaceChildren(...(s ? s.modelos_whisper : ["tiny", "base", "small", "medium", "large-v3-turbo", "large-v3"]).map((m) =>
    el("label", { class: "check" },
      el("input", { type: "radio", name: "modelo", value: m, ...(m === modeloSel ? { checked: "" } : {}) }),
      `${m}${baixados.includes(m) ? " ✓" : ""}${m === h.modelo_padrao ? " (recomendado)" : ""}`)));
  const idioma = cfg.idioma === undefined ? "pt" : (cfg.idioma || "auto");
  if (["pt", "auto", "en", "es"].includes(idioma)) { $("#idioma").value = idioma; $("#idioma-outro").value = ""; }
  else { $("#idioma").value = "outro"; $("#idioma-outro").value = idioma; }
  $("#idioma-outro").classList.toggle("oculto", $("#idioma").value !== "outro");
  $("#disp-trans").value = cfg.dispositivo_transcricao || h.dispositivo_transcricao;
  $("#disp-diar").value = cfg.dispositivo_diarizacao || h.dispositivo_diarizacao;
  const diarOk = !s || s.diarizacao.disponivel;
  $("#diarizar").checked = cfg.diarizar !== undefined ? cfg.diarizar && diarOk : diarOk;
  $("#diar-status").textContent = diarOk ? "" :
    `⚠ Diarização indisponível: ${s.diarizacao.detalhe}. Sem ela, todos os trechos ficarão como SPEAKER_00 e você poderá definir as pessoas manualmente na revisão.`;
  $("#diar-status").classList.toggle("ruim", !diarOk);
  atualizarModoSpeakers();
  mostrar("participantes");
}

function atualizarModoSpeakers() {
  const modo = $("#modo-speakers").value;
  $("#caixa-exato").classList.toggle("oculto", modo !== "exato");
  $("#caixa-min").classList.toggle("oculto", modo !== "faixa");
  $("#caixa-max").classList.toggle("oculto", modo !== "faixa");
  $("#caixa-num-speakers").classList.toggle("oculto", !$("#diarizar").checked);
}

function lerParticipantes() {
  return $$("#corpo-participantes tr").map((tr) => ({
    nome: $(".p-nome", tr).value.trim(), papel: $(".p-papel", tr).value.trim(),
  })).filter((p) => p.nome);
}

async function processar() {
  const participantes = lerParticipantes();
  const modelo = ($("input[name=modelo]:checked") || {}).value || "small";
  const baixados = estado.sistema ? estado.sistema.modelos_baixados : [];
  if (estado.sistema && !baixados.includes(modelo)) {
    if (!confirm(`O modelo "${modelo}" não parece estar baixado em modelos/whisper.\n\nExecute antes:\n  python baixar_modelos.py --whisper ${modelo}\n\nTentar mesmo assim?`)) return;
  }
  let idioma = $("#idioma").value;
  if (idioma === "outro") idioma = $("#idioma-outro").value.trim().toLowerCase() || "auto";
  const cfg = {
    modelo, idioma,
    dispositivo_transcricao: $("#disp-trans").value,
    dispositivo_diarizacao: $("#disp-diar").value,
    diarizar: $("#diarizar").checked,
    usar_nomes_no_prompt: $("#usar-nomes").checked,
    num_speakers: null, min_speakers: null, max_speakers: null,
  };
  const modo = $("#modo-speakers").value;
  if (modo === "participantes" && participantes.length) cfg.num_speakers = participantes.length;
  if (modo === "exato") cfg.num_speakers = Number($("#num-exato").value) || null;
  if (modo === "faixa") { cfg.min_speakers = Number($("#num-min").value) || null; cfg.max_speakers = Number($("#num-max").value) || null; }
  try {
    $("#btn-processar").disabled = true;
    await api("PUT", `/api/projetos/${estado.proj.id}/participantes`, { entrevista: $("#entrevista-id").value, participantes });
    estado.proj = await api("POST", `/api/projetos/${estado.proj.id}/processar`, cfg);
    estado.inicioProc = Date.now();
    telaProcessamento();
  } catch (e) {
    alert("Erro: " + e.message);
  } finally {
    $("#btn-processar").disabled = false;
  }
}

// ------------------------------------------------------------------ processamento

function telaProcessamento() {
  mostrar("processamento");
  if (!estado.inicioProc) estado.inicioProc = Date.now();
  $("#proc-arquivo").textContent = `${estado.proj.entrevista || ""} — ${estado.proj.arquivo_video}`;
  atualizarProcessamento(estado.proj);
  clearInterval(estado.timerPoll);
  estado.timerPoll = setInterval(async () => {
    try {
      const p = await api("GET", `/api/projetos/${estado.proj.id}`);
      estado.proj = p;
      atualizarProcessamento(p);
      if (p.status === "mapear_speakers") {
        clearInterval(estado.timerPoll);
        estado.inicioProc = null;
        estado.segs = p.segmentos;
        telaSpeakers();
      } else if (p.status === "erro") {
        clearInterval(estado.timerPoll);
        estado.inicioProc = null;
      }
    } catch (_) { /* servidor ocupado; tenta de novo */ }
  }, 1000);
}

function atualizarProcessamento(p) {
  $("#proc-barra").style.width = Math.round((p.progresso || 0) * 100) + "%";
  $("#proc-msg").textContent = `${Math.round((p.progresso || 0) * 100)}% — ${p.mensagem || ""}`;
  const seg = Math.floor((Date.now() - (estado.inicioProc || Date.now())) / 1000);
  $("#proc-tempo").textContent = `${Math.floor(seg / 60)}:${p2(seg % 60)}`;
  const erro = p.status === "erro";
  $("#proc-erro").classList.toggle("oculto", !erro);
  $("#proc-erro").textContent = erro ? p.erro : "";
  $("#btn-voltar-config").classList.toggle("oculto", !erro);
}

// ------------------------------------------------------------------ player

function prepararPlayer() {
  const player = $("#player");
  const base = `/api/projetos/${estado.proj.id}/midia`;
  if (player.dataset.projeto === estado.proj.id) return;
  player.dataset.projeto = estado.proj.id;
  player.dataset.tipo = "video";
  player.src = base + "?tipo=video";
  player.onerror = () => {
    if (player.dataset.tipo === "video") {  // formato não suportado pelo navegador (ex.: .avi/.mkv): usa o áudio extraído
      player.dataset.tipo = "audio";
      player.src = base + "?tipo=audio";
    }
  };
}

function irPara(t, pararEm = null) {
  const player = $("#player");
  player.currentTime = Math.max(0, t - 0.3);
  estado.pararEm = pararEm;
  player.play().catch(() => {});
}

function configurarPlayer() {
  const player = $("#player");
  $("#btn-play").onclick = () => (player.paused ? player.play() : player.pause());
  player.addEventListener("play", () => ($("#btn-play").textContent = "⏸ Pausar"));
  player.addEventListener("pause", () => ($("#btn-play").textContent = "▶︎ Play"));
  $("#btn-voltar5").onclick = () => (player.currentTime = Math.max(0, player.currentTime - 5));
  $("#btn-avancar5").onclick = () => (player.currentTime += 5);
  $$(".velocidades button").forEach((b) => b.addEventListener("click", () => {
    player.playbackRate = Number(b.dataset.vel);
    $$(".velocidades button").forEach((x) => x.classList.toggle("ativo", x === b));
  }));
  player.addEventListener("timeupdate", () => {
    const t = player.currentTime;
    $("#tempo-atual").textContent = fmt(t);
    if (estado.pararEm !== null && t >= estado.pararEm) { player.pause(); estado.pararEm = null; }
    destacarAtual(t);
  });
  document.addEventListener("keydown", (e) => {
    if ($("#tela-trabalho").classList.contains("oculto")) return;
    if (e.ctrlKey && e.code === "Space") { e.preventDefault(); player.paused ? player.play() : player.pause(); }
    if (e.altKey && e.key === "ArrowLeft") { e.preventDefault(); player.currentTime = Math.max(0, player.currentTime - 5); }
    if (e.altKey && e.key === "ArrowRight") { e.preventDefault(); player.currentTime += 5; }
  });
}

let indiceAtual = -1;
function destacarAtual(t) {
  if ($("#tela-revisao").classList.contains("oculto")) return;
  const i = estado.segs.findIndex((s) => t >= s.inicio - 0.05 && t < s.fim + 0.3);
  if (i === indiceAtual) return;
  indiceAtual = i;
  const seletor = estado.visao === "blocos" ? "#blocos .bloco" : "#corpo-tabela tr";
  $$(seletor).forEach((e) => e.classList.toggle("atual", Number(e.dataset.i) === i));
  if (i < 0 || !$("#seguir").checked || $("#player").paused) return;
  const ativo = document.activeElement;
  if (ativo && (ativo.tagName === "TEXTAREA" || ativo.tagName === "INPUT" || ativo.tagName === "SELECT")) return;
  const alvo = $(`${seletor}[data-i="${i}"]`);
  if (alvo) {
    const r = alvo.getBoundingClientRect();
    if (r.top < 140 || r.bottom > window.innerHeight - 20) alvo.scrollIntoView({ block: "center", behavior: "smooth" });
  }
}

// ------------------------------------------------------------------ associação de speakers

function telaSpeakers() {
  prepararPlayer();
  const proj = estado.proj;
  const estat = {};
  for (const s of estado.segs) {
    const e = (estat[s.speaker] ||= { dur: 0, n: 0, segs: [] });
    e.dur += s.fim - s.inicio; e.n += 1; e.segs.push(s);
  }
  const rotulos = Object.keys(estat).sort();
  const total = rotulos.reduce((a, r) => a + estat[r].dur, 0) || 1;
  $("#speakers-resumo").textContent = `Foram identificados ${rotulos.length} speaker(s).` +
    (proj.info && proj.info.diarizacao === false ? " (Diarização desativada: todos os trechos estão como SPEAKER_00.)" : "");
  const participantes = (proj.participantes || []).map((p) => p.nome);
  const caixa = $("#lista-speakers");
  caixa.replaceChildren(...rotulos.map((r) => {
    const atual = (proj.speakers || {})[r] || "";
    const ehParticipante = participantes.includes(atual);
    const sel = el("select", { class: "map-sel", "data-speaker": r },
      el("option", { value: "" }, "— Selecionar participante —"),
      ...participantes.map((n) => el("option", { value: n, ...(n === atual ? { selected: "" } : {}) }, n)),
      el("option", { value: "__outro", ...(atual && !ehParticipante ? { selected: "" } : {}) }, DESCONHECIDO));
    const outro = el("input", { type: "text", class: "map-outro curto-largo", placeholder: "Nome (opcional)",
      value: atual && !ehParticipante && atual !== DESCONHECIDO ? atual : "" });
    outro.classList.toggle("oculto", sel.value !== "__outro");
    sel.addEventListener("change", () => outro.classList.toggle("oculto", sel.value !== "__outro"));
    const exemplos = [...estat[r].segs].filter((s) => s.texto.length > 15)
      .sort((a, b) => (b.fim - b.inicio) - (a.fim - a.inicio)).slice(0, 3)
      .sort((a, b) => a.inicio - b.inicio);
    if (!exemplos.length) exemplos.push(...estat[r].segs.slice(0, 3));
    return el("div", { class: "speaker" },
      el("div", { class: "cabeca" },
        el("span", { class: "rotulo" }, r), el("span", {}, "→"), sel, outro,
        el("span", { class: "nota" }, `${estat[r].n} trechos · ${fmt(estat[r].dur)} de fala (${Math.round(100 * estat[r].dur / total)}%)`)),
      el("ul", { class: "exemplos" }, ...exemplos.map((s) => el("li", {},
        el("button", { class: "secundario", title: "Ouvir este trecho", onclick: () => irPara(s.inicio, s.fim) }, "▶"),
        el("span", { class: "mono" }, `[${fmt(s.inicio)}]`),
        el("em", {}, `“${s.texto.length > 160 ? s.texto.slice(0, 160) + "…" : s.texto}”`)))));
  }));
  mostrar("speakers");
}

async function aplicarSpeakers() {
  const mapa = {};
  let semEscolha = 0;
  for (const sel of $$(".map-sel")) {
    const r = sel.dataset.speaker;
    if (sel.value === "__outro") {
      mapa[r] = sel.parentElement.querySelector(".map-outro").value.trim() || DESCONHECIDO;
    } else {
      mapa[r] = sel.value;
      if (!sel.value) semEscolha++;
    }
  }
  if (semEscolha && !confirm(`${semEscolha} speaker(s) sem participante associado. Eles aparecerão com o código (ex.: SPEAKER_01). Continuar?`)) return;
  try {
    estado.proj = await api("PUT", `/api/projetos/${estado.proj.id}/speakers`, { speakers: mapa });
    estado.segs = estado.proj.segmentos;
    telaRevisao();
  } catch (e) { alert(e.message); }
}

// ------------------------------------------------------------------ revisão

function telaRevisao() {
  prepararPlayer();
  $("#rev-titulo").textContent = `${estado.proj.entrevista || estado.proj.arquivo_video} — ${estado.segs.length} trechos`;
  $("#status-salvo").textContent = estado.proj.atualizado_em ? `Salvo (${estado.proj.atualizado_em})` : "";
  mostrar("revisao");
  renderizar();
}

function preencherSelectPessoa(sel, atual) {
  sel.replaceChildren(...opcoesPessoas().map((n) => el("option", { value: n, ...(n === atual ? { selected: "" } : {}) }, n)));
}

function ajustarAltura(ta) {
  ta.style.height = "auto";
  ta.style.height = ta.scrollHeight + 2 + "px";
}

function renderizar() {
  indiceAtual = -1;
  const filtro = $("#filtro-pessoa");
  const valorFiltro = filtro.value;
  filtro.replaceChildren(el("option", { value: "" }, "Todas as pessoas"),
    ...opcoesPessoas().map((n) => el("option", { value: n, ...(n === valorFiltro ? { selected: "" } : {}) }, n)));
  $("#blocos").classList.toggle("oculto", estado.visao !== "blocos");
  $("#tabela-box").classList.toggle("oculto", estado.visao !== "tabela");
  if (estado.visao === "blocos") renderizarBlocos(); else renderizarTabela();
  aplicarFiltro();
}

function renderizarBlocos() {
  const tpl = $("#tpl-bloco");
  const frag = document.createDocumentFragment();
  estado.segs.forEach((s, i) => {
    const b = tpl.content.firstElementChild.cloneNode(true);
    b.dataset.i = i;
    const nome = nomePessoa(s);
    b.style.setProperty("--cor", corPessoa(nome));
    if (s.confianca !== null && s.confianca !== undefined && s.confianca < 0.6) {
      b.classList.add("baixa-confianca");
      b.title = "Trecho com baixa confiança na transcrição — vale conferir.";
    }
    const bt = $(".tempo", b);
    bt.textContent = `[${fmt(s.inicio)}]`;
    bt.onclick = () => irPara(s.inicio);
    const sel = $(".pessoa", b);
    preencherSelectPessoa(sel, nome);
    sel.onchange = () => { s.pessoa = sel.value; b.style.setProperty("--cor", corPessoa(sel.value)); agendarSalvar(); };
    const ti = $(".t-inicio", b), tf = $(".t-fim", b);
    ti.value = fmt(s.inicio, true); tf.value = fmt(s.fim, true);
    ti.onchange = () => alterarTempo(s, "inicio", ti);
    tf.onchange = () => alterarTempo(s, "fim", tf);
    const ta = $(".texto", b);
    ta.value = s.texto;
    ta.oninput = () => { s.texto = ta.value; ajustarAltura(ta); agendarSalvar(); };
    $(".dividir", b).onclick = () => dividir(i, ta.selectionStart);
    $(".juntar", b).onclick = () => juntar(i);
    $(".excluir", b).onclick = () => excluir(i);
    $(".juntar", b).disabled = i === estado.segs.length - 1;
    frag.append(b);
  });
  $("#blocos").replaceChildren(frag);
  $$("#blocos textarea").forEach(ajustarAltura);
}

function renderizarTabela() {
  const frag = document.createDocumentFragment();
  estado.segs.forEach((s, i) => {
    const sel = el("select", { onchange: () => { s.pessoa = sel.value; agendarSalvar(); } });
    preencherSelectPessoa(sel, nomePessoa(s));
    const ta = el("textarea", { rows: "1" });
    ta.value = s.texto;
    ta.oninput = () => { s.texto = ta.value; ajustarAltura(ta); agendarSalvar(); };
    const tr = el("tr", { "data-i": i },
      el("td", {}, el("button", { class: "tempo mono", onclick: () => irPara(s.inicio) }, fmt(s.inicio))),
      el("td", { class: "mono" }, fmt(s.fim)),
      el("td", {}, sel),
      el("td", {}, ta));
    frag.append(tr);
  });
  $("#corpo-tabela").replaceChildren(frag);
  $$("#corpo-tabela textarea").forEach(ajustarAltura);
}

function aplicarFiltro() {
  const termo = $("#busca").value.trim().toLowerCase();
  const pessoa = $("#filtro-pessoa").value;
  const seletor = estado.visao === "blocos" ? "#blocos .bloco" : "#corpo-tabela tr";
  $$(seletor).forEach((e) => {
    const s = estado.segs[Number(e.dataset.i)];
    const ok = (!termo || s.texto.toLowerCase().includes(termo)) && (!pessoa || nomePessoa(s) === pessoa);
    e.classList.toggle("oculto", !ok);
  });
}

function alterarTempo(s, campo, input) {
  const v = parseTempo(input.value);
  if (isNaN(v)) { alert("Tempo inválido. Use hh:mm:ss ou hh:mm:ss.d"); input.value = fmt(s[campo], true); return; }
  s[campo] = Math.round(v * 100) / 100;
  if (s.fim < s.inicio) {
    if (campo === "inicio") s.fim = s.inicio; else s.inicio = s.fim;
  }
  estado.segs.sort((a, b) => a.inicio - b.inicio);
  agendarSalvar();
  renderizar();
}

function dividir(i, pos) {
  const s = estado.segs[i];
  const texto = s.texto;
  if (pos > 0 && pos < texto.length && /\S/.test(texto[pos - 1]) && /\S/.test(texto[pos])) {
    // Cursor no meio de uma palavra: usa o espaço mais próximo.
    const antes = texto.lastIndexOf(" ", pos), depois = texto.indexOf(" ", pos);
    if (antes < 0) pos = depois; else if (depois < 0) pos = antes;
    else pos = pos - antes <= depois - pos ? antes : depois;
  }
  if (!pos || pos <= 0 || pos >= texto.length) {
    alert("Posicione o cursor no texto, no ponto onde o trecho deve ser dividido, e clique em ✂︎.");
    return;
  }
  const a = texto.slice(0, pos).trim(), b = texto.slice(pos).trim();
  if (!a || !b) return;
  // Estima o tempo do corte proporcionalmente à posição no texto.
  const corte = Math.round((s.inicio + (s.fim - s.inicio) * (pos / texto.length)) * 100) / 100;
  const novo = { ...s, inicio: corte, texto: b };
  s.fim = corte; s.texto = a;
  estado.segs.splice(i + 1, 0, novo);
  agendarSalvar();
  renderizar();
}

function juntar(i) {
  const a = estado.segs[i], b = estado.segs[i + 1];
  if (!b) return;
  if (nomePessoa(a) !== nomePessoa(b) && !confirm(`Os trechos são de pessoas diferentes (${nomePessoa(a)} / ${nomePessoa(b)}). Juntar mesmo assim (fica ${nomePessoa(a)})?`)) return;
  a.texto = `${a.texto} ${b.texto}`.trim();
  a.fim = Math.max(a.fim, b.fim);
  if (a.confianca != null && b.confianca != null) a.confianca = Math.min(a.confianca, b.confianca);
  estado.segs.splice(i + 1, 1);
  agendarSalvar();
  renderizar();
}

function excluir(i) {
  const s = estado.segs[i];
  if (!confirm(`Excluir o trecho [${fmt(s.inicio)}] de ${nomePessoa(s)}?\n\n“${s.texto.slice(0, 120)}”`)) return;
  estado.segs.splice(i, 1);
  agendarSalvar();
  renderizar();
}

function agendarSalvar() {
  $("#status-salvo").textContent = "Alterações não salvas…";
  clearTimeout(estado.timerSalvar);
  estado.timerSalvar = setTimeout(salvar, 800);
}

async function salvar() {
  clearTimeout(estado.timerSalvar);
  estado.timerSalvar = null;
  try {
    $("#status-salvo").textContent = "Salvando…";
    const r = await api("PUT", `/api/projetos/${estado.proj.id}/segmentos`, { segmentos: estado.segs });
    estado.proj.atualizado_em = r.atualizado_em;
    $("#status-salvo").textContent = `Salvo (${r.atualizado_em})`;
    $("#rev-titulo").textContent = `${estado.proj.entrevista || estado.proj.arquivo_video} — ${estado.segs.length} trechos`;
  } catch (e) {
    $("#status-salvo").textContent = "⚠ Erro ao salvar: " + e.message;
  }
}

async function exportar(formato) {
  if (estado.timerSalvar) await salvar();
  window.location.href = `/api/projetos/${estado.proj.id}/exportar/${formato}`;
}

// ------------------------------------------------------------------ inicialização

function iniciar() {
  $("#btn-enviar").onclick = enviarArquivos;
  $("#ir-inicio").onclick = () => { location.hash = ""; voltarInicio(); };
  $("#btn-add-participante").onclick = () => $("#corpo-participantes").append(linhaParticipante());
  $("#btn-processar").onclick = processar;
  $("#idioma").onchange = () => $("#idioma-outro").classList.toggle("oculto", $("#idioma").value !== "outro");
  $("#modo-speakers").onchange = atualizarModoSpeakers;
  $("#diarizar").onchange = atualizarModoSpeakers;
  $("#btn-voltar-config").onclick = telaParticipantes;
  $("#btn-aplicar-speakers").onclick = aplicarSpeakers;
  $("#btn-remapear").onclick = async () => { if (estado.timerSalvar) await salvar(); telaSpeakers(); };
  $$(".alternador button").forEach((b) => b.addEventListener("click", () => {
    estado.visao = b.dataset.visao;
    $$(".alternador button").forEach((x) => x.classList.toggle("ativo", x === b));
    renderizar();
  }));
  $("#busca").oninput = aplicarFiltro;
  $("#filtro-pessoa").onchange = aplicarFiltro;
  $$("[data-exp]").forEach((a) => a.addEventListener("click", (e) => { e.preventDefault(); exportar(a.dataset.exp); }));
  window.addEventListener("beforeunload", (e) => { if (estado.timerSalvar) { salvar(); e.preventDefault(); } });
  configurarPlayer();

  carregarSistema().then(() => {
    const m = location.hash.match(/p=([\w-]+)/);
    if (m) abrirProjeto(m[1]); else voltarInicio();
  });
}

function voltarInicio() {
  if (estado.timerSalvar) salvar();
  const player = $("#player");
  player.pause();
  mostrar("inicio");
  carregarLista();
}

iniciar();
