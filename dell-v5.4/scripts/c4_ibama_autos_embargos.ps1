# [4] IBAMA Dados Abertos: autos de infracao + termos de embargo + cruzamento (RJ)  -  v5 (06/11/2026)
# Fonte oficial, sem login. Se o download falhar, usa a ultima copia local (RESERVA) e avisa.
# v5: (1) municipio com grafia unica pelo codigo IBGE; (2) autos cancelados/excluidos ficam FORA da soma e do
#     cruzamento (vao para arquivo proprio); (3) embargos: status VIGENTE/DESEMBARGADO/CANCELADO, arquivo dos
#     ultimos 12 meses e arquivo dos VIGENTES; cruzamento so com embargos vigentes; (4) prazo de defesa ESTIMADO
#     (Decreto 6.514/2008, art. 113: 20 dias da ciencia do auto) - estimativa, conferir no processo.
. "$PSScriptRoot\comum.ps1"
$UFALVO = 'RJ'; $DIAS = 365
$BASE = Join-Path $RAIZ '01-Coletas\ibama'; $INT = Join-Path $RAIZ '05-Interno'; $ACH = Join-Path $RAIZ '04-Achados'
New-Item -ItemType Directory -Force $BASE, $INT, $ACH, (Join-Path $RAIZ 'logs') | Out-Null
$STAMP = (Get-Date).ToString('yyyy-MM-dd_HHmm'); $HOJE = (Get-Date).ToString('yyyy-MM-dd'); $HOJED = (Get-Date).Date; $DESDE = $HOJED.AddDays(-$DIAS)
$LOG = Join-Path $RAIZ "logs\c4_$STAMP.log"
$URL_AUTOS = 'https://stibamadadosabertosprd.blob.core.windows.net/dados-abertos/dados/SIFISC/auto_infracao/auto_infracao/auto_infracao_csv.zip'
$URL_EMB = 'https://stibamadadosabertosprd.blob.core.windows.net/dados-abertos/dados/TERMOS_DE_EMBARGO/TERMO_EMBARGO/termo_de_embargo.csv'
$PAG_AUTOS = 'https://dadosabertos.ibama.gov.br/dataset/fiscalizacao-auto-de-infracao'
$PAG_EMB = 'https://dadosabertos.ibama.gov.br/dataset/fiscalizacao-termo-de-embargo'
$PRAZO_DEFESA = 20   # Decreto 6.514/2008, art. 113
$SEMLEITURA = ($env:RADAR_SEM_DOWNLOAD -eq '1')   # para teste: usa so as copias locais
$ini0 = Get-Date; $ET = 6
Write-Host "== IBAMA: AUTOS, EMBARGOS E CRUZAMENTO ($UFALVO) - v5 ==`nAutos desde $($DESDE.ToString('dd/MM/yyyy')) | coleta $HOJE`n"
function Invalido($cancel, $sit, $status) {
  $t = Norm-Txt "$sit $status"
  return (([string]$cancel).Trim().ToUpper() -eq 'S') -or ($t -match 'EXCLUID|CANCELAD')
}

Cabecalho-Etapa 1 $ET 'Download dos autos de infracao' $ini0
$zip = Join-Path $BASE 'auto_infracao_csv.zip'
$stA = if ($SEMLEITURA) { if (Test-Path (Join-Path $BASE 'autos_csv')) { 'RESERVA' } else { $null } } else { Baixar-Arquivo $URL_AUTOS $zip }
Cabecalho-Etapa 2 $ET 'Download dos termos de embargo' $ini0
$emb = Join-Path $BASE 'termo_de_embargo.csv'
$stE = if ($SEMLEITURA) { if (Test-Path $emb) { 'RESERVA' } else { $null } } else { Baixar-Arquivo $URL_EMB $emb }
Add-Content $LOG "autos: $stA | embargos: $stE"
if (-not $stA -and -not $stE) { Write-Host 'Nenhuma fonte disponivel e nenhuma copia local. Tente mais tarde.' -ForegroundColor Red; Som; exit 1 }
Carregar-Municipios

