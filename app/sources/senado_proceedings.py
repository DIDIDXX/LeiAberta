"""Official Senate process, amendment and roll-call data for enacted norms."""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass

from app.sources.network import open_with_retry
from app.sources.senado import BASE_URL, TYPE_CODES

CHAMBER_BASE_URL = "https://dadosabertos.camara.leg.br/api/v2"
MAX_RESPONSE_BYTES = 20_000_000
MAX_DOSSIER_BYTES = 50_000_000
MAX_MATCHING_PROCESSES = 25
MAX_CHAMBER_CROSS_REFERENCES = 5
MAX_NOMINAL_VOTE_SESSIONS = 30


@dataclass(frozen=True)
class OfficialJsonDocument:
    url: str
    body: bytes
    data: object


def _fetch_json(url: str, *, timeout: int = 25) -> OfficialJsonDocument:
    request = urllib.request.Request(url, headers={
        "User-Agent": "LeiAberta/0.2 (+fontes oficiais)",
        "Accept": "application/json",
    })
    with open_with_retry(request, timeout=timeout) as response:
        body = response.read()
        if response.status != 200 or len(body) > MAX_RESPONSE_BYTES:
            raise ValueError("Resposta JSON inválida ou acima do limite da API oficial do Senado.")
        try:
            data = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("A API oficial do Senado retornou JSON inválido.") from exc
        return OfficialJsonDocument(response.geturl(), body, data)


def _rows(value: object, *keys: str) -> list[dict]:
    if isinstance(value, list):
        return [row for row in value if isinstance(row, dict)]
    if isinstance(value, dict):
        for key in keys:
            if key in value:
                return _rows(value[key], *keys)
        if value:
            return [value]
    return []


def _digits(value: object) -> str:
    return "".join(re.findall(r"\d", str(value or "")))


def _normalized_number(value: object) -> str:
    return re.sub(r"[^\d-]", "", str(value or "")).lstrip("0") or "0"


def _process_norm_matches(process: dict, law_type: str, number: str, year: int) -> bool:
    generated = process.get("normaGerada")
    expected_number = _normalized_number(number)
    expected_type = TYPE_CODES[law_type]
    if isinstance(generated, dict):
        generated_type = str(generated.get("siglaTipo") or "")
        generated_number = _normalized_number(generated.get("numero"))
        generated_year = _digits(generated.get("anoAssinatura"))
        return generated_type == expected_type and generated_number == expected_number and generated_year == str(year)
    if isinstance(generated, str):
        match = re.search(r"\bn[º°o.]?\s*([\d.]+(?:-\d+)?)\s+de\s+(\d{2}/\d{2}/\d{4})", generated, re.I)
        if not match:
            return False
        generated_number = _normalized_number(match.group(1))
        generated_year = match.group(2).rsplit("/", 1)[-1]
        type_name = generated[:match.start()].strip().casefold()
        expected_prefix = {
            "Lei": "lei",
            "Lei Complementar": "lei complementar",
            "Emenda Constitucional": "emenda constitucional",
            "Decreto Legislativo": "decreto legislativo",
            "Resolução do Senado Federal": "resolução",
            "Resolução do Congresso Nacional": "resolução",
        }.get(law_type, law_type.casefold())
        return (generated_number == expected_number and generated_year == str(year)
                and type_name.startswith(expected_prefix))
    return False


def _commission_votes(data: object) -> list[dict]:
    if not isinstance(data, dict):
        return []
    wrapper = data.get("VotacoesComissao", data)
    if not isinstance(wrapper, dict):
        return []
    sessions = wrapper.get("Votacoes", {})
    if isinstance(sessions, dict):
        sessions = sessions.get("Votacao", [])
    rows = _rows(sessions)
    normalized = []
    for item in rows:
        votes = item.get("Votos", {})
        if isinstance(votes, dict):
            votes = votes.get("Voto", [])
        normalized.append({
            "committee": item.get("NomeColegiado") or item.get("SiglaColegiado") or "",
            "committee_code": item.get("SiglaColegiado") or "",
            "date": item.get("DataHoraInicioReuniao") or "",
            "description": item.get("DescricaoVotacao") or "",
            "matter": item.get("IdentificacaoMateria") or "",
            "votes": _rows(votes),
        })
    return normalized


def _chamber_cross_references(detail: dict) -> list[dict]:
    references = []
    seen = set()
    for item in detail.get("outrosNumeros") or []:
        if not isinstance(item, dict):
            continue
        house = str(item.get("casaIdentificadora") or item.get("siglaEnteIdentificador") or "").upper()
        sigla = str(item.get("sigla") or "").upper()
        number = str(item.get("numero") or "")
        year = _digits(item.get("ano"))
        if house != "CD" or not re.fullmatch(r"[A-Z0-9]{1,12}", sigla):
            continue
        if not re.fullmatch(r"[\d.]+(?:-\d+)?", number) or not re.fullmatch(r"\d{4}", year):
            continue
        key = (sigla, _normalized_number(number), year)
        if key not in seen:
            references.append({"sigla": sigla, "numero": number, "ano": year,
                               "senate_reference_id": str(item.get("idOutroProcesso") or "")})
            seen.add(key)
    return references


