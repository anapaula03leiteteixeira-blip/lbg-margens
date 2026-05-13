from unittest.mock import patch, MagicMock
from src.platforms.mercado_livre import (
    _detectar_tipo,
    _resolver_order_ids,
    obter_vliquido,
)


# ---------- _detectar_tipo ----------

def test_detectar_flex():
    order = {'shipping': {'logistic_type': 'self_service'}}
    assert _detectar_tipo(order) == 'flex'


def test_detectar_full():
    order = {'shipping': {'logistic_type': 'fulfillment'}}
    assert _detectar_tipo(order) == 'full'


def test_detectar_padrao():
    order = {'shipping': {'logistic_type': 'me2'}}
    assert _detectar_tipo(order) == 'padrao'


def test_detectar_padrao_sem_shipping():
    assert _detectar_tipo({}) == 'padrao'


# ---------- _resolver_order_ids ----------

def test_resolve_pack_para_order_ids():
    with patch('src.platforms.mercado_livre._get') as mock_get:
        mock_get.return_value = {'orders': [{'id': 111}, {'id': 222}]}
        ids = _resolver_order_ids('999888777')
    assert ids == ['111', '222']


def test_resolve_order_id_direto_quando_pack_falha():
    with patch('src.platforms.mercado_livre._get', side_effect=Exception('404')):
        ids = _resolver_order_ids('123456')
    assert ids == ['123456']


# ---------- obter_vliquido ----------

def test_vliquido_padrao_usa_net_received():
    order_padrao = {'shipping': {'logistic_type': 'me2'}, 'total_amount': 200.0}
    with patch('src.platforms.mercado_livre._resolver_order_ids', return_value=['123']):
        with patch('src.platforms.mercado_livre._get', return_value=order_padrao):
            with patch('src.platforms.mercado_livre._obter_net_received', return_value=185.0):
                resultado = obter_vliquido('123')

    assert resultado['v_liquido'] == 185.0
    assert resultado['plataforma'] == 'Mercado Livre'
    assert resultado['v_liquido_estimado'] is False


def test_vliquido_flex_desconta_taxa_fixa():
    order_flex = {'shipping': {'logistic_type': 'self_service'}, 'total_amount': 200.0}
    with patch('src.platforms.mercado_livre._resolver_order_ids', return_value=['123']):
        with patch('src.platforms.mercado_livre._get', return_value=order_flex):
            resultado = obter_vliquido('123', taxa_fixa_flex=14.90)

    assert resultado['v_liquido'] == round(200.0 - 14.90, 2)
    assert resultado['plataforma'] == 'Mercado Livre Flex'


def test_vliquido_full_usa_net_received():
    order_full = {'shipping': {'logistic_type': 'fulfillment'}, 'total_amount': 300.0}
    with patch('src.platforms.mercado_livre._resolver_order_ids', return_value=['456']):
        with patch('src.platforms.mercado_livre._get', return_value=order_full):
            with patch('src.platforms.mercado_livre._obter_net_received', return_value=270.0):
                resultado = obter_vliquido('456')

    assert resultado['v_liquido'] == 270.0
    assert resultado['plataforma'] == 'Mercado Livre Full'


def test_canal_sempre_ecommerce():
    order = {'shipping': {'logistic_type': 'me2'}, 'total_amount': 100.0}
    with patch('src.platforms.mercado_livre._resolver_order_ids', return_value=['1']):
        with patch('src.platforms.mercado_livre._get', return_value=order):
            with patch('src.platforms.mercado_livre._obter_net_received', return_value=90.0):
                resultado = obter_vliquido('1')
    assert resultado['canal'] == 'E-commerce'
