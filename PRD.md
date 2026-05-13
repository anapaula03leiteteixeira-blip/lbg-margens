# PRD — Sistema de Controle de Margens La Bella Griffe
> **FONTE DE VERDADE ÚNICA.** Leia este arquivo antes de qualquer implementação.
> Qualquer mudança de regra deve ser registrada aqui ANTES de mexer no código.
>
> Versão: 2.0 — 2026-05-13

---

## 1. VISÃO GERAL

Pipeline automático que coleta pedidos de todos os canais de venda, consolida em banco único e calcula margem real por pedido × SKU.

**Tecnologia:**
- Python (pipeline local)
- Supabase — PostgreSQL gratuito na nuvem (banco de dados)
- Streamlit Community Cloud — dashboard web gratuito

**Fluxo:**
```
rodar.py (local) → Supabase → Streamlit Cloud (dashboard)
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
    mercado_livre.py      ← conector ML (✅ funcionando)
    amazon.py             ← pendente
    leroy_merlin.py       ← pendente
    nuvemshop.py          ← pendente
    shopee.py             ← pendente (aguarda credenciais)
    magalu.py             ← pendente (fallback)
    madeira_madeira.py    ← pendente (aguarda token)
  pipeline.py             ← orquestrador (não modificar)
  calculator.py           ← fórmulas de margem (não modificar)
  custos.py               ← lê data/custos.json (não modificar)
  detector_plataforma.py  ← detecta plataforma pelo pedido Tiny
  database.py             ← grava no Supabase
config/
  taxas.yaml              ← percentuais e taxas configuráveis
data/
  custos.json             ← custo e embalagem por SKU (277 SKUs)
app/
  main.py                 ← dashboard Streamlit
rodar.py                  ← script de execução manual
migrar_sqlite_supabase.py ← migração única (já executada)
```

**Regra de mudança segura:**
1. Identificar qual arquivo precisa mudar
2. Rodar testes do módulo antes de mexer
3. Fazer a mudança
4. Rodar testes do módulo + pipeline
5. Nunca alterar dois módulos ao mesmo tempo

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

## 4. CONECTOR MERCADO LIVRE (✅ FUNCIONANDO)

**Credenciais no `.env`:** `ML_APP_ID`, `ML_CLIENT_SECRET`, `ML_ACCESS_TOKEN`, `ML_REFRESH_TOKEN`, `ML_SELLER_ID`

### Renovação automática de token
Token expira periodicamente. A cada requisição com status 401, o sistema renova automaticamente via `refresh_token` e atualiza o `.env`.

### Fluxo para obter V.LIQUIDO (`obter_vliquido`)

**Passo 1 — Resolver IDs:**
O `numero_ecommerce` do Tiny pode ser um `pack_id` (pedido com múltiplos itens) ou um `order_id` direto.
```
GET /packs/{num_pedido}
  → se retornar orders → lista de order_ids
  → se falhar → usar num_pedido como order_id direto
```

**Passo 2 — Detectar tipo:**
```
order.shipping.logistic_type == 'self_service' → Flex
order.shipping.logistic_type == 'fulfillment'  → Full
caso contrário                                 → Padrão
```

**Passo 3 — Calcular V.LIQUIDO:**
```
Flex:          total_amount − R$14,90 (taxa_fixa configurável em taxas.yaml)
Full/Padrão:   net_received_amount via GET /collections/search?order_id={id}
```

**Plataformas geradas:**
| Tipo | plataforma | canal |
|---|---|---|
| flex | Mercado Livre Flex | E-commerce |
| full | Mercado Livre Full | E-commerce |
| padrao | Mercado Livre | E-commerce |

---

## 5. DETECÇÃO DE PLATAFORMA (`detector_plataforma.py`)

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

## 6. BANCO DE DADOS — SUPABASE

**Projeto:** `cbjthcuqstpoogooetpe.supabase.co`
**Credenciais no `.env`:** `SUPABASE_URL`, `SUPABASE_KEY`

