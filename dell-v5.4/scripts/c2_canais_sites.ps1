# [2] Canais de transparencia ambiental nos sites (pagina inicial) - INDICIO, nao prova omissao
. "$PSScriptRoot\comum.ps1"
$SAIDA = Join-Path $RAIZ '01-Coletas\canais_sites'; New-Item -ItemType Directory -Force $SAIDA | Out-Null
$URLS = Join-Path $SAIDA 'urls_municipios.csv'
$CAN = [ordered]@{ autos_infracao = 'auto[s]? de infra|multa[s]? ambienta|autua|fiscaliza'; licencas = 'licen[cç]a[s]? ambienta|licenciamento'; tac = 'ajustamento de conduta|\bTAC\b'
  embargos = 'embargo|interdi'; diario_oficial = 'di[aá]rio oficial|imprensa oficial'; meio_ambiente = 'meio ambiente|SEMMA|SMAC|SEMAM'; esic_ouvidoria = 'e-?sic|acesso [aà] informa|ouvidoria|transpar' }
if (-not (Test-Path $URLS)) {
  $l = foreach ($m in Municipios-RJ) { $s = ($m.nome.Normalize([Text.NormalizationForm]::FormD) -replace '\p{Mn}','' -replace '[^A-Za-z0-9]','').ToLower()
    [pscustomobject]@{ esfera = 'MUNICIPIO'; cod_ibge = $m.cod; orgao = $m.nome; url = "https://www.$s.rj.gov.br/"; url_conferida = 'NAO' } }
  $l += [pscustomobject]@{ esfera='ESTADO'; cod_ibge=''; orgao='INEA'; url='https://www.inea.rj.gov.br/'; url_conferida='SIM' }
  $l += [pscustomobject]@{ esfera='UNIAO'; cod_ibge=''; orgao='IBAMA'; url='https://www.gov.br/ibama/pt-br'; url_conferida='SIM' }
  $l | Export-Csv $URLS -Delimiter ';' -NoTypeInformation -Encoding UTF8
}
$lista = Import-Csv $URLS -Delimiter ';'; $ini = Get-Date; $i = 0
$res = foreach ($o in $lista) {
  $i++; $r = [ordered]@{ esfera = $o.esfera; cod_ibge = $o.cod_ibge; orgao = $o.orgao; status = ''; url_testada = $o.url }
  try { $p = Invoke-WebRequest $o.url -UseBasicParsing -UserAgent $UA -TimeoutSec 25; $r.status = 'OK'
        $links = $p.Links | ForEach-Object { [pscustomobject]@{ h = $_.href; t = (($_.outerHTML -replace '<[^>]+>', ' ') -replace '\s+', ' ') } }
        foreach ($k in $CAN.Keys) { $a = $links | Where-Object { $_.t -match $CAN[$k] } | Select-Object -First 1; $r[$k] = if ($a) { $a.h } else { '' } } }
  catch { $code = $_.Exception.Response.StatusCode.value__; $r.status = if ($code -in 401,403,429) { 'BLOQUEADO (nao contornado)' } else { 'SITE NAO ENCONTRADO - conferir URL' } }
  $r.data_coleta = (Get-Date).ToString('s'); [pscustomobject]$r
  Progresso $i $lista.Count $ini ('{0,-26} {1}' -f $o.orgao, $r.status); Start-Sleep -Seconds 1
}
$out = Join-Path $SAIDA ("canais_{0:yyyy-MM-dd_HHmm}.csv" -f (Get-Date))
$res | Export-Csv $out -Delimiter ';' -NoTypeInformation -Encoding UTF8
Write-Host "`nPronto: $out (INDICIO: nao achar link na pagina inicial nao prova omissao)"; Som
