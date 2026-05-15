import pytest
from unittest.mock import patch
from src.platforms.shopee import obter_vliquido, _resolver_plataforma


# helpers de resposta mock

def _carrier_resp(carrier, status='COMPLETED'):
    return {
        'error': '',
        'response': {'order_list': [{'shipping_carrier': carrier, 'order_status': status}]}
    }


_ESCROW_OK = {
    'error': '',
    'response': {'order_income': {'escrow_amount': 123.85}}
}

_ESCROW_VAZIO = {
    'error': '',
    'response': {'order_income': {}}
}


# ---------- _resolver_plataforma ----------

def test_resolver_plataforma_entrega_direta():
    assert _resolver_plataforma('Entrega Direta') == 'Shopee Flex'


def test_resolver_plataforma_xpress():
    assert _resolver_plataforma('Shopee Xpress') == 'Shopee'


def test_resolver_plataforma_retirada():
    assert _resolver_plataforma('Retirada pelo Comprador') == 'Shopee'


def test_resolver_plataforma_desconhecido():
    assert _resolver_plataforma('Desconhecido') == 'Shopee'


# ---------- pedido COMPLETED — escrow real ----------

def test_completed_flex_desconta_taxa_fixa():
    with patch('src.platforms.shopee._get', side_effect=[_carrier_resp('Entrega Direta'), _ESCROW_OK]):
        resultado = obter_vliquido('123', taxa_fixa_flex=9.99)
    assert resultado['v_liquido'] == round(123.85 - 9.99, 2)
    assert resultado['plataforma'] == 'Shopee Flex'
    assert resultado['v_liquido_estimado'] is False
    assert resultado['aguardando_escrow'] is False


def test_completed_xpress_sem_deducao():
    with patch('src.platforms.shopee._get', side_effect=[_carrier_resp('Shopee Xpress'), _ESCROW_OK]):
        resultado = obter_vliquido('123')
    assert resultado['v_liquido'] == 123.85
    assert resultado['plataforma'] == 'Shopee'
    assert resultado['v_liquido_estimado'] is False


def test_canal_sempre_ecommerce():
    with patch('src.platforms.shopee._get', side_effect=[_carrier_resp('Shopee Xpress'), _ESCROW_OK]):
        resultado = obter_vliquido('123')
    assert resultado['canal'] == 'E-commerce'


def test_completed_escrow_vazio_retorna_none():
    with patch('src.platforms.shopee._get', side_effect=[_carrier_resp('Shopee Xpress'), _ESCROW_VAZIO]):
        resultado = obter_vliquido('123')
    assert resultado['v_liquido'] is None


# ---------- pedido em trânsito — aguardando escrow ----------

def test_em_transito_retorna_aguardando():
    with patch('src.platforms.shopee._get', return_value=_carrier_resp('Shopee Xpress', status='READY_TO_SHIP')):
        resultado = obter_vliquido('456')
    assert resultado['v_liquido'] is None
    assert resultado['aguardando_escrow'] is True
    assert resultado['v_liquido_estimado'] is False
    assert resultado['plataforma'] == 'Shopee'


def test_shipped_retorna_aguardando():
    with patch('src.platforms.shopee._get', return_value=_carrier_resp('Entrega Direta', status='SHIPPED')):
        resultado = obter_vliquido('789')
    assert resultado['aguardando_escrow'] is True
    assert resultado['plataforma'] == 'Shopee Flex'


def test_unpaid_retorna_aguardando():
    with patch('src.platforms.shopee._get', return_value=_carrier_resp('Shopee Xpress', status='UNPAID')):
        resultado = obter_vliquido('101')
    assert resultado['aguardando_escrow'] is True


# ---------- sem credenciais ----------

def test_sem_credenciais_retorna_none():
    import src.platforms.shopee as shopee
    original = shopee._PARTNER_ID
    shopee._PARTNER_ID = 0
    resultado = obter_vliquido('123')
    shopee._PARTNER_ID = original
    assert resultado['v_liquido'] is None
    assert resultado['aguardando_escrow'] is False
