# [17] DIARIO ELETRONICO DO INEA  -  v1 (13/11/2026)
# Le a EDICAO DO DIA do Diario Eletronico do INEA (https://diarioeletronico.inea.rj.gov.br/): a mesma lista que a
# pagina usa para montar o PDF do botao "Exportar para PDF". Sem login e sem captcha. A pesquisa com filtros da
# pagina tem reCAPTCHA e NAO e usada. Roda deste PC porque o site nao responde ao GitHub (fora do Brasil).
#
# Separacao (licenciado nao e autuado):
#  - NOTIFICACAO DE FISCALIZACAO de empresa (CNPJ com DV valido) -> 04-Achados\inea-diario\fiscalizacao_*.csv
#    e, se existir 05-Interno\supabase_secret.txt, tabela ocorrencias do site (chave INEA-DE|...), nivel FATO.
#    Notificacao NAO e auto de infracao nem multa: o que foi exigido esta no processo (SEI).
#  - Licenca/documento emitido, pedido e notificacao de licenciamento -> licenciamento_*.csv e tabela
#    inea_licenciamento (se ja existir; criada pelo supabase/09_inea_diario.sql). Nunca vira lead.
# CPF nunca vai para o site nem para os CSVs de achados (pessoa fisica so e contada). Copia bruta do dia em
# 01-Coletas\inea-diario com CPF mascarado. O municipio e o do ENDERECO do interessado, nao do local fiscalizado.
#
# Uso pelo MENU: opcao 17 (le desde o ultimo dia lido; na 1a vez, 30 dias).
# Historico completo (desde 29/08/2023, ~800 dias, ~20 min):  ... c15_inea_diario.ps1 -Desde 2023-08-29
param([string]$Desde = '', [int]$Dias = 0)
. "$PSScriptRoot\comum.ps1"
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
    if ($cat -eq 'NOTIFICACAO DE FISCALIZACAO') {
      $veic = $setor -match 'SERVCPV$'
      $ch = "INEA-DE|$ident|$doc"
      $fisc[$ch] = [pscustomobject][ordered]@{
        chave = $ch; fonte = 'Diário Eletrônico do INEA'; orgao = 'INEA'; tipo_documento = 'NOTIFICACAO INEA (FISCALIZACAO)'
        numero = $numero; processo = $proc; data_documento = $dpub; data_documento_status = 'data de publicação no Diário Eletrônico'
        situacao = 'VALIDO'; cnpj = $cnpjF; nome = (Mascara-Texto $nome); municipio = $mun
        assunto = $(if ($veic) { 'Fiscalização - poluição veicular (INEA/SERVCPV)' } else { 'Fiscalização' })
        descricao = "Notificação publicada no Diário Eletrônico do INEA nº $ed de $($d.ToString('dd/MM/yyyy')). Setor: $(if ($setor) { $setor } else { 'não informado' }). Processo: $(if ($proc) { $proc } else { 'não informado' }). Notificação não é auto de infração nem multa; o que foi exigido está no processo (SEI). Município do endereço do interessado, não necessariamente do local fiscalizado."
        nivel = 'FATO'; link_fonte = $linkIn; ultima_coleta = $hojeIn.ToString('yyyy-MM-dd'); origem = 'radar-pc'
      }
    } else {
      $ch = "INEADE|$cat|$ident|$doc"
      $dval = Vazio-In $x.Data_Validade
      $lic[$ch] = [pscustomobject][ordered]@{
        chave = $ch; categoria = $cat; ato = (Vazio-In $x.Descricao_Instrumento); titulo = $titulo; numero = $numero; processo = $proc
        data_publicacao = $dpub; data_validade = $(if ($cat -eq 'DOCUMENTO EMITIDO' -and $dval.Length -ge 10) { $dval.Substring(0, 10) } else { $null })
        cnpj = $cnpjF; nome = (Mascara-Texto $nome); municipio_endereco = $mun; atividade = (Vazio-In $x.Atividade)
        codigo_atividade = (Vazio-In $x.Codigo_Atividade); classe_impacto = (Vazio-In $x.Classe_Impacto); setor = $setor
        edicao = $ed; link_fonte = $linkIn; ultima_coleta = $hojeIn.ToString('yyyy-MM-dd')
      }
    }
  }
  Progresso $k $diasIn.Count $iniLeit "$($d.ToString('dd/MM')) $($lista.Count) publicacao(oes) | notif. fiscalizacao PJ: $($fisc.Count)"
  Start-Sleep -Milliseconds 800   # nao pesar no servidor do INEA
}

# ---------- 3. arquivos ----------
Cabecalho-Etapa 3 4 'Gravando CSVs em 04-Achados\inea-diario' $iniGeral
$fF = Join-Path $ACH_DIR "fiscalizacao_$STAMP_IN.csv"; $fL = Join-Path $ACH_DIR "licenciamento_$STAMP_IN.csv"
@($fisc.Values) | Sort-Object data_documento -Descending | Export-Csv $fF -Delimiter ';' -NoTypeInformation -Encoding UTF8
@($lic.Values) | Sort-Object data_publicacao -Descending | Export-Csv $fL -Delimiter ';' -NoTypeInformation -Encoding UTF8
if ($ultimoOk -and -not $falhasIn.Count) { Set-Content $ARQ_ULT $ultimoOk.ToString('yyyy-MM-dd') -Encoding ASCII }
elseif ($falhasIn.Count) { Set-Content $ARQ_ULT ([datetime]::ParseExact(($falhasIn | Sort-Object | Select-Object -First 1), 'yyyy-MM-dd', $null)).AddDays(-1).ToString('yyyy-MM-dd') -Encoding ASCII }

# ---------- 4. site (opcional) ----------
Cabecalho-Etapa 4 4 'Enviando ao site (se houver a chave)' $iniGeral
$envF = 0; $envL = 'nao enviado'
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
  $envF = Post-In 'ocorrencias' $fisc.Values
  $r2 = Post-In 'inea_licenciamento' $lic.Values
  $envL = if ($r2 -lt 0) { 'NAO enviado (rode supabase/09_inea_diario.sql no Supabase)' } else { "$r2 enviado(s)" }
  Write-Host "  Notificacoes de fiscalizacao enviadas: $(if ($envF -lt 0) { 'ERRO, veja o log' } else { $envF }) | licenciamento: $envL"
} else { Write-Host '  Sem 05-Interno\supabase_secret.txt: so os CSVs foram gravados.' -ForegroundColor Yellow }

Write-Host "`n================ RESUMO ================"
Write-Host "Publicacoes lidas: $lidosIn"
$contaCat.GetEnumerator() | Sort-Object Value -Descending | ForEach-Object { Write-Host ('  {0,-32} {1}' -f $_.Key, $_.Value) }
Write-Host "Fora: $((($fora.GetEnumerator() | ForEach-Object { "$($_.Key) $($_.Value)" }) -join ', '))"
Write-Host "Notificacoes de fiscalizacao de empresa: $($fisc.Count) ($(@($fisc.Values | Where-Object { $_.assunto -match 'veicular' }).Count) de poluicao veicular)"
Write-Host "Atos de licenciamento de empresa: $($lic.Count)"
if ($falhasIn.Count) { Write-Host "ATENCAO: $($falhasIn.Count) dia(s) sem resposta: $(($falhasIn | Select-Object -First 15) -join ', ') (serao lidos de novo na proxima vez)" -ForegroundColor Yellow }
Write-Host "Arquivos: $fF`n          $fL"
Write-Host "Tempo total: $(Fmt ((Get-Date) - $iniGeral).TotalSeconds)"
Som
