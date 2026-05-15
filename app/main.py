"""
app/main.py — Dashboard La Bella Griffe
Sistema de Controle de Margens
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import yaml
import streamlit as st
import pandas as pd

TAXAS_PATH = os.path.join(os.path.dirname(__file__), '..', 'config', 'taxas.yaml')

st.set_page_config(
    page_title='La Bella Griffe — Controle de Margens',
    page_icon='💎',
    layout='wide',
)

# ── Supabase ──────────────────────────────────────────────────────────────────
try:
    _SUPA_URL = st.secrets['SUPABASE_URL']
    _SUPA_KEY = st.secrets['SUPABASE_KEY']
except (KeyError, Exception):
    st.error(
        '⚠️ **Credenciais Supabase não encontradas.**\n\n'
        'Configure `SUPABASE_URL` e `SUPABASE_KEY` nos Secrets do Streamlit Cloud\n'
        '(Settings → Secrets).'
    )
    st.stop()

# ── Autenticação ──────────────────────────────────────────────────────────────
def _checar_senha():
    try:
        senha_correta = st.secrets.get('DASHBOARD_SENHA', 'labg2026')
    except Exception:
        senha_correta = 'labg2026'
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

# ── Estilo ────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
[data-testid="stMetricValue"] { font-size: 1.6rem; }
.estimado-badge {
    background: #fff3cd; color: #856404;
    padding: 2px 6px; border-radius: 4px;
    font-size: 0.78rem; font-weight: 600;
}
</style>
""", unsafe_allow_html=True)


# ── Dados ─────────────────────────────────────────────────────────────────────
@st.cache_data(ttl=60)
def carregar_dados():
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


def fmt_brl(val):
    if pd.isna(val) or val is None:
        return '—'
    return f'R$ {val:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


def fmt_pct(val):
    if pd.isna(val) or val is None:
        return '—'
    return f'{val * 100:.1f}%'


