import os
import time
import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = 'https://api.tiny.com.br/api2'
TOKEN = os.getenv('TINY_API_TOKEN')
_INTERVALO_REQUISICAO = 1.0  # segundos entre chamadas (max 60 req/min — margem de segurança)
_RETRY_ESPERA = 65            # segundos de espera ao ser bloqueado pela API
_MAX_RETRIES = 5


def _post(endpoint, params):
    payload = {'token': TOKEN, 'formato': 'JSON', **params}
    for tentativa in range(1, _MAX_RETRIES + 1):
        response = requests.post(f'{BASE_URL}/{endpoint}', data=payload, timeout=30)
        response.raise_for_status()
        data = response.json()
        retorno = data.get('retorno', {})
        if retorno.get('status') == 'Erro':
            erros = retorno.get('erros', [])
            msg = str(erros)
            if 'Bloqueada' in msg or 'bloqueada' in msg:
                if tentativa < _MAX_RETRIES:
                    print(f'  [rate limit] aguardando {_RETRY_ESPERA}s antes de tentar novamente ({tentativa}/{_MAX_RETRIES})...')
                    time.sleep(_RETRY_ESPERA)
                    continue
            raise ValueError(f'Tiny API erro em {endpoint}: {erros}')
        time.sleep(_INTERVALO_REQUISICAO)
        return retorno
    raise ValueError(f'Tiny API bloqueada em {endpoint} apos {_MAX_RETRIES} tentativas')


def _buscar_pedidos_situacao(data_inicio, data_fim, situacao):
    """Busca pedidos de uma situação específica, paginando até o fim."""
    todos = []
    pagina = 1

    while True:
        retorno = _post('pedidos.pesquisa.php', {
            'dataInicial': data_inicio,
            'dataFinal': data_fim,
            'situacao': situacao,
            'pagina': pagina,
        })

        pedidos_raw = retorno.get('pedidos', [])
        if not pedidos_raw:
            break

        for item in pedidos_raw:
            pedido = item.get('pedido', item)
            todos.append({
                'id_erp': str(pedido.get('id', '')),
                'numero_ecommerce': str(pedido.get('numero_ecommerce', '') or pedido.get('numeroPedidoEcommerce', '')),
                'data_pedido': pedido.get('data_pedido', ''),
                'cliente': pedido.get('nome', ''),
                'situacao': pedido.get('situacao', ''),
                'ecommerce': pedido.get('ecommerce', ''),
                'id_nota_fiscal': pedido.get('id_nota_fiscal', ''),
            })

        numero_paginas = int(retorno.get('numero_paginas', 1))
        if pagina >= numero_paginas:
            break
        pagina += 1
        time.sleep(_INTERVALO_REQUISICAO)

    return todos


def buscar_pedidos(data_inicio, data_fim, situacao=None):
    """
    Retorna pedidos faturados no período (Enviado + Entregue + Faturado).
    A Tiny evolui o status: Faturado → Enviado → Entregue, então buscamos
    as três situações para não perder pedidos já expedidos.
    data_inicio / data_fim: string 'DD/MM/YYYY'
    """
    if situacao is not None:
        return _buscar_pedidos_situacao(data_inicio, data_fim, situacao)

    vistos = set()
    todos = []
    for sit in ('Enviado', 'Entregue', 'Faturado'):
        for p in _buscar_pedidos_situacao(data_inicio, data_fim, sit):
            if p['id_erp'] not in vistos:
                vistos.add(p['id_erp'])
                todos.append(p)
        time.sleep(_INTERVALO_REQUISICAO)

    return todos


def buscar_detalhe_pedido(id_erp):
    """
    Retorna detalhes completos de um pedido, incluindo itens (SKUs).
    """
    retorno = _post('pedido.obter.php', {'id': id_erp})
    pedido = retorno.get('pedido', {})

    itens_raw = pedido.get('itens', [])
    itens = []
    for item_wrap in itens_raw:
        item = item_wrap.get('item', item_wrap)
        itens.append({
            'sku': str(item.get('codigo', '')),
            'descricao': item.get('descricao', ''),
            'quantidade': float(item.get('quantidade', 1)),
            'valor_unitario': float(item.get('valor_unitario', 0)),
        })

    marcadores = []
    for m in pedido.get('marcadores', []):
        inner = m.get('marcador', m)
        marcadores.append(str(inner.get('descricao', '')).lower())

    ecommerce_raw = pedido.get('ecommerce', '')
    if isinstance(ecommerce_raw, dict):
        ecommerce = ecommerce_raw.get('nomeEcommerce', '')
    else:
        ecommerce = str(ecommerce_raw or '')

    return {
        'id_erp': str(pedido.get('id', '')),
        'num_nf': str(pedido.get('numero_nota_fiscal', '') or ''),
        'numero_ecommerce': str(pedido.get('numero_ecommerce', '') or pedido.get('numeroPedidoEcommerce', '')),
        'cliente': (pedido.get('cliente') or {}).get('nome') or pedido.get('nome_contato', ''),
        'data_pedido': pedido.get('data_pedido', ''),
        'data_emissao': pedido.get('data_emissao', ''),
        'uf': (pedido.get('cliente') or {}).get('uf', ''),
        'situacao': pedido.get('situacao', ''),
        'ecommerce': ecommerce,
        'forma_pagamento': pedido.get('forma_pagamento', ''),
        'total_pedido': float(pedido.get('total_pedido', 0) or 0),
        'id_nota_fiscal': str(pedido.get('id_nota_fiscal', '') or ''),
        'marcadores': marcadores,
        'itens': itens,
    }


def buscar_nota_fiscal(id_nota_fiscal):
    """
    Retorna valor unitário por SKU da nota fiscal emitida (V.NF real).
    """
    retorno = _post('nota.fiscal.obter.php', {'id': id_nota_fiscal})
    nf = retorno.get('nota_fiscal', {})

    itens_raw = nf.get('itens', [])
    valores_por_sku = {}
    for item_wrap in itens_raw:
        item = item_wrap.get('item', item_wrap)
        sku = str(item.get('codigo', ''))
        if sku:
            valores_por_sku[sku] = float(item.get('valor_unitario', 0))

    return {
        'valor_nota': float(nf.get('valor', 0) or 0),
        'valores_por_sku': valores_por_sku,
    }
