const main = document.querySelector("#main");
const API = "/api";
const FEATURED_ORDER = ["constituicao-1988", "5452-1943", "10406-2002", "2848-1940", "8078-1990", "8069-1990", "12965-2014", "13709-2018", "11340-2006", "14133-2021", "5172-1966"];
const esc = (value = "") => String(value).replace(/[&<>"']/g, ch => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
const datePt = value => value ? new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "short", year: "numeric", timeZone: "UTC" }).format(new Date(value)) : "Data não informada";
const lawPath = law => `/lei/${encodeURIComponent(law.slug)}`;
const externalIcon = '<svg class="external-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M14 3h7v7M21 3l-10 10"/><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/></svg>';
const searchIcon = `<svg class="search-icon" viewBox="0 0 24 24" fill="none" aria-hidden="true"><circle cx="10.8" cy="10.8" r="6.8" stroke="currentColor" stroke-width="1.7"/><path d="m16 16 4.3 4.3" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/></svg>`;

async function getJSON(url, options) {
  const response = await fetch(url, options);
  let data;
  try { data = await response.json(); } catch { data = {}; }
  if (!response.ok) throw new Error(data.detail || "Não foi possível carregar esta informação.");
  return data;
}

function setMeta(title, description) {
  document.title = title;
  const meta = document.querySelector('meta[name="description"]');
  if (meta) meta.content = description;
  const canonical = document.querySelector('link[rel="canonical"]');
  if (canonical) canonical.href = `${location.origin}${location.pathname}`;
}

function crumbs(items) {
  return `<nav class="breadcrumbs" aria-label="Você está em">${items.map((item, i) => `${i ? '<span class="crumb-sep">/</span>' : ""}${item.href ? `<a href="${esc(item.href)}">${esc(item.label)}</a>` : `<span aria-current="page">${esc(item.label)}</span>`}`).join("")}</nav>`;
}

function lawLabel(law) {
  if (law.law_type === "Constituição") return law.title;
  return `${law.law_type} nº ${law.number}/${law.year}`;
}

function searchResultRow(law, correction = false) {
  const designation = `${law.law_type} nº ${law.number}/${law.year}`;
  const article = law.article ? `<span> · Art. ${esc(law.article)}</span>` : "";
  return `<a class="suggestion-row" href="${lawPath(law)}${law.article ? `/artigo/${encodeURIComponent(law.article)}` : ""}">
    <span class="result-symbol" aria-hidden="true">${esc(law.law_type === "Constituição" ? "CF" : law.law_type.slice(0, 2).toUpperCase())}</span>
    <span class="suggestion-main"><span class="suggestion-title">${esc(law.title)}</span><span class="suggestion-subtitle">${esc(designation)}${article}</span></span>
    ${correction ? '<span class="suggestion-correction"><strong>Talvez você quis dizer</strong></span>' : `<span class="suggestion-arrow">${externalIcon}</span>`}
  </a>`;
}

function searchBox({ placeholder = "Pesquise uma lei, artigo, município ou assunto...", autofocus = false } = {}) {
  return `<form class="search-box" data-search-form role="search" autocomplete="off">
    ${searchIcon}<input class="search-input" name="q" type="search" maxlength="180" aria-label="Pesquisar legislação" placeholder="${esc(placeholder)}" ${autofocus ? "autofocus" : ""} aria-controls="search-suggestions" aria-expanded="false" />
    <span class="search-key"><kbd>↵</kbd> para buscar</span>
    <div class="suggestions" id="search-suggestions" role="listbox" hidden></div>
  </form>`;
}

