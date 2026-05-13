import json
import os

_CUSTOS_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'custos.json')
_cache = None


def _carregar():
    global _cache
    if _cache is not None:
        return _cache
    if not os.path.exists(_CUSTOS_PATH):
        _cache = {}
        return _cache
    with open(_CUSTOS_PATH, 'r', encoding='utf-8') as f:
        dados = json.load(f)
    # Remove chaves de instrução (começam com _)
    _cache = {k: v for k, v in dados.items() if not k.startswith('_')}
    return _cache


def buscar_custo(sku):
    """Retorna custo unitário do SKU. Retorna 0.0 se não encontrado."""
    dados = _carregar()
    return float(dados.get(str(sku), {}).get('custo_unitario', 0.0))


def buscar_embalagem(sku):
    """Retorna custo de embalagem unitário do SKU. Retorna 0.0 se não encontrado."""
    dados = _carregar()
    return float(dados.get(str(sku), {}).get('embalagem', 0.0))


def recarregar():
    """Força releitura do arquivo (usar após atualizar custos.json)."""
    global _cache
    _cache = None
