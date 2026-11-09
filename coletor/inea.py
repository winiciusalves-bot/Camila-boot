#!/usr/bin/env python3
"""
Ambiental Costa · INEA (órgão ambiental do Estado do RJ): penalidades aplicadas e ações de fiscalização.

Fonte: Portal de Dados Abertos do Estado do RJ, conjunto "Fiscalização e combate às infrações ambientais"
(https://dadosabertos.rj.gov.br/dataset/fiscalizacao-e-combate-as-infracoes-ambientais), atualização semestral, sem login.
Mesma regra da opção [13] do Radar-Ambiental v5.1 (c11_inea_penalidades.ps1), agora rodando online:
  - a planilha não tem dicionário de dados: o cabeçalho e as colunas são achados sozinhos e vão para o log;
  - só pessoa jurídica com DV do CNPJ válido entra no banco (tabela ocorrencias, orgao INEA, nivel FATO);
  - CPF nunca entra; nomes passam pela máscara de CPF;
  - valor é o indicado na penalidade: NÃO é dano nem condenação;
  - planilha só de totais (sem CNPJ) é registrada como agregado e não vira ocorrência.

Uso: python -I coletor/inea.py [--sem-supabase] [--xlsx arquivo.xlsx ...]
"""
import datetime as dt, hashlib, io, os, re, sys, time, urllib.request

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
from coletar import Supabase, dv_cnpj, fmt_cnpj, mascara, sem_acento, log, valor, data_iso, UA   # mesmas regras do coletor diário

PAG = 'https://dadosabertos.rj.gov.br/dataset/fiscalizacao-e-combate-as-infracoes-ambientais'
ARQS = [
    ('penalidades', 'INEA - penalidades aplicadas',
     'https://dadosabertos.rj.gov.br/dataset/0f650197-c519-44fb-b87d-44d59eeefbb0/resource/11b4744f-593b-47e6-a09f-a6c2fa64f230/download/penalidades_aplicadas.xlsx'),
    ('acoes_fiscalizacao', 'INEA - ações de fiscalização',
     'https://dadosabertos.rj.gov.br/dataset/0f650197-c519-44fb-b87d-44d59eeefbb0/resource/dd261fea-4fc0-4d39-80d0-189447862374/download/acoes-de-fiscalizacao.xlsx'),
]


def baixar(url, tentativas=4):
    for i in range(tentativas):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': UA}), timeout=120) as r:
                return r.read()
        except Exception as e:
            log(f'download falhou ({e}); nova tentativa em {2 ** (i + 1)} s'); time.sleep(2 ** (i + 1))
    return None


def achar(cab, padroes, usados=()):
    for p in padroes:
        for j, c in enumerate(cab):
            if j not in usados and re.search(p, c): return j
    return -1


def data_cel(v):
    if v is None or v == '': return None
    if isinstance(v, dt.datetime): return v.date()
    if isinstance(v, dt.date): return v
    if isinstance(v, (int, float)) and 20000 < v < 80000:            # número de série do Excel
        return dt.date(1899, 12, 30) + dt.timedelta(days=int(v))
    return data_iso(str(v))


def ler(binario, ident, nome, link):
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(binario), read_only=True, data_only=True)
    out, agregado = [], True
    for ws in wb.worksheets:
        linhas = [list(r) for r in ws.iter_rows(values_only=True)]
        if not linhas: continue
        # cabeçalho = primeira linha (entre as 15 primeiras) com 3 ou mais células preenchidas
        hi = next((j for j in range(min(15, len(linhas))) if sum(1 for x in linhas[j] if x not in (None, '')) >= 3), -1)
        if hi < 0: continue
        cab = [sem_acento(str(x or '')).strip() or f'COL{j + 1}' for j, x in enumerate(linhas[hi])]
        iDoc = achar(cab, ['CNPJ', 'CPF', 'DOCUMENTO'])
        if iDoc < 0:   # sem coluna de documento: procura a coluna com CNPJ válido nos valores
            for j in range(len(cab)):
                vals = [re.sub(r'\D', '', str(r[j] if j < len(r) else '') or '') for r in linhas[hi + 1:hi + 61]]
                vals = [v for v in vals if v]
                if len(vals) >= 5 and sum(1 for v in vals if len(v) == 14 and dv_cnpj(v)) / len(vals) >= 0.3: iDoc = j; break
        iData = achar(cab, [r'^DATA', 'DATA', r'^DT ', 'DT ', r'^EMISSAO', 'EMISSAO'], (iDoc,))
        iMun = achar(cab, ['MUNICIPIO', 'CIDADE'])
        iNome = achar(cab, ['RAZAO', 'AUTUADO', 'INFRATOR', 'EMPRESA', 'EMPREENDIMENTO', 'NOME'], (iDoc,))
        iVal = achar(cab, ['VALOR', 'MULTA'])
        iTipo = achar(cab, [r'^TIPO', 'PENALIDADE', 'SANCAO', 'INFRACAO', 'TIPO'], (iData, iDoc, iVal))
        iProc = achar(cab, ['PROCESSO'])
        iNum = achar(cab, [r'^AUTO', 'N AUTO', 'NUMERO', r'^N '], (iProc,))
        log(f"{ident} aba '{ws.title}': cabeçalho na linha {hi + 1}: {' | '.join(cab)[:600]}")
        log(f'   colunas usadas: doc={iDoc} data={iData} municipio={iMun} nome={iNome} valor={iVal} tipo={iTipo} processo={iProc} numero={iNum}')
        if iDoc >= 0: agregado = False
        cel = lambda r, j: (r[j] if 0 <= j < len(r) else None)
        n_pj = n_pf = n_inv = 0
        for r in linhas[hi + 1:]:
            if not any(x not in (None, '') for x in r): continue
            doc = re.sub(r'\D', '', str(cel(r, iDoc) or '')) if iDoc >= 0 else ''
            if len(doc) == 11: n_pf += 1; continue                       # pessoa física: não entra
            if len(doc) != 14 or not dv_cnpj(doc): n_inv += 1; continue
            n_pj += 1
            d = data_cel(cel(r, iData))
            num, proc = str(cel(r, iNum) or '').strip(), str(cel(r, iProc) or '').strip()
            pen = str(cel(r, iTipo) or '').strip()
            v = cel(r, iVal); v = float(v) if isinstance(v, (int, float)) else valor(str(v or ''))
            base_chave = num or proc or hashlib.sha1(repr(r).encode()).hexdigest()[:12]
            out.append(dict(
                chave=f"INEA-{'PEN' if ident == 'penalidades' else 'FISC'}|{doc}|{d or ''}|{base_chave}"[:300],
                fonte=f'{nome} (Dados Abertos RJ)', orgao='INEA',
                tipo_documento=('PENALIDADE INEA' + (f' - {sem_acento(pen)[:60]}' if pen else '')) if ident == 'penalidades' else 'ACAO DE FISCALIZACAO INEA',
                numero=num[:80], processo=proc[:80], data_documento=d.isoformat() if d else None,
                data_documento_status='' if d else 'sem data na planilha', situacao='VALIDO',
                cnpj=fmt_cnpj(doc), nome=mascara(str(cel(r, iNome) or ''))[:200], municipio=str(cel(r, iMun) or '').strip().title()[:80],
                valor_indicado_rs_nao_e_dano=v if (v and ident == 'penalidades') else None,
                assunto=pen[:200], descricao='', nivel='FATO', link_fonte=PAG, ultima_coleta=dt.date.today().isoformat(),
                origem='coletor-online'))
        log(f'   {n_pj} linha(s) de PJ com CNPJ válido · {n_pf} de pessoa física (fora) · {n_inv} sem CNPJ válido (fora)')
    return out, agregado


