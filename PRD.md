# PRD — Sistema de Controle de Margens La Bella Griffe
> **FONTE DE VERDADE ÚNICA.** Leia este arquivo antes de qualquer implementação.
> Qualquer mudança de regra deve ser registrada aqui ANTES de mexer no código.
>
> Versão: 1.2 — 2026-05-12
> Localização do projeto: `C:\Users\DELL\Desktop\Sistema - LBG\`
> Código de referência (arquivo, não usar sem permissão): `C:\Users\DELL\margem-multicanal\`

---

## 1. VISÃO GERAL

**O que é:** Pipeline automático que coleta pedidos de todos os canais de venda da La Bella Griffe, consolida em um banco de dados único (BANCO DE DADOS MASTER) e calcula a margem real por pedido × SKU.

**Por que existe:** Hoje o processo é manual — a equipe consolida dados de ~10 plataformas. O sistema elimina esse trabalho manual.

**Tecnologia:**
- Linguagem: Python
- Banco de dados: **Supabase** (PostgreSQL gratuito na nuvem) — dados acessíveis de qualquer lugar
- Dashboard web: **Streamlit Community Cloud** (gratuito) — sistema online que funcionários acessam via link
- Credenciais: arquivo `.env` na raiz do projeto (nunca no código)

**Fluxo de dados:**
```
Pipeline Python (local) → Supabase (banco online) → Streamlit (sistema web)
                                                          ↓
                                               Funcionários via navegador
```

**Custos:** R$ 0. Supabase free tier + Streamlit Community Cloud são permanentemente gratuitos.

**Permissões:** SOMENTE LEITURA em todos os ERPs e marketplaces. O sistema NUNCA escreve, cancela ou altera pedidos nas plataformas.

---

## 2. ARQUITETURA MODULAR — REGRA DE OURO

> **Cada plataforma é um módulo independente.** Mudar o Shopee não afeta o Mercado Livre. Mudar o Mercado Livre não afeta o Amazon. O pipeline central não sabe como cada conector funciona — só recebe o resultado.

### Estrutura de pastas

```
C:\Users\DELL\Desktop\Sistema - LBG\
  PRD.md                        ← este arquivo (fonte de verdade)
  .env                          ← credenciais (nunca versionar)
  .env.example                  ← template de variáveis sem valores
  config/
    taxas.yaml                  ← todos os percentuais e valores configuráveis
  src/
    platforms/
      mercado_livre.py          ← conector ML (primeira entrega)
      shopee.py                 ← conector Shopee
      amazon.py                 ← conector Amazon
      leroy_merlin.py           ← conector Leroy Merlin
      magalu.py                 ← conector Magazine Luiza
      madeira_madeira.py        ← conector MadeiraMadeira
      nuvemshop.py              ← conector Nuvemshop (site próprio)
    erp/
      olist.py                  ← conector Tiny/Olist ERP
    pipeline.py                 ← orquestrador central (não muda)
    calculator.py               ← cálculos de margem (não muda)
    custos.py                   ← leitura da planilha de custos (não muda)
    database.py                 ← gravação no Supabase (PostgreSQL)
  app/
    main.py                     ← dashboard Streamlit (sistema web)
  tests/
    test_mercado_livre.py
    test_calculator.py
    test_pipeline.py
