# [5] DOU Secao 3: editais de notificacao/intimacao de orgaos ambientais (IBAMA, ICMBio, MMA, ANA)
# v4 (06/11/2026) - baseado na automacao oficial do INLABS (github.com/Imprensa-Nacional/inlabs)
#
# FONTES (nenhuma sozinha):
#   A) INLABS diario (DO3 + DO3E extras). Ultimos ~4 meses. Login SEU.
#   B) Base mensal de Dados Abertos da Imprensa Nacional (S03MMAAAA.zip). Reserva quando o INLABS
#      esta fora do ar/manutencao ou a data passou de 4 meses. Pergunta antes de baixar (arquivo grande).
#      Tambem aceita o zip baixado A MAO e colocado em 01-Coletas\dou\mensal\
#   C) Edicoes ja baixadas em 01-Coletas\dou (cache/reserva local).
#
# LOGIN: feito por voce. Opcao [6] do menu guarda o login criptografado pelo Windows (DPAPI): so o seu
# usuario neste computador consegue abrir. A senha nunca aparece na tela, no log nem nos CSVs.
param([switch]$Cadastrar, [switch]$Esquecer, [int]$Dias = 0)
. "$PSScriptRoot\comum.ps1"
$ProgressPreference = 'SilentlyContinue'
Add-Type -AssemblyName System.IO.Compression, System.IO.Compression.FileSystem
$BASE = Join-Path $RAIZ '01-Coletas\dou'; $MENSAL = Join-Path $BASE 'mensal'; $ACH = Join-Path $RAIZ '04-Achados'; $INT = Join-Path $RAIZ '05-Interno'
New-Item -ItemType Directory -Force $BASE, $MENSAL, $ACH, $INT, (Join-Path $RAIZ 'logs') | Out-Null
$ARQ_CRED = Join-Path $INT 'inlabs_login.xml'
$STAMP = (Get-Date).ToString('yyyy-MM-dd_HHmm'); $HOJE = (Get-Date).ToString('yyyy-MM-dd'); $LOG = Join-Path $RAIZ "logs\c5_$STAMP.log"
$INLABS = 'https://inlabs.in.gov.br'
$ORIGEM = @{ origem = '736372697074' }   # cabecalho usado pelos scripts oficiais do INLABS
$DADOS_ABERTOS = 'https://www.in.gov.br/acesso-a-informacao/dados-abertos/base-de-dados'
$SECOES = 'DO3', 'DO3E'
$LIMITE_INLABS = 120   # dias disponiveis no INLABS (README oficial: ultimos 4 meses)
$ORGAO = 'Instituto Brasileiro do Meio Ambiente|Instituto Chico Mendes|Meio Ambiente|Ag[eê]ncia Nacional de [AÁ]guas'
$ASSUNTO = 'auto de infra|notifica|intima|embargo|multa|penalidade|infrator|autuad'
$NA_FILA = ([int]("0" + $env:RADAR_FILA)) -gt 1   # rodando junto com outras tarefas: nao parar para perguntar

# ---------- [6] guardar / apagar login ----------
if ($Esquecer) { Remove-Item $ARQ_CRED -ErrorAction SilentlyContinue; Write-Host 'Login do INLABS apagado deste computador.' -ForegroundColor Green; exit 0 }
if ($Cadastrar) {
  Write-Host "Digite o e-mail e a senha do INLABS na janela que vai abrir.`nFica salvo criptografado (DPAPI) em 05-Interno\inlabs_login.xml - so o seu usuario do Windows abre."
  $c = Get-Credential -Message 'Login do INLABS (inlabs.in.gov.br)'
  if (-not $c) { Write-Host 'Cancelado.'; exit 1 }
  $c | Export-Clixml $ARQ_CRED
  Write-Host 'Login guardado. Agora a opcao [5] roda na fila sem parar para pedir senha.' -ForegroundColor Green; Som; exit 0
}

