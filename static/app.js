const main = document.querySelector("#main");
const API = "/api";
const FEATURED_ORDER = ["constituicao-1988", "5452-1943", "10406-2002", "2848-1940", "8078-1990", "8069-1990", "12965-2014", "13709-2018", "11340-2006", "14133-2021", "5172-1966"];
const esc = (value = "") => String(value).replace(/[&<>"']/g, ch => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
const safeHttpHref = value => { try { const url = new URL(String(value)); return ["http:", "https:"].includes(url.protocol) ? esc(url.href) : "#"; } catch { return "#"; } };
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

function copyLinkControl(label = "Copiar link desta página") {
  return `<div class="copy-link-control"><button type="button" class="copy-link-button" data-copy-page-link>${esc(label)}</button><span role="status" aria-live="polite" class="copy-link-status"></span></div>`;
}

function bindPageLinkCopy(scope = main) {
  scope.querySelectorAll("[data-copy-page-link]").forEach(button => {
    button.addEventListener("click", async () => {
      let copied = false;
      try {
        if (navigator.clipboard?.writeText) {
          await navigator.clipboard.writeText(location.href);
          copied = true;
        }
      } catch { /* Fall through to the selection-based clipboard path. */ }
      if (!copied) {
        const field = document.createElement("textarea");
        field.value = location.href;
        field.setAttribute("readonly", "");
        field.style.position = "fixed";
        field.style.opacity = "0";
        document.body.append(field);
        field.select();
        try { copied = document.execCommand("copy"); } catch { copied = false; }
        field.remove();
      }
      const status = button.parentElement.querySelector(".copy-link-status");
      if (status) status.textContent = copied ? "Link copiado." : "Não foi possível copiar. Você pode copiar o endereço do navegador.";
    });
  });
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
            const heading = result.parsed?.article && resultRows.length > 1
              ? `O Art. ${esc(result.parsed.article)} aparece em várias normas`
              : "Normas encontradas";
            box.innerHTML = `<div class="suggestion-heading">${heading}</div>${resultRows.map(row => searchResultRow(row)).join("")}${result.suggestion ? `<div class="suggestion-correction">Sugestão aproximada para <strong>${esc(query)}</strong></div>` : ""}`;
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
  const material = law.materialization_status === "ready" ? "Texto estruturado" : law.materialization_status === "partial" ? "Texto parcial · auditoria pendente" : "Fonte oficial";
  return `<a class="catalog-row" href="${lawPath(law)}">
    <span class="catalog-id">${esc(law.law_type)} ${law.law_type === "Constituição" ? "" : `nº ${esc(law.number)}/${esc(law.year)}`}</span>
    <span class="catalog-title">${esc(law.title)}</span>
    <span class="catalog-status"><i class="ready-mark"></i>${esc(material)}</span>
    <span class="row-arrow">${externalIcon}</span>
  </a>`;
}

async function renderHome() {
  setMeta("LeiAberta — entenda como uma lei chegou ao texto atual", "Pesquise legislação brasileira e siga alterações verificadas até suas fontes oficiais.");
  main.innerHTML = `<div class="home-shell">
    <section class="hero">
      <div><div class="eyebrow"><span class="eyebrow-line"></span> Legislação brasileira, em contexto</div>
        <h1>Entenda como uma lei<br/><span>chegou ao texto atual.</span></h1>
        <p class="hero-copy">Pesquise uma lei, artigo, município ou assunto e siga as alterações até suas fontes oficiais.</p>
      </div>
      <aside class="hero-aside" aria-label="Sobre a plataforma"><span class="hero-aside-label">Um registro que se pode conferir</span><p><strong>Texto, histórico e origem</strong> reunidos em um só lugar — com cada informação ligada à sua fonte.</p><span class="hero-aside-rule"></span><span class="hero-aside-label">Fontes públicas · leitura aberta</span></aside>
    </section>
    <div class="search-wrap"><label class="search-label" for="home-search">Encontre uma norma ou dispositivo</label>${searchBox({})}<div class="search-examples">Experimente: ${[["LGPD","LGPD"],["LGDP","LGDP"],["13709/18","13709/18"],["Art. 7º da LGPD","art 7 lgpd"],["Lei Maria da Penha","Lei Maria da Penha"]].map(([label,q])=>`<a href="/buscar?q=${encodeURIComponent(q)}">${label}</a>`).join(" · ")}</div></div>
    <a class="hero-cta" href="/diff/be3a1531-edaa-5a78-94ca-70c6544e3853"><span><small>DEMO · CÓDIGO CIVIL</small><strong>Veja o antes e depois de um artigo</strong><em>Art. 389 · Lei 14.905/2024</em></span><b>Ver alteração →</b></a>
    <section class="catalog-section" id="acervo">
      <div class="section-head"><div><div class="section-kicker">Ponto de partida</div><h2>Normas em destaque</h2></div><a class="section-action" href="/buscar?q=">Ver acervo ${externalIcon}</a></div>
      <div class="catalog-list" id="catalog-list"><div class="page-loading"><span class="spinner"></span> Carregando normas</div></div>
    <div class="catalog-footer"><span id="catalog-count">Catálogo atual das fontes integradas</span><span>Catálogo não equivale à totalidade da legislação brasileira.</span></div>
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
    const featured = laws.items.sort((a, b) => (FEATURED_ORDER.indexOf(a.slug) < 0 ? 999 : FEATURED_ORDER.indexOf(a.slug)) - (FEATURED_ORDER.indexOf(b.slug) < 0 ? 999 : FEATURED_ORDER.indexOf(b.slug)));
    document.querySelector("#catalog-list").innerHTML = featured.map(catalogRow).join("");
    document.querySelector("#catalog-count").textContent = `${Number(stats.indexed_laws).toLocaleString("pt-BR")} registros catalogados nas fontes integradas`;
    document.querySelector("#metric-strip").innerHTML = `<div class="metric"><strong>${Number(stats.indexed_laws).toLocaleString("pt-BR")}</strong><span>registros catalogados</span></div><div class="metric"><strong>${Number(stats.materialized_laws).toLocaleString("pt-BR")}</strong><span>normas com texto</span></div><div class="metric"><strong>${Number(stats.enumerated_sources).toLocaleString("pt-BR")}</strong><span>fontes enumeradas</span></div><div class="metric"><strong>${Number(stats.documented_changes).toLocaleString("pt-BR")}</strong><span>alterações documentadas</span></div>`;
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
    <div class="law-meta"><span class="law-status">${esc(law.status.toUpperCase())}</span><span>Publicada em <b>${datePt(law.published_at)}</b></span>${law.signed_at ? `<span>Assinada em <b>${datePt(law.signed_at)}</b></span>` : ""}<span>${law.article_count || 0} artigos estruturados</span></div>
  </header><div class="law-toolbar"><nav class="law-tabs" aria-label="Seções da norma">
    <a class="law-tab ${activeTab === "text" ? "active" : ""}" href="${lawPath(law)}">Texto</a>
    <a class="law-tab ${activeTab === "history" ? "active" : ""}" href="${lawPath(law)}/historico">Histórico</a>
    <a class="law-tab ${activeTab === "blame" ? "active" : ""}" href="${lawPath(law)}/blame">Blame</a>
    <a class="law-tab ${activeTab === "proceedings" ? "active" : ""}" href="${lawPath(law)}/tramitacao">Tramitação</a>
  </nav><a class="source-link" href="${esc(law.source_url)}" target="_blank" rel="noopener">Fonte oficial ${externalIcon}</a></div>`;
}

function coverageCard(law, recentChange) {
  const c = law.coverage || {};
  const val = status => ({ available: "Disponível", complete: "Completo no intervalo verificado", partial: "Parcial", queued: "Na fila", running: "Em andamento", unavailable: "Fonte indisponível", failed: "Falhou", not_requested: "Ainda não reconstruído", not_materialized: "Ainda não reconstruído", not_identified: "Não identificado", not_available: "Indisponível" }[status] || "Não verificado");
  return `<aside class="law-aside"><div class="aside-block"><div class="aside-heading">Cobertura desta norma</div>
    <div class="aside-row"><span>Fonte oficial</span><strong>${esc(val(c.official_source))}</strong></div>
    <div class="aside-row"><span>Texto estruturado</span><strong>${esc(val(c.structured_text))}</strong></div>
    <div class="aside-row"><span>Histórico</span><strong>${esc(val(c.history))}</strong></div>
    <div class="aside-row"><span>Autoria e votos</span><strong>${esc(val(c.authors || c.votes))}</strong></div>
    <p class="coverage-caption">A cobertura indica quais dados foram localizados em documentos públicos.</p>
  </div><div class="aside-block"><div class="aside-heading">Última alteração vinculada</div>
    ${recentChange ? `<a class="aside-update" href="/diff/${encodeURIComponent(recentChange.id)}">${esc(recentChange.source_law_label)}<span class="aside-update-meta">${datePt(recentChange.changed_at)} · ${esc(recentChange.summary)}</span></a>` : `<p class="aside-empty">${c.history === "partial" ? "Há vínculos documentados no histórico." : "Informação ainda não identificada em fonte oficial."}</p>`}
  </div><div class="aside-block"><div class="aside-heading">Documento consultado</div>
    <div class="aside-row"><span>Origem</span><strong>${esc(law.source_name || "Fonte oficial")}</strong></div>
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

function articleHtml(nodes, slug) {
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
    const provenanceHref = `${lawPath({ slug })}/blame?node=${encodeURIComponent(group.article.id)}`;
    const intro = group.article.text ? `<p class="article-lead">${esc(group.article.text)}</p>` : "";
    const clauses = group.clauses.map(node => {
      const kind = node.type === "item" ? " item" : node.type === "subitem" ? " subitem" : "";
      const label = node.type === "paragraph" ? `${node.label} ` : `${node.label} — `;
      return `<p class="article-clause${kind}" id="${esc(node.id.replaceAll(":", "-"))}"><strong class="article-clause-label">${esc(label)}</strong>${esc(node.text)} <a class="why-inline" href="${lawPath({ slug })}/blame?node=${encodeURIComponent(node.id)}">Por que este trecho?</a></p>`;
    }).join("");
    return `<section class="law-article" id="article-${esc(number)}"><div class="article-index">${esc(number)}</div><div class="article-body"><h3>${esc(title)}</h3>${intro}<a class="why-inline" href="${provenanceHref}">Por que este artigo está assim? →</a>${clauses}</div></section>`;
  }).join("")}</div>`;
}

async function renderLaw(slug, targetArticle = "") {
  let initial;
  try { initial = await getJSON(`${API}/laws/${encodeURIComponent(slug)}`); }
  catch (error) { renderNotFound(error.message); return; }
  const law = initial.law;
  setMeta(`${lawLabel(law)} — ${law.title} | LeiAberta`, `${law.title}: texto atual, histórico documentado e fonte oficial no LeiAberta.`);
  const trail = [{ label: "Início", href: "/" }, { label: "Acervo", href: "/#acervo" }, { label: law.title }];
  if (!initial.version) {
    if (!initial.materializable) {
      main.innerHTML = `<div class="content-shell">${lawHeader(law, "text", trail)}<div class="law-layout"><div class="law-content"><p class="law-intro">${esc(law.description || "Metadados registrados no acervo oficial do Senado.")}</p><div class="history-callout">Encontramos a norma no catálogo oficial, mas ainda não há adapter para baixar e estruturar seu texto integral. A data abaixo é a de assinatura; a data de publicação não foi identificada na listagem consultada.</div><p><a class="section-action" href="${esc(law.source_url)}" target="_blank" rel="noopener">Consultar registro oficial no Senado ${externalIcon}</a></p></div>${coverageCard(law, null)}</div></div>`;
      return;
    }
    main.innerHTML = `<div class="content-shell">${lawHeader(law, "text", trail)}<div class="law-layout"><div class="law-content"><p class="law-intro">${esc(law.description || "Texto e metadados da norma federal.")}</p>${initial.job?.status === "failed" ? `<div class="error-banner" role="alert">${esc(initial.job.message)} <button class="text-button" data-retry="${esc(slug)}">Tentar novamente</button></div>` : progressPanel(initial.job)}<p class="aside-empty">Enquanto preparamos o texto, você pode consultar o documento integral na fonte oficial.</p></div>${coverageCard(law, null)}</div></div>`;
    const retry = main.querySelector("[data-retry]");
    retry?.addEventListener("click", async () => { await getJSON(`${API}/laws/${encodeURIComponent(slug)}/hydrate`, { method: "POST" }); renderLaw(slug, targetArticle); });
    if (initial.job?.status !== "failed") pollLaw(slug, targetArticle);
    return;
  }
  try {
    const [nodeData, history] = await Promise.all([getJSON(`${API}/laws/${encodeURIComponent(slug)}/nodes`), getJSON(`${API}/laws/${encodeURIComponent(slug)}/history`)]);
    const recent = history.items?.[0];
    const auditNotice = law.materialization_status === "partial" ? `<div class="history-callout">Texto estruturado em conferência. Consulte o documento oficial enquanto verificamos anexos, segmentos e completude.</div>` : "";
    const article = targetArticle ? `<div class="law-intro">Abrindo o Art. ${esc(targetArticle)} · <a class="section-action" href="#article-${encodeURIComponent(targetArticle)}">Ir ao dispositivo ↓</a></div>` : `<p class="law-intro">${esc(law.description || "Texto consultado na fonte oficial.")} Esta versão foi estruturada a partir do documento público indicado abaixo.</p>`;
    main.innerHTML = `<div class="content-shell">${lawHeader(law, "text", trail)}${targetArticle ? copyLinkControl("Copiar link deste artigo") : ""}<div class="law-layout"><div class="law-content">${auditNotice}${article}${articleHtml(nodeData.items || [], slug)}</div>${coverageCard(law, recent)}</div></div>`;
    if (targetArticle) bindPageLinkCopy();
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
      if (data.version || data.job?.status === "failed") {
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
    const status = history.status || history.coverage || "not_requested";
    const items = history.items || [];
    const statusCopy = {
      not_requested: "O histórico ainda não foi reconstruído. Solicite a busca de relações oficiais para esta norma.",
      queued: "O job está persistido e aguarda o worker.",
      running: history.job?.message || "O worker está consultando as fontes oficiais.",
      partial: items.length ? `${history.events_pending_text || 0} referência(s) oficial(is) foram localizadas. As redações anteriores e as datas de vigência precisam de conferência antes de uma comparação completa.` : "A fonte oficial foi consultada e não listou relações para esta norma. Isso não comprova que nunca houve alteração.",
      unavailable: history.error || "A fonte oficial não disponibilizou relações para esta norma.",
      failed: history.error || "O último processamento falhou. Você pode tentar novamente."
    }[status] || "O intervalo comprovado ainda não contém eventos de alteração. Consulte a cobertura antes de concluir que não houve alterações.";
    main.innerHTML = `<div class="content-shell">${lawHeader(law, "history", trail)}<section class="history-layout">
      <p class="history-intro">Alterações ligadas a esta norma por referências identificadas em documentos oficiais. Cada registro abre o dispositivo e a fonte que sustenta o vínculo.</p>
      <div class="history-callout" role="status">${esc(statusCopy)}${history.checked_at ? `<br/>Fontes conferidas em ${datePt(history.checked_at)}.` : ""}</div>
      ${status === "running" || status === "queued" ? `<div class="law-progress"><span class="spinner" aria-hidden="true"></span><div><p class="progress-title">${status === "queued" ? "Histórico na fila" : "Buscando relações oficiais"}</p><p class="progress-copy">${esc(history.job?.message || statusCopy)}</p></div></div>` : ""}
      ${items.length ? `<div class="timeline">${items.map(item => `<div class="timeline-item"><div class="timeline-date">${datePt(item.changed_at)}</div><article class="timeline-card"><span class="timeline-source">${esc(item.source_law_label)}</span><h3>${esc(item.summary)}</h3><p>Dispositivo ${esc((item.node_id || "Norma relacionada").replaceAll(":", " · "))}${item.kind === "relation" ? " · redação anterior ainda não conferida" : ""}</p><a class="timeline-view" href="${item.comparison_available ? `/diff/${encodeURIComponent(item.id)}` : esc(item.source_url)}" ${item.comparison_available ? "" : 'target="_blank" rel="noopener"'}>${item.comparison_available ? `Ver antes e depois ${externalIcon}` : `Abrir referência oficial ${externalIcon}`}</a></article></div>`).join("")}</div>` : `<div class="empty-state"><h2>${status === "complete" ? "Nenhuma alteração no intervalo verificado" : status === "running" || status === "queued" ? "Nenhuma referência encontrada ainda" : "Histórico sem redações reconstruídas"}</h2><p>${status === "complete" ? "A fonte foi verificada no intervalo indicado." : "As referências encontradas e as pendências de texto aparecem nesta página. Sem reconstrução completa, ausência de resultado não significa ausência de alteração."}</p><a class="section-action" href="${esc(law.source_url)}" target="_blank" rel="noopener">Consultar a fonte oficial ${externalIcon}</a></div>`}
      ${status !== "running" && status !== "queued" ? `<button class="text-button" data-prepare-history="${esc(slug)}">${status === "not_requested" ? "Buscar histórico oficial" : "Tentar atualizar o histórico"}</button>` : ""}
    </section></div>`;
    const prepare = main.querySelector("[data-prepare-history]");
    prepare?.addEventListener("click", async () => {
      prepare.disabled = true;
      try {
        await getJSON(`${API}/laws/${encodeURIComponent(slug)}/history/prepare`, { method: "POST" });
        await renderHistory(slug);
        pollHistory(slug);
      } catch (error) {
        const banner = document.createElement("div"); banner.className = "error-banner"; banner.textContent = error.message;
        main.querySelector(".history-layout")?.prepend(banner); prepare.disabled = false;
      }
    });
    if (history.job && ["queued", "running"].includes(history.job.status)) pollHistory(slug, history.job.id);
  } catch (error) {
    main.innerHTML = `<div class="content-shell">${lawHeader(law, "history", trail)}<div class="error-banner">${esc(error.message)}</div></div>`;
  }
}

async function renderBlame(slug) {
  const selected = new URLSearchParams(location.search).get("node") || "";
  const pageSize = 250;
  const offset = Math.max(0, Number.parseInt(new URLSearchParams(location.search).get("offset") || "0", 10) || 0);
  try {
    const detail = await getJSON(`${API}/laws/${encodeURIComponent(slug)}`);
    const law = detail.law;
    const [blame, provenance] = await Promise.all([
      getJSON(`${API}/laws/${encodeURIComponent(slug)}/blame?limit=${pageSize}&offset=${offset}${selected ? `&node_id=${encodeURIComponent(selected)}` : ""}`),
      selected ? getJSON(`${API}/laws/${encodeURIComponent(slug)}/nodes/${encodeURIComponent(selected)}/provenance`) : Promise.resolve(null),
    ]);
    setMeta(`Blame jurídico — ${law.title} | LeiAberta`, `Atos modificadores verificados e lacunas de evidência para ${law.title}.`);
    const trail = [{ label: "Início", href: "/" }, { label: law.title, href: lawPath(law) }, { label: "Blame" }];
    const humanStatus = status => status === "verified" ? "Fonte confirmada" : status === "partial" ? "Evidência parcial" : status === "not_materialized" ? "Texto ainda não disponível" : "Ainda não identificado";
    const selectedBlock = provenance ? `<section class="why-panel"><div class="evidence-badge ${esc(provenance.evidence?.level || "partial")}">${esc(provenance.evidence?.label || humanStatus(provenance.status))}</div><h2>${esc(provenance.node?.label || selected)}</h2><p class="why-current">${esc(provenance.current_text || "O texto atual ainda não está materializado.")}</p><p class="why-note">${provenance.status === "verified" ? "O ato abaixo tem comparação de texto registrada em fonte oficial. Isso identifica o ato responsável pela alteração, não a autoria individual de cada linha." : provenance.status === "partial" ? "Relação oficial localizada; texto histórico ainda não reconstruído." : "Ainda não conseguimos rastrear a origem deste trecho com segurança."}</p>${provenance.last_verified_change ? `<div class="why-change"><p><strong>Última alteração verificada</strong> · ${datePt(provenance.last_verified_change.changed_at)}</p><p>${esc(provenance.last_verified_change.source_law_label)}</p><a class="section-action" href="/diff/${encodeURIComponent(provenance.last_verified_change.id)}">Ver antes e depois →</a><p><a href="${safeHttpHref(provenance.last_verified_change.source_url)}" target="_blank" rel="noopener">Abrir norma modificadora oficial ${externalIcon}</a></p></div>` : ""}${provenance.relations?.length ? `<div class="relation-note"><strong>Relações oficiais encontradas</strong>${provenance.relations.map(item => `<p>${esc(item.label)} · ${esc(item.notice)} <a href="${safeHttpHref(item.source_url)}" target="_blank" rel="noopener">Fonte ${externalIcon}</a></p>`).join("")}</div>` : ""}</section>` : `<p class="history-intro">Blame jurídico mostra qual ato está ligado à última alteração verificada do dispositivo. Não atribui a redação a uma pessoa. Escolha um dispositivo para consultar as evidências.</p>`;
    const rows = blame.items.map(item => `<a class="blame-row ${selected === item.node_id ? "selected" : ""}" href="${lawPath(law)}/blame?node=${encodeURIComponent(item.node_id)}"><span><strong>${esc(item.label)}</strong><small>${esc(item.node_id)}</small></span><span class="blame-origin">${item.responsible_act ? `<strong>${esc(item.responsible_act.label)}</strong><small>${datePt(item.responsible_act.changed_at)}</small>` : `<strong>Ainda não identificado</strong><small>Sem before/after verificado</small>`}</span><span class="evidence-badge ${item.evidence_level === "verified_primary" ? "verified_primary" : "partial"}">${item.responsible_act ? (item.evidence_level === "verified_primary" ? "Fonte confirmada" : "Evidência parcial") : "Não identificado"}</span></a>`).join("");
    const pagination = blame.count > pageSize ? `<nav class="blame-pagination" aria-label="Páginas de dispositivos"><span>Dispositivos ${Number(blame.offset + 1).toLocaleString("pt-BR")}–${Number(blame.offset + blame.items.length).toLocaleString("pt-BR")} de ${Number(blame.count).toLocaleString("pt-BR")}</span><div>${offset > 0 ? `<a href="${lawPath(law)}/blame?offset=${Math.max(0, offset-pageSize)}">Anterior</a>` : ""}${blame.has_more ? `<a href="${lawPath(law)}/blame?offset=${offset+pageSize}">Próximos dispositivos →</a>` : ""}</div></nav>` : "";
    main.innerHTML = `<div class="content-shell">${lawHeader(law, "blame", trail)}<section class="history-layout"><div class="blame-heading"><div><h2>Quem responde pelo texto?</h2><p>O ato modificador é mostrado quando há comparação verificável. Origem de autoria permanece sem atribuição individual.</p></div><span>${Number(blame.count).toLocaleString("pt-BR")} dispositivos</span></div>${selectedBlock}${selected ? copyLinkControl("Copiar link desta evidência") : ""}<div class="blame-list">${rows || `<div class="empty-state">${blame.status === "not_materialized" ? "O texto desta norma ainda está sendo preparado." : "Nenhum dispositivo estruturado foi localizado."}</div>`}</div>${pagination}<p class="source-note">O LeiAberta só trata uma alteração como confirmada quando existe evidência oficial suficiente para sustentar a relação apresentada.</p></section></div>`;
    if (selected) bindPageLinkCopy();
  } catch (error) { renderNotFound(error.message); }
}

async function renderSources() {
  setMeta("Fontes e atualizações | LeiAberta", "Veja quais catálogos oficiais estão integrados e quando foram consultados.");
  main.innerHTML = `<div class="content-shell editorial-page"><div class="eyebrow"><span class="eyebrow-line"></span> Transparência</div><h1 class="diff-title">Fontes oficiais, estado por estado.</h1><p class="history-intro">O LeiAberta consulta periodicamente as fontes já integradas. Novas normas dessas fontes entram no catálogo sem necessidade de novo deploy. A cobertura varia por jurisdição e pela disponibilidade dos portais oficiais.</p><div id="source-list" class="source-list"><div class="page-loading"><span class="spinner"></span> Consultando estado das fontes</div></div></div>`;
  try {
    const data = await getJSON(`${API}/sources`);
    document.querySelector("#source-list").innerHTML = `<p class="catalog-footer">${data.count} registros de fonte · consultado ${datePt(data.checked_at)}</p>${data.items.length ? data.items.map(source => `<article class="source-card"><div><span class="source-adapter">${esc(source.adapter)} · ${esc(source.freshness_status)}</span><h2>${esc(source.name)}</h2><p>${esc(source.jurisdiction_name)} · status ${esc(source.status)}</p></div><dl><div><dt>Freshness</dt><dd>${source.freshness_seconds ? `${Math.round(source.freshness_seconds / 86400)} dias` : "Sem política publicada"}</dd></div><div><dt>Limites do adapter</dt><dd>${esc(sourcePolicyLabel(source.request_policy))}</dd></div><div><dt>Última tentativa</dt><dd>${datePt(source.last_checked_at)}</dd></div><div><dt>Último sucesso registrado</dt><dd>${datePt(source.last_success_at)}</dd></div><div><dt>Catálogo · texto</dt><dd>${source.cataloged_laws == null ? "Não informado" : `${Number(source.cataloged_laws).toLocaleString("pt-BR")} · ${Number(source.with_text).toLocaleString("pt-BR")}`}</dd></div><div><dt>Novos · atualizados · falhas de sync</dt><dd>${source.new_records == null ? "Sem contagem registrada" : `${source.new_records} · ${source.updated_records} · ${source.failed_records ?? "n/d"} · ${source.sync_failures ?? 0}`}</dd></div></dl>${source.last_error ? `<p class="source-error">Aviso recente: ${esc(source.last_error.slice(0, 240))}</p>` : ""}<a href="${safeHttpHref(source.evidence_url || source.base_url)}" target="_blank" rel="noopener">Fonte oficial ${externalIcon}</a></article>`).join("") : `<div class="empty-state">Ainda não há registries de fontes carregados neste ambiente.</div>`}`;
  } catch (error) { document.querySelector("#source-list").innerHTML = `<div class="error-banner">${esc(error.message)}</div>`; }
}

function sourcePolicyLabel(policy) {
  if (!policy) return "Não há adapter de catálogo ativo";
  const parts = [];
  if (policy.page_size) parts.push(`${Number(policy.page_size).toLocaleString("pt-BR")} por página`);
  if (policy.max_response_bytes) parts.push(`${Math.round(policy.max_response_bytes / 1_000_000)} MB máx.`);
  if (policy.timeout_seconds) parts.push(`${policy.timeout_seconds} s timeout`);
  if (policy.max_attempts) parts.push(`${policy.max_attempts} tentativas máx.`);
  return parts.join(" · ") || "Política específica do adapter";
}

async function renderCoverage() {
  setMeta("Cobertura legislativa | LeiAberta", "Cobertura e lacunas por jurisdição nas fontes integradas ao LeiAberta.");
  main.innerHTML = `<div class="content-shell editorial-page"><div class="eyebrow"><span class="eyebrow-line"></span> Escopo e lacunas</div><h1 class="diff-title">Cobertura que mostra as lacunas.</h1><p class="history-intro">Catálogo, texto, histórico e tramitação são estágios diferentes. Uma fonte configurada não significa que toda a sua legislação esteja coberta.</p><div id="coverage-content"><div class="page-loading"><span class="spinner"></span> Calculando métricas públicas</div></div></div>`;
  try {
    const [stats, sources] = await Promise.all([getJSON(`${API}/stats`), getJSON(`${API}/sources`)]);
    const categoryName = id => !id || id.startsWith("federal:") ? "Federal" : id.startsWith("state:DF") ? "Distrito Federal" : id.startsWith("state:") ? "Estados" : id.startsWith("municipality:") ? "Municípios" : "Diretórios e descoberta";
    const groups = new Map();
    for (const source of sources.items) { const key = categoryName(source.jurisdiction_id); groups.set(key, [...(groups.get(key) || []), source]); }
    const categories = ["Federal", "Estados", "Distrito Federal", "Municípios", "Diretórios e descoberta"];
    document.querySelector("#coverage-content").innerHTML = `<div class="coverage-metrics"><div><strong>${Number(stats.indexed_laws).toLocaleString("pt-BR")}</strong><span>registros catalogados</span></div><div><strong>${Number(stats.materialized_laws).toLocaleString("pt-BR")}</strong><span>normas com texto</span></div><div><strong>${Number(stats.enumerated_sources).toLocaleString("pt-BR")}</strong><span>fontes enumeradas</span></div></div><p class="source-note">Registros catalogados são metadados enumerados em fontes oficiais integradas. Isso não equivale à totalidade da legislação brasileira. A configuração de uma fonte não representa cobertura integral da jurisdição.</p><div class="coverage-grid">${categories.map(category => { const rows=groups.get(category)||[]; const integrated=rows.filter(s=>s.status==="enumerated").length; return `<section class="coverage-jurisdiction"><h2>${category}</h2><p><strong>${integrated} fontes enumeradas de ${rows.length} registradas</strong><span>Normas com texto e histórico variam por fonte. Consulte a lista detalhada e os estados observados em <a href="/fontes">Fontes</a>.</span></p>${rows.filter(s=>s.status!=="enumerated").slice(0,3).map(s=>`<p><strong>${esc(s.name)}</strong><span>${esc(s.status)} · freshness ${esc(s.freshness_status)}</span></p>`).join("")}</section>`; }).join("")}</div><div class="contribute-callout"><h2>Sua cidade ainda não aparece?</h2><p>Ajude a conectar a fonte oficial e a documentar suas lacunas.</p><a class="section-action" href="https://github.com/DIDIDXX/LeiAberta/blob/main/CONTRIBUTING.md" target="_blank" rel="noopener">Como contribuir ${externalIcon}</a></div>`;
  } catch (error) { document.querySelector("#coverage-content").innerHTML = `<div class="error-banner">${esc(error.message)}</div>`; }
}

function renderAbout() {
  setMeta("Sobre o LeiAberta", "Como o LeiAberta conecta fontes públicas oficiais, textos e alterações verificáveis.");
  main.innerHTML = `<div class="content-shell editorial-page"><div class="eyebrow"><span class="eyebrow-line"></span> Sobre o projeto</div><h1 class="diff-title">A fonte vem primeiro.</h1><div class="about-columns"><section><h2>O problema</h2><p>O Brasil não tem uma API única com todas as normas, versões, alterações e processos.</p><h2>O que fazemos</h2><p>Conectamos fontes oficiais, mantemos catálogos, estruturamos textos e ligamos alterações verificáveis às suas evidências.</p><div class="pipeline">Fontes oficiais → catálogo → texto → estrutura → histórico → evidência</div></section><section><h2>O que não fazemos</h2><ul><li>Não substituímos a publicação oficial.</li><li>Não inventamos autoria nem completude.</li><li>Uma relação legislativa não vira diff sem texto comparável.</li><li>Data de captura não é data de vigência.</li></ul><h2>Como atualiza</h2><p>O worker consulta fontes integradas conforme a política de freshness de cada adapter. Uma norma pode entrar no catálogo antes de o texto ou histórico estarem disponíveis.</p></section></div><div class="contribute-callout"><h2>Open source · MIT</h2><p>Ajude a mapear a legislação brasileira, com fixtures e evidência oficial.</p><a class="section-action" href="https://github.com/DIDIDXX/LeiAberta" target="_blank" rel="noopener">Abrir repositório ${externalIcon}</a></div></div>`;
}

async function pollHistory(slug, jobId) {
  for (let i = 0; i < 60; i++) {
    await new Promise(resolve => setTimeout(resolve, 5000));
    const job = await getJSON(`${API}/jobs/${encodeURIComponent(jobId)}`).catch(() => null);
    if (job && !["queued", "running"].includes(job.status)) { renderHistory(slug); return; }
  }
  if (location.pathname.endsWith("/historico")) renderHistory(slug);
}

async function renderProceedings(slug) {
  let detail;
  try { detail = await getJSON(`${API}/laws/${encodeURIComponent(slug)}`); }
  catch (error) { renderNotFound(error.message); return; }
  const law = detail.law;
  setMeta(`Tramitação: ${law.title} | LeiAberta`, `Processos, emendas e votações oficiais ligados a ${law.title}.`);
  const trail = [{ label: "Início", href: "/" }, { label: law.title, href: lawPath(law) }, { label: "Tramitação" }];
  try {
    const dossier = await getJSON(`${API}/laws/${encodeURIComponent(slug)}/proceedings`);
    const active = ["queued", "running"].includes(dossier.status);
    const statusCopy = {
      not_requested: "A tramitação ainda não foi consultada. Buscaremos processos que o Senado relaciona exatamente a esta norma.",
      queued: "A consulta oficial está registrada e aguarda o worker.",
      running: dossier.job?.message || "Consultando processos, emendas e votações no Senado.",
      complete: `${dossier.matching_processes_found || dossier.processes.length} processo(s) compatível(is) localizado(s) em dados abertos do Senado.`,
      partial: "A consulta encontrou uma lacuna ou excedeu um limite seguro em referências, tramitações ou votações; parte do dossiê pode estar incompleta.",
      no_process: "A consulta exata ao Senado não listou processo gerador para esta norma. Isso não consulta a Câmara nem prova que a norma não teve tramitação.",
      failed: dossier.error || "A última consulta falhou. Você pode tentar novamente."
    }[dossier.status] || "O estado da consulta não está verificado.";
    const visibleStatusCopy = dossier.error && !active && dossier.status !== "failed"
      ? statusCopy + " A atualização falhou; os dados salvos anteriormente continuam disponíveis. " + dossier.error
      : statusCopy;
    const authorLine = process => {
      const authors = process.documento?.autoria || [];
      const names = authors.map(item => [item.cargo, item.autor, item.siglaPartido && `(${item.siglaPartido}${item.uf ? `/${item.uf}` : ""})`].filter(Boolean).join(" "));
      return names.length ? names.join("; ") : process.documento?.resumoAutoria || "Autoria não informada no registro consultado";
    };
    const voteLabel = value => ({ S: "Sim", N: "Não", A: "Abstenção", P: "Presente" }[String(value || "").toUpperCase()] || String(value || "Voto sem classificação"));
    const processCards = dossier.processes.map(item => {
      const process = item.process || {};
      const doc = process.documento || {};
      const amendmentCards = (item.amendments || []).map(amendment => "<li><strong>" + esc(amendment.identificacao || amendment.descricaoDocumentoEmenda || "Emenda") + "</strong>" + (amendment.autoria ? "<span>" + esc(amendment.autoria) + "</span>" : "") + (amendment.dataApresentacao ? "<span>Apresentada em " + datePt(amendment.dataApresentacao) + "</span>" : "") + (amendment.urlDocumentoEmenda ? "<a href='" + safeHttpHref(amendment.urlDocumentoEmenda) + "' target='_blank' rel='noopener'>Documento da emenda " + externalIcon + "</a>" : "") + "</li>").join("");
      const voteCards = (item.committee_votes || []).map(session => {
        const rollCall = (session.votes || []).map(vote => "<li>" + esc(vote.NomeParlamentar || "Parlamentar") + ": " + esc(voteLabel(vote.QualidadeVoto)) + (vote.SiglaPartidoParlamentar ? " (" + esc(vote.SiglaPartidoParlamentar) + ")" : "") + "</li>").join("");
        return "<li><strong>" + esc(session.committee || "Votação em comissão") + "</strong><span>" + esc(session.date ? datePt(session.date) : "Data não informada") + (session.description ? " · " + esc(session.description) : "") + "</span>" + (rollCall ? "<ul class='proceeding-rollcall'>" + rollCall + "</ul>" : "<span>A fonte não publicou voto nominal nesta sessão.</span>") + "</li>";
      }).join("");
      const sourceUrls = (item.source_urls || []).filter(Boolean);
      const sourceLinks = sourceUrls.map((url, index) => "<a href='" + safeHttpHref(url) + "' target='_blank' rel='noopener'>Fonte oficial do Senado " + (index + 1) + " " + externalIcon + "</a>").join("");
      const plenary = item.plenary_votes?.length ? "<h3>Votações em plenário</h3><pre class='proceeding-raw'>" + esc(JSON.stringify(item.plenary_votes, null, 2)) + "</pre>" : "<p>A API de votação em plenário não retornou registros para este processo.</p>";
      const senateMovements = (process.autuacoes || []).flatMap(row => row.situacoes || []).map(event => "<li><strong>" + esc(event.descricao || "Situação legislativa") + "</strong><span>" + esc(event.inicio ? datePt(event.inicio) : "Data não informada") + (event.colegiado?.nome ? " · " + esc(event.colegiado.nome) : "") + "</span></li>").join("");
      const chamberCards = (item.chamber_processes || []).map(chamber => {
        if (chamber.status !== "complete" && chamber.status !== "partial") return "<p>Referência cruzada oficial da Câmara: " + esc(chamber.status) + " para " + esc(chamber.reference?.sigla + " " + chamber.reference?.numero + "/" + chamber.reference?.ano) + ".</p>";
        const proposal = chamber.proposal || {};
        const chamberAuthors = (chamber.authors || []).map(author => "<li>" + esc(author.nome || author.tipo || "Autor") + "</li>").join("");
        const chamberMovements = (chamber.proceedings || []).map(movement => "<li><strong>" + esc(movement.descricaoTramitacao || "Tramitação") + "</strong><span>" + esc(movement.dataHora ? datePt(movement.dataHora) : "Data não informada") + (movement.siglaOrgao ? " · " + esc(movement.siglaOrgao) : "") + (movement.despacho ? " — " + esc(movement.despacho) : "") + "</span>" + (movement.url ? "<a href='" + safeHttpHref(movement.url) + "' target='_blank' rel='noopener'>Documento deste andamento " + externalIcon + "</a>" : "") + "</li>").join("");
        const related = (chamber.related_proposals || []).map(row => "<li><a href='" + safeHttpHref(row.uri) + "' target='_blank' rel='noopener'><strong>" + esc(row.siglaTipo + " " + row.numero + "/" + row.ano) + "</strong> " + externalIcon + "</a><span>" + esc(row.ementa || "Ementa não informada") + "</span></li>").join("");
        const chamberVotes = (chamber.votes || []).map(row => {
          const vote = row.vote || {};
          const ballots = (row.nominal_votes || []).map(ballot => {
            const deputy = ballot.deputado_ || {};
            return "<li>" + esc(deputy.nome || "Parlamentar") + ": " + esc(ballot.tipoVoto || "Voto não informado") + (deputy.siglaPartido ? " (" + esc(deputy.siglaPartido) + (deputy.siglaUf ? "/" + esc(deputy.siglaUf) : "") + ")" : "") + "</li>";
          }).join("");
          return "<details><summary>" + esc(vote.data ? datePt(vote.data) : "Data não informada") + " · " + esc(vote.descricao || "Votação") + " · " + (row.nominal_votes || []).length + " voto(s) nominal(is)</summary>" + (ballots ? "<ul class='proceeding-rollcall'>" + ballots + "</ul>" : "<p>Esta votação não publicou votos nominais.</p>") + (row.source_url ? "<a href='" + safeHttpHref(row.source_url) + "' target='_blank' rel='noopener'>Votos oficiais " + externalIcon + "</a>" : "") + "</details>";
        }).join("");
        const chamberSource = proposal.uri ? "<a href='" + safeHttpHref(proposal.uri) + "' target='_blank' rel='noopener'>Registro da proposição na Câmara " + externalIcon + "</a>" : "";
        const rapporteur = chamber.last_rapporteur;
        const rapporteurName = rapporteur?.name || "Parlamentar";
        const rapporteurLabel = rapporteur ? rapporteurName + (rapporteur.party ? " (" + rapporteur.party + (rapporteur.state ? "/" + rapporteur.state : "") + ")" : "") : "Relator mais recente não informado na API";
        const rapporteurLine = rapporteur ? (rapporteur.uri ? "<a href='" + safeHttpHref(rapporteur.uri) + "' target='_blank' rel='noopener'>" + esc(rapporteurLabel) + " " + externalIcon + "</a>" : esc(rapporteurLabel)) : rapporteurLabel;
        return "<section class='chamber-dossier'><h3>Câmara dos Deputados · " + esc(proposal.siglaTipo + " " + proposal.numero + "/" + proposal.ano) + "</h3><p>Vínculo confirmado pela referência cruzada do processo do Senado. Situação: " + esc(proposal.statusProposicao?.descricaoSituacao || "não informada") + ".</p><dl class='proceeding-facts'><div><dt>Autoria</dt><dd>" + (chamberAuthors ? "<ul class='proceeding-list'>" + chamberAuthors + "</ul>" : "Não informada") + "</dd></div><div><dt>Relator mais recente</dt><dd>" + rapporteurLine + "</dd></div><div><dt>Ementa</dt><dd>" + esc(proposal.ementa || "Não informada") + "</dd></div></dl>" + chamberSource + (chamberVotes ? "<details class='proceeding-section' open><summary>Votações da Câmara (" + chamber.votes.length + ")</summary>" + chamberVotes + "</details>" : "<p>A API não listou votações para esta proposição.</p>") + (chamberMovements ? "<details class='proceeding-section'><summary>Tramitações da Câmara (" + chamber.proceedings.length + ")</summary><ul class='proceeding-list'>" + chamberMovements + "</ul></details>" : "") + (related ? "<details class='proceeding-section'><summary>Proposições relacionadas (" + chamber.related_proposals.length + ")</summary><ul class='proceeding-list'>" + related + "</ul></details>" : "") + "</section>";
      }).join("");
      const senateTimeline = senateMovements ? "<details class='proceeding-section'><summary>Situações registradas no Senado (" + process.autuacoes.flatMap(row => row.situacoes || []).length + ")</summary><ul class='proceeding-list'>" + senateMovements + "</ul></details>" : "";
      return "<article class='timeline-card proceeding-card'><span class='timeline-source'>" + esc(process.sigla || "Processo legislativo") + " · " + esc(process.casaIdentificadora || "Senado Federal") + "</span><h2>" + esc(process.identificacao || "Processo sem identificação") + "</h2><p>" + esc(process.situacaoAtual || "Situação não informada") + (process.dataSituacaoAtual ? " · atualizada em " + datePt(process.dataSituacaoAtual) : "") + "</p><dl class='proceeding-facts'><div><dt>Autoria</dt><dd>" + esc(authorLine(process)) + "</dd></div><div><dt>Apresentação</dt><dd>" + esc(doc.dataApresentacao ? datePt(doc.dataApresentacao) : "Data não informada") + "</dd></div><div><dt>Ementa</dt><dd>" + esc(process.conteudo?.ementa || "Não informada") + "</dd></div></dl>" + (amendmentCards ? "<h3>Emendas do Senado (" + item.amendments.length + ")</h3><ul class='proceeding-list'>" + amendmentCards + "</ul>" : "<p>Esta consulta não listou emendas para o processo do Senado.</p>") + (voteCards ? "<h3>Votações nominais do Senado em comissão</h3><ul class='proceeding-list'>" + voteCards + "</ul>" : "<p>Esta consulta não retornou votação nominal de comissão do Senado.</p>") + plenary + senateTimeline + chamberCards + "<details class='proceeding-section'><summary>Respostas oficiais consultadas no Senado (" + sourceUrls.length + ")</summary><div class='proceeding-sources'>" + sourceLinks + "</div></details></article>";
    }).join("");
    const noProcess = dossier.status === "no_process" ? "<div class='empty-state'><h2>Nenhum processo listado pelo Senado</h2><p>A consulta foi feita por tipo, número e ano da norma. A Câmara e registros externos não fazem parte deste resultado.</p><a class='section-action' href='" + safeHttpHref(law.source_url) + "' target='_blank' rel='noopener'>Consultar a fonte da norma " + externalIcon + "</a></div>" : "";
    main.innerHTML = "<div class='content-shell'>" + lawHeader(law, "proceedings", trail) + "<section class='history-layout'><p class='history-intro'>Dados oficiais de tramitação consultados no Senado: proposição geradora, autoria, emendas, documentos e votos nominais publicados. Cada bloco mantém seus links de origem.</p><div class='history-callout' role='status'>" + esc(visibleStatusCopy) + (dossier.checked_at ? "<br/>Consultado em " + datePt(dossier.checked_at) + "." : "") + "</div>" + (active ? "<div class='law-progress'><span class='spinner' aria-hidden='true'></span><div><p class='progress-title'>" + (dossier.status === "queued" ? "Consulta na fila" : "Consultando o Senado") + "</p><p class='progress-copy'>" + esc(dossier.job?.message || statusCopy) + "</p></div></div>" : "") + processCards + noProcess + "<button class='text-button' data-prepare-proceedings='" + esc(slug) + "' " + (active ? "disabled" : "") + ">" + (dossier.status === "not_requested" ? "Buscar tramitação oficial" : "Atualizar tramitação") + "</button></section></div>";
    main.querySelector("[data-prepare-proceedings]")?.addEventListener("click", async event => {
      const button = event.currentTarget; button.disabled = true;
      try {
        await getJSON(`${API}/laws/${encodeURIComponent(slug)}/proceedings/prepare?refresh=${dossier.status !== "not_requested"}`, { method: "POST" });
        await renderProceedings(slug);
      } catch (error) {
        const banner = document.createElement("div"); banner.className = "error-banner"; banner.textContent = error.message;
        main.querySelector(".history-layout")?.prepend(banner); button.disabled = false;
      }
    });
    if (active && dossier.job?.id) pollProceedings(slug, dossier.job.id);
  } catch (error) {
    main.innerHTML = "<div class='content-shell'>" + lawHeader(law, "proceedings", trail) + "<div class='error-banner'>" + esc(error.message) + "</div></div>";
  }
}

async function pollProceedings(slug, jobId) {
  for (let i = 0; i < 60; i++) {
    await new Promise(resolve => setTimeout(resolve, 5000));
    const job = await getJSON(`${API}/jobs/${encodeURIComponent(jobId)}`).catch(() => null);
    if (job && !["queued", "running"].includes(job.status)) { renderProceedings(slug); return; }
  }
  if (location.pathname.endsWith("/tramitacao")) renderProceedings(slug);
}

async function renderDiff(changeId) {
  let change;
  try { change = await getJSON(`${API}/changes/${encodeURIComponent(changeId)}`); }
  catch (error) { renderNotFound(error.message); return; }
  const law = change.law;
  setMeta(`${change.summary} — ${law.title} | LeiAberta`, `Texto anterior e posterior de uma alteração documentada em ${change.source_law_label}.`);
  const nodeName = change.node_id.replaceAll(":", " · ");
  const before = change.before_text || "Este dispositivo ainda não existia no texto anterior consultado.";
  const evidence = change.evidence || { label: "Evidência parcial", level: "partial" };
  const isNormasVersion = evidence.source_host === "normas.leg.br";
  const comparisonLinkLabel = evidence.level === "verified_primary"
    ? "Fonte oficial da norma modificadora"
    : isNormasVersion ? "Versão da comparação no Normas.leg.br" : "Referência da alteração";
  const evidenceNote = isNormasVersion
    ? "A comparação está registrada na versão citada do Normas.leg.br, que classifica essa transcrição como valor jurídico não oficial. A data do registro não confirma vigência."
    : "A comparação disponível sustenta a alteração; não identifica a pessoa que redigiu cada linha.";
  const whyText = change.change_type === "ADD"
    ? `O dispositivo aparece marcado como incluído pela ${esc(change.source_law_label)}.`
    : `A comparação associa a atualização do dispositivo à ${esc(change.source_law_label)}.`;
  const articleNumber = change.node_id.startsWith("art:") ? change.node_id.slice(4) : "";
  main.innerHTML = `<div class="content-shell">${crumbs([{ label: "Início", href: "/" }, { label: law.title, href: lawPath(law) }, { label: "Histórico", href: `${lawPath(law)}/historico` }, { label: "Alteração" }])}
    <section class="diff-layout"><div class="law-eyebrow"><span class="eyebrow-line"></span> Alteração documentada</div><div class="evidence-badge ${esc(evidence.level)}">${esc(evidence.label)}</div><h1 class="diff-title">${esc(change.summary)}</h1><p class="diff-subtitle">${esc(law.title)} · ${esc(nodeName)}</p>
    ${copyLinkControl("Copiar link desta alteração")}${articleNumber ? `<p class="diff-article-link"><a class="section-action" href="${lawPath(law)}/artigo/${encodeURIComponent(articleNumber)}">Ler o artigo atual →</a></p>` : ""}
    <div class="diff-meta"><span>Data registrada: ${datePt(change.changed_at)}</span><span>Origem: <a href="${esc(change.source_url)}" target="_blank" rel="noopener">${esc(change.source_law_label)} ${externalIcon}</a></span><span>Tipo: ${esc(change.change_type === "ADD" ? "Dispositivo incluído" : change.change_type === "UPDATE" ? "Redação alterada" : change.change_type)}</span></div>
    <div class="diff-panes"><section class="diff-pane before"><div class="diff-pane-head"><span>Antes</span><span>Texto anterior</span></div><p class="diff-text ${change.before_text ? "" : "diff-empty"}">${esc(before)}</p></section>
      <section class="diff-pane after"><div class="diff-pane-head"><span>Depois</span><span>${esc(nodeName)}</span></div><p class="diff-text">${esc(change.after_text)}</p></section></div>
    <div class="diff-source-note"><strong>Por que este trecho está assim?</strong> ${whyText} ${evidenceNote} <a class="source-link" href="${safeHttpHref(change.source_url)}" target="_blank" rel="noopener">${comparisonLinkLabel} ${externalIcon}</a> · <a class="source-link" href="${safeHttpHref(change.law_source_url)}" target="_blank" rel="noopener">Texto da norma consultada ${externalIcon}</a> · <a class="source-link" href="${lawPath(law)}/blame?node=${encodeURIComponent(change.node_id)}">Ver evidências deste dispositivo →</a></div>
    </section></div>`;
  bindPageLinkCopy();
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
      const heading = result.parsed.article
        ? result.results.length > 1
          ? `Art. ${esc(result.parsed.article)} aparece em ${result.results.length} normas`
          : `Art. ${esc(result.parsed.article)} encontrado`
        : `${result.results.length} resultado${result.results.length === 1 ? "" : "s"}`;
      el.innerHTML = `<div class="section-kicker">${heading}${result.suggestion ? ` · sugestão aproximada para “${esc(query)}”` : ""}</div><div class="catalog-list" style="margin-top:12px">${result.results.map(catalogRow).join("")}</div>${result.parsed.article ? `<p class="catalog-footer">A busca também identificou o Art. ${esc(result.parsed.article)}.</p>` : ""}`;
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
  if (path === "/fontes") return renderSources();
  if (path === "/cobertura") return renderCoverage();
  if (path === "/sobre") return renderAbout();
  const law = path.match(/^\/lei\/([^/]+)(?:\/(historico|tramitacao|blame|artigo\/([^/]+)))?/);
  if (law) {
    if (law[2] === "historico") return renderHistory(law[1]);
    if (law[2] === "tramitacao") return renderProceedings(law[1]);
    if (law[2] === "blame") return renderBlame(law[1]);
    if (law[3]) return renderLaw(law[1], law[3]);
    return renderLaw(law[1]);
  }
  if (path === "/buscar") return renderSearchPage(new URLSearchParams(location.search).get("q") || "");
  if (path === "/" || path === "") return renderHome();
  renderNotFound();
}

route();
