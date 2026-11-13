# [9] Enriquecer CNPJs com a base publica da Receita (CNPJ aberto)  -  v5 (06/11/2026)
# Junta os CNPJs de TODAS as coletas (autos validos, embargos vigentes, notificacoes, suspensoes, diarios)
# e busca: razao social, situacao, CNAE, porte, natureza, endereco, telefone e e-mail CADASTRAIS.
# Fontes em ordem (se uma cair, passa para a proxima): BrasilAPI -> Minha Receita -> CNPJ.ws publica -> ReceitaWS.
# Nao contorna captcha nem login. Respeita limite de cada fonte. Cache de 30 dias em 05-Interno.
# Regras: DV do CNPJ conferido antes de consultar; razao social comparada com o nome no documento do IBAMA;
#         MEI / empresario individual: CPF mascarado no nome; contato cadastral mantido (decisao do usuario em 06/11/2026).
# E-mail (07/11/2026): todo CNPJ novo que chega sem e-mail passa pela etapa 2c (CNPJ.ws e ReceitaWS alternados).
# ATENCAO (PowerShell nao diferencia maiusculas): nao reutilize nomes como $f/$p/$n/$k fora das funcoes.
. "$PSScriptRoot\comum.ps1"
$ACH = Join-Path $RAIZ '04-Achados'; $INT = Join-Path $RAIZ '05-Interno'
New-Item -ItemType Directory -Force $ACH, $INT, (Join-Path $RAIZ 'logs') | Out-Null
$STAMP = (Get-Date).ToString('yyyy-MM-dd_HHmm'); $HOJE = (Get-Date).ToString('yyyy-MM-dd')
$LOG = Join-Path $RAIZ "logs\c7_$STAMP.log"
$ARQ_CACHE = Join-Path $INT 'cache_receita_cnpj.json'; $VALIDADE_DIAS = 30
$ARQ_EXCL = Join-Path $INT 'excluir_cnpj.txt'
if (-not (Test-Path $ARQ_EXCL)) {
  @('# CNPJs (ou raiz de 8 digitos) que NAO entram na prospeccao. Um por linha. Linhas com # sao comentario.',
    '# Ex.: grandes empresas fora do perfil, orgaos publicos, clientes atuais, quem pediu para nao ser contatado.',
    '33000167   # Petrobras (todas as filiais)') | Set-Content $ARQ_EXCL -Encoding UTF8
}
$excl = @(Get-Content $ARQ_EXCL -Encoding UTF8 | ForEach-Object { ($_ -replace '#.*$', '') -replace '\D', '' } | Where-Object { $_.Length -ge 8 })
function Excluido($c) { foreach ($e in $excl) { if ($c.StartsWith($e)) { return $true } }; return $false }
$ini0 = Get-Date
Write-Host "== ENRIQUECER CNPJs (base publica da Receita) ==`n"

