# [14] ENVIAR BASE AO SITE (Supabase)  -  v5.1 (06/11/2026)
# Le 02-Base\supabase\ocorrencias_pj.csv e empresas.csv (gerados pelo c10) e envia ao banco do site.
#  - ocorrencias: upsert por "chave". As chaves IBAMA-AUTO, IBAMA-EMB, IBAMA-NOT e IBAMA-SUS sao puladas,
#    porque o coletor online do GitHub ja grava essas todo dia. O resto vai com origem = 'radar-pc'.
#  - empresas: so os CNPJs que ainda NAO estao no banco (nao sobrescreve o que o coletor online atualizou).
# So pessoa juridica com DV do CNPJ conferido. CPF sempre mascarado em qualquer texto.
# A chave secreta fica num arquivo que VOCE cria: 05-Interno\supabase_secret.txt (uma linha, so a chave).
# O script le esse arquivo e nunca mostra o conteudo, nem grava no log.
. "$PSScriptRoot\comum.ps1"
$BAS = Join-Path $RAIZ '02-Base'; $SUP = Join-Path $BAS 'supabase'; $INT = Join-Path $RAIZ '05-Interno'
New-Item -ItemType Directory -Force (Join-Path $RAIZ 'logs') | Out-Null
$STAMP = (Get-Date).ToString('yyyy-MM-dd_HHmm'); $LOG = Join-Path $RAIZ "logs\c12_envio_site_$STAMP.log"
$URL = if ($env:RADAR_SUPA_URL) { $env:RADAR_SUPA_URL } else { 'https://mxfgezgmyowqjmaibdkl.supabase.co' }
$ARQ_CHAVE = Join-Path $INT 'supabase_secret.txt'
$LOTE = 500
$PULAR = '^IBAMA-(AUTO|EMB|NOT|SUS)\|'
$COLS_OC = 'chave','fonte','orgao','tipo_documento','numero','processo','data_documento','data_documento_status','data_ciencia',
  'prazo_defesa_fim_estimado','prazo_defesa_status','situacao','cnpj','nome','municipio','cod_ibge','valor_indicado_rs_nao_e_dano',
  'assunto','descricao','nivel','link_fonte','primeira_coleta','ultima_coleta'
$DATAS_OC = 'data_documento','data_ciencia','prazo_defesa_fim_estimado','primeira_coleta','ultima_coleta'
$ini0 = Get-Date; $TOTET = 4
Write-Host "== ENVIAR BASE AO SITE (Supabase) ==`n"

function Fim($txt, $cor) { Write-Host "`n$txt" -ForegroundColor $cor; Add-Content $LOG $txt; Som; exit }
function Txt($v) { if ($null -eq $v) { '' } else { ([string]$v).Trim() } }
function Data-Iso($v) { $d = Ler-Data (Txt $v); if ($d) { $d.ToString('yyyy-MM-dd') } else { $null } }
function Ler-Ponto($arq) {
  # CSV do c10: separador ';', UTF-8 com BOM. Le tudo (arquivos pequenos, so PJ).
  if (-not (Test-Path $arq)) { return @() }
  @(Import-Csv -Path $arq -Delimiter ';' -Encoding UTF8)
}
function Post-Lote($tabela, $conflito, $linhas) {
  $json = ConvertTo-Json -InputObject @($linhas) -Depth 3 -Compress
  $bytes = [Text.Encoding]::UTF8.GetBytes($json)
  $h = @{ apikey = $script:CHAVE; Prefer = 'resolution=merge-duplicates,return=minimal' }
  $u = "$URL/rest/v1/$tabela" + "?on_conflict=$conflito"
  for ($t = 1; $t -le 3; $t++) {
    try { Invoke-WebRequest -UseBasicParsing -Method Post -Uri $u -Headers $h -ContentType 'application/json; charset=utf-8' -Body $bytes -TimeoutSec 120 | Out-Null; return $true }
    catch { $cod = Cod-Erro $_; $msg = Erro-Texto $_; Add-Content $LOG "$tabela lote (tentativa $t): $msg"
      if ($cod -ge 400 -and $cod -lt 500 -and $cod -ne 408 -and $cod -ne 429) { Write-Host "   recusado pelo banco: $msg" -ForegroundColor Red; return $false }
      Start-Sleep -Seconds (5 * $t) }
  }
  Write-Host '   falhou 3 vezes (rede ou servidor). Veja o log.' -ForegroundColor Red; return $false
}