```

### Contrato de cada conector de plataforma

Todo conector em `src/platforms/` deve implementar a mesma interface:

```
Entrada:  número do pedido (string)
Saída:    valor líquido em R$ (float) OU None se não disponível
```

O pipeline central chama qualquer conector da mesma forma. Se a API de uma plataforma mudar, só o arquivo dessa plataforma é alterado — o restante não sabe que aconteceu nada.

### Regra de mudança segura

```
1. Identificar qual arquivo precisa mudar
2. Rodar testes desse módulo antes de mexer
3. Fazer a mudança
4. Rodar testes do módulo + testes do pipeline
5. Só commitar se tudo passar
6. NUNCA alterar dois módulos ao mesmo tempo
```

---

## 3. FONTE PRINCIPAL DE DADOS — ERP

**ERP utilizado:** Olist (antigo Tiny ERP — mesma API)

**Relatório de origem:** Controle de Margem
- Caminho: INÍCIO → VENDAS → RELATÓRIOS → PERSONALIZADOS → CONTROLE DE MARGEM
- Selecionar período desejado

**Campos extraídos do ERP:**

| Campo no ERP | Campo no Master | Observação |
|---|---|---|
| Data da Venda | DATA_VENDA | |
| ID ERP | ID_ERP | |
| N. NF | NUM_NF | |
| Número do pedido no e-commerce | NUM_PEDIDO_ECOMMERCE | Chave de cruzamento com plataformas |
| Nome do cliente | CLIENTE | |
| Código (SKU) | SKU | Cada SKU = uma linha |
| Preço total | V_BRUTO | |
| Quantidade de produtos | QUANTIDADE | |
| E-commerce | ECOMMERCE | Nome da plataforma conforme ERP |
| Total Produtos | V_NF | |
| Data de Emissão | DATA_EMISSAO | |
| UF | UF | |
| Situação da venda | SITUACAO | |

> **Regra:** Cada SKU de um pedido = uma linha separada no banco. Um pedido com 3 SKUs diferentes = 3 linhas.

---

## 4. CANAIS E PLATAFORMAS

| PLATAFORMA | CANAL | Como detectar |
|---|---|---|
| LBG | PISCINAS | Tag "piscinas" no ERP |
| LBG | CONSTRUTORA | Tag "construtor" no ERP |
| Nuvemshop | SITE | Cross-reference com API Nuvemshop |
| Mercado Livre | E-COMMERCE | Campo ecommerce = ML, entrega padrão |
| Mercado Livre Full | E-COMMERCE | Estoque no galpão ML |
| Mercado Livre Flex | E-COMMERCE | Campo "Forma de entrega" = "Mercado Envios Flex" |
| Shopee | E-COMMERCE | Campo ecommerce = Shopee |
| Shopee Flex | E-COMMERCE | A confirmar como diferenciar |
| Amazon | E-COMMERCE | Campo ecommerce = Amazon |
| Amazon Flex | E-COMMERCE | A confirmar como diferenciar |
| Leroy Merlin | E-COMMERCE | Campo ecommerce = Leroy |
| Magazine Luiza | E-COMMERCE | Campo ecommerce = Magalu |
| Magazine Luiza Flex | E-COMMERCE | A confirmar como diferenciar |
| LBG | REVENDA | Pix/Boleto + CNPJ, sem tag específica |
| Madeira Madeira | E-COMMERCE | Campo ecommerce = MadeiraMadeira |

---

## 5. ESTRUTURA DO BANCO DE DADOS MASTER

### Sistema web (Streamlit) — Telas esperadas

| Tela | Conteúdo | Quem usa |
|---|---|---|
| Margem | Pedidos com filtro por mês/plataforma/canal, margem calculada | Todos |
| Devoluções | Pedidos devolvidos, campo para marcar condição (editar) | Equipe operacional |
| Custos | Custo por SKU, campo para atualizar manualmente | Gestão |
| Histórico | Consulta de meses anteriores | Gestão |

---

### Tabela principal: `pedidos`

| Coluna | Tipo | Fonte | Observação |
|---|---|---|---|
| id | PK auto | Sistema | |
| data_venda | DATE | ERP | |
| id_erp | TEXT | ERP | |
| num_nf | TEXT | ERP | |
| num_pedido_ecommerce | TEXT | ERP | Chave de cruzamento |
| cliente | TEXT | ERP | |
| sku | TEXT | ERP | |
| v_bruto | DECIMAL | ERP | |
| quantidade | INTEGER | ERP | |
| ecommerce | TEXT | ERP | |
| v_nf | DECIMAL | ERP | |
| data_emissao | DATE | ERP | |
| uf | TEXT | ERP | |
| situacao | TEXT | ERP | |
| v_liquido | DECIMAL | Conector plataforma | NULL se não disponível |
| plataforma | TEXT | Detectado | |
| canal | TEXT | Detectado | |
| impostos | DECIMAL | Calculado | 13% × V_NF |
| comissao | DECIMAL | Calculado | 4% × V_LIQUIDO |
| embalagem | DECIMAL | Tabela custos | |
| custo_produto | DECIMAL | Tabela custos | |
| margem_rs | DECIMAL | Calculado | Ver fórmula |
| margem_pct | DECIMAL | Calculado | Ver fórmula |
| devolucao | BOOLEAN | Detectado | |
| data_retorno | DATE | Plataforma | NULL se sem devolução |
| condicao_devolucao | TEXT | Manual | 'COM AVARIAS' / 'SEM AVARIAS' |
| custo_devolucao | DECIMAL | Calculado | Ver fórmula |
| status | TEXT | Sistema | 'ATIVO', 'CANCELADO', 'DEVOLVIDO' |
| criado_em | TIMESTAMP | Sistema | |
| atualizado_em | TIMESTAMP | Sistema | |

---

## 6. FÓRMULAS DE CÁLCULO

```
IMPOSTOS     = V_NF × 13%
COMISSAO     = V_LIQUIDO × 4%
EMBALAGEM    = buscar_embalagem(SKU) × QUANTIDADE
CUSTO_PROD   = buscar_custo(SKU) × QUANTIDADE
MARGEM_RS    = V_LIQUIDO − IMPOSTOS − COMISSAO − EMBALAGEM − CUSTO_PROD
MARGEM_PCT   = MARGEM_RS / CUSTO_PROD
```

> **Regra MARGEM %:** Denominador é CUSTO DO PRODUTO (retorno sobre custo).
> **Regra COMISSÃO:** 4% de V.LIQUIDO (não de V.BRUTO).

### Devolução com avarias
```
CUSTO_DEVOLUCAO = CUSTO_PROD + IMPOSTOS + (CUSTO_PROD × 10%)
```

### Devolução sem avarias
```
CUSTO_DEVOLUCAO = CUSTO_PROD × 10%
```

---

## 7. REGRAS DE V.LIQUIDO POR PLATAFORMA

> V.LIQUIDO = valor que a empresa efetivamente recebe após taxas e comissões do marketplace.

### Mercado Livre ✅ API disponível
- **Mercado Livre Flex:** `V_LIQUIDO = Total (BRL) − TAXA_FIXA_ML_FLEX`
  - Taxa padrão: R$ 14,90 (configurável em `config/taxas.yaml`)
- **Mercado Livre padrão / Full:** `V_LIQUIDO = Total (BRL)` via campo `net_received_amount`
- **Cruzamento:** `NUM_PEDIDO_ECOMMERCE` no ERP = número do pedido ML
  - Atenção: ERP pode armazenar `pack_id` (pedidos com múltiplos itens) — resolver via endpoint `/packs/{pack_id}` para obter `order_ids`
- **Relatório manual alternativo:** Minha conta → Vendas → Filtrar período → Exportar

### Amazon ✅ API disponível (SP-API)
- V.LIQUIDO via Financial Events API: soma `Principal` menos todas as fees (`ItemFeeList`)
- Inclui: comissão Amazon + frete Amazon DBA
- Pedidos recentes sem Financial Events (não liquidados): usar fallback → linha destacada
- **Fallback:** `V_BRUTO × (1 − AMAZON_TAXA_COMISSAO)` — sem dedução de frete
- Credenciais: `AMAZON_LWA_CLIENT_ID`, `AMAZON_LWA_CLIENT_SECRET`, `AMAZON_REFRESH_TOKEN` no `.env`
- Marketplace ID Brasil: `A2Q3Y263D00KWC`

### Leroy Merlin ✅ API disponível (Mirakl)
- **Endpoint correto:** `GET /api/orders?order_ids={NUM_PEDIDO_ECOMMERCE}` (não `/api/orders/{id}`)
- **Fórmula:** `total_price − total_commission − shipping_price`
- Campos na resposta: `total_price`, `total_commission`, `shipping_price`
- Credenciais: `LEROY_API_KEY`, `LEROY_BASE_URL` no `.env`
- **Fallback:** `V_BRUTO × (1 − LEROY_TAXA_COMISSAO)` → linha destacada

### Nuvemshop (site próprio) ✅ API disponível
- Pedidos Pix/Boleto sem campo ecommerce no ERP → identificar via cross-reference NS
- Cross-reference: compara valor total ±R$2 e data ±1 dia com API Nuvemshop
- `PLATAFORMA = Nuvemshop`, `CANAL = Site`
- Credenciais: `NUVEMSHOP_ACCESS_TOKEN`, `NUVEMSHOP_USER_ID` no `.env`
- V.LIQUIDO para site próprio: a confirmar (sem taxa marketplace?)

### Shopee ⏳ Aguardando aprovação de API
- Perfil Open Platform submetido em 30/04/2026 — aguardando aprovação
- V.LIQUIDO = em branco até ter credenciais (nunca estimar)
- Credenciais necessárias: `SHOPEE_PARTNER_ID`, `SHOPEE_PARTNER_KEY`, `SHOPEE_SHOP_ID`, `SHOPEE_ACCESS_TOKEN`

### Magazine Luiza ⚠️ Sem API disponível (por enquanto)
- **Fallback:** `Subtotal × (1 − 0.18) − R$6,00`
- Linhas Magalu com V.LIQUIDO estimado devem ser marcadas no banco (`v_liquido_estimado = TRUE`)

### Madeira Madeira ⚠️ Token inválido — necessita novo acesso
- Token atual sem acesso externo (API interna deles)
- **Ação necessária:** solicitar token válido ao suporte da Madeira Madeira
- **Fallback:** `subtotal_itens × (1 − MM_TAXA_COMISSAO)`
  - subtotal_itens = soma `valor_unitario × qtd` dos itens (sem frete)
  - `MM_TAXA_COMISSAO = 0.176` (17,6%)

### Vendas diretas LBG (Piscinas, Construtora, Revenda)
- `V_LIQUIDO = V_BRUTO` (sem taxa de marketplace)

---

## 8. PLANILHA DE CUSTOS

> Fonte de verdade para CUSTO PRODUTO e EMBALAGEM por SKU.
> Esta planilha é separada do banco de dados principal.

**Localização:** Google Sheets
**ID da planilha:** `1K-typUs7IATurbFHHI_5BdvnXRRhc2_jHikLSmAGQ3g`

**Colunas:**

| Col | Campo | Preenchimento |
|---|---|---|
| A | SKU | Automático (sistema) |
| B | Nome do produto | Automático (ERP) |
| C | Preço de venda | Informativo |
| D | Custo unitário (R$) | **Manual pela equipe** |
| E | Custo embalagem (R$) | **Manual pela equipe** |
| F | Data de atualização | Automático |

**Automações:**
1. SKU novo detectado no ERP → sistema adiciona linha com custo em branco
2. Todo dia 28 → snapshot da aba atual gravado como aba `Custos_YYYY-MM`
3. Início do mês → nova aba com os mesmos valores (para ajuste manual)

---

## 9. ARQUIVO DE CONFIGURAÇÃO — `config/taxas.yaml`

```yaml
# Impostos e cálculos
impostos: 0.13           # 13% sobre V.NF
comissao: 0.04           # 4% sobre V.LIQUIDO

