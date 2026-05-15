"""Shopee Open Platform v2 — V.LIQUIDO via escrow (COMPLETED) ou estimativa (em trânsito)."""
import os
import re
import hmac
import hashlib
import time
import requests
from dotenv import load_dotenv

load_dotenv()

_HOST        = 'https://partner.shopeemobile.com'
_PARTNER_ID  = int(os.getenv('SHOPEE_PARTNER_ID', '0') or '0')
_PARTNER_KEY = os.getenv('SHOPEE_PARTNER_KEY', '')
_SHOP_ID     = int(os.getenv('SHOPEE_SHOP_ID', '0') or '0')

_token = {
    'access':  os.getenv('SHOPEE_ACCESS_TOKEN', ''),
    'refresh': os.getenv('SHOPEE_REFRESH_TOKEN', ''),
}

# Em GitHub Actions não há .env — carrega tokens rotacionados do Supabase se disponível
try:
    from src.database import buscar_config as _buscar_config
    _supa_access  = _buscar_config('SHOPEE_ACCESS_TOKEN')
    _supa_refresh = _buscar_config('SHOPEE_REFRESH_TOKEN')
    if _supa_access:
        _token['access'] = _supa_access
    if _supa_refresh:
        _token['refresh'] = _supa_refresh
except Exception:
    pass

_CARRIER_PLATAFORMA = {
    'entrega direta': 'Shopee Flex',
    'shopee xpress':  'Shopee',
}

# Statuses em que o escrow já é definitivo
_STATUS_ESCROW_DISPONIVEL = {'COMPLETED'}


# ---------- autenticação ----------

def _sign(path, timestamp):
    base = f'{_PARTNER_ID}{path}{timestamp}{_token["access"]}{_SHOP_ID}'
    return hmac.new(_PARTNER_KEY.encode(), base.encode(), hashlib.sha256).hexdigest()


def _sign_public(path, timestamp):
    base = f'{_PARTNER_ID}{path}{timestamp}'
    return hmac.new(_PARTNER_KEY.encode(), base.encode(), hashlib.sha256).hexdigest()


def _atualizar_env(chave, valor):
    env_path = os.path.join(os.path.dirname(__file__), '..', '..', '.env')
    with open(env_path, 'r', encoding='utf-8') as f:
        conteudo = f.read()
    if re.search(rf'^{chave}=', conteudo, flags=re.MULTILINE):
        conteudo = re.sub(rf'^{chave}=.*$', f'{chave}={valor}', conteudo, flags=re.MULTILINE)
    else:
        conteudo += f'\n{chave}={valor}'
    with open(env_path, 'w', encoding='utf-8') as f:
        f.write(conteudo)


def _persistir_token(chave, valor):
    """Salva token rotacionado no Supabase (sempre) e no .env local (se existir)."""
    try:
        from src.database import salvar_config
        salvar_config(chave, valor)
    except Exception:
        pass
    env_path = os.path.join(os.path.dirname(__file__), '..', '..', '.env')
    if os.path.exists(env_path):
        _atualizar_env(chave, valor)


def renovar_token():
    path = '/api/v2/auth/access_token/get'
    timestamp = int(time.time())
    sign = _sign_public(path, timestamp)
    resp = requests.post(
        f'{_HOST}{path}',
        params={'partner_id': _PARTNER_ID, 'timestamp': timestamp, 'sign': sign},
        json={'refresh_token': _token['refresh'], 'shop_id': _SHOP_ID, 'partner_id': _PARTNER_ID},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get('error'):
        raise RuntimeError(f'Shopee refresh token falhou: {data.get("message")}')
    _token['access'] = data['access_token']
    _token['refresh'] = data.get('refresh_token', _token['refresh'])
    _persistir_token('SHOPEE_ACCESS_TOKEN', _token['access'])
    _persistir_token('SHOPEE_REFRESH_TOKEN', _token['refresh'])


def _get(path, params=None):
    for tentativa in range(2):
        timestamp = int(time.time())
        base_params = {
            'partner_id':   _PARTNER_ID,
            'timestamp':    timestamp,
            'access_token': _token['access'],
            'shop_id':      _SHOP_ID,
            'sign':         _sign(path, timestamp),
        }
        if params:
            base_params.update(params)
        resp = requests.get(f'{_HOST}{path}', params=base_params, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if data.get('error') in ('error_auth', 'invalid_access_token') and tentativa == 0:
                renovar_token()
                continue
            return data
        if resp.status_code == 401 and tentativa == 0:
            renovar_token()
            continue
        resp.raise_for_status()
    raise RuntimeError(f'Falha na requisição Shopee: {path}')


# ---------- lógica de negócio ----------

def _obter_order_info(order_sn):
    """Retorna (order_status, shipping_carrier) do pedido."""
    data = _get('/api/v2/order/get_order_detail', {
        'order_sn_list':            order_sn,
        'response_optional_fields': 'shipping_carrier',
    })
    order_list = data.get('response', {}).get('order_list', [])
    if not order_list:
        return None, None
    order = order_list[0]
    return order.get('order_status'), order.get('shipping_carrier', '')


def _obter_escrow(order_sn):
    """Retorna escrow_amount real. None se indisponível."""
    try:
        data = _get('/api/v2/payment/get_escrow_detail', {'order_sn': order_sn})
        if data.get('error'):
            return None
        return data.get('response', {}).get('order_income', {}).get('escrow_amount')
    except Exception:
        return None


def _resolver_plataforma(carrier):
    if not carrier:
        return 'Shopee'
    return _CARRIER_PLATAFORMA.get(carrier.lower(), 'Shopee')


# ---------- interface pública ----------

def obter_vliquido(num_pedido_ecommerce, taxa_fixa_flex=None, **kwargs):
    """
    Contrato padrão das plataformas.
    Retorna dict com: v_liquido, plataforma, canal, v_liquido_estimado, aguardando_escrow.

    - COMPLETED → escrow real, v_liquido_estimado=False
    - Demais    → v_liquido=None, aguardando_escrow=True (pipeline fará estimativa)
    """
    if not _PARTNER_ID or not _PARTNER_KEY or not _SHOP_ID:
        return {
            'v_liquido': None, 'plataforma': 'Shopee',
            'canal': 'E-commerce', 'v_liquido_estimado': False, 'aguardando_escrow': True,
        }

    if taxa_fixa_flex is None:
        taxa_fixa_flex = float(os.getenv('SHOPEE_TAXA_FIXA_FLEX', 9.99))

    order_sn = str(num_pedido_ecommerce)
    try:
        order_status, carrier = _obter_order_info(order_sn)
    except Exception:
        return {
            'v_liquido': None, 'plataforma': 'Shopee',
            'canal': 'E-commerce', 'v_liquido_estimado': False, 'aguardando_escrow': True,
        }

    plataforma = _resolver_plataforma(carrier)

    if order_status in _STATUS_ESCROW_DISPONIVEL:
        escrow = _obter_escrow(order_sn)
        if escrow is not None:
            v_base = round(float(escrow), 2)
            v_liquido = round(v_base - taxa_fixa_flex, 2) if plataforma == 'Shopee Flex' else v_base
            return {
                'v_liquido': v_liquido, 'plataforma': plataforma,
                'canal': 'E-commerce', 'v_liquido_estimado': False, 'aguardando_escrow': False,
            }

    # Pedido ainda em trânsito ou escrow indisponível — pipeline calculará estimativa
    return {
        'v_liquido': None, 'plataforma': plataforma,
        'canal': 'E-commerce', 'v_liquido_estimado': False, 'aguardando_escrow': True,
    }