# ---------- 1. juntar CNPJs de todas as coletas ----------
Write-Host '[1/3] Juntando CNPJs das coletas (arquivos mais recentes de cada fonte)' -ForegroundColor Cyan
$alvo = @{}   # cnpj14 -> @{ nomes=@{}; origens=@{} }
function Add-Alvo($doc, $nome, $origem) {
  $d = ([string]$doc) -replace '\D', ''; if ($d.Length -ne 14) { return }
  if (-not $alvo.ContainsKey($d)) { $alvo[$d] = @{ nomes = @{}; origens = @{} } }
  if ($nome) { $alvo[$d].nomes[([string]$nome).Trim()] = 1 }; $alvo[$d].origens[$origem] = 1
}
$entradas = @(
  @{ filtro = 'ibama_autos_RJ_*.csv'; origem = 'AUTO IBAMA'; doc = 'cpf_cnpj'; nome = 'autuado' },
  @{ filtro = 'ibama_embargos_VIGENTES_RJ_*.csv'; origem = 'EMBARGO VIGENTE IBAMA'; doc = 'CPF_CNPJ_EMBARGADO'; nome = 'NOME_EMBARGADO' },
  @{ filtro = 'ibama_notificacoes_RJ_*.csv'; origem = 'NOTIFICACAO IBAMA'; doc = 'cpf_cnpj'; nome = '' },
  @{ filtro = 'ibama_suspensoes_RJ_*.csv'; origem = 'SUSPENSAO IBAMA'; doc = 'cpf_cnpj'; nome = '' },
  @{ filtro = 'ibama_demolicoes_RJ_*.csv'; origem = 'DEMOLICAO IBAMA'; doc = 'cpf_cnpj'; nome = '' },
  @{ filtro = 'ibama_apreensoes_RJ_*.csv'; origem = 'APREENSAO IBAMA'; doc = 'cpf_cnpj'; nome = '' },
  @{ filtro = 'ibama_acidentes_RJ_*.csv'; origem = 'ACIDENTE SIEMA'; doc = 'cpf_cnpj'; nome = '' },
  @{ filtro = 'ibama_licencas_federais_RJ_*.csv'; origem = 'LICENCA FEDERAL'; doc = 'cpf_cnpj'; nome = '' },
  @{ filtro = 'inea_penalidades_RJ_*.csv'; origem = 'PENALIDADE INEA'; doc = 'cpf_cnpj'; nome = 'nome' },
  @{ filtro = 'dou_editais_CNPJ_*.csv'; origem = 'DOU SECAO 3'; doc = 'cnpj'; nome = '' },
  @{ filtro = 'autos_ambientais_CONFERIDO_*.csv'; origem = 'DIARIO OFICIAL'; doc = 'cnpj'; nome = 'razao_social' }
)
foreach ($ent in $entradas) {
  $arqE = Ultimo-Arquivo $ACH $ent.filtro
  if (-not $arqE) { Write-Host ("   {0,-24} sem arquivo (rode a coleta correspondente)" -f $ent.origem) -ForegroundColor DarkYellow; continue }
  $lin = @(Import-Csv $arqE.FullName -Delimiter ';' -Encoding UTF8)
  if ($ent.origem -match 'NOTIF|SUSP|DEMOL|APREEN|ACIDENTE|LICENCA') { $lin = @($lin | Where-Object { $_.valido -eq 'SIM' }) }
  $antes = $alvo.Count
  foreach ($l in $lin) {
    $nm = if ($ent.nome) { $l.($ent.nome) } else { ($l.psobject.Properties | Where-Object { $_.Name -match '^(NOME|NOM_)' -and $_.Name -notmatch 'MUNIC|IMOVEL|FANTASIA' } | Select-Object -First 1).Value }
    Add-Alvo $l.($ent.doc) $nm $ent.origem
  }
  Write-Host ("   {0,-24} {1,6} linhas | {2,5} CNPJs novos | {3}" -f $ent.origem, $lin.Count, ($alvo.Count - $antes), $arqE.Name)
}
$todos = @($alvo.Keys | Sort-Object)
$dvRuim = @($todos | Where-Object { -not (Cnpj-Ok $_) })
$exc = @($todos | Where-Object { (Cnpj-Ok $_) -and (Excluido $_) })
$lista = @($todos | Where-Object { (Cnpj-Ok $_) -and -not (Excluido $_) })
Write-Host "   Total: $($todos.Count) CNPJs | DV invalido: $($dvRuim.Count) (nao consultados) | na lista de exclusao: $($exc.Count) | a enriquecer: $($lista.Count)"
Add-Content $LOG "alvo=$($todos.Count) dv_ruim=$($dvRuim.Count) excluidos=$($exc.Count) lista=$($lista.Count)"
if ($lista.Count -eq 0) { Write-Host 'Nada para consultar. Rode antes a [4] (IBAMA) e/ou a [8].' -ForegroundColor Yellow; Som; return }

# ---------- 2. consultar (cache + 4 fontes) ----------
$cache = @{}
if (Test-Path $ARQ_CACHE) { try { (Get-Content $ARQ_CACHE -Raw -Encoding UTF8 | ConvertFrom-Json).psobject.Properties | ForEach-Object { $cache[$_.Name] = $_.Value } } catch { Write-Host '   cache ilegivel: sera refeito' -ForegroundColor Yellow } }
function Txt($v) {
  if ($null -eq $v) { return '' }; $t = ([string]$v).Trim()
  # Windows PowerShell 5.1 le JSON sem "charset" como Latin-1: "SÃ£o" -> "São"
  if ($t -match '[ÂÃ][-¿]') { try { $t = [Text.Encoding]::UTF8.GetString([Text.Encoding]::GetEncoding(28591).GetBytes($t)) } catch {} }
  return $t
}
function Fone($ddd, $num) { $d = ((Txt $ddd) + (Txt $num)) -replace '\D', ''; if ($d.Length -ge 10) { $d } else { '' } }
# Quadro de socios (QSA) da base publica do CNPJ: so nome e qualificacao. O CPF do socio NUNCA e gravado.
function Socios($qsa) { @(@($qsa) | Where-Object { $_ -and (Txt $_.nome_socio) } | Select-Object -First 6 | ForEach-Object {
  $n = (Txt $_.nome_socio) -replace '\d{3}\.?\d{3}\.?\d{3}-?\d{2}', '[CPF omitido]'; $q = Txt $_.qualificacao_socio; if ($q) { "$n ($q)" } else { $n } }) -join ' | ' }