# Mercado Livre
mercado_livre_flex:
  taxa_fixa: 14.90       # R$ — taxa fixa por pedido Flex

# Plataformas sem API (fallback)
amazon:
  taxa_comissao: 0.13    # fallback quando sem Financial Events
magalu:
  taxa_comissao: 0.18
  taxa_fixa: 6.00
leroy_merlin:
  taxa_comissao: 0.18
madeira_madeira:
  taxa_comissao: 0.176

# Devolução
devolucao:
  taxa_avaria: 0.10      # 10% do custo produto
```

> Mudar qualquer taxa: editar só este arquivo. Sem tocar no código.

---

## 10. AUTOMAÇÕES ESPERADAS

| Automação | Frequência | Descrição |
|---|---|---|
| Importar novos pedidos | Diária | Puxa ERP + enriquece V.LIQUIDO por plataforma |
| Detectar devoluções | Diária | Verifica pedidos devolvidos nas plataformas |
| Sincronizar custos | A cada importação | Recalcula margem do mês atual com custo atualizado |
| Fechar mês de custos | Dia 28 | Cria snapshot `Custos_YYYY-MM` |
| Adicionar SKUs novos | Ao detectar | SKU novo no ERP → linha nova na planilha de custos |

---

## 11. ORDEM DE IMPLEMENTAÇÃO (entregas modulares)

```
Entrega 1 — Fundação
  ├── Banco de dados (estrutura da tabela)
  ├── Conector ERP Olist (buscar pedidos)
  └── Calculator (fórmulas de margem)

