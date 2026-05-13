from unittest.mock import patch, MagicMock
from src.pipeline import (
    _deduplicar_itens,
    _distribuir_vbruto,
    _distribuir_vliquido,
    processar_pedido,
)

TAXAS = {'impostos': 0.13, 'comissao': 0.04}

DETALHE_ML = {
    'id_erp': '123',
    'num_nf': 'NF001',
    'numero_ecommerce': '2000111222',
    'cliente': 'Ana Paula',
    'data_pedido': '01/05/2026',
    'data_emissao': '01/05/2026',
    'uf': 'SP',
    'situacao': 'Faturado',
    'ecommerce': 'Mercado Livre',
    'forma_pagamento': 'Mercado Pago',
    'total_pedido': 200.0,
    'id_nota_fiscal': '456',
    'marcadores': [],
    'itens': [
        {'sku': 'SKU-A', 'descricao': 'Produto A', 'quantidade': 2.0, 'valor_unitario': 100.0},
    ],
}


# ---------- deduplicar ----------

def test_deduplicar_agrupa_sku_igual():
    itens = [
        {'sku': 'A', 'valor_unitario': 10.0, 'quantidade': 2},
        {'sku': 'A', 'valor_unitario': 10.0, 'quantidade': 3},
    ]
    resultado = _deduplicar_itens(itens)
    assert len(resultado) == 1
    assert resultado[0]['quantidade'] == 5


def test_deduplicar_mantem_skus_diferentes():
    itens = [
        {'sku': 'A', 'valor_unitario': 10.0, 'quantidade': 1},
        {'sku': 'B', 'valor_unitario': 20.0, 'quantidade': 1},
    ]
    assert len(_deduplicar_itens(itens)) == 2


def test_deduplicar_mesmo_sku_preco_diferente_nao_agrupa():
    itens = [
        {'sku': 'A', 'valor_unitario': 10.0, 'quantidade': 1},
        {'sku': 'A', 'valor_unitario': 15.0, 'quantidade': 1},
    ]
    assert len(_deduplicar_itens(itens)) == 2


# ---------- distribuição de V.BRUTO ----------

def test_vbruto_pedido_unico_sku_igual_total():
    item = {'sku': 'A', 'valor_unitario': 100.0, 'quantidade': 2}
    resultado = _distribuir_vbruto(item, [item], 200.0)
    assert resultado == 200.0


def test_vbruto_dois_skus_proporcional():
    item_a = {'sku': 'A', 'valor_unitario': 100.0, 'quantidade': 1}
    item_b = {'sku': 'B', 'valor_unitario': 100.0, 'quantidade': 1}
    todos = [item_a, item_b]
    assert _distribuir_vbruto(item_a, todos, 240.0) == 120.0
    assert _distribuir_vbruto(item_b, todos, 240.0) == 120.0


def test_vbruto_fallback_sem_total():
    item = {'sku': 'A', 'valor_unitario': 50.0, 'quantidade': 3}
    resultado = _distribuir_vbruto(item, [item], 0)
    assert resultado == 150.0


# ---------- distribuição de V.LIQUIDO ----------

def test_vliquido_proporcional():
    item_a = {'sku': 'A', 'valor_unitario': 100.0, 'quantidade': 1}
    item_b = {'sku': 'B', 'valor_unitario': 100.0, 'quantidade': 1}
    todos = [item_a, item_b]
    assert _distribuir_vliquido(item_a, todos, 180.0) == 90.0


def test_vliquido_none_quando_total_none():
    item = {'sku': 'A', 'valor_unitario': 100.0, 'quantidade': 1}
    assert _distribuir_vliquido(item, [item], None) is None


# ---------- processar_pedido ----------

def test_processar_pedido_ml_gera_uma_linha_por_sku():
    with patch('src.pipeline.buscar_detalhe_pedido', return_value=DETALHE_ML), \
         patch('src.pipeline.buscar_nota_fiscal', return_value={'valores_por_sku': {'SKU-A': 90.0}}), \
         patch('src.pipeline.buscar_custo', return_value=30.0), \
         patch('src.pipeline.buscar_embalagem', return_value=2.0), \
         patch('src.pipeline.detectar', return_value={'plataforma': 'Mercado Livre', 'canal': 'E-commerce'}), \
         patch('src.pipeline._obter_vliquido', return_value={'v_liquido': 180.0, 'v_liquido_estimado': False}):

        linhas = processar_pedido('123', TAXAS)

    assert len(linhas) == 1
    linha = linhas[0]
    assert linha['sku'] == 'SKU-A'
    assert linha['plataforma'] == 'Mercado Livre'
    assert linha['canal'] == 'E-commerce'
    assert linha['v_bruto'] == 200.0
    assert linha['v_liquido'] == 180.0
    assert linha['v_nf'] == 180.0  # 90.0 × 2
    assert linha['impostos'] == round(180.0 * 0.13, 2)
    assert linha['comissao'] == round(180.0 * 0.04, 2)