function De-BrasilAPI($j, $fonte) {
  $sec = @($j.cnaes_secundarios | Where-Object { $_.codigo -and $_.codigo -ne 0 } | Select-Object -First 5 | ForEach-Object { "$($_.codigo) $($_.descricao)" }) -join ' | '
  [ordered]@{ razao_social = Txt $j.razao_social; nome_fantasia = Txt $j.nome_fantasia; situacao_receita = Txt $j.descricao_situacao_cadastral; data_situacao = Txt $j.data_situacao_cadastral
    natureza_juridica = Txt $j.natureza_juridica; natureza_codigo = Txt $j.codigo_natureza_juridica; porte = Txt $j.porte; opcao_mei = Txt $j.opcao_pelo_mei
    cnae_codigo = Txt $j.cnae_fiscal; cnae_descricao = Txt $j.cnae_fiscal_descricao; cnaes_secundarios = $sec; data_abertura = Txt $j.data_inicio_atividade; capital_social = Txt $j.capital_social
    endereco = ((@((Txt $j.descricao_tipo_de_logradouro), (Txt $j.logradouro)) -join ' ').Trim() + ', ' + (Txt $j.numero) + ' ' + (Txt $j.complemento)).Trim(); bairro = Txt $j.bairro
    cep = Txt $j.cep; municipio_sede = Txt $j.municipio; uf_sede = Txt $j.uf
    telefones = @((Fone '' $j.ddd_telefone_1), (Fone '' $j.ddd_telefone_2) | Where-Object { $_ }) -join ' / '; email = (Txt $j.email).ToLower(); socios = (Socios $j.qsa); fonte = $fonte }
}
function De-CnpjWs($j) {
  $e = $j.estabelecimento
  $sec = @($e.atividades_secundarias | Select-Object -First 5 | ForEach-Object { "$($_.id) $($_.descricao)" }) -join ' | '
  [ordered]@{ razao_social = Txt $j.razao_social; nome_fantasia = Txt $e.nome_fantasia; situacao_receita = Txt $e.situacao_cadastral; data_situacao = Txt $e.data_situacao_cadastral
    natureza_juridica = Txt $j.natureza_juridica.descricao; natureza_codigo = ((Txt $j.natureza_juridica.id) -replace '\D', ''); porte = Txt $j.porte.descricao; opcao_mei = Txt $j.simples.mei
    cnae_codigo = Txt $e.atividade_principal.id; cnae_descricao = Txt $e.atividade_principal.descricao; cnaes_secundarios = $sec; data_abertura = Txt $e.data_inicio_atividade; capital_social = Txt $j.capital_social
    endereco = ((Txt $e.tipo_logradouro) + ' ' + (Txt $e.logradouro) + ', ' + (Txt $e.numero) + ' ' + (Txt $e.complemento)).Trim(); bairro = Txt $e.bairro
    cep = Txt $e.cep; municipio_sede = Txt $e.cidade.nome; uf_sede = Txt $e.estado.sigla
    telefones = @((Fone $e.ddd1 $e.telefone1), (Fone $e.ddd2 $e.telefone2) | Where-Object { $_ }) -join ' / '; email = (Txt $e.email).ToLower(); fonte = 'CNPJ.ws publica (base CNPJ/Receita)' }
}
function De-ReceitaWs($j) {
  if ((Txt $j.status) -eq 'ERROR') { throw "HTTP 404 | ReceitaWS: $(Txt $j.message)" }
  $nat = Txt $j.natureza_juridica; $ap = @($j.atividade_principal)[0]
  $sec = @($j.atividades_secundarias | Select-Object -First 5 | ForEach-Object { "$($_.code) $($_.text)" }) -join ' | '
  [ordered]@{ razao_social = Txt $j.nome; nome_fantasia = Txt $j.fantasia; situacao_receita = Txt $j.situacao; data_situacao = Txt $j.data_situacao
    natureza_juridica = ($nat -replace '^[\d-]+\s*-\s*', ''); natureza_codigo = (([regex]::Match($nat, '^[\d-]+')).Value -replace '\D', ''); porte = Txt $j.porte; opcao_mei = Txt $j.simei.optante
    cnae_codigo = ((Txt $ap.code) -replace '\D', ''); cnae_descricao = Txt $ap.text; cnaes_secundarios = $sec; data_abertura = Txt $j.abertura; capital_social = Txt $j.capital_social
    endereco = ((Txt $j.logradouro) + ', ' + (Txt $j.numero) + ' ' + (Txt $j.complemento)).Trim(); bairro = Txt $j.bairro
    cep = ((Txt $j.cep) -replace '\D', ''); municipio_sede = Txt $j.municipio; uf_sede = Txt $j.uf
    telefones = @(((Txt $j.telefone) -split '/') | ForEach-Object { $_ -replace '\D', '' } | Where-Object { $_.Length -ge 10 }) -join ' / '; email = (Txt $j.email).ToLower(); fonte = 'ReceitaWS (base CNPJ/Receita)' }
}
$PROV = @(
  @{ nome = 'BrasilAPI'; url = 'https://brasilapi.com.br/api/cnpj/v1/{0}'; espera = 1.2; conv = { param($j) De-BrasilAPI $j 'BrasilAPI (base CNPJ/Receita)' } },
  @{ nome = 'MinhaReceita'; url = 'https://minhareceita.org/{0}'; espera = 1.2; conv = { param($j) De-BrasilAPI $j 'Minha Receita (base CNPJ/Receita)' } },
  @{ nome = 'CNPJ.ws'; url = 'https://publica.cnpj.ws/cnpj/{0}'; espera = 21; conv = { param($j) De-CnpjWs $j } },
  @{ nome = 'ReceitaWS'; url = 'https://receitaws.com.br/v1/cnpj/{0}'; espera = 21; conv = { param($j) De-ReceitaWs $j } }
)
foreach ($pv in $PROV) { $pv.ultimo = [datetime]::MinValue; $pv.falhas = 0; $pv.usos = 0 }
function Consultar($c) {
  $nao = 0; $erros = @()
  foreach ($pv in $PROV) {
    if ($pv.falhas -ge 8) { continue }   # 8 falhas seguidas (sem resposta valida): fonte fora do ar nesta execucao, pula
    $w = $pv.espera - ((Get-Date) - $pv.ultimo).TotalSeconds; if ($w -gt 0) { Start-Sleep -Milliseconds ([int]($w * 1000)) }
    try {
      $j = Get-J ($pv.url -f $c) 1; $pv.ultimo = Get-Date
      $r = & $pv.conv $j; if (-not $r.razao_social) { throw 'HTTP 0 | resposta sem razao social' }
      $pv.falhas = 0; $pv.usos++; $r['data_consulta'] = $HOJE; return [pscustomobject]$r
    } catch {
      $pv.ultimo = Get-Date; $cod = Cod-Erro $_; $erros += "$($pv.nome): $(Erro-Texto $_)"
      if ($cod -eq 404) { $pv.falhas = 0; $nao++; if ($nao -ge 2) { break } } else { $pv.falhas++ }
    }
  }
  Add-Content $LOG "$c -> $($erros -join ' || ')"
  if ($nao -ge 2 -or ($nao -ge 1 -and $nao -eq $erros.Count)) { return [pscustomobject]@{ razao_social = 'NAO ENCONTRADO NA RECEITA'; fonte = 'consulta sem resultado'; data_consulta = $HOJE } }
  return $null
}
Write-Host "[2/3] Consultando $($lista.Count) CNPJs (cache de $VALIDADE_DIAS dias: $($cache.Count) guardados)" -ForegroundColor Cyan
$ini = Get-Date; $i = 0; $nCache = 0; $nErro = 0; $nNovo = 0
foreach ($c in $lista) {
  $i++
  $k0 = $cache[$c]; $fresco = $false
  if ($k0 -and $k0.data_consulta) { $dc = Ler-Data $k0.data_consulta; $fresco = ($dc -and ((Get-Date) - $dc).TotalDays -le $VALIDADE_DIAS) }
  if ($fresco) { $nCache++; if ($i % 25 -eq 0) { Progresso $i $lista.Count $ini "(cache) $c" }; continue }
  $r = Consultar $c
  if ($r) {
    # Mantem o que as etapas 2b/2c ja acharam, para nao refazer a busca de e-mail a cada renovacao do cadastro
    if ($k0) { foreach ($cp in 'email', 'email_fonte', 'email_busca_em', 'email_conferido', 'socios') { if (-not (Txt $r.$cp) -and (Txt $k0.$cp)) { $r | Add-Member $cp $k0.$cp -Force } } }
    $cache[$c] = $r; $nNovo++ } else { $nErro++ }
  if ($r) { $fnt = ([string]$r.fonte) -replace ' \(.*', ''; $rot = (Mascara-Texto $r.razao_social) + ' [' + $fnt + ']' } else { $rot = 'ERRO EM TODAS AS FONTES - repetir depois' }
  Progresso $i $lista.Count $ini ((Cnpj-Fmt $c) + ' ' + $rot)
  if ($nNovo % 20 -eq 0) { $cache | ConvertTo-Json -Depth 4 | Set-Content $ARQ_CACHE -Encoding UTF8 }
  if ($nErro -ge 15 -and $nNovo -eq 0) { Write-Host 'Todas as fontes estao falhando. Parando para nao rodar horas com erro (ver log).' -ForegroundColor Red; break }
}
$cache | ConvertTo-Json -Depth 4 | Set-Content $ARQ_CACHE -Encoding UTF8