function bindSearch(scope = document) {
  scope.querySelectorAll("[data-search-form]").forEach(form => {
    const input = form.querySelector("input[name=q]");
    const box = form.querySelector(".suggestions");
    let timer;
    let active = -1;
    let resultRows = [];

    const openBox = () => { box.hidden = false; input.setAttribute("aria-expanded", "true"); };
    const closeBox = () => { box.hidden = true; input.setAttribute("aria-expanded", "false"); active = -1; };
    const navigateSearch = () => {
      const first = resultRows[0];
      if (first) location.href = lawPath(first) + (first.article ? `/artigo/${encodeURIComponent(first.article)}` : "");
      else location.href = `/buscar?q=${encodeURIComponent(input.value.trim())}`;
    };
    input.addEventListener("input", () => {
      clearTimeout(timer);
      const query = input.value.trim();
      if (!query) { closeBox(); return; }
      timer = setTimeout(async () => {
        try {
          const result = await getJSON(`${API}/search?q=${encodeURIComponent(query)}&limit=6`);
          resultRows = result.results || [];
          if (!resultRows.length) {
            box.innerHTML = `<div class="suggestion-empty">Nenhuma correspondência no catálogo inicial. Tente o número da norma ou outro nome.</div><div class="suggestion-correction"><a href="/buscar?q=${encodeURIComponent(query)}">Ver busca completa ${externalIcon}</a></div>`;
          } else {
            box.innerHTML = `<div class="suggestion-heading">Normas encontradas</div>${resultRows.map(row => searchResultRow(row)).join("")}${result.suggestion ? `<div class="suggestion-correction">Sugestão aproximada para <strong>${esc(query)}</strong></div>` : ""}`;
          }
          openBox();
        } catch {
          box.innerHTML = `<div class="suggestion-empty">A busca está indisponível por um instante. Tente novamente.</div>`;
          openBox();
        }
      }, 160);
    });
    input.addEventListener("keydown", event => {
      const rows = [...box.querySelectorAll(".suggestion-row")];
      if (event.key === "ArrowDown" && rows.length) {
        event.preventDefault(); active = (active + 1) % rows.length;
        rows.forEach((row, i) => row.setAttribute("aria-selected", String(i === active)));
      } else if (event.key === "ArrowUp" && rows.length) {
        event.preventDefault(); active = (active - 1 + rows.length) % rows.length;
        rows.forEach((row, i) => row.setAttribute("aria-selected", String(i === active)));
      } else if (event.key === "Enter") {
        event.preventDefault();
        if (active >= 0 && rows[active]) location.href = rows[active].href;
        else navigateSearch();
      } else if (event.key === "Escape") closeBox();
    });
    form.addEventListener("submit", event => { event.preventDefault(); navigateSearch(); });
    document.addEventListener("click", event => { if (!form.contains(event.target)) closeBox(); }, { once: true });
  });
}

function catalogRow(law) {
  const material = law.materialization_status === "ready" ? "Texto estruturado" : "Fonte oficial";
  return `<a class="catalog-row" href="${lawPath(law)}">
    <span class="catalog-id">${esc(law.law_type)} ${law.law_type === "Constituição" ? "" : `nº ${esc(law.number)}/${esc(law.year)}`}</span>
    <span class="catalog-title">${esc(law.title)}</span>
    <span class="catalog-status"><i class="ready-mark"></i>${esc(material)}</span>
    <span class="row-arrow">${externalIcon}</span>
  </a>`;
}

