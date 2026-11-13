# [15] SITES DAS EMPRESAS: acha o site de cada CNPJ e traz os contatos publicados la  -  v5.2 (07/11/2026)
# Para cada CNPJ do cadastro (c7), sem repetir quem ja foi conferido nos ultimos $REVER_DIAS dias:
#  1. Candidatos a site: dominio do e-mail da Receita (se nao for gmail/hotmail etc.) e enderecos provaveis
#     montados com o nome fantasia e a razao social (.com.br).
#  2. Confirmacao: para dominio .br, consulta o RDAP do Registro.br (fonte oficial do titular do dominio).
#     So vale se o titular tiver a MESMA raiz de CNPJ (8 digitos). Titular diferente = dominio de terceiro
#     (ex.: contador): o site NAO e usado. Para dominio fora do .br, so vale se a pagina mostrar o CNPJ.
#  3. Le a pagina inicial e ate 4 paginas de contato/sobre (respeita o robots.txt; 1 s entre paginas do mesmo site)
#     e extrai: e-mails, telefones, WhatsApp, Instagram, Facebook, LinkedIn, YouTube e TikTok.
# Regras alinhadas com o coletor online (coletar.py, buscar_sites) em 07/11/2026; mesmos nomes de campo do Supabase.
# Nao contorna captcha, login nem bloqueio. Nao usa buscador (Google/Bing). CPF mascarado em todo texto.
# Cada contato sai com o endereco da pagina (fonte) e a data. Cache em 05-Interno\cache_sites.json.
# ATENCAO (PowerShell nao diferencia maiusculas): nomes de variavel unicos; nada de $c/$C, $s/$S misturados.
. "$PSScriptRoot\comum.ps1"
$ACH = Join-Path $RAIZ '04-Achados'; $INT = Join-Path $RAIZ '05-Interno'
New-Item -ItemType Directory -Force $ACH, $INT, (Join-Path $RAIZ 'logs') | Out-Null
$STAMP = (Get-Date).ToString('yyyy-MM-dd_HHmm'); $HOJE = (Get-Date).ToString('yyyy-MM-dd')
$LOG = Join-Path $RAIZ "logs\c13_sites_$STAMP.log"
$ARQ_SITES = Join-Path $INT 'cache_sites.json'; $ARQ_RECEITA = Join-Path $INT 'cache_receita_cnpj.json'
$REVER_DIAS = 180; $ESPERA_RDAP = 3; $ESPERA_PAG = 1; $MAX_PAG = 5
$RDAP = if ($env:RADAR_RDAP_URL) { $env:RADAR_RDAP_URL } else { 'https://rdap.registro.br/domain/{0}' }
$PROTO = if ($env:RADAR_SITE_PROTO) { $env:RADAR_SITE_PROTO } else { 'https' }
$SITEBASE = $env:RADAR_SITE_BASE   # so para teste local (mock); vazio no uso normal
$GENERICOS = '^(gmail|googlemail|hotmail|outlook|live|msn|yahoo|ymail|bol|uol|terra|ig|globo|globomail|oi|r7|icloud|me|mac|aol|zipmail|superig|protonmail|proton|gmx|yandex|mail|email|veloxmail|click21|pop|ibest|itelefonica|brturbo|contab\w*|contad\w*|escritorio\w*|assessoria\w*)\.'
$ini0 = Get-Date; $TOTET = 4
Write-Host "== SITES DAS EMPRESAS: contatos publicados ==`n"

function Txt($v) { if ($null -eq $v) { '' } else { ([string]$v).Trim() } }
function Raiz($doc) { $dd = ($doc -replace '\D', ''); if ($dd.Length -ge 8) { $dd.Substring(0, 8) } else { '' } }
function Ler-Json($arq) { $h = @{}; if (Test-Path $arq) { try { $jj = Get-Content $arq -Raw -Encoding UTF8 | ConvertFrom-Json; foreach ($pp in $jj.PSObject.Properties) { $h[$pp.Name] = $pp.Value } } catch { Add-Content $LOG "cache ilegivel: $arq" } }; return $h }
function Salvar-Cache { $SITES | ConvertTo-Json -Depth 5 | Set-Content $ARQ_SITES -Encoding UTF8 }

