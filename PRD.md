# PRD — Sistema de Controle de Margens La Bella Griffe
> **FONTE DE VERDADE ÚNICA.** Leia este arquivo antes de qualquer implementação.
> Qualquer mudança de regra deve ser registrada aqui ANTES de mexer no código.
>
> Versão: 4.0 — 2026-05-15

---

## 1. VISÃO GERAL

Pipeline automático que coleta pedidos de todos os canais de venda, consolida em banco único e calcula margem real por pedido × SKU.

**Tecnologia:**
- Python (pipeline — roda via GitHub Actions todo dia às 00h Brasília)
- Supabase — PostgreSQL gratuito na nuvem (banco de dados **exclusivo**)
- Streamlit Community Cloud — dashboard web gratuito (somente leitura)

**Fluxo:**
```
GitHub Actions (00h Brasília)
  └── rodar.py → Tiny API → ML/Shopee APIs → Supabase → Streamlit Cloud (dashboard)
                                                               ↓
                                                     Funcionários via navegador
```

**Dashboard online:** `https://lbg-margens-2yy5prbjq2e4zl4vobwysy.streamlit.app`
**Senha:** `labg2026`

**Regra absoluta:** SOMENTE LEITURA em todas as APIs. O sistema nunca escreve, cancela ou altera pedidos.

---

## 2. ARQUITETURA MODULAR — REGRA DE OURO

Cada plataforma é um arquivo independente em `src/platforms/`. Mudar ML não afeta Amazon. Mudar Amazon não afeta Leroy.

```
src/
  erp/
    olist.py              ← conector Tiny/Olist (✅ funcionando)
  platforms/
    mercado_livre.py      ← conector ML (✅ funcionando — token persistence Supabase)
    shopee.py             ← conector Shopee (✅ funcionando — token persistence Supabase)
    amazon.py             ← pendente
    leroy_merlin.py       ← pendente
    nuvemshop.py          ← pendente
    magalu.py             ← pendente (fallback)
    madeira_madeira.py    ← pendente (aguarda token)
  pipeline.py             ← orquestrador incremental (novos + reconciliação Shopee 45 dias)
  controle.py             ← estado do pipeline (Supabase config + fallback .controle.json)
  calculator.py           ← fórmulas de margem (não modificar)
  custos.py               ← lê data/custos.json (não modificar)
  detector_plataforma.py  ← detecta plataforma pelo pedido Tiny
  database.py             ← persistência exclusiva no Supabase
config/
  taxas.yaml              ← percentuais e taxas configuráveis (editável no dashboard)
data/
  custos.json             ← custo e embalagem por SKU (277 SKUs)
app/
  main.py                 ← dashboard Streamlit (abas: Margens | ⚙️ Configurações)
rodar.py                  ← CLI: D-1 automático | --desde | --ate | --so-reconciliar
.github/
  workflows/
    pipeline.yml          ← GitHub Actions: cron 00h Brasília + workflow_dispatch
```

**Regra de mudança segura:**
1. Identificar qual arquivo precisa mudar
2. Rodar testes do módulo antes de mexer
3. Fazer a mudança
4. Rodar testes do módulo + pipeline
5. Nunca alterar dois módulos ao mesmo tempo

### Contrato da Interface de Plataforma

Toda plataforma em `src/platforms/` DEVE expor exatamente uma função pública:

```python
def obter_vliquido(num_pedido_ecommerce: str, **kwargs) -> dict:
```

**Retorno obrigatório (4 campos):**
| Campo | Tipo | Descrição |
|---|---|---|
| `v_liquido` | `float \| None` | Valor líquido real; `None` se não disponível |
| `plataforma` | `str` | Nome da plataforma (ex: `'Shopee'`) |
| `canal` | `str` | Sempre `'E-commerce'` para plataformas externas |
| `v_liquido_estimado` | `bool` | `True` quando calculado por fallback |

**Arquivo de testes obrigatório:** `tests/test_{nome_arquivo}.py` (ex: `tests/test_shopee.py`)

Mudanças em uma plataforma **não podem** exigir alterações em `pipeline.py`, `calculator.py`, `custos.py`, `database.py` ou `detector_plataforma.py`. Exceções exigem registro neste PRD antes de implementadas.

