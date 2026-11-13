# [12] BASE UNICA CONSOLIDADA (02-Base)  -  v5 (06/11/2026)
# Junta TODAS as coletas numa tabela so de ocorrencias (um documento = uma linha), sem duplicatas, e acumula
# o historico entre execucoes: o que sai da janela de 12 meses da fonte NAO some da base.
# Fontes lidas (o arquivo mais recente de cada; os historicos tambem):
#   IBAMA autos validos + cancelados [4] | IBAMA historico de autos [13] | IBAMA embargos (historico) [4]
#   IBAMA notificacoes, suspensoes, demolicoes, apreensoes, acidentes e licencas [8] | INEA penalidades [13]
#   Diarios municipais [1]/[3] | DOU Secao 3 [5]
# Chave unica por documento (fonte + numero sequencial oficial). Mudou a situacao (ex.: auto cancelado depois,
# embargo desembargado)? Guarda a situacao anterior e a data da mudanca. Nunca apaga linha: so acrescenta/atualiza.
# Antes de gravar, guarda copia da base anterior em 02-Base\historico (dado-fonte nao se perde).
# FATO = documento oficial em base de dados aberta. INDICIO = CNPJ citado em diario oficial (ler o ato).
. "$PSScriptRoot\comum.ps1"
$ACH = Join-Path $RAIZ '04-Achados'; $COL = Join-Path $RAIZ '01-Coletas'; $BAS = Join-Path $RAIZ '02-Base'
$HIS = Join-Path $BAS 'historico'; $SUP = Join-Path $BAS 'supabase'
New-Item -ItemType Directory -Force $BAS, $HIS, $SUP | Out-Null
$STAMP = (Get-Date).ToString('yyyy-MM-dd_HHmm'); $HOJE = (Get-Date).ToString('yyyy-MM-dd')
$ARQ_BASE = Join-Path $BAS 'base_ocorrencias.csv'; $ARQ_EMP = Join-Path $BAS 'base_empresas.csv'
$ini0 = Get-Date; $TOTET = 6
Write-Host "== BASE UNICA CONSOLIDADA ==`n"
Carregar-Municipios
$munOk = @{}; foreach ($v in $script:MUNI.cod.Values) { $munOk[(Norm-Txt $v)] = 1 }

# ---------- 1. base anterior ----------
Cabecalho-Etapa 1 $TOTET 'Lendo a base anterior' $ini0
$BASE = @{}
if (Test-Path $ARQ_BASE) {
  Copy-Item $ARQ_BASE (Join-Path $HIS "base_ocorrencias_ANTES_$STAMP.csv")
  foreach ($r in (Import-Csv $ARQ_BASE -Delimiter ';' -Encoding UTF8)) { $BASE[$r.chave] = $r }
  Write-Host "   $($BASE.Count) ocorrencias na base (copia guardada em 02-Base\historico)"
} else { Write-Host '   Primeira execucao: a base sera criada.' }
# Regra de chave v2 (06/11/2026 21h): chave pelo sequencial do proprio documento. Base gravada com a regra antiga
# e recriada do zero (a copia antiga ja foi guardada em historico; tudo e relido das coletas em 04-Achados e 01-Coletas).
$VERSAO_CHAVE = '2'
if ($BASE.Count -and (@($BASE.Values)[0].versao_chave -ne $VERSAO_CHAVE)) {
  Write-Host "   Regra de chave mudou: base recriada a partir das coletas (copia anterior em 02-Base\historico)." -ForegroundColor Yellow
  $BASE = @{}
}
# 06/11/2026: licencas SISLIC sairam da base (arquivo sem UF nem CNPJ: era o Brasil inteiro). Copia guardada em historico.
$lic = @($BASE.Keys | Where-Object { $_ -like 'IBAMA-LIC|*' }); foreach ($k in $lic) { $BASE.Remove($k) }
if ($lic.Count) { Write-Host "   $($lic.Count) licencas SISLIC retiradas da base (sem UF/CNPJ na fonte)" -ForegroundColor Yellow }
$antes = $BASE.Count

