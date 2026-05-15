# Handoff — Próxima Sessão
> Cole este arquivo no início da próxima conversa com o @dev

---

## Contexto do projeto

Sistema de Controle de Margens da La Bella Griffe.
**Pasta do projeto:** `C:\Users\DELL\Desktop\Sistema - LBG\`
**Fonte de verdade:** `C:\Users\DELL\Desktop\Sistema - LBG\PRD.md`
**Código antigo (referência, não usar sem avisar):** `C:\Users\DELL\margem-multicanal\`

---

## O que foi construído e testado

| Arquivo | O que faz | Testes |
|---|---|---|
| `src/calculator.py` | Fórmulas de margem | 9 ✅ |
| `src/database.py` | SQLite + Supabase, com `buscar_shopee_pendentes()` | ✅ |
| `src/custos.py` | Lê custos por SKU de `data/custos.json` | ✅ |
| `src/detector_plataforma.py` | Detecta plataforma pelo pedido Tiny | ✅ |
| `src/erp/olist.py` | Conector API Tiny/Olist | ✅ |
| `src/controle.py` | Estado incremental (`.controle.json`) — NOVO | ✅ |
| `src/platforms/mercado_livre.py` | Reescrito: V.LIQUIDO por order_id via `/collections/search` | 12 ✅ |
| `src/platforms/shopee.py` | Reescrito: COMPLETED→escrow real, trânsito→aguardando_escrow | 12 ✅ |
| `src/pipeline.py` | Reescrito: incremental + estimativa Shopee + reconciliação | ✅ |
| `rodar.py` | Atualizado: `--desde`, `--ate`, `--so-reconciliar` | ✅ |

**Total: 46 testes passando.**

---

## Arquitetura atual (resumo)

### Pipeline incremental
```
python rodar.py                              # desde última execução até hoje
python rodar.py --desde 01/05/2026           # desde data específica
python rodar.py --desde 01/05/2026 --ate 14/05/2026
python rodar.py --so-reconciliar             # só reconcilia Shopee pendentes
```

### V.LIQUIDO por plataforma
- **ML Flex**: `total_amount − R$14,99` (sem chamada de collections)
- **ML Full/Padrão**: `/collections/search?order_id={id}` → `net_received_amount`
- **Shopee COMPLETED**: `get_escrow_detail` → escrow real
- **Shopee em trânsito**: estimativa `v_bruto × (1 − 10%)`, badge amarelo no dashboard, reconcilia diariamente
- **LBG**: = V.BRUTO

### Taxas configuráveis (`config/taxas.yaml`)
- `mercado_livre_flex.taxa_fixa: 14.99`
- `shopee_flex.taxa_fixa: 9.99`
- `shopee.taxa_comissao: 0.10` (confirmar % real com Shopee)

---

## Banco de dados atual (lbg.db)

420 linhas do run anterior com a arquitetura antiga:
- ML: 162 linhas com V.LIQUIDO real ✅
- Shopee: 228 linhas com `v_liquido = NULL` (arquitetura antiga, não reprocessar)
- LBG: 11 linhas ✅
- Amazon/Leroy/MM: sem V.LIQUIDO (aguardando conector)

**O banco foi mantido** — próxima execução processa pedidos NOVOS desde a última data + reconcilia Shopee.

---

## Próxima tarefa — TESTAR o novo pipeline

1. Rodar os testes: `python -m pytest tests/ -v` → deve mostrar **46 passed**
2. Executar pipeline incremental para o período atual:
   ```
   python rodar.py --desde 01/05/2026 --ate 14/05/2026
   ```
   - Deve ser mais rápido que antes (só novos pedidos)
   - ML deve ter V.LIQUIDO preenchido para Full/Padrão
   - Shopee em trânsito deve ter estimativa com badge

3. Se tudo ok: rodar sem datas (modo incremental puro)
   ```
   python rodar.py
   ```

4. Verificar no banco quantos Shopee ficaram com estimativa vs real

---

## Pendente (próximas entregas)

- **Aba ⚙️ Configurações** no dashboard Streamlit (`app/main.py`) — editar taxas_fixa ML e Shopee diretamente na UI
- **Entrega 4**: Amazon + Leroy Merlin
- **Entrega 5**: Nuvemshop
- **Entrega 6**: Magalu + MadeiraMadeira
- **Entrega 7**: Automação diária

---

## Como rodar os testes

```
cd "C:\Users\DELL\Desktop\Sistema - LBG"
python -m pytest tests/ -v
```
Deve mostrar: `46 passed`
