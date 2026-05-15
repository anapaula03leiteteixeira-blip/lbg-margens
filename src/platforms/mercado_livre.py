"""Mercado Livre — V.LIQUIDO por pedido via collections ou cálculo Flex."""
import os
import re
from datetime import datetime
import requests
from dotenv import load_dotenv

load_dotenv()

_BASE = 'https://api.mercadolibre.com'
_APP_ID = os.getenv('ML_APP_ID')
_CLIENT_SECRET = os.getenv('ML_CLIENT_SECRET')
_SELLER_ID = os.getenv('ML_SELLER_ID')

_token = {
    'access': os.getenv('ML_ACCESS_TOKEN', ''),
    'refresh': os.getenv('ML_REFRESH_TOKEN', ''),
}

# Em GitHub Actions não há .env — carrega tokens rotacionados do Supabase se disponível
try:
    from src.database import buscar_config as _buscar_config
    _supa_access  = _buscar_config('ML_ACCESS_TOKEN')
    _supa_refresh = _buscar_config('ML_REFRESH_TOKEN')
    if _supa_access:
        _token['access'] = _supa_access
    if _supa_refresh:
        _token['refresh'] = _supa_refresh
except Exception:
    pass

_PLATAFORMA_MAP = {
    'flex':   'Mercado Livre Flex',
    'full':   'Mercado Livre Full',
    'padrao': 'Mercado Livre',
}


# ---------- autenticação ----------

def _atualizar_env(chave, valor):
    env_path = os.path.join(os.path.dirname(__file__), '..', '..', '.env')
    with open(env_path, 'r', encoding='utf-8') as f:
        conteudo = f.read()
    conteudo = re.sub(rf'^{chave}=.*$', f'{chave}={valor}', conteudo, flags=re.MULTILINE)
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
    resp = requests.post(f'{_BASE}/oauth/token', data={
        'grant_type': 'refresh_token',
        'client_id': _APP_ID,
        'client_secret': _CLIENT_SECRET,
        'refresh_token': _token['refresh'],
    }, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    _token['access'] = data['access_token']
    _token['refresh'] = data.get('refresh_token', _token['refresh'])
    _persistir_token('ML_ACCESS_TOKEN', _token['access'])
    _persistir_token('ML_REFRESH_TOKEN', _token['refresh'])


def _get(endpoint, params=None):
    for tentativa in range(2):
        resp = requests.get(
            f'{_BASE}{endpoint}',
            headers={'Authorization': f'Bearer {_token["access"]}'},
            params=params,
            timeout=30,
        )
        if resp.status_code == 401 and tentativa == 0:
            renovar_token()
            continue
        resp.raise_for_status()
        return resp.json()
    raise RuntimeError(f'Falha na requisição ML: {endpoint}')


# ---------- utilitários ----------

def _detectar_tipo(logistic_type):
    if logistic_type == 'self_service':
        return 'flex'
    if logistic_type == 'fulfillment':
        return 'full'
    return 'padrao'


def _net_received_por_order(order_id):
    """
    Busca net_received_amount de um order_id específico via /collections/search.
    Retorna float ou None se não encontrado.
    """
    try:
        resultado = _get('/collections/search', params={'order_id': str(order_id), 'status': 'approved'})
        for item in resultado.get('results', []):
            col = item.get('collection', item)
            net = col.get('net_received_amount')
            if net is not None:
                return round(float(net), 2)
    except Exception:
        pass
    return None


# ---------- interface pública ----------

def obter_vliquido(num_pedido_ecommerce, taxa_fixa_flex=None, **kwargs):
    """
    Contrato padrão das plataformas.
    Retorna dict com: v_liquido, plataforma, canal, v_liquido_estimado.

    Estratégia:
      1. Resolve num_pedido como pack_id → lista de order_ids (ou usa direto)
      2. Para cada order_id: detecta logistic_type
         - Flex: total_amount − taxa_fixa_flex  (sem chamada de collections)
         - Full/Padrão: /collections/search?order_id → net_received_amount
    """
    if taxa_fixa_flex is None:
        taxa_fixa_flex = float(os.getenv('ML_TAXA_FIXA_FLEX', 14.99))

    num = str(num_pedido_ecommerce)

    # Tenta resolver como pack primeiro
    try:
        pack = _get(f'/packs/{num}')
        order_ids = [str(o['id']) for o in pack.get('orders', [])]
    except Exception:
        order_ids = []

    if not order_ids:
        order_ids = [num]

    v_total = 0.0
    tipo_final = 'padrao'

    for order_id in order_ids:
        try:
            order = _get(f'/orders/{order_id}')
        except Exception:
            continue

        tipo = _detectar_tipo((order.get('shipping') or {}).get('logistic_type', ''))
        if order_ids.index(order_id) == 0:
            tipo_final = tipo

        if tipo == 'flex':
            v_total += round(float(order.get('total_amount') or 0) - taxa_fixa_flex, 2)
        else:
            net = _net_received_por_order(order_id)
            if net is not None:
                v_total += net

    return {
        'v_liquido':          round(v_total, 2) if v_total else None,
        'plataforma':         _PLATAFORMA_MAP[tipo_final],
        'canal':              'E-commerce',
        'v_liquido_estimado': False,
    }