# ---------- 2. ler as coletas ----------
Cabecalho-Etapa 2 $TOTET 'Lendo as coletas de todas as fontes' $ini0
$novas = New-Object System.Collections.ArrayList
$cont = [ordered]@{}
function Linha($o) { [void]$novas.Add([pscustomobject]$o) }
function Ultimos($pasta, $filtro, [int]$qtd = 1) { @(Get-ChildItem $pasta -Filter $filtro -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First $qtd) }
function Doc($d) { $x = ([string]$d) -replace '\D', ''; if ($x.Length -eq 14) { return $x }; return '' }
function TP($tp, $doc) { if ($tp) { return $tp }; $x = ([string]$doc) -replace '[^\d*]', ''; if ($x.Length -eq 14) { 'PJ' } elseif ($doc -match '\*') { 'PF' } else { '' } }
function Ler($arq) { @(Import-Csv $arq.FullName -Delimiter ';' -Encoding UTF8) }
function Corta($t, $n) { $t = [string]$t; if ($t.Length -gt $n) { $t.Substring(0, $n) + '...' } else { $t } }
function Conta($rot, $n, $arq) { $cont[$rot] = $n; Write-Host ("   {0,-34} {1,7} linhas | {2}" -f $rot, $n, $arq) }

# IBAMA autos (validos, cancelados e historicos): todos os arquivos, do mais antigo ao mais novo (o mais novo prevalece)
$arqsA = @(Get-ChildItem $ACH -Filter '*ibama_autos_*RJ_*.csv' -ErrorAction SilentlyContinue | Where-Object { $_.Name -notmatch 'NOVOS' } | Sort-Object LastWriteTime)
$nA = 0
foreach ($a in $arqsA) { foreach ($r in (Ler $a)) { $nA++
  $d = Doc $r.cpf_cnpj
  Linha ([ordered]@{ chave = "IBAMA-AUTO|$(if ($r.n_auto) { "$($r.n_auto)/$($r.serie)" } else { $r.seq_ibama })"; fonte = 'IBAMA Dados Abertos'; orgao = 'IBAMA'; tipo_documento = 'AUTO DE INFRACAO'
    numero = "$($r.n_auto) $($r.serie)".Trim(); processo = $r.processo; data_documento = $r.data_auto; data_ciencia = $r.data_ciencia; prazo_defesa_fim_estimado = $r.prazo_defesa_fim_estimado; prazo_defesa_status = $r.prazo_defesa_status
    situacao = $(if ($r.valido -eq 'NAO' -or $r.cancelado -eq 'S') { 'CANCELADO/EXCLUIDO' } else { 'VALIDO' })
    tipo_pessoa = (TP $r.tipo_pessoa $r.cpf_cnpj); cnpj = $(if ($d) { Cnpj-Fmt $d } else { '' }); doc_mascarado = $r.cpf_cnpj; nome = $r.autuado
    municipio = $r.municipio; cod_ibge = $r.cod_ibge; valor_indicado_RS_NAO_E_DANO = ('{0:0.00}' -f (Num-Br $r.valor_auto_RS_nao_e_dano)).Replace(',', '.')
    assunto = $r.tipo_infracao; descricao = (Corta $r.descricao 400); link_fonte = $r.link; arquivo_origem = $a.Name; nivel = 'FATO' }) } }
Conta 'IBAMA autos (todos os arquivos)' $nA "$($arqsA.Count) arquivos"

