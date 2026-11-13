# [17] DIARIO ELETRONICO DO INEA  -  v1 (13/11/2026)
# Le a EDICAO DO DIA do Diario Eletronico do INEA (https://diarioeletronico.inea.rj.gov.br/): a mesma lista que a
# pagina usa para montar o PDF do botao "Exportar para PDF". Sem login e sem captcha. A pesquisa com filtros da
# pagina tem reCAPTCHA e NAO e usada. Roda deste PC porque o site nao responde ao GitHub (fora do Brasil).
#
# Pedido do usuario (13/11/2026): ficar so com as NOTIFICACOES (v1.1).
#  - NOTIFICACAO DE FISCALIZACAO -> fiscalizacao_*.csv e ocorrencias do site (chave INEA-DE|...).
#  - NOTIFICACAO DE LICENCIAMENTO (exigencia num pedido de licenca; nao e infracao) -> licenciamento_*.csv e
#    ocorrencias do site (chave INEA-DL|...). Ambas FATO, so empresa com DV do CNPJ valido.
#  - Licenca emitida e pedido (requerimento): so contados no RESUMO e descartados.
#  Notificacao NAO e auto de infracao nem multa: o que foi exigido esta no processo (SEI).
#  Envio ao site so se existir 05-Interno\supabase_secret.txt.
# CPF nunca vai para o site nem para os CSVs de achados (pessoa fisica so e contada). Copia bruta do dia em
# 01-Coletas\inea-diario com CPF mascarado. O municipio e o do ENDERECO do interessado, nao do local fiscalizado.
#
# Uso pelo MENU: opcao 17 (le desde o ultimo dia lido; na 1a vez, 30 dias).
# Historico completo (desde 29/08/2023, ~800 dias, ~20 min):  ... c15_inea_diario.ps1 -Desde 2023-08-29
param([string]$Desde = '', [int]$Dias = 0)
if (Test-Path "$PSScriptRoot\comum.ps1") { . "$PSScriptRoot\comum.ps1" }
else {
  # Modo sozinho (sem o Radar-Ambiental): as funcoes que este script usa, iguais as do comum.ps1 v5.1
  $ErrorActionPreference = 'Continue'
  $RAIZ = Split-Path -Parent $PSScriptRoot
  $UA = 'Mozilla/5.0 (Gabinete ALERJ - levantamento de transparencia publica)'
  function Set-Tls($com13) { $p = [Net.SecurityProtocolType]::Tls12; if ($com13) { try { $p = $p -bor [Net.SecurityProtocolType]'Tls13' } catch {} }; [Net.ServicePointManager]::SecurityProtocol = $p }
  function Erro-Texto($e) { try { $m = $e.Exception.Message } catch { $m = "$e" }; return ($m -replace '\s+', ' ').Trim() }
  function Fmt($s) { $t = [TimeSpan]::FromSeconds([int]$s); '{0:00}:{1:00}:{2:00}' -f [int][math]::Floor($t.TotalHours), $t.Minutes, $t.Seconds }
  function Progresso($i, $total, $ini, $txt) {
    $dec = ((Get-Date) - $ini).TotalSeconds; $eta = $dec / $i * ($total - $i)
    $fim = (Get-Date).AddSeconds($eta).ToString('HH:mm')
    Write-Host ('[{0,5:N1}%] {1}/{2} {3} | decorrido {4} | faltam ~{5} | termino ~{6}' -f ($i / $total * 100), $i, $total, $txt, (Fmt $dec), (Fmt $eta), $fim)
  }
  function Som { try { [console]::beep(880,300); [console]::beep(988,300); [console]::beep(1175,400) } catch {} }
  function Cnpj-Ok($c) {
    $d = ($c -replace '\D', ''); if ($d.Length -ne 14 -or $d -match '^(\d)\1{13}$') { return $false }
    $p1 = 5,4,3,2,9,8,7,6,5,4,3,2; $p2 = ,6 + $p1
    $dv = { param($b, $p) $s = 0; for ($k = 0; $k -lt $p.Count; $k++) { $s += [int][string]$b[$k] * $p[$k] }; $r = $s % 11; if ($r -lt 2) { 0 } else { 11 - $r } }
    return ([int][string]$d[12] -eq (& $dv $d $p1)) -and ([int][string]$d[13] -eq (& $dv $d $p2))
  }
  function Cnpj-Fmt($c) { $d = $c -replace '\D', ''; '{0}.{1}.{2}/{3}-{4}' -f $d.Substring(0,2), $d.Substring(2,3), $d.Substring(5,3), $d.Substring(8,4), $d.Substring(12) }
  function Mascara-Cpf($t) { [regex]::Replace($t, '(?<![\d./])(\d{3})\.?(\d{3})\.?(\d{3})-?(\d{2})(?![\d/])', '***.$2.$3-**') }
  function Cpf-Ok($c) {
    $d = ($c -replace '\D', ''); if ($d.Length -ne 11 -or $d -match '^(\d)\1{10}$') { return $false }
    foreach ($n in 9, 10) { $s = 0; for ($i = 0; $i -lt $n; $i++) { $s += [int][string]$d[$i] * ($n + 1 - $i) }; if ((($s * 10) % 11) % 10 -ne [int][string]$d[$n]) { return $false } }
    return $true
  }
  function Mascara-Texto($t) {
    if ($null -eq $t) { return $t }
    $t = [string]$t
    $t = [regex]::Replace($t, '(?i)(CPF\s*[:nº°.]*\s*)\d{3}\.?\d{3}\.?\d{3}(-?\d{2})?', '$1[CPF omitido]')
    $t = [regex]::Replace($t, '(?<![\d/])\d{3}\.?\d{3}\.?\d{3}-?\d{2}(?![\d/])', { param($m) if (Cpf-Ok $m.Value) { '[CPF omitido]' } else { $m.Value } })
    return $t.Trim()
  }
  function Cabecalho-Etapa($n, $tot, $txt, $ini) {
    $dec = ((Get-Date) - $ini).TotalSeconds
    Write-Host ('[{0}/{1}] {2,-55} | {3,5:N1}% | decorrido {4}' -f $n, $tot, $txt, (($n - 1) / $tot * 100), (Fmt $dec)) -ForegroundColor Cyan
  }
}
Set-Tls $true
$SITE_INEA = 'https://diarioeletronico.inea.rj.gov.br/'
$API_INEA = $SITE_INEA + 'DiarioEletronico.Api/Processo/BuscaProcessosDiaAnterior'
$PRIMEIRA_ED = [datetime]'2023-08-29'
$SUPA_URL = if ($env:RADAR_SUPA_URL) { $env:RADAR_SUPA_URL } else { 'https://mxfgezgmyowqjmaibdkl.supabase.co' }
$INT_DIR = Join-Path $RAIZ '05-Interno'
$ARQ_ULT = Join-Path $INT_DIR 'inea_diario_ultimo_dia.txt'
$ARQ_SEGREDO = Join-Path $INT_DIR 'supabase_secret.txt'
$STAMP_IN = (Get-Date).ToString('yyyy-MM-dd_HHmm')
$BRUTO_DIR = Join-Path $RAIZ '01-Coletas\inea-diario'; New-Item -ItemType Directory -Force $BRUTO_DIR | Out-Null
$ACH_DIR = Join-Path $RAIZ '04-Achados\inea-diario'; New-Item -ItemType Directory -Force $ACH_DIR | Out-Null
New-Item -ItemType Directory -Force (Join-Path $RAIZ 'logs') | Out-Null
$LOG_IN = Join-Path $RAIZ "logs\c15_inea_diario_$STAMP_IN.log"
$iniGeral = Get-Date
Write-Host "== DIARIO ELETRONICO DO INEA ==`n"

