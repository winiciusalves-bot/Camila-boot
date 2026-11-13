# Funcoes comuns - Radar Ambiental (PowerShell, sem Python)
$ErrorActionPreference = 'Continue'
$RAIZ = Split-Path -Parent $PSScriptRoot
$UA = 'Mozilla/5.0 (Gabinete ALERJ - levantamento de transparencia publica)'
# --- Conexao: PowerShell (TLS 1.2 / 1.3) ou curl.exe; escolhida automaticamente pelo teste ---
$script:TRANSP = 'irm'
function Set-Tls($com13) {
  $p = [Net.SecurityProtocolType]::Tls12
  if ($com13) { try { $p = $p -bor [Net.SecurityProtocolType]'Tls13' } catch {} }
  [Net.ServicePointManager]::SecurityProtocol = $p
}
Set-Tls $false
function Curl-Candidatos {
  $l = @(); $sys = Get-Command curl.exe -ErrorAction SilentlyContinue; if ($sys) { $l += $sys.Source }
  foreach ($p in "$env:ProgramFiles\Git\mingw64\bin\curl.exe", "${env:ProgramFiles(x86)}\Git\mingw64\bin\curl.exe", "$env:LOCALAPPDATA\Programs\Git\mingw64\bin\curl.exe") { if (Test-Path $p) { $l += $p } }
  @($l | Select-Object -Unique)
}
function Get-Curl($exe, $url) {
  $tmp = [IO.Path]::GetTempFileName(); $errf = [IO.Path]::GetTempFileName()
  try {
    $cod = & $exe -sS -L -A $UA --max-time 60 -o $tmp -w '%{http_code}' $url 2>$errf
    $rc = $LASTEXITCODE
    $txt = [IO.File]::ReadAllText($tmp, [Text.Encoding]::UTF8); $err = (Get-Content $errf -Raw) -replace '\s+', ' '
  } finally { Remove-Item $tmp, $errf -ErrorAction SilentlyContinue }
  if ($rc -ne 0) { throw "HTTP 0 | curl erro $rc | $err" }
  if ("$cod" -ne '200') { $c = $txt -replace '\s+', ' '; throw ("HTTP $cod | curl | " + $c.Substring(0, [math]::Min(300, $c.Length))) }
  return ($txt | ConvertFrom-Json)
}
function Get-J1($url) {
  if ($script:TRANSP -eq 'irm') { return Invoke-RestMethod -Uri $url -UserAgent $UA -TimeoutSec 60 }
  return Get-Curl $script:TRANSP $url
}
function Cod-Erro($e) {
  $c = 0; try { $c = [int]$e.Exception.Response.StatusCode } catch {}
  if (-not $c) { $m = [regex]::Match([string]$e.Exception.Message, '^HTTP (\d+)'); if ($m.Success) { $c = [int]$m.Groups[1].Value } }
  $c
}
function Erro-Texto($e) {
  # Devolve o motivo real da falha: codigo HTTP, mensagem e inicio da resposta do servidor
  if ([string]$e.Exception.Message -match '^HTTP \d+ \|') { return [string]$e.Exception.Message }
  $cod = Cod-Erro $e; $corpo = ''
  if ($e.ErrorDetails -and $e.ErrorDetails.Message) { $corpo = $e.ErrorDetails.Message }
  else { try { $sr = New-Object IO.StreamReader($e.Exception.Response.GetResponseStream()); $corpo = $sr.ReadToEnd() } catch {} }
  $corpo = ($corpo -replace '\s+', ' '); if ($corpo.Length -gt 300) { $corpo = $corpo.Substring(0, 300) }
  $ex = $e.Exception; while ($ex.InnerException) { $ex = $ex.InnerException }
  "HTTP $cod | $($ex.Message) | $corpo"
}
function Get-J($url, $tent = 4) {
  for ($i = 1; $i -le $tent; $i++) {
    try { return Get-J1 $url }
    catch {
      $script:ultimoErro = $_; $cod = Cod-Erro $_; $script:ultimoCodigo = $cod
      # 4xx (exceto 408/429) nao adianta repetir: parametro errado, acesso negado ou endereco inexistente
      if ($cod -ge 400 -and $cod -lt 500 -and $cod -ne 408 -and $cod -ne 429) { throw }
      # 429 = limite de requisicoes: espera mais (respeita o limite, nao contorna)
      if ($cod -eq 429) { Start-Sleep -Seconds (30 * $i) } else { Start-Sleep -Seconds (3 * $i) }
    }
  }
  throw $script:ultimoErro
}
function Escolher-Transporte($url) {
  # Testa formas de conexao em ordem e fica com a primeira que funcionar. Nao contorna bloqueio: so muda o protocolo/cliente HTTPS.
  try { $so = (Get-CimInstance Win32_OperatingSystem); Write-Host "  Windows: $($so.Caption) ($($so.Version)) | PowerShell $($PSVersionTable.PSVersion)" } catch {}
  $tent = @(@{ n = 'PowerShell TLS 1.2'; t = 'irm'; t13 = $false }, @{ n = 'PowerShell TLS 1.2+1.3'; t = 'irm'; t13 = $true })
  foreach ($c in (Curl-Candidatos)) { $tent += @{ n = "curl ($c)"; t = $c; t13 = $false } }
  $erros = @()
  foreach ($x in $tent) {
    Set-Tls $x.t13; $script:TRANSP = $x.t
    try { $r = Get-J1 $url; Write-Host "  OK via $($x.n)" -ForegroundColor Green; $script:TRANSP_NOME = $x.n; return $r }
    catch { $m = Erro-Texto $_; $erros += "$($x.n): $m"; Write-Host "  falhou via $($x.n): $m" -ForegroundColor DarkYellow
      if ((Cod-Erro $_) -ge 400) { Set-Tls $false; $script:TRANSP = 'irm'; throw } }
  }
  Set-Tls $false; $script:TRANSP = 'irm'
  throw ("HTTP 0 | nenhuma forma de conexao funcionou || " + ($erros -join ' || '))
}
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
function Municipios-RJ { $lst = Get-J 'https://servicodados.ibge.gov.br/api/v1/localidades/estados/33/municipios'; @($lst) | ForEach-Object { $_ } | Sort-Object nome | ForEach-Object { [pscustomobject]@{ cod = [string]$_.id; nome = $_.nome } } }