# IBAMA embargos: historico completo (01-Coletas\ibama), senao o de vigentes
$aE = Ultimos (Join-Path $COL 'ibama') 'ibama_embargos_HISTORICO_RJ_*.csv'; if (-not $aE.Count) { $aE = Ultimos $ACH 'ibama_embargos_VIGENTES_RJ_*.csv' }
$nE = 0
foreach ($a in $aE) { foreach ($r in (Ler $a)) { $nE++
  $d = Doc $r.CPF_CNPJ_EMBARGADO; $id = if ($r.SEQ_TAD) { $r.SEQ_TAD } else { "$($r.NUM_TAD)-$($r.SER_TAD)" }
  $sit = ([string]$r.status_embargo) -replace ' \(.*$', ''
  Linha ([ordered]@{ chave = "IBAMA-EMB|$id"; fonte = 'IBAMA Dados Abertos'; orgao = 'IBAMA'; tipo_documento = 'TERMO DE EMBARGO'
    numero = "$($r.NUM_TAD) $($r.SER_TAD)".Trim(); processo = $r.NUM_PROCESSO; data_documento = $r.data_embargo; situacao = $sit
    tipo_pessoa = (TP '' $r.CPF_CNPJ_EMBARGADO); cnpj = $(if ($d) { Cnpj-Fmt $d } else { '' }); doc_mascarado = $r.CPF_CNPJ_EMBARGADO; nome = $r.NOME_EMBARGADO
    municipio = $r.municipio_normalizado; cod_ibge = $r.COD_MUNICIPIO; valor_indicado_RS_NAO_E_DANO = ''
    assunto = $r.TIPO_AREA; descricao = (Corta $r.DES_TAD 400); link_fonte = $r.link; arquivo_origem = $a.Name; nivel = 'FATO' }) } }
Conta 'IBAMA embargos (historico)' $nE ($aE | ForEach-Object Name)

# IBAMA notificacoes e suspensoes (colunas detectadas pelo [8])
foreach ($t in @(@('ibama_notificacoes_RJ_*.csv', 'IBAMA-NOT', 'NOTIFICACAO'), @('ibama_suspensoes_RJ_*.csv', 'IBAMA-SUS', 'TERMO DE SUSPENSAO'),
                 @('ibama_demolicoes_RJ_*.csv', 'IBAMA-DEM', 'TERMO DE DEMOLICAO'), @('ibama_apreensoes_RJ_*.csv', 'IBAMA-APR', 'TERMO DE APREENSAO'),
                 @('ibama_acidentes_RJ_*.csv', 'IBAMA-SIEMA', 'ACIDENTE AMBIENTAL (SIEMA)'))) {
  $aN = Ultimos $ACH $t[0]; $n = 0
  foreach ($a in $aN) { foreach ($r in (Ler $a)) { $n++
    $props = @($r.psobject.Properties | ForEach-Object Name)
    # chave = sequencial do PROPRIO documento (SEQ_TAD / SEQ_NOTIFICACAO); nunca SEQ_AUTO_INFRACAO, SEQ_ORDEM etc. (06/11: colisao real)
    $cSeq = @('SEQ_TAD', 'SEQ_NOTIFICACAO', 'FID') | Where-Object { $props -contains $_ } | Select-Object -First 1
    $cNum = @('NUM_TAD', 'CD_TAD', 'NUM_NOTIFICACAO', 'NRO_OCORRENCIA', 'NUM_OCORRENCIA') | Where-Object { $props -contains $_ } | Select-Object -First 1
    $cSer = @('SER_TAD', 'CD_SERIE_TAD', 'SER_NOTIFICACAO') | Where-Object { $props -contains $_ } | Select-Object -First 1
    $cNome = $props | Where-Object { $_ -match '^(NOME|NOM_|NO_PESSOA)' -and $_ -notmatch 'MUNIC|IMOVEL|FANTASIA' } | Select-Object -First 1; $cProc = $props | Where-Object { $_ -match '^(NUM|NU)_PROCESSO' } | Select-Object -First 1
    $cDes = $props | Where-Object { $_ -match '^DES_' -and $_ -notmatch 'STATUS|LOCAL' } | Select-Object -First 1
    $id = if ($cSeq -and $r.$cSeq) { $r.$cSeq } elseif ($cNum -and $r.$cNum) { $r.$cNum } else { "$($r.cpf_cnpj)|$($r.data_documento)" }
    $d = Doc $r.cpf_cnpj
    Linha ([ordered]@{ chave = "$($t[1])|$id"; fonte = 'IBAMA Dados Abertos'; orgao = 'IBAMA'; tipo_documento = $t[2]
      numero = $(if ($cNum) { "$($r.$cNum) $(if ($cSer) { $r.$cSer })".Trim() } else { '' }); processo = $(if ($cProc) { $r.$cProc } else { '' }); data_documento = $r.data_documento
      situacao = $(if ($r.valido -eq 'SIM') { 'VALIDO' } else { 'CANCELADO/EXCLUIDO' })
      tipo_pessoa = $r.tipo_pessoa; cnpj = $(if ($d) { Cnpj-Fmt $d } else { '' }); doc_mascarado = $r.cpf_cnpj; nome = $(if ($cNome) { $r.$cNome } else { '' })
      municipio = $r.municipio_normalizado; cod_ibge = $r.COD_MUNICIPIO; valor_indicado_RS_NAO_E_DANO = ''
      assunto = ''; descricao = $(if ($cDes) { Corta $r.$cDes 400 } else { '' }); link_fonte = $r.link; arquivo_origem = $a.Name; nivel = 'FATO' }) } }
  Conta "IBAMA $($t[2].ToLower())" $n ($aN | ForEach-Object Name)
}