# ---------- AUTOS ----------
$autos = New-Object System.Collections.ArrayList     # validos
$canc = New-Object System.Collections.ArrayList      # cancelados / excluidos
$interno = New-Object System.Collections.ArrayList
if ($stA) {
  Cabecalho-Etapa 3 $ET 'Lendo autos (filtro UF e 12 meses)' $ini0
  $dirA = Join-Path $BASE 'autos_csv'
  if (-not $SEMLEITURA -and (Test-Path $zip)) { Remove-Item $dirA -Recurse -Force -ErrorAction SilentlyContinue; Expand-Archive $zip $dirA -Force }
  $vistosArq = Join-Path $BASE "autos_vistos_$UFALVO.txt"
  $vistos = @{}; $primeira = -not (Test-Path $vistosArq)
  if (-not $primeira) { Get-Content $vistosArq | ForEach-Object { $vistos[$_] = 1 } }
  # so os arquivos dos anos que podem ter autos do periodo (o nome traz o ano)
  $arqs = Get-ChildItem $dirA -Recurse -Filter *.csv | Where-Object { $m = [regex]::Match($_.Name, '(19|20)\d\d'); (-not $m.Success) -or ([int]$m.Value -ge $DESDE.Year) } | Sort-Object Name
  foreach ($f in $arqs) {
    $cab = Ler-Csv $f.FullName {
      param($r)
      if ($r['UF'] -ne $UFALVO) { return }
      $dt = Ler-Data $r['DAT_HORA_AUTO_INFRACAO']; if (-not $dt -or $dt -lt $DESDE) { return }
      $seq = [string]$r['SEQ_AUTO_INFRACAO']; if (-not $seq.Trim()) { $seq = "N:$($r['NUM_AUTO_INFRACAO'])/$($r['SER_AUTO_INFRACAO'])" }; $doc = ($r['CPF_CNPJ_INFRATOR'] -replace '\D', '')
      $tp = ([string]$r['TP_PESSOA_INFRATOR']).Trim().ToUpper()
      if ($tp -ne 'PJ' -and $tp -ne 'PF') { $tp = if ($doc.Length -eq 14) { 'PJ' } elseif ($doc.Length -eq 11) { 'PF' } else { '' } }
      $pj = ($doc.Length -eq 14)
      $novo = if ($primeira) { 'PRIMEIRA COLETA' } elseif ($vistos.ContainsKey($seq)) { '' } else { 'NOVO' }
      $inval = Invalido $r['SIT_CANCELADO'] $r['DS_SIT_AUTO_AIE'] $r['DES_STATUS_FORMULARIO']
      $cie = Ler-Data $r['DAT_CIENCIA_AUTUACAO']; $fimP = ''; $stP = ''
      if ($inval) { $stP = 'AUTO CANCELADO/EXCLUIDO' }
      elseif ($cie) { $fp = $cie.Date.AddDays($PRAZO_DEFESA); $fimP = $fp.ToString('yyyy-MM-dd')
        $stP = if ($HOJED -le $fp) { 'ABERTO (estimado)' } else { 'ENCERRADO (estimado)' } }
      elseif ($dt -ge $HOJED.AddDays(-45)) { $stP = 'SEM CIENCIA REGISTRADA - auto recente' }
      else { $stP = 'SEM CIENCIA REGISTRADA' }
      $o = [pscustomobject][ordered]@{
        data_auto = $dt.ToString('yyyy-MM-dd'); data_ciencia = $(if ($cie) { $cie.ToString('yyyy-MM-dd') } else { '' })
        prazo_defesa_fim_estimado = $fimP; prazo_defesa_status = $stP
        data_lancamento = $r['DT_LANCAMENTO']; novo_desde_ultima_coleta = $novo
        municipio = (Muni-Nome $r['COD_MUNICIPIO'] $r['MUNICIPIO']); cod_ibge = $r['COD_MUNICIPIO']; tipo_pessoa = $tp
        autuado = (Mascara-Texto $r['NOME_INFRATOR']); cpf_cnpj = (Mascara-Doc $doc); cnpj_dv_ok = $(if ($pj) { if (Cnpj-Ok $doc) { 'SIM' } else { 'NAO' } } else { '' })
        n_auto = $r['NUM_AUTO_INFRACAO']; serie = $r['SER_AUTO_INFRACAO']; processo = $r['NU_PROCESSO_FORMATADO']
        valor_auto_RS_nao_e_dano = $r['VAL_AUTO_INFRACAO']; tipo_multa = $r['TIPO_MULTA']; tipo_infracao = $r['TIPO_INFRACAO']; infracao = $r['DES_INFRACAO']
        gravidade = $r['GRAVIDADE_INFRACAO']; descricao = (Mascara-Texto $r['DES_AUTO_INFRACAO']); local = (Mascara-Texto $r['DES_LOCAL_INFRACAO'])
        forma_entrega = $r['FORMA_ENTREGA']; cancelado = $r['SIT_CANCELADO']; situacao = $r['DS_SIT_AUTO_AIE']; status_formulario = $r['DES_STATUS_FORMULARIO']
        valido = $(if ($inval) { 'NAO' } else { 'SIM' }); operacao = $r['OPERACAO']; seq_ibama = $seq; doc_digitos = $doc
        fonte = 'IBAMA Dados Abertos - auto_infracao_csv.zip'; link = $PAG_AUTOS; data_coleta = $HOJE; copia = $stA
        metodo = "UF=$UFALVO; DAT_HORA_AUTO_INFRACAO >= $($DESDE.ToString('yyyy-MM-dd')); cancelados/excluidos fora da soma; municipio pelo codigo IBGE; CPF mascarado; CNPJ com DV conferido; prazo = ciencia + $PRAZO_DEFESA dias (Dec. 6.514/2008 art. 113), estimado"
        classificacao = 'FATO: auto lavrado. NAO e condenacao (cabe defesa/recurso). Valor do auto NAO e dano' }
      if ($inval) { [void]$canc.Add($o) } else { [void]$autos.Add($o); if ($novo -eq 'NOVO') { } }
      if ($tp -eq 'PF' -and $doc) { [void]$interno.Add([pscustomobject][ordered]@{ origem = 'AUTO'; seq_ibama = $seq; n_auto = $r['NUM_AUTO_INFRACAO']; data = $dt.ToString('yyyy-MM-dd'); nome = $r['NOME_INFRATOR']; cpf = $doc }) }
    } $f.Name
    Add-Content $LOG "colunas autos ($($f.Name)): $($cab -join ',')"
  }
  $todos = @($vistos.Keys) + @($autos | ForEach-Object { $_.seq_ibama }) + @($canc | ForEach-Object { $_.seq_ibama }) | Sort-Object -Unique
  $todos | Set-Content $vistosArq -Encoding ASCII
} else { Write-Host '   Autos: sem arquivo, pulando.' -ForegroundColor Yellow }

