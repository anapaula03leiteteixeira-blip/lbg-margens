# Handoff — Próxima Sessão
> Cole este arquivo no início da próxima conversa com o @dev

---

## Contexto do projeto

Sistema de Controle de Margens da La Bella Griffe.
Projeto novo, limpo, começado do zero em 12/05/2026.

**Pasta do projeto:** `C:\Users\DELL\Desktop\Sistema - LBG\`
**Fonte de verdade:** `C:\Users\DELL\Desktop\Sistema - LBG\PRD.md`
**Código antigo (referência, não usar sem avisar):** `C:\Users\DELL\margem-multicanal\`

---

## O que já foi construído e testado

| Arquivo | O que faz | Testes |
|---|---|---|
| `src/calculator.py` | Fórmulas de margem (IMPOSTOS, COMISSÃO, MARGEM R$, MARGEM %) | 9 ✅ |
| `src/database.py` | Banco SQLite local (`lbg.db`) | ✅ |
| `src/custos.py` | Lê custos por SKU de `data/custos.json` | ✅ |
| `src/detector_plataforma.py` | Detecta plataforma e canal pelo pedido Tiny | ✅ |
| `src/erp/olist.py` | Conector API Tiny/Olist — busca pedidos e detalhes | ✅ |
| `src/platforms/mercado_livre.py` | Conector ML — V.LIQUIDO, FLEX, FULL, renovação de token | 10 ✅ |
| `src/pipeline.py` | Orquestrador central — une tudo e salva no banco | 9 ✅ |

**Total: 28 testes passando.**

---

## Regras de negócio confirmadas (do PRD)

- `IMPOSTOS = V_NF × 13%`
- `COMISSÃO = V_LIQUIDO × 4%`
- `MARGEM R$ = V_LIQUIDO − IMPOSTOS − COMISSÃO − EMBALAGEM − CUSTO_PRODUTO`
- `MARGEM % = MARGEM R$ / CUSTO_PRODUTO`
- ML FLEX: `V_LIQUIDO = total_pedido − R$14,90`
- ML FULL / Padrão: `V_LIQUIDO = net_received_amount` da API
- V.BRUTO = `total_pedido` do Tiny distribuído proporcionalmente por SKU
- V.NF = `valor_unitario` da NF fiscal × quantidade

---

## Tarefa da próxima sessão

1. Criar `rodar.py` na raiz do projeto
2. Executar o pipeline para Mercado Livre no período **01/05/2026 a 12/05/2026**
3. Verificar que os dados chegaram corretos no banco SQLite
4. Corrigir qualquer erro que aparecer
5. Mostrar resumo dos resultados (pedidos, linhas, erros)

**Comando para rodar após criar o arquivo:**
```
! python rodar.py
```

---

## Credenciais disponíveis

Todas no arquivo `.env` — não precisa pedir nenhuma credencial.
Plataformas com API pronta: Tiny ERP, Mercado Livre, Amazon, Leroy Merlin, Nuvemshop.

---

## Arquitetura modular — regra de ouro

Cada plataforma é um arquivo independente em `src/platforms/`.
Mudar ML não afeta Amazon. Mudar Amazon não afeta Leroy.
**Nunca alterar dois módulos ao mesmo tempo.**

---

## Como rodar os testes

```
cd "C:\Users\DELL\Desktop\Sistema - LBG"
python -m pytest tests/ -v
```
Deve mostrar: `28 passed`