# INEA [13]: penalidades (por empresa). A planilha de acoes (so totais) nao entra na base de ocorrencias.
# A planilha atual do INEA nao traz CNPJ/nome (arquivo AGREGADO): entra na base por municipio, sem empresa.
$aI = Ultimos $ACH 'inea_penalidades_*RJ_*.csv'; $nI = 0
foreach ($a in $aI) { foreach ($r in (Ler $a)) { if (-not $r.numero -and -not $r.processo -and -not $r.cpf_cnpj) { continue }; $nI++
  $d = Doc $r.cpf_cnpj
  $id = if ($r.processo -or $r.numero) { "$($r.processo)|$($r.numero)|$($r.cpf_cnpj)|$($r.data_documento)" } else { "$($r.cpf_cnpj)|$($r.data_documento)|$($r.penalidade)" }
  Linha ([ordered]@{ chave = "INEA-PEN|$id"; fonte = 'INEA via dados abertos RJ'; orgao = 'INEA'; tipo_documento = $(if ($r.cpf_cnpj) { 'PENALIDADE INEA' } else { 'PENALIDADE INEA (fonte sem CNPJ)' })
    numero = $r.numero; processo = $r.processo; data_documento = $r.data_documento; situacao = 'REGISTRADA'
    tipo_pessoa = $r.tipo_pessoa; cnpj = $(if ($d) { Cnpj-Fmt $d } else { '' }); doc_mascarado = $r.cpf_cnpj; nome = $r.nome
    municipio = $r.municipio_normalizado; cod_ibge = ''; valor_indicado_RS_NAO_E_DANO = $r.valor_indicado_RS_NAO_E_DANO
    assunto = $r.penalidade; descricao = ''; link_fonte = $r.link; arquivo_origem = $a.Name; nivel = 'FATO' }) } }
Conta 'INEA penalidades' $nI ($aI | ForEach-Object Name)
# Diarios municipais (Querido Diario) - conferido [3] tem prioridade sobre o bruto [1]
$aD = Ultimos $ACH 'autos_ambientais_CONFERIDO_*.csv'; if (-not $aD.Count) { $aD = Ultimos (Join-Path $COL 'autos_diarios') 'autos_ambientais_CNPJ_*.csv' }
$nD = 0
foreach ($a in $aD) { foreach ($r in (Ler $a)) { $nD++
  $d = Doc $r.cnpj
  Linha ([ordered]@{ chave = "DOM|$d|$($r.data_edicao)|$($r.link_diario)"; fonte = 'Querido Diario / DO municipal'; orgao = "Prefeitura de $($r.municipio)"; tipo_documento = "MENCAO EM DIARIO: $($r.tipo_indicio)"
    numero = $r.edicao; processo = ''; data_documento = $r.data_edicao; situacao = 'INDICIO - ler o ato'
    tipo_pessoa = 'PJ'; cnpj = $(if ($d) { Cnpj-Fmt $d } else { '' }); doc_mascarado = $(if ($d) { Cnpj-Fmt $d } else { '' }); nome = $r.razao_social
    municipio = (Muni-Nome $r.cod_ibge $r.municipio); cod_ibge = $r.cod_ibge; valor_indicado_RS_NAO_E_DANO = ''
    assunto = $r.termo_busca; descricao = (Corta (Mascara-Texto $r.trecho) 400); link_fonte = $r.link_diario; arquivo_origem = $a.Name; nivel = 'INDICIO' }) } }
