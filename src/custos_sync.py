"""
custos_sync.py — Sincroniza custos do Google Sheets para data/custos.json.

Uso:
    python src/custos_sync.py

Requer: gspread + credenciais Google em .env ou arquivo service_account.json
"""
import json
import os
import re
import sys
from datetime import datetime

from dotenv import load_dotenv
load_dotenv()

SHEET_ID = '1K-typUs7IATurbFHHI_5BdvnXRRhc2_jHikLSmAGQ3g'
CUSTOS_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'custos.json')
SERVICE_ACCOUNT_PATH = os.path.join(os.path.dirname(__file__), '..', 'google_credentials.json')

# Índices das colunas (0-based)
COL_SKU = 0
COL_CUSTO_UNITARIO = 3   # D
COL_EMBALAGEM = 5        # F


def _parse_valor(s):
    """Converte 'R$ 7,10' ou '7,10' ou '7.10' para float."""
    if not s:
        return 0.0
    s = str(s).replace('R$', '').strip()
    s = s.replace('.', '').replace(',', '.')
    try:
        return float(s)
    except ValueError:
        return 0.0


def sincronizar():
    """
    Lê o Google Sheets e atualiza data/custos.json.
    Retorna dict com resumo: {'skus': int, 'atualizados': int, 'novos': int}
    """
    try:
        import gspread
    except ImportError:
        print('ERRO: gspread não instalado. Execute: pip install gspread')
        sys.exit(1)

    # Autenticação: tenta service account primeiro, depois OAuth
    if os.path.exists(SERVICE_ACCOUNT_PATH):
        gc = gspread.service_account(filename=SERVICE_ACCOUNT_PATH)
    else:
        # OAuth — abre browser na primeira vez, salva token localmente
        gc = gspread.oauth()

    print(f'Conectando ao Google Sheets ({SHEET_ID})...')
    sh = gc.open_by_key(SHEET_ID)
    ws = sh.get_worksheet(0)  # aba principal
    rows = ws.get_all_values()

    if not rows:
        print('ERRO: planilha vazia')
        sys.exit(1)

    # Carregar custos existentes
    if os.path.exists(CUSTOS_PATH):
        with open(CUSTOS_PATH, 'r', encoding='utf-8') as f:
            custos_existentes = json.load(f)
        # Remover chaves de instrução (começam com _)
        custos_existentes = {k: v for k, v in custos_existentes.items() if not k.startswith('_')}
    else:
        custos_existentes = {}

    novos = 0
    atualizados = 0
    custos_novos = {}

    for row in rows[1:]:  # pular cabeçalho
        if not row or len(row) < 4:
            continue
        sku = str(row[COL_SKU]).strip()
        if not sku or sku.startswith('_'):
            continue

        custo_unitario = _parse_valor(row[COL_CUSTO_UNITARIO] if len(row) > COL_CUSTO_UNITARIO else '')
        embalagem = _parse_valor(row[COL_EMBALAGEM] if len(row) > COL_EMBALAGEM else '')

        entrada = {'custo_unitario': custo_unitario, 'embalagem': embalagem}
        custos_novos[sku] = entrada

        if sku not in custos_existentes:
            novos += 1
        elif custos_existentes[sku] != entrada:
            atualizados += 1

    with open(CUSTOS_PATH, 'w', encoding='utf-8') as f:
        json.dump(custos_novos, f, ensure_ascii=False, indent=2)

    resumo = {
        'skus': len(custos_novos),
        'novos': novos,
        'atualizados': atualizados,
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M'),
    }

    print(f'Sincronizado: {resumo["skus"]} SKUs | {resumo["novos"]} novos | {resumo["atualizados"]} atualizados')
    return resumo


if __name__ == '__main__':
    sincronizar()