# ---------- 1. quem consultar ----------
Cabecalho-Etapa 1 $TOTET 'Lendo cadastro da Receita e cache de sites' $ini0
$REC = Ler-Json $ARQ_RECEITA; $SITES = Ler-Json $ARQ_SITES
if (-not $REC.Count) { Write-Host 'Sem cadastro da Receita. Rode antes a [9].' -ForegroundColor Red; Som; return }
$excl = @(); $ax = Join-Path $INT 'excluir_cnpj.txt'
if (Test-Path $ax) { $excl = @(Get-Content $ax -Encoding UTF8 | ForEach-Object { ($_ -replace '#.*$', '') -replace '\D', '' } | Where-Object { $_.Length -ge 8 }) }
function Excluido($cn) { foreach ($ex in $excl) { if ($cn.StartsWith($ex)) { return $true } }; return $false }
$fila = @($REC.Keys | Sort-Object | Where-Object {
  $kr = $REC[$_]; $ks = $SITES[$_]
  (Cnpj-Ok $_) -and -not (Excluido $_) -and $kr.razao_social -and $kr.razao_social -ne 'NAO ENCONTRADO NA RECEITA' -and
  ((Txt $kr.situacao_receita) -match '(?i)^ativa') -and
  (-not $ks -or -not (Ler-Data (Txt $ks.data_busca)) -or (((Get-Date) - (Ler-Data (Txt $ks.data_busca))).TotalDays -gt $REVER_DIAS))
})
Write-Host "  CNPJs ativos no cadastro: $(@($REC.Keys | Where-Object { (Txt $REC[$_].situacao_receita) -match '(?i)^ativa' }).Count) | ja conferidos (ultimos $REVER_DIAS dias): $(@($SITES.Keys).Count) | a conferir agora: $($fila.Count)"

# ---------- funcoes de rede ----------
$script:ultRdap = [datetime]::MinValue
function Get-Rdap($dom) {
  # devolve: @{ existe=$bool; raizes=@(...) } ; nunca grava o JSON (pode ter dado pessoal do titular)
  $w = $ESPERA_RDAP - ((Get-Date) - $script:ultRdap).TotalSeconds; if ($w -gt 0) { Start-Sleep -Milliseconds ([int]($w * 1000)) }
  for ($t = 1; $t -le 3; $t++) {
    try {
      $rr = Invoke-WebRequest -UseBasicParsing -Uri ($RDAP -f $dom) -UserAgent $UA -TimeoutSec 30 -Headers @{ Accept = 'application/rdap+json' }
      $script:ultRdap = Get-Date
      $txt = if ($rr.Content -is [byte[]]) { [Text.Encoding]::UTF8.GetString($rr.Content) } else { [string]$rr.Content }
      $raizes = @([regex]::Matches($txt, '\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}') | ForEach-Object { $_.Value -replace '\D', '' } | Where-Object { $_.Length -eq 14 -and (Cnpj-Ok $_) } | ForEach-Object { $_.Substring(0, 8) } | Sort-Object -Unique)
      return @{ existe = $true; raizes = $raizes }
    } catch {
      $script:ultRdap = Get-Date; $cod = Cod-Erro $_
      if ($cod -eq 404) { return @{ existe = $false; raizes = @() } }
      if ($cod -eq 429) { Add-Content $LOG "RDAP 429 em $dom; esperando 60 s"; Start-Sleep -Seconds 60; continue }
      Add-Content $LOG "RDAP $dom : $(Erro-Texto $_)"; Start-Sleep -Seconds (3 * $t)
    }
  }
  return $null
}
function Get-Pagina($url) {
  try {
    $rr = Invoke-WebRequest -UseBasicParsing -Uri $url -UserAgent $UA -TimeoutSec 20 -MaximumRedirection 5
    $ct = [string]$rr.Headers['Content-Type']; if ($ct -and $ct -notmatch 'html|text') { return $null }
    $html = if ($rr.Content -is [byte[]]) { [Text.Encoding]::UTF8.GetString($rr.Content) } else { [string]$rr.Content }; if ($html.Length -gt 1500000) { $html = $html.Substring(0, 1500000) }
    $final = $url; try { $final = [string]$rr.BaseResponse.ResponseUri.AbsoluteUri } catch {}; if (-not $final) { try { $final = [string]$rr.BaseResponse.RequestMessage.RequestUri.AbsoluteUri } catch {} }; if (-not $final) { $final = $url }
    return @{ html = $html; url = $final }
  } catch { Add-Content $LOG "pagina $url : $(Erro-Texto $_)"; return $null }
}
function Robots-Bloqueia($base) {
  # Regras de "User-agent: *" do robots.txt. Devolve a lista de prefixos proibidos ('/' = site inteiro).
  $proib = @()
  try {
    $rr = Invoke-WebRequest -UseBasicParsing -Uri "$base/robots.txt" -UserAgent $UA -TimeoutSec 15
    $grupo = $false; $rt = if ($rr.Content -is [byte[]]) { [Text.Encoding]::UTF8.GetString($rr.Content) } else { [string]$rr.Content }
    foreach ($ln in ($rt -split "`n")) {
      $l2 = ($ln -replace '#.*$', '').Trim(); if (-not $l2) { continue }
      if ($l2 -match '^(?i)user-agent:\s*(.+)$') { $grupo = ($Matches[1].Trim() -eq '*'); continue }
      if ($grupo -and $l2 -match '^(?i)disallow:\s*(\S+)') { $proib += $Matches[1] }
    }
  } catch {}
  return $proib
}
function Permitido($caminho, $proib) { foreach ($pp in $proib) { if ($caminho.StartsWith($pp)) { return $false } }; return $true }