# ---------- 2b. completar e-mail (06/11/2026) ----------
# A BrasilAPI nao devolve o e-mail da Receita (em 06/11 veio vazio nos 499 CNPJs). A Minha Receita devolve o campo
# "email" da mesma base publica do CNPJ. So consulta quem esta sem e-mail e ainda nao foi conferido nesta validade.
$semMail = @($lista | Where-Object { $k = $cache[$_]; $k -and $k.razao_social -and $k.razao_social -ne 'NAO ENCONTRADO NA RECEITA' -and -not (Txt $k.email_conferido) })
if ($semMail.Count) {
  Write-Host "[2b] Buscando e-mail e socios na Minha Receita para $($semMail.Count) CNPJs" -ForegroundColor Cyan
  $ini2 = Get-Date; $i2 = 0; $achou = 0; $falhaMR = 0; $ultMR = [datetime]::MinValue
  foreach ($c in $semMail) {
    $i2++; $k = $cache[$c]
    $w = 1.2 - ((Get-Date) - $ultMR).TotalSeconds; if ($w -gt 0) { Start-Sleep -Milliseconds ([int]($w * 1000)) }
    try {
      $j = Get-J ("https://minhareceita.org/{0}" -f $c) 1; $ultMR = Get-Date; $falhaMR = 0
      $m = (Txt $j.email).ToLower()
      if ($m -match '@') { $k | Add-Member email $m -Force; $achou++ }
      $so = Socios $j.qsa; if ($so) { $k | Add-Member socios $so -Force }
      if (-not (Txt $k.telefones)) { $t = @((Fone '' $j.ddd_telefone_1), (Fone '' $j.ddd_telefone_2) | Where-Object { $_ }) -join ' / '; if ($t) { $k | Add-Member telefones $t -Force } }
      $k | Add-Member email_conferido $HOJE -Force
    } catch {
      $ultMR = Get-Date; $falhaMR++; Add-Content $LOG "$c -> e-mail MinhaReceita: $(Erro-Texto $_)"
      if ((Cod-Erro $_) -eq 404) { $k | Add-Member email_conferido $HOJE -Force; $falhaMR = 0 }
      if ($falhaMR -ge 8) { Write-Host '   Minha Receita fora do ar agora: e-mails ficam para a proxima execucao.' -ForegroundColor Yellow; break }
    }
    Progresso $i2 $semMail.Count $ini2 "$(Cnpj-Fmt $c) | e-mails achados: $achou"
    if ($i2 % 25 -eq 0) { $cache | ConvertTo-Json -Depth 4 | Set-Content $ARQ_CACHE -Encoding UTF8 }
  }
  $cache | ConvertTo-Json -Depth 4 | Set-Content $ARQ_CACHE -Encoding UTF8
  Write-Host "   E-mails encontrados: $achou de $i2 consultados"
}