Conta 'Diarios municipais' $nD ($aD | ForEach-Object Name)

# DOU Secao 3 [5]
$aU = Ultimos $ACH 'dou_editais_CNPJ_*.csv'; $nU = 0
foreach ($a in $aU) { foreach ($r in (Ler $a)) { $nU++
  $d = Doc $r.cnpj
  Linha ([ordered]@{ chave = "DOU|$d|$($r.data_dou)|$($r.link)"; fonte = 'DOU Secao 3'; orgao = $r.orgao; tipo_documento = 'MENCAO NO DOU'
    numero = ''; processo = ''; data_documento = $r.data_dou; situacao = 'INDICIO - ler o ato'
    tipo_pessoa = 'PJ'; cnpj = $(if ($d) { Cnpj-Fmt $d } else { '' }); doc_mascarado = $(if ($d) { Cnpj-Fmt $d } else { '' }); nome = $r.razao_social
    municipio = $(if ($r.menciona_RJ -match '(?i)sim|true') { '(menciona RJ)' } else { '' }); cod_ibge = ''; valor_indicado_RS_NAO_E_DANO = ''
    assunto = ''; descricao = (Corta $r.identificacao 400); link_fonte = $r.link; arquivo_origem = $a.Name; nivel = 'INDICIO' }) } }
Conta 'DOU Secao 3' $nU ($aU | ForEach-Object Name)

# ---------- 3. deduplicar e atualizar ----------
Cabecalho-Etapa 3 $TOTET "Deduplicando $($novas.Count) linhas e atualizando a base" $ini0
$dupMesmaColeta = 0; $nNovo = 0; $nMudou = 0; $nIgual = 0; $vistoAgora = @{}; $mudancas = New-Object System.Collections.ArrayList
$ini = Get-Date; $i = 0
foreach ($o in $novas) {
  $i++; if ($i % 2000 -eq 0) { Progresso $i $novas.Count $ini 'linhas' }
  if ($vistoAgora.ContainsKey($o.chave)) { $dupMesmaColeta++ }
  $vistoAgora[$o.chave] = 1
  $old = $BASE[$o.chave]
  $o | Add-Member primeira_coleta $(if ($old) { $old.primeira_coleta } else { $HOJE }) -Force
  $o | Add-Member ultima_coleta $HOJE -Force
  $o | Add-Member situacao_anterior $(if ($old) { $old.situacao_anterior } else { '' }) -Force
  $o | Add-Member situacao_mudou_em $(if ($old) { $old.situacao_mudou_em } else { '' }) -Force
  if (-not $old) { $nNovo++ }
  elseif ($old.situacao -ne $o.situacao) {
    $nMudou++; $o.situacao_anterior = $old.situacao; $o.situacao_mudou_em = $HOJE
    [void]$mudancas.Add([pscustomobject][ordered]@{ chave = $o.chave; tipo = $o.tipo_documento; numero = $o.numero; cnpj_ou_doc = $o.doc_mascarado; nome = $o.nome; de = $old.situacao; para = $o.situacao; data = $HOJE })
  } else { $nIgual++ }
  $BASE[$o.chave] = $o
}