# ---------- Utilitarios de arquivo (v3) ----------
function Baixar-Arquivo($url, $destino) {
  # Baixa para .tmp e so substitui a copia anterior se o download terminar. A copia anterior e a reserva.
  $tmp = "$destino.tmp"; Remove-Item $tmp -ErrorAction SilentlyContinue
  $ini = Get-Date
  try {
    $wc = New-Object Net.WebClient; $wc.Headers['User-Agent'] = $UA
    Write-Host "  baixando $url"
    $wc.DownloadFile($url, $tmp)
    if ((Get-Item $tmp).Length -lt 100) { throw 'arquivo vazio' }
    Move-Item $tmp $destino -Force
    Write-Host ('  OK: {0:N1} MB em {1}' -f ((Get-Item $destino).Length / 1MB), (Fmt ((Get-Date) - $ini).TotalSeconds)) -ForegroundColor Green
    return 'NOVO'
  } catch {
    Remove-Item $tmp -ErrorAction SilentlyContinue
    $m = $_.Exception; while ($m.InnerException) { $m = $m.InnerException }
    Write-Host "  FALHOU: $($m.Message)" -ForegroundColor Yellow
    if (Test-Path $destino) {
      Write-Host ('  Usando a copia local de {0:dd/MM/yyyy HH:mm} (RESERVA - dados podem estar desatualizados)' -f (Get-Item $destino).LastWriteTime) -ForegroundColor Yellow
      return 'RESERVA'
    }
    return $null
  }
}
function Codificacao($arq) {
  # UTF-8 se o inicio do arquivo for UTF-8 valido; senao Windows-1252
  $fs = [IO.File]::OpenRead($arq); $buf = New-Object byte[] 262144; $n = $fs.Read($buf, 0, $buf.Length); $fs.Close()
  try { (New-Object Text.UTF8Encoding($false, $true)).GetString($buf, 0, [math]::Max(0, $n - 4)) | Out-Null; return [Text.Encoding]::UTF8 }
  catch { return [Text.Encoding]::GetEncoding(1252) }
}
function Ler-Csv($arq, [scriptblock]$porLinha, $rotulo) {
  # Le CSV grande em fluxo (sem carregar tudo na memoria). Chama $porLinha com um hashtable coluna->valor.
  Add-Type -AssemblyName Microsoft.VisualBasic
  $enc = Codificacao $arq
  $prim = (Get-Content $arq -TotalCount 1 -Encoding UTF8)
  $sep = if (($prim.Split(';').Count) -ge ($prim.Split(',').Count)) { ';' } else { ',' }
  $sr = New-Object IO.StreamReader($arq, $enc); $tot = $sr.BaseStream.Length
  $p = New-Object Microsoft.VisualBasic.FileIO.TextFieldParser($sr)
  $p.SetDelimiters($sep); $p.HasFieldsEnclosedInQuotes = $true; $p.TrimWhiteSpace = $true
  $cab = $p.ReadFields() | ForEach-Object { ($_ -replace '^﻿', '').Trim().ToUpper() }
  $ini = Get-Date; $n = 0; $ult = Get-Date
  while (-not $p.EndOfData) {
    try { $f = $p.ReadFields() } catch { continue }
    $n++; $h = @{}; for ($k = 0; $k -lt $cab.Count -and $k -lt $f.Count; $k++) { $h[$cab[$k]] = $f[$k] }
    & $porLinha $h | Out-Null
    if (((Get-Date) - $ult).TotalSeconds -ge 5) { $ult = Get-Date
      $pos = [math]::Max(1, $sr.BaseStream.Position); $dec = ((Get-Date) - $ini).TotalSeconds; $eta = $dec / $pos * ($tot - $pos)
      Write-Host ('  [{0,5:N1}%] {1} | {2:N0} linhas | decorrido {3} | faltam ~{4}' -f ($pos / $tot * 100), $rotulo, $n, (Fmt $dec), (Fmt $eta)) }
  }
  $p.Close(); $sr.Close()
  Write-Host ('  [100,0%] {0} | {1:N0} linhas | {2}' -f $rotulo, $n, (Fmt ((Get-Date) - $ini).TotalSeconds))
  return ,$cab
}
function Cpf-Ok($c) {
  $d = ($c -replace '\D', ''); if ($d.Length -ne 11 -or $d -match '^(\d)\1{10}$') { return $false }
  foreach ($n in 9, 10) {
    $s = 0; for ($i = 0; $i -lt $n; $i++) { $s += [int][string]$d[$i] * ($n + 1 - $i) }
    if ((($s * 10) % 11) % 10 -ne [int][string]$d[$n]) { return $false }
  }
  return $true
}
function Mascara-Doc($doc) {
  # CNPJ fica aberto; CPF vira ***.xxx.xxx-**
  $d = ($doc -replace '\D', '')
  if ($d.Length -eq 14) { return (Cnpj-Fmt $d) }
  if ($d.Length -eq 11) { return ('***.{0}.{1}-**' -f $d.Substring(3, 3), $d.Substring(6, 3)) }
  if ($d) { return '[doc omitido]' } else { return '' }
}
function Mascara-Texto($t) {
  if ($null -eq $t) { return $t }
  $t = [string]$t
  $t = [regex]::Replace($t, '(?i)(CPF\s*[:nº°.]*\s*)\d{3}\.?\d{3}\.?\d{3}(-?\d{2})?', '$1[CPF omitido]')
  $t = [regex]::Replace($t, '(?<![\d/])\d{3}\.?\d{3}\.?\d{3}-?\d{2}(?![\d/])', { param($m) if (Cpf-Ok $m.Value) { '[CPF omitido]' } else { $m.Value } })
  return $t.Trim()
}
function Ler-Data($s) {
  if (-not $s) { return $null }
  $s = ([string]$s).Trim()
  $fmts = 'yyyy-MM-dd HH:mm:ss', 'yyyy-MM-dd HH:mm:ss.fff', 'yyyy-MM-ddTHH:mm:ss', 'yyyy-MM-dd', 'dd/MM/yyyy HH:mm:ss', 'dd/MM/yyyy HH:mm', 'dd/MM/yyyy', 'dd-MMM-yy', 'dd/MM/yy'
  $d = [datetime]::MinValue
  foreach ($f in $fmts) { if ([datetime]::TryParseExact($s, $f, [Globalization.CultureInfo]::InvariantCulture, 'None', [ref]$d)) { return $d } }
  if ([datetime]::TryParse($s, [Globalization.CultureInfo]'pt-BR', 'None', [ref]$d)) { return $d }
  return $null
}
function Col($cab, [string[]]$padroes) { foreach ($p in $padroes) { $c = $cab | Where-Object { $_ -match $p } | Select-Object -First 1; if ($c) { return $c } }; return $null }