# ---------- 1. conferencias ----------
$etapa = 1; Cabecalho-Etapa $etapa $TOTET 'Conferindo arquivos e chave' $ini0
if (-not (Test-Path $ARQ_CHAVE)) {
  Fim ("Falta a chave do Supabase. Crie o arquivo`n  $ARQ_CHAVE`ncom uma linha so: a chave secreta (Supabase > Project Settings > API keys > secret).`nNinguem precisa ver esse arquivo; o script so le.") 'Yellow'
}
$script:CHAVE = (Get-Content -LiteralPath $ARQ_CHAVE -TotalCount 1 -Encoding UTF8 | Out-String).Trim()
if ($script:CHAVE.Length -lt 20) { Fim "O arquivo $ARQ_CHAVE parece vazio ou incompleto. Confira e rode de novo." 'Yellow' }
$aoc = Join-Path $SUP 'ocorrencias_pj.csv'; $aem = Join-Path $SUP 'empresas.csv'
if (-not (Test-Path $aoc)) { Fim "Nao achei $aoc. Rode antes a opcao [12] (base consolidada)." 'Yellow' }
Write-Host "  Banco: $URL" ; Write-Host "  Arquivos: $(Split-Path $aoc -Leaf) ($([math]::Round((Get-Item $aoc).Length/1KB)) KB), $(if (Test-Path $aem) { Split-Path $aem -Leaf } else { 'empresas.csv (nao encontrado)' })"
try { Invoke-WebRequest -UseBasicParsing -Uri "$URL/rest/v1/empresas?select=cnpj&limit=1" -Headers @{ apikey = $script:CHAVE } -TimeoutSec 60 | Out-Null; Write-Host '  Conexao com o banco: OK' -ForegroundColor Green }
catch { Fim ("Nao consegui falar com o banco: " + (Erro-Texto $_) + "`nSe for 401, a chave do arquivo esta errada ou nao e a secret.") 'Red' }

# ---------- 2. ocorrencias ----------
$etapa = 2; Cabecalho-Etapa $etapa $TOTET 'Preparando ocorrencias' $ini0
$puladasOnline = 0; $semCnpj = 0; $env_oc = New-Object System.Collections.ArrayList
foreach ($r in (Ler-Ponto $aoc)) {
  $ch = Txt $r.chave; if (-not $ch) { continue }
  if ($ch -match $PULAR) { $puladasOnline++; continue }
  if (-not (Cnpj-Ok $r.cnpj)) { $semCnpj++; continue }
  $o = [ordered]@{}
  foreach ($c in $COLS_OC) {
    $v = if ($c -eq 'valor_indicado_rs_nao_e_dano') { $r.'valor_indicado_RS_NAO_E_DANO' } else { $r.$c }
    $v = Txt $v
    if ($DATAS_OC -contains $c) { $o[$c] = Data-Iso $v }
    elseif ($c -eq 'valor_indicado_rs_nao_e_dano') { $o[$c] = if ($v) { Num-Br $v } else { $null } }
    elseif ($c -eq 'cnpj') { $o[$c] = Cnpj-Fmt $v }
    else { $o[$c] = if ($v) { Mascara-Texto $v } else { $null } }
  }
  $o['origem'] = 'radar-pc'
  [void]$env_oc.Add([pscustomobject]$o)
}
Write-Host "  A enviar: $($env_oc.Count) | puladas (o coletor online ja envia): $puladasOnline | sem CNPJ valido: $semCnpj"
$okOc = 0; $falhaOc = 0
if ($env_oc.Count) {
  $ini = Get-Date; $nl = [math]::Ceiling($env_oc.Count / $LOTE)
  for ($i = 0; $i -lt $nl; $i++) {
    $parte = $env_oc[($i * $LOTE)..([math]::Min($env_oc.Count, ($i + 1) * $LOTE) - 1)]
    if (Post-Lote 'ocorrencias' 'chave' $parte) { $okOc += @($parte).Count } else { $falhaOc += @($parte).Count }
    Progresso ($i + 1) $nl $ini "lotes de ocorrencias | enviadas $okOc"
  }
}

