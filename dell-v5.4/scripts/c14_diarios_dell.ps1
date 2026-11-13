# [16] DIARIOS MUNICIPAIS QUE SO ABREM DESTE PC  -  v1 (12/11/2026)
# Para os municipios do RJ cujo diario oficial nao abre do GitHub (bloqueio por pais/rede ou site fora do ar de la).
# So LE paginas publicas: acha a pagina do Diario Oficial, conta os PDFs com data e guarda uma copia da pagina
# para a conversa escrever o robo de cada um. Sem login, sem captcha, sem contornar Cloudflare ou bloqueio:
# pagina de desafio/captcha = BLOQUEADO e pronto.
# Resultado: 04-Achados\sondagem\diarios_dell_<data>.csv  +  01-Coletas\diarios-dell\<data>\ (copias das paginas)
. "$PSScriptRoot\comum.ps1"
$STAMP = (Get-Date).ToString('yyyy-MM-dd_HHmm')
$SAI = Join-Path $RAIZ '04-Achados\sondagem'; New-Item -ItemType Directory -Force $SAI | Out-Null
$PAG = Join-Path $RAIZ "01-Coletas\diarios-dell\$STAMP"; New-Item -ItemType Directory -Force $PAG | Out-Null

# Municipios sem diario na base comum em 12/11/2026 (os demais ja sao lidos pelo GitHub)
$MUNIS = @('Angra dos Reis','Barra Mansa','Cachoeiras de Macacu','Cantagalo','Carapebus','Conceicao de Macabu','Itaocara','Mage',
  'Mangaratiba','Petropolis','Pinheiral','Pirai','Porciuncula','Porto Real','Resende','Rio das Flores','Santo Antonio de Padua',
  'Silva Jardim','Teresopolis','Tres Rios','Valenca','Volta Redonda','Macuco','Laje do Muriae','Sao Sebastiao do Alto',
  'Italva','Cardoso Moreira','Santa Maria Madalena','Nova Friburgo')
$CAMINHOS = @('/diario-oficial', '/diariooficial', '/diario_oficial', '/diario-oficial-eletronico', '/boletim-oficial',
  '/jornal-oficial', '/publicacoes/diario-oficial', '/site/diarios_oficiais', '/transparencia/diario-oficial', '/portal/diario-oficial')
$RXDIARIO = '(?i)di[aá]rio\s*oficial|boletim\s*(oficial|informativo|municipal)|jornal\s*oficial|imprensa\s*oficial|atos\s*oficiais|publica[cç][oõ]es\s*oficiais'
$RXHREF = '(?i)diario|boletim|jornal-?oficial|imprensa-?oficial|atos-?oficiais|\bdom\b|\bjom\b|doem|dioenet'
$RXBLOQ = '(?i)cf-chl|challenge-platform|just a moment|g-recaptcha|hcaptcha|turnstile|captcha'
$RXDATA = '\d{1,2}[/.\-_]\d{1,2}[/.\-_]\d{4}|\d{4}[/.\-_]\d{2}[/.\-_]\d{2}|\d{1,2}\s+de\s+[a-zç]+\s+de\s+\d{4}'
$RXLIXO = '(?i)facebook|instagram|youtube|twitter|whatsapp|linkedin|google|wa\.me|mailto:|javascript:|#$'
$PLATAF = @{ 'betha' = 'Betha'; 'dioenet' = 'Dioenet'; 'diariomunicipal' = 'Diario Municipal (AEMERJ/CNM)'; 'doem' = 'DOEM';
  'atende.net' = 'IPM Atende.net'; 'governa' = 'Governa'; 'siganet' = 'Siganet'; 'portalgov' = 'PortalGov'; 'geosiap' = 'GeoSiap';
  'docman' = 'Joomla DOCman'; 'wp-content' = 'WordPress'; 'egov' = 'eGov'; 'transparencia' = 'portal de transparencia' }