# ---------- v5: normalizacao, municipios, valores, leitura de CSV pequeno ----------
function Sem-Acento($t) { if ($null -eq $t) { return '' }; ([string]$t).Normalize([Text.NormalizationForm]::FormD) -replace '\p{Mn}', '' }
function Norm-Txt($t) { ((Sem-Acento $t).ToUpper() -replace '[^A-Z0-9 ]', ' ' -replace '\s+', ' ').Trim() }
$script:MUNI = $null
function Carregar-Municipios {
  # Nome oficial (IBGE) por codigo e por nome normalizado. Reserva: cache local; se nada houver, usa o nome do arquivo normalizado.
  if ($script:MUNI) { return }
  $script:MUNI = @{ cod = @{}; nome = @{} }
  $cache = Join-Path $RAIZ '05-Interno\municipios_RJ_ibge.csv'
  $lst = $null
  try { $lst = @(Municipios-RJ); if ($lst.Count -gt 50) { $lst | Export-Csv $cache -Delimiter ';' -NoTypeInformation -Encoding UTF8 } } catch {}
  if ((-not $lst -or $lst.Count -lt 50) -and (Test-Path $cache)) { $lst = @(Import-Csv $cache -Delimiter ';') }
  foreach ($m in @($lst)) { if ($m.cod) { $script:MUNI.cod[[string]$m.cod] = $m.nome; $script:MUNI.nome[(Norm-Txt $m.nome)] = $m.nome } }
}
function Muni-Nome($cod, $nome) {
  # Uma grafia so por municipio: "RIO DE JANEIRO", "Rio de Janeiro" -> "Rio de Janeiro"
  Carregar-Municipios
  $c = ([string]$cod) -replace '\D', ''
  if ($c -and $script:MUNI.cod.ContainsKey($c)) { return $script:MUNI.cod[$c] }
  $n = Norm-Txt $nome
  if ($script:MUNI.nome.ContainsKey($n)) { return $script:MUNI.nome[$n] }
  return $n
}
function Num-Br($v) {
  # "1.234,56" / "1234,56" / "1234.56" -> double (0 se vazio)
  $s = ([string]$v).Trim(); if (-not $s) { return 0.0 }
  if ($s -match ',') { $s = ($s -replace '\.', '') -replace ',', '.' }
  $d = 0.0; if ([double]::TryParse($s, [Globalization.NumberStyles]::Any, [Globalization.CultureInfo]::InvariantCulture, [ref]$d)) { return $d }; return 0.0
}
function Ultimo-Arquivo($pasta, $filtro) { Get-ChildItem $pasta -Filter $filtro -ErrorAction SilentlyContinue | Sort-Object LastWriteTime | Select-Object -Last 1 }
function Cabecalho-Etapa($n, $tot, $txt, $ini) {
  $dec = ((Get-Date) - $ini).TotalSeconds
  Write-Host ('[{0}/{1}] {2,-55} | {3,5:N1}% | decorrido {4}' -f $n, $tot, $txt, (($n - 1) / $tot * 100), (Fmt $dec)) -ForegroundColor Cyan
}