Write-Host "== DOU SECAO 3: EDITAIS AMBIENTAIS (IBAMA, ICMBio, MMA, ANA) ==`nFontes: INLABS diario -> base mensal Dados Abertos -> copia local`n"
if ($Dias -le 0) {
  if ($NA_FILA) { $Dias = 7; Write-Host 'Na fila: usando 7 dias.' }
  else { $Dias = Read-Host 'Quantos dias para tras? (Enter = 7)'; if (-not ($Dias -as [int])) { $Dias = 7 } else { $Dias = [int]$Dias } }
}

# ---------- funcoes ----------
function Testar-Inlabs {
  # Teste previo: evita pedir senha e rodar a toa quando o site esta em manutencao
  try {
    $r = Invoke-WebRequest "$INLABS/" -UserAgent $UA -UseBasicParsing -TimeoutSec 30
    if ($r.Content -match '(?i)manuten') { return 'EM MANUTENCAO' }
    return 'OK'
  } catch {
    $t = Erro-Texto $_; Add-Content $LOG "teste INLABS: $t"
    if ($t -match '(?i)manuten') { return 'EM MANUTENCAO' }
    return "FORA DO AR ($((Cod-Erro $_)))"
  }
}
function Login-Inlabs($cred) {
  $b = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($cred.Password)
  try {
    $senha = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($b)
    $null = Invoke-WebRequest "$INLABS/logar.php" -Method Post -Body @{ email = $cred.UserName; password = $senha } -Headers $ORIGEM -SessionVariable SESSAO -UserAgent $UA -UseBasicParsing -TimeoutSec 60
  } catch { Write-Host "Falha no login: $(Erro-Texto $_)" -ForegroundColor Yellow; Add-Content $LOG "login: $(Erro-Texto $_)"; return $null }
  finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($b); $senha = $null }
  if (-not $SESSAO.Cookies.GetCookies($INLABS)['inlabs_session_cookie']) { Write-Host 'Login nao aceito (sem cookie de sessao). Confira e-mail/senha no site do INLABS.' -ForegroundColor Yellow; return $null }
  return $SESSAO
}
function Eh-Zip($arq) { $fs = [IO.File]::OpenRead($arq); $pk = New-Object byte[] 2; [void]$fs.Read($pk, 0, 2); $fs.Close(); ($pk[0] -eq 0x50 -and $pk[1] -eq 0x4B) }