# ---------- 4. qualidade ----------
Cabecalho-Etapa 4 $TOTET 'Conferindo qualidade (DV, datas, municipios, duplicatas)' $ini0
$Q = [ordered]@{ dv_invalido = 0; sem_data = 0; data_futura = 0; municipio_fora_ibge = 0; possivel_duplicata = 0; sem_documento = 0 }
$assin = @{}
foreach ($r in $BASE.Values) {
  $al = @()
  $c = ([string]$r.cnpj) -replace '\D', ''
  if ($c -and -not (Cnpj-Ok $c)) { $al += 'DV DO CNPJ INVALIDO'; $Q.dv_invalido++ }
  if (-not $r.doc_mascarado) { $al += 'SEM CPF/CNPJ'; $Q.sem_documento++ }
  $dt = Ler-Data $r.data_documento
  $r | Add-Member data_documento_status $(if ($dt) { 'DATA DA FONTE' } else { 'SEM DATA NA FONTE' }) -Force
  # prazo de defesa e calculado de novo a cada execucao (ABERTO vira ENCERRADO com o tempo)
  if ($r.prazo_defesa_fim_estimado) { $pz = Ler-Data $r.prazo_defesa_fim_estimado; if ($pz) { $r | Add-Member prazo_defesa_status $(if ($pz -ge (Get-Date).Date) { 'ABERTO (estimado)' } else { 'ENCERRADO (estimado)' }) -Force } }
  if (-not $dt) { $al += 'SEM DATA'; $Q.sem_data++ } elseif ($dt -gt (Get-Date).AddDays(1)) { $al += 'DATA FUTURA'; $Q.data_futura++ }
  if ($r.municipio -and $r.municipio -notmatch '^\(' -and $munOk.Count -and -not $munOk.ContainsKey((Norm-Txt $r.municipio))) { $al += 'MUNICIPIO FORA DA LISTA IBGE'; $Q.municipio_fora_ibge++ }
  # mesma pessoa/empresa + mesmo tipo + mesmo numero + mesma data com chaves diferentes = possivel duplicata na fonte
  if ($r.numero) { $sig = "$($r.tipo_documento)|$($r.doc_mascarado)|$($r.numero)|$($r.data_documento)"; if ($assin.ContainsKey($sig)) { $al += "POSSIVEL DUPLICATA DE $($assin[$sig])"; $Q.possivel_duplicata++ } else { $assin[$sig] = $r.chave } }
  $r | Add-Member alerta_qualidade ($al -join ' | ') -Force
  $r | Add-Member versao_chave $VERSAO_CHAVE -Force
  $r | Add-Member visto_na_ultima_execucao $(if ($vistoAgora.ContainsKey($r.chave)) { 'SIM' } else { 'NAO (saiu da janela da fonte ou fonte nao rodou)' }) -Force
}

# ---------- 5. tabela de empresas ----------
Cabecalho-Etapa 5 $TOTET 'Montando a tabela de empresas (CNPJ)' $ini0
$cad = @{}; $aC = Ultimo-Arquivo $ACH 'empresas_enriquecidas_RJ_*.csv'
if ($aC) { foreach ($e in (Import-Csv $aC.FullName -Delimiter ';' -Encoding UTF8)) { $cad[($e.cnpj -replace '\D', '')] = $e } }
$porCnpj = @{}
foreach ($r in $BASE.Values) { $c = ([string]$r.cnpj) -replace '\D', ''; if ($c.Length -ne 14) { continue }
  if (-not $porCnpj.ContainsKey($c)) { $porCnpj[$c] = @{ docs = 0; fato = 0; ind = 0; tipos = @{}; fontes = @{}; munis = @{}; prim = '9999'; ult = '0000'; nomes = @{}; validos = 0 } }
  $g = $porCnpj[$c]; $g.docs++; if ($r.nivel -eq 'FATO') { $g.fato++ } else { $g.ind++ }
  if ($r.situacao -notmatch 'CANCELADO|DESEMBARGADO') { $g.validos++ }
  $g.tipos[$r.tipo_documento -replace ':.*$', ''] = 1; $g.fontes[$r.fonte] = 1; if ($r.municipio) { $g.munis[$r.municipio] = 1 }; if ($r.nome) { $g.nomes[$r.nome] = 1 }
  if ($r.data_documento -and $r.data_documento -lt $g.prim) { $g.prim = $r.data_documento }; if ($r.data_documento -gt $g.ult) { $g.ult = $r.data_documento } }
