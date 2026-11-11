"""Chance de a empresa contratar assessoria de engenharia ambiental para licenciamento.

Juízo COMERCIAL (não é acusação). Pedido do usuário em 11/11/2026: rodar sempre antes de atualizar o painel.
Regras documentadas em radar-ambiental/juizo-licenciamento-2026-11-11/JUIZO-licenciamento-2026-11-11.md.
Faixas: Alta >= 60, Média 40 a 59, Baixa < 40. Descartadas (prioridade X) não recebem faixa e não vão ao painel.
"""
import datetime as dt
import re

# (código, pontos, conta porte?, rótulo, regex) na ordem em que são testados em cada documento
REGRAS = [
    ('AREA', 30, True, 'Dano em vegetação/APP: recuperação (PRAD) e regularização',
     r'(destruir|danificar|desmat|suprim|supress)\w*.{0,80}(hectare|\bha\b|vegeta|floresta|mata atl|preserva[cç][aã]o permanente)'),
    ('SISGEN', 10, False, 'Patrimônio genético/conhecimento tradicional (SisGen): tema de defesa',
     r'conhecimento tradicional|patrim[oô]nio gen|13\.123'),
    ('FALSO', 5, False, 'Informação falsa em sistema oficial: tema de defesa', r'informa[cç][aã]o falsa|inid[oô]ne'),
    ('PESCA', 5, False, 'Pesca em local proibido: tema de defesa', r'\bpesca(r)?\b.{0,60}proibid'),
    ('ORIGEM', 10, False, 'Pescado/fauna sem comprovação de origem: tema de defesa',
     r'pescad|camar[aã]o|esp[eé]cimes? da fauna|fauna aqu[aá]tica|comprovante de origem|comprova[cç][aã]o de origem'),
    ('AREA_UC', 5, False, 'Entrada em área restrita de unidade de conservação: tema de defesa', r'[aá]rea restrita'),
    ('MADEIRA', 20, True, 'Produto florestal/madeira (CTF e DOF)', r'\bDOF\b|origem vegetal|madeir'),
    ('COND_FED', 10, True, 'Condicionantes de licença federal já existente / descarga offshore',
     r'condicionante|efetuar a descarga|parecer t[eé]cnico n|dilic'),
    ('AGRO', 25, True, 'Uso de agrotóxico em desacordo', r'agrot[oó]xico'),
    ('EXPORT', 20, True, 'Resíduo exportado/movimentado sem autorização', r'res[ií]duo.{0,80}sem autoriza'),
    ('CTF', 25, True, 'Pendência no Cadastro Técnico Federal / RAPP', r'cadastro t[eé]cnico|\bRAPP|relat[oó]rio de atividade'),
    ('OLUC', 15, True, 'Logística reversa / óleo lubrificante usado', r'log[ií]stica reversa|lubrificante usado|\bOLUC\b'),
    ('LIC_DESAC', 25, True, 'Operar em desacordo com a licença obtida', r'desacordo com a (licen|autoriza)'),
    ('LIC_SEM', 35, True, 'Operar ou transportar sem licença/autorização ambiental',
     r'sem (a )?(devida )?(licen|\.?autoriza)|sem licen'),
    ('POLUI', 25, True, 'Poluição ligada à operação', r'causar polui|lan[cç]ar (subst|res[ií]duo)'),
    ('PERIGO', 20, True, 'Produto perigoso em desacordo com a legislação', r'perigos|t[oó]xica|\bGLP\b|\bg[aá]s\b|botij'),
]
NOTIF_MADEIRA = (20, 'Comércio de madeira notificado (CTF e DOF a confirmar)')
NOTIF = (5, 'Só notificação, sem texto detalhado na base')

GRANDES = r'PETROBRAS|TRANSPETRO|SHELL|EQUINOR|PERENCO|TRIDENT|\bPRIO\b|3R PETROLEUM|VIBRA|MONJASA|ALE COMBUST|LUBRIZOL|' \
          r'WILSON SONS|\bTGS\b|MOVIDA|UNIDAS|ELETRONUCLEAR|CONCESSIONARIA|TRANSMISSORA|ECOPONTE'
ATIV_LIC = r'extra[cç][aã]o|min[eé]rio|cria[cç][aã]o de (peixes|camar)|aquicultura|fabrica[cç][aã]o|cer[aâ]mica|' \
           r'g[aá]s liq|combust[ií]ve|qu[ií]mic|(?<!exceto )produtos perigosos|preserva[cç][aã]o de peixes|refino'
PORTE_PTS = {'PEQ': 20, 'EPP': 15, 'MED': 0, 'GRANDE': -30, 'ENTIDADE': -10}


def _valido(o):
    s = (o.get('situacao') or '').upper()
    return (o.get('nivel') or '') != 'INDICIO' and 'CANCEL' not in s and 'EXCLU' not in s and 'DESEMBARG' not in s


