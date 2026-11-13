# [8] IBAMA Dados Abertos: notificacoes, suspensoes, demolicoes, apreensoes, acidentes (SIEMA) e licencas federais (RJ)  -  v5.1
# Fontes novas para nao depender so dos autos. Sem login. Download falhou -> usa a copia local (RESERVA).
# ATENCAO (PowerShell nao diferencia maiusculas): nao use $f/$p/$n/$k no escopo de fora do Ler-Csv.
# Notificacao = IBAMA exige algo da empresa (documento, providencia). Suspensao = atividade suspensa.
# As duas sao FATO documentado, NAO condenacao. Nomes de coluna sao detectados e gravados no log.
. "$PSScriptRoot\comum.ps1"
$UFALVO = 'RJ'; $DIAS = 365
$BASE = Join-Path $RAIZ '01-Coletas\ibama'; $INT = Join-Path $RAIZ '05-Interno'; $ACH = Join-Path $RAIZ '04-Achados'
New-Item -ItemType Directory -Force $BASE, $INT, $ACH, (Join-Path $RAIZ 'logs') | Out-Null
$STAMP = (Get-Date).ToString('yyyy-MM-dd_HHmm'); $HOJE = (Get-Date).ToString('yyyy-MM-dd'); $DESDE = (Get-Date).Date.AddDays(-$DIAS)
$LOG = Join-Path $RAIZ "logs\c6_$STAMP.log"
$SEMLEITURA = ($env:RADAR_SEM_DOWNLOAD -eq '1')
$URL_BLOB = 'https://stibamadadosabertosprd.blob.core.windows.net/dados-abertos/dados'; $URL_PAG = 'https://dadosabertos.ibama.gov.br/dataset'
# dias = janela de datas (0 = todo o historico do RJ). classe = como o documento entra na base.
$FONTES = @(
  @{ id = 'notificacoes'; nome = 'Notificacao'; arq = 'fiscalizacao_notificacao.csv'; tipo = 'csv'; dias = 365
     url = "$URL_BLOB/FISCALIZACAO_NOTIFICACAO/fiscalizacao_notificacao.csv"; pag = "$URL_PAG/fiscalizacao-notificacao"; classe = 'FATO: notificacao emitida pelo IBAMA. NAO e condenacao' },
  @{ id = 'suspensoes'; nome = 'Termo de suspensao'; arq = 'termo_de_suspensao.csv'; tipo = 'csv'; dias = 365
     url = "$URL_BLOB/TERMOS/TERMO_SUSPENSAO/termo_de_suspensao.csv"; pag = "$URL_PAG/fiscalizacao-termo-de-suspensao"; classe = 'FATO: termo de suspensao lavrado pelo IBAMA. NAO e condenacao' },
  @{ id = 'demolicoes'; nome = 'Termo de demolicao'; arq = 'termo_de_demolicao.csv'; tipo = 'csv'; dias = 0
     url = "$URL_BLOB/TERMOS/TERMO_DEMOLICAO/termo_de_demolicao.csv"; pag = "$URL_PAG/fiscalizacao-termo-de-demolicao"; classe = 'FATO: termo de demolicao lavrado pelo IBAMA. NAO e condenacao' },
  @{ id = 'apreensoes'; nome = 'Termo de apreensao'; arq = 'apreensao_csv.zip'; tipo = 'zip'; dias = 365
     url = 'https://dadosabertos.ibama.gov.br/dados/SIFISC/termo_apreensao/apreensao/apreensao_csv.zip'; pag = "$URL_PAG/fiscalizacao-termo-de-apreensao"; classe = 'FATO: termo de apreensao lavrado pelo IBAMA. NAO e condenacao' },
  @{ id = 'acidentes'; nome = 'Comunicado de acidente ambiental (SIEMA)'; arq = 'siema_acidentes.csv'; tipo = 'csv'; dias = 730
     url = 'http://siscom.ibama.gov.br/geoserver/publica/ows?service=WFS&version=1.0.0&request=GetFeature&typeName=publica%3Aadm_comunicacidente_p&outputFormat=csv'; pag = "$URL_PAG/siema-comunicado-de-acidente-ambiental"; classe = 'FATO: acidente ambiental comunicado ao IBAMA (SIEMA). NAO e infracao nem condenacao' }
  # SISLIC (licencas federais) retirado em 06/11/2026: o arquivo nao tem UF nem CNPJ (veio o Brasil inteiro, 14.376 linhas).
)
$ini0 = Get-Date; $TOTET = $FONTES.Count * 2 + 1; $etapa = 0
Write-Host "== IBAMA: NOTIFICACOES, SUSPENSOES, DEMOLICOES, APREENSOES, E ACIDENTES ($UFALVO) ==`ncoleta $HOJE`n"
Carregar-Municipios
$interno = New-Object System.Collections.ArrayList
$resumo = @()
foreach ($FONTE in $FONTES) {
  $etapa++; Cabecalho-Etapa $etapa $TOTET "Download: $($FONTE.nome)" $ini0
  $dest = Join-Path $BASE $FONTE.arq
  $st = if ($SEMLEITURA) { if (Test-Path $dest) { 'RESERVA' } else { $null } } else { Baixar-Arquivo $FONTE.url $dest }
  if ($st -and $FONTE.tipo -eq 'zip') {
    $dz = Join-Path $BASE ($FONTE.id + '_csv'); Remove-Item $dz -Recurse -Force -ErrorAction SilentlyContinue
    try { Expand-Archive $dest $dz -Force; $dest = (Get-ChildItem $dz -Recurse -Filter *.csv | Sort-Object Length -Descending | Select-Object -First 1).FullName } catch { $dest = $null }
    if (-not $dest) { Write-Host "   $($FONTE.nome): zip sem CSV legivel." -ForegroundColor Yellow; $st = $null }
  }
  $DESDE = if ($FONTE.dias -gt 0) { (Get-Date).Date.AddDays(-$FONTE.dias) } else { [datetime]::MinValue }
  Add-Content $LOG "$($FONTE.id): $st"
  $etapa++; Cabecalho-Etapa $etapa $TOTET "Lendo: $($FONTE.nome)" $ini0
  if (-not $st) { Write-Host "   $($FONTE.nome): sem arquivo, pulando." -ForegroundColor Yellow; $resumo += "$($FONTE.nome): SEM DADOS (download falhou e nao ha copia local)"; continue }
  $lin = New-Object System.Collections.ArrayList
  $script:cc = $null; $script:nUF = 0
  $cab = Ler-Csv $dest {
    param($r)
    if (-not $script:cc) {
      $k = @($r.Keys)
      $script:cc = @{ uf = (Col $k '^UF$', '^SIG_UF$', '^SG_UF', '^DES_UF$', '^UF_', '^ESTADO$', 'UF'); doc = (Col $k 'CPF_CNPJ', 'CNPJ', 'CPF', 'NUM_DOC', 'DOCUMENTO'); nome = (Col $k '^NOME_', '^NOM_PESSOA', '^NO_PESSOA', '^NOM_', 'NOME', 'EMPREENDEDOR', 'RAZAO')
        data = (Col $k '^DAT_NOTIFICACAO', '^DT_NOTIFICACAO', '^DAT_TERMO', '^DAT_SUSPENSAO', '^DT_SUSPENSAO', '^DAT_DEMOLICAO', '^DAT_APREENSAO', '^DAT_LAVRATURA', '^DAT_EMISSAO', '^DT_EMISSAO', '^DAT_HORA', '^DT_OCORRENCIA', '^DAT_OCORRENCIA', '^DAT_ACIDENTE', '^DAT_', '^DT_', 'DATA')
        muni = (Col $k '^MUNICIPIO$', '^NOM_MUNICIPIO', 'MUNICIPIO'); cmun = (Col $k '^COD_MUNICIPIO$', '^CD_MUNICIPIO$', 'COD_MUN', 'IBGE')
        canc = (Col $k '^SIT_CANCELADO$', 'CANCELAD'); stf = (Col $k '^DES_STATUS_FORMULARIO$', 'STATUS') }
      Add-Content $LOG "$($FONTE.id) colunas usadas: $($script:cc | ConvertTo-Json -Compress)"
    }
    if ($script:cc.uf -and ($r[$script:cc.uf] -ne $UFALVO)) { return }
    $script:nUF++
    $dt = if ($script:cc.data) { Ler-Data $r[$script:cc.data] } else { $null }
    if ($FONTE.dias -gt 0 -and (-not $dt -or $dt -lt $DESDE)) { return }
    $doc = if ($script:cc.doc) { ([string]$r[$script:cc.doc]) -replace '\D', '' } else { '' }
    $vC = if ($script:cc.canc) { [string]$r[$script:cc.canc] } else { '' }; $vS = if ($script:cc.stf) { [string]$r[$script:cc.stf] } else { '' }
    $inval = ($vC.Trim().ToUpper() -eq 'S') -or ((Norm-Txt $vS) -match 'EXCLUID|CANCELAD')
    $o = [ordered]@{ tipo_documento = $FONTE.nome; data_documento = $(if ($dt) { $dt.ToString('yyyy-MM-dd') } else { '' }); valido = $(if ($inval) { 'NAO (cancelado/excluido)' } else { 'SIM' })
      municipio_normalizado = (Muni-Nome $(if ($script:cc.cmun) { $r[$script:cc.cmun] }) $(if ($script:cc.muni) { $r[$script:cc.muni] }))
      tipo_pessoa = $(if ($doc.Length -eq 14) { 'PJ' } elseif ($doc.Length -eq 11) { 'PF' } else { '' })
      cpf_cnpj = (Mascara-Doc $doc); cnpj_dv_ok = $(if ($doc.Length -eq 14) { if (Cnpj-Ok $doc) { 'SIM' } else { 'NAO' } } else { '' }) }
    foreach ($c in ($r.Keys | Sort-Object)) { if ($c -match 'CPF|CNPJ') { $o[$c] = Mascara-Doc $r[$c] } elseif ($c -notmatch 'WKT|GEOM') { $o[$c] = Mascara-Texto $r[$c] } }
    $o['fonte'] = "IBAMA Dados Abertos - $($FONTE.arq)"; $o['link'] = $FONTE.pag; $o['data_coleta'] = $HOJE; $o['copia'] = $st
    $o['classificacao'] = $FONTE.classe
    [void]$lin.Add([pscustomobject]$o)
    if ($doc.Length -eq 11) { [void]$interno.Add([pscustomobject][ordered]@{ origem = $FONTE.id; data = $o.data_documento; nome = $(if ($script:cc.nome) { $r[$script:cc.nome] }); cpf = $doc }) }
  } $FONTE.nome
  Add-Content $LOG "$($FONTE.id) colunas: $($cab -join ',')"
  if (-not $script:cc.uf) { Write-Host "   ATENCAO: coluna de UF nao encontrada em $($FONTE.arq). Ver $LOG" -ForegroundColor Yellow }
  if (-not $script:cc.data) { Write-Host "   ATENCAO: coluna de data nao encontrada em $($FONTE.arq). Ver $LOG" -ForegroundColor Yellow }
  $saida = Join-Path $ACH "ibama_$($FONTE.id)_${UFALVO}_$STAMP.csv"
  $lin | Sort-Object data_documento -Descending | Export-Csv $saida -Delimiter ';' -NoTypeInformation -Encoding UTF8
  $pj = @($lin | Where-Object { $_.tipo_pessoa -eq 'PJ' -and $_.valido -eq 'SIM' }).Count
  $jan = if ($FONTE.dias) { "de $($FONTE.dias) dias" } else { '(tudo)' }
  $resumo += "$($FONTE.nome): $($script:nUF) no RJ (historico) | $($lin.Count) na janela $jan | $pj de empresa (validos) | copia $st"
  $resumo += "   -> $saida"
}
$etapa++; Cabecalho-Etapa $etapa $TOTET 'Gravando interno e conferindo CPF' $ini0
$fI = Join-Path $INT "INTERNO_ibama_notif_susp_PF_${UFALVO}_$STAMP.csv"; $interno | Export-Csv $fI -Delimiter ';' -NoTypeInformation -Encoding UTF8
$vaz = 0; foreach ($arq in (Get-ChildItem $ACH -Filter "ibama_*_${UFALVO}_$STAMP.csv")) { foreach ($m in [regex]::Matches((Get-Content $arq.FullName -Raw -Encoding UTF8) + '', '(?<![\d/])\d{3}\.?\d{3}\.?\d{3}-?\d{2}(?![\d/])')) { if (Cpf-Ok $m.Value) { $vaz++ } } }
Write-Host "`n================ RESUMO ================"
$resumo | ForEach-Object { Write-Host $_ }
if ($vaz) { Write-Host "ATENCAO: $vaz possiveis CPFs nos arquivos publicos. NAO publicar antes de conferir." -ForegroundColor Red } else { Write-Host 'Conferencia de CPF nos arquivos publicos: OK (zero).' -ForegroundColor Green }
Write-Host "Colunas detectadas: $LOG`nTempo total: $(Fmt ((Get-Date) - $ini0).TotalSeconds)"
Som