$atos = New-Object System.Collections.ArrayList; $cnpjs = New-Object System.Collections.ArrayList
$vistos = New-Object 'System.Collections.Generic.HashSet[string]'
$datasLidas = New-Object 'System.Collections.Generic.HashSet[string]'   # datas que realmente apareceram nos arquivos
function Ler-Artigo([string]$xmlTexto, [string]$fonte, $soDatas) {
  # Le um XML de materia do DOU (mesmo formato no INLABS e na base mensal). Devolve 1 se for ato ambiental.
  try { [xml]$x = $xmlTexto } catch { return 0 }
  $a = $x.SelectSingleNode('//article'); if (-not $a) { return 0 }
  $pub = $a.GetAttribute('pubDate'); if ($soDatas -and -not $soDatas.Contains($pub)) { return 0 }
  [void]$script:datasLidas.Add($pub)
  $cat = $a.GetAttribute('artCategory'); if ($cat -notmatch $ORGAO) { return 0 }
  $partes = @($a.SelectNodes('.//body/*') | ForEach-Object { $_.InnerText }); $bruto = if ($partes) { $partes -join ' ' } else { $a.InnerText }
  $txt = ($bruto -replace '<[^>]+>', ' ' -replace '&nbsp;', ' ' -replace '\s+', ' ').Trim()
  if ($txt -notmatch $ASSUNTO) { return 0 }
  $chave = "$($a.GetAttribute('id'))|$($a.GetAttribute('idMateria'))|$pub"; if (-not $script:vistos.Add($chave)) { return 0 }
  $rj = if (($cat + ' ' + $txt) -match 'Rio de Janeiro|/RJ\b|\bRJ\b') { 'SIM' } else { '' }
  $ident = $a.SelectSingleNode('.//Identifica'); $ident = if ($ident) { $ident.InnerText.Trim() } else { $a.GetAttribute('name') }
  $link = $a.GetAttribute('pdfPage')
  $docs = @(); foreach ($mm in [regex]::Matches($txt, '(?<!\d)\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}(?!\d)')) { if (Cnpj-Ok $mm.Value) { $docs += (Cnpj-Fmt $mm.Value) } }
  $docs = @($docs | Sort-Object -Unique)
  $nautos = @([regex]::Matches($txt, '(?i)autos? de infra[cç][aã]o\s*(?:n[º°o]\.?|n[uú]mero)?\s*[:.]?\s*([A-Z]{0,4}\d[0-9A-Z]{4,11}(?:-[A-Z])?)\b') | ForEach-Object { $_.Groups[1].Value } | Sort-Object -Unique)
  [void]$script:atos.Add([pscustomobject][ordered]@{ data_dou = $pub; secao = $a.GetAttribute('pubName'); pagina = $a.GetAttribute('numberPage')
    orgao = $cat; tipo_ato = $a.GetAttribute('artType'); identificacao = (Mascara-Texto $ident); menciona_RJ = $rj; cnpjs = ($docs -join ' | '); qtd_cnpjs = $docs.Count
    n_autos_citados = ($nautos -join ' | '); trecho = (Mascara-Texto ($txt.Substring(0, [math]::Min(1500, $txt.Length))))
    link = $link; fonte = $fonte; data_coleta = $HOJE
    metodo = "artCategory ~ orgao ambiental e texto ~ ($ASSUNTO); CPF mascarado; CNPJ com DV conferido"
    classificacao = 'FATO: ato publicado no DOU. Notificacao/intimacao NAO e condenacao' })
  foreach ($c in $docs) { [void]$script:cnpjs.Add([pscustomobject][ordered]@{ cnpj = $c; razao_social = 'CONFERIR NA RECEITA'; data_dou = $pub; orgao = $cat; identificacao = (Mascara-Texto $ident); menciona_RJ = $rj; link = $link; fonte = $fonte; data_coleta = $HOJE }) }
  return 1
}
function Ler-Zip($zipArq, [string]$fonte, $soDatas, [switch]$mostrar) {
  # Le os XML direto de dentro do zip (sem extrair). Aceita zip dentro de zip (base mensal).
  $n = 0; $z = [IO.Compression.ZipFile]::OpenRead($zipArq)
  try {
    $ents = @($z.Entries); $tot = [math]::Max(1, $ents.Count); $ini = Get-Date; $ult = Get-Date; $k = 0
    foreach ($e in $ents) {
      $k++
      if ($e.FullName -match '(?i)\.xml$') { $sr = New-Object IO.StreamReader($e.Open(), [Text.Encoding]::UTF8); $n += Ler-Artigo $sr.ReadToEnd() $fonte $soDatas; $sr.Close() }
      elseif ($e.FullName -match '(?i)\.zip$') {
        $tmp = [IO.Path]::GetTempFileName(); [IO.Compression.ZipFileExtensions]::ExtractToFile($e, $tmp, $true)
        try { $n += Ler-Zip $tmp $fonte $soDatas } finally { Remove-Item $tmp -ErrorAction SilentlyContinue }
      }
      if ($mostrar -and ((Get-Date) - $ult).TotalSeconds -ge 5) { $ult = Get-Date; Progresso $k $tot $ini "lendo $(Split-Path $zipArq -Leaf) | atos ambientais: $n" }
    }
  } finally { $z.Dispose() }
  return $n
}

