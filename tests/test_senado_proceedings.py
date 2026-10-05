import json

import pytest

from app.sources import senado_proceedings as source


def _document(url, value):
    body = json.dumps(value, ensure_ascii=False).encode()
    return source.OfficialJsonDocument(url, body, value)


def test_senate_proceedings_collects_exact_process_amendments_and_named_votes(monkeypatch):
    session = {
        "CodigoVotacao": "34118",
        "DataHoraInicioReuniao": "2022-12-13T10:00:00",
        "NomeColegiado": "Comissão de Constituição, Justiça e Cidadania",
        "DescricaoVotacao": "PL 1604/2022 (nos termos do Parecer)",
        "Votos": {"Voto": [{"NomeParlamentar": "Simone Tebet", "QualidadeVoto": "S"}]},
    }
    fixtures = {
        "/processo?": [{"id": 8272922, "normaGerada": "Lei nº 14.550 de 19/04/2023"}],
        "/processo/8272922": {
            "id": 8272922, "identificacao": "PL 1604/2022", "sigla": "PL", "numero": "1604", "ano": 2022,
            "casaIdentificadora": "SF", "situacaoAtual": "TRANSFORMADA EM NORMA JURÍDICA",
            "conteudo": {"ementa": "Altera a Lei Maria da Penha."},
            "documento": {"dataApresentacao": "2022-06-13", "autoria": [{"autor": "Simone Tebet"}]},
        },
        "/processo/emenda?": [{"identificacao": "EMENDA 1 / CCJ", "autoria": "Eliziane Gama"}],
        "/votacao?": [],
        "/votacaoComissao/materia/PL/1604/2022": {
            "VotacoesComissao": {"Votacoes": {"Votacao": session}},
        },
    }
    calls = []

    def fake_fetch(url, timeout=25):
        calls.append(url)
        fixture_key = next(key for key in fixtures if key in url)
        return _document(url, fixtures[fixture_key])

    monkeypatch.setattr(source, "_fetch_json", fake_fetch)
    archived = []
    result, documents = source.fetch_senate_proceedings("Lei", "14.550", 2023, on_document=archived.append)

    assert result["status"] == "complete"
    assert result["matching_processes_found"] == 1
    dossier = result["processes"][0]
    assert dossier["process"]["identificacao"] == "PL 1604/2022"
    assert dossier["amendments"][0]["identificacao"] == "EMENDA 1 / CCJ"
    assert dossier["committee_votes"][0]["votes"][0]["NomeParlamentar"] == "Simone Tebet"
    assert len(documents) == 5
    assert len(archived) == 5
    assert "numeroNorma=14550" in calls[0]


def test_senate_process_requires_exact_generated_norm_identity(monkeypatch):
    listing = [{"id": 1, "normaGerada": "Lei nº 14.551 de 19/04/2023"}]
    monkeypatch.setattr(source, "_fetch_json", lambda url, timeout=25: _document(url, listing))

    result, documents = source.fetch_senate_proceedings("Lei", "14.550", 2023)

    assert result["status"] == "no_process"
    assert result["processes"] == []
    assert len(documents) == 1


def test_senate_dossier_archives_documents_before_later_fetch_failure(monkeypatch):
    replies = [
        _document("https://example.test/list", [{"id": 8272922, "normaGerada": "Lei nº 14.550 de 19/04/2023"}]),
        _document("https://example.test/detail", {"id": 8272922, "sigla": "PL", "numero": "1604", "ano": 2022}),
    ]
    archived = []

    def fake_fetch(url, timeout=25):
        if "/processo/emenda?" in url:
            raise RuntimeError("transient endpoint failure")
        return replies.pop(0)

    monkeypatch.setattr(source, "_fetch_json", fake_fetch)
    with pytest.raises(RuntimeError, match="transient endpoint failure"):
        source.fetch_senate_proceedings("Lei", "14.550", 2023, on_document=archived.append)
    assert [item.url for item in archived] == ["https://example.test/list", "https://example.test/detail"]


def test_chamber_proposal_requires_exact_senate_cross_reference_and_identity(monkeypatch):
    reference = {"sigla": "PL", "numero": "01604", "ano": "2022", "senate_reference_id": "8349662"}
    responses = {
        "/proposicoes?": {"dados": [
            {"id": 7, "siglaTipo": "PL", "numero": 1604, "ano": 2023},
            {"id": 2345499, "siglaTipo": "PL", "numero": 1604, "ano": 2022},
        ]},
        "/proposicoes/2345499": {"dados": {"id": 2345499, "siglaTipo": "PL", "numero": 1604, "ano": 2022,
                                             "statusProposicao": {"uriUltimoRelator": "https://dadosabertos.camara.leg.br/api/v2/deputados/74848"}}},
        "/deputados/74848": {"dados": {"id": 74848, "nomeCivil": "RELATORA TESTE",
                                         "uri": "https://dadosabertos.camara.leg.br/api/v2/deputados/74848",
                                         "ultimoStatus": {"nome": "Relatora Teste", "siglaPartido": "ABC", "siglaUf": "SP"},
                                         "cpf": "00000000000", "dataNascimento": "1970-01-01"}},
        "/proposicoes/2345499/autores": {"dados": [{"nome": "Senado Federal - Simone Tebet"}]},
        "/proposicoes/2345499/tramitacoes": {"dados": [{"dataHora": "2023-01-03", "descricaoTramitacao": "Recebimento"}]},
        "/proposicoes/2345499/relacionadas": {"dados": [{"id": 99, "siglaTipo": "PEP", "numero": "1", "ano": "0"}]},
        "/proposicoes/2345499/votacoes": {"dados": [{"id": "2345499-50", "data": "2023-03-21", "descricao": "Projeto aprovado"}]},
        "/votacoes/2345499-50/votos": {"dados": [{"tipoVoto": "Sim", "deputado_": {"nome": "Deputada Teste"}}]},
    }
    archived = []

    def fake_fetch(url, timeout=25):
        key = next(key for key in sorted(responses, key=len, reverse=True) if key in url)
        return _document(url, responses[key])

    monkeypatch.setattr(source, "_fetch_json", fake_fetch)
    dossier = source._fetch_chamber_process(reference, lambda document: archived.append(document) or document)

    assert dossier["status"] == "complete"
    assert dossier["proposal"]["id"] == 2345499
    assert dossier["authors"][0]["nome"] == "Senado Federal - Simone Tebet"
    assert dossier["votes"][0]["nominal_votes"][0]["deputado_"]["nome"] == "Deputada Teste"
    assert dossier["last_rapporteur"]["name"] == "Relatora Teste"
    assert "cpf" not in dossier["last_rapporteur"]
    assert len(archived) == 8


def test_senate_dossier_only_uses_explicit_chamber_cross_references():
    detail = {"outrosNumeros": [
        {"idOutroProcesso": 8349662, "sigla": "PL", "numero": "01604", "ano": 2022,
         "casaIdentificadora": "CD", "siglaEnteIdentificador": "CD"},
        {"idOutroProcesso": 999, "sigla": "PL", "numero": "1604", "ano": 2022,
         "casaIdentificadora": "SF", "siglaEnteIdentificador": "SF"},
    ]}
    assert source._chamber_cross_references(detail) == [
        {"sigla": "PL", "numero": "01604", "ano": "2022", "senate_reference_id": "8349662"},
    ]