# ---------- v5.1: leitor de XLSX sem Excel (o .xlsx e um zip de XML) ----------
function Ler-Xlsx($arq) {
  # Devolve uma lista de abas: @{ nome = 'Aba'; linhas = [lista de arrays de texto] }. Celulas vazias viram ''.
  Add-Type -AssemblyName System.IO.Compression.FileSystem
  $z = [IO.Compression.ZipFile]::OpenRead($arq)
  function LerXml($nome) { $e = $z.Entries | Where-Object { $_.FullName -eq $nome } | Select-Object -First 1; if (-not $e) { return $null }
    $sr = New-Object IO.StreamReader($e.Open()); $t = $sr.ReadToEnd(); $sr.Close(); [xml]$t }
  try {
    $ss = @(); $x = LerXml 'xl/sharedStrings.xml'
    if ($x) { foreach ($si in $x.sst.si) { if ($si.t) { $ss += [string]($(if ($si.t.'#text') { $si.t.'#text' } else { $si.t })) } else { $ss += (@($si.r | ForEach-Object { if ($_.t.'#text') { $_.t.'#text' } else { $_.t } }) -join '') } } }
    $wb = LerXml 'xl/workbook.xml'; $rel = LerXml 'xl/_rels/workbook.xml.rels'
    $abas = @()
    foreach ($sh in @($wb.workbook.sheets.sheet)) {
      $rid = $sh.GetAttribute('id', 'http://schemas.openxmlformats.org/officeDocument/2006/relationships')
      $alvo = ($rel.Relationships.Relationship | Where-Object { $_.Id -eq $rid }).Target
      $caminho = if ($alvo -like '/*') { $alvo.TrimStart('/') } else { 'xl/' + $alvo }
      $sx = LerXml $caminho; if (-not $sx) { continue }
      $linhas = New-Object System.Collections.ArrayList
      foreach ($row in @($sx.worksheet.sheetData.row)) {
        $cel = @{}; $max = -1
        foreach ($c in @($row.c)) {
          if (-not $c) { continue }
          $ref = [string]$c.r; $col = 0; foreach ($ch in ($ref -replace '\d', '').ToCharArray()) { $col = $col * 26 + ([int][char]$ch - 64) }; $col--
          $v = if ($c.t -eq 's') { $ss[[int]$c.v] } elseif ($c.t -eq 'inlineStr') { [string]$c.is.t } else { [string]$c.v }
          $cel[$col] = $v; if ($col -gt $max) { $max = $col }
        }
        $arr = @(); for ($k2 = 0; $k2 -le $max; $k2++) { $arr += $(if ($cel.ContainsKey($k2)) { ([string]$cel[$k2]).Trim() } else { '' }) }
        [void]$linhas.Add($arr)
      }
      $abas += @{ nome = $sh.name; linhas = $linhas }
    }
    return $abas
  } finally { $z.Dispose() }
}
function Data-Excel($v) {
  # numero de serie do Excel (ex.: 45231) ou texto de data -> datetime
  $d = 0.0; if ([double]::TryParse([string]$v, [Globalization.NumberStyles]::Float, [Globalization.CultureInfo]::InvariantCulture, [ref]$d) -and $d -gt 20000 -and $d -lt 80000) { return [datetime]::FromOADate($d) }
  return (Ler-Data $v)
}