# ---------- A) INLABS ----------
$datas = @(0..($Dias - 1) | ForEach-Object { (Get-Date).Date.AddDays(-$_) } | Where-Object { $_.DayOfWeek -ne 'Saturday' -and $_.DayOfWeek -ne 'Sunday' })
$cob = New-Object System.Collections.ArrayList
Write-Host 'Testando o INLABS...'
$sitInlabs = Testar-Inlabs
$SESSAO = $null
if ($sitInlabs -eq 'OK') {
  Write-Host '  INLABS no ar.' -ForegroundColor Green
  $cred = $null
  if (Test-Path $ARQ_CRED) { try { $cred = Import-Clixml $ARQ_CRED; Write-Host '  Usando o login guardado (opcao 6).' } catch { Write-Host '  Login guardado nao abriu (outro usuario/PC?). Refaca na opcao 6.' -ForegroundColor Yellow } }
  if (-not $cred -and -not $NA_FILA) {
    $email = Read-Host 'E-mail do INLABS (Enter = pular o INLABS)'
    if ($email) { $sec = Read-Host 'Senha do INLABS (nao aparece na tela)' -AsSecureString; $cred = New-Object Management.Automation.PSCredential($email, $sec)
                  Write-Host '  Dica: a opcao [6] guarda o login para a fila rodar sozinha.' -ForegroundColor DarkGray }
  }
  if (-not $cred -and $NA_FILA) { Write-Host '  Sem login guardado e rodando na fila: INLABS pulado (use a opcao 6 uma vez).' -ForegroundColor Yellow; $sitInlabs = 'SEM LOGIN' }
  elseif ($cred) { $SESSAO = Login-Inlabs $cred; if ($SESSAO) { Write-Host '  Login OK.' -ForegroundColor Green } else { $sitInlabs = 'LOGIN FALHOU' } }
  else { $sitInlabs = 'PULADO' }
} else { Write-Host "  INLABS $sitInlabs. Vou usar as reservas (copia local e base mensal)." -ForegroundColor Yellow }

$tarefas = foreach ($d in $datas) { foreach ($sx in $SECOES) { [pscustomobject]@{ d = $d; s = $sx } } }
$ini = Get-Date; $i = 0
foreach ($t in $tarefas) {
  $i++; $ds = $t.d.ToString('yyyy-MM-dd'); $nome = "$ds-$($t.s).zip"; $zip = Join-Path $BASE $nome; $st = 'OK'
  $recente = $t.d -ge (Get-Date).Date.AddDays(-1)
  if ((Test-Path $zip) -and -not ($recente -and $SESSAO)) { $st = 'CACHE' }
  elseif (((Get-Date).Date - $t.d).TotalDays -gt $LIMITE_INLABS) { $st = 'FORA DO PRAZO INLABS' }
  elseif (-not $SESSAO) { $st = if (Test-Path $zip) { 'RESERVA (copia local)' } else { "INLABS $sitInlabs" } }
  else {
    try {
      Invoke-WebRequest "$INLABS/index.php?p=$ds&dl=$nome" -WebSession $SESSAO -Headers $ORIGEM -OutFile "$zip.tmp" -UserAgent $UA -UseBasicParsing -TimeoutSec 300
      if (-not (Eh-Zip "$zip.tmp")) {
        # nao e ZIP: sem edicao, sessao expirada ou manutencao (o site devolve pagina HTML)
        $html = Get-Content "$zip.tmp" -Raw -ErrorAction SilentlyContinue; Remove-Item "$zip.tmp"
        $st = if ($html -match '(?i)manuten') { 'ERRO MANUTENCAO' } elseif ($html -match '(?i)logar|login|senha') { 'ERRO SESSAO' } else { 'SEM EDICAO' }
      } else { Move-Item "$zip.tmp" $zip -Force }
    } catch {
      Remove-Item "$zip.tmp" -ErrorAction SilentlyContinue; $c = Cod-Erro $_; $st = if ($c -eq 404) { 'SEM EDICAO' } else { "ERRO $c" }; Add-Content $LOG "$nome : $(Erro-Texto $_)"
    }
    if ($st -like 'ERRO*' -and (Test-Path $zip)) { $st = 'RESERVA (copia local)' }
  }
  if ($st -eq 'SEM EDICAO' -and $t.s -eq 'DO3E') { $st = 'SEM EXTRA' }
  $n = 0
  if ((Test-Path $zip) -and $st -notlike 'ERRO*') {
    try { $n = Ler-Zip $zip "DOU $($t.s) via INLABS (Imprensa Nacional)" $null } catch { $st = 'ZIP INVALIDO'; Add-Content $LOG "$nome zip invalido: $($_.Exception.Message)" }
  }
  [void]$cob.Add([pscustomobject][ordered]@{ data = $ds; secao = $t.s; situacao = $st; fonte = 'INLABS'; atos_ambientais = $n })
  Progresso $i $tarefas.Count $ini ("{0} {1,-4} {2,-26} atos ambientais: {3}" -f $ds, $t.s, $st, $n)
}