async function renderHome() {
  setMeta("LeiAberta — veja o que mudou", "Pesquise legislação brasileira e acompanhe o texto, as fontes oficiais e as alterações documentadas.");
  main.innerHTML = `<div class="home-shell">
    <section class="hero">
      <div><div class="eyebrow"><span class="eyebrow-line"></span> Legislação brasileira, em contexto</div>
        <h1>Veja o que mudou.<br/><span>Quem mudou. E por quê.</span></h1>
        <p class="hero-copy">Um acervo público para pesquisar normas, ler seus dispositivos e acompanhar alterações com links para as fontes oficiais.</p>
      </div>
      <aside class="hero-aside" aria-label="Sobre a plataforma"><span class="hero-aside-label">Um registro que se pode conferir</span><p><strong>Texto, histórico e origem</strong> reunidos em um só lugar — com cada informação ligada à sua fonte.</p><span class="hero-aside-rule"></span><span class="hero-aside-label">Fontes públicas · leitura aberta</span></aside>
    </section>
    <div class="search-wrap"><label class="search-label" for="home-search">Encontre uma norma ou dispositivo</label>${searchBox({})}</div>
    <section class="catalog-section" id="acervo">
      <div class="section-head"><div><div class="section-kicker">Ponto de partida</div><h2>Normas em destaque</h2></div><a class="section-action" href="/buscar?q=">Ver acervo ${externalIcon}</a></div>
      <div class="catalog-list" id="catalog-list"><div class="page-loading"><span class="spinner"></span> Carregando normas</div></div>
      <div class="catalog-footer"><span id="catalog-count">Catálogo federal inicial</span><span>Os textos são consultados em <a href="https://www.planalto.gov.br/ccivil_03/" target="_blank" rel="noopener">fontes oficiais ${externalIcon}</a></span></div>
    </section>
    <div class="home-lower">
      <section id="como-funciona"><div class="section-kicker">Como funciona</div><h2 class="lower-title">Do texto oficial ao artigo</h2><p class="lower-copy">O catálogo começa pelos dados essenciais. Quando você abre uma norma, o LeiAberta obtém o documento oficial, organiza os dispositivos e guarda uma cópia verificável.</p>
        <div class="step-list"><div class="step-row"><span class="step-number">01</span><div><strong>Localizamos a fonte</strong><span>O documento oficial é a referência.</span></div></div><div class="step-row"><span class="step-number">02</span><div><strong>Estruturamos os dispositivos</strong><span>Artigos e subdivisões recebem identificadores estáveis.</span></div></div><div class="step-row"><span class="step-number">03</span><div><strong>Registramos vínculos comprovados</strong><span>Alterações aparecem quando a fonte permite identificá-las.</span></div></div></div>
      </section>
      <section id="fontes"><div class="section-kicker">Transparência</div><h2 class="lower-title">A fonte vem primeiro.</h2><p class="lower-copy">Cada texto materializado mantém o endereço oficial, a data da consulta e a impressão digital do documento arquivado. Informações que não conseguimos confirmar aparecem como indisponíveis.</p>
        <div class="source-note"><strong>Sem atalhos sobre autoria.</strong> O vínculo entre uma alteração e sua origem só é exibido quando consta na legislação ou em documento público verificável.</div>
        <div class="metric-strip" id="metric-strip"><div class="metric"><strong>—</strong><span>normas no catálogo</span></div><div class="metric"><strong>—</strong><span>artigos estruturados</span></div></div>
      </section>
    </div>
  </div>`;
  const form = main.querySelector("[data-search-form]");
  if (form) form.querySelector("input").id = "home-search";
  bindSearch(main);
  try {
    const [laws, stats] = await Promise.all([getJSON(`${API}/laws?limit=20`), getJSON(`${API}/stats`)]);
    const featured = laws.items.sort((a, b) => FEATURED_ORDER.indexOf(a.slug) - FEATURED_ORDER.indexOf(b.slug));
    document.querySelector("#catalog-list").innerHTML = featured.map(catalogRow).join("");
    document.querySelector("#catalog-count").textContent = `${stats.indexed_laws} normas federais indexadas · cobertura em expansão`;
    document.querySelector("#metric-strip").innerHTML = `<div class="metric"><strong>${stats.indexed_laws}</strong><span>normas no catálogo inicial</span></div><div class="metric"><strong>${stats.structured_articles}</strong><span>artigos estruturados</span></div>`;
  } catch (error) {
    document.querySelector("#catalog-list").innerHTML = `<div class="empty-state">O catálogo está indisponível no momento. ${esc(error.message)}</div>`;
  }
}

function badgeClass(status) {
  return status === "ready" ? "Ready" : status === "unavailable" ? "Indisponível" : "Em preparação";
}

