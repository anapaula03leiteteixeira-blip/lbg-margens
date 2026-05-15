"""
database.py — Persistência exclusiva no Supabase.
Toda query passa por este módulo. Nenhum outro arquivo acessa o banco diretamente.
"""
import os
from collections import defaultdict
from datetime import datetime, timedelta

from dotenv import load_dotenv
load_dotenv()

_sb = None


def _get_client():
    """Inicialização lazy do cliente Supabase. Falha com mensagem clara se não configurado."""
    global _sb
    if _sb is not None:
        return _sb
    url = os.getenv('SUPABASE_URL', '').strip()
    key = os.getenv('SUPABASE_KEY', '').strip()
    if not url or not key:
        raise EnvironmentError(
            'SUPABASE_URL e SUPABASE_KEY são obrigatórios no .env\n'
            'Configure as credenciais antes de executar o pipeline.'
        )
    from supabase import create_client
    _sb = create_client(url, key)
    return _sb


def _paginar(tabela, select, filtros=None, page_size=1000):
    """Busca todas as páginas de uma query Supabase e retorna lista completa."""
    sb = _get_client()
    rows = []
    offset = 0
    while True:
        q = sb.table(tabela).select(select)
        if filtros:
            for metodo, args in filtros:
                q = getattr(q, metodo)(*args)
        resp = q.range(offset, offset + page_size - 1).execute()
        rows.extend(resp.data)
        if len(resp.data) < page_size:
            break
        offset += page_size
    return rows


# Tabela é criada via painel Supabase — esta função existe apenas para compatibilidade
# com chamadas em pipeline.py e rodar.py.
def criar_tabelas():
    pass


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
    sb = _get_client()
    rows_raw = [{c: p.get(c) for c in _COLUNAS} for p in pedidos]
    seen = {}
    for r in rows_raw:
        seen[(r['id_erp'], r['sku'])] = r
    rows = list(seen.values())
    CHUNK = 500
    total = 0
    for i in range(0, len(rows), CHUNK):
        sb.table('pedidos').upsert(rows[i:i + CHUNK], on_conflict='id_erp,sku').execute()
        total += len(rows[i:i + CHUNK])
    return total


def buscar_ids_existentes():
    """Retorna set de id_erp já gravados (paginado para não perder registros)."""
    rows = _paginar('pedidos', 'id_erp')
    return {row['id_erp'] for row in rows}


def buscar_shopee_pendentes():
    """Retorna pedidos Shopee com v_liquido_estimado=1 para reconciliação."""
    campos = 'id_erp,num_pedido_ecommerce,sku,quantidade,v_nf,v_bruto,plataforma,canal'
    filtros = [
        ('eq',    ('v_liquido_estimado', 1)),
        ('ilike', ('plataforma', 'Shopee%')),
    ]
    return _paginar('pedidos', campos, filtros)


def atualizar_shopee_reconciliado(id_erp, sku, v_liquido, plataforma, margem):
    """Atualiza apenas V.LIQUIDO e margem — não toca em metadados do pedido."""
    sb = _get_client()
    campos = {
        'v_liquido':          v_liquido,
        'v_liquido_estimado': 0,
        'plataforma':         plataforma,
        'impostos':           margem['impostos'],
        'comissao':           margem['comissao'],
        'embalagem':          margem['embalagem'],
        'custo_produto':      margem['custo_produto'],
        'margem_rs':          margem['margem_rs'],
        'margem_pct':         margem['margem_pct'],
    }
    sb.table('pedidos').update(campos).eq('id_erp', id_erp).eq('sku', sku).execute()


def buscar_pedidos_periodo(data_inicio, data_fim):
    """data_inicio / data_fim: 'YYYY-MM-DD'"""
    sb = _get_client()
    resp = (
        sb.table('pedidos')
        .select('*')
        .gte('data_venda', data_inicio)
        .lte('data_venda', data_fim)
        .order('data_venda')
        .execute()
    )
    return resp.data


def buscar_config(chave):
    """Lê valor da tabela config. Retorna None se não existir."""
    sb = _get_client()
    resp = sb.table('config').select('valor').eq('chave', chave).execute()
    if resp.data:
        return resp.data[0]['valor']
    return None


def salvar_config(chave, valor):
    """Persiste valor na tabela config (upsert por chave)."""
    sb = _get_client()
    sb.table('config').upsert(
        {'chave': chave, 'valor': str(valor)},
        on_conflict='chave',
    ).execute()


def buscar_ids_por_data(data_iso):
    """
    Retorna set de id_erp gravados para uma data específica.
    data_iso: 'YYYY-MM-DD' — converte para 'DD/MM/YYYY' (formato armazenado).
    Muito mais eficiente que buscar_ids_existentes() para processamento diário.
    """
    dt = datetime.strptime(data_iso, '%Y-%m-%d')
    data_ddmmyyyy = dt.strftime('%d/%m/%Y')
    rows = _paginar('pedidos', 'id_erp', [('eq', ('data_venda', data_ddmmyyyy))])
    return {row['id_erp'] for row in rows}


def buscar_shopee_pendentes_recentes(dias=45):
    """
    Retorna pedidos Shopee com V.LIQUIDO estimado nos últimos N dias.
    Ignora pedidos mais antigos que o prazo máximo de reconciliação.
    """
    campos = 'id_erp,num_pedido_ecommerce,sku,quantidade,v_nf,v_bruto,plataforma,canal,data_venda'
    filtros = [
        ('eq',    ('v_liquido_estimado', 1)),
        ('ilike', ('plataforma', 'Shopee%')),
    ]
    rows = _paginar('pedidos', campos, filtros)

    # Filtra em Python — DD/MM/YYYY não ordena corretamente como texto no Supabase
    cutoff = datetime.now() - timedelta(days=dias)
    resultado = []
    for r in rows:
        try:
            dt = datetime.strptime(r['data_venda'], '%d/%m/%Y')
            if dt >= cutoff:
                resultado.append(r)
        except Exception:
            resultado.append(r)
    return resultado


def buscar_resumo():
    """
    Retorna totais agregados para exibição no terminal após execução do pipeline.
    Consulta o Supabase — mesma fonte de verdade usada pelo pipeline.
    """
    rows = _paginar('pedidos', 'plataforma,v_bruto,v_liquido,margem_pct,v_liquido_estimado')

    total = len(rows)
    por_plataforma = defaultdict(lambda: {
        'linhas': 0, 'v_bruto': 0.0, 'v_liquido': 0.0,
        'margem_sum': 0.0, 'margem_count': 0,
    })
    estimados = 0
    sem_vliq = 0

    for r in rows:
        p = r.get('plataforma') or '—'
        por_plataforma[p]['linhas'] += 1
        por_plataforma[p]['v_bruto'] += r.get('v_bruto') or 0.0
        por_plataforma[p]['v_liquido'] += r.get('v_liquido') or 0.0
        if r.get('margem_pct') is not None:
            por_plataforma[p]['margem_sum'] += r['margem_pct']
            por_plataforma[p]['margem_count'] += 1
        if r.get('v_liquido_estimado') == 1:
            estimados += 1
        if r.get('v_liquido') is None:
            sem_vliq += 1

    plataformas = sorted(
        [{'plataforma': k, **v} for k, v in por_plataforma.items()],
        key=lambda x: x['linhas'],
        reverse=True,
    )
    return {'total': total, 'plataformas': plataformas, 'estimados': estimados, 'sem_vliq': sem_vliq}