# ---------- EMBARGOS ----------
$embs = New-Object System.Collections.ArrayList
if ($stE) {
  Cabecalho-Etapa 4 $ET 'Lendo termos de embargo (status e data)' $ini0
  $script:cE = $null
  $cabE = Ler-Csv $emb {
    param($r)
    if (-not $script:cE) {
      $k = @($r.Keys)
      $script:cE = @{ uf = (Col $k '^UF$', '^SIG_UF$', 'UF'); doc = (Col $k 'CPF_CNPJ', 'CPF', 'CNPJ'); nome = (Col $k 'NOME_EMBARGADO', 'NOME_PESSOA', 'NOME')
        data = (Col $k '^DAT_EMBARGO$', 'DAT_EMBARGO', 'DT_EMBARGO', 'DAT_IMPRESSAO'); canc = (Col $k '^SIT_CANCELADO$'); stf = (Col $k '^DES_STATUS_FORMULARIO$')
        sdes = (Col $k '^SIT_DESEMBARGO$'); ddes = (Col $k '^DAT_DESEMBARGO$'); muni = (Col $k '^MUNICIPIO$'); cmun = (Col $k '^COD_MUNICIPIO$') }
    }
    if ($r[$script:cE.uf] -ne $UFALVO) { return }
    $dE = Ler-Data $r[$script:cE.data]
    $st = if (Invalido $r[$script:cE.canc] '' $r[$script:cE.stf]) { 'CANCELADO' }
          elseif ((([string]$r[$script:cE.sdes]).Trim().ToUpper() -eq 'S') -or ([string]$r[$script:cE.ddes]).Trim()) { 'DESEMBARGADO' }
          else { 'VIGENTE (sem desembargo nos dados abertos)' }
    $o = [ordered]@{ status_embargo = $st; data_embargo = $(if ($dE) { $dE.ToString('yyyy-MM-dd') } else { '' }); ultimos_12m = $(if ($dE -and $dE -ge $DESDE) { 'SIM' } else { 'NAO' })
      municipio_normalizado = (Muni-Nome $r[$script:cE.cmun] $r[$script:cE.muni]) }
    foreach ($c in ($r.Keys | Sort-Object)) {
      if ($c -match 'CPF|CNPJ') { $o[$c] = Mascara-Doc $r[$c] } else { $o[$c] = Mascara-Texto $r[$c] }
    }
    $doc = ($r[$script:cE.doc] -replace '\D', '')
    $o['doc_digitos'] = $doc; $o['cnpj_dv_ok'] = $(if ($doc.Length -eq 14) { if (Cnpj-Ok $doc) { 'SIM' } else { 'NAO' } } else { '' })
    $o['fonte'] = 'IBAMA Dados Abertos - termo_de_embargo.csv'; $o['link'] = $PAG_EMB; $o['data_coleta'] = $HOJE; $o['copia'] = $stE
    $o['classificacao'] = 'FATO: termo de embargo lavrado. VIGENTE = sem registro de desembargo nos dados abertos; confirmar no processo antes de afirmar'
    [void]$embs.Add([pscustomobject]$o)
    if ($doc.Length -eq 11) { [void]$interno.Add([pscustomobject][ordered]@{ origem = 'EMBARGO'; seq_ibama = ''; n_auto = ''; data = $o.data_embargo; nome = $r[$script:cE.nome]; cpf = $doc }) }
  } 'embargos'
  Add-Content $LOG "colunas embargos: $($cabE -join ',')"
  Add-Content $LOG "colunas usadas embargos: $($script:cE | ConvertTo-Json -Compress)"
  if ($embs.Count -eq 0) { Write-Host "  ATENCAO: nenhum embargo $UFALVO encontrado. Pode ser nome de coluna diferente: ver $LOG" -ForegroundColor Yellow }
} else { Write-Host '   Embargos: sem arquivo, pulando.' -ForegroundColor Yellow }
$vig = @($embs | Where-Object { $_.status_embargo -like 'VIGENTE*' })
$e12 = @($embs | Where-Object { $_.ultimos_12m -eq 'SIM' })

