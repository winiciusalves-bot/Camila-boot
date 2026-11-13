# [3] Conferir CNPJs da coleta 1 na BrasilAPI (dados publicos da Receita)
. "$PSScriptRoot\comum.ps1"
$ENT = Join-Path $RAIZ '01-Coletas\autos_diarios'; $SAI = Join-Path $RAIZ '04-Achados'; $ARQ_CACHE = Join-Path $RAIZ '05-Interno\cache_cnpj.json'
New-Item -ItemType Directory -Force $SAI, (Split-Path $ARQ_CACHE) | Out-Null
$arq = Get-ChildItem $ENT -Filter 'autos_ambientais_CNPJ_*.csv' -ErrorAction SilentlyContinue | Sort-Object Name | Select-Object -Last 1
if (-not $arq) { Write-Host 'Nenhuma coleta encontrada. Rode a opcao 1 antes.'; return }
$linhas = Import-Csv $arq.FullName -Delimiter ';'
$cache = @{}; if (Test-Path $ARQ_CACHE) { (Get-Content $ARQ_CACHE -Raw -Encoding UTF8 | ConvertFrom-Json).psobject.Properties | ForEach-Object { $cache[$_.Name] = $_.Value } }
# consultas que deram erro nao ficam no cache: sao repetidas na proxima execucao
@($cache.Keys) | Where-Object { $cache[$_].razao_social -eq 'ERRO NA CONSULTA - repetir' } | ForEach-Object { $cache.Remove($_) }
$fila = @($linhas.cnpj | Sort-Object -Unique | Where-Object { -not $cache.ContainsKey($_) })
Write-Host "Arquivo: $($arq.Name)`nCNPJs a consultar: $($fila.Count) (cache: $($cache.Count))`n"
$ini = Get-Date; $i = 0
foreach ($c in $fila) {
  $i++
  try { $j = Get-J ("https://brasilapi.com.br/api/cnpj/v1/" + ($c -replace '\D','')) 3
        $cache[$c] = [pscustomobject]@{ razao_social = $j.razao_social; situacao = $j.descricao_situacao_cadastral; municipio_sede = $j.municipio; cnae = $j.cnae_fiscal_descricao } }
  catch { $r = if ((Cod-Erro $_) -eq 404) { 'NAO ENCONTRADO NA RECEITA' } else { 'ERRO NA CONSULTA - repetir' }
          $cache[$c] = [pscustomobject]@{ razao_social = $r; situacao = ''; municipio_sede = ''; cnae = '' } }
  if ($i % 20 -eq 0) { $cache | ConvertTo-Json -Depth 3 | Set-Content $ARQ_CACHE -Encoding UTF8 }
  Progresso $i $fila.Count $ini "$c $($cache[$c].razao_social)"
  Start-Sleep -Milliseconds 1200
}
$cache | ConvertTo-Json -Depth 3 | Set-Content $ARQ_CACHE -Encoding UTF8
$out = Join-Path $SAI ("autos_ambientais_CONFERIDO_{0:yyyy-MM-dd_HHmm}.csv" -f (Get-Date))
$linhas | ForEach-Object { $k = $cache[$_.cnpj]; $_.razao_social = $k.razao_social
  $_ | Add-Member situacao $k.situacao -Force -PassThru | Add-Member municipio_sede $k.municipio_sede -Force -PassThru | Add-Member cnae $k.cnae -Force -PassThru } |
  Export-Csv $out -Delimiter ';' -NoTypeInformation -Encoding UTF8
Write-Host "`nPronto: $out`nTempo: $(Fmt ((Get-Date)-$ini).TotalSeconds)"; Som
