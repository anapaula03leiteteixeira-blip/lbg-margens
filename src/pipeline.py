import yaml
import os
import time
from decimal import Decimal

from src.erp.olist import buscar_pedidos, buscar_detalhe_pedido, buscar_nota_fiscal
from src.detector_plataforma import detectar
from src.calculator import calcular_margem
from src.custos import buscar_custo, buscar_embalagem
from src.database import criar_tabelas, upsert_pedidos

_TAXAS_PATH = os.path.join(os.path.dirname(__file__), '..', 'config', 'taxas.yaml')


def _carregar_taxas():
    with open(_TAXAS_PATH, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def _deduplicar_itens(itens):
    """Agrupa itens com mesmo SKU e valor_unitario, somando quantidades."""
    agrupados = {}
    for item in itens:
        chave = (item['sku'], item['valor_unitario'])
        if chave in agrupados:
            agrupados[chave]['quantidade'] += item['quantidade']
        else:
            agrupados[chave] = dict(item)
    return list(agrupados.values())


def _distribuir_vbruto(item, todos_itens, total_pedido):
    """
    Distribui total_pedido proporcionalmente pelo peso de cada item.
    Peso = valor_unitario × quantidade.
    """
    if not total_pedido:
        return round(item['valor_unitario'] * item['quantidade'], 2)

    peso_total = sum(i['valor_unitario'] * i['quantidade'] for i in todos_itens)
    if peso_total == 0:
        return 0.0

    peso_item = item['valor_unitario'] * item['quantidade']
    return round(float(Decimal(str(total_pedido)) * Decimal(str(peso_item)) / Decimal(str(peso_total))), 2)


def _distribuir_vliquido(item, todos_itens, v_liquido_total):
    """Distribui V.LIQUIDO total do pedido proporcionalmente, igual ao V.BRUTO."""
    if not v_liquido_total:
        return None

    peso_total = sum(i['valor_unitario'] * i['quantidade'] for i in todos_itens)
    if peso_total == 0:
        return None

    peso_item = item['valor_unitario'] * item['quantidade']
    return round(float(Decimal(str(v_liquido_total)) * Decimal(str(peso_item)) / Decimal(str(peso_total))), 2)


def _obter_vliquido(plataforma_info, detalhe):
    """Chama o conector certo para obter V.LIQUIDO. Retorna dict com v_liquido e flags."""
    plataforma = plataforma_info['plataforma']
    num_ec = detalhe.get('numero_ecommerce', '')

    if 'Mercado Livre' in plataforma:
        from src.platforms.mercado_livre import obter_vliquido as ml_vliq
        return ml_vliq(num_ec)

    if plataforma == 'LBG':
        return {'v_liquido': detalhe.get('total_pedido', 0.0), 'v_liquido_estimado': False}

    # Plataformas ainda sem conector — retorna None (será estimado ou deixado em branco)
    return {'v_liquido': None, 'v_liquido_estimado': False}


def processar_pedido(id_erp, taxas):
    """
    Processa um único pedido e retorna lista de linhas (uma por SKU).
    Útil para reprocessar pedidos individuais.
    """
    detalhe = buscar_detalhe_pedido(id_erp)

    vnf_por_sku = {}
    if detalhe.get('id_nota_fiscal'):
        try:
            nf = buscar_nota_fiscal(detalhe['id_nota_fiscal'])
            vnf_por_sku = nf.get('valores_por_sku', {})
        except Exception:
            pass

    plataforma_info = detectar(detalhe)
    vliq_info = _obter_vliquido(plataforma_info, detalhe)

    itens = _deduplicar_itens(detalhe.get('itens', []))
    v_liquido_total = vliq_info.get('v_liquido')

    linhas = []
    for item in itens:
        sku = item['sku']
        qtd = item['quantidade']
        v_nf_unit = vnf_por_sku.get(sku, item['valor_unitario'])
        v_nf = round(v_nf_unit * qtd, 2)
        v_bruto = _distribuir_vbruto(item, itens, detalhe.get('total_pedido', 0))
        v_liq_item = _distribuir_vliquido(item, itens, v_liquido_total)

        margem = calcular_margem(
            v_liquido=v_liq_item or 0,
            v_nf=v_nf,
            custo_unitario=buscar_custo(sku),
            custo_embalagem_unitario=buscar_embalagem(sku),
            quantidade=qtd,
            taxas=taxas,
        ) if v_liq_item else {
            'impostos': round(v_nf * taxas['impostos'], 2),
            'comissao': None,
            'embalagem': round(buscar_embalagem(sku) * qtd, 2),
            'custo_produto': round(buscar_custo(sku) * qtd, 2),
            'margem_rs': None,
            'margem_pct': None,
        }

        linhas.append({
            'data_venda': detalhe['data_pedido'],
            'id_erp': detalhe['id_erp'],
            'num_nf': detalhe['num_nf'],
            'num_pedido_ecommerce': detalhe['numero_ecommerce'],
            'cliente': detalhe['cliente'],
            'sku': sku,
            'v_bruto': v_bruto,
            'quantidade': qtd,
            'ecommerce': detalhe['ecommerce'],
            'v_nf': v_nf,
            'data_emissao': detalhe['data_emissao'],
            'uf': detalhe['uf'],
            'situacao': detalhe['situacao'],
            'v_liquido': v_liq_item,
            'v_liquido_estimado': 1 if vliq_info.get('v_liquido_estimado') else 0,
            'plataforma': plataforma_info['plataforma'],
            'canal': plataforma_info['canal'],
            **margem,
            'status': 'ATIVO',
        })

    return linhas


def executar_pipeline(data_inicio, data_fim):
    """
    Importa todos os pedidos faturados no período para o banco de dados.
    data_inicio / data_fim: 'DD/MM/YYYY'

    Retorna dict com resumo da execução.
    """
    criar_tabelas()
    taxas = _carregar_taxas()

    print(f'Buscando pedidos de {data_inicio} a {data_fim}...')
    pedidos = buscar_pedidos(data_inicio, data_fim)
    print(f'  {len(pedidos)} pedidos encontrados')

    todas_linhas = []
    erros = []

    for i, p in enumerate(pedidos, 1):
        try:
            linhas = processar_pedido(p['id_erp'], taxas)
            todas_linhas.extend(linhas)
            if i % 10 == 0:
                print(f'  Processados {i}/{len(pedidos)}...')
            time.sleep(0.5)
        except Exception as e:
            erros.append({'id_erp': p['id_erp'], 'erro': str(e)})
            print(f'  ERRO pedido {p["id_erp"]}: {e}')

    gravados = upsert_pedidos(todas_linhas)

    resumo = {
        'pedidos_encontrados': len(pedidos),
        'linhas_gravadas': gravados,
        'erros': len(erros),
        'detalhes_erros': erros,
    }
    print(f'\nConcluído: {gravados} linhas gravadas, {len(erros)} erros')
    return resumo