function lawHeader(law, activeTab, crumbsList) {
  return `${crumbs(crumbsList)}<header class="law-header">
    <div class="law-eyebrow"><span class="eyebrow-line"></span>${esc(law.jurisdiction === "federal" ? "Legislação federal" : law.jurisdiction)} · ${esc(law.law_type)}</div>
    <h1>${esc(law.title)}</h1><div class="law-number">${esc(lawLabel(law))}</div>
    <div class="law-meta"><span class="law-status">${esc(law.status.toUpperCase())}</span><span>Publicada em <b>${datePt(law.published_at)}</b></span><span>${law.article_count || 0} artigos estruturados</span></div>
  </header><div class="law-toolbar"><nav class="law-tabs" aria-label="Seções da norma">
    <a class="law-tab ${activeTab === "text" ? "active" : ""}" href="${lawPath(law)}">Texto</a>
    <a class="law-tab ${activeTab === "history" ? "active" : ""}" href="${lawPath(law)}/historico">Histórico</a>
  </nav><a class="source-link" href="${esc(law.source_url)}" target="_blank" rel="noopener">Fonte oficial ${externalIcon}</a></div>`;
}

function coverageCard(law, recentChange) {
  const c = law.coverage || {};
  const val = status => ({ available: "Disponível", partial: "Parcial", not_materialized: "A preparar", not_identified: "Não identificado", not_available: "Indisponível" }[status] || "A preparar");
  return `<aside class="law-aside"><div class="aside-block"><div class="aside-heading">Cobertura desta norma</div>
    <div class="aside-row"><span>Fonte oficial</span><strong>${esc(val(c.official_source))}</strong></div>
    <div class="aside-row"><span>Texto estruturado</span><strong>${esc(val(c.structured_text))}</strong></div>
    <div class="aside-row"><span>Histórico</span><strong>${esc(val(c.history))}</strong></div>
    <div class="aside-row"><span>Autoria e votos</span><strong>${esc(val(c.authors || c.votes))}</strong></div>
    <p class="coverage-caption">A cobertura indica quais dados foram localizados em documentos públicos.</p>
  </div><div class="aside-block"><div class="aside-heading">Última alteração vinculada</div>
    ${recentChange ? `<a class="aside-update" href="/diff/${encodeURIComponent(recentChange.id)}">${esc(recentChange.source_law_label)}<span class="aside-update-meta">${datePt(recentChange.changed_at)} · ${esc(recentChange.summary)}</span></a>` : `<p class="aside-empty">${c.history === "partial" ? "Há vínculos documentados no histórico." : "Informação ainda não identificada em fonte oficial."}</p>`}
  </div><div class="aside-block"><div class="aside-heading">Documento consultado</div>
    <div class="aside-row"><span>Origem</span><strong>Planalto</strong></div>
    <div class="aside-row"><span>Checksum</span><strong>${law.coverage?.snapshot_checksum ? `<code>${esc(law.coverage.snapshot_checksum.slice(0, 12))}…</code>` : "Aguardando"}</strong></div>
  </div></aside>`;
}

function progressPanel(job) {
  const stage = job?.stage || 0;
  const steps = ["Fonte localizada", "Texto obtido", "Dispositivos", "Histórico" ];
  return `<div class="law-progress" role="status" aria-live="polite"><span class="spinner" aria-hidden="true"></span><div style="flex:1">
    <p class="progress-title">Estamos preparando esta norma</p><p class="progress-copy">${esc(job?.message || "A fonte foi localizada. O texto está entrando no acervo.")}</p>
    <div class="progress-steps">${steps.map((step, i) => `<span class="progress-step ${stage > i + 1 ? "complete" : stage === i + 1 ? "current" : ""}">${esc(step)}</span>`).join("")}</div>
  </div></div>`;
}

