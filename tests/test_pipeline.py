from unittest.mock import patch, call
from src.pipeline import (
    _deduplicar_itens,
    _distribuir_proporcional,
    _reconciliar_shopee_pendentes,
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


def test_deduplicar_mesmo_sku_preco_diferente_agrupa():
    # Mesmo SKU com preço diferente é agrupado (unicidade por SKU no banco)
    itens = [
        {'sku': 'A', 'valor_unitario': 10.0, 'quantidade': 1},
        {'sku': 'A', 'valor_unitario': 15.0, 'quantidade': 1},
    ]
    resultado = _deduplicar_itens(itens)
    assert len(resultado) == 1
    assert resultado[0]['quantidade'] == 2


# ---------- distribuição proporcional ----------

def test_proporcional_pedido_unico_sku_igual_total():
    item = {'sku': 'A', 'valor_unitario': 100.0, 'quantidade': 2}
    resultado = _distribuir_proporcional(item, [item], 200.0)
    assert resultado == 200.0


def test_proporcional_dois_skus_proporcional():
    item_a = {'sku': 'A', 'valor_unitario': 100.0, 'quantidade': 1}
    item_b = {'sku': 'B', 'valor_unitario': 100.0, 'quantidade': 1}
    todos = [item_a, item_b]
    assert _distribuir_proporcional(item_a, todos, 240.0) == 120.0
    assert _distribuir_proporcional(item_b, todos, 240.0) == 120.0


def test_proporcional_fallback_quando_total_zero_ou_none():
    item = {'sku': 'A', 'valor_unitario': 50.0, 'quantidade': 3}
    assert _distribuir_proporcional(item, [item], 0) == 150.0
    assert _distribuir_proporcional(item, [item], None) == 150.0


def test_proporcional_vliquido_dois_skus():
    item_a = {'sku': 'A', 'valor_unitario': 100.0, 'quantidade': 1}
    item_b = {'sku': 'B', 'valor_unitario': 100.0, 'quantidade': 1}
    todos = [item_a, item_b]
    assert _distribuir_proporcional(item_a, todos, 180.0) == 90.0


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


# ---------- reconciliar Shopee ----------

TAXAS_COMPLETAS = {
    'impostos': 0.13,
    'comissao': 0.04,
    'shopee_flex': {'taxa_fixa': 9.99},
}

PENDENTE_SHOPEE = {
    'id_erp': '9001',
    'num_pedido_ecommerce': 'SHP123',
    'sku': 'SKU-B',
    'quantidade': 1.0,
    'v_nf': 100.0,
    'v_bruto': 110.0,
    'plataforma': 'Shopee',
    'canal': 'E-commerce',
}


def test_reconciliar_shopee_chama_atualizar_nao_upsert():
    """Garante que reconciliação usa atualizar_shopee_reconciliado (update cirúrgico),
    não upsert_pedidos (que sobrescreveria campos com None)."""
    vliq_resultado = {
        'v_liquido': 95.0,
        'plataforma': 'Shopee',
        'canal': 'E-commerce',
        'v_liquido_estimado': False,
        'aguardando_escrow': False,
    }

    with patch('src.pipeline.buscar_shopee_pendentes_recentes', return_value=[PENDENTE_SHOPEE]), \
         patch('src.platforms.shopee.obter_vliquido', return_value=vliq_resultado), \
         patch('src.pipeline.buscar_custo', return_value=40.0), \
         patch('src.pipeline.buscar_embalagem', return_value=3.0), \
         patch('src.pipeline.atualizar_shopee_reconciliado') as mock_atualizar, \
         patch('src.pipeline.upsert_pedidos') as mock_upsert:

        n = _reconciliar_shopee_pendentes(TAXAS_COMPLETAS)

    assert n == 1
    assert mock_upsert.call_count == 0, 'upsert_pedidos não deve ser chamado na reconciliação'
    assert mock_atualizar.call_count == 1
    kwargs = mock_atualizar.call_args.kwargs
    assert kwargs['id_erp'] == '9001'
    assert kwargs['sku'] == 'SKU-B'
    assert kwargs['v_liquido'] == 95.0
    assert kwargs['plataforma'] == 'Shopee'
    assert 'margem_rs' in kwargs['margem']


def test_reconciliar_shopee_sem_pendentes_retorna_zero():
    with patch('src.pipeline.buscar_shopee_pendentes_recentes', return_value=[]):
        assert _reconciliar_shopee_pendentes(TAXAS_COMPLETAS) == 0


def test_reconciliar_shopee_aguardando_escrow_nao_atualiza():
    """Pedido ainda em trânsito (aguardando_escrow=True) não deve ser atualizado."""
    vliq_em_transito = {
        'v_liquido': None,
        'plataforma': 'Shopee',
        'canal': 'E-commerce',
        'v_liquido_estimado': False,
        'aguardando_escrow': True,
    }

    with patch('src.pipeline.buscar_shopee_pendentes_recentes', return_value=[PENDENTE_SHOPEE]), \
         patch('src.platforms.shopee.obter_vliquido', return_value=vliq_em_transito), \
         patch('src.pipeline.atualizar_shopee_reconciliado') as mock_atualizar:

        n = _reconciliar_shopee_pendentes(TAXAS_COMPLETAS)

    assert n == 0
    assert mock_atualizar.call_count == 0