$emp = foreach ($c in $porCnpj.Keys) { $g = $porCnpj[$c]; $e = $cad[$c]
  [pscustomobject][ordered]@{ cnpj = (Cnpj-Fmt $c); cnpj_dv_ok = $(if (Cnpj-Ok $c) { 'SIM' } else { 'NAO' })
    razao_social = $(if ($e) { $e.razao_social } else { 'SEM CADASTRO - rodar [9]' }); nome_fantasia = $(if ($e) { $e.nome_fantasia } else { '' })
    situacao_receita = $(if ($e) { $e.situacao_receita } else { '' }); porte = $(if ($e) { $e.porte } else { '' }); natureza_juridica = $(if ($e) { $e.natureza_juridica } else { '' })
    mei_ou_individual = $(if ($e) { $e.mei_ou_individual } else { '' }); atividade_principal = $(if ($e) { $e.atividade_principal } else { '' }); municipio_sede = $(if ($e) { $e.municipio_sede } else { '' })
    telefone = $(if ($e) { $e.telefone } else { '' }); email = $(if ($e) { $e.email } else { '' })
    ocorrencias = $g.docs; ocorrencias_validas_ou_vigentes = $g.validos; fatos = $g.fato; indicios = $g.ind
    tipos_documento = (($g.tipos.Keys | Sort-Object) -join '; '); fontes = (($g.fontes.Keys | Sort-Object) -join '; '); municipios = (($g.munis.Keys | Sort-Object) -join '; ')
    primeira_ocorrencia = $g.prim; ultima_ocorrencia = $g.ult; nomes_nos_documentos = ((@($g.nomes.Keys) | Select-Object -First 3) -join ' | ')
    alerta_cadastro = $(if ($e) { $e.alerta } else { '' }); data_cadastro = $(if ($e) { $e.data_consulta } else { '' }) } }

# ---------- 6. gravar ----------
Cabecalho-Etapa 6 $TOTET 'Gravando base, empresas, Supabase e relatorio' $ini0
$COLS = 'chave', 'fonte', 'orgao', 'tipo_documento', 'numero', 'processo', 'data_documento', 'data_documento_status', 'data_ciencia', 'prazo_defesa_fim_estimado', 'prazo_defesa_status', 'situacao', 'situacao_anterior', 'situacao_mudou_em', 'tipo_pessoa', 'cnpj', 'doc_mascarado', 'nome', 'municipio', 'cod_ibge', 'valor_indicado_RS_NAO_E_DANO', 'assunto', 'descricao', 'nivel', 'link_fonte', 'arquivo_origem', 'primeira_coleta', 'ultima_coleta', 'visto_na_ultima_execucao', 'alerta_qualidade', 'versao_chave'
$tmp = "$ARQ_BASE.tmp"
$BASE.Values | Sort-Object data_documento -Descending | Select-Object $COLS | Export-Csv $tmp -Delimiter ';' -NoTypeInformation -Encoding UTF8
Move-Item $tmp $ARQ_BASE -Force
@($emp) | Sort-Object ocorrencias -Descending | Export-Csv $ARQ_EMP -Delimiter ';' -NoTypeInformation -Encoding UTF8
if ($mudancas.Count) { $mudancas | Export-Csv (Join-Path $BAS "mudancas_de_situacao_$STAMP.csv") -Delimiter ';' -NoTypeInformation -Encoding UTF8 }
# Supabase: so pessoa juridica com DV ok (PF nunca vai para o banco online)
$fSO = Join-Path $SUP 'ocorrencias_pj.csv'
$BASE.Values | Where-Object { $_.tipo_pessoa -eq 'PJ' -and $_.cnpj -and (Cnpj-Ok $_.cnpj) } | Sort-Object data_documento -Descending |
  Select-Object chave, fonte, orgao, tipo_documento, numero, processo, data_documento, data_documento_status, data_ciencia, prazo_defesa_fim_estimado, prazo_defesa_status, situacao, cnpj, nome, municipio, cod_ibge, valor_indicado_RS_NAO_E_DANO, assunto, descricao, nivel, link_fonte, primeira_coleta, ultima_coleta |
  Export-Csv $fSO -Delimiter ';' -NoTypeInformation -Encoding UTF8