Entrega 2 — Primeiro conector
  ├── Conector Mercado Livre (ML padrão + Full + Flex)
  └── Pipeline funcional para ML

Entrega 3 — Expansão
  ├── Conector Amazon
  └── Conector Leroy Merlin

Entrega 4 — Site próprio
  └── Conector Nuvemshop

Entrega 5 — Quando credenciais disponíveis
  ├── Conector Shopee (aguarda aprovação API)
  └── Conector MadeiraMadeira (aguarda token)

Entrega 6 — Fallbacks temporários
  └── Magalu (fallback até ter API)

Entrega 7 — Automação
  └── Agendamento diário + alertas
```

---

## 12. PERGUNTAS EM ABERTO (preencher antes de implementar cada entrega)

| # | Pergunta | Status |
|---|---|---|
| 1 | Banco de dados: SQLite (local) ou PostgreSQL (servidor)? | ✅ **SQLite** |
| 2 | Nuvemshop: V.LIQUIDO = V.BRUTO ou tem desconto? | ⏳ A confirmar |
| 3 | Shopee Flex: como diferenciar Shopee padrão vs Flex? | ⏳ A confirmar quando API aprovada |
| 4 | Amazon Flex: como diferenciar Amazon padrão vs Flex? | ⏳ A confirmar |
| 5 | Magalu Flex: como diferenciar Magalu padrão vs Flex? | ⏳ A confirmar |
| 6 | Devoluções: como identificar devoluções em cada plataforma além do ML? | ⏳ A confirmar por plataforma |
| 7 | Período inicial: o sistema precisa importar histórico? A partir de quando? | ⏳ A confirmar |
| 8 | Alertas: o sistema deve avisar quando V.LIQUIDO estiver em branco? | ⏳ A confirmar |

---

## 13. GLOSSÁRIO

| Termo | Definição |
|---|---|
| V.BRUTO | Preço total que o cliente pagou (antes de taxas do marketplace) |
| V.NF | Valor que consta na nota fiscal emitida |
| V.LIQUIDO | Valor que a empresa efetivamente recebe após taxas do marketplace |
| MARGEM R$ | Lucro real em reais: V.LIQUIDO − impostos − comissão − embalagem − custo |
| MARGEM % | MARGEM R$ ÷ CUSTO DO PRODUTO (retorno sobre custo) |
| SKU | Código identificador do produto |
| Pack | Pedido com múltiplos itens no Mercado Livre (tem pack_id próprio) |
| Flex | Modalidade onde o vendedor faz a entrega (sem galpão do marketplace) |
| ERP | Sistema de gestão (Olist/Tiny) |
| V.LIQUIDO estimado | Valor calculado por fórmula (sem API real) — deve ser marcado no banco |

---

## 14. REGRAS DO PROCESSO (para sessões futuras com IA)

1. **Este PRD é a fonte de verdade.** Em caso de conflito entre este documento e memória de conversa anterior, este documento prevalece.
2. **Código de referência** em `C:\Users\DELL\margem-multicanal\` — consultar só se necessário, avisar antes, validar com a usuária se faz sentido usar.
3. **Nunca implementar sem story** — toda funcionalidade nova tem acceptance criteria definidos antes de codar.
4. **Mudança de regra = atualizar PRD primeiro** — depois código.
5. **Módulos independentes** — mudança em plataforma A não afeta plataforma B.
6. **Rodar testes antes e depois** de qualquer mudança.

---

*Última atualização: 2026-05-12*
*Próximo passo: Responder item 12 (banco de dados SQLite ou PostgreSQL?) e iniciar Entrega 1*