# ---------- 3. empresas novas ----------
$etapa = 3; Cabecalho-Etapa $etapa $TOTET 'Empresas que ainda nao estao no site' $ini0
$noBanco = @{}; $off = 0
try {
  do {
    $pg = Invoke-RestMethod -Uri "$URL/rest/v1/empresas?select=cnpj&order=cnpj&limit=1000&offset=$off" -Headers @{ apikey = $script:CHAVE } -TimeoutSec 60
    foreach ($e in @($pg)) { if ($e.cnpj) { $noBanco[($e.cnpj -replace '\D', '')] = 1 } }
    $off += 1000
  } while (@($pg).Count -eq 1000)
} catch { Fim ("Nao consegui ler as empresas do banco: " + (Erro-Texto $_)) 'Red' }
Write-Host "  Empresas ja no banco: $($noBanco.Count)"
$cache = @{}; $acache = Join-Path $INT 'cache_receita_cnpj.json'
if (Test-Path $acache) { try { $j = Get-Content $acache -Raw -Encoding UTF8 | ConvertFrom-Json; foreach ($p in $j.PSObject.Properties) { $cache[$p.Name] = $p.Value } } catch {} }
$env_em = New-Object System.Collections.ArrayList; $jaTem = 0; $dvRuim = 0
foreach ($r in (Ler-Ponto $aem)) {
  $d = (Txt $r.cnpj) -replace '\D', ''
  if (-not (Cnpj-Ok $d)) { $dvRuim++; continue }
  if ($noBanco.ContainsKey($d)) { $jaTem++; continue }
  $soc = Txt $r.socios; if (-not $soc -and $cache.ContainsKey($d)) { $soc = Txt $cache[$d].socios }
  $mei = (Txt $r.mei_ou_individual) -match '^(SIM|S|TRUE|1|MEI)'
  $o = [ordered]@{
    cnpj = Cnpj-Fmt $d; razao_social = Mascara-Texto (Txt $r.razao_social); nome_fantasia = Mascara-Texto (Txt $r.nome_fantasia)
    situacao_receita = Txt $r.situacao_receita; natureza_juridica = Txt $r.natureza_juridica; individual = [bool]$mei
    atividade = Txt $r.atividade_principal; municipio_sede = Txt $r.municipio_sede; porte = Txt $r.porte
    telefone = Txt $r.telefone; email = Txt $r.email; socios = Mascara-Texto $soc; alerta = Mascara-Texto (Txt $r.alerta_cadastro)
    data_coleta = Data-Iso $r.data_cadastro
  }
  foreach ($k in @($o.Keys)) { if ($o[$k] -is [string] -and -not $o[$k]) { $o[$k] = $null } }
  if ($o.email -and $o.email -notmatch '@') { $o.email = $null }
  if ($o.telefone -and -not (($o.telefone -replace '\D', '') -replace '0', '')) { $o.telefone = $null }
  [void]$env_em.Add([pscustomobject]$o)
}
Write-Host "  Novas a enviar: $($env_em.Count) | ja estavam no banco: $jaTem | DV invalido (fora): $dvRuim"
$okEm = 0; $falhaEm = 0
if ($env_em.Count) {
  $ini = Get-Date; $nl = [math]::Ceiling($env_em.Count / $LOTE)
  for ($i = 0; $i -lt $nl; $i++) {
    $parte = $env_em[($i * $LOTE)..([math]::Min($env_em.Count, ($i + 1) * $LOTE) - 1)]
    if (Post-Lote 'empresas' 'cnpj' $parte) { $okEm += @($parte).Count } else { $falhaEm += @($parte).Count }
    Progresso ($i + 1) $nl $ini "lotes de empresas | enviadas $okEm"
  }
}

# ---------- 4. resumo ----------
$etapa = 4; Cabecalho-Etapa $etapa $TOTET 'Resumo' $ini0
$res = @(
  "Envio ao site em $STAMP ($URL)",
  "Ocorrencias enviadas: $okOc | falharam: $falhaOc | puladas (coletor online): $puladasOnline | sem CNPJ valido: $semCnpj",
  "Empresas novas enviadas: $okEm | falharam: $falhaEm | ja no banco: $jaTem | DV invalido: $dvRuim",
  "Tempo total: $(Fmt ((Get-Date) - $ini0).TotalSeconds)"
)
$res | ForEach-Object { Write-Host "  $_"; Add-Content $LOG $_ }
$cor = if ($falhaOc -or $falhaEm) { 'Yellow' } else { 'Green' }
Fim $(if ($falhaOc -or $falhaEm) { "Terminou com falhas. Detalhes em $LOG" } else { 'Envio concluido.' }) $cor
