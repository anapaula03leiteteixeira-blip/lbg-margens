"""
Controle de estado do pipeline — registra última execução e calcula datas a processar.
Estado persiste no Supabase (tabela config). Fallback para .controle.json em dev local.
"""
import os
import json
from datetime import datetime, timedelta

_PATH = os.path.join(os.path.dirname(__file__), '..', '.controle.json')
_CHAVE_SUPABASE = 'ultima_data_executada'
_MAX_CATCHUP_DIAS = 7


def _usar_supabase():
    return bool(os.getenv('SUPABASE_URL', '').strip() and os.getenv('SUPABASE_KEY', '').strip())


def _ler_ultima_data_supabase():
    try:
        from src.database import buscar_config
        return buscar_config(_CHAVE_SUPABASE)
    except Exception:
        return None


def _ler_ultima_data_local():
    if not os.path.exists(_PATH):
        return None
    try:
        with open(_PATH, 'r', encoding='utf-8') as f:
            return json.load(f).get('ultima_data_tiny')
    except Exception:
        return None


def _ler_ultima_data():
    """Retorna última data processada em formato 'YYYY-MM-DD', ou None."""
    if _usar_supabase():
        valor = _ler_ultima_data_supabase()
        if valor:
            return valor
    return _ler_ultima_data_local()


def registrar_execucao(data_iso):
    """Salva data_iso ('YYYY-MM-DD') como última data processada."""
    if _usar_supabase():
        try:
            from src.database import salvar_config
            salvar_config(_CHAVE_SUPABASE, data_iso)
        except Exception:
            pass

    try:
        estado = {'ultima_data_tiny': data_iso, 'atualizado_em': datetime.now().isoformat()}
        with open(_PATH, 'w', encoding='utf-8') as f:
            json.dump(estado, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def datas_para_processar(desde_arg=None, ate_arg=None):
    """
    Retorna lista ordenada de datas ISO ('YYYY-MM-DD') a processar.

    Modo automático (sem args):
      - Início: dia seguinte à última execução registrada
      - Fim: D-1 (ontem)
      - Catch-up limitado a _MAX_CATCHUP_DIAS dias para evitar explosão na primeira execução

    Modo manual (desde_arg e/ou ate_arg em 'DD/MM/YYYY'):
      - Processa o intervalo especificado sem limite de dias
    """
    ontem = datetime.now() - timedelta(days=1)

    if desde_arg:
        inicio = datetime.strptime(desde_arg, '%d/%m/%Y')
        fim = datetime.strptime(ate_arg, '%d/%m/%Y') if ate_arg else ontem
    else:
        ultima = _ler_ultima_data()
        if ultima:
            inicio = datetime.strptime(ultima, '%Y-%m-%d') + timedelta(days=1)
        else:
            # Primeira execução: D-7 como ponto de partida
            inicio = ontem - timedelta(days=_MAX_CATCHUP_DIAS - 1)
        fim = ontem

        # Limita catch-up a _MAX_CATCHUP_DIAS dias
        max_inicio = ontem - timedelta(days=_MAX_CATCHUP_DIAS - 1)
        if inicio < max_inicio:
            inicio = max_inicio

    datas = []
    atual = inicio
    while atual <= fim:
        datas.append(atual.strftime('%Y-%m-%d'))
        atual += timedelta(days=1)
    return datas


def data_inicio_incremental(desde_arg=None):
    """Compatibilidade legada — retorna data de início em DD/MM/YYYY."""
    if desde_arg:
        return desde_arg
    ultima = _ler_ultima_data()
    if ultima:
        dt = datetime.strptime(ultima, '%Y-%m-%d') + timedelta(days=1)
        return dt.strftime('%d/%m/%Y')
    fallback = datetime.now() - timedelta(days=30)
    return fallback.strftime('%d/%m/%Y')