def main():
    sem_sb = '--sem-supabase' in sys.argv
    locais = sys.argv[sys.argv.index('--xlsx') + 1:] if '--xlsx' in sys.argv else []
    sb = None if sem_sb else Supabase(os.environ['SUPABASE_URL'].strip(), os.environ['SUPABASE_SERVICE_KEY'].strip())
    t0 = dt.datetime.now(dt.timezone.utc)
    occ, resumo = [], []
    for k, (ident, nome, url) in enumerate(ARQS):
        log(f'baixando {nome}', 100 * k / len(ARQS))
        b = open(locais[k], 'rb').read() if k < len(locais) else baixar(url)
        if not b: resumo.append(f'{nome}: SEM DADOS (download falhou)'); continue
        try: linhas, agregado = ler(b, ident, nome, url)
        except Exception as e: resumo.append(f'{nome}: planilha ilegível ({e})'); continue
        if agregado: resumo.append(f'{nome}: só totais, sem CNPJ (agregado; não vira ocorrência)')
        else: resumo.append(f'{nome}: {len(linhas)} registro(s) de PJ')
        occ += linhas
    # mesma chave repetida na planilha: fica a última
    occ = list({o['chave']: o for o in occ}.values())
    un = len({o['cnpj'] for o in occ})
    log(f'{len(occ)} ocorrência(s) do INEA de {un} empresa(s)', 90)
    if sb:
        ja = {o['chave'] for o in sb.todos('ocorrencias', 'chave') if o['chave'].startswith('INEA-')}
        sb.upsert('ocorrencias', occ, 'chave')
        novas = len([o for o in occ if o['chave'] not in ja])
        sb.req('POST', '/coletas', dict(
            fonte=f'INEA - Dados Abertos RJ (penalidades aplicadas e ações de fiscalização) {PAG}',
            metodo='planilhas XLSX; colunas achadas pelo cabeçalho; só CNPJ com DV válido; CPF fora; valor não é dano',
            status='ok', iniciada_em=t0.isoformat(), terminada_em=dt.datetime.now(dt.timezone.utc).isoformat(),
            autos_lidos=len(occ), autos_novos=novas, empresas_novas=None,
            mensagem='; '.join(resumo)[:900]), {'Prefer': 'return=minimal'})
        log(f'{novas} ocorrência(s) nova(s) gravada(s)')
    if '--amostra' in sys.argv:   # teste: mostra 8 linhas de cada fonte, já com CPF fora e máscara aplicada
        for pre in ('INEA-PEN', 'INEA-FISC'):
            for o in [o for o in occ if o['chave'].startswith(pre)][:8]:
                log(f"   amostra {pre}: {o['cnpj']} · {o['nome'][:50]} · {o['data_documento']} · {o['municipio']} · {o['tipo_documento'][:50]} · nº {o['numero']} · proc {o['processo']} · R$ {o['valor_indicado_rs_nao_e_dano']}")
        datas = sorted(o['data_documento'] for o in occ if o['data_documento'])
        if datas: log(f'   datas de {datas[0]} a {datas[-1]}; em 12 meses: {sum(1 for d in datas if d >= (dt.date.today() - dt.timedelta(days=365)).isoformat())}')
    for r in resumo: log(r)
    log('FIM', 100)
    print('\a')


if __name__ == '__main__':
    main()