# ---------- extracao ----------
$RX_MAIL = '(?i)(?<![\w.+-])[a-z0-9][a-z0-9._%+-]{0,63}@[a-z0-9-]+(\.[a-z0-9-]+)*\.[a-z]{2,}(?![\w-])'
$RX_FONE = '(?<!\d)(?:\+?55[\s.-]?)?\(?([1-9][1-9])\)?[\s.-]?(9?\s?\d{4})[\s.-](\d{4})(?!\d)'
function Extrair($html, $dominio) {
  $dec = [Net.WebUtility]::HtmlDecode($html)
  $dec = $dec -replace '(?i)\[\s*(at|arroba)\s*\]', '@' -replace '(?i)\s\(\s*(at|arroba)\s*\)\s', '@'
  $semTag = ($dec -replace '(?is)<script.*?</script>|<style.*?</style>', ' ') -replace '<[^>]+>', ' '
  $mails = @([regex]::Matches($dec, $RX_MAIL) | ForEach-Object { $_.Value.ToLower().TrimEnd('.') } | Where-Object {
      $_ -notmatch '\.(png|jpe?g|gif|svg|webp|css|js)$' -and $_ -notmatch '(sentry|wixpress|example\.|exemplo\.|seuemail|seu-email|email@|nome@|usuario@|domain\.|dominio\.|@2x|@3x|godaddy|cloudflare)' } | Sort-Object -Unique | Select-Object -First 15)
  $tels = New-Object System.Collections.ArrayList
  foreach ($m in [regex]::Matches($dec, '(?i)href=["'']tel:([+\d\s().-]{8,})')) { [void]$tels.Add((($m.Groups[1].Value -replace '\D', '') -replace '^55(?=\d{10,11}$)', '')) }
  foreach ($m in [regex]::Matches($semTag, $RX_FONE)) {
    $ctx = $semTag.Substring([math]::Max(0, $m.Index - 25), [math]::Min(25, $m.Index))
    if ($ctx -match '(?i)cnpj|cpf|cep|inscri') { continue }
    [void]$tels.Add((($m.Groups[1].Value + $m.Groups[2].Value + $m.Groups[3].Value) -replace '\D', ''))
  }
  $tels = @($tels | Where-Object { ($_.Length -eq 10 -or $_.Length -eq 11) -and ($_ -replace '0', '') -and -not (Cpf-Ok $_) } | Sort-Object -Unique | Select-Object -First 15)
  $was = @([regex]::Matches($dec, '(?i)(?:wa\.me/|api\.whatsapp\.com/send\?phone=|web\.whatsapp\.com/send\?phone=|whatsapp://send\?phone=)\+?(\d{10,13})') | ForEach-Object { ($_.Groups[1].Value -replace '^55(?=\d{10,11}$)', '') } | Where-Object { $_.Length -in 10, 11 } | Sort-Object -Unique | Select-Object -First 15)
  $redes = @([regex]::Matches($dec, '(?i)https?://(?:www\.|m\.|br\.)?(instagram\.com|facebook\.com|fb\.com|linkedin\.com/company|linkedin\.com/in|tiktok\.com/@|youtube\.com/(?:@|c/|channel/|user/))[^\s"''<>?#]*') | ForEach-Object { $_.Value.TrimEnd('/') } |
    Where-Object { $_ -notmatch '(?i)/(sharer|share|intent|plugins|dialog|tr|p/|reel/|watch|embed|hashtag|explore)\b' -and $_ -notmatch '(?i)(instagram\.com|facebook\.com|fb\.com|youtube\.com)/?$' } | Sort-Object -Unique | Select-Object -First 15)
  $cnpjs = @([regex]::Matches($semTag, '\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}') | ForEach-Object { $_.Value -replace '\D', '' } | Where-Object { Cnpj-Ok $_ } | Sort-Object -Unique)
  $links = @([regex]::Matches($dec, '(?is)<a\b[^>]*href=["'']([^"''#]+)["''][^>]*>(.*?)</a>') | Where-Object { ($_.Groups[1].Value + ' ' + ($_.Groups[2].Value -replace '<[^>]+>', '')) -match '(?i)contato|contact|fale|atendimento' } | ForEach-Object { $_.Groups[1].Value } | Select-Object -First 4)
  return @{ mails = $mails; tels = $tels; was = $was; redes = $redes; cnpjs = $cnpjs; links = $links; texto = $semTag }
}
function Nome-Base($t) {
  $n = (Norm-Txt (Txt $t)).ToLower()
  $n = $n -replace '\b(ltda|me|epp|eireli|s a|sa|cia|companhia|limitada|empresa|empresarial|mei|spe|holding|participacoes|comercio|servicos|industria|de|da|do|das|dos|e)\b', ' '
  @($n -split ' ' | Where-Object { $_.Length -ge 2 -and $_ -notmatch '^\d+$' })
}
function Candidatos($kr) {
  $cand = [ordered]@{}
  $em = (Txt $kr.email).ToLower()
  if ($em -match '@([a-z0-9.-]+\.[a-z]{2,})$') { $dm = $Matches[1] -replace '^www\.', ''; if ($dm -notmatch $GENERICOS) { $cand[$dm] = 'dominio do e-mail da Receita' } }
  foreach ($nm in @((Txt $kr.nome_fantasia), (Txt $kr.razao_social))) {
    if ($nm -match '\d{11}') { continue }   # MEI com CPF no nome: nao monta endereco com isso
    $tk = Nome-Base $nm; if (-not $tk.Count) { continue }
    $c1 = ($tk -join ''); $c2 = (@($tk | Select-Object -First 2) -join ''); $c3 = $tk[0]
    foreach ($x in @($c1, $c2, $c3)) { if ($x.Length -ge 4 -and $x.Length -le 40) { $d1 = "$x.com.br"; if (-not $cand.Contains($d1)) { $cand[$d1] = 'endereco provavel pelo nome (conferido no Registro.br)' } } }
  }
  $cand
}

