"""
Pipeline de margens LBG — modo incremental.
Processa apenas pedidos novos (desde última execução) + reconcilia Shopee pendentes.
"""
import yaml
import os
import time
from decimal import Decimal

from src.erp.olist import buscar_pedidos, buscar_detalhe_pedido, buscar_nota_fiscal
from src.detector_plataforma import detectar
from src.calculator import calcular_margem
from src.custos import buscar_custo, buscar_embalagem
from src.database import (
    criar_tabelas, upsert_pedidos, buscar_ids_por_data,
    buscar_shopee_pendentes_recentes, atualizar_shopee_reconciliado,
    buscar_shopee_nulos, atualizar_shopee_estimado,
)

_TAXAS_PATH = os.path.join(os.path.dirname(__file__), '..', 'config', 'taxas.yaml')


def _carregar_taxas():
    with open(_TAXAS_PATH, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


# ---------- distribuição proporcional ----------

def _deduplicar_itens(itens):
    agrupados = {}
    for item in itens:
        chave = item['sku']
        if chave in agrupados:
            agrupados[chave]['quantidade'] += item['quantidade']
        else:
            agrupados[chave] = dict(item)
    return list(agrupados.values())


def _distribuir_proporcional(item, todos_itens, total, arredondar=2):
    if not total:
        return round(item['valor_unitario'] * item['quantidade'], arredondar)
    peso_total = sum(i['valor_unitario'] * i['quantidade'] for i in todos_itens)
    if not peso_total:
        return 0.0
    peso_item = item['valor_unitario'] * item['quantidade']
    return round(float(Decimal(str(total)) * Decimal(str(peso_item)) / Decimal(str(peso_total))), arredondar)


# ---------- estimativa Shopee para pedidos em trânsito ----------

def _estimar_vliquido_shopee(plataforma, v_bruto, taxas):
    """
    Calcula V.LIQUIDO estimado para pedidos Shopee ainda em trânsito.
    Usa shopee.taxa_comissao do taxas.yaml. Deduz taxa_fixa se Shopee Flex.
    Retorna float.
    """
    taxa_comissao = taxas.get('shopee', {}).get('taxa_comissao', 0.10)
    v_est = round(v_bruto * (1 - taxa_comissao), 2)
    if plataforma == 'Shopee Flex':
        taxa_flex = taxas.get('shopee_flex', {}).get('taxa_fixa', 9.99)
        v_est = round(v_est - taxa_flex, 2)
    return v_est


# ---------- obter V.LIQUIDO por plataforma ----------

def _obter_vliquido(plataforma_info, detalhe, taxas, v_bruto_total=None):
    plataforma = plataforma_info['plataforma']
    num_ec = detalhe.get('numero_ecommerce', '')

    if 'Mercado Livre' in plataforma:
        from src.platforms.mercado_livre import obter_vliquido as ml_vliq
        taxa_flex = taxas.get('mercado_livre_flex', {}).get('taxa_fixa', 14.99)
        return ml_vliq(num_ec, taxa_fixa_flex=taxa_flex)

    if plataforma == 'LBG':
        return {
            'v_liquido': detalhe.get('total_pedido', 0.0),
            'v_liquido_estimado': False,
            'plataforma': plataforma_info['plataforma'],
            'canal': plataforma_info['canal'],
        }

    if 'Shopee' in plataforma:
        from src.platforms.shopee import obter_vliquido as shopee_vliq
        taxa_flex = taxas.get('shopee_flex', {}).get('taxa_fixa', 9.99)
        resultado = shopee_vliq(num_ec, taxa_fixa_flex=taxa_flex)

        # Se pedido em trânsito, calcula estimativa com v_bruto
        if resultado.get('aguardando_escrow') and v_bruto_total:
            v_est = _estimar_vliquido_shopee(resultado['plataforma'], v_bruto_total, taxas)
            resultado['v_liquido'] = v_est
            resultado['v_liquido_estimado'] = True

        return resultado

    return {'v_liquido': None, 'v_liquido_estimado': False,
            'plataforma': plataforma_info['plataforma'], 'canal': plataforma_info['canal']}


# ---------- processamento de um pedido ----------

def processar_pedido(id_erp, taxas):
    detalhe = buscar_detalhe_pedido(id_erp)

    vnf_por_sku = {}
    if detalhe.get('id_nota_fiscal'):
        try:
            nf = buscar_nota_fiscal(detalhe['id_nota_fiscal'])
            vnf_por_sku = nf.get('valores_por_sku', {})
        except Exception:
            pass

    plataforma_info = detectar(detalhe)
    itens = _deduplicar_itens(detalhe.get('itens', []))
    v_bruto_total = detalhe.get('total_pedido', 0)

    vliq_info = _obter_vliquido(plataforma_info, detalhe, taxas, v_bruto_total=v_bruto_total)
    v_liquido_total = vliq_info.get('v_liquido')

    linhas = []
    for item in itens:
        sku = item['sku']
        qtd = item['quantidade']
        v_nf_unit = vnf_por_sku.get(sku, item['valor_unitario'])
        v_nf    = round(v_nf_unit * qtd, 2)
        v_bruto = _distribuir_proporcional(item, itens, v_bruto_total)
        v_liq   = _distribuir_proporcional(item, itens, v_liquido_total) if v_liquido_total else None

        margem = calcular_margem(
            v_liquido=v_liq or 0,
            v_nf=v_nf,
            custo_unitario=buscar_custo(sku),
            custo_embalagem_unitario=buscar_embalagem(sku),
            quantidade=qtd,
            taxas=taxas,
        ) if v_liq else {
            'impostos':      round(v_nf * taxas['impostos'], 2),
            'comissao':      None,
            'embalagem':     round(buscar_embalagem(sku) * qtd, 2),
            'custo_produto': round(buscar_custo(sku) * qtd, 2),
            'margem_rs':     None,
            'margem_pct':    None,
        }

        linhas.append({
            'data_venda':           detalhe['data_pedido'],
            'id_erp':               detalhe['id_erp'],
            'num_nf':               detalhe['num_nf'],
            'num_pedido_ecommerce': detalhe['numero_ecommerce'],
            'cliente':              detalhe['cliente'],
            'sku':                  sku,
            'v_bruto':              v_bruto,
            'quantidade':           qtd,
            'ecommerce':            detalhe['ecommerce'],
            'v_nf':                 v_nf,
            'data_emissao':         detalhe['data_emissao'],
            'uf':                   detalhe['uf'],
            'situacao':             detalhe['situacao'],
            'v_liquido':            v_liq,
            'v_liquido_estimado':   1 if vliq_info.get('v_liquido_estimado') else 0,
            'plataforma':           vliq_info.get('plataforma', plataforma_info['plataforma']),
            'canal':                vliq_info.get('canal', plataforma_info['canal']),
            **margem,
            'status': 'ATIVO',
        })

    return linhas


# ---------- reconciliação Shopee pendentes ----------

def _reconciliar_shopee_pendentes(taxas):
    """
    Verifica pedidos Shopee pendentes em dois grupos:
    - estimados (v_liquido_estimado=1): substitui pelo escrow real se COMPLETED
    - travados (v_liquido=null, v_liquido_estimado=0): grava estimativa ou escrow real
    Retorna número de pedidos atualizados.
    """
    from src.platforms.shopee import obter_vliquido as shopee_vliq

    pendentes = buscar_shopee_pendentes_recentes(dias=45)
    nulos = buscar_shopee_nulos(dias=60)

    # Dedup por (id_erp, sku) — pendentes têm prioridade
    vistos = {(r['id_erp'], r['sku']): 'pendente' for r in pendentes}
    nulos_novos = [r for r in nulos if (r['id_erp'], r['sku']) not in vistos]
    for r in nulos_novos:
        vistos[(r['id_erp'], r['sku'])] = 'nulo'

    todos = pendentes + nulos_novos
    if not todos:
        return 0

    print(f'  [Shopee reconciliação] {len(pendentes)} estimados, {len(nulos_novos)} travados para verificar...')
    atualizados = 0
    taxa_flex = taxas.get('shopee_flex', {}).get('taxa_fixa', 9.99)

    for p in todos:
        tipo = vistos[(p['id_erp'], p['sku'])]
        resultado = shopee_vliq(p['num_pedido_ecommerce'], taxa_fixa_flex=taxa_flex)

        if resultado.get('v_liquido') is not None and not resultado.get('aguardando_escrow'):
            # Escrow real disponível → reconciliar definitivamente (remove estimativa)
            v_liq = resultado['v_liquido']
            margem = calcular_margem(
                v_liquido=v_liq,
                v_nf=p.get('v_nf', 0),
                custo_unitario=buscar_custo(p['sku']),
                custo_embalagem_unitario=buscar_embalagem(p['sku']),
                quantidade=p['quantidade'],
                taxas=taxas,
            )
            atualizar_shopee_reconciliado(
                id_erp=p['id_erp'],
                sku=p['sku'],
                v_liquido=v_liq,
                plataforma=resultado['plataforma'],
                margem=margem,
            )
            atualizados += 1

        elif tipo == 'nulo' and resultado.get('aguardando_escrow'):
            # Pedido em trânsito sem nenhuma estimativa → calcular e gravar
            v_bruto = p.get('v_bruto') or 0
            if v_bruto:
                plataforma = resultado.get('plataforma') or p.get('plataforma', 'Shopee')
                v_est = _estimar_vliquido_shopee(plataforma, v_bruto, taxas)
                margem = calcular_margem(
                    v_liquido=v_est,
                    v_nf=p.get('v_nf', 0),
                    custo_unitario=buscar_custo(p['sku']),
                    custo_embalagem_unitario=buscar_embalagem(p['sku']),
                    quantidade=p['quantidade'],
                    taxas=taxas,
                )
                atualizar_shopee_estimado(
                    id_erp=p['id_erp'],
                    sku=p['sku'],
                    v_liquido_est=v_est,
                    plataforma=plataforma,
                    margem=margem,
                )
                atualizados += 1

    if atualizados:
        print(f'  [Shopee reconciliação] {atualizados} pedidos atualizados.')

    return atualizados


# ---------- entrada principal ----------

def executar_pipeline(data_iso, reconciliar=True):
    """
    Importa pedidos faturados em data_iso e reconcilia Shopee pendentes.
    data_iso: 'YYYY-MM-DD'
    """
    from datetime import datetime as _dt
    criar_tabelas()
    taxas = _carregar_taxas()

    # Converte ISO → DD/MM/YYYY para Tiny API
    data_ddmmyyyy = _dt.strptime(data_iso, '%Y-%m-%d').strftime('%d/%m/%Y')

    # --- Fase 1: pedidos novos do Tiny ---
    print(f'Buscando pedidos de {data_ddmmyyyy}...')
    pedidos = buscar_pedidos(data_ddmmyyyy, data_ddmmyyyy)
    print(f'  {len(pedidos)} pedidos encontrados')

    # Verifica apenas IDs do dia — muito mais eficiente que buscar todos
    ids_existentes = buscar_ids_por_data(data_iso)
    pedidos_novos = [p for p in pedidos if p['id_erp'] not in ids_existentes]
    pulados = len(pedidos) - len(pedidos_novos)
    if pulados:
        print(f'  {pulados} já processados — pulando. {len(pedidos_novos)} novos.')

    # --- Fase 2+3: processar pedidos novos ---
    todas_linhas = []
    erros = []

    if pedidos_novos:
        print(f'Processando {len(pedidos_novos)} pedidos novos...')
        for i, p in enumerate(pedidos_novos, 1):
            try:
                linhas = processar_pedido(p['id_erp'], taxas)
                todas_linhas.extend(linhas)
                if i % 10 == 0:
                    print(f'  Processados {i}/{len(pedidos_novos)}...')
                time.sleep(1.2)
            except Exception as e:
                erros.append({'id_erp': p['id_erp'], 'erro': str(e)})
                print(f'  ERRO pedido {p["id_erp"]}: {e}')

        gravados = upsert_pedidos(todas_linhas)
        print(f'  {gravados} linhas gravadas, {len(erros)} erros')
    else:
        gravados = 0
        print('  Nenhum pedido novo.')

    # --- Fase 4: reconciliação Shopee pendentes ---
    reconciliados = 0
    if reconciliar:
        print('Reconciliando Shopee pendentes...')
        reconciliados = _reconciliar_shopee_pendentes(taxas)
        if reconciliados == 0:
            print('  Nenhuma atualização.')

    return {
        'pedidos_encontrados': len(pedidos),
        'pedidos_novos':       len(pedidos_novos),
        'linhas_gravadas':     gravados,
        'shopee_reconciliados': reconciliados,
        'erros':               len(erros),
        'detalhes_erros':      erros,
    }
