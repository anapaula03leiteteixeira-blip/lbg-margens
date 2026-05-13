"""
migrar_sqlite_supabase.py — Copia todos os dados de lbg.db para Supabase.
Uso: python migrar_sqlite_supabase.py
"""
import os
import sqlite3
from dotenv import load_dotenv
load_dotenv()

SUPABASE_URL = os.getenv('SUPABASE_URL', '').strip()
SUPABASE_KEY = os.getenv('SUPABASE_KEY', '').strip()
DB_PATH = os.path.join(os.path.dirname(__file__), 'lbg.db')

COLUNAS = [
    'data_venda', 'id_erp', 'num_nf', 'num_pedido_ecommerce', 'cliente',
    'sku', 'v_bruto', 'quantidade', 'ecommerce', 'v_nf', 'data_emissao',
    'uf', 'situacao', 'v_liquido', 'v_liquido_estimado', 'plataforma',
    'canal', 'impostos', 'comissao', 'embalagem', 'custo_produto',
    'margem_rs', 'margem_pct', 'status',
]

if __name__ == '__main__':
    if not SUPABASE_URL or not SUPABASE_KEY:
        print('ERRO: SUPABASE_URL e SUPABASE_KEY nao configurados no .env')
        exit(1)

    if not os.path.exists(DB_PATH):
        print(f'ERRO: {DB_PATH} nao encontrado')
        exit(1)

    from supabase import create_client
    sb = create_client(SUPABASE_URL, SUPABASE_KEY)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute('SELECT * FROM pedidos').fetchall()
    conn.close()

    total_sqlite = len(rows)
    print(f'Lendo {total_sqlite} linhas do SQLite...')

    pedidos = [{c: dict(row).get(c) for c in COLUNAS} for row in rows]

    CHUNK = 500
    enviados = 0
    for i in range(0, len(pedidos), CHUNK):
        chunk = pedidos[i:i + CHUNK]
        sb.table('pedidos').upsert(chunk, on_conflict='id_erp,sku').execute()
        enviados += len(chunk)
        print(f'  Enviados: {enviados}/{total_sqlite}')

    print(f'\nMigracao concluida! {enviados} linhas inseridas/atualizadas no Supabase.')