# ---------- 2c. e-mail para todo CNPJ que chegar (07/11/2026) ----------
# BrasilAPI nao traz e-mail e a Minha Receita veio com e-mail vazio nos 499 CNPJs (06/11). CNPJ.ws publica e ReceitaWS
# trazem o e-mail cadastral, mas cada uma so aceita 3 consultas por minuto. O script alterna as duas (cerca de 6 por minuto),
# respeita o limite de cada uma e so consulta quem ainda nao tem e-mail e nao foi conferido nos ultimos $REVER_EMAIL dias.
# Assim, na rotina diaria so os CNPJs NOVOS entram aqui. Grava o cache a cada 10 e pode ser interrompido: retoma de onde parou.
# Nao contorna limite nem bloqueio: com 429 a fonte descansa 65 s; com falhas seguidas, a fonte sai desta execucao.
# Obs.: o e-mail da Receita e o que a empresa informou no cadastro; muitas vezes e o do contador.
$REVER_EMAIL = 180
$FE = @(
  @{ nome = 'CNPJ.ws'; url = 'https://publica.cnpj.ws/cnpj/{0}'; espera = 21; prox = [datetime]::MinValue; falhas = 0; ok = 0; achou = 0; fora = $false
     mail = { param($j) (Txt $j.estabelecimento.email).ToLower() }
     soc = { param($j) @(@($j.socios) | Where-Object { $_ -and (Txt $_.nome) } | Select-Object -First 6 | ForEach-Object { $n = (Txt $_.nome) -replace '\d{3}\.?\d{3}\.?\d{3}-?\d{2}', '[CPF omitido]'; $q = Txt $_.qualificacao_socio.descricao; if ($q) { "$n ($q)" } else { $n } }) -join ' | ' } },
  @{ nome = 'ReceitaWS'; url = 'https://receitaws.com.br/v1/cnpj/{0}'; espera = 21; prox = [datetime]::MinValue; falhas = 0; ok = 0; achou = 0; fora = $false
     mail = { param($j) if ((Txt $j.status) -eq 'ERROR') { throw "HTTP 404 | ReceitaWS: $(Txt $j.message)" }; (Txt $j.email).ToLower() }
     soc = { param($j) @(@($j.qsa) | Where-Object { $_ -and (Txt $_.nome) } | Select-Object -First 6 | ForEach-Object { $n = (Txt $_.nome) -replace '\d{3}\.?\d{3}\.?\d{3}-?\d{2}', '[CPF omitido]'; $q = (Txt $_.qual) -replace '^\d+-', ''; if ($q) { "$n ($q)" } else { $n } }) -join ' | ' } }
)
function Precisa-Email($c) {
  $k = $cache[$c]; if (-not $k -or -not $k.razao_social -or $k.razao_social -eq 'NAO ENCONTRADO NA RECEITA') { return $false }
  if ((Txt $k.email) -match '@') { return $false }
  $d = Ler-Data (Txt $k.email_busca_em); return (-not $d) -or (((Get-Date) - $d).TotalDays -gt $REVER_EMAIL)
}
$filaMail = @($lista | Where-Object { (Cnpj-Ok $_) -and -not (Excluido $_) -and (Precisa-Email $_) })
if ($filaMail.Count) {
  $estM = [math]::Ceiling($filaMail.Count * 21 / 2 / 60)
  Write-Host "[2c] E-mail na CNPJ.ws e na ReceitaWS para $($filaMail.Count) CNPJs sem e-mail (estimativa: ~$estM min; pode interromper e retomar)" -ForegroundColor Cyan
  $ini3 = Get-Date; $i3 = 0; $achouT = 0; $pend = New-Object System.Collections.Queue; $filaMail | ForEach-Object { $pend.Enqueue($_) }
  $tentou = @{}
  while ($pend.Count) {
    $ativas = @($FE | Where-Object { -not $_.fora }); if (-not $ativas.Count) { Write-Host '   As duas fontes de e-mail estao fora agora: o resto fica para a proxima execucao.' -ForegroundColor Yellow; break }
    $fx = $ativas | Sort-Object { $_.prox } | Select-Object -First 1
    $w = ($fx.prox - (Get-Date)).TotalSeconds; if ($w -gt 0) { Start-Sleep -Milliseconds ([int]($w * 1000)) }
    $c = $pend.Dequeue(); $k = $cache[$c]
    try {
      $j = Get-J1 ($fx.url -f $c); $fx.prox = (Get-Date).AddSeconds($fx.espera); $fx.falhas = 0; $fx.ok++
      $m = & $fx.mail $j
      if ($m -match '^[^@\s]+@[^@\s]+\.[^@\s]+$') { $k | Add-Member email $m -Force; $k | Add-Member email_fonte "$($fx.nome) (cadastro da Receita)" -Force; $achouT++; $fx.achou++ }
      if (-not (Txt $k.socios)) { $so = & $fx.soc $j; if ($so) { $k | Add-Member socios $so -Force } }
      $k | Add-Member email_busca_em $HOJE -Force; $i3++
    } catch {
      $cod = Cod-Erro $_; Add-Content $LOG "$c -> e-mail $($fx.nome): $(Erro-Texto $_)"
      if ($cod -eq 404) { $k | Add-Member email_busca_em $HOJE -Force; $fx.prox = (Get-Date).AddSeconds($fx.espera); $i3++ }
      else {
        $fx.falhas++; $fx.prox = (Get-Date).AddSeconds($(if ($cod -eq 429) { 65 } else { $fx.espera }))
        if (-not $tentou.ContainsKey("$c|$($fx.nome)")) { $tentou["$c|$($fx.nome)"] = 1; $pend.Enqueue($c) } else { $i3++ }
        if ($fx.falhas -ge 6) { $fx.fora = $true; Write-Host "   $($fx.nome) falhou 6 vezes seguidas: sai desta execucao (ver log)." -ForegroundColor Yellow }
      }
    }
    # Se as fontes respondem mas nao trazem e-mail nenhum, nao adianta rodar horas: avisa e para.
    $okT = 0; foreach ($q in $FE) { $okT += $q.ok }
    if ($okT -ge 40 -and $achouT -eq 0) { Write-Host '   40 respostas sem nenhum e-mail: as fontes nao estao trazendo o campo. Parando a etapa (ver log).' -ForegroundColor Yellow; Add-Content $LOG 'ETAPA 2c PARADA: 40 respostas sem e-mail'; break }
    Progresso ([math]::Max(1, $i3)) $filaMail.Count $ini3 "$(Cnpj-Fmt $c) via $($fx.nome) | e-mails achados: $achouT"
    if ($i3 % 10 -eq 0) { $cache | ConvertTo-Json -Depth 4 | Set-Content $ARQ_CACHE -Encoding UTF8 }
  }
  $cache | ConvertTo-Json -Depth 4 | Set-Content $ARQ_CACHE -Encoding UTF8
  Write-Host "   E-mails encontrados: $achouT | por fonte: $(($FE | ForEach-Object { "$($_.nome) $($_.achou)/$($_.ok)" }) -join ', ')"
  $script:EMAIL_RESUMO = "Etapa 2c: $achouT e-mails em $i3 CNPJs ($(($FE | ForEach-Object { "$($_.nome) $($_.achou)/$($_.ok)" }) -join ', '))"
}

