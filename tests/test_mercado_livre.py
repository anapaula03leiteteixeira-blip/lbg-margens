from unittest.mock import patch
from src.platforms.mercado_livre import (
    _detectar_tipo,
    _net_received_por_order,
    obter_vliquido,
)


# ---------- _detectar_tipo ----------

def test_detectar_flex():
    assert _detectar_tipo('self_service') == 'flex'


def test_detectar_full():
    assert _detectar_tipo('fulfillment') == 'full'


def test_detectar_padrao():
    assert _detectar_tipo('me2') == 'padrao'


def test_detectar_padrao_sem_logistic_type():
    assert _detectar_tipo('') == 'padrao'


# ---------- _net_received_por_order ----------

def test_net_received_retorna_valor():
    def mock_get(endpoint, params=None):
        return {'results': [{'net_received_amount': 185.0}]}

    with patch('src.platforms.mercado_livre._get', side_effect=mock_get):
        resultado = _net_received_por_order('123')

    assert resultado == 185.0


def test_net_received_com_collection_aninhado():
    def mock_get(endpoint, params=None):
        return {'results': [{'collection': {'net_received_amount': 200.0}}]}

    with patch('src.platforms.mercado_livre._get', side_effect=mock_get):
        resultado = _net_received_por_order('123')

    assert resultado == 200.0


def test_net_received_retorna_none_sem_resultados():
    with patch('src.platforms.mercado_livre._get', return_value={'results': []}):
        assert _net_received_por_order('999') is None


# ---------- obter_vliquido individual ----------

def test_vliquido_padrao_usa_net_received():
    def mock_get(endpoint, params=None):
        if '/packs/' in endpoint:
            raise Exception('404')
        if '/orders/' in endpoint:
            return {'shipping': {'logistic_type': 'me2'}, 'total_amount': 200.0}
        if '/collections/search' in endpoint:
            return {'results': [{'net_received_amount': 185.0}]}
        return {}

    with patch('src.platforms.mercado_livre._get', side_effect=mock_get):
        resultado = obter_vliquido('123')

    assert resultado['v_liquido'] == 185.0
    assert resultado['plataforma'] == 'Mercado Livre'
    assert resultado['v_liquido_estimado'] is False


def test_vliquido_flex_desconta_taxa_fixa():
    def mock_get(endpoint, params=None):
        if '/packs/' in endpoint:
            raise Exception('404')
        if '/orders/' in endpoint:
            return {'shipping': {'logistic_type': 'self_service'}, 'total_amount': 200.0}
        return {}

    with patch('src.platforms.mercado_livre._get', side_effect=mock_get):
        resultado = obter_vliquido('123', taxa_fixa_flex=14.99)

    assert resultado['v_liquido'] == round(200.0 - 14.99, 2)
    assert resultado['plataforma'] == 'Mercado Livre Flex'
    assert resultado['v_liquido_estimado'] is False


def test_vliquido_full_usa_net_received():
    def mock_get(endpoint, params=None):
        if '/packs/' in endpoint:
            raise Exception('404')
        if '/orders/' in endpoint:
            return {'shipping': {'logistic_type': 'fulfillment'}, 'total_amount': 300.0}
        if '/collections/search' in endpoint:
            return {'results': [{'net_received_amount': 270.0}]}
        return {}

    with patch('src.platforms.mercado_livre._get', side_effect=mock_get):
        resultado = obter_vliquido('456')

    assert resultado['v_liquido'] == 270.0
    assert resultado['plataforma'] == 'Mercado Livre Full'


def test_vliquido_canal_ecommerce():
    def mock_get(endpoint, params=None):
        if '/packs/' in endpoint:
            raise Exception('404')
        if '/orders/' in endpoint:
            return {'shipping': {'logistic_type': 'self_service'}, 'total_amount': 100.0}
        return {}

    with patch('src.platforms.mercado_livre._get', side_effect=mock_get):
        resultado = obter_vliquido('1')

    assert resultado['canal'] == 'E-commerce'


def test_vliquido_via_pack():
    def mock_get(endpoint, params=None):
        if '/packs/' in endpoint:
            return {'orders': [{'id': 999}]}
        if '/orders/' in endpoint:
            return {'shipping': {'logistic_type': 'self_service'}, 'total_amount': 150.0}
        return {}

    with patch('src.platforms.mercado_livre._get', side_effect=mock_get):
        resultado = obter_vliquido('777', taxa_fixa_flex=14.99)

    assert resultado['v_liquido'] == round(150.0 - 14.99, 2)
    assert resultado['plataforma'] == 'Mercado Livre Flex'
