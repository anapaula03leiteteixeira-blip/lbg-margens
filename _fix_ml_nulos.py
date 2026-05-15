from dotenv import load_dotenv
load_dotenv()
from src.database import _sb, _USE_SUPABASE, upsert_pedidos
from src.pipeline import processar_pedido, _carregar_taxas
import time

if not _USE_SUPABASE:
    print('ERRO: Supabase nao configurado.')
    exit(1)

# 1. Busca id_erp ML com v_liquido NULL
print('Buscando pedidos Mercado Livre com v_liquido NULL...')
resp = _sb.table('pedidos').select('id_erp').like('plataforma', 'Mercado%').is_('v_liquido', 'null').execute()
ids = list({r['id_erp'] for r in resp.data})
print(f'  {len(ids)} pedidos encontrados.')

if not ids:
    print('Nada a fazer.')
    exit()

# 2. Deleta
print('Deletando registros desatualizados do Supabase...')
CHUNK = 100
for i in range(0, len(ids), CHUNK):
    lote = ids[i:i + CHUNK]
    _sb.table('pedidos').delete().in_('id_erp', lote).like('plataforma', 'Mercado%').execute()
print(f'  {len(ids)} registros deletados.')

# 3. Reprocessa
print('Reprocessando com codigo corrigido...')
taxas = _carregar_taxas()
todas_linhas = []
erros = []

for i, id_erp in enumerate(ids, 1):
    try:
        linhas = processar_pedido(id_erp, taxas)
        todas_linhas.extend(linhas)
        if i % 10 == 0:
            print(f'  {i}/{len(ids)} processados...')
        time.sleep(1.2)
    except Exception as e:
        erros.append({'id_erp': id_erp, 'erro': str(e)})
        print(f'  ERRO {id_erp}: {e}')

# 4. Grava
gravados = upsert_pedidos(todas_linhas)
print(f'\nConcluido: {gravados} linhas gravadas, {len(erros)} erros.')
if erros:
    for e in erros:
        print(f'  {e}')

# Status final
resp2 = _sb.table('pedidos').select('v_liquido,plataforma').like('plataforma', 'Mercado%').execute()
rows = resp2.data
com = sum(1 for r in rows if r['v_liquido'] is not None)
sem = sum(1 for r in rows if r['v_liquido'] is None)
print(f'\nStatus ML: {com} com v_liquido | {sem} sem (Enviado sem liquidacao)')
