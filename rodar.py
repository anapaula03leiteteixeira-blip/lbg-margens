"""
rodar.py — Executa o pipeline de margens da La Bella Griffe.
Uso: python rodar.py
"""
from dotenv import load_dotenv
load_dotenv()

from src.pipeline import executar_pipeline
from src.database import get_conn

DATA_INICIO = '01/05/2026'
DATA_FIM    = '12/05/2026'


def mostrar_resumo_banco():
    with get_conn() as conn:
        conn.row_factory = None

        total = conn.execute('SELECT COUNT(*) FROM pedidos').fetchone()[0]
        print(f'\n=== BANCO DE DADOS ===')
        print(f'Total de linhas: {total}')

        print('\nPor plataforma:')
        rows = conn.execute(
            'SELECT plataforma, COUNT(*) as linhas, '
            'ROUND(SUM(v_bruto), 2) as v_bruto_total, '
            'ROUND(SUM(v_liquido), 2) as v_liquido_total, '
            'ROUND(AVG(margem_pct)*100, 1) as margem_media_pct '
            'FROM pedidos GROUP BY plataforma ORDER BY linhas DESC'
        ).fetchall()
        for r in rows:
            plataforma, linhas, v_bruto, v_liquido, margem = r
            print(f'  {plataforma or "—"}: {linhas} linhas | V.Bruto R${v_bruto} | V.Líq R${v_liquido} | Margem {margem}%')

        print('\nSem V.LIQUIDO (estimado ou pendente):')
        sem_vliq = conn.execute(
            'SELECT COUNT(*) FROM pedidos WHERE v_liquido IS NULL'
        ).fetchone()[0]
        estimados = conn.execute(
            'SELECT COUNT(*) FROM pedidos WHERE v_liquido_estimado = 1'
        ).fetchone()[0]
        print(f'  Sem V.LIQUIDO: {sem_vliq} | Estimados: {estimados}')


if __name__ == '__main__':
    print(f'Iniciando pipeline: {DATA_INICIO} a {DATA_FIM}\n')

    resumo = executar_pipeline(DATA_INICIO, DATA_FIM)

    print(f'\n=== RESUMO DA EXECUÇÃO ===')
    print(f'Pedidos encontrados : {resumo["pedidos_encontrados"]}')
    print(f'Linhas gravadas     : {resumo["linhas_gravadas"]}')
    print(f'Erros               : {resumo["erros"]}')

    if resumo['detalhes_erros']:
        print('\nDetalhes dos erros:')
        for e in resumo['detalhes_erros']:
            print(f'  id_erp {e["id_erp"]}: {e["erro"]}')

    mostrar_resumo_banco()