function Slug($t) { ((Sem-Acento $t).ToLower() -replace '[^a-z0-9]', '') }
function Ler-Pagina($endereco) {
  # PowerShell primeiro; se falhar (TLS/rede), curl.exe. Mesma identificacao do gabinete, sem disfarce.
  try {
    $r = Invoke-WebRequest $endereco -UseBasicParsing -UserAgent $UA -TimeoutSec 40 -MaximumRedirection 5
    $fim = $endereco; try { $fim = [string]$r.BaseResponse.ResponseUri.AbsoluteUri } catch {}
    if (-not $fim) { $fim = $endereco }
    $corpo = if ($r.Content -is [byte[]]) { [Text.Encoding]::UTF8.GetString($r.Content) } else { [string]$r.Content }
    return @{ ok = $true; http = [int]$r.StatusCode; final = $fim; html = $corpo; erro = '' }
  } catch {
    $cod = Cod-Erro $_; $msg = Erro-Texto $_
    if ($cod -ge 400) { return @{ ok = $false; http = $cod; final = $endereco; html = ''; erro = $msg } }
    foreach ($c in (Curl-Candidatos)) {
      $tmp = [IO.Path]::GetTempFileName()
      $h = & $c -sS -L -A $UA --max-time 40 -o $tmp -w '%{http_code}|%{url_effective}' $endereco 2>$null; $rc = $LASTEXITCODE
      $b = ''; try { $b = [IO.File]::ReadAllText($tmp, [Text.Encoding]::UTF8) } catch {}; Remove-Item $tmp -ErrorAction SilentlyContinue
      if ($rc -eq 0) { $p = "$h".Split('|'); return @{ ok = ($p[0] -match '^2'); http = [int]$p[0]; final = $p[1]; html = $b; erro = "via curl" } }
    }
    return @{ ok = $false; http = $cod; final = $endereco; html = ''; erro = $msg }
  }
}
function Links($html, $base) {
  $l = @()
  foreach ($m in [regex]::Matches($html, '(?is)<a\b[^>]*?href\s*=\s*["'']([^"''#][^"'']*)["''][^>]*>(.*?)</a>')) {
    $h = $m.Groups[1].Value.Trim(); $t = (($m.Groups[2].Value -replace '<[^>]+>', ' ') -replace '\s+', ' ').Trim()
    try { $abs = [string]([Uri]::new([Uri]$base, [Net.WebUtility]::HtmlDecode($h))).AbsoluteUri } catch { continue }
    $l += [pscustomobject]@{ texto = $(if ($t.Length -gt 80) { $t.Substring(0, 80) } else { $t }); href = $abs }
  }
  foreach ($m in [regex]::Matches($html, '(?is)<iframe\b[^>]*?src\s*=\s*["'']([^"'']+)["'']')) {
    try { $l += [pscustomobject]@{ texto = '[iframe]'; href = [string]([Uri]::new([Uri]$base, $m.Groups[1].Value)).AbsoluteUri } } catch {}
  }
  $l
}
function Guardar($slug, $nome, $html) {
  $d = Join-Path $PAG $slug; New-Item -ItemType Directory -Force $d | Out-Null
  [IO.File]::WriteAllText((Join-Path $d "$nome.html"), (Mascara-Cpf $html), [Text.Encoding]::UTF8)
}
function Plataformas($txt) { (@($PLATAF.Keys | Where-Object { $txt -match [regex]::Escape($_) } | ForEach-Object { $PLATAF[$_] }) | Sort-Object -Unique) -join ', ' }