**Exceções registradas:** nenhuma ativa.

### Core Compartilhado — Camadas Estáveis

Os arquivos abaixo são estabilizados e compartilhados por todas as plataformas. **Não modificar sem justificativa explícita registrada neste PRD:**

| Arquivo | Responsabilidade |
|---|---|
| `src/calculator.py` | Fórmulas de margem |
| `src/custos.py` | Leitura de custos/embalagem por SKU |
| `src/database.py` | Persistência exclusiva no Supabase |
| `src/detector_plataforma.py` | Detecção de plataforma pelo pedido Tiny |
| `src/pipeline.py` | Orquestração central |
| `config/taxas.yaml` | Percentuais e taxas configuráveis |

---

## 3. CONECTOR ERP — OLIST (✅ FUNCIONANDO)

**API:** `https://api.tiny.com.br/api2`
**Credencial:** `TINY_API_TOKEN` no `.env`

### Rate limit
- Intervalo entre requisições: `1.0s`
- Se receber erro "Bloqueada": aguarda `65s` e retenta (máx. 5 tentativas)

### Como buscar pedidos (`buscar_pedidos`)
Pesquisa as **3 situações** para não perder pedidos em trânsito, deduplicando por `id_erp`:
```
Faturado → Enviado → Entregue
```
Endpoint: `pedidos.pesquisa.php` com `dataInicial`, `dataFinal`, `situacao`, `pagina`

### Como buscar detalhe (`buscar_detalhe_pedido`)
Endpoint: `pedido.obter.php` com `id`

**Atenção crítica:** o campo `ecommerce` na resposta do detalhe é um **dict**, não string:
```python
ecommerce_raw = pedido.get('ecommerce', '')
if isinstance(ecommerce_raw, dict):
    ecommerce = ecommerce_raw.get('nomeEcommerce', '')
else:
    ecommerce = str(ecommerce_raw or '')
```

**Chave de cruzamento:** `numero_ecommerce` do Tiny = número do pedido na plataforma (ex: ID do pedido no ML)

### Como buscar NF (`buscar_nota_fiscal`)
Endpoint: `nota.fiscal.obter.php` com `id`
Retorna `valores_por_sku` — valor unitário real da nota por SKU (usado como V.NF)

---

## 4. ARQUITETURA DO PIPELINE — INCREMENTAL + DIÁRIO

O pipeline é incremental: a cada execução processa apenas o delta (pedidos novos do dia anterior + pendentes), nunca reprocessa o que já tem dado definitivo.

### Execução automática
`rodar.py` sem argumentos executa em modo automático:
- **Datas a processar:** D-1 (ontem) + catch-up de até 7 dias caso execuções anteriores tenham sido puladas
- **Reconciliação Shopee:** executada ao final, uma única vez por rodada
- **Registro de progresso:** cada data processada com sucesso é salva imediatamente (tolerante a falhas parciais)

### Estado persistente (`src/controle.py`)

Estado armazenado na tabela `config` do Supabase (chave `ultima_data_executada`).
Fallback automático para `.controle.json` local quando Supabase não disponível (dev offline).

```
Supabase config → chave: 'ultima_data_executada' | valor: '2026-05-14'
```

**`datas_para_processar(desde_arg, ate_arg)`** retorna lista de datas ISO a processar:
- Modo automático (sem args): `ultima_data_executada + 1 dia` até D-1, máximo 7 dias de catch-up
- Modo manual (`--desde`/`--ate`): intervalo exato sem limite de dias

### Fases de execução (por data)

**Fase 1 — Novos pedidos (Tiny incremental)**
- Busca pedidos no Tiny para a data específica (DD/MM/YYYY = DD/MM/YYYY — uma data por vez)
- Filtra `id_erp` já existentes para aquela data via `buscar_ids_por_data(data_iso)` — muito mais eficiente que buscar todos os IDs do banco
- Resultado: lista de pedidos novos a processar

