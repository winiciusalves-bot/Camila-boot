# [13] INEA (orgao ambiental do Estado): penalidades aplicadas + acoes de fiscalizacao  -  v5.1 (06/11/2026)
# Fonte: Portal de Dados Abertos do Estado do RJ (dadosabertos.rj.gov.br), conjunto
# "Fiscalizacao e combate as infracoes ambientais" (INEA, atualizacao semestral). Sem login.
# A planilha nao tem dicionario de dados: o script acha sozinho a linha de cabecalho e as colunas
# (CNPJ/CPF, data, municipio, nome, valor, penalidade) e grava no log o que encontrou.
# Se a planilha for so de totais (sem CNPJ), grava como AGREGADO (serve para estatistica, nao para lead).
. "$PSScriptRoot\comum.ps1"
$BASE = Join-Path $RAIZ '01-Coletas\inea'; $ACH = Join-Path $RAIZ '04-Achados'; $INT = Join-Path $RAIZ '05-Interno'
New-Item -ItemType Directory -Force $BASE, $ACH, $INT, (Join-Path $RAIZ 'logs') | Out-Null
$STAMP = (Get-Date).ToString('yyyy-MM-dd_HHmm'); $HOJE = (Get-Date).ToString('yyyy-MM-dd')
$LOG = Join-Path $RAIZ "logs\c11_inea_$STAMP.log"
$SEMLEITURA = ($env:RADAR_SEM_DOWNLOAD -eq '1')
$PAG = 'https://dadosabertos.rj.gov.br/dataset/fiscalizacao-e-combate-as-infracoes-ambientais'
$ARQS = @(
  @{ id = 'penalidades'; nome = 'INEA - penalidades aplicadas'; arq = 'penalidades_aplicadas.xlsx'
     url = 'https://dadosabertos.rj.gov.br/dataset/0f650197-c519-44fb-b87d-44d59eeefbb0/resource/11b4744f-593b-47e6-a09f-a6c2fa64f230/download/penalidades_aplicadas.xlsx' },
  @{ id = 'acoes_fiscalizacao'; nome = 'INEA - acoes de fiscalizacao'; arq = 'acoes-de-fiscalizacao.xlsx'
     url = 'https://dadosabertos.rj.gov.br/dataset/0f650197-c519-44fb-b87d-44d59eeefbb0/resource/dd261fea-4fc0-4d39-80d0-189447862374/download/acoes-de-fiscalizacao.xlsx' }
)
$ini0 = Get-Date; $TOTET = $ARQS.Count * 2 + 1; $etapa = 0
Write-Host "== INEA: PENALIDADES E ACOES DE FISCALIZACAO ==`ncoleta $HOJE`n"
Carregar-Municipios
$interno = New-Object System.Collections.ArrayList; $resumo = @()
function Achar($cab, [string[]]$pad, $usados = @()) { foreach ($q in $pad) { for ($j = 0; $j -lt $cab.Count; $j++) { if ($usados -notcontains $j -and $cab[$j] -match $q) { return $j } } }; return -1 }
foreach ($A in $ARQS) {
  $etapa++; Cabecalho-Etapa $etapa $TOTET "Download: $($A.nome)" $ini0
  $dest = Join-Path $BASE $A.arq
  $st = if ($SEMLEITURA) { if (Test-Path $dest) { 'RESERVA' } else { $null } } else { Baixar-Arquivo $A.url $dest }
  $etapa++; Cabecalho-Etapa $etapa $TOTET "Lendo: $($A.nome)" $ini0
  if (-not $st) { $resumo += "$($A.nome): SEM DADOS (download falhou e nao ha copia local). Baixe a mao em $PAG e ponha em $BASE"; continue }
  try { $abas = Ler-Xlsx $dest } catch { $resumo += "$($A.nome): planilha ilegivel ($($_.Exception.Message))"; continue }
  $saida = New-Object System.Collections.ArrayList; $agregado = $true
  foreach ($aba in $abas) {
    $LIN_ABA = $aba.linhas; if (-not $LIN_ABA.Count) { continue }
    # cabecalho = primeira linha (entre as 15 primeiras) com 3 ou mais celulas preenchidas
    $hi = -1; for ($j = 0; $j -lt [math]::Min(15, $LIN_ABA.Count); $j++) { if (@($LIN_ABA[$j] | Where-Object { $_ }).Count -ge 3) { $hi = $j; break } }
    if ($hi -lt 0) { continue }
    $cab = @($LIN_ABA[$hi] | ForEach-Object { Norm-Txt $_ })
    for ($j = 0; $j -lt $cab.Count; $j++) { if (-not $cab[$j]) { $cab[$j] = "COL$($j + 1)" } }
    $iDoc = Achar $cab 'CNPJ', 'CPF', 'DOCUMENTO'; $iData = Achar $cab '^DATA', 'DATA', '^DT ', 'DT ', '^EMISSAO', 'EMISSAO' @($iDoc)
    $iMun = Achar $cab 'MUNICIPIO', 'CIDADE'; $iNome = Achar $cab 'RAZAO', 'AUTUADO', 'INFRATOR', 'EMPRESA', 'EMPREENDIMENTO', 'NOME'
    $iVal = Achar $cab 'VALOR', 'MULTA'; $iTipo = Achar $cab '^TIPO', 'PENALIDADE', 'SANCAO', 'INFRACAO', 'TIPO' @($iData, $iDoc, $iVal); $iProc = Achar $cab 'PROCESSO'; $iNum = Achar $cab '^AUTO', 'N AUTO', 'NUMERO', '^N ' @($iProc)
    # sem coluna de documento no cabecalho? procura CNPJ valido nos valores
    if ($iDoc -lt 0) { for ($j = 0; $j -lt $cab.Count -and $iDoc -lt 0; $j++) { $ok = 0; $tt = 0
        for ($r = $hi + 1; $r -lt [math]::Min($LIN_ABA.Count, $hi + 60); $r++) { $v = ([string]$LIN_ABA[$r][$j]) -replace '\D', ''; if ($v) { $tt++; if ($v.Length -eq 14 -and (Cnpj-Ok $v)) { $ok++ } } }
        if ($tt -ge 5 -and $ok / $tt -ge 0.3) { $iDoc = $j } } }
    Add-Content $LOG "$($A.id) aba '$($aba.nome)': cabecalho na linha $($hi + 1): $($cab -join ' | ')"
    Add-Content $LOG "   colunas usadas: doc=$iDoc data=$iData municipio=$iMun nome=$iNome valor=$iVal tipo=$iTipo processo=$iProc numero=$iNum"
    if ($iDoc -ge 0) { $agregado = $false }
    for ($r = $hi + 1; $r -lt $LIN_ABA.Count; $r++) {
      $lin = $LIN_ABA[$r]; if (-not @($lin | Where-Object { $_ }).Count) { continue }
      $doc = if ($iDoc -ge 0) { ([string]$lin[$iDoc]) -replace '\D', '' } else { '' }
      $dt = if ($iData -ge 0) { Data-Excel $lin[$iData] } else { $null }
      $o = [ordered]@{ aba = $aba.nome; data_documento = $(if ($dt) { $dt.ToString('yyyy-MM-dd') } else { '' })
        tipo_pessoa = $(if ($doc.Length -eq 14) { 'PJ' } elseif ($doc.Length -eq 11) { 'PF' } else { '' }); cpf_cnpj = (Mascara-Doc $doc)
        cnpj_dv_ok = $(if ($doc.Length -eq 14) { if (Cnpj-Ok $doc) { 'SIM' } else { 'NAO' } } else { '' })
        nome = $(if ($iNome -ge 0) { Mascara-Texto $lin[$iNome] } else { '' }); municipio_normalizado = $(if ($iMun -ge 0) { Muni-Nome '' $lin[$iMun] } else { '' })
        valor_indicado_RS_NAO_E_DANO = $(if ($iVal -ge 0) { ('{0:0.00}' -f (Num-Br $lin[$iVal])).Replace(',', '.') } else { '' })
        penalidade = $(if ($iTipo -ge 0) { $lin[$iTipo] } else { '' }); processo = $(if ($iProc -ge 0) { $lin[$iProc] } else { '' }); numero = $(if ($iNum -ge 0) { $lin[$iNum] } else { '' })
        valido = 'SIM' }
      for ($j = 0; $j -lt $cab.Count; $j++) { $c = $cab[$j]; $v = [string]$lin[$j]; if ($c -match 'CPF|CNPJ|DOCUMENTO') { $o["orig_$c"] = Mascara-Doc $v } else { if ($j -eq $iData -and $dt) { $o["orig_$c"] = $dt.ToString('yyyy-MM-dd') } else { $o["orig_$c"] = Mascara-Texto $v } } }
      $o['fonte'] = "INEA via dadosabertos.rj.gov.br - $($A.arq)"; $o['link'] = $PAG; $o['data_coleta'] = $HOJE; $o['copia'] = $st
      $o['classificacao'] = $(if ($A.id -eq 'penalidades') { 'FATO: penalidade registrada pelo INEA em dados abertos. Ver se cabe recurso; NAO afirmar condenacao definitiva' } else { 'FATO: acao de fiscalizacao do INEA (dados abertos)' })
      [void]$saida.Add([pscustomobject]$o)
      if ($doc.Length -eq 11) { [void]$interno.Add([pscustomobject][ordered]@{ origem = "INEA $($A.id)"; data = $o.data_documento; nome = $(if ($iNome -ge 0) { $lin[$iNome] } else { '' }); cpf = $doc }) }
    }
  }
  # colunas variam por aba: une todas
  $todasCols = @(); foreach ($x in $saida) { foreach ($p in $x.psobject.Properties.Name) { if ($todasCols -notcontains $p) { $todasCols += $p } } }
  # coluna de 'documento' sem nenhum CNPJ valido (ex.: ORIGEM DOCUMENTO) = planilha sem empresa
  if (-not @($saida | Where-Object { $_.cnpj_dv_ok -eq 'SIM' }).Count) { $agregado = $true }
  $sfx = if ($agregado) { 'AGREGADO_' } else { '' }
  $fSaida = Join-Path $ACH "inea_$($A.id)_${sfx}RJ_$STAMP.csv"
  $saida | Select-Object $todasCols | Export-Csv $fSaida -Delimiter ';' -NoTypeInformation -Encoding UTF8
  $pj = @($saida | Where-Object { $_.cnpj_dv_ok -eq 'SIM' }); $u = @($pj | ForEach-Object cpf_cnpj | Sort-Object -Unique)
  $resumo += ('{0}: {1} linhas em {2} aba(s) | {3} com CNPJ valido ({4} empresas) | {5} | copia {6}' -f $A.nome, $saida.Count, @($abas).Count, $pj.Count, $u.Count, $(if ($agregado) { 'SO TOTAIS (sem CNPJ): serve para estatistica' } else { 'por empresa' }), $st)
  $resumo += "   -> $fSaida"
}
$etapa++; Cabecalho-Etapa $etapa $TOTET 'Gravando interno e conferindo CPF' $ini0
if ($interno.Count) { $interno | Export-Csv (Join-Path $INT "INTERNO_inea_PF_RJ_$STAMP.csv") -Delimiter ';' -NoTypeInformation -Encoding UTF8 }
$vaz = 0; foreach ($arq in (Get-ChildItem $ACH -Filter "inea_*_$STAMP.csv")) { foreach ($m in [regex]::Matches((Get-Content $arq.FullName -Raw -Encoding UTF8) + '', '(?<![\d/])\d{3}\.?\d{3}\.?\d{3}-?\d{2}(?![\d/])')) { if (Cpf-Ok $m.Value) { $vaz++ } } }
Write-Host "`n================ RESUMO ================"; $resumo | ForEach-Object { Write-Host $_ }
if ($vaz) { Write-Host "ATENCAO: $vaz possiveis CPFs. NAO publicar antes de conferir." -ForegroundColor Red } else { Write-Host 'Conferencia de CPF: OK (zero).' -ForegroundColor Green }
Write-Host "Colunas detectadas: $LOG`nTempo total: $(Fmt ((Get-Date) - $ini0).TotalSeconds)"
Som