def _porte(e, n_docs):
    nome, nat = (e.get('razao_social') or '').upper(), (e.get('natureza_juridica') or '')
    if re.search(GRANDES, nome) or re.search(r'An[oô]nima Aberta|Economia Mista', nat) or n_docs >= 10 \
            or re.search(r'petr[oó]leo e g[aá]s|transmiss[aã]o de energia|concession[aá]ria', e.get('atividade') or '', re.I):
        return 'GRANDE'
    if re.search(r'Sindical|Associa[cç][aã]o|Funda[cç][aã]o', nat):
        return 'ENTIDADE'
    if e.get('individual') or 'MICRO' in (e.get('porte') or '').upper():
        return 'PEQ'
    if 'PEQUENO' in (e.get('porte') or '').upper():
        return 'EPP'
    return 'MED'


def chance(e, occs, hoje, prioridade):
    """Devolve dict(chance_licenciamento, chance_pontos, chance_motivo, chance_em) ou campos vazios para descartadas."""
    vazio = dict(chance_licenciamento=None, chance_pontos=None, chance_motivo=None, chance_em=hoje.isoformat())
    if str(prioridade or '').startswith('X'):
        return vazio
    docs = [o for o in occs if _valido(o)]
    if not docs:
        return vazio
    melhor_lic, melhor_def = None, None
    for o in docs:
        txt = f"{o.get('descricao') or ''} {o.get('assunto') or ''}"
        tipo = (o.get('tipo_documento') or '').upper()
        achou = None
        if 'NOTIFICA' in tipo and len(txt.strip()) < 60:      # notificação só traz a atividade
            achou = ('MADEIRA_N', *NOTIF_MADEIRA, True) if re.search(r'made\w*r', txt, re.I) else ('NOTIF', *NOTIF, True)
        else:
            for cod, pts, lic, rot, rx in REGRAS:
                if re.search(rx, txt, re.I):
                    achou = (cod, pts, rot, lic); break
        if not achou:
            if 'SUSPENS' in tipo or 'EMBARGO' in tipo or 'APREENS' in tipo:
                continue
            achou = ('AUTO_OUTRO', 15, 'Auto de infração ambiental (tipo a conferir)', True) if 'AUTO' in tipo else ('NOTIF', *NOTIF, True)
        cod, pts, rot, lic = achou
        if lic and (not melhor_lic or pts > melhor_lic[1]): melhor_lic = (cod, pts, rot)
        if not lic and (not melhor_def or pts > melhor_def[1]): melhor_def = (cod, pts, rot)
    nec = melhor_lic or melhor_def
    if not nec:
        nec = ('NOTIF', NOTIF[0], NOTIF[1]); lic = True
    else:
        lic = nec is melhor_lic
    pts, calc = nec[1], [f'{nec[2]} +{nec[1]}']
    tipos = ' '.join((o.get('tipo_documento') or '').upper() for o in docs)
    if 'SUSPENS' in tipos or 'EMBARGO' in tipos:
        pts += 15; calc.append('suspensão/embargo vigente +15')
    elif 'APREENS' in tipos:
        pts += 5; calc.append('apreensão +5')
    if any(len(re.findall(r'20\d\d/20\d\d', o.get('descricao') or '')) >= 3 for o in docs):
        pts += 10; calc.append('anos seguidos sem cumprir obrigação +10')
    ult = max((o.get('data_documento') or '') for o in docs)
    dias = (hoje - dt.date.fromisoformat(ult[:10])).days if ult else 9999
    r = 15 if dias <= 60 else 10 if dias <= 180 else 5 if dias <= 365 else 0
    pts += r; calc.append(f'documento mais recente há {dias} dias +{r}')
    porte = _porte(e, len(docs))
    pp = PORTE_PTS[porte] if (lic or porte in ('GRANDE', 'ENTIDADE')) else 0
    if pp: pts += pp; calc.append(f'porte {porte} {pp:+d}')
    if not (e.get('municipio_sede') or '').upper().endswith('/RJ'):
        pts -= 5; calc.append('sede fora do RJ -5')
    if (e.get('telefone') or '').strip() or (e.get('email') or '').strip():
        pts += 5; calc.append('tem contato +5')
    else:
        pts -= 5; calc.append('sem contato -5')
    if re.search(ATIV_LIC, e.get('atividade') or '', re.I):
        pts += 5; calc.append('atividade licenciável +5')
    if 'RECUPERACAO JUDICIAL' in (e.get('razao_social') or '').upper():
        pts -= 10; calc.append('recuperação judicial -10')
    faixa = 'Alta' if pts >= 60 else 'Média' if pts >= 40 else 'Baixa'
    return dict(chance_licenciamento=faixa, chance_pontos=pts, chance_motivo='; '.join(calc), chance_em=hoje.isoformat())