# ---------- CRUZAMENTO ----------
Cabecalho-Etapa 5 $ET 'Cruzando autos validos x embargos vigentes' $ini0
$cx = @{}
foreach ($a in $autos) { if (-not $a.doc_digitos) { continue }
  if (-not $cx[$a.doc_digitos]) { $cx[$a.doc_digitos] = @{ nome = $a.autuado; autos = 0; valor = 0.0; vig = 0; vig12 = 0; munis = @{} } }
  $x = $cx[$a.doc_digitos]; $x.autos++; $x.valor += (Num-Br $a.valor_auto_RS_nao_e_dano); $x.munis[$a.municipio] = 1 }
foreach ($e in $vig) { $d = $e.doc_digitos; if (-not $d) { continue }
  if (-not $cx[$d]) { $cx[$d] = @{ nome = $e.($script:cE.nome); autos = 0; valor = 0.0; vig = 0; vig12 = 0; munis = @{} } }
  $cx[$d].vig++; if ($e.ultimos_12m -eq 'SIM') { $cx[$d].vig12++ } }
$cruz = foreach ($d in $cx.Keys) { $x = $cx[$d]; if ($x.autos -gt 0 -and $x.vig -gt 0) {
  [pscustomobject][ordered]@{ cpf_cnpj = (Mascara-Doc $d); tipo = $(if ($d.Length -eq 14) { 'PJ' } else { 'PF' }); cnpj_dv_ok = $(if ($d.Length -eq 14) { if (Cnpj-Ok $d) { 'SIM' } else { 'NAO' } } else { '' })
    nome = $x.nome; autos_validos_12m = $x.autos; embargos_vigentes_RJ = $x.vig; embargos_vigentes_12m = $x.vig12
    soma_valor_autos_RS_NAO_E_DANO = $x.valor; municipios_autos = (($x.munis.Keys | Sort-Object) -join '; ')
    classificacao = 'FATO: mesmo CPF/CNPJ com auto valido (12m) e embargo do IBAMA sem desembargo registrado. Conferir razao social na Receita antes de usar' } } }

