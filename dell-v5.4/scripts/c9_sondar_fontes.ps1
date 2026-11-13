# [11] SONDAR NOVAS FONTES (INEA, DOERJ, Diario Oficial do Rio, MPRJ, portais de dados abertos, Querido Diario)  -  v5
# So TESTA se cada fonte responde deste PC e procura conjuntos de dados nos portais CKAN. Nao baixa base grande,
# nao faz login, nao contorna captcha nem bloqueio (403/429 = registrado como BLOQUEADO e pronto).
# Resultado: 04-Achados\sondagem\ -> diz quais fontes podem virar coleta automatica na proxima versao.
. "$PSScriptRoot\comum.ps1"
$SAI = Join-Path $RAIZ '04-Achados\sondagem'; New-Item -ItemType Directory -Force $SAI | Out-Null
$STAMP = (Get-Date).ToString('yyyy-MM-dd_HHmm'); $HOJE = (Get-Date).ToString('yyyy-MM-dd')
$LISTA = @(
  @('IBAMA', 'Dados abertos IBAMA (CKAN) - lista de conjuntos', 'https://dadosabertos.ibama.gov.br/api/3/action/package_list', 'ckan_lista'),
  @('IBAMA', 'Arquivos do IBAMA (blob)', 'https://stibamadadosabertosprd.blob.core.windows.net/dados-abertos/dados/FISCALIZACAO_NOTIFICACAO/fiscalizacao_notificacao.csv', 'cabecalho'),
  @('ESTADO RJ', 'Portal de Dados Abertos RJ (CKAN) - busca "inea"', 'https://dadosabertos.rj.gov.br/api/3/action/package_search?q=inea&rows=100', 'ckan_busca'),
  @('ESTADO RJ', 'Portal de Dados Abertos RJ (CKAN) - busca "infracao"', 'https://dadosabertos.rj.gov.br/api/3/action/package_search?q=infracao&rows=100', 'ckan_busca'),
  @('ESTADO RJ', 'Portal de Dados Abertos RJ (CKAN) - busca "fiscalizacao"', 'https://dadosabertos.rj.gov.br/api/3/action/package_search?q=fiscalizacao&rows=100', 'ckan_busca'),
  @('ESTADO RJ', 'Portal de Dados Abertos RJ (CKAN) - busca "licenca"', 'https://dadosabertos.rj.gov.br/api/3/action/package_search?q=licenca&rows=100', 'ckan_busca'),
  @('ESTADO RJ', 'INEA - site', 'https://www.inea.rj.gov.br/', 'pagina'),
  @('ESTADO RJ', 'IOERJ - Diario Oficial do Estado (DOERJ)', 'https://www.ioerj.com.br/', 'pagina'),
  @('ESTADO RJ', 'MPRJ - site', 'https://www.mprj.mp.br/', 'pagina'),
  @('CAPITAL', 'Diario Oficial do Rio (DOWeb)', 'https://doweb.rio.rj.gov.br/', 'pagina'),
  @('CAPITAL', 'DATA.RIO (dados abertos da Prefeitura do Rio)', 'https://www.data.rio/', 'pagina'),
  @('MUNICIPIOS', 'Querido Diario - API (diarios das prefeituras)', 'https://api.queridodiario.ok.org.br/gazettes?territory_ids=3304557&querystring=%22auto%20de%20infra%C3%A7%C3%A3o%22&size=1', 'json'),
  @('MUNICIPIOS', 'Querido Diario - site', 'https://queridodiario.ok.org.br/', 'pagina'),
  @('CADASTRO', 'BrasilAPI CNPJ', 'https://brasilapi.com.br/api/cnpj/v1/33000167000101', 'json'),
  @('CADASTRO', 'Minha Receita', 'https://minhareceita.org/33000167000101', 'json'),
  @('CADASTRO', 'CNPJ.ws publica', 'https://publica.cnpj.ws/cnpj/33000167000101', 'json'),
  @('CADASTRO', 'ReceitaWS', 'https://receitaws.com.br/v1/cnpj/33000167000101', 'json'),
  @('APOIO', 'IBGE municipios RJ', 'https://servicodados.ibge.gov.br/api/v1/localidades/estados/33/municipios', 'json')
)
$PADRAO = '(?i)infra|autua|fiscaliz|embarg|notific|suspens|apreens|licen|multa|ambient|inea|tac|ajustamento|polui|residuo|res[ií]duo|outorga|agua|água'
function Testar($url, $tipo) {
  $t0 = Get-Date
  try {
    if ($tipo -eq 'cabecalho') { $r = Invoke-WebRequest $url -Method Head -UseBasicParsing -UserAgent $UA -TimeoutSec 30 }
    else { $r = Invoke-WebRequest $url -UseBasicParsing -UserAgent $UA -TimeoutSec 30 }
    $tam = ''; try { $tam = '{0:N1} MB' -f ([double]$r.Headers['Content-Length'] / 1MB) } catch {}
    return @{ ok = $true; http = [int]$r.StatusCode; ms = [int]((Get-Date) - $t0).TotalMilliseconds; corpo = $(if ($tipo -ne 'cabecalho') { if ($r.Content -is [byte[]]) { [Text.Encoding]::UTF8.GetString($r.Content) } else { [string]$r.Content } } else { '' }); tam = $tam; via = 'PowerShell' }
  } catch {
    $cod = Cod-Erro $_; $msg = Erro-Texto $_
    # segunda tentativa com curl.exe (outro cliente HTTPS: diferencia erro de TLS do Windows de site fora do ar)
    foreach ($c in (Curl-Candidatos)) {
      $tmp = [IO.Path]::GetTempFileName()
      $h = & $c -sS -L -A $UA --max-time 30 -o $tmp -w '%{http_code}' $url 2>$null; $rc = $LASTEXITCODE
      if ($rc -eq 0 -and "$h" -match '^2') { $b = [IO.File]::ReadAllText($tmp); Remove-Item $tmp -ErrorAction SilentlyContinue
        return @{ ok = $true; http = [int]$h; ms = [int]((Get-Date) - $t0).TotalMilliseconds; corpo = $b; tam = ''; via = 'curl (PowerShell falhou: ' + $msg.Substring(0, [math]::Min(80, $msg.Length)) + ')' } }
      Remove-Item $tmp -ErrorAction SilentlyContinue
    }
    return @{ ok = $false; http = $cod; ms = [int]((Get-Date) - $t0).TotalMilliseconds; corpo = ''; erro = $msg; via = '' }
  }
}
$ini = Get-Date; $i = 0; $res = @(); $acha = @()
Write-Host "== SONDAGEM DE FONTES ($($LISTA.Count) testes) ==`n"
foreach ($x in $LISTA) {
  $i++; $r = Testar $x[2] $x[3]
  $status = if ($r.ok) { 'OK' } elseif ($r.http -in 401, 403) { 'BLOQUEADO (nao contornado)' } elseif ($r.http -eq 429) { 'LIMITE DE ACESSO (tentar mais tarde)' } elseif ($r.erro -match '(?i)ssl|tls|cipher|seguro|secure') { 'ERRO TLS/SSL no servidor' } elseif ($r.http -ge 500) { 'FORA DO AR / MANUTENCAO' } elseif ($r.http -eq 404) { 'ENDERECO NAO EXISTE (404)' } else { 'SEM RESPOSTA' }
  $obs = ''
  if ($r.ok -and $x[3] -like 'ckan*') {
    try {
      $j = $r.corpo | ConvertFrom-Json
      if ($x[3] -eq 'ckan_lista') {
        $sel = @($j.result | Where-Object { $_ -match $PADRAO }); $obs = "$(@($j.result).Count) conjuntos; $($sel.Count) de interesse"
        foreach ($s in $sel) { $acha += [pscustomobject][ordered]@{ portal = $x[1]; conjunto = $s; titulo = ''; orgao = ''; recursos = ''; link = "https://dadosabertos.ibama.gov.br/dataset/$s"; data_sondagem = $HOJE } }
      } else {
        $obs = "$($j.result.count) resultados"
        foreach ($d in $j.result.results) {
          $acha += [pscustomobject][ordered]@{ portal = $x[1]; conjunto = $d.name; titulo = $d.title; orgao = $d.organization.title
            recursos = ((@($d.resources | ForEach-Object { "$($_.format) $($_.url)" }) | Select-Object -First 5) -join ' | ')
            link = "https://dadosabertos.rj.gov.br/dataset/$($d.name)"; data_sondagem = $HOJE }
        }
      }
    } catch { $obs = 'respondeu, mas nao e JSON do CKAN' }
  } elseif ($r.ok -and $x[3] -eq 'json') { try { $null = $r.corpo | ConvertFrom-Json; $obs = 'JSON valido' } catch { $obs = 'respondeu, mas nao e JSON (pode ser pagina de erro)' } }
  elseif ($r.ok -and $x[3] -eq 'cabecalho') { $obs = "arquivo disponivel $($r.tam)" }
  elseif (-not $r.ok) { $obs = $r.erro }
  $res += [pscustomobject][ordered]@{ esfera = $x[0]; fonte = $x[1]; status = $status; http = $r.http; tempo_ms = $r.ms; via = $r.via; observacao = $obs; url = $x[2]; data_sondagem = (Get-Date).ToString('s') }
  Progresso $i $LISTA.Count $ini ('{0,-55} {1}' -f $x[1], $status)
  Start-Sleep -Milliseconds 500
}
$fR = Join-Path $SAI "fontes_$STAMP.csv"; $res | Export-Csv $fR -Delimiter ';' -NoTypeInformation -Encoding UTF8
$fC = Join-Path $SAI "conjuntos_encontrados_$STAMP.csv"; $acha | Sort-Object portal, conjunto -Unique | Export-Csv $fC -Delimiter ';' -NoTypeInformation -Encoding UTF8
Write-Host "`n================ RESUMO ================"
$res | Group-Object status | ForEach-Object { Write-Host ("{0,-38} {1}" -f $_.Name, (($_.Group | ForEach-Object { $_.fonte -replace ' -.*$', '' } | Sort-Object -Unique) -join '; ')) }
Write-Host "Conjuntos de dados de interesse achados nos portais: $(@($acha).Count)"
Write-Host "`nArquivos:`n $fR`n $fC`nMande esses dois arquivos na conversa para eu transformar as fontes que responderam em coleta automatica."
Write-Host "Tempo total: $(Fmt ((Get-Date) - $ini).TotalSeconds)"
Som
