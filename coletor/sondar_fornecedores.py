"""
Procura, para os 92 municípios do RJ, os sistemas de diário oficial que já têm robô-base no Querido Diário
(um robô serve para todos os municípios do mesmo fornecedor). Só faz GET em páginas públicas; não contorna nada.
Saída: relatorio/fornecedores.csv com as combinações que responderam com edições.
"""
import csv, os, re, sys
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sondar_fontes import get, slug, municipios, desafio

INI, FIM = '01/10/2026', '09/11/2026'
RX_ED = re.compile(r'(edi[cç][aã]o\s*n?[ºo°.]?\s*\d+|\.pdf|arquivos_download|visualizar edi)', re.I)


def padroes(s, s_):
    hosts = [f'transparencia.{s}.rj.gov.br', f'www.transparencia.{s}.rj.gov.br', f'portal.{s}.rj.gov.br',
             f'{s}.rj.gov.br', f'www.{s}.rj.gov.br']
    for h in hosts:
        yield 'adiarios_v2 (jornal.php)', f'https://{h}/jornal.php?dtini={INI}&dtfim={FIM}'
        yield 'adiarios_v1 (diariooficial.php)', f'https://{h}/diariooficial.php?dtini={INI}&dtfim={FIM}'
        yield 'busca (diario_oficial_busca.php)', f'https://{h}/diario_oficial_busca.php'
    yield 'dioenet', f'https://plenussistemas.dioenet.com.br/list/{s_}'


def testar(m):
    cod, nome = m
    achados = []
    for fam, url in padroes(slug(nome), slug(nome, '-')):
        st, fin, html = get(url, timeout=20)
        if st == 200 and len(RX_ED.findall(html or '')) >= 3 and slug(nome)[:5] in slug(html[:300000]):
            achados.append((fam, fin, 'captcha?' if desafio(html) else '', len(RX_ED.findall(html))))
    return cod, nome, achados


def main(saida='relatorio'):
    os.makedirs(saida, exist_ok=True)
    with ThreadPoolExecutor(10) as ex:
        res = list(ex.map(testar, municipios()))
    with open(f'{saida}/fornecedores.csv', 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f, delimiter=';'); w.writerow(['codigo_ibge', 'municipio', 'familia', 'url', 'obs', 'marcas'])
        for cod, nome, ach in res:
            for a in ach: w.writerow([cod, nome, *a])
    n = sum(1 for r in res if r[2])
    print(f'{n} município(s) com sistema conhecido respondendo')
    for cod, nome, ach in res:
        for fam, url, obs, k in ach: print(f'{nome};{fam};{url};{obs};{k}')


if __name__ == '__main__':
    main(*(sys.argv[1:2] or []))