# ---------- 3. montar a planilha ----------
Write-Host '[3/3] Conferindo nomes e gravando' -ForegroundColor Cyan
$RUIDO = '\b(LTDA|ME|EPP|EIRELI|S ?A|SA|CIA|COMPANHIA|DE|DA|DO|DAS|DOS|E|EM|LIMITADA|SOCIEDADE|EMPRESA|EMPRESARIA|MEI|SPE|S/A)\b'
function Tokens($t) { @(((Norm-Txt $t) -replace $RUIDO, ' ') -split ' ' | Where-Object { $_.Length -ge 3 } | Sort-Object -Unique) }
function Parecido($a, $b) {
  $x = Tokens $a; $y = Tokens $b; if (-not $x.Count -or -not $y.Count) { return 0 }
  $com = @($x | Where-Object { $y -contains $_ }).Count; return $com / [math]::Min($x.Count, $y.Count)
}
$saida = foreach ($c in $todos) {
  $k = $cache[$c]; $nomes = @($alvo[$c].nomes.Keys); $orig = (@($alvo[$c].origens.Keys) | Sort-Object) -join '; '
  $alertas = @()
  if (-not (Cnpj-Ok $c)) { $alertas += 'DV DO CNPJ INVALIDO - nao consultado (erro no documento de origem?)' }
  elseif (Excluido $c) { $alertas += 'NA LISTA DE EXCLUSAO (05-Interno\excluir_cnpj.txt)' }
  elseif (-not $k) { $alertas += 'SEM CONSULTA - todas as fontes falharam; rodar [9] de novo' }
  $nat = Txt $k.natureza_juridica; $natc = Txt $k.natureza_codigo
  $indiv = ($natc -eq '2135') -or ($nat -match '(?i)empres[aá]rio.*individual') -or ((Txt $k.opcao_mei) -match '^(?i)(true|sim|s)$') -or ((Txt $k.razao_social) -match '\d{11}')
  $rs = Txt $k.razao_social; if ($indiv) { $rs = (Mascara-Texto $rs) -replace '\d{11}', '[CPF omitido]' } else { $rs = Mascara-Texto $rs }
  if ($k -and $rs -ne 'NAO ENCONTRADO NA RECEITA') {
    $sim = 0; foreach ($nm in $nomes) { $sim = [math]::Max($sim, [math]::Max((Parecido $nm $k.razao_social), (Parecido $nm $k.nome_fantasia))) }
    if ($nomes.Count -and $sim -lt 0.5) { $alertas += 'NOME NO DOCUMENTO DIFERE DA RAZAO SOCIAL - conferir antes de usar' }
    if ((Txt $k.situacao_receita) -and (Txt $k.situacao_receita).ToUpper() -ne 'ATIVA') { $alertas += "SITUACAO NA RECEITA: $((Txt $k.situacao_receita).ToUpper())" }
    if ($natc -match '^1' -or $nat -match '(?i)(munic[ií]pio|estado|uni[aã]o|autarquia|funda[cç][aã]o p[uú]blica|[oó]rg[aã]o p[uú]blico)') { $alertas += 'ORGAO/ENTE PUBLICO - fora do perfil de cliente' }
  }
  $tel = Txt $k.telefones; $mail = Txt $k.email; $soc = Txt $k.socios
  # 06/11/2026 22h: o usuario pediu os MEI (sao o principal publico). Contato comercial da Receita liberado; CPF no nome segue mascarado.
  [pscustomobject][ordered]@{
    cnpj = (Cnpj-Fmt $c); razao_social = $rs; nome_fantasia = (Mascara-Texto (Txt $k.nome_fantasia)); situacao_receita = Txt $k.situacao_receita; data_situacao = Txt $k.data_situacao
    natureza_juridica = $nat; mei_ou_individual = $(if ($indiv) { 'SIM' } else { 'NAO' }); porte = Txt $k.porte
    atividade_principal = ((Txt $k.cnae_codigo) + ' - ' + (Txt $k.cnae_descricao)).Trim(' -'); cnaes_secundarios = Txt $k.cnaes_secundarios
    data_abertura = Txt $k.data_abertura; capital_social = Txt $k.capital_social
    endereco = $(if ($indiv) { '(empresario individual: endereco omitido)' } else { Txt $k.endereco }); bairro = $(if ($indiv) { '' } else { Txt $k.bairro }); cep = $(if ($indiv) { '' } else { Txt $k.cep })
    municipio_sede = $(if ($k.municipio_sede) { "$(Txt $k.municipio_sede)/$(Txt $k.uf_sede)" } else { '' })
    telefone = $(if ($tel) { $tel } else { '(nao informado na Receita)' })
    email = $(if ($mail) { $mail } else { '(nao informado na Receita)' })
    socios = $soc
    email_fonte = $(if ($mail) { Txt $k.email_fonte } else { '' })
    nomes_nos_documentos = ((@($nomes | ForEach-Object { Mascara-Texto $_ }) | Select-Object -First 3) -join ' | '); origens = $orig
    cnpj_dv_ok = $(if (Cnpj-Ok $c) { 'SIM' } else { 'NAO' }); alerta = ($alertas -join ' | ')
    fonte_cadastro = Txt $k.fonte; data_consulta = Txt $k.data_consulta
    classificacao = 'FATO: dado cadastral publico (Receita). Contato cadastral pode estar desatualizado' }
}
$fSaida = Join-Path $ACH "empresas_enriquecidas_RJ_$STAMP.csv"
$saida | Sort-Object { $_.alerta -ne '' }, razao_social | Export-Csv $fSaida -Delimiter ';' -NoTypeInformation -Encoding UTF8
$vaz = 0; foreach ($m in [regex]::Matches((Get-Content $fSaida -Raw -Encoding UTF8) + '', '(?<![\d/])\d{3}\.?\d{3}\.?\d{3}-?\d{2}(?![\d/])')) { if (Cpf-Ok $m.Value) { $vaz++ } }
$ok = @($saida | Where-Object { $_.fonte_cadastro -and $_.razao_social -ne 'NAO ENCONTRADO NA RECEITA' })
Write-Host "`n================ RESUMO ================"
Write-Host "CNPJs: $($todos.Count) | consultados agora: $nNovo | do cache: $nCache | falharam: $nErro | DV invalido: $($dvRuim.Count) | excluidos: $($exc.Count)"
Write-Host "Ativas na Receita: $(@($ok | Where-Object { $_.situacao_receita -match '(?i)^ativa' }).Count) | com telefone: $(@($ok | Where-Object { $_.telefone -match '^\d' }).Count) | com e-mail: $(@($ok | Where-Object { $_.email -match '@' }).Count) | MEI/individual: $(@($ok | Where-Object mei_ou_individual -eq 'SIM').Count)"
Write-Host "Nome diferente da razao social (conferir): $(@($saida | Where-Object { $_.alerta -match 'NOME NO DOCUMENTO' }).Count)"
if ($script:EMAIL_RESUMO) { Write-Host $script:EMAIL_RESUMO }
Write-Host ('Fontes usadas: ' + (($PROV | ForEach-Object { "$($_.nome)=$($_.usos)" }) -join ' | '))
if ($vaz) { Write-Host "ATENCAO: $vaz possiveis CPFs no arquivo. NAO publicar antes de conferir." -ForegroundColor Red } else { Write-Host 'Conferencia de CPF: OK (zero).' -ForegroundColor Green }
Write-Host "`nArquivo: $fSaida`nTempo total: $(Fmt ((Get-Date) - $ini0).TotalSeconds)`nProximo passo: [10] fila de prospeccao."
Som
