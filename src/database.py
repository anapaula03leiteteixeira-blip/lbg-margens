import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'lbg.db')


def get_conn():
    return sqlite3.connect(DB_PATH)


def criar_tabelas():
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


def upsert_pedidos(pedidos):
    """
    Insere ou atualiza pedidos. Chave única: (id_erp, sku).
    """
    if not pedidos:
        return 0

    colunas = [
        'data_venda', 'id_erp', 'num_nf', 'num_pedido_ecommerce', 'cliente',
        'sku', 'v_bruto', 'quantidade', 'ecommerce', 'v_nf', 'data_emissao',
        'uf', 'situacao', 'v_liquido', 'v_liquido_estimado', 'plataforma',
        'canal', 'impostos', 'comissao', 'embalagem', 'custo_produto',
        'margem_rs', 'margem_pct', 'status',
    ]

    placeholders = ', '.join(['?' for _ in colunas])
    updates = ', '.join([f'{c}=excluded.{c}' for c in colunas if c not in ('id_erp', 'sku')])
    sql = f'''
        INSERT INTO pedidos ({', '.join(colunas)})
        VALUES ({placeholders})
        ON CONFLICT(id_erp, sku) DO UPDATE SET {updates},
            atualizado_em=datetime('now')
    '''

    rows = [[p.get(c) for c in colunas] for p in pedidos]
    with get_conn() as conn:
        conn.executemany(sql, rows)
        conn.commit()

    return len(rows)


def buscar_pedidos_periodo(data_inicio, data_fim):
    """data_inicio / data_fim: 'YYYY-MM-DD'"""
    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            'SELECT * FROM pedidos WHERE data_venda BETWEEN ? AND ? ORDER BY data_venda',
            (data_inicio, data_fim)
        )
        return [dict(row) for row in cursor.fetchall()]