**Upsert:** `ON CONFLICT(id_erp, sku)` — reprocessar o mesmo pedido nunca cria duplicata.

**`database.py` — modo dual:**
- Se `SUPABASE_URL` e `SUPABASE_KEY` estiverem no `.env` → usa Supabase
- Se não → usa SQLite local `lbg.db` (apenas para desenvolvimento offline)

---

## 7. FÓRMULAS DE CÁLCULO

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

## 8. PLANILHA DE CUSTOS

**Google Sheets ID:** `1K-typUs7IATurbFHHI_5BdvnXRRhc2_jHikLSmAGQ3g`
**Arquivo local:** `data/custos.json` (277 SKUs)

| Coluna | Campo |
|---|---|
| A | SKU |
| D | Custo unitário (R$) — manual |
| F | Custo embalagem (R$) — manual |

Para sincronizar manualmente: `python src/custos_sync.py`

---

## 9. CONFIGURAÇÃO DE TAXAS (`config/taxas.yaml`)

```yaml
impostos: 0.13           # 13% sobre V.NF
comissao: 0.04           # 4% sobre V.LIQUIDO

mercado_livre_flex:
  taxa_fixa: 14.90       # R$ por pedido Flex

amazon:
  taxa_comissao: 0.13    # fallback quando sem Financial Events
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

---

## 10. STATUS DAS PLATAFORMAS

| Plataforma | V.LIQUIDO | Status |
|---|---|---|
| Mercado Livre (padrão/Full/Flex) | API real | ✅ Funcionando |
| LBG direto (Piscinas/Construtor/Revenda) | = V.BRUTO | ✅ Funcionando |
| Amazon | Financial Events API | ⏳ Pendente (Entrega 3) |
| Leroy Merlin | Mirakl API | ⏳ Pendente (Entrega 3) |
| Nuvemshop | API + cross-reference | ⏳ Pendente (Entrega 4) |
| Shopee | API | ⏳ Aguarda aprovação de conta (submetido 30/04/2026) |
| Magalu | Fallback: `subtotal × 0,82 − R$6,00` | ⏳ Pendente (Entrega 6) |
| MadeiraMadeira | Fallback: `subtotal × 0,824` | ⏳ Aguarda token válido |

---

## 11. PRÓXIMAS ENTREGAS

```
Entrega 3 — Amazon + Leroy Merlin
  ├── src/platforms/amazon.py
  │     Financial Events API: soma Principal − ItemFeeList
  │     Fallback: V_BRUTO × (1 − 0,13) quando sem liquidação
  └── src/platforms/leroy_merlin.py
        GET /api/orders?order_ids={NUM_PEDIDO_ECOMMERCE}
        V.LIQUIDO = total_price − total_commission − shipping_price

Entrega 4 — Nuvemshop (site próprio)
  └── src/platforms/nuvemshop.py
        Cross-reference: valor ±R$2 e data ±1 dia
        V.LIQUIDO a confirmar (provavelmente = V.BRUTO)

Entrega 5 — Shopee e MadeiraMadeira
  (quando credenciais disponíveis)

Entrega 6 — Magalu fallback
  └── src/platforms/magalu.py
        V.LIQUIDO = subtotal × (1 − 0,18) − R$6,00
        Marcar v_liquido_estimado = True

Entrega 7 — Automação diária
  Agendar rodar.py para executar todo dia automaticamente
```

---

## 12. PERGUNTAS EM ABERTO

| # | Pergunta | Status |
|---|---|---|
| 1 | Nuvemshop: V.LIQUIDO = V.BRUTO ou tem desconto? | ⏳ Confirmar |
| 2 | Shopee/Amazon/Magalu Flex: como diferenciar padrão vs Flex? | ⏳ Confirmar quando integrar |
| 3 | Período histórico: importar dados de meses anteriores? A partir de quando? | ⏳ Confirmar |
| 4 | Devoluções: como identificar em cada plataforma além do ML? | ⏳ Confirmar por plataforma |

---

*Última atualização: 2026-05-13*