# ---------- B) base mensal (reserva) para os dias sem DO3 ----------
$DO3ok = @($cob | Where-Object { $_.secao -eq 'DO3' -and $_.situacao -in 'OK', 'CACHE', 'RESERVA (copia local)', 'SEM EDICAO' } | ForEach-Object data)
$faltam = @($datas | Where-Object { $DO3ok -notcontains $_.ToString('yyyy-MM-dd') })
if ($faltam) {
  Write-Host "`n$($faltam.Count) dia(s) sem a Secao 3 pelo INLABS. Tentando a base mensal (Dados Abertos)..." -ForegroundColor Yellow
  $meses = $faltam | Group-Object { $_.ToString('MMyyyy') }
  $pagina = $null
  foreach ($g in $meses) {
    $mmaaaa = $g.Name; $soDatas = New-Object 'System.Collections.Generic.HashSet[string]'; foreach ($d in $g.Group) { [void]$soDatas.Add($d.ToString('dd/MM/yyyy')) }
    $local = @(Get-ChildItem $MENSAL -Filter '*.zip' -ErrorAction SilentlyContinue | Where-Object { $_.Name -match "(?i)S0?3\w*$mmaaaa" })
    if (-not $local) {
      if (-not $pagina) { try { $pagina = (Invoke-WebRequest $DADOS_ABERTOS -UserAgent $UA -UseBasicParsing -TimeoutSec 60).Content } catch { $pagina = ''; Add-Content $LOG "pagina dados abertos: $(Erro-Texto $_)" } }
      $links = @([regex]::Matches($pagina, "href=""([^""]*?S0?3\w*?$mmaaaa[^""]*?\.zip[^""]*)""", 'IgnoreCase') | ForEach-Object { $u = $_.Groups[1].Value -replace '&amp;', '&'; if ($u -notmatch '^http') { $u = 'https://www.in.gov.br' + $u }; $u } | Select-Object -Unique)
      if (-not $links) { Write-Host "  $mmaaaa : base mensal ainda nao publicada ou link nao encontrado. Se tiver o zip, ponha em $MENSAL" -ForegroundColor Yellow; Add-Content $LOG "mensal $mmaaaa sem link"; continue }
      foreach ($u in $links) {
        $tam = ''; try { $h = Invoke-WebRequest $u -Method Head -UserAgent $UA -UseBasicParsing -TimeoutSec 60; $tam = '{0:N0} MB' -f ([double]$h.Headers['Content-Length'] / 1MB) } catch {}
        if ($NA_FILA) { Write-Host "  $mmaaaa : achei $u ($tam). Na fila nao baixo arquivo grande sem perguntar; rode a opcao 5 sozinha." -ForegroundColor Yellow; continue }
        $ok = Read-Host "  Baixar base mensal $mmaaaa ($tam)? $u  [S/N]"
        if ($ok -notmatch '^[sS]') { continue }
        $dest = Join-Path $MENSAL ("S03_${mmaaaa}_" + [IO.Path]::GetFileName(($u -split '\?')[0]))
        $r = Baixar-Arquivo $u $dest
        if ($r -and (Eh-Zip $dest)) { $local += Get-Item $dest } elseif (Test-Path $dest) { Write-Host '  O arquivo baixado nao e zip. Ignorado.' -ForegroundColor Yellow; Remove-Item $dest }
      }
    }
    foreach ($f in $local) {
      Write-Host "  Lendo $($f.Name) (so os dias que faltaram)..."
      $n = 0; try { $n = Ler-Zip $f.FullName "DOU Secao 3 - base mensal Dados Abertos (Imprensa Nacional)" $soDatas -mostrar } catch { Add-Content $LOG "$($f.Name): $($_.Exception.Message)" }
      foreach ($d in $g.Group) { if ($datasLidas.Contains($d.ToString('dd/MM/yyyy'))) { [void]$cob.Add([pscustomobject][ordered]@{ data = $d.ToString('yyyy-MM-dd'); secao = 'DO3'; situacao = 'BASE MENSAL'; fonte = $f.Name; atos_ambientais = '' }) } }
      Write-Host "  $($f.Name): $n atos ambientais nos dias que faltavam." -ForegroundColor Green
    }
  }
}