**Fase 2 — V.LIQUIDO Mercado Livre (bulk corrigido)**
- Busca V.LIQUIDO de todos os pedidos ML novos via `/collections/search?order_id={id}`
- Flex (`logistic_type=self_service`): `total_amount − taxa_fixa_flex` — sem chamada de collections
- Full/Padrão: `/collections/search` individual por order_id (garante dado certo)
- Fallback para pack_id quando `numero_ecommerce` é um pack

**Fase 3 — V.LIQUIDO Shopee**
- Pedidos novos Shopee: verifica `order_status` via `get_order_detail`
  - `COMPLETED` → `get_escrow_detail` → V.LIQUIDO real, `v_liquido_estimado=False`
  - Demais status → estimativa: `v_bruto × (1 − shopee.taxa_comissao)`, `v_liquido_estimado=True`
- Estimativa para Shopee Flex: deduz também `shopee_flex.taxa_fixa`

**Fase 4 — Reconciliação Shopee pendentes**
- Busca pedidos Shopee com `v_liquido_estimado=1` nos últimos **45 dias** (`buscar_shopee_pendentes_recentes(dias=45)`)
- Para cada um: checa se `order_status` virou `COMPLETED`
  - Sim → substitui estimativa pelo escrow real via `atualizar_shopee_reconciliado()` (UPDATE cirúrgico — não sobrescreve campos não relacionados)
  - Não → mantém estimativa
- Pedidos com mais de 45 dias sem fechar são ignorados (prazo esgotado)

**Fase 5 — Gravação**
- `upsert_pedidos()` — `ON CONFLICT(id_erp, sku)` garante idempotência

### Deduplicação de itens
`_deduplicar_itens()` agrupa itens com mesmo SKU somando quantidades. Garante unicidade por `(id_erp, sku)`.

### Distribuição proporcional
`_distribuir_proporcional(item, todos_itens, total)` distribui V.BRUTO e V.LIQUIDO pelo peso `valor_unitario × quantidade` de cada SKU. Quando `total=0` ou `total=None`, usa `valor_unitario × quantidade` direto.

### Tempo estimado de execução

| Cenário | Chamadas Tiny | Tempo estimado |
|---|---|---|
| Primeira execução (histórico) | ~500 pedidos | 8–12 min |
| Execução diária (delta D-1) | ~15–30 pedidos | 1–3 min |

---

## 5. CONECTOR MERCADO LIVRE (✅ FUNCIONANDO)

**Credenciais estáticas no `.env` / GitHub Secrets:** `ML_APP_ID`, `ML_CLIENT_SECRET`, `ML_SELLER_ID`
**Tokens rotativos:** `ML_ACCESS_TOKEN`, `ML_REFRESH_TOKEN` — gerenciados automaticamente (ver abaixo)

### Renovação e persistência de token

Token expira periodicamente. A cada requisição com status 401, o sistema renova via `refresh_token`.

**Persistência pós-renovação (`_persistir_token`):**
- Salva sempre na tabela `config` do Supabase (`ML_ACCESS_TOKEN`, `ML_REFRESH_TOKEN`)
- Também atualiza o `.env` local se o arquivo existir (dev local)

**Carregamento na inicialização do módulo:**
1. Lê tokens do ambiente (`.env` ou variáveis de ambiente do Actions)
2. Sobrescreve com valores do Supabase `config` se disponíveis (sempre mais frescos após rotação)

Resultado: tokens rotacionam corretamente em GitHub Actions sem nenhum `.env`.

### Estratégia de V.LIQUIDO: por order_id

```
1. GET /packs/{num}  → tenta resolver como pack (pode retornar lista de order_ids)
   Se falhar: usa num_pedido diretamente como order_id

2. Para cada order_id:
   GET /orders/{order_id}  → logistic_type + total_amount

3. Calcular V.LIQUIDO:
   Flex (self_service):  total_amount − taxa_fixa_flex   → v_liquido_estimado=False
   Full (fulfillment):   GET /collections/search?order_id={id}  → net_received_amount
   Padrão (outros):      GET /collections/search?order_id={id}  → net_received_amount
```

**Plataformas geradas:**
| logistic_type | plataforma | canal |
|---|---|---|
| self_service | Mercado Livre Flex | E-commerce |
| fulfillment | Mercado Livre Full | E-commerce |
| outros | Mercado Livre | E-commerce |