# ---------- 2. procurar e confirmar sites ----------
Cabecalho-Etapa 2 $TOTET "Procurando e confirmando sites ($($fila.Count) CNPJs)" $ini0
$ini = Get-Date; $i = 0; $achados = 0; $terceiros = 0; $rdapFalha = 0
foreach ($cn in $fila) {
  $i++; $kr = $REC[$cn]; $raiz = Raiz $cn
  $reg = [ordered]@{ cnpj = (Cnpj-Fmt $cn); site = ''; confianca = ''; como_achou = ''; emails_site = ''; telefones_site = ''; whatsapp_site = ''; redes_sociais = ''; paginas_lidas = ''; observacao = ''; data_busca = $HOJE }
  $obs = @()
  foreach ($kv in (Candidatos $kr).GetEnumerator()) {
    $dom = $kv.Key; $como = $kv.Value; $conf = ''
    if ($dom -match '\.br$') {
      $rd = Get-Rdap $dom
      if ($null -eq $rd) { $rdapFalha++; $obs += "Registro.br sem resposta para $dom"; if ($rdapFalha -ge 10) { break }; continue }
      $rdapFalha = 0
      if (-not $rd.existe) { continue }
      if ($rd.raizes -contains $raiz) { $conf = 'CONFIRMADO (titular no Registro.br = mesmo CNPJ)' }
      elseif ($rd.raizes.Count) { if ($como -match 'e-mail') { $terceiros++; $obs += "$dom e de outro CNPJ no Registro.br (provavel contador ou terceiro): nao usado" }; continue }
      else { if ($como -notmatch 'e-mail') { continue }; $conf = 'A CONFIRMAR NA PAGINA' }   # titular pessoa fisica ou sem documento publico
    } else { if ($como -notmatch 'e-mail') { continue }; $conf = 'A CONFIRMAR NA PAGINA' }
    # ler o site
    $base = if ($SITEBASE) { "$SITEBASE/$dom" } else { "${PROTO}://$dom" }; $hostAlvo = (New-Object Uri($base)).Host -replace '^www\.', ''; $proib = Robots-Bloqueia $base
    if (-not (Permitido '/' $proib)) { $obs += "$dom bloqueia leitura automatica (robots.txt): nao lido"; if ($conf -like 'CONFIRMADO*') { $reg.site = $base; $reg.confianca = $conf; $reg.como_achou = $como }; break }
    $pg = Get-Pagina "$base/"; if (-not $pg -and -not $SITEBASE) { $pg = Get-Pagina "http://www.$dom/"; if ($pg) { $base = "http://www.$dom"; $hostAlvo = $dom } }
    if (-not $pg) { $obs += "$dom nao abriu"; if ($conf -like 'CONFIRMADO*') { $reg.site = $base; $reg.confianca = $conf; $reg.como_achou = $como; break }; continue }
    $ex = Extrair $pg.html $dom; $lidas = @($pg.url); $todos = @($ex)
    if ($conf -eq 'A CONFIRMAR NA PAGINA') {
      if (@($ex.cnpjs | Where-Object { $_.StartsWith($raiz) }).Count) { $conf = 'CONFIRMADO (CNPJ na pagina)' }
      else { $obs += "$dom nao mostra o CNPJ da empresa: nao usado"; continue }
    }
    $paths = @($ex.links | ForEach-Object { try { (New-Object Uri((New-Object Uri($pg.url)), $_)) } catch { $null } } | Where-Object { $_ -and ($_.Host -replace '^www\.', '') -eq $hostAlvo -and $_.AbsoluteUri.StartsWith($base) } | ForEach-Object { $_.AbsoluteUri } | Sort-Object -Unique | Select-Object -First ($MAX_PAG - 1))
    foreach ($fx in '/contato', '/fale-conosco', '/contatos', '/contact', '/sobre', '/quem-somos') { if ($paths.Count -ge ($MAX_PAG - 1)) { break }; $ux = "$base$fx"; if ($paths -notcontains $ux -and $lidas -notcontains $ux) { $paths += $ux } }
    foreach ($u in $paths) {
      $up = (New-Object Uri($u)).AbsolutePath; if (-not (Permitido $up $proib)) { continue }
      Start-Sleep -Seconds $ESPERA_PAG; $p2 = Get-Pagina $u; if ($p2) { $todos += (Extrair $p2.html $dom); $lidas += $p2.url }
    }
    $reg.site = $base; $reg.confianca = $conf; $reg.como_achou = $como; $reg.paginas_lidas = ($lidas -join ' | ')
    $reg.emails_site = ((@($todos | ForEach-Object { $_.mails }) | Sort-Object -Unique | Select-Object -First 15) -join " / ")
    $reg.telefones_site = ((@($todos | ForEach-Object { $_.tels }) | Sort-Object -Unique | Select-Object -First 15) -join " / ")
    $reg.whatsapp_site = ((@($todos | ForEach-Object { $_.was }) | Sort-Object -Unique | Select-Object -First 15) -join " / ")
    $reg.redes_sociais = ((@($todos | ForEach-Object { $_.redes }) | Sort-Object -Unique | Select-Object -First 15) -join ' | ')
    $achados++; break
  }
  if (-not $reg.site -and -not $obs.Count) { $obs += 'nenhum site encontrado pelos caminhos usados' }
  $reg.observacao = Mascara-Texto ($obs -join '; ')
  foreach ($cp in 'emails_site', 'redes_sociais', 'paginas_lidas') { $reg[$cp] = Mascara-Texto $reg[$cp] }
  if ($rdapFalha -lt 10) { $SITES[$cn] = [pscustomobject]$reg }   # com o Registro.br fora, nao marca como conferido
  Progresso $i $fila.Count $ini "$(Cnpj-Fmt $cn) | sites confirmados: $achados"
  if ($i % 10 -eq 0) { Salvar-Cache }
  if ($rdapFalha -ge 10) { Write-Host 'Registro.br sem resposta 10 vezes seguidas: parando agora; o resto fica para a proxima execucao.' -ForegroundColor Yellow; break }
}
Salvar-Cache

