# [1] Autos/multas/licencas/TAC/embargos ambientais nos Diarios Oficiais (Querido Diario), 12 meses, com CNPJ
. "$PSScriptRoot\comum.ps1"
$SAIDA = Join-Path $RAIZ '01-Coletas\autos_diarios'; New-Item -ItemType Directory -Force $SAIDA | Out-Null
$DESDE = (Get-Date).AddDays(-365).ToString('yyyy-MM-dd'); $ATE = (Get-Date).ToString('yyyy-MM-dd'); $STAMP = (Get-Date).ToString('yyyy-MM-dd_HHmm')
$TERMOS = '"auto de infração" ambiental', '"multa ambiental"', '"infração ambiental"', '"licença ambiental"', '"termo de ajustamento de conduta" ambiental', '"embargo" ambiental'
$CLASSE = [ordered]@{ 'AUTO/MULTA' = 'auto de infra|multa|penalidade|autuad'; 'TAC' = 'ajustamento de conduta|\bTAC\b'; 'EMBARGO/INTERDICAO' = 'embarg|interdi'; 'LICENCA' = 'licen[cç]a|licenciamento' }
$AMB = 'ambient|meio ambiente|polui|desmat|supress|res[ií]duo|efluente|vegeta'
Write-Host "== AUTOS/MULTAS AMBIENTAIS NOS DIARIOS OFICIAIS (RJ) ==`nPeriodo $DESDE a $ATE | Fonte: Querido Diario`n"
$LOG = Join-Path $RAIZ ('logs\c1_erros_' + $STAMP + '.log')
$API = 'https://api.queridodiario.ok.org.br/gazettes'
function Falha-Teste($msg) {
  Write-Host "`nFALHA NO TESTE DA API: $msg" -ForegroundColor Red
  Add-Content $LOG "[$((Get-Date).ToString('s'))] TESTE: $msg"
  if ($msg -match 'HTTP 403') { Write-Host 'Acesso negado (403). NAO contornar. Ver se a rede do gabinete bloqueia o site (proxy/firewall) ou testar em outra rede.' -ForegroundColor Yellow }
  elseif ($msg -match 'HTTP 429') { Write-Host 'Limite de requisicoes (429). Esperar e rodar mais tarde.' -ForegroundColor Yellow }
  elseif ($msg -match 'HTTP 5') { Write-Host 'Erro no servidor do Querido Diario. Rodar mais tarde.' -ForegroundColor Yellow }
  elseif ($msg -match 'SSL|TLS|canal seguro|secure channel|schannel') { Write-Host 'Falha de TLS/SSL em todas as formas testadas. Provavel: Windows sem suporte ao protocolo exigido pelo site, ou inspecao SSL do proxy da rede. Mande esta tela.' -ForegroundColor Yellow }
  elseif ($msg -match 'HTTP 0 \| ') { Write-Host 'Sem resposta HTTP: rede, DNS, proxy ou certificado. Teste abrir https://queridodiario.ok.org.br no navegador deste PC.' -ForegroundColor Yellow }
  Write-Host "Detalhe salvo em $LOG"
  Write-Host 'Enquanto o Querido Diario estiver fora, use as fontes alternativas: [4] IBAMA (autos novos + embargos) e [5] DOU (editais).' -ForegroundColor Cyan
  Som; exit 1
}
# --- Teste 1: a API responde? (consulta minima) ---
Write-Host 'Teste 1/2: a API do Querido Diario responde...'
try { $t = Escolher-Transporte "$API`?querystring=$([uri]::EscapeDataString('meio ambiente'))&size=1"; Write-Host ("  Total na base: {0} | conexao: {1}" -f $t.total_gazettes, $script:TRANSP_NOME) -ForegroundColor Green }
catch { Falha-Teste (Erro-Texto $_) }
Add-Content $LOG "[$((Get-Date).ToString('s'))] conexao escolhida: $script:TRANSP_NOME"
# --- Teste 2: a consulta completa e aceita? Se nao, usa parametros menores ---
$PARAMS = 'excerpt_size=600&number_of_excerpts=20&size=100'
$RESERVA = 'excerpt_size=500&number_of_excerpts=5&size=50'
# via curl o JSON e lido pelo ConvertFrom-Json do PowerShell 5.1, que falha com resposta muito grande: paginas menores
if ($script:TRANSP -ne 'irm') { $PARAMS = 'excerpt_size=600&number_of_excerpts=10&size=20'; $RESERVA = 'excerpt_size=500&number_of_excerpts=5&size=10' }
$teste = '{0}?territory_ids=3304557&querystring={1}&published_since={2}&published_until={3}&{4}&offset=0&sort_by=descending_date'
Write-Host 'Teste 2/2: consulta completa (Rio de Janeiro)...'
try { $t = Get-J ($teste -f $API, [uri]::EscapeDataString($TERMOS[1]), $DESDE, $ATE, $PARAMS) 2; Write-Host ("  OK ({0} edicoes)" -f $t.total_gazettes) -ForegroundColor Green }
catch {
  $m1 = Erro-Texto $_; Add-Content $LOG "[$((Get-Date).ToString('s'))] parametros completos recusados: $m1"
  Write-Host "  Parametros completos recusados ($m1). Tentando parametros menores..." -ForegroundColor Yellow
  try { $t = Get-J ($teste -f $API, [uri]::EscapeDataString($TERMOS[1]), $DESDE, $ATE, $RESERVA) 2; $PARAMS = $RESERVA; Write-Host '  OK com parametros menores' -ForegroundColor Green }
  catch { Falha-Teste ("parametros completos: $m1 || parametros menores: " + (Erro-Texto $_)) }
}
$muns = Municipios-RJ
$tarefas = foreach ($m in $muns) { foreach ($t in $TERMOS) { [pscustomobject]@{ m = $m; t = $t } } }
$linhas = New-Object System.Collections.ArrayList; $vistos = @{}; $cob = [ordered]@{}; $ini = Get-Date; $i = 0; $erroSeq = 0; $MAXSEQ = 12; $abortou = $false
foreach ($x in $tarefas) {
  $i++; $gs = @(); $st = 'OK'; $off = 0
  try {
    do {
      $q = 'territory_ids={0}&querystring={1}&published_since={2}&published_until={3}&{5}&offset={4}&sort_by=descending_date' -f $x.m.cod, [uri]::EscapeDataString($x.t), $DESDE, $ATE, $off, $PARAMS
      $d = Get-J "$API`?$q"
      $g = @($d.gazettes); $gs += $g; $off += $g.Count; Start-Sleep -Milliseconds 400
    } while ($g.Count -gt 0 -and $off -lt $d.total_gazettes)
    $erroSeq = 0
  } catch {
    $msg = Erro-Texto $_; $cod = ([regex]::Match($msg, 'HTTP (\d+)')).Groups[1].Value
    $st = if ($cod) { "E$cod" } else { 'ERRO' }; $erroSeq++
    Add-Content $LOG "[$((Get-Date).ToString('s'))] $($x.m.nome) | $($x.t) | $msg"
    if ($erroSeq -ge $MAXSEQ) { $abortou = $true }
  }
  if (-not $cob.Contains($x.m.nome)) { $cob[$x.m.nome] = @{ cod = $x.m.cod; ed = 0; err = 0 } }
  $cob[$x.m.nome].ed += $gs.Count; if ($st -ne 'OK') { $cob[$x.m.nome].err++ }
  foreach ($g in $gs) { foreach ($ex in @($g.excerpts)) {
    $e = ($ex -replace '\s+', ' ')
    if ($e -notmatch $AMB) { continue }
    $cl = 'OUTRO'; foreach ($k in $CLASSE.Keys) { if ($e -match $CLASSE[$k]) { $cl = $k; break } }
    foreach ($mm in [regex]::Matches($e, '(?<!\d)(\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2})(?!\d)')) {
      if (-not (Cnpj-Ok $mm.Value)) { continue }
      $cn = Cnpj-Fmt $mm.Value; $ch = "$cn|$($g.date)|$($g.url)"; if ($vistos[$ch]) { continue }; $vistos[$ch] = 1
      $a = [math]::Max(0, $mm.Index - 250); $b = [math]::Min($e.Length, $mm.Index + $mm.Length + 250)
      [void]$linhas.Add([pscustomobject][ordered]@{ municipio = $x.m.nome; cod_ibge = $x.m.cod; cnpj = $cn; razao_social = 'CONFERIR NA RECEITA'
        tipo_indicio = $cl; data_edicao = $g.date; edicao = $g.edition; termo_busca = $x.t; trecho = (Mascara-Cpf $e.Substring($a, $b - $a))
        link_diario = $g.url; link_texto = $g.txt_url; classificacao = 'INDICIO - ler o ato'; fonte = 'Querido Diario / DO municipal'; data_coleta = (Get-Date).ToString('s') })
    }
  } }
  Progresso $i $tarefas.Count $ini ('{0,-24} {1,-28} {2,4} ed. {3,-5} | CNPJs {4}' -f $x.m.nome.Substring(0, [math]::Min(24, $x.m.nome.Length)), $x.t.Substring(0, [math]::Min(28, $x.t.Length)), $gs.Count, $st, $linhas.Count)
  if ($abortou) {
    Write-Host "`nPARADO: $MAXSEQ erros seguidos. Ultimo erro: $msg" -ForegroundColor Red
    Write-Host "Os resultados parciais foram salvos. Lista de erros em $LOG"; break
  }
}
$arq = Join-Path $SAIDA "autos_ambientais_CNPJ_$STAMP.csv"
$linhas | Export-Csv $arq -Delimiter ';' -NoTypeInformation -Encoding UTF8
$cobArq = Join-Path $SAIDA "cobertura_municipios_$STAMP.csv"
$cob.Keys | ForEach-Object { $c = $cob[$_]; $n = @($linhas | Where-Object municipio -eq $_).Count
  $sit = if ($c.err -gt 0 -and $c.ed -eq 0) { 'CONSULTA FALHOU - repetir' } elseif ($c.err -eq $TERMOS.Count) { 'CONSULTA FALHOU - repetir' } elseif ($c.ed -eq 0) { 'SEM EDICAO NA BASE - verificar no DO proprio' } else { 'OK' }
  [pscustomobject][ordered]@{ municipio = $_; cod_ibge = $c.cod; edicoes_com_termo = $c.ed; cnpjs = $n; erros = $c.err; situacao = $sit } } |
  Export-Csv $cobArq -Delimiter ';' -NoTypeInformation -Encoding UTF8
Write-Host "`nPronto:`n $arq`n $cobArq`nOcorrencias: $($linhas.Count) | CNPJs distintos: $(@($linhas.cnpj | Sort-Object -Unique).Count)`nTempo: $(Fmt ((Get-Date)-$ini).TotalSeconds)"
Write-Host 'ATENCAO: cada linha e INDICIO. Ler o ato no link antes de afirmar multa.'
Som