# ---------- saida ----------
$fA = Join-Path $ACH "dou_editais_ambientais_$STAMP.csv"; $atos | Export-Csv $fA -Delimiter ';' -NoTypeInformation -Encoding UTF8
$fC = Join-Path $ACH "dou_editais_CNPJ_$STAMP.csv"; $cnpjs | Export-Csv $fC -Delimiter ';' -NoTypeInformation -Encoding UTF8
$fB = Join-Path $BASE "cobertura_$STAMP.csv"; $cob | Export-Csv $fB -Delimiter ';' -NoTypeInformation -Encoding UTF8
$vaz = 0; if (Test-Path $fA) { foreach ($m in [regex]::Matches((Get-Content $fA -Raw -Encoding UTF8) + '', '(?<![\d/])\d{3}\.?\d{3}\.?\d{3}-?\d{2}(?![\d/])')) { if (Cpf-Ok $m.Value) { $vaz++ } } }
Write-Host "`n================ RESUMO ================"
Write-Host "INLABS: $sitInlabs"
Write-Host "Atos ambientais: $($atos.Count) | mencionam RJ: $(@($atos | Where-Object menciona_RJ -eq 'SIM').Count) | CNPJs (DV ok): $(@($cnpjs | ForEach-Object cnpj | Sort-Object -Unique).Count)"
$semDado = @($datas | Where-Object { $dd = $_.ToString('yyyy-MM-dd'); -not ($cob | Where-Object { $_.data -eq $dd -and $_.secao -eq 'DO3' -and $_.situacao -in 'OK', 'CACHE', 'RESERVA (copia local)', 'SEM EDICAO', 'BASE MENSAL' }) })
if ($semDado) { Write-Host "ATENCAO: $($semDado.Count) dia(s) SEM COBERTURA da Secao 3: $(($semDado | ForEach-Object { $_.ToString('dd/MM') }) -join ', '). Rode de novo mais tarde. Ver $LOG" -ForegroundColor Yellow }
else { Write-Host 'Cobertura: todos os dias uteis pedidos foram lidos.' -ForegroundColor Green }
if ($vaz) { Write-Host "ATENCAO: $vaz possiveis CPFs no arquivo publico. NAO publicar antes de conferir." -ForegroundColor Red } else { Write-Host 'Conferencia de CPF: OK (zero).' -ForegroundColor Green }
Write-Host "Arquivos:`n $fA`n $fC`n $fB`nTempo: $(Fmt ((Get-Date) - $ini).TotalSeconds)"
Write-Host 'Cada linha e um ato publicado (INDICIO para prospeccao). Ler o ato no link antes de afirmar qualquer coisa.'
Som
