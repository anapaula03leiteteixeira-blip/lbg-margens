from dotenv import load_dotenv
load_dotenv()
from src.database import _sb
from collections import Counter

resp = _sb.table('pedidos').select('plataforma,v_liquido,situacao').like('plataforma', 'Mercado%').execute()
rows = resp.data

nulos = [r for r in rows if r['v_liquido'] is None]
print(f'ML NULL: {len(nulos)}')
print('Por situacao:')
for sit, cnt in Counter(r['situacao'] for r in nulos).most_common():
    print(f'  {sit}: {cnt}')

print(f'\nML COM v_liquido: {len(rows) - len(nulos)}')
print('Por situacao:')
for sit, cnt in Counter(r['situacao'] for r in rows if r['v_liquido'] is not None).most_common():
    print(f'  {sit}: {cnt}')