$ini = Get-Date; $i = 0; $res = @()
Write-Host "== DIARIOS QUE SO ABREM DESTE PC ($($MUNIS.Count) municipios) ==`n"
foreach ($mu in $MUNIS) {
  $i++; $s = Slug $mu
  $cand = @("https://www.$s.rj.gov.br", "https://$s.rj.gov.br", "https://prefeiturade$s.rj.gov.br", "https://www.prefeiturade$s.rj.gov.br", "https://prefeitura$s.rj.gov.br", "https://pm$s.rj.gov.br")
  $site = $null; $p = $null; $tentativas = @()
  foreach ($u in $cand) { $p = Ler-Pagina $u; $tentativas += "$u=$($p.http)"; if ($p.ok -and $p.html.Length -gt 500) { $site = $p.final; break } }
  $r = [ordered]@{ municipio = $mu; site = $site; status = ''; pagina_diario = ''; http_diario = ''; pdfs = 0; pdfs_com_data = 0;
    plataforma = ''; exemplos = ''; links_diario = ''; externos = ''; tentativas = ($tentativas -join ' '); data_sondagem = (Get-Date).ToString('s') }
  if (-not $site) { $r.status = 'SITE NAO ABRIU'; $res += [pscustomobject]$r; Progresso $i $MUNIS.Count $ini ('{0,-26} {1}' -f $mu, $r.status); continue }
  Guardar $s '00-inicio' $p.html
  if ($p.html -match $RXBLOQ -and $p.html.Length -lt 20000) { $r.status = 'BLOQUEADO (desafio/captcha, nao contornado)'; $res += [pscustomobject]$r; Progresso $i $MUNIS.Count $ini ('{0,-26} {1}' -f $mu, $r.status); continue }
  $lk = @(Links $p.html $site)
  $dl = @($lk | Where-Object { ($_.texto -match $RXDIARIO -or $_.href -match $RXHREF) -and $_.href -notmatch $RXLIXO } | Sort-Object href -Unique | Select-Object -First 6)
  $r.links_diario = (($dl | ForEach-Object { "$($_.texto) => $($_.href)" }) -join ' || ')
  # caminhos comuns de diario no proprio site
  $raiz = ([Uri]$site).GetLeftPart([UriPartial]::Authority)
  $visitar = @($dl | ForEach-Object { $_.href }) + @($CAMINHOS | ForEach-Object { $raiz + $_ })
  $melhor = $null; $n = 0
  foreach ($v in ($visitar | Select-Object -Unique)) {
    $n++; $q = Ler-Pagina $v
    if (-not $q.ok -or $q.html.Length -lt 500) { continue }
    $ql = @(Links $q.html $q.final)
    $pdf = @($ql | Where-Object { $_.href -match '(?i)\.pdf|download|arquivo|visualiz|baixar|/file' })
    $pdfData = @($pdf | Where-Object { ($_.texto + ' ' + $_.href) -match $RXDATA })
    Guardar $s ('{0:00}-{1}' -f $n, (($q.final -replace '^https?://', '' -replace '[^A-Za-z0-9]+', '_'))) $q.html
    $ext = @($ql | ForEach-Object { try { ([Uri]$_.href).Host } catch {} } | Where-Object { $_ -and $_ -notmatch [regex]::Escape(([Uri]$site).Host) -and $_ -notmatch $RXLIXO } | Sort-Object -Unique)
    $nota = [pscustomobject]@{ url = $q.final; http = $q.http; pdf = $pdf.Count; pdfData = $pdfData.Count; ex = (($pdfData | Select-Object -First 3 | ForEach-Object { "$($_.texto) => $($_.href)" }) -join ' || ');
      plat = (Plataformas ($q.final + ' ' + $q.html)); ext = (($ext | Select-Object -First 8) -join ', '); bloq = ($q.html -match $RXBLOQ -and $q.html.Length -lt 20000) }
    if (-not $melhor -or $nota.pdfData -gt $melhor.pdfData -or ($nota.pdfData -eq $melhor.pdfData -and $nota.pdf -gt $melhor.pdf)) { $melhor = $nota }
    Start-Sleep -Milliseconds 400
  }
  if ($melhor) {
    $r.pagina_diario = $melhor.url; $r.http_diario = $melhor.http; $r.pdfs = $melhor.pdf; $r.pdfs_com_data = $melhor.pdfData
    $r.plataforma = $melhor.plat; $r.exemplos = $melhor.ex; $r.externos = $melhor.ext
    $r.status = if ($melhor.bloq) { 'BLOQUEADO NA PAGINA DO DIARIO (nao contornado)' } elseif ($melhor.pdfData -gt 0) { 'ACHOU PDFs COM DATA' } elseif ($melhor.pdf -gt 0) { 'ACHOU PDFs SEM DATA NO LINK' } else { 'PAGINA SEM PDF (pode carregar por script)' }
  } else { $r.status = 'SEM PAGINA DE DIARIO' }
  $res += [pscustomobject]$r
  Progresso $i $MUNIS.Count $ini ('{0,-26} {1}' -f $mu, $r.status)
}
$fR = Join-Path $SAI "diarios_dell_$STAMP.csv"; $res | Export-Csv $fR -Delimiter ';' -NoTypeInformation -Encoding UTF8
Write-Host "`n================ RESUMO ================"
$res | Group-Object status | ForEach-Object { Write-Host ("{0,-46} {1}" -f $_.Name, (($_.Group | ForEach-Object { $_.municipio }) -join '; ')) }
Write-Host "`nArquivo: $fR`nCopias das paginas: $PAG`nAvise na conversa: eu leio esses arquivos e escrevo o robo de cada municipio."
Write-Host "Tempo total: $(Fmt ((Get-Date) - $ini).TotalSeconds)"
Som
