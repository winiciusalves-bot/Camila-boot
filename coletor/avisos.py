"""Avisos por e-mail da Origem Consultoria Ambiental (roda no fim da coleta diária).

Envia UM e-mail só quando há novidade:
  1) empresas novas que entraram hoje no sistema e esperam a Conferência;
  2) aprovadas sem resposta que chegaram hoje ao prazo de nova tentativa (7 dias após a 1ª mensagem,
     14 dias após a 2ª) ou que foram para o lixo (14 dias sem resposta após a 3ª mensagem).
Mesma regra do painel (site/area-restrita/painel.js, VOLTAS = [7, 14]).

Fica DESLIGADO enquanto não existirem os Secrets GMAIL_USUARIO e GMAIL_SENHA_APP (senha de app do Gmail,
criada e colada pelo próprio usuário; nunca no código). Destino: AVISO_PARA (padrão: e-mail da Origem).
CPF nunca vai no e-mail: só razão social de empresa (masc() da coleta) e CNPJ.
"""
import html, os, smtplib, sys
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText

sys.path.insert(0, os.path.dirname(__file__))
from coletar import Supabase, mascara as masc, log  # noqa: E402

VOLTAS = [7, 14]
SITE = 'https://ambientalcosta.netlify.app/area-restrita/'
PARA = os.environ.get('AVISO_PARA', 'origemconsultoriaambiental@gmail.com')


def dt(s):
    try: return datetime.fromisoformat(str(s).replace('Z', '+00:00'))
    except Exception: return None


def calcular(sb, agora):
    hoje = agora.date()
    emp = {e['cnpj']: e for e in sb.todos('empresas', 'cnpj,razao_social,prioridade,municipio_sede')}
    try: tri = {t['cnpj']: t for t in sb.todos('triagem', 'cnpj,decisao')}
    except RuntimeError: tri = {}
    primeira = {}
    for tab in ('autos', 'ocorrencias'):
        try:
            for r in sb.todos(tab, 'cnpj,primeira_coleta'):
                d = str(r.get('primeira_coleta') or '')[:10]
                if r.get('cnpj') and d and (r['cnpj'] not in primeira or d < primeira[r['cnpj']]): primeira[r['cnpj']] = d
        except RuntimeError: pass
    novas = [emp[c] for c, d in primeira.items() if d == hoje.isoformat() and c in emp and c not in tri
             and (emp[c].get('prioridade') or '')[:1] != 'X']
    novas.sort(key=lambda e: (e.get('prioridade') or 'Z', e['razao_social']))

    cont = {}
    for c in sb.todos('contatos', 'cnpj,status,canal,criado_em'): cont.setdefault(c['cnpj'], []).append(c)
    voltar, lixo = [], []
    for cnpj, lst in cont.items():
        if (tri.get(cnpj) or {}).get('decisao') != 'aprovado' or cnpj not in emp: continue
        lst.sort(key=lambda c: c['criado_em'])
        ult = lst[-1]
        if ult['status'] != 'contatado': continue
        tent = 0
        for c in reversed(lst):
            if c['status'] == 'novo': break
            if c['status'] == 'contatado': tent += 1
        espera = VOLTAS[min(tent, len(VOLTAS)) - 1]
        quando = dt(ult['criado_em']) + timedelta(days=espera)
        if not (agora - timedelta(days=1) < quando <= agora): continue   # chegou ao prazo nas últimas 24 h
        item = dict(e=emp[cnpj], tent=tent, canal=ult.get('canal') or '', desde=dt(ult['criado_em']))
        (lixo if tent > len(VOLTAS) else voltar).append(item)
    return novas, voltar, lixo