# ---------- 3. planilha ----------
Cabecalho-Etapa 3 $TOTET 'Gravando a planilha de contatos dos sites' $ini0
$saida = @($SITES.Keys | Sort-Object | ForEach-Object { $rg = $SITES[$_]; $kr = $REC[$_]
  [pscustomobject][ordered]@{ cnpj = $rg.cnpj; razao_social = (Mascara-Texto (Txt $kr.razao_social)) -replace '\d{11}', '[CPF omitido]'; site = $rg.site; site_confirmacao = $rg.confianca; como_achou = $rg.como_achou
    emails_site = $rg.emails_site; telefones_site = $rg.telefones_site; whatsapp_site = $rg.whatsapp_site; redes_sociais = $rg.redes_sociais
    fonte_paginas = $rg.paginas_lidas; site_busca_em = $rg.data_busca; observacao = $rg.observacao
    classificacao = 'FATO: contato publicado no site da propria empresa (fonte e data ao lado). Site confirmado pelo titular no Registro.br ou pelo CNPJ na pagina' } })
$fS = Join-Path $ACH "contatos_sites_RJ_$STAMP.csv"
$saida | Export-Csv $fS -Delimiter ';' -NoTypeInformation -Encoding UTF8
$vaz = 0; foreach ($m in [regex]::Matches((Get-Content $fS -Raw -Encoding UTF8) + '', '(?<![\d/])\d{3}\.?\d{3}\.?\d{3}-?\d{2}(?![\d/])')) { if (Cpf-Ok $m.Value) { $vaz++ } }

