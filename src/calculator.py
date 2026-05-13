from decimal import Decimal, ROUND_HALF_UP


def _d(value):
    return Decimal(str(value or 0))


def _arredondar(value):
    return float(_d(value).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))


def calcular_margem(v_liquido, v_nf, custo_unitario, custo_embalagem_unitario, quantidade, taxas):
    """
    Retorna dict com todos os campos calculados de margem.
    Denominador de margem_pct é CUSTO PRODUTO (retorno sobre custo).
    """
    vl = _d(v_liquido)
    vn = _d(v_nf)
    qtd = _d(quantidade)
    custo_unit = _d(custo_unitario)
    emb_unit = _d(custo_embalagem_unitario)

    impostos = vn * _d(taxas['impostos'])
    comissao = vl * _d(taxas['comissao'])
    embalagem = emb_unit * qtd
    custo_produto = custo_unit * qtd
    margem_rs = vl - impostos - comissao - embalagem - custo_produto
    margem_pct = (margem_rs / custo_produto) if custo_produto > 0 else _d(0)

    return {
        'impostos': _arredondar(impostos),
        'comissao': _arredondar(comissao),
        'embalagem': _arredondar(embalagem),
        'custo_produto': _arredondar(custo_produto),
        'margem_rs': _arredondar(margem_rs),
        'margem_pct': _arredondar(margem_pct),
    }


def calcular_custo_devolucao(custo_produto, impostos, condicao, taxa_avaria):
    """
    condicao: 'COM AVARIAS' ou 'SEM AVARIAS'
    """
    cp = _d(custo_produto)
    imp = _d(impostos)
    taxa = _d(taxa_avaria)

    if condicao == 'COM AVARIAS':
        return _arredondar(cp + imp + cp * taxa)
    elif condicao == 'SEM AVARIAS':
        return _arredondar(cp * taxa)
    return 0.0