def montar(novas, voltar, lixo):
    e = lambda s: html.escape(masc(str(s or '')))
    li = lambda x: f'<li><b>{e(x["razao_social"])}</b> · {e(x["cnpj"])} · {e(x.get("municipio_sede"))} · prioridade {e(x.get("prioridade") or "-")}</li>'
    lc = lambda i: (f'<li><b>{e(i["e"]["razao_social"])}</b> · {e(i["e"]["cnpj"])} · {i["tent"]}ª mensagem por {e(i["canal"])} '
                    f'em {i["desde"]:%d/%m/%Y}</li>')
    partes = []
    if novas: partes.append(f'<h2>{len(novas)} empresa(s) nova(s) para conferir</h2><ul>{"".join(li(x) for x in novas[:60])}</ul>' +
                            (f'<p>e mais {len(novas) - 60}.</p>' if len(novas) > 60 else ''))
    if voltar: partes.append(f'<h2>{len(voltar)} sem resposta: hora de tentar de novo</h2><p>Prazo de 7 dias (após a 1ª mensagem) ou 14 dias (após a 2ª). '
                             f'De preferência, use outro canal.</p><ul>{"".join(lc(i) for i in voltar)}</ul>')
    if lixo: partes.append(f'<h2>{len(lixo)} foram para o lixo</h2><p>14 dias sem resposta após a 3ª mensagem. Ficam 45 dias em Reprovados '
                           f'(dá para restaurar) e depois saem do banco.</p><ul>{"".join(lc(i) for i in lixo)}</ul>')
    assunto = ' · '.join(filter(None, [f'{len(novas)} empresa(s) nova(s)' if novas else '', f'{len(voltar)} para recontatar' if voltar else '',
                                       f'{len(lixo)} no lixo' if lixo else '']))
    corpo = ('<div style="font-family:Arial,sans-serif;color:#2E2E2E;max-width:640px">'
             '<p style="letter-spacing:.3em;color:#1F3B2E;font-size:13px;margin:0">ORIGEM</p>'
             '<p style="letter-spacing:.2em;font-size:10px;color:#9B7B5A;margin:2px 0 18px">CONSULTORIA AMBIENTAL</p>'
             + ''.join(partes) +
             f'<p><a href="{SITE}" style="background:#1F3B2E;color:#F5F0E8;padding:10px 18px;border-radius:999px;text-decoration:none">Abrir a área restrita</a></p>'
             '<p style="font-size:12px;color:#777">Fontes: IBAMA Dados Abertos, diários oficiais e cadastro público do CNPJ. '
             'Auto de infração não é condenação e valor indicado não é dano. CPF nunca é enviado.</p></div>')
    return 'Origem · ' + assunto, corpo


def main():
    agora = datetime.now(timezone.utc)
    usuario, senha = os.environ.get('GMAIL_USUARIO', '').strip(), os.environ.get('GMAIL_SENHA_APP', '').strip()
    sb = Supabase(os.environ['SUPABASE_URL'].strip(), os.environ['SUPABASE_SERVICE_KEY'].strip())
    novas, voltar, lixo = calcular(sb, agora)
    log(f'avisos: {len(novas)} nova(s), {len(voltar)} para recontatar, {len(lixo)} no lixo')
    if not (novas or voltar or lixo):
        log('avisos: nada novo, nenhum e-mail enviado'); return
    if not (usuario and senha):
        log('avisos: e-mail DESLIGADO (faltam os Secrets GMAIL_USUARIO e GMAIL_SENHA_APP)'); return
    assunto, corpo = montar(novas, voltar, lixo)
    m = MIMEText(corpo, 'html', 'utf-8'); m['Subject'] = assunto; m['From'] = usuario; m['To'] = PARA
    with smtplib.SMTP_SSL('smtp.gmail.com', 465, timeout=60) as s:
        s.login(usuario, senha); s.sendmail(usuario, [PARA], m.as_string())
    log(f'avisos: e-mail enviado para {PARA}')


if __name__ == '__main__':
    try: main()
    except Exception as ex:   # aviso nunca derruba a coleta
        log(f'avisos: falhou ({ex})')