# ---------- 4. resumo ----------
Cabecalho-Etapa 4 $TOTET 'Resumo' $ini0
$comSite = @($saida | Where-Object site)
$res = @(
  "CNPJs conferidos agora: $i de $($fila.Count) | sites confirmados agora: $achados | dominios de terceiros descartados: $terceiros",
  "No total (cache): $($saida.Count) conferidos | com site: $($comSite.Count) | com e-mail do site: $(@($saida | Where-Object emails_site).Count) | com telefone do site: $(@($saida | Where-Object telefones_site).Count) | com WhatsApp do site: $(@($saida | Where-Object whatsapp_site).Count) | com rede social: $(@($saida | Where-Object redes_sociais).Count)",
  "Planilha: $fS"
)
Write-Host "`n================ RESUMO ================"
$res | ForEach-Object { Write-Host $_; Add-Content $LOG $_ }
if ($vaz) { Write-Host "ATENCAO: $vaz possiveis CPFs na planilha. NAO publicar antes de conferir." -ForegroundColor Red } else { Write-Host 'Conferencia de CPF: OK (zero).' -ForegroundColor Green }
Write-Host "Tempo total: $(Fmt ((Get-Date) - $ini0).TotalSeconds)`nProximo passo: [10] LEADS (junta estes contatos na fila)."
Som
