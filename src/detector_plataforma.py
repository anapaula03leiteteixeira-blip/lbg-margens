def detectar(detalhe_pedido):
    """
    Retorna {'plataforma': str, 'canal': str} baseado nos dados do pedido Tiny.
    """
    ecommerce = str(detalhe_pedido.get('ecommerce', '') or '').lower()
    forma_pag = str(detalhe_pedido.get('forma_pagamento', '') or '').lower()
    marcadores = [str(m).lower() for m in detalhe_pedido.get('marcadores', [])]

    # Marketplaces — detectados pelo campo ecommerce do Tiny
    if 'mercado livre' in ecommerce or 'mercadolivre' in ecommerce:
        return {'plataforma': 'Mercado Livre', 'canal': 'E-commerce'}
    if 'shopee' in ecommerce:
        return {'plataforma': 'Shopee', 'canal': 'E-commerce'}
    if 'amazon' in ecommerce:
        return {'plataforma': 'Amazon', 'canal': 'E-commerce'}
    if 'leroy' in ecommerce:
        return {'plataforma': 'Leroy Merlin', 'canal': 'E-commerce'}
    if 'magalu' in ecommerce or 'magazine' in ecommerce:
        return {'plataforma': 'Magalu', 'canal': 'E-commerce'}
    if 'madeira' in ecommerce:
        return {'plataforma': 'MadeiraMadeira', 'canal': 'E-commerce'}

    # Vendas diretas — Pix/Boleto detectado pela forma de pagamento
    eh_direto = any(p in forma_pag for p in ('pix', 'boleto', 'transferencia', 'deposito'))

    if eh_direto or not ecommerce:
        if 'piscinas' in marcadores:
            return {'plataforma': 'LBG', 'canal': 'Piscinas'}
        if 'construtor' in marcadores or 'construtora' in marcadores:
            return {'plataforma': 'LBG', 'canal': 'Construtor'}
        # Nuvemshop cross-reference será feito em camada separada
        # Por ora, trata como LBG direto
        return {'plataforma': 'LBG', 'canal': 'Revenda'}

    return {'plataforma': 'Desconhecido', 'canal': 'Desconhecido'}
