import os
import re
import requests
from dotenv import load_dotenv

load_dotenv()

_BASE = 'https://api.mercadolibre.com'
_APP_ID = os.getenv('ML_APP_ID')
_CLIENT_SECRET = os.getenv('ML_CLIENT_SECRET')
_SELLER_ID = os.getenv('ML_SELLER_ID')

_token = {
    'access': os.getenv('ML_ACCESS_TOKEN'),
    'refresh': os.getenv('ML_REFRESH_TOKEN'),
}


# ---------- autenticação ----------

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
    _atualizar_env('ML_ACCESS_TOKEN', _token['access'])
    _atualizar_env('ML_REFRESH_TOKEN', _token['refresh'])


def _atualizar_env(chave, valor):
    env_path = os.path.join(os.path.dirname(__file__), '..', '..', '.env')
    with open(env_path, 'r', encoding='utf-8') as f:
        conteudo = f.read()
    conteudo = re.sub(rf'^{chave}=.*$', f'{chave}={valor}', conteudo, flags=re.MULTILINE)
    with open(env_path, 'w', encoding='utf-8') as f:
        f.write(conteudo)


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


# ---------- lógica de negócio ----------

def _resolver_order_ids(num_pedido):
    """Pack ID → lista de order IDs. Order ID regular → lista com ele mesmo."""
    try:
        pack = _get(f'/packs/{num_pedido}')
        orders = pack.get('orders', [])
        if orders:
            return [str(o['id']) for o in orders]
    except Exception:
        pass
    return [str(num_pedido)]


def _detectar_tipo(order):
    """Retorna 'flex', 'full' ou 'padrao'."""
    logistic = (order.get('shipping') or {}).get('logistic_type', '')
    if logistic == 'self_service':
        return 'flex'
    if logistic == 'fulfillment':
        return 'full'
    return 'padrao'


def _obter_net_received(order_id):
    """Retorna net_received_amount da cobrança do pedido."""
    resultado = _get('/collections/search', params={'order_id': order_id})
    resultados = resultado.get('results', [])
    total = 0.0
    for item in resultados:
        colecao = item.get('collection', item)
        total += float(colecao.get('net_received_amount', 0) or 0)
    return total


# ---------- interface pública ----------

def obter_vliquido(num_pedido_ecommerce, taxa_fixa_flex=None):
    """
    Retorna dict com v_liquido, plataforma, v_liquido_estimado.
    Chame esta função passando o numeroPedidoEcommerce do Tiny.
    """
    if taxa_fixa_flex is None:
        taxa_fixa_flex = float(os.getenv('ML_TAXA_FIXA_FLEX', 14.90))

    order_ids = _resolver_order_ids(str(num_pedido_ecommerce))
    v_liquido_total = 0.0
    tipo = 'padrao'

    for order_id in order_ids:
        order = _get(f'/orders/{order_id}')
        tipo = _detectar_tipo(order)

        if tipo == 'flex':
            total_order = float((order.get('total_amount') or 0))
            v_liquido_total += total_order - taxa_fixa_flex
        else:
            v_liquido_total += _obter_net_received(order_id)

    plataforma_map = {
        'flex': 'Mercado Livre Flex',
        'full': 'Mercado Livre Full',
        'padrao': 'Mercado Livre',
    }

    return {
        'v_liquido': round(v_liquido_total, 2),
        'plataforma': plataforma_map[tipo],
        'canal': 'E-commerce',
        'v_liquido_estimado': False,
    }