def _fetch_chamber_process(reference: dict, capture) -> dict:
    query = urllib.parse.urlencode({"siglaTipo": reference["sigla"],
                                    "numero": _digits(reference["numero"].split("-", 1)[0]),
                                    "ano": reference["ano"], "pagina": 1, "itens": 100})
    search_doc = capture(_fetch_json(f"{CHAMBER_BASE_URL}/proposicoes?{query}"))
    search_data = search_doc.data
    rows = _rows(search_data, "dados", "proposicoes", "items") if isinstance(search_data, dict) else []
    matches = [row for row in rows if str(row.get("siglaTipo") or "").upper() == reference["sigla"]
               and _normalized_number(row.get("numero")) == _normalized_number(reference["numero"])
               and _digits(row.get("ano")) == reference["ano"]]
    if not matches:
        return {"status": "not_found", "reference": reference, "source_urls": [search_doc.url]}
    if len(matches) != 1:
        return {"status": "ambiguous", "reference": reference, "candidates": matches,
                "source_urls": [search_doc.url]}
    chamber_id = str(matches[0].get("id") or "")
    if not chamber_id.isdigit():
        raise ValueError("A Câmara retornou proposição sem identificador numérico verificável.")

    paths = [f"/proposicoes/{chamber_id}", f"/proposicoes/{chamber_id}/autores",
             f"/proposicoes/{chamber_id}/tramitacoes", f"/proposicoes/{chamber_id}/relacionadas",
             f"/proposicoes/{chamber_id}/votacoes"]
    captured = [capture(_fetch_json(CHAMBER_BASE_URL + path)) for path in paths]
    detail_data = captured[0].data
    detail = detail_data.get("dados") if isinstance(detail_data, dict) else None
    if not isinstance(detail, dict) or str(detail.get("id") or "") != chamber_id:
        raise ValueError("O detalhe da Câmara não corresponde à referência cruzada consultada.")
    last_rapporteur = None
    rapporteur_uri = ((detail.get("statusProposicao") or {}).get("uriUltimoRelator")
                      if isinstance(detail.get("statusProposicao"), dict) else None)
    rapporteur_match = re.fullmatch(
        r"https://dadosabertos\.camara\.leg\.br/api/v2/deputados/(\d+)", str(rapporteur_uri or ""),
    )
    if rapporteur_match:
        rapporteur_doc = capture(_fetch_json(f"{CHAMBER_BASE_URL}/deputados/{rapporteur_match.group(1)}"))
        captured.append(rapporteur_doc)
        rapporteur_payload = rapporteur_doc.data
        rapporteur_record = rapporteur_payload.get("dados") if isinstance(rapporteur_payload, dict) else None
        if not isinstance(rapporteur_record, dict):
            raise ValueError("A Câmara retornou um vínculo de relatoria sem os dados do parlamentar.")
        ultimo_status = rapporteur_record.get("ultimoStatus") or {}
        last_rapporteur = {
            "id": rapporteur_record.get("id"),
            "uri": rapporteur_record.get("uri") or rapporteur_uri,
            "name": ultimo_status.get("nome") or rapporteur_record.get("nomeCivil"),
            "party": ultimo_status.get("siglaPartido"),
            "state": ultimo_status.get("siglaUf"),
        }
    authors = _rows(captured[1].data, "dados", "items")
    movements = _rows(captured[2].data, "dados", "items")
    related = _rows(captured[3].data, "dados", "items")
    votes = _rows(captured[4].data, "dados", "items")

    vote_details = []
    truncated_votes = len(votes) > MAX_NOMINAL_VOTE_SESSIONS
    for vote in votes[:MAX_NOMINAL_VOTE_SESSIONS]:
        vote_id = str(vote.get("id") or "")
        nominal_votes = []
        if re.fullmatch(r"\d+-\d+", vote_id):
            vote_doc = capture(_fetch_json(f"{CHAMBER_BASE_URL}/votacoes/{urllib.parse.quote(vote_id, safe='-')}/votos"))
            nominal_votes = _rows(vote_doc.data, "dados", "items")
            vote_details.append({"vote": vote, "nominal_votes": nominal_votes, "source_url": vote_doc.url})
        else:
            vote_details.append({"vote": vote, "nominal_votes": [], "source_url": ""})
    status = "partial" if truncated_votes else "complete"
    return {
        "status": status,
        "reference": reference,
        "proposal": detail,
        "last_rapporteur": last_rapporteur,
        "authors": authors,
        "proceedings": movements,
        "related_proposals": related,
        "votes": vote_details,
        "truncated_votes": truncated_votes,
        "source_urls": [document.url for document in captured],
    }


