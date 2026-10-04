"""Synchronize Brazil's official territorial directory from IBGE."""
from __future__ import annotations

import gzip
import json
import urllib.request
from datetime import datetime, timezone

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Jurisdiction, SourceRegistry

IBGE_STATES = "https://servicodados.ibge.gov.br/api/v1/localidades/estados"
IBGE_MUNICIPALITIES = "https://servicodados.ibge.gov.br/api/v1/localidades/municipios"


def _get_json(url: str):
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "Accept-Encoding": "gzip", "User-Agent": "LeiAberta/1.0 (+https://github.com/DIDIDXX/LeiAberta)"},
    )
    with urllib.request.urlopen(request, timeout=45) as response:
        body = response.read()
        if response.headers.get("Content-Encoding", "").lower() == "gzip" or body[:2] == b"\x1f\x8b":
            body = gzip.decompress(body)
        return json.loads(body.decode("utf-8"))


def _uf(item: dict) -> str | None:
    """IBGE nests UF differently between locality endpoints; walk known paths."""
    if item.get("sigla") and len(str(item["sigla"])) == 2:
        return str(item["sigla"])
    current = item
    for key in ("microrregiao", "mesorregiao", "regiao-imediata", "regiao-intermediaria", "UF"):
        if not isinstance(current, dict):
            break
        current = current.get(key)
    if isinstance(current, dict) and current.get("sigla"):
        return str(current["sigla"])
    # Current IBGE municipality payload: regiao-imediata -> regiao-intermediaria -> UF.
    current = item.get("regiao-imediata") or {}
    current = current.get("regiao-intermediaria") or {}
    current = current.get("UF") or {}
    return str(current["sigla"]) if current.get("sigla") else None


def _upsert(session, jurisdiction_id: str, *, kind: str, name: str, code: str | None,
            uf: str | None, parent_id: str | None, eligible: bool, note: str,
            source_url: str, observed_at: datetime) -> None:
    item = session.get(Jurisdiction, jurisdiction_id)
    if item is None:
        item = Jurisdiction(id=jurisdiction_id, source_url=source_url)
        session.add(item)
    item.kind = kind
    item.name = name
    item.ibge_code = code
    item.uf = uf
    item.parent_id = parent_id
    item.legislature_eligible = eligible
    item.territorial_status = "active"
    item.metadata_json = {"classification_note": note} if note else {}
    item.source_url = source_url
    item.observed_at = observed_at


def _seed_sources(session, observed_at: datetime) -> int:
    # Only sources with observed primary evidence are registered here. These are
    # starting points; "discovered" does not mean that national coverage exists.
    seeds = [
        ("federal:planalto", None, "Planalto", "planalto", "https://www.planalto.gov.br/ccivil_03/", {"jurisdiction": "federal", "status": "confirmed_entrypoint"}),
        ("federal:senado", None, "Senado Federal — Dados Abertos", "senado", "https://legis.senado.leg.br/dadosabertos/", {"jurisdiction": "federal", "status": "confirmed_api"}),
        ("federal:camara", None, "Câmara dos Deputados — Legislação", "camara", "https://www.camara.leg.br/legislacao/", {"jurisdiction": "federal", "status": "confirmed_entrypoint"}),
        ("discovery:lexml", None, "LexML Brasil", "lexml", "https://www.lexml.gov.br/", {"status": "discovery_only", "limitation": "protocol not validated"}),
        ("state:SP:alesp", "state:SP", "ALESP — Normas", "alesp", "https://www.al.sp.gov.br/norma/", {"status": "entrypoint_confirmed", "coverage": "pilot pending"}),
        ("state:DF:sinj", "state:DF", "SINJ-DF", "sinj", "https://www.sinj.df.gov.br/sinj/", {"status": "entrypoint_confirmed", "coverage": "pilot pending"}),
    ]
    for rid, jid, name, adapter, url, scope in seeds:
        row = session.get(SourceRegistry, rid)
        if row is None:
            row = SourceRegistry(id=rid, name=name, adapter=adapter, base_url=url,
                                 evidence_url=url, scope=scope, status="discovered")
            session.add(row)
        row.jurisdiction_id = jid
        row.name = name
        row.adapter = adapter
        row.base_url = url
        row.evidence_url = url
        row.scope = scope
        # Do not promote a discovered source to operational based on a registry seed.
        row.last_checked_at = observed_at
    return len(seeds)


def sync_ibge_jurisdictions() -> dict:
    """Idempotently upsert federal, state and municipality entities.

    IBGE lists districts/administrative localities along with municipalities.
    Brasília and Fernando de Noronha are explicitly excluded as independent
    municipal legislatures; Brasília is a DF region and Fernando de Noronha is
    a district of PE. All fetched records remain in the inventory.
    """
    states = _get_json(IBGE_STATES)
    municipalities = _get_json(IBGE_MUNICIPALITIES)
    observed_at = datetime.now(timezone.utc)
    state_by_code: dict[str, dict] = {}
    with SessionLocal() as session:
        _upsert(session, "federal", kind="federal", name="União", code=None, uf=None,
                parent_id=None, eligible=True, note="", source_url=IBGE_STATES, observed_at=observed_at)
        for state in states:
            uf = str(state.get("sigla", "")).upper()
            code = str(state["id"])
            state_by_code[code] = state
            _upsert(session, f"state:{uf}", kind="state", name=state["nome"], code=code,
                    uf=uf, parent_id="federal", eligible=True, note="",
                    source_url=IBGE_STATES, observed_at=observed_at)
        special = {"5300108": "Brasília é região administrativa do DF, não município legislativo independente.",
                   "2605459": "Fernando de Noronha é distrito estadual de Pernambuco, não município legislativo independente."}
        for city in municipalities:
            code = str(city["id"])
            uf = _uf(city)
            if uf is None:
                raise ValueError(f"IBGE municipality {code} has no resolvable UF")
            _upsert(session, f"municipality:{code}", kind="municipality", name=city["nome"],
                    code=code, uf=uf, parent_id=f"state:{uf}", eligible=code not in special,
                    note=special.get(code, ""), source_url=IBGE_MUNICIPALITIES, observed_at=observed_at)
        source_count = _seed_sources(session, observed_at)
        session.commit()
        eligible_count = sum(1 for city in municipalities if str(city["id"]) not in special)
        return {"states": len(states), "localities": len(municipalities),
                "municipal_legislatures": eligible_count, "excluded_special_localities": len(special),
                "sources_seeded": source_count, "observed_at": observed_at.isoformat()}