---

## 6. CONECTOR SHOPEE (✅ FUNCIONANDO)

**Credenciais estáticas no `.env` / GitHub Secrets:** `SHOPEE_PARTNER_ID`, `SHOPEE_PARTNER_KEY`, `SHOPEE_SHOP_ID`
**Tokens rotativos:** `SHOPEE_ACCESS_TOKEN`, `SHOPEE_REFRESH_TOKEN` — gerenciados automaticamente (mesmo padrão do ML)

### Renovação e persistência de token
Mesmo padrão do ML: `_persistir_token()` salva no Supabase + `.env` local. Inicialização carrega do Supabase se disponível.

### Estratégia de V.LIQUIDO (`obter_vliquido`)

```
1. GET /order/get_order_detail → order_status + shipping_carrier

2. Se order_status == 'COMPLETED':
   GET /payment/get_escrow_detail → escrow_amount (valor real confirmado)
   → v_liquido = escrow_amount (− taxa_fixa se Flex)
   → v_liquido_estimado = False

3. Se order_status != 'COMPLETED' (pedido em trânsito):
   → v_liquido = None, aguardando_escrow = True
   → Pipeline calcula estimativa: v_bruto × (1 − shopee.taxa_comissao)
   → Shopee Flex: deduz também shopee_flex.taxa_fixa
   → v_liquido_estimado = True
   → Reconciliação diária por até 45 dias: verifica se virou COMPLETED
```

**Subtipos por carrier:**
| shipping_carrier | plataforma | Dedução extra |
|---|---|---|
| Entrega Direta | Shopee Flex | − shopee_flex.taxa_fixa (editável no dashboard) |
| Shopee Xpress | Shopee | nenhuma |
| outros | Shopee | nenhuma |

---

## 7. DETECÇÃO DE PLATAFORMA (`detector_plataforma.py`)

Baseada no campo `ecommerce` do Tiny (texto) e `forma_pagamento`:

| Condição | plataforma | canal |
|---|---|---|
| ecommerce contém "mercado livre" | Mercado Livre | E-commerce |
| ecommerce contém "shopee" | Shopee | E-commerce |
| ecommerce contém "amazon" | Amazon | E-commerce |
| ecommerce contém "leroy" | Leroy Merlin | E-commerce |
| ecommerce contém "magalu" ou "magazine" | Magalu | E-commerce |
| ecommerce contém "madeira" | MadeiraMadeira | E-commerce |
| Pix/Boleto + marcador "piscinas" | LBG | Piscinas |
| Pix/Boleto + marcador "construtor" | LBG | Construtor |
| Pix/Boleto sem marcador | LBG | Revenda |

**Nota:** Nuvemshop (site próprio) ainda é detectado como LBG/Revenda — conector pendente.

---

## 8. BANCO DE DADOS — SUPABASE (EXCLUSIVO)

**Projeto:** `cbjthcuqstpoogooetpe.supabase.co`
**Credenciais:** `SUPABASE_URL`, `SUPABASE_KEY` (no `.env` local / GitHub Secrets no Actions)

**Upsert:** `ON CONFLICT(id_erp, sku)` — reprocessar o mesmo pedido nunca cria duplicata.

**Modo:** Supabase exclusivo. Não há fallback SQLite. Se `SUPABASE_URL`/`SUPABASE_KEY` estiverem ausentes, o sistema falha imediatamente com mensagem clara.

### Tabelas

**`pedidos`** — tabela principal (gerenciada via painel Supabase):
| Coluna | Tipo | Descrição |
|---|---|---|
| id | serial | PK auto |
| id_erp | text | ID do pedido no Tiny |
| sku | text | SKU do item |
| data_venda | text | DD/MM/YYYY (formato Tiny) |
| ... | ... | demais campos de margem |

Chave única: `(id_erp, sku)`

**`config`** — tabela de estado e tokens (key-value):
```sql
CREATE TABLE config (
  chave TEXT PRIMARY KEY,
  valor TEXT,
  atualizado_em TIMESTAMPTZ DEFAULT now()
);
```