def fetch_senate_proceedings(law_type: str, number: str, year: int, *, on_document=None) -> tuple[dict, list[OfficialJsonDocument]]:
    """Resolve and collect process metadata using exact generated-norm identity."""
    type_code = TYPE_CODES.get(law_type)
    if not type_code:
        raise ValueError(f"Tipo normativo sem código de consulta do Senado: {law_type}")
    query_number = _digits(str(number).split("-", 1)[0])
    if not query_number:
        raise ValueError("A consulta de tramitação do Senado exige número normativo.")
    query = urllib.parse.urlencode({"tipoNorma": type_code, "numeroNorma": query_number, "anoNorma": year})
    documents: list[OfficialJsonDocument] = []
    captured_bytes = 0

    def capture(document: OfficialJsonDocument) -> OfficialJsonDocument:
        nonlocal captured_bytes
        captured_bytes += len(document.body)
        if captured_bytes > MAX_DOSSIER_BYTES:
            raise ValueError("O dossiê do Senado excedeu o limite total de arquivamento.")
        documents.append(document)
        if on_document:
            on_document(document)
        return document

    listing = capture(_fetch_json(f"{BASE_URL}/processo?{query}"))
    matches = [process for process in _rows(listing.data, "processos", "processo", "items")
               if _process_norm_matches(process, law_type, number, year)]
    matches.sort(key=lambda item: str(item.get("id") or ""))
    if not matches:
        return ({"status": "no_process", "processes": [], "notice":
                 "A consulta exata ao Senado não retornou processo legislativo vinculado a esta norma."}, documents)

    truncated = len(matches) > MAX_MATCHING_PROCESSES
    selected = matches[:MAX_MATCHING_PROCESSES]
    dossiers = []
    for process in selected:
        process_id = str(process.get("id") or "")
        if not process_id.isdigit():
            raise ValueError("A API do Senado retornou processo sem identificador numérico verificável.")
        detail_doc = capture(_fetch_json(f"{BASE_URL}/processo/{process_id}"))
        detail = detail_doc.data
        if not isinstance(detail, dict) or str(detail.get("id") or "") != process_id:
            raise ValueError("O detalhe retornado pelo Senado não corresponde ao processo consultado.")

        amendments_doc = capture(_fetch_json(f"{BASE_URL}/processo/emenda?" + urllib.parse.urlencode({"idProcesso": process_id})))
        plenary_doc = capture(_fetch_json(f"{BASE_URL}/votacao?" + urllib.parse.urlencode({"idProcesso": process_id})))

        process_sigla = str(detail.get("sigla") or "")
        process_number = str(detail.get("numero") or "")
        process_year = str(detail.get("ano") or "")
        committee_sessions: list[dict] = []
        committee_url = None
        if (re.fullmatch(r"[A-Za-z0-9_-]{1,24}", process_sigla)
                and re.fullmatch(r"\d{1,12}", process_number)
                and re.fullmatch(r"\d{4}", process_year)):
            votes_url = (f"{BASE_URL}/votacaoComissao/materia/"
                         f"{urllib.parse.quote(process_sigla, safe='')}/"
                         f"{urllib.parse.quote(process_number, safe='')}/"
                         f"{urllib.parse.quote(process_year, safe='')}")
            committee_url = votes_url
            committee_doc = capture(_fetch_json(votes_url))
            committee_sessions = _commission_votes(committee_doc.data)

        chamber_refs = _chamber_cross_references(detail)
        chamber_items = [_fetch_chamber_process(reference, capture)
                         for reference in chamber_refs[:MAX_CHAMBER_CROSS_REFERENCES]]
        chamber_truncated = len(chamber_refs) > MAX_CHAMBER_CROSS_REFERENCES

        dossiers.append({
            "search_result": process,
            "process": detail,
            "amendments": _rows(amendments_doc.data, "emendas", "emenda", "Emendas", "Emenda", "items", "dados"),
            "plenary_votes": _rows(plenary_doc.data, "votacoes", "votacao", "Votacoes", "Votacao", "items", "dados"),
            "committee_votes": committee_sessions,
            "chamber_references": chamber_refs,
            "chamber_processes": chamber_items,
            "chamber_truncated": chamber_truncated,
            "source_urls": [listing.url, detail_doc.url, amendments_doc.url, plenary_doc.url,
                            *([committee_url] if committee_url else [])],
        })
    status = "partial" if truncated or any(
        item.get("status") == "partial" or item.get("chamber_truncated")
        or any(chamber.get("status") != "complete" for chamber in item.get("chamber_processes", []))
        for item in dossiers
    ) else "complete"
    return ({"status": status, "processes": dossiers, "matching_processes_found": len(matches),
             "processes_loaded": len(dossiers), "truncated": truncated}, documents)