# ---------- SAIDAS ----------
Cabecalho-Etapa 6 $ET 'Gravando arquivos' $ini0
$tira = { $_ | Select-Object * -ExcludeProperty doc_digitos }
$nov = @($autos | Where-Object novo_desde_ultima_coleta -eq 'NOVO' | Sort-Object data_auto -Descending)
$fA = Join-Path $ACH "ibama_autos_${UFALVO}_$STAMP.csv"; $autos | Sort-Object data_auto -Descending | ForEach-Object $tira | Export-Csv $fA -Delimiter ';' -NoTypeInformation -Encoding UTF8
$fX = Join-Path $ACH "ibama_autos_CANCELADOS_${UFALVO}_$STAMP.csv"; $canc | Sort-Object data_auto -Descending | ForEach-Object $tira | Export-Csv $fX -Delimiter ';' -NoTypeInformation -Encoding UTF8
$fN = Join-Path $ACH "ibama_autos_NOVOS_${UFALVO}_$STAMP.csv"; $nov | ForEach-Object $tira | Export-Csv $fN -Delimiter ';' -NoTypeInformation -Encoding UTF8
$fV = Join-Path $ACH "ibama_embargos_VIGENTES_${UFALVO}_$STAMP.csv"; $vig | Sort-Object data_embargo -Descending | ForEach-Object $tira | Export-Csv $fV -Delimiter ';' -NoTypeInformation -Encoding UTF8
$f12 = Join-Path $ACH "ibama_embargos_12m_${UFALVO}_$STAMP.csv"; $e12 | Sort-Object data_embargo -Descending | ForEach-Object $tira | Export-Csv $f12 -Delimiter ';' -NoTypeInformation -Encoding UTF8
$fE = Join-Path $BASE "ibama_embargos_HISTORICO_${UFALVO}_$STAMP.csv"; $embs | Sort-Object data_embargo -Descending | ForEach-Object $tira | Export-Csv $fE -Delimiter ';' -NoTypeInformation -Encoding UTF8
$fC = Join-Path $ACH "ibama_cruzamento_autos_embargos_${UFALVO}_$STAMP.csv"; @($cruz) | Sort-Object autos_validos_12m -Descending | Export-Csv $fC -Delimiter ';' -NoTypeInformation -Encoding UTF8
$fI = Join-Path $INT "INTERNO_ibama_PF_${UFALVO}_$STAMP.csv"; $interno | Export-Csv $fI -Delimiter ';' -NoTypeInformation -Encoding UTF8