function articleHtml(nodes) {
  const groups = [];
  let current;
  for (const node of nodes) {
    if (node.type === "article") {
      current = { article: node, clauses: [] };
      groups.push(current);
    } else if (current) current.clauses.push(node);
  }
  if (!groups.length) return `<div class="empty-state">O documento oficial ainda não retornou artigos estruturados.</div>`;
  return `<div class="article-list">${groups.map(group => {
    const number = group.article.id.replace(/^art:/, "");
    const title = group.article.label.endsWith("º") || group.article.label.endsWith(".") ? group.article.label : `${group.article.label}.`;
    const intro = group.article.text ? `<p class="article-lead">${esc(group.article.text)}</p>` : "";
    const clauses = group.clauses.map(node => {
      const kind = node.type === "item" ? " item" : node.type === "subitem" ? " subitem" : "";
      const label = node.type === "paragraph" ? `${node.label} ` : `${node.label} — `;
      return `<p class="article-clause${kind}" id="${esc(node.id.replaceAll(":", "-"))}"><strong class="article-clause-label">${esc(label)}</strong>${esc(node.text)}</p>`;
    }).join("");
    return `<section class="law-article" id="article-${esc(number)}"><div class="article-index">${esc(number)}</div><div class="article-body"><h3>${esc(title)}</h3>${intro}${clauses}</div></section>`;
  }).join("")}</div>`;
}

async function renderLaw(slug, targetArticle = "") {
  let initial;
  try { initial = await getJSON(`${API}/laws/${encodeURIComponent(slug)}`); }
  catch (error) { renderNotFound(error.message); return; }
  const law = initial.law;
  setMeta(`${lawLabel(law)} — ${law.title} | LeiAberta`, `${law.title}: texto atual, histórico documentado e fonte oficial no LeiAberta.`);
  const trail = [{ label: "Início", href: "/" }, { label: "Acervo", href: "/#acervo" }, { label: law.title }];
  if (law.materialization_status !== "ready") {
    main.innerHTML = `<div class="content-shell">${lawHeader(law, "text", trail)}<div class="law-layout"><div class="law-content"><p class="law-intro">${esc(law.description || "Texto e metadados da norma federal.")}</p>${initial.job?.status === "failed" ? `<div class="error-banner" role="alert">${esc(initial.job.message)} <button class="text-button" data-retry="${esc(slug)}">Tentar novamente</button></div>` : progressPanel(initial.job)}<p class="aside-empty">Enquanto preparamos o texto, você pode consultar o documento integral na fonte oficial.</p></div>${coverageCard(law, null)}</div></div>`;
    const retry = main.querySelector("[data-retry]");
    retry?.addEventListener("click", async () => { await getJSON(`${API}/laws/${encodeURIComponent(slug)}/hydrate`, { method: "POST" }); renderLaw(slug, targetArticle); });
    if (initial.job?.status !== "failed") pollLaw(slug, targetArticle);
    return;
  }
  try {
    const [nodeData, history] = await Promise.all([getJSON(`${API}/laws/${encodeURIComponent(slug)}/nodes`), getJSON(`${API}/laws/${encodeURIComponent(slug)}/history`)]);
    const recent = history.items?.[0];
    const article = targetArticle ? `<div class="law-intro">Abrindo o Art. ${esc(targetArticle)} · <a class="section-action" href="#article-${encodeURIComponent(targetArticle)}">Ir ao dispositivo ↓</a></div>` : `<p class="law-intro">${esc(law.description || "Texto consultado na fonte oficial.")} Esta versão foi estruturada a partir do documento público indicado abaixo.</p>`;
    main.innerHTML = `<div class="content-shell">${lawHeader(law, "text", trail)}<div class="law-layout"><div class="law-content">${article}${articleHtml(nodeData.items || [])}</div>${coverageCard(law, recent)}</div></div>`;
    if (targetArticle) setTimeout(() => document.getElementById(`article-${CSS.escape(targetArticle)}`)?.scrollIntoView({ block: "start" }), 50);
  } catch (error) {
    main.innerHTML = `<div class="content-shell">${lawHeader(law, "text", trail)}<div class="error-banner">${esc(error.message)}</div></div>`;
  }
}

async function pollLaw(slug, article) {
  for (let i = 0; i < 45; i++) {
    await new Promise(resolve => setTimeout(resolve, 1600));
    try {
      const data = await getJSON(`${API}/laws/${encodeURIComponent(slug)}`);
      if (data.law.materialization_status === "ready" || data.job?.status === "failed") {
        renderLaw(slug, article);
        return;
      }
    } catch { return; }
  }
}