function Txt-In($v) { if ($null -eq $v) { '' } else { (([string]$v) -replace '\s+', ' ').Trim() } }
function Edicao-In($d) { [int](($d.Date - $PRIMEIRA_ED).TotalDays) + 1 }
function Ler-Dia-In($d, $tent = 4) {
  $corpo = '{"date":"' + $d.ToString('yyyy-MM-dd') + '"}'
  for ($t = 1; $t -le $tent; $t++) {
    try {
      $r = Invoke-WebRequest -UseBasicParsing -Method Post -Uri $API_INEA -UserAgent $UA -TimeoutSec 60 `
        -ContentType 'application/json' -Headers @{ Accept = 'application/json'; Referer = $SITE_INEA } -Body $corpo
      # sempre decodifica os bytes como UTF-8 (o PowerShell 5 pode ler como Latin-1 e estragar os acentos)
      $txt = [Text.Encoding]::UTF8.GetString($r.RawContentStream.ToArray())
      $obj = $txt | ConvertFrom-Json
      $itens = New-Object System.Collections.ArrayList
      foreach ($y in $obj) { if ($y) { [void]$itens.Add($y) } }   # PowerShell 5 devolve a lista inteira como 1 objeto
      return ,@{ texto = $txt; lista = $itens }
    } catch {
      $m = Erro-Texto $_; Add-Content $LOG_IN "$($d.ToString('yyyy-MM-dd')) tentativa $t : $m"
      Start-Sleep -Seconds (2 * $t)
    }
  }
  return $null
}
function Categoria-In($x) {
  if ($x.Tipo -eq 2) { return 'REQUERIMENTO' }
  if ($x.Tipo -eq 0) { return 'DOCUMENTO EMITIDO' }
  if ((Txt-In $x.Descricao_Instrumento_Titulo) -match '(?i)fiscaliza') { return 'NOTIFICACAO DE FISCALIZACAO' }
  return 'NOTIFICACAO DE LICENCIAMENTO'
}
function Vazio-In($v) { $s = Txt-In $v; if ($s -match '^(?i)(null|none|n/a)$') { '' } else { $s } }

# ---------- 1. periodo ----------
Cabecalho-Etapa 1 4 'Periodo e teste de conexao' $iniGeral
$hojeIn = (Get-Date).Date
if ($Desde) { $iniIn = [datetime]::ParseExact($Desde, 'yyyy-MM-dd', $null) }
elseif ($Dias -gt 0) { $iniIn = $hojeIn.AddDays(-$Dias) }
elseif (Test-Path $ARQ_ULT) { $iniIn = ([datetime]::ParseExact((Get-Content $ARQ_ULT -TotalCount 1).Trim(), 'yyyy-MM-dd', $null)).AddDays(-3) }  # 3 dias de folga (publicacao tardia)
else { $iniIn = $hojeIn.AddDays(-30) }
if ($iniIn -lt $PRIMEIRA_ED) { $iniIn = $PRIMEIRA_ED }
$diasIn = @(); for ($d = $iniIn; $d -le $hojeIn; $d = $d.AddDays(1)) { $diasIn += $d }
Write-Host "  De $($iniIn.ToString('dd/MM/yyyy')) a $($hojeIn.ToString('dd/MM/yyyy')): $($diasIn.Count) dia(s)"
$teste = Ler-Dia-In $hojeIn.AddDays(-1) 2
if ($null -eq $teste) { Write-Host "`nO site do INEA nao respondeu ao teste. Nada foi lido. Veja $LOG_IN" -ForegroundColor Red; Som; exit }
Write-Host '  Conexao com o INEA: OK' -ForegroundColor Green

# ---------- 2. leitura dia a dia ----------
Cabecalho-Etapa 2 4 'Lendo as edicoes' $iniGeral
$fisc = @{}; $lic = @{}; $contaCat = @{}; $fora = @{}; $falhasIn = @(); $lidosIn = 0; $ultimoOk = $null
$iniLeit = Get-Date; $k = 0
foreach ($d in $diasIn) {
  $k++
  $res = Ler-Dia-In $d
  if ($null -eq $res) { $falhasIn += $d.ToString('yyyy-MM-dd'); Progresso $k $diasIn.Count $iniLeit "$($d.ToString('dd/MM')) SEM RESPOSTA"; continue }
  $ultimoOk = $d
  $lista = $res.lista
  $lidosIn += $lista.Count
  if ($lista.Count) {
    $mesDir = Join-Path $BRUTO_DIR $d.ToString('yyyy-MM'); New-Item -ItemType Directory -Force $mesDir | Out-Null
    [IO.File]::WriteAllText((Join-Path $mesDir ($d.ToString('yyyy-MM-dd') + '.json')), (Mascara-Cpf $res.texto), [Text.Encoding]::UTF8)
  }
  $ed = Edicao-In $d
  $linkIn = "$SITE_INEA (edicao n. $ed de $($d.ToString('dd/MM/yyyy')))"
  foreach ($x in $lista) {
    $cat = Categoria-In $x; $contaCat[$cat] = 1 + [int]$contaCat[$cat]
    $doc = (Txt-In $x.Documento) -replace '\D', ''
    $nome = Vazio-In $x.Nome_Requerente
    if ($nome -match '(?i)\bTESTE\b') { $fora['teste do INEA'] = 1 + [int]$fora['teste do INEA']; continue }
    if ($doc.Length -eq 11) { $fora['pessoa fisica (fora)'] = 1 + [int]$fora['pessoa fisica (fora)']; continue }
    if (-not (Cnpj-Ok $doc)) { $fora['sem CNPJ valido'] = 1 + [int]$fora['sem CNPJ valido']; continue }
    $titulo = (Vazio-In $x.Descricao_Instrumento_Titulo) -replace '\s*\(\)\s*$', ''
    $numero = Vazio-In $x.Numero_Documento; $proc = Vazio-In $x.Processo; $setor = Vazio-In $x.Setor_Sigla
    $dpub = (Vazio-In $x.Data_Publicacao); $dpub = if ($dpub.Length -ge 10) { $dpub.Substring(0, 10) } else { $d.ToString('yyyy-MM-dd') }
    $mun = Vazio-In $x.Municipio; if ($mun -match '^(?i)todos') { $mun = '' }
    $ident = if ($numero) { $numero } else { "$(Txt-In $x.IdRequerimento)-$proc-$titulo" }
    $cnpjF = Cnpj-Fmt $doc
    if ($cat -notmatch '^NOTIFICACAO') { $fora["$($cat.ToLower()) (fora)"] = 1 + [int]$fora["$($cat.ToLower()) (fora)"]; continue }
    $ehFisc = ($cat -eq 'NOTIFICACAO DE FISCALIZACAO')
    $veic = $ehFisc -and ($setor -match 'SERVCPV$')
    $ativ = Vazio-In $x.Atividade; $codAt = Vazio-In $x.Codigo_Atividade
    $assn = if ($ehFisc) { if ($veic) { 'Fiscalização - poluição veicular (INEA/SERVCPV)' } else { 'Fiscalização' } } elseif ($titulo) { "Licenciamento - $titulo" } else { 'Licenciamento' }
    if ($ativ) { $assn = ("$assn · atividade $codAt $ativ").Trim() }
    if ($assn.Length -gt 200) { $assn = $assn.Substring(0, 200) }
    $natur = if ($ehFisc) { 'Notificação não é auto de infração nem multa; o que foi exigido está no processo (SEI).' } else { 'Notificação de exigência num pedido de licença: não é infração; o que falta entregar está no processo (SEI).' }
    $ch = "$(if ($ehFisc) { 'INEA-DE' } else { 'INEA-DL' })|$ident|$doc"
    $linhaOc = [pscustomobject][ordered]@{
      chave = $ch; fonte = 'Diário Eletrônico do INEA'; orgao = 'INEA'
      tipo_documento = $(if ($ehFisc) { 'NOTIFICACAO INEA (FISCALIZACAO)' } else { 'NOTIFICACAO INEA (LICENCIAMENTO)' })
      numero = $numero; processo = $proc; data_documento = $dpub; data_documento_status = 'data de publicação no Diário Eletrônico'
      situacao = 'VALIDO'; cnpj = $cnpjF; nome = (Mascara-Texto $nome); municipio = $mun; assunto = $assn
      descricao = "Notificação publicada no Diário Eletrônico do INEA nº $ed de $($d.ToString('dd/MM/yyyy')). Setor: $(if ($setor) { $setor } else { 'não informado' }). Processo: $(if ($proc) { $proc } else { 'não informado' }). $natur Município do endereço do interessado, não necessariamente do local da atividade."
      nivel = 'FATO'; link_fonte = $linkIn; ultima_coleta = $hojeIn.ToString('yyyy-MM-dd'); origem = 'radar-pc'
    }
    if ($ehFisc) { $fisc[$ch] = $linhaOc } else { $lic[$ch] = $linhaOc }
  }
  Progresso $k $diasIn.Count $iniLeit "$($d.ToString('dd/MM')) $($lista.Count) publicacao(oes) | notif. fiscalizacao PJ: $($fisc.Count)"
  Start-Sleep -Milliseconds 800   # nao pesar no servidor do INEA
}

# ---------- 3. arquivos ----------
Cabecalho-Etapa 3 4 'Gravando CSVs em 04-Achados\inea-diario' $iniGeral
$fF = Join-Path $ACH_DIR "fiscalizacao_$STAMP_IN.csv"; $fL = Join-Path $ACH_DIR "licenciamento_$STAMP_IN.csv"
@($fisc.Values) | Sort-Object data_documento -Descending | Export-Csv $fF -Delimiter ';' -NoTypeInformation -Encoding UTF8
@($lic.Values) | Sort-Object data_documento -Descending | Export-Csv $fL -Delimiter ';' -NoTypeInformation -Encoding UTF8
if ($ultimoOk -and -not $falhasIn.Count) { Set-Content $ARQ_ULT $ultimoOk.ToString('yyyy-MM-dd') -Encoding ASCII }
elseif ($falhasIn.Count) { Set-Content $ARQ_ULT ([datetime]::ParseExact(($falhasIn | Sort-Object | Select-Object -First 1), 'yyyy-MM-dd', $null)).AddDays(-1).ToString('yyyy-MM-dd') -Encoding ASCII }

# ---------- 4. site (opcional) ----------
Cabecalho-Etapa 4 4 'Enviando ao site (se houver a chave)' $iniGeral
$envF = 0
if (Test-Path $ARQ_SEGREDO) {
  $segredo = (Get-Content -LiteralPath $ARQ_SEGREDO -TotalCount 1 -Encoding UTF8 | Out-String).Trim()
  function Post-In($tabela, $linhas) {
    $todas = @($linhas); $ok = 0
    for ($i = 0; $i -lt $todas.Count; $i += 500) {
      $parte = $todas[$i..([math]::Min($todas.Count, $i + 500) - 1)]
      $bytes = [Text.Encoding]::UTF8.GetBytes((ConvertTo-Json -InputObject @($parte) -Depth 3 -Compress))
      try {
        Invoke-WebRequest -UseBasicParsing -Method Post -Uri ("$SUPA_URL/rest/v1/$tabela" + '?on_conflict=chave') -TimeoutSec 120 `
          -Headers @{ apikey = $segredo; Prefer = 'resolution=merge-duplicates,return=minimal' } -ContentType 'application/json; charset=utf-8' -Body $bytes | Out-Null
        $ok += @($parte).Count
      } catch { Add-Content $LOG_IN "$tabela : $(Erro-Texto $_)"; return -1 }
    }
    return $ok
  }
  $envF = Post-In 'ocorrencias' (@($fisc.Values) + @($lic.Values))
  Write-Host "  Notificacoes enviadas ao site (fiscalizacao + licenciamento): $(if ($envF -lt 0) { 'ERRO, veja o log' } else { $envF })"
} else { Write-Host '  Sem 05-Interno\supabase_secret.txt: so os CSVs foram gravados.' -ForegroundColor Yellow }

Write-Host "`n================ RESUMO ================"
Write-Host "Publicacoes lidas: $lidosIn"
$contaCat.GetEnumerator() | Sort-Object Value -Descending | ForEach-Object { Write-Host ('  {0,-32} {1}' -f $_.Key, $_.Value) }
Write-Host "Fora: $((($fora.GetEnumerator() | ForEach-Object { "$($_.Key) $($_.Value)" }) -join ', '))"
Write-Host "Notificacoes de fiscalizacao de empresa: $($fisc.Count) ($(@($fisc.Values | Where-Object { $_.assunto -match 'veicular' }).Count) de poluicao veicular)"
Write-Host "Notificacoes de licenciamento de empresa: $($lic.Count)"
if ($falhasIn.Count) { Write-Host "ATENCAO: $($falhasIn.Count) dia(s) sem resposta: $(($falhasIn | Select-Object -First 15) -join ', ') (serao lidos de novo na proxima vez)" -ForegroundColor Yellow }
Write-Host "Arquivos: $fF`n          $fL"
Write-Host "Tempo total: $(Fmt ((Get-Date) - $iniGeral).TotalSeconds)"
Som