Chaves usadas:
| chave | conteúdo |
|---|---|
| `ultima_data_executada` | Última data processada com sucesso (`YYYY-MM-DD`) |
| `ML_ACCESS_TOKEN` | Token ML rotacionado mais recente |
| `ML_REFRESH_TOKEN` | Refresh token ML mais recente |
| `SHOPEE_ACCESS_TOKEN` | Token Shopee rotacionado mais recente |
| `SHOPEE_REFRESH_TOKEN` | Refresh token Shopee mais recente |

### Paginação
Todas as queries usam `_paginar()` — busca automática de todas as páginas (limite padrão Supabase: 1.000 linhas por request).

### Funções principais de `database.py`

| Função | Descrição |
|---|---|
| `upsert_pedidos(pedidos)` | Grava/atualiza pedidos (chunks de 500) |
| `buscar_ids_por_data(data_iso)` | IDs do dia específico — para skip-check eficiente |
| `buscar_shopee_pendentes_recentes(dias=45)` | Pedidos Shopee estimados nos últimos N dias |
| `atualizar_shopee_reconciliado(...)` | UPDATE cirúrgico: só V.LIQUIDO + margem |
| `buscar_config(chave)` | Lê valor da tabela config |
| `salvar_config(chave, valor)` | Upsert na tabela config |
| `buscar_resumo()` | Agregados por plataforma para exibição no terminal |

---

## 9. AUTOMAÇÃO — GITHUB ACTIONS

**Arquivo:** `.github/workflows/pipeline.yml`

**Execução automática:** `cron: '0 3 * * *'` — todo dia às 00h00 Brasília (UTC-3)

**Execução manual** (`workflow_dispatch`) — parâmetros:
| Parâmetro | Descrição |
|---|---|
| `desde` | Data início DD/MM/YYYY (opcional) |
| `ate` | Data fim DD/MM/YYYY (opcional, padrão: ontem) |
| `so_reconciliar` | Boolean — apenas reconcilia Shopee sem buscar novos |

**GitHub Secrets obrigatórios:**
```
SUPABASE_URL, SUPABASE_KEY
ML_APP_ID, ML_CLIENT_SECRET, ML_SELLER_ID
ML_ACCESS_TOKEN, ML_REFRESH_TOKEN      ← iniciais; Supabase assume após primeiro run
SHOPEE_PARTNER_ID, SHOPEE_PARTNER_KEY, SHOPEE_SHOP_ID
SHOPEE_ACCESS_TOKEN, SHOPEE_REFRESH_TOKEN  ← iniciais; Supabase assume após primeiro run
```

**Timeout:** 30 minutos

---

## 10. FÓRMULAS DE CÁLCULO

```
IMPOSTOS     = V_NF × 13%
COMISSAO     = V_LIQUIDO × 4%
EMBALAGEM    = buscar_embalagem(SKU) × quantidade
CUSTO_PROD   = buscar_custo(SKU) × quantidade
MARGEM_RS    = V_LIQUIDO − IMPOSTOS − COMISSAO − EMBALAGEM − CUSTO_PROD
MARGEM_PCT   = MARGEM_RS / CUSTO_PROD
```

Quando V.LIQUIDO é `None` (plataforma sem conector): `COMISSAO`, `MARGEM_RS` e `MARGEM_PCT` ficam `None`. `IMPOSTOS`, `EMBALAGEM` e `CUSTO_PROD` são calculados normalmente.

---

## 11. PLANILHA DE CUSTOS

**Google Sheets ID:** `1K-typUs7IATurbFHHI_5BdvnXRRhc2_jHikLSmAGQ3g`
**Arquivo local:** `data/custos.json` (277 SKUs)

| Coluna | Campo |
|---|---|
| A | SKU |
| D | Custo unitário (R$) — manual |
| F | Custo embalagem (R$) — manual |

Para sincronizar manualmente: `python src/custos_sync.py`

---

## 12. CONFIGURAÇÃO DE TAXAS (`config/taxas.yaml`)

