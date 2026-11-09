"""
Gravação no formato comum do gabinete (schema "comum" do Supabase mxfgezgmyowqjmaibdkl), combinado em 09/11/2026.

  comum.coleta         uma linha por rodada (robo, versao, onde, status, linhas)
  comum.diario_edicao  uma linha por arquivo de edição (único por fonte, data, edicao, parte)
  comum.diario_ato     um ato por linha: 'cnpj_citado' ou 'pessoal' (único por hash_ato)

Conexão: só pela variável DATABASE_URL (Secret do GitHub, cadastrada pelo dono). Sem ela, o coletor segue normal
e só avisa no log. O schema comum não dá acesso à API REST, por isso a conexão é direta ao Postgres.
O banco recusa CPF aberto: tudo passa por mascarar_cpf() antes (formato ***.456.789-**).
"""
import hashlib, os, re

FONTE = 'QUERIDO_DIARIO'
_CPF_FMT = re.compile(r'(?<![0-9])(\d{3})\.(\d{3})\.(\d{3})-(\d{2})(?![0-9])')
_CPF_11 = re.compile(r'(?<![0-9./-])(\d{3})(\d{3})(\d{3})(\d{2})(?![0-9])')


def mascarar_cpf(t):
    """Máscara exigida pelo banco: ***.456.789-** (só os 6 dígitos do meio ficam)."""
    t = _CPF_FMT.sub(lambda m: f'***.{m.group(2)}.{m.group(3)}-**', t or '')
    return _CPF_11.sub(lambda m: f'***.{m.group(2)}.{m.group(3)}-**', t)


def hash_ato(*partes):
    return hashlib.sha256('|'.join(str(p) for p in partes).encode('utf-8')).hexdigest()


class Comum:
    """Abre a conexão se houver DATABASE_URL. self.ok diz se dá para gravar; self.motivo diz por que não."""

    def __init__(self, robo, versao, onde):
        self.ok, self.motivo, self.cx, self.coleta_id = False, '', None, None
        url = os.environ.get('DATABASE_URL', '').strip()
        if not url:
            self.motivo = 'sem DATABASE_URL nos Secrets (o dono cadastra)'; return
        try:
            import psycopg
            self.cx = psycopg.connect(url, autocommit=True, connect_timeout=30)
            with self.cx.cursor() as c:
                c.execute("insert into comum.coleta (fonte, robo, versao, onde, iniciou, status) "
                          "values (%s,%s,%s,%s, now(), 'rodando') returning id", (FONTE, robo, versao, onde))
                self.coleta_id = c.fetchone()[0]
            self.ok = True
        except Exception as e:
            self.motivo = f'conexão falhou: {type(e).__name__}: {str(e)[:200]}'

    def edicao(self, ente, data, edicao, parte, link, sha256, paginas, id_fonte='', arquivo='', nbytes=None):
        with self.cx.cursor() as c:
            c.execute("""insert into comum.diario_edicao (fonte, ente, data, edicao, parte, link, sha256, paginas, coleta_id,
                                                          id_fonte, arquivo, bytes)
                         values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                         on conflict (fonte, data, edicao, parte) do update
                           set link = excluded.link, sha256 = excluded.sha256, paginas = excluded.paginas,
                               coleta_id = excluded.coleta_id, bytes = excluded.bytes
                         returning id""",
                      (FONTE, ente, data, edicao, parte, link, sha256, paginas, self.coleta_id, id_fonte, arquivo, nbytes))
            return c.fetchone()[0]

    def atos(self, linhas):
        """linhas: dicts com as colunas de comum.diario_ato (sem id/coleta_id). Repetido (mesmo hash_ato) é ignorado."""
        cols = ['edicao_id', 'data', 'fonte', 'ente', 'orgao', 'tipo', 'cnpj', 'razao_receita', 'pessoa_nome', 'cargo',
                'valor', 'processo', 'classe', 'link', 'pagina', 'trecho', 'hash_ato', 'acao', 'papel', 'nivel']
        novos = 0
        with self.cx.cursor() as c:
            for a in linhas:
                a = dict(a, fonte=FONTE)
                for k in ('trecho', 'pessoa_nome', 'cargo', 'papel'):
                    if a.get(k): a[k] = mascarar_cpf(a[k])[:1500 if k == 'trecho' else 300]
                c.execute(f"insert into comum.diario_ato ({', '.join(cols)}, coleta_id) values ({', '.join(['%s'] * len(cols))}, %s) "
                          "on conflict (hash_ato) do nothing", [a.get(k) for k in cols] + [self.coleta_id])
                novos += c.rowcount
        return novos

    def fim(self, status, linhas, erro=''):
        if not self.ok: return
        try:
            with self.cx.cursor() as c:
                c.execute("update comum.coleta set terminou = now(), status = %s, linhas = %s, erro = %s where id = %s",
                          (status, linhas, (erro or None) and erro[:900], self.coleta_id))
        finally:
            self.cx.close()
