"""
Gravação na BASE COMUM do gabinete (Supabase mxfgezgmyowqjmaibdkl, schema "comum"), regras de 09/11/2026.

O schema comum não fica exposto: tudo passa por 3 funções RPC da API REST, que só a chave service chama
(a mesma SUPABASE_URL + SUPABASE_SERVICE_KEY que o coletor já usa nos Secrets do GitHub):
  cnpj_pedir      põe CNPJs na fila do robô da Receita (DV conferido; inválido volta em dv_invalido)
  cnpj_consultar  devolve razão social da Receita, situação, CNAE, município, sócios (CPF mascarado)
  diarios_gravar  grava coleta + edições (fonte, ente, data, edicao, parte) + atos (hash_ato único);
                  linha recusada (CPF aberto, DV errado) volta em "rejeitados" sem derrubar o lote.
O banco recusa CPF aberto: tudo passa por mascarar_cpf() antes (formato ***.456.789-**).
"""
import hashlib, json, os, re, urllib.request

FONTE = 'QUERIDO_DIARIO'
PROJETO = 'Ambiental Costa (Camila-boot)'
_CPF_FMT = re.compile(r'(?<![0-9])(\d{3})\.(\d{3})\.(\d{3})[-.](\d{2})(?![0-9])')
_CPF_11 = re.compile(r'(?<![0-9./-])(\d{3})(\d{3})(\d{3})(\d{2})(?![0-9])')


def mascarar_cpf(t):
    """Máscara exigida pelo banco: ***.456.789-** (só os 6 dígitos do meio ficam)."""
    t = _CPF_FMT.sub(lambda m: f'***.{m.group(2)}.{m.group(3)}-**', t or '')
    return _CPF_11.sub(lambda m: f'***.{m.group(2)}.{m.group(3)}-**', t)


def hash_ato(*partes):
    return hashlib.sha256('|'.join(str(p) for p in partes).encode('utf-8')).hexdigest()


class Comum:
    """self.ok diz se dá para gravar; self.motivo diz por que não."""

    def __init__(self, robo, versao, onde):
        self.url = os.environ.get('SUPABASE_URL', '').strip().rstrip('/')
        self.key = os.environ.get('SUPABASE_SERVICE_KEY', '').strip()
        self.robo, self.versao, self.onde = robo, versao, onde
        self.coleta_id, self.rejeitados = None, []
        self.ok = bool(self.url and self.key)
        self.motivo = '' if self.ok else 'sem SUPABASE_URL/SUPABASE_SERVICE_KEY nos Secrets'

    def rpc(self, funcao, corpo):
        req = urllib.request.Request(f'{self.url}/rest/v1/rpc/{funcao}', data=json.dumps(corpo, default=str).encode('utf-8'),
                                     method='POST', headers={'apikey': self.key, 'Authorization': f'Bearer {self.key}',
                                                             'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read().decode('utf-8') or 'null')

    def cnpj_pedir(self, cnpjs):
        return self.rpc('cnpj_pedir', {'cnpjs': sorted(set(cnpjs)), 'projeto': PROJETO}) if cnpjs else {}

    def cnpj_consultar(self, cnpjs):
        """{cnpj: registro da Receita} só dos que a base comum já tem."""
        cnpjs = sorted(set(cnpjs)); out = {}
        for i in range(0, len(cnpjs), 200):
            for r in self.rpc('cnpj_consultar', {'cnpjs': cnpjs[i:i + 200]}) or []:
                out[r['cnpj']] = r
        return out

    def gravar(self, edicoes, atos, lote=300):
        """Edições primeiro (num lote), depois os atos em lotes. Devolve (edições, atos novos, repetidos)."""
        coleta = {'fonte': FONTE, 'robo': self.robo, 'versao': self.versao, 'onde': self.onde}
        for a in atos:
            a['fonte'] = FONTE
            for k in ('trecho', 'pessoa_nome', 'cargo', 'papel'):
                if a.get(k): a[k] = mascarar_cpf(a[k])[:1500 if k == 'trecho' else 300]
        for e in edicoes: e['fonte'] = FONTE
        r = self.rpc('diarios_gravar', {'p': {'coleta': coleta, 'edicoes': edicoes, 'atos': []}})
        self.coleta_id = r['coleta_id']; self.rejeitados += r.get('rejeitados') or []
        n_ed, novos, rep = r.get('edicoes', 0), 0, 0
        for i in range(0, len(atos), lote):
            r = self.rpc('diarios_gravar', {'p': {'coleta_id': self.coleta_id, 'atos': atos[i:i + lote]}})
            novos += r.get('atos_novos', 0); rep += r.get('atos_repetidos', 0); self.rejeitados += r.get('rejeitados') or []
        return n_ed, novos, rep

    def fim(self, status, linhas, erro=''):
        if not (self.ok and self.coleta_id): return
        try:
            self.rpc('diarios_gravar', {'p': {'coleta_id': self.coleta_id,
                                              'coleta': {'status': status, 'linhas': linhas, 'erro': (erro or None) and erro[:900]}}})
        except Exception:
            pass