# conferencia final: nenhum CPF aparente nos arquivos publicos
$vaz = 0; foreach ($arq in $fA, $fX, $fN, $fV, $f12, $fC) { foreach ($m in [regex]::Matches((Get-Content $arq -Raw -Encoding UTF8) + '', '(?<![\d/])\d{3}\.?\d{3}\.?\d{3}-?\d{2}(?![\d/])')) { if (Cpf-Ok $m.Value) { $vaz++ } } }

$pjv = @($autos | Where-Object { $_.tipo_pessoa -eq 'PJ' -and $_.cnpj_dv_ok -eq 'SIM' } | ForEach-Object doc_digitos | Sort-Object -Unique)
Write-Host "`n================ RESUMO ================"
Write-Host "Autos VALIDOS $UFALVO (12 meses): $($autos.Count) | cancelados/excluidos (fora da soma): $($canc.Count) | hoje ($HOJE): $(@($autos | Where-Object data_auto -eq $HOJE).Count)"
Write-Host "Empresas (CNPJ valido) com auto valido: $($pjv.Count) | prazo de defesa ABERTO (estimado): $(@($autos | Where-Object prazo_defesa_status -eq 'ABERTO (estimado)').Count) autos"
Write-Host "Municipios distintos (grafia unica): $(@($autos | ForEach-Object municipio | Sort-Object -Unique).Count)"
if ($primeira) { Write-Host 'Primeira coleta: a partir da proxima, os autos novos serao marcados.' } else { Write-Host "NOVOS desde a ultima coleta: $($nov.Count)" -ForegroundColor Cyan }
$nov | Select-Object -First 15 | ForEach-Object { Write-Host ("  {0} {1,-22} {2,-4} {3} | {4}" -f $_.data_auto, $_.municipio, $_.tipo_pessoa, $_.autuado, $_.tipo_infracao) }
Write-Host "Embargos $UFALVO no historico: $($embs.Count) | VIGENTES: $($vig.Count) | lavrados nos ultimos 12 meses: $($e12.Count) | desembargados: $(@($embs | Where-Object status_embargo -eq 'DESEMBARGADO').Count) | cancelados: $(@($embs | Where-Object status_embargo -eq 'CANCELADO').Count)"
Write-Host "Cruzamento (auto valido + embargo vigente): $(@($cruz).Count)"
if ($stA -eq 'RESERVA' -or $stE -eq 'RESERVA') { Write-Host 'ATENCAO: parte dos dados veio da COPIA LOCAL (download falhou).' -ForegroundColor Yellow }
if ($vaz) { Write-Host "ATENCAO: $vaz possiveis CPFs nos arquivos publicos. NAO publicar antes de conferir." -ForegroundColor Red } else { Write-Host 'Conferencia de CPF nos arquivos publicos: OK (zero).' -ForegroundColor Green }
Write-Host "`nArquivos (04-Achados):`n $fA`n $fX`n $fN`n $fV`n $f12`n $fC`n (historico completo de embargos, 01-Coletas) $fE`n (interno) $fI`nTempo total: $(Fmt ((Get-Date) - $ini0).TotalSeconds)"
Write-Host 'Proximo passo sugerido: [9] enriquecer CNPJs e [10] gerar a fila de prospeccao.'
Write-Host 'Lembrete: auto e embargo NAO sao condenacao; valor do auto NAO e dano; prazo e ESTIMADO.'
Add-Content $LOG "resumo: validos=$($autos.Count) cancelados=$($canc.Count) emb=$($embs.Count) vig=$($vig.Count) e12=$($e12.Count) cruz=$(@($cruz).Count) cpf_vazado=$vaz"
Som
