"""
rodar.py — Executa o pipeline de margens da La Bella Griffe.

Uso:
  python rodar.py                              # D-1 + catch-up de até 7 dias (modo padrão)
  python rodar.py --desde 01/05/2026           # desde data específica até ontem
  python rodar.py --desde 01/05/2026 --ate 14/05/2026  # intervalo fixo
  python rodar.py --so-reconciliar             # apenas reconcilia Shopee pendentes
"""
import sys
import argparse
from dotenv import load_dotenv

load_dotenv()

from src.pipeline import executar_pipeline
from src.controle import datas_para_processar, registrar_execucao
from src.database import buscar_resumo


def _parse_args():
    parser = argparse.ArgumentParser(description='Pipeline de margens LBG')
    parser.add_argument('--desde', metavar='DD/MM/YYYY', help='Data de início')
    parser.add_argument('--ate',   metavar='DD/MM/YYYY', help='Data de fim (padrão: ontem)')
    parser.add_argument('--so-reconciliar', action='store_true', help='Só reconcilia Shopee pendentes')
    return parser.parse_args()


def mostrar_resumo_banco():
    resumo = buscar_resumo()
    print(f'\n=== BANCO DE DADOS (Supabase) ===')
    print(f'Total de linhas: {resumo["total"]}')

    print('\nPor plataforma:')
    for p in resumo['plataformas']:
        margem_str = (
            f'{round(p["margem_sum"] / p["margem_count"] * 100, 1)}%'
            if p['margem_count'] else '—'
        )
        print(
            f'  {p["plataforma"]}: {p["linhas"]} linhas'
            f' | V.Bruto R${round(p["v_bruto"], 2)}'
            f' | V.Líq R${round(p["v_liquido"], 2)}'
            f' | Margem {margem_str}'
        )

    print('\nEstimados (Shopee em trânsito):')
    print(f'  Estimados: {resumo["estimados"]} | Sem V.LIQUIDO: {resumo["sem_vliq"]}')


if __name__ == '__main__':
    args = _parse_args()

    # Modo só-reconciliar: não processa pedidos novos
    if args.so_reconciliar:
        print('Modo: somente reconciliação Shopee pendentes\n')
        from src.database import criar_tabelas
        from src.pipeline import _reconciliar_shopee_pendentes
        import yaml, os
        criar_tabelas()
        taxas_path = os.path.join(os.path.dirname(__file__), 'config', 'taxas.yaml')
        with open(taxas_path) as f:
            taxas = yaml.safe_load(f)
        n = _reconciliar_shopee_pendentes(taxas)
        print(f'\n{n} pedidos Shopee atualizados com valor real.')
        mostrar_resumo_banco()
        sys.exit(0)

    # Calcula lista de datas a processar
    datas = datas_para_processar(desde_arg=args.desde, ate_arg=args.ate)
    if not datas:
        print('Nenhuma data nova para processar.')
        mostrar_resumo_banco()
        sys.exit(0)

    modo = 'manual' if args.desde else 'automático'
    print(f'Modo {modo}: {datas[0]} → {datas[-1]} ({len(datas)} dia(s))\n')

    total_encontrados   = 0
    total_novos         = 0
    total_gravados      = 0
    total_reconciliados = 0
    total_erros         = 0
    todos_detalhes_erros = []

    for i, data_iso in enumerate(datas):
        # Reconcilia apenas na última data para não repetir a cada iteração
        reconciliar = (i == len(datas) - 1)
        print(f'[{i + 1}/{len(datas)}] {data_iso}...')

        resumo = executar_pipeline(data_iso, reconciliar=reconciliar)

        total_encontrados   += resumo['pedidos_encontrados']
        total_novos         += resumo['pedidos_novos']
        total_gravados      += resumo['linhas_gravadas']
        total_reconciliados += resumo['shopee_reconciliados']
        total_erros         += resumo['erros']
        todos_detalhes_erros.extend(resumo['detalhes_erros'])

        # Registra progresso após cada data (exceto em modo manual com --desde)
        if not args.desde:
            registrar_execucao(data_iso)

    print(f'\n=== RESUMO DA EXECUÇÃO ===')
    print(f'Datas processadas     : {len(datas)}')
    print(f'Pedidos encontrados   : {total_encontrados}')
    print(f'Pedidos novos         : {total_novos}')
    print(f'Linhas gravadas       : {total_gravados}')
    print(f'Shopee reconciliados  : {total_reconciliados}')
    print(f'Erros                 : {total_erros}')

    if todos_detalhes_erros:
        print('\nDetalhes dos erros:')
        for e in todos_detalhes_erros:
            print(f'  id_erp {e["id_erp"]}: {e["erro"]}')

    mostrar_resumo_banco()