```yaml
impostos: 0.13           # 13% sobre V.NF
comissao: 0.04           # 4% sobre V.LIQUIDO

mercado_livre_flex:
  taxa_fixa: 14.99       # R$ por pedido Flex — editável no dashboard

shopee:
  taxa_comissao: 0.10    # 10% estimativa para pedidos em trânsito

shopee_flex:
  taxa_fixa: 9.99        # R$ por pedido Entrega Direta — editável no dashboard

amazon:
  taxa_comissao: 0.13
magalu:
  taxa_comissao: 0.18
  taxa_fixa: 6.00
leroy_merlin:
  taxa_comissao: 0.18
madeira_madeira:
  taxa_comissao: 0.176

devolucao:
  taxa_avaria: 0.10      # 10% do custo produto
```

**Regra:** mudar taxa = editar só este arquivo, nunca o código.
**Taxas editáveis no dashboard:** `mercado_livre_flex.taxa_fixa`, `shopee_flex.taxa_fixa`, `shopee.taxa_comissao`.

---

## 13. STATUS DAS PLATAFORMAS

| Plataforma | V.LIQUIDO | Status |
|---|---|---|
| Mercado Livre Flex | `total_amount − taxa_fixa_flex` (R$14,99) | ✅ Funcionando |
| Mercado Livre Full/Padrão | `net_received_amount` via `/collections/search?order_id` | ✅ Funcionando |
| LBG direto (Piscinas/Construtor/Revenda) | = V.BRUTO | ✅ Funcionando |
| Shopee COMPLETED | `escrow_amount` real via `get_escrow_detail` | ✅ Funcionando |
| Shopee em trânsito | Estimativa: `v_bruto × (1 − 10%)`, reconcilia por 45 dias | ✅ Estimado |
| Shopee Flex em trânsito | Estimativa: `v_bruto × 0,90 − R$9,99`, reconcilia por 45 dias | ✅ Estimado |
| Amazon | Financial Events API | ⏳ Pendente (Entrega 4) |
| Leroy Merlin | Mirakl API | ⏳ Pendente (Entrega 4) |
| Nuvemshop | API + cross-reference | ⏳ Pendente (Entrega 5) |
| Magalu | Fallback: `subtotal × 0,82 − R$6,00` | ⏳ Pendente (Entrega 6) |
| MadeiraMadeira | Fallback: `subtotal × 0,824` | ⏳ Aguarda token válido |

---

## 14. PRÓXIMAS ENTREGAS

```
✅ Entrega 3 — Refatoração ML + Shopee (arquitetura incremental)
✅ Entrega 7 — Automação diária (GitHub Actions + rotina D-1 + token persistence)

Entrega 4 — Amazon + Leroy Merlin
  ├── src/platforms/amazon.py
  │     Financial Events API: soma Principal − ItemFeeList
  │     Fallback: V_BRUTO × (1 − 0,13) quando sem liquidação
  └── src/platforms/leroy_merlin.py
        GET /api/orders?order_ids={NUM_PEDIDO_ECOMMERCE}
        V.LIQUIDO = total_price − total_commission − shipping_price

Entrega 5 — Nuvemshop (site próprio)
  └── src/platforms/nuvemshop.py
        Cross-reference: valor ±R$2 e data ±1 dia
        V.LIQUIDO a confirmar (provavelmente = V.BRUTO)

Entrega 6 — Magalu + MadeiraMadeira
  ├── src/platforms/magalu.py
  │     V.LIQUIDO = subtotal × (1 − 0,18) − R$6,00
  │     Marcar v_liquido_estimado = True
  └── src/platforms/madeira_madeira.py
        (aguarda token válido)
```

---

## 15. PERGUNTAS EM ABERTO

| # | Pergunta | Status |
|---|---|---|
| 1 | Nuvemshop: V.LIQUIDO = V.BRUTO ou tem desconto? | ⏳ Confirmar |
| 2 | Shopee/Amazon/Magalu Flex: como diferenciar padrão vs Flex? | ⏳ Confirmar quando integrar |
| 3 | Período histórico: importar dados de meses anteriores? A partir de quando? | ⏳ Confirmar |
| 4 | Devoluções: como identificar em cada plataforma além do ML? | ⏳ Confirmar por plataforma |

---

*Última atualização: 2026-05-15 — v4.0*