$fSE = Join-Path $SUP 'empresas.csv'; @($emp) | Where-Object { $_.cnpj_dv_ok -eq 'SIM' } | ForEach-Object {
  $x = $_ | Select-Object *; $x } | Export-Csv $fSE -Delimiter ';' -NoTypeInformation -Encoding UTF8

$vaz = 0; foreach ($arq in $ARQ_BASE, $ARQ_EMP, $fSO, $fSE) { foreach ($m in [regex]::Matches((Get-Content $arq -Raw -Encoding UTF8) + '', '(?<![\d/])\d{3}\.?\d{3}\.?\d{3}-?\d{2}(?![\d/])')) { if (Cpf-Ok $m.Value) { $vaz++ } } }
$tot = $BASE.Count
$porFonte = $BASE.Values | Group-Object tipo_documento | Sort-Object Count -Descending | ForEach-Object { '  {0,-40} {1,7}' -f ($_.Name -replace ':.*$', ''), $_.Count }
$rel = @(
  "RELATORIO DA BASE UNICA - $((Get-Date).ToString('dd/MM/yyyy HH:mm'))", '',
  "Ocorrencias na base: $tot (antes: $antes) | novas: $nNovo | situacao mudou: $nMudou | sem mudanca: $nIgual",
  "Linhas lidas nesta execucao: $($novas.Count) | repetidas entre arquivos (deduplicadas): $dupMesmaColeta",
  "Empresas (CNPJ) na base: $(@($emp).Count) | com cadastro da Receita: $(@($emp | Where-Object { $_.razao_social -notlike 'SEM CADASTRO*' }).Count)",
  "Pessoas juridicas / fisicas: $(@($BASE.Values | Where-Object tipo_pessoa -eq 'PJ').Count) / $(@($BASE.Values | Where-Object tipo_pessoa -eq 'PF').Count)",
  "FATO / INDICIO: $(@($BASE.Values | Where-Object nivel -eq 'FATO').Count) / $(@($BASE.Values | Where-Object nivel -eq 'INDICIO').Count)", '',
  'Por tipo de documento:') + $porFonte + @('', 'Lido de cada fonte nesta execucao:') + @($cont.Keys | ForEach-Object { '  {0,-40} {1,7}' -f $_, $cont[$_] }) + @('',
  'Qualidade:') + @($Q.Keys | ForEach-Object { '  {0,-40} {1,7}' -f $_, $Q[$_] }) + @(
  "  CPF aparente nos arquivos (deve ser 0)     $vaz", '',
  'Regras: auto/embargo/notificacao/suspensao = FATO (documento oficial), NAO condenacao; mencao em diario = INDICIO (ler o ato);',
  'valor indicado NAO e dano; PF so com CPF mascarado; arquivos de 02-Base sao internos (supabase\ so PJ).',
  "Arquivos: $ARQ_BASE | $ARQ_EMP | $SUP")
$fR = Join-Path $BAS "relatorio_qualidade_$STAMP.txt"; $rel | Set-Content $fR -Encoding UTF8
Write-Host "`n================ RESUMO ================"; $rel | ForEach-Object { Write-Host $_ }
if ($vaz) { Write-Host "ATENCAO: $vaz possiveis CPFs. NAO publicar." -ForegroundColor Red }
Write-Host "Tempo total: $(Fmt ((Get-Date) - $ini0).TotalSeconds)"
Som
