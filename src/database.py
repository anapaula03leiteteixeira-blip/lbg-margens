import os
import sqlite3

from dotenv import load_dotenv
load_dotenv()

SUPABASE_URL = os.getenv('SUPABASE_URL', '').strip()
SUPABASE_KEY = os.getenv('SUPABASE_KEY', '').strip()
_USE_SUPABASE = bool(SUPABASE_URL and SUPABASE_KEY)

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'lbg.db')

_sb = None
if _USE_SUPABASE:
    from supabase import create_client
    _sb = create_client(SUPABASE_URL, SUPABASE_KEY)


def get_conn():
    return sqlite3.connect(DB_PATH)


def criar_tabelas():
    if _USE_SUPABASE:
        return
    with get_conn() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS pedidos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data_venda TEXT,
                id_erp TEXT,
                num_nf TEXT,
                num_pedido_ecommerce TEXT,
                cliente TEXT,
                sku TEXT,
                v_bruto REAL,
                quantidade REAL,
                ecommerce TEXT,
                v_nf REAL,
                data_emissao TEXT,
                uf TEXT,
                situacao TEXT,
                v_liquido REAL,
                v_liquido_estimado INTEGER DEFAULT 0,
                plataforma TEXT,
                canal TEXT,
                impostos REAL,
                comissao REAL,
                embalagem REAL,
                custo_produto REAL,
                margem_rs REAL,
                margem_pct REAL,
                devolucao INTEGER DEFAULT 0,
                data_retorno TEXT,
                condicao_devolucao TEXT,
                custo_devolucao REAL,
                status TEXT DEFAULT 'ATIVO',
                criado_em TEXT DEFAULT (datetime('now')),
                atualizado_em TEXT DEFAULT (datetime('now')),
                UNIQUE(id_erp, sku)
            )
        ''')
        conn.commit()


_COLUNAS = [
    'data_venda', 'id_erp', 'num_nf', 'num_pedido_ecommerce', 'cliente',
    'sku', 'v_bruto', 'quantidade', 'ecommerce', 'v_nf', 'data_emissao',
    'uf', 'situacao', 'v_liquido', 'v_liquido_estimado', 'plataforma',
    'canal', 'impostos', 'comissao', 'embalagem', 'custo_produto',
    'margem_rs', 'margem_pct', 'status',
]


def upsert_pedidos(pedidos):
    if not pedidos:
        return 0

    if _USE_SUPABASE:
        rows = [{c: p.get(c) for c in _COLUNAS} for p in pedidos]
        CHUNK = 500
        total = 0
        for i in range(0, len(rows), CHUNK):
            _sb.table('pedidos').upsert(rows[i:i + CHUNK], on_conflict='id_erp,sku').execute()
            total += len(rows[i:i + CHUNK])
        return total

    placeholders = ', '.join(['?' for _ in _COLUNAS])
    updates = ', '.join([f'{c}=excluded.{c}' for c in _COLUNAS if c not in ('id_erp', 'sku')])
    sql = f'''
        INSERT INTO pedidos ({', '.join(_COLUNAS)})
        VALUES ({placeholders})
        ON CONFLICT(id_erp, sku) DO UPDATE SET {updates},
            atualizado_em=datetime('now')
    '''
    rows = [[p.get(c) for c in _COLUNAS] for p in pedidos]
    with get_conn() as conn:
        conn.executemany(sql, rows)
        conn.commit()
    return len(rows)


def buscar_pedidos_periodo(data_inicio, data_fim):
    """data_inicio / data_fim: 'YYYY-MM-DD'"""
    if _USE_SUPABASE:
        resp = (
            _sb.table('pedidos')
            .select('*')
            .gte('data_venda', data_inicio)
            .lte('data_venda', data_fim)
            .order('data_venda')
            .execute()
        )
        return resp.data

    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            'SELECT * FROM pedidos WHERE data_venda BETWEEN ? AND ? ORDER BY data_venda',
            (data_inicio, data_fim)
        )
        return [dict(row) for row in cursor.fetchall()]