def carregar_taxas():
    with open(TAXAS_PATH, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def salvar_taxas(taxas):
    with open(TAXAS_PATH, 'w', encoding='utf-8') as f:
        yaml.dump(taxas, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


# ── Navegação por abas ────────────────────────────────────────────────────────
aba_margens, aba_config = st.tabs(['💎 Margens', '⚙️ Configurações'])


# ═══════════════════════════════════════════════════════════════════════════════
# ABA MARGENS
# ═══════════════════════════════════════════════════════════════════════════════
with aba_margens:
    st.title('💎 La Bella Griffe — Controle de Margens')

    df_raw = carregar_dados()

    if df_raw.empty:
        st.warning('Nenhum dado no banco. Rode `python rodar.py` primeiro.')
        st.stop()

    df_raw['data_venda'] = pd.to_datetime(df_raw['data_venda'], dayfirst=True, errors='coerce')

    # ── Sidebar — Filtros ─────────────────────────────────────────────────────
    with st.sidebar:
        st.header('Filtros')

        meses_disp = sorted(df_raw['data_venda'].dt.to_period('M').dropna().unique().tolist(), reverse=True)
        meses_str  = [str(m) for m in meses_disp]
        mes_sel    = st.multiselect('Mês', meses_str, default=meses_str[:1] if meses_str else [])

        plats_disp = sorted(df_raw['plataforma'].dropna().unique().tolist())
        plat_sel   = st.multiselect('Plataforma', plats_disp, default=plats_disp)

        canais_disp = sorted(df_raw['canal'].dropna().unique().tolist())
        canal_sel   = st.multiselect('Canal', canais_disp, default=canais_disp)

        st.divider()
        mostrar_estimados = st.checkbox('Mostrar estimados (Shopee em trânsito)', value=True)

    # ── Filtros ───────────────────────────────────────────────────────────────
    df = df_raw.copy()
    if mes_sel:
        df = df[df['data_venda'].dt.to_period('M').astype(str).isin(mes_sel)]
    if plat_sel:
        df = df[df['plataforma'].isin(plat_sel)]
    if canal_sel:
        df = df[df['canal'].isin(canal_sel)]
    if not mostrar_estimados:
        df = df[df.get('v_liquido_estimado', 0) != 1]

    # ── Aviso estimados ───────────────────────────────────────────────────────
    n_estimados = int(df.get('v_liquido_estimado', pd.Series(dtype=int)).sum()) if 'v_liquido_estimado' in df.columns else 0
    if n_estimados > 0:
        st.warning(
            f'⚠️ **{n_estimados} linhas com V. Líquido estimado** (Shopee em trânsito). '
            'Os valores serão atualizados automaticamente quando o pedido for entregue.',
            icon='⚠️'
        )

    # ── KPIs ──────────────────────────────────────────────────────────────────
    pedidos_unicos = df['id_erp'].nunique()
    total_vbruto   = df['v_bruto'].sum()
    total_vliq     = df['v_liquido'].sum()
    total_margem   = df['margem_rs'].sum()
    sem_vliq       = df['v_liquido'].isna().sum()

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric('Pedidos',      f'{pedidos_unicos:,}')
    c2.metric('V. Bruto',     fmt_brl(total_vbruto))
    c3.metric('V. Líquido',   fmt_brl(total_vliq) if total_vliq > 0 else '—')
    c4.metric('Margem R$',    fmt_brl(total_margem) if total_margem else '—')
    c5.metric('Sem V. Líquido', f'{sem_vliq} linhas')

    st.divider()

    # ── Resumo por plataforma ─────────────────────────────────────────────────
    st.subheader('Por plataforma')

    resumo = (
        df.groupby('plataforma', sort=False)
        .agg(
            Pedidos=('id_erp', 'nunique'),
            Linhas=('id', 'count'),
            V_Bruto=('v_bruto', 'sum'),
            V_Liquido=('v_liquido', 'sum'),
            Margem_RS=('margem_rs', 'sum'),
            Estimados=('v_liquido_estimado', 'sum') if 'v_liquido_estimado' in df.columns else ('id', 'count'),
        )
        .reset_index()
        .sort_values('V_Bruto', ascending=False)
    )

    def _fmt_vliq_resumo(row):
        val = row['V_Liquido']
        est = row.get('Estimados', 0)
        if not val or val == 0:
            return '⚠️ sem conector'
        texto = fmt_brl(val)
        if est and est > 0:
            texto += f' ⚠️ ({int(est)} est.)'
        return texto

    resumo['V. Bruto']   = resumo['V_Bruto'].apply(fmt_brl)
    resumo['V. Líquido'] = resumo.apply(_fmt_vliq_resumo, axis=1)
    resumo['Margem R$']  = resumo['Margem_RS'].apply(lambda x: fmt_brl(x) if x and x != 0 else '—')
    resumo = resumo.rename(columns={'plataforma': 'Plataforma'})[
        ['Plataforma', 'Pedidos', 'Linhas', 'V. Bruto', 'V. Líquido', 'Margem R$']
    ]
    st.dataframe(resumo, use_container_width=True, hide_index=True)

    st.divider()

    # ── Tabela detalhada ──────────────────────────────────────────────────────
    st.subheader('Pedidos detalhados')

    cols_exibir = [
        'data_venda', 'id_erp', 'num_pedido_ecommerce', 'cliente',
        'sku', 'quantidade', 'plataforma', 'canal',
        'v_bruto', 'v_nf', 'v_liquido', 'v_liquido_estimado',
        'impostos', 'comissao', 'embalagem', 'custo_produto',
        'margem_rs', 'margem_pct', 'situacao',
    ]
    cols_exibir = [c for c in cols_exibir if c in df.columns]
    df_tabela = df[cols_exibir].copy()

    df_tabela['data_venda'] = df_tabela['data_venda'].dt.strftime('%d/%m/%Y')
    df_tabela['margem_pct'] = df_tabela['margem_pct'].apply(fmt_pct)

    # V. Líquido: adiciona badge ⚠️ para estimados
    if 'v_liquido_estimado' in df_tabela.columns:
        def _fmt_vliq_tabela(row):
            val = fmt_brl(row['v_liquido'])
            if row.get('v_liquido_estimado') == 1:
                return f'{val} ⚠️ est.'
            return val
        df_tabela['v_liquido'] = df_tabela.apply(_fmt_vliq_tabela, axis=1)
        df_tabela = df_tabela.drop(columns=['v_liquido_estimado'])

    for col in ['v_bruto', 'v_nf', 'impostos', 'comissao', 'embalagem', 'custo_produto', 'margem_rs']:
        if col in df_tabela.columns:
            df_tabela[col] = df_tabela[col].apply(fmt_brl)

    df_tabela.columns = [c.replace('_', ' ').upper() for c in df_tabela.columns]
    st.dataframe(df_tabela, use_container_width=True, hide_index=True, height=500)

    # ── Legenda ───────────────────────────────────────────────────────────────
    if n_estimados > 0:
        st.caption('⚠️ est. = V. Líquido estimado (Shopee em trânsito). Será substituído pelo valor real após entrega confirmada.')

    st.caption(f'Banco: Supabase | {len(df_raw)} linhas totais | Rode `python rodar.py` para importar novos pedidos')


# ═══════════════════════════════════════════════════════════════════════════════
# ABA CONFIGURAÇÕES
# ═══════════════════════════════════════════════════════════════════════════════
with aba_config:
    st.title('⚙️ Configurações de Taxas')
    st.caption('Alterações aqui são salvas em `config/taxas.yaml` e aplicadas na próxima execução do pipeline.')

    try:
        taxas = carregar_taxas()
    except Exception as e:
        st.error(f'Erro ao carregar taxas.yaml: {e}')
        st.stop()

    st.divider()

    # ── Taxas fixas de Flex ───────────────────────────────────────────────────
    st.subheader('Taxas Fixas por Pedido (Flex)')
    st.info('Deduzidas do valor total do pedido para calcular V. Líquido.')

    col1, col2 = st.columns(2)
    with col1:
        ml_flex = st.number_input(
            'Mercado Livre Flex — taxa fixa (R$)',
            min_value=0.0, max_value=100.0,
            value=float(taxas.get('mercado_livre_flex', {}).get('taxa_fixa', 14.99)),
            step=0.01, format='%.2f',
            help='Deduzida de total_amount para pedidos com logistic_type=self_service',
        )
    with col2:
        shopee_flex = st.number_input(
            'Shopee Flex (Entrega Direta) — taxa fixa (R$)',
            min_value=0.0, max_value=100.0,
            value=float(taxas.get('shopee_flex', {}).get('taxa_fixa', 9.99)),
            step=0.01, format='%.2f',
            help='Deduzida do escrow_amount para pedidos com carrier=Entrega Direta',
        )

    st.divider()

    # ── Comissões percentuais ─────────────────────────────────────────────────
    st.subheader('Comissões Percentuais')

    col3, col4, col5 = st.columns(3)
    with col3:
        shopee_comissao = st.number_input(
            'Shopee — comissão estimada (%)',
            min_value=0.0, max_value=50.0,
            value=float(taxas.get('shopee', {}).get('taxa_comissao', 0.10)) * 100,
            step=0.5, format='%.1f',
            help='Usada para estimar V. Líquido de pedidos Shopee ainda em trânsito',
        )
    with col4:
        impostos = st.number_input(
            'Impostos sobre V. NF (%)',
            min_value=0.0, max_value=50.0,
            value=float(taxas.get('impostos', 0.13)) * 100,
            step=0.5, format='%.1f',
        )
    with col5:
        comissao_interna = st.number_input(
            'Comissão interna sobre V. Líquido (%)',
            min_value=0.0, max_value=50.0,
            value=float(taxas.get('comissao', 0.04)) * 100,
            step=0.5, format='%.1f',
        )

    st.divider()

    # ── Salvar ────────────────────────────────────────────────────────────────
    if st.button('💾 Salvar configurações', type='primary'):
        taxas['mercado_livre_flex']['taxa_fixa'] = round(ml_flex, 2)
        taxas['shopee_flex']['taxa_fixa']        = round(shopee_flex, 2)
        if 'shopee' not in taxas:
            taxas['shopee'] = {}
        taxas['shopee']['taxa_comissao'] = round(shopee_comissao / 100, 4)
        taxas['impostos']  = round(impostos / 100, 4)
        taxas['comissao']  = round(comissao_interna / 100, 4)

        try:
            salvar_taxas(taxas)
            st.success('✅ Taxas salvas com sucesso! Serão aplicadas na próxima execução do pipeline.')
            st.cache_data.clear()
        except Exception as e:
            st.error(f'Erro ao salvar: {e}')

    # ── Preview ───────────────────────────────────────────────────────────────
    with st.expander('Ver arquivo taxas.yaml atual'):
        with open(TAXAS_PATH, 'r') as f:
            st.code(f.read(), language='yaml')
