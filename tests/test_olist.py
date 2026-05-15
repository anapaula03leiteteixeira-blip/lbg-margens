import pytest
import requests
from unittest.mock import patch, MagicMock

from src.erp.olist import _post


def _mock_response(json_data):
    mock = MagicMock()
    mock.raise_for_status.return_value = None
    mock.json.return_value = json_data
    return mock


_RETORNO_OK = {'retorno': {'status': 'OK', 'pedidos': [], 'numero_paginas': 1}}


# ---------- retry em erro de rede ----------

def test_post_retenta_em_connection_error():
    """ConnectionError nas primeiras tentativas deve retentar e ter sucesso."""
    respostas = [
        requests.exceptions.ConnectionError('rede caiu'),
        requests.exceptions.ConnectionError('rede caiu'),
        _mock_response(_RETORNO_OK),
    ]
    with patch('requests.post', side_effect=respostas) as mock_post, \
         patch('time.sleep'):
        resultado = _post('pedidos.pesquisa.php', {'dataInicial': '01/05/2026'})

    assert mock_post.call_count == 3
    assert resultado['status'] == 'OK'


def test_post_retenta_em_timeout():
    """Timeout deve retentar e ter sucesso na próxima tentativa."""
    respostas = [
        requests.exceptions.Timeout('timeout'),
        _mock_response(_RETORNO_OK),
    ]
    with patch('requests.post', side_effect=respostas) as mock_post, \
         patch('time.sleep'):
        resultado = _post('pedidos.pesquisa.php', {})

    assert mock_post.call_count == 2
    assert resultado['status'] == 'OK'


def test_post_falha_apos_max_retries_de_rede():
    """Após 5 ConnectionErrors consecutivos deve propagar a exceção."""
    with patch('requests.post', side_effect=requests.exceptions.ConnectionError('rede')), \
         patch('time.sleep'):
        with pytest.raises(requests.exceptions.ConnectionError):
            _post('pedidos.pesquisa.php', {})


# ---------- retry em rate limit ----------

def test_post_retenta_em_bloqueada():
    """Erro 'Bloqueada' da Tiny deve retentar após espera."""
    bloqueada = {'retorno': {'status': 'Erro', 'erros': [{'erro': 'Bloqueada'}]}}
    respostas = [
        _mock_response(bloqueada),
        _mock_response(_RETORNO_OK),
    ]
    with patch('requests.post', side_effect=respostas) as mock_post, \
         patch('time.sleep'):
        resultado = _post('pedidos.pesquisa.php', {})

    assert mock_post.call_count == 2
    assert resultado['status'] == 'OK'


# ---------- sucesso direto ----------

def test_post_retorna_retorno_em_sucesso():
    with patch('requests.post', return_value=_mock_response(_RETORNO_OK)), \
         patch('time.sleep'):
        resultado = _post('pedidos.pesquisa.php', {})

    assert resultado['status'] == 'OK'
