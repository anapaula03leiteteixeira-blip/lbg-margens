import pytest
from src.calculator import calcular_margem, calcular_custo_devolucao

TAXAS = {'impostos': 0.13, 'comissao': 0.04}


def test_impostos_13_pct_do_vnf():
    resultado = calcular_margem(
        v_liquido=200, v_nf=180, custo_unitario=50, custo_embalagem_unitario=0, quantidade=1, taxas=TAXAS
    )
    assert resultado['impostos'] == round(180 * 0.13, 2)


def test_comissao_4_pct_do_vliquido():
    resultado = calcular_margem(
        v_liquido=200, v_nf=180, custo_unitario=50, custo_embalagem_unitario=0, quantidade=1, taxas=TAXAS
    )
    assert resultado['comissao'] == round(200 * 0.04, 2)


def test_margem_rs_formula_completa():
    resultado = calcular_margem(
        v_liquido=200, v_nf=180, custo_unitario=50, custo_embalagem_unitario=5, quantidade=2, taxas=TAXAS
    )
    impostos = round(180 * 0.13, 2)
    comissao = round(200 * 0.04, 2)
    embalagem = round(5 * 2, 2)
    custo = round(50 * 2, 2)
    esperado = round(200 - impostos - comissao - embalagem - custo, 2)
    assert resultado['margem_rs'] == esperado


def test_margem_pct_denominador_custo_produto():
    resultado = calcular_margem(
        v_liquido=200, v_nf=180, custo_unitario=50, custo_embalagem_unitario=0, quantidade=2, taxas=TAXAS
    )
    custo = 50 * 2
    assert resultado['margem_pct'] == round(resultado['margem_rs'] / custo, 2)


def test_margem_pct_zero_quando_custo_zero():
    resultado = calcular_margem(
        v_liquido=200, v_nf=180, custo_unitario=0, custo_embalagem_unitario=0, quantidade=1, taxas=TAXAS
    )
    assert resultado['margem_pct'] == 0.0


def test_embalagem_multiplicada_por_quantidade():
    resultado = calcular_margem(
        v_liquido=200, v_nf=180, custo_unitario=50, custo_embalagem_unitario=3, quantidade=4, taxas=TAXAS
    )
    assert resultado['embalagem'] == round(3 * 4, 2)


def test_devolucao_com_avarias():
    resultado = calcular_custo_devolucao(
        custo_produto=100, impostos=23, condicao='COM AVARIAS', taxa_avaria=0.10
    )
    assert resultado == round(100 + 23 + 100 * 0.10, 2)


def test_devolucao_sem_avarias():
    resultado = calcular_custo_devolucao(
        custo_produto=100, impostos=23, condicao='SEM AVARIAS', taxa_avaria=0.10
    )
    assert resultado == round(100 * 0.10, 2)


def test_devolucao_condicao_invalida_retorna_zero():
    resultado = calcular_custo_devolucao(
        custo_produto=100, impostos=23, condicao='', taxa_avaria=0.10
    )
    assert resultado == 0.0