async function renderHistory(slug) {
  let detail;
  try { detail = await getJSON(`${API}/laws/${encodeURIComponent(slug)}`); }
  catch (error) { renderNotFound(error.message); return; }
  const law = detail.law;
  setMeta(`Histórico: ${law.title} | LeiAberta`, `Alterações documentadas de ${law.title} e links às fontes oficiais.`);
  const trail = [{ label: "Início", href: "/" }, { label: law.title, href: lawPath(law) }, { label: "Histórico" }];
  try {
    const history = await getJSON(`${API}/laws/${encodeURIComponent(slug)}/history`);
    const partial = history.coverage === "partial";
    const items = history.items || [];
    main.innerHTML = `<div class="content-shell">${lawHeader(law, "history", trail)}<section class="history-layout">
      <p class="history-intro">Alterações ligadas a esta norma por referências identificadas em documentos oficiais. Cada registro abre o dispositivo e a fonte que sustenta o vínculo.</p>
      ${partial ? `<div class="history-callout">Histórico parcial. A linha do tempo mostra apenas alterações cuja origem foi confirmada; outros vínculos ainda não foram identificados.</div>` : ""}
      ${items.length ? `<div class="timeline">${items.map(item => `<div class="timeline-item"><div class="timeline-date">${datePt(item.changed_at)}</div><a class="timeline-card" href="/diff/${encodeURIComponent(item.id)}"><span class="timeline-source">${esc(item.source_law_label)}</span><h3>${esc(item.summary)}</h3><p>Dispositivo ${esc(item.node_id.replaceAll(":", " · "))}</p><span class="timeline-view">Ver antes e depois ${externalIcon}</span></a></div>`).join("")}</div>` : `<div class="empty-state"><h2>O histórico está sendo preparado</h2><p>Quando uma alteração puder ser vinculada a uma fonte oficial, ela aparecerá aqui.</p><a class="section-action" href="${esc(law.source_url)}" target="_blank" rel="noopener">Consultar o texto oficial ${externalIcon}</a></div>`}
    </section></div>`;
    if (!items.length && law.materialization_status !== "ready") pollHistory(slug);
  } catch (error) {
    main.innerHTML = `<div class="content-shell">${lawHeader(law, "history", trail)}<div class="error-banner">${esc(error.message)}</div></div>`;
  }
}

async function pollHistory(slug) {
  for (let i = 0; i < 30; i++) {
    await new Promise(resolve => setTimeout(resolve, 1800));
    const data = await getJSON(`${API}/laws/${encodeURIComponent(slug)}/history`).catch(() => null);
    if (data?.items?.length) { renderHistory(slug); return; }
  }
}

async function renderDiff(changeId) {
  let change;
  try { change = await getJSON(`${API}/changes/${encodeURIComponent(changeId)}`); }
  catch (error) { renderNotFound(error.message); return; }
  const law = change.law;
  setMeta(`${change.summary} — ${law.title} | LeiAberta`, `Texto anterior e posterior de uma alteração documentada em ${change.source_law_label}.`);
  const nodeName = change.node_id.replaceAll(":", " · ");
  const before = change.before_text || "Este dispositivo ainda não existia no texto anterior consultado.";
  main.innerHTML = `<div class="content-shell">${crumbs([{ label: "Início", href: "/" }, { label: law.title, href: lawPath(law) }, { label: "Histórico", href: `${lawPath(law)}/historico` }, { label: "Alteração" }])}
    <section class="diff-layout"><div class="law-eyebrow"><span class="eyebrow-line"></span> Alteração documentada</div><h1 class="diff-title">${esc(change.summary)}</h1><p class="diff-subtitle">${esc(law.title)} · ${esc(nodeName)}</p>
    <div class="diff-meta"><span>${datePt(change.changed_at)}</span><span>Origem: <a href="${esc(change.source_url)}" target="_blank" rel="noopener">${esc(change.source_law_label)} ${externalIcon}</a></span><span>Tipo: ${esc(change.change_type === "ADD" ? "Dispositivo incluído" : change.change_type)}</span></div>
    <div class="diff-panes"><section class="diff-pane before"><div class="diff-pane-head"><span>Antes</span><span>Texto anterior</span></div><p class="diff-text ${change.before_text ? "" : "diff-empty"}">${esc(before)}</p></section>
      <section class="diff-pane after"><div class="diff-pane-head"><span>Depois</span><span>${esc(nodeName)}</span></div><p class="diff-text">${esc(change.after_text)}</p></section></div>
    <div class="diff-source-note"><strong>Origem do vínculo.</strong> O texto consolidado da norma identifica esta inclusão pela ${esc(change.source_law_label)}. O texto do dispositivo foi conferido no documento oficial da norma modificadora e na versão consolidada. <a class="source-link" href="${esc(change.law_source_url)}" target="_blank" rel="noopener">Fonte do texto consolidado ${externalIcon}</a></div>
    </section></div>`;
}

