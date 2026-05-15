"""
Reprocessa pedidos Shopee com v_liquido=NULL.
Funciona com SQLite (local) e Supabase.
"""
from dotenv import load_dotenv
load_dotenv()

import time
from src.database import get_conn, upsert_pedidos, _USE_SUPABASE, _sb
from src.pipeline import processar_pedido, _carregar_taxas


def _buscar_ids_shopee_nulos():
    if _USE_SUPABASE:
        resp = _sb.table('pedidos').select('id_erp').eq('plataforma', 'Shopee').is_('v_liquido', 'null').execute()
        return list({r['id_erp'] for r in resp.data})
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT DISTINCT id_erp FROM pedidos WHERE plataforma='Shopee' AND v_liquido IS NULL"
        ).fetchall()
        return [r[0] for r in rows]


def _apagar_shopee_nulos(ids):
    if _USE_SUPABASE:
        CHUNK = 100
        for i in range(0, len(ids), CHUNK):
            _sb.table('pedidos').delete().in_('id_erp', ids[i:i + CHUNK]).eq('plataforma', 'Shopee').execute()
        return
    with get_conn() as conn:
        CHUNK = 100
        for i in range(0, len(ids), CHUNK):
            placeholders = ','.join('?' * len(ids[i:i + CHUNK]))
            conn.execute(
                f"DELETE FROM pedidos WHERE id_erp IN ({placeholders}) AND plataforma='Shopee'",
                ids[i:i + CHUNK]
            )
        conn.commit()


def _status_shopee():
    if _USE_SUPABASE:
        resp = _sb.table('pedidos').select('v_liquido,v_liquido_estimado').eq('plataforma', 'Shopee').execute()
        rows = resp.data
    else:
        with get_conn() as conn:
            rows = [
                {'v_liquido': r[0], 'v_liquido_estimado': r[1]}
                for r in conn.execute(
                    "SELECT v_liquido, v_liquido_estimado FROM pedidos WHERE plataforma='Shopee'"
                ).fetchall()
            ]
    com = sum(1 for r in rows if r['v_liquido'] is not None)
    sem = sum(1 for r in rows if r['v_liquido'] is None)
    est = sum(1 for r in rows if r['v_liquido_estimado'] == 1)
    print(f'Status Shopee: {com} com v_liquido | {sem} sem | {est} estimados')


# --- 1. Coleta ---
print('Buscando pedidos Shopee com v_liquido NULL...')
ids_nulos = _buscar_ids_shopee_nulos()
print(f'  {len(ids_nulos)} pedidos encontrados.')

if not ids_nulos:
    print('Nada a fazer.')
    _status_shopee()
    exit()

# --- 2. Apaga ---
print('Apagando registros desatualizados...')
_apagar_shopee_nulos(ids_nulos)
print(f'  {len(ids_nulos)} registros apagados.')

# --- 3. Reprocessa ---
print('Reprocessando...')
taxas = _carregar_taxas()
todas_linhas = []
erros = []

for i, id_erp in enumerate(ids_nulos, 1):
    try:
        linhas = processar_pedido(id_erp, taxas)
        todas_linhas.extend(linhas)
        if i % 10 == 0:
            print(f'  {i}/{len(ids_nulos)} processados...')
        time.sleep(1.2)
    except Exception as e:
        erros.append({'id_erp': id_erp, 'erro': str(e)})
        print(f'  ERRO {id_erp}: {e}')

# --- 4. Grava ---
gravados = upsert_pedidos(todas_linhas)
print(f'\nConcluido: {gravados} linhas gravadas, {len(erros)} erros.')

if erros:
    for e in erros:
        print(f'  {e}')

_status_shopee()
