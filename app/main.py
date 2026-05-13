"""
app/main.py — Dashboard La Bella Griffe
Sistema de Controle de Margens
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import streamlit as st
import pandas as pd
import sqlite3

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'lbg.db')

st.set_page_config(
    page_title='La Bella Griffe — Controle de Margens',
    page_icon='💎',
    layout='wide',
)

# ── Credenciais Supabase ──────────────────────────────────────────────────────
try:
    _SUPA_URL = st.secrets.get('SUPABASE_URL', '') or ''
    _SUPA_KEY = st.secrets.get('SUPABASE_KEY', '') or ''
except Exception:
    _SUPA_URL = os.getenv('SUPABASE_URL', '')
    _SUPA_KEY = os.getenv('SUPABASE_KEY', '')

_USE_SUPABASE = bool(_SUPA_URL and _SUPA_KEY)

# ── Autenticação ─────────────────────────────────────────────────────────────
def _checar_senha():
    senha_correta = st.secrets.get('DASHBOARD_SENHA', 'labg2026')
    if 'autenticado' not in st.session_state:
        st.session_state.autenticado = False
    if st.session_state.autenticado:
        return True
    st.title('💎 La Bella Griffe')
    senha = st.text_input('Senha de acesso', type='password')
    if st.button('Entrar'):
        if senha == senha_correta:
            st.session_state.autenticado = True
            st.rerun()
        else:
            st.error('Senha incorreta')
    return False

if not _checar_senha():
    st.stop()

# ── Estilo ───────────────────────────────────────────────────────────────────
st.markdown("""
<style>
[data-testid="stMetricValue"] { font-size: 1.6rem; }
.sem-vliq { color: #f0a500; font-weight: 600; }
</style>
""", unsafe_allow_html=True)


@st.cache_data(ttl=60)
def carregar_dados():
    if _USE_SUPABASE:
        from supabase import create_client
        sb = create_client(_SUPA_URL, _SUPA_KEY)
        rows = []
        PAGE = 1000
        offset = 0
        while True:
            resp = (
                sb.table('pedidos')
                .select('*')
                .order('data_venda', desc=True)
                .range(offset, offset + PAGE - 1)
                .execute()
            )
            rows.extend(resp.data)
            if len(resp.data) < PAGE:
                break
            offset += PAGE
        return pd.DataFrame(rows)
    else:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute('SELECT * FROM pedidos ORDER BY data_venda DESC').fetchall()
        return pd.DataFrame([dict(r) for r in rows])


def fmt_brl(val):
    if pd.isna(val) or val is None:
        return '—'
    return f'R$ {val:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


def fmt_pct(val):
    if pd.isna(val) or val is None:
        return '—'
    return f'{val * 100:.1f}%'


# ── Header ───────────────────────────────────────────────────────────────────
st.title('💎 La Bella Griffe — Controle de Margens')

df_raw = carregar_dados()

if df_raw.empty:
    st.warning('Nenhum dado no banco. Rode `python rodar.py` primeiro.')
    st.stop()

# Converter datas
df_raw['data_venda'] = pd.to_datetime(df_raw['data_venda'], dayfirst=True, errors='coerce')

# ── Sidebar — Filtros ────────────────────────────────────────────────────────
with st.sidebar:
    st.header('Filtros')

    meses_disp = sorted(df_raw['data_venda'].dt.to_period('M').dropna().unique().tolist(), reverse=True)
    meses_str = [str(m) for m in meses_disp]
    mes_sel = st.multiselect('Mês', meses_str, default=meses_str[:1] if meses_str else [])

    plats_disp = sorted(df_raw['plataforma'].dropna().unique().tolist())
    plat_sel = st.multiselect('Plataforma', plats_disp, default=plats_disp)

    canais_disp = sorted(df_raw['canal'].dropna().unique().tolist())
    canal_sel = st.multiselect('Canal', canais_disp, default=canais_disp)

# ── Aplicar filtros ──────────────────────────────────────────────────────────
df = df_raw.copy()
if mes_sel:
    df = df[df['data_venda'].dt.to_period('M').astype(str).isin(mes_sel)]
if plat_sel:
    df = df[df['plataforma'].isin(plat_sel)]
if canal_sel:
    df = df[df['canal'].isin(canal_sel)]

# ── KPIs ─────────────────────────────────────────────────────────────────────
pedidos_unicos = df['id_erp'].nunique()
total_vbruto   = df['v_bruto'].sum()
total_vliq     = df['v_liquido'].sum()
total_margem   = df['margem_rs'].sum()
sem_vliq       = df['v_liquido'].isna().sum()

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric('Pedidos', f'{pedidos_unicos:,}')
c2.metric('V. Bruto', fmt_brl(total_vbruto))
c3.metric('V. Líquido', fmt_brl(total_vliq) if total_vliq > 0 else '—')
c4.metric('Margem R$', fmt_brl(total_margem) if total_margem else '—')
c5.metric('Sem V. Líquido', f'{sem_vliq} linhas', delta=None)

st.divider()

# ── Resumo por plataforma ────────────────────────────────────────────────────
st.subheader('Por plataforma')

resumo = (
    df.groupby('plataforma', sort=False)
    .agg(
        Pedidos=('id_erp', 'nunique'),
        Linhas=('id', 'count'),
        V_Bruto=('v_bruto', 'sum'),
        V_Liquido=('v_liquido', 'sum'),
        Margem_RS=('margem_rs', 'sum'),
    )
    .reset_index()
    .sort_values('V_Bruto', ascending=False)
)

resumo['V. Bruto']    = resumo['V_Bruto'].apply(fmt_brl)
resumo['V. Líquido']  = resumo['V_Liquido'].apply(lambda x: fmt_brl(x) if x and x > 0 else '⚠️ sem conector')
resumo['Margem R$']   = resumo['Margem_RS'].apply(lambda x: fmt_brl(x) if x and x != 0 else '—')
resumo = resumo.rename(columns={'plataforma': 'Plataforma'})[
    ['Plataforma', 'Pedidos', 'Linhas', 'V. Bruto', 'V. Líquido', 'Margem R$']
]

st.dataframe(resumo, use_container_width=True, hide_index=True)

st.divider()

# ── Tabela de pedidos ────────────────────────────────────────────────────────
st.subheader('Pedidos detalhados')

cols_exibir = [
    'data_venda', 'id_erp', 'num_pedido_ecommerce', 'cliente',
    'sku', 'quantidade', 'plataforma', 'canal',
    'v_bruto', 'v_nf', 'v_liquido', 'impostos', 'comissao',
    'embalagem', 'custo_produto', 'margem_rs', 'margem_pct', 'situacao',
]
cols_exibir = [c for c in cols_exibir if c in df.columns]
df_tabela = df[cols_exibir].copy()

df_tabela['data_venda']   = df_tabela['data_venda'].dt.strftime('%d/%m/%Y')
df_tabela['margem_pct']   = df_tabela['margem_pct'].apply(fmt_pct)
for col in ['v_bruto', 'v_nf', 'v_liquido', 'impostos', 'comissao', 'embalagem', 'custo_produto', 'margem_rs']:
    if col in df_tabela.columns:
        df_tabela[col] = df_tabela[col].apply(fmt_brl)

df_tabela.columns = [c.replace('_', ' ').upper() for c in df_tabela.columns]

st.dataframe(df_tabela, use_container_width=True, hide_index=True, height=500)

# ── Rodapé ───────────────────────────────────────────────────────────────────
fonte = 'Supabase' if _USE_SUPABASE else DB_PATH
st.caption(f'Banco: {fonte} | {len(df_raw)} linhas totais | Atualizado: rode `python rodar.py` para importar novos pedidos')