async function renderSearchPage(query) {
  setMeta(`Busca: ${query || "legislação"} | LeiAberta`, "Pesquise leis e dispositivos no catálogo público do LeiAberta.");
  main.innerHTML = `<div class="content-shell"><div class="eyebrow"><span class="eyebrow-line"></span> Busca no acervo</div><h1 class="diff-title" style="margin:13px 0 17px">Encontre uma norma.</h1>${searchBox({ placeholder: "Número, nome, sigla ou artigo..." })}<section style="padding-top:28px" id="search-results"><div class="page-loading"><span class="spinner"></span> Buscando no catálogo</div></section></div>`;
  const form = main.querySelector("[data-search-form]");
  form.querySelector("input").value = query;
  bindSearch(main);
  if (!query) { main.querySelector("#search-results").innerHTML = `<div class="empty-state">Digite um nome, número ou artigo para pesquisar.</div>`; return; }
  try {
    const result = await getJSON(`${API}/search?q=${encodeURIComponent(query)}&limit=30`);
    const el = main.querySelector("#search-results");
    if (!result.results.length) {
      el.innerHTML = `<div class="empty-state"><h2>Nenhuma norma encontrada no catálogo inicial</h2><p>O catálogo está sendo ampliado. Confira a grafia ou tente informar número e ano.</p><a class="source-link" href="https://www.lexml.gov.br/busca/" target="_blank" rel="noopener">Pesquisar na Rede LexML ${externalIcon}</a></div>`;
    } else {
      el.innerHTML = `<div class="section-kicker">${result.results.length} resultado${result.results.length === 1 ? "" : "s"}${result.suggestion ? ` · sugestão aproximada para “${esc(query)}”` : ""}</div><div class="catalog-list" style="margin-top:12px">${result.results.map(catalogRow).join("")}</div>${result.parsed.article ? `<p class="catalog-footer">A busca também identificou o Art. ${esc(result.parsed.article)}.</p>` : ""}`;
    }
  } catch (error) { main.querySelector("#search-results").innerHTML = `<div class="error-banner">${esc(error.message)}</div>`; }
}

function renderNotFound(message = "Página não encontrada.") {
  setMeta("Página não encontrada | LeiAberta", "A página solicitada não foi encontrada no LeiAberta.");
  main.innerHTML = `<div class="content-shell"><div class="empty-state"><div class="eyebrow"><span class="eyebrow-line"></span> LeiAberta</div><h2>Não encontramos esta página.</h2><p>${esc(message)}</p><a class="section-action" href="/">Voltar ao acervo ${externalIcon}</a></div></div>`;
}

function route() {
  const path = decodeURIComponent(location.pathname);
  const diff = path.match(/^\/diff\/([^/]+)/);
  if (diff) return renderDiff(diff[1]);
  const law = path.match(/^\/lei\/([^/]+)(?:\/(historico|artigo\/([^/]+)))?/);
  if (law) {
    if (law[2] === "historico") return renderHistory(law[1]);
    if (law[3]) return renderLaw(law[1], law[3]);
    return renderLaw(law[1]);
  }
  if (path === "/buscar") return renderSearchPage(new URLSearchParams(location.search).get("q") || "");
  if (path === "/" || path === "") return renderHome();
  renderNotFound();
}

route();
