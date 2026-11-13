# [10] LEADS: pontuacao + fila de prospeccao (planilha, pagina de WhatsApp e arquivos da area restrita)  -  v5
# Junta, por CNPJ: autos validos (12m), embargos vigentes, notificacoes e suspensoes (12m) + cadastro da Receita ([9]).
# Pontua de 0 a 100 e explica o motivo de cada ponto. Nada aqui e acusacao: e prioridade comercial.
# Regras: so PJ com DV ok; situacao na Receita diferente de ATIVA = descartar; orgao publico = fora do perfil;
#         MEI/empresario individual COM contato (pedido do usuario em 06/11/2026), CPF do nome mascarado; lista "nao contatar" respeitada; valor de auto NAO e dano.
# Arquivos editaveis em 05-Interno: excluir_cnpj.txt, contatos_status.csv, modelo_mensagem.txt
. "$PSScriptRoot\comum.ps1"
$ACH = Join-Path $RAIZ '04-Achados'; $INT = Join-Path $RAIZ '05-Interno'; $PRO = Join-Path $ACH 'prospeccao'; $SITE = Join-Path $PRO 'para-o-site'
New-Item -ItemType Directory -Force $PRO, $SITE, $INT | Out-Null
$STAMP = (Get-Date).ToString('yyyy-MM-dd_HHmm'); $HOJE = (Get-Date).ToString('yyyy-MM-dd'); $HOJED = (Get-Date).Date; $DESDE = $HOJED.AddDays(-365)
$ini0 = Get-Date; $TOTET = 5
Write-Host "== LEADS: PONTUACAO E FILA DE PROSPECCAO ==`n"

# ---------- arquivos editaveis ----------
$MODELO = Join-Path $INT 'modelo_mensagem.txt'
if (-not (Test-Path $MODELO)) {
  @('# Modelo da mensagem de prospecção (Origem Consultoria Ambiental). Linhas com # são ignoradas.',
    '# Campos: {EMPRESA} {ORGAO} {DOCUMENTO} {MUNICIPIO} {MES}. {P} = novo parágrafo, {L} = quebra de linha (só no WhatsApp; na planilha vira espaço).',
    'À {EMPRESA}{P}',
    'Prezados(as) Senhores(as),{P}',
    'A Origem Consultoria Ambiental é uma empresa de engenharia e consultoria ambiental registrada no CREA-RJ, com atuação em todo o Estado do Rio de Janeiro.{P}',
    'Em consulta a dados públicos {ORGAO}, identificamos {DOCUMENTO} em nome de sua empresa, no município de {MUNICIPIO} (referência: {MES}).{P}',
    'Prestamos assessoria técnica a empresas nessa situação, que compreende: análise técnica do caso e dos prazos administrativos; elaboração de laudos e pareceres técnicos; Projeto de Recuperação de Área Degradada (PRAD); e regularização e licenciamento ambiental.{P}',
    'Caso seja de interesse, teremos satisfação em agendar uma breve reunião de apresentação, sem compromisso, para avaliar a situação e indicar os caminhos técnicos possíveis.{P}',
    'Atenciosamente,{L}Origem Consultoria Ambiental{L}https://ambientalcosta.netlify.app{P}',
    'Caso não deseje receber novos contatos, basta responder SAIR.') | Set-Content $MODELO -Encoding UTF8
}
$STATUS = Join-Path $INT 'contatos_status.csv'
if (-not (Test-Path $STATUS)) { 'cnpj;status;data;obs' | Set-Content $STATUS -Encoding UTF8
  '# status possiveis: CONTATADO, RESPONDEU, REUNIAO, PROPOSTA, CLIENTE, SEM INTERESSE, NAO CONTATAR' | Add-Content $STATUS -Encoding UTF8 }
$ARQ_EXCL = Join-Path $INT 'excluir_cnpj.txt'
$excl = @(); if (Test-Path $ARQ_EXCL) { $excl = @(Get-Content $ARQ_EXCL -Encoding UTF8 | ForEach-Object { ($_ -replace '#.*$', '') -replace '\D', '' } | Where-Object { $_.Length -ge 8 }) }
function Excluido($c) { foreach ($e in $excl) { if ($c.StartsWith($e)) { return $true } }; return $false }
$textoModelo = (Get-Content $MODELO -Encoding UTF8 | Where-Object { $_ -notmatch '^\s*#' }) -join ' '
$stat = @{}; Get-Content $STATUS -Encoding UTF8 | Select-Object -Skip 1 | Where-Object { $_ -and $_ -notmatch '^#' } | ForEach-Object {
  $p = $_ -split ';'; $d = $p[0] -replace '\D', ''; if ($d.Length -eq 14) { $stat[$d] = [pscustomobject]@{ status = ([string]$p[1]).Trim().ToUpper(); data = $p[2]; obs = $p[3] } } }

# ---------- 1. carregar ----------
Cabecalho-Etapa 1 $TOTET 'Carregando coletas e cadastro' $ini0
function Carregar($filtro, $rot) {
  $a = Ultimo-Arquivo $ACH $filtro
  if (-not $a) { Write-Host ("   {0,-22} sem arquivo" -f $rot) -ForegroundColor DarkYellow; return @() }
  $l = @(Import-Csv $a.FullName -Delimiter ';' -Encoding UTF8); Write-Host ("   {0,-22} {1,6} linhas | {2}" -f $rot, $l.Count, $a.Name); return $l
}
$autos = Carregar 'ibama_autos_RJ_*.csv' 'autos validos'
$embs = Carregar 'ibama_embargos_VIGENTES_RJ_*.csv' 'embargos vigentes'
$nots = @(Carregar 'ibama_notificacoes_RJ_*.csv' 'notificacoes' | Where-Object { $_.valido -eq 'SIM' })
$suss = @(Carregar 'ibama_suspensoes_RJ_*.csv' 'suspensoes' | Where-Object { $_.valido -eq 'SIM' })
$dems = @(Carregar 'ibama_demolicoes_RJ_*.csv' 'demolicoes' | Where-Object { $_.valido -eq 'SIM' })
$aprs = @(Carregar 'ibama_apreensoes_RJ_*.csv' 'apreensoes' | Where-Object { $_.valido -eq 'SIM' })
$acis = @(Carregar 'ibama_acidentes_RJ_*.csv' 'acidentes (SIEMA)' | Where-Object { $_.valido -eq 'SIM' })
$lics = @()  # SISLIC retirado em 06/11/2026: a fonte nao tem UF nem CNPJ
$ineas = @(Carregar 'inea_penalidades_RJ_*.csv' 'INEA penalidades')
$emps = Carregar 'empresas_enriquecidas_RJ_*.csv' 'cadastro (Receita)'
if (-not $emps.Count) { Write-Host 'Sem cadastro da Receita. Rode antes a [9] (enriquecer CNPJs).' -ForegroundColor Red; Som; return }
$ant = Ultimo-Arquivo $PRO 'LEADS_RJ_*.csv'; $antes = @{}
if ($ant) { Import-Csv $ant.FullName -Delimiter ';' -Encoding UTF8 | ForEach-Object { $antes[($_.cnpj -replace '\D', '')] = 1 } }

# ---------- 2. agrupar por CNPJ ----------
Cabecalho-Etapa 2 $TOTET 'Agrupando documentos por CNPJ' $ini0
$GRP = @{}
function DataOu($d) { if ([string]$d -match '^\d{4}-\d{2}-\d{2}') { return ([string]$d).Substring(0, 10) }; return '(sem data na fonte)' }
function Grupo($doc) { $d = ([string]$doc) -replace '\D', ''; if ($d.Length -ne 14 -or -not (Cnpj-Ok $d)) { return $null }
  if (-not $GRP.ContainsKey($d)) { $GRP[$d] = @{ autos = @(); embs = @(); nots = @(); suss = @(); dems = @(); aprs = @(); acis = @(); lics = @(); ineas = @() } }; return $GRP[$d] }
foreach ($x in $autos) { if ($x.tipo_pessoa -ne 'PJ') { continue }; $g = Grupo $x.cpf_cnpj; if ($g) { $g.autos += $x } }
foreach ($x in $embs) { $g = Grupo $x.CPF_CNPJ_EMBARGADO; if ($g) { $g.embs += $x } }
foreach ($x in $nots) { $g = Grupo $x.cpf_cnpj; if ($g) { $g.nots += $x } }
foreach ($x in $suss) { $g = Grupo $x.cpf_cnpj; if ($g) { $g.suss += $x } }
foreach ($x in $dems) { $g = Grupo $x.cpf_cnpj; if ($g) { $g.dems += $x } }
foreach ($x in $aprs) { $g = Grupo $x.cpf_cnpj; if ($g) { $g.aprs += $x } }
foreach ($x in $acis) { $g = Grupo $x.cpf_cnpj; if ($g) { $g.acis += $x } }
foreach ($x in $lics) { $g = Grupo $x.cpf_cnpj; if ($g) { $g.lics += $x } }
foreach ($x in $ineas) { $g = Grupo $x.cpf_cnpj; if ($g) { $g.ineas += $x } }
$CAD = @{}; foreach ($e in $emps) { $CAD[($e.cnpj -replace '\D', '')] = $e }
# v5.2 (07/11/2026): contatos publicados no site da propria empresa (opcao [15], c13)
$CONTSITE = @{}; foreach ($x in (Carregar 'contatos_sites_RJ_*.csv' 'contatos dos sites')) { if ($x.site) { $CONTSITE[($x.cnpj -replace '\D', '')] = $x } }

# ---------- 3. pontuar ----------
Cabecalho-Etapa 3 $TOTET "Pontuando $($GRP.Count) empresas" $ini0
function Mes($d) { if ($d) { $dt = Ler-Data $d; if ($dt) { return $dt.ToString('MM/yyyy') } }; '' }
function Fones($t) { @(([string]$t -split '/') | ForEach-Object { $_ -replace '\D', '' } | Where-Object { $_.Length -ge 10 -and ($_ -replace '0', '') }) }
function Fmt-Fone($n) { if ($n.Length -eq 11) { '({0}) {1}-{2}' -f $n.Substring(0, 2), $n.Substring(2, 5), $n.Substring(7) } else { '({0}) {1}-{2}' -f $n.Substring(0, 2), $n.Substring(2, 4), $n.Substring(6) } }
$leads = foreach ($d in $GRP.Keys) {
  $g = $GRP[$d]; $e = $CAD[$d]; $pts = 0; $mot = @()
  # recencia do documento mais recente
  $datas = @(@($g.autos | ForEach-Object { $_.data_auto }) + @($g.embs | ForEach-Object { $_.data_embargo }) + @($g.nots + $g.suss + $g.dems + $g.aprs + $g.acis + $g.ineas | ForEach-Object { $_.data_documento }) | Where-Object { $_ } | Sort-Object -Descending)
  $ult = if ($datas.Count) { Ler-Data $datas[0] } else { $null }; $dias = if ($ult) { [int]($HOJED - $ult.Date).TotalDays } else { 99999 }
  if ($dias -le 30) { $pts += 25; $mot += "documento ha $dias dias (+25)" } elseif ($dias -le 90) { $pts += 18; $mot += "documento ha $dias dias (+18)" } elseif ($dias -le 180) { $pts += 10; $mot += "documento ha $dias dias (+10)" } elseif ($dias -le 365) { $pts += 5; $mot += "documento ha $dias dias (+5)" }
  $ab = @($g.autos | Where-Object { $_.prazo_defesa_status -eq 'ABERTO (estimado)' }); $rec = @($g.autos | Where-Object { $_.prazo_defesa_status -like 'SEM CIENCIA REGISTRADA - auto recente*' })
  if ($ab.Count) { $pts += 15; $mot += 'prazo de defesa provavelmente aberto (+15)' } elseif ($rec.Count) { $pts += 8; $mot += 'auto recente sem ciencia registrada (+8)' }
  $e12 = @($g.embs | Where-Object { $_.ultimos_12m -eq 'SIM' })
  if ($e12.Count) { $pts += 20; $mot += 'embargo vigente lavrado nos ultimos 12 meses (+20)' } elseif ($g.embs.Count) { $pts += 8; $mot += "embargo vigente antigo, sem desembargo registrado (+8)" }
  if ($g.suss.Count) { $pts += 15; $mot += 'termo de suspensao nos ultimos 12 meses (+15)' }
  if ($g.nots.Count) { $pts += 8; $mot += 'notificacao do IBAMA nos ultimos 12 meses (+8)' }
  if ($g.dems.Count) { $pts += 15; $mot += 'termo de demolicao do IBAMA (+15)' }
  if ($g.aprs.Count) { $pts += 10; $mot += 'termo de apreensao nos ultimos 12 meses (+10)' }
  if ($g.acis.Count) { $pts += 10; $mot += 'acidente ambiental comunicado (SIEMA) em 24 meses (+10)' }
  $i12 = @($g.ineas | Where-Object { $_.data_documento -and $_.data_documento -ge $DESDE.ToString('yyyy-MM-dd') })
  if ($i12.Count) { $pts += 15; $mot += 'penalidade do INEA nos ultimos 12 meses (+15)' } elseif ($g.ineas.Count) { $pts += 5; $mot += 'penalidade do INEA mais antiga (+5)' }
  if ($g.lics.Count) { $pts += 3; $mot += 'tem licenca federal (condicionantes a cumprir) (+3)' }
  $ndoc = $g.autos.Count + $g.embs.Count + $g.nots.Count + $g.suss.Count + $g.dems.Count + $g.aprs.Count + $g.acis.Count + $g.ineas.Count
  if ($ndoc -ge 4) { $pts += 10; $mot += "$ndoc documentos (+10)" } elseif ($ndoc -ge 2) { $pts += 5; $mot += "$ndoc documentos (+5)" }
  $val = 0.0; foreach ($a in $g.autos) { $val += Num-Br $a.valor_auto_RS_nao_e_dano }
  if ($val -ge 1000000) { $pts += 15; $mot += 'valor indicado nos autos >= R$ 1 mi (+15)' } elseif ($val -ge 100000) { $pts += 10; $mot += 'valor indicado >= R$ 100 mil (+10)' } elseif ($val -ge 10000) { $pts += 5; $mot += 'valor indicado >= R$ 10 mil (+5)' } elseif ($val -gt 0) { $pts += 2; $mot += 'valor indicado < R$ 10 mil (+2)' }
  $porte = if ($e) { ([string]$e.porte).ToUpper() } else { '' }
  if ($porte -match 'DEMAIS') { $pts += 5; $mot += 'porte medio/grande (+5)' } elseif ($porte -match 'PEQUENO|EPP') { $pts += 4; $mot += 'empresa de pequeno porte (+4)' } elseif ($porte -match 'MICRO|ME\b') { $pts += 2; $mot += 'microempresa (+2)' }
  $tels = @(); if ($e) { $tels = @(Fones $e.telefone) }; $mail = if ($e -and $e.email -match '@') { $e.email } else { '' }
  $cSite = $CONTSITE[$d]; $telsSite = @(); $waSite = @(); $mailSite = ''
  if ($cSite) { $telsSite = @(Fones $cSite.telefones_site); $waSite = @(Fones $cSite.whatsapp_site); $mailSite = (([string]$cSite.emails_site) -split ' / ')[0] }
  if ($tels.Count -or $mail -or $telsSite.Count -or $waSite.Count -or $mailSite) { $pts += 5; $mot += 'tem contato cadastral (+5)' }
  $pts = [math]::Min(100, $pts)
  # classificacao
  $sit = if ($e) { [string]$e.situacao_receita } else { '' }; $alerta = if ($e) { [string]$e.alerta } else { 'SEM CADASTRO - rodar [9]' }
  $s0 = $stat[$d]
  $pri = if ($pts -ge 55) { 'A' } elseif ($pts -ge 35) { 'B' } else { 'C' }
  if (Excluido $d) { $pri = 'X - lista de exclusao' }
  elseif ($s0 -and $s0.status -match 'NAO CONTATAR|SEM INTERESSE|CLIENTE') { $pri = "X - $($s0.status)" }
  elseif (-not $e -or $e.razao_social -eq 'NAO ENCONTRADO NA RECEITA') { $pri = 'X - sem cadastro na Receita' }
  elseif ($sit -and $sit -notmatch '(?i)^ativa') { $pri = "X - situacao $($sit.ToUpper())" }
  elseif ($alerta -match 'ORGAO/ENTE PUBLICO') { $pri = 'X - orgao publico' }
  if ($pri.Length -eq 1 -and $alerta -match 'NOME NO DOCUMENTO') { $pri += ' (conferir nome)' }
  # documento principal para a mensagem: suspensao > embargo recente > auto > embargo antigo > notificacao
  $docMsg = ''; $dataMsg = ''; $muniMsg = ''
  $orgMsg = 'do IBAMA'
  if ($g.suss.Count) { $x = $g.suss | Sort-Object data_documento -Descending | Select-Object -First 1; $docMsg = 'um termo de suspensão'; $dataMsg = $x.data_documento; $muniMsg = $x.municipio_normalizado }
  elseif ($g.dems.Count) { $x = $g.dems | Sort-Object data_documento -Descending | Select-Object -First 1; $docMsg = 'um termo de demolição'; $dataMsg = $x.data_documento; $muniMsg = $x.municipio_normalizado }
  elseif ($i12.Count) { $x = $i12 | Sort-Object data_documento -Descending | Select-Object -First 1; $docMsg = 'uma penalidade ambiental'; $orgMsg = 'do INEA'; $dataMsg = $x.data_documento; $muniMsg = $x.municipio_normalizado }
  elseif ($e12.Count) { $x = $e12 | Sort-Object data_embargo -Descending | Select-Object -First 1; $docMsg = 'um termo de embargo'; $dataMsg = $x.data_embargo; $muniMsg = $x.municipio_normalizado }
  elseif ($g.autos.Count) { $x = $g.autos | Sort-Object data_auto -Descending | Select-Object -First 1; $docMsg = 'um auto de infração'; $dataMsg = $x.data_auto; $muniMsg = $x.municipio }
  elseif ($g.embs.Count) { $x = $g.embs | Sort-Object data_embargo -Descending | Select-Object -First 1; $docMsg = 'um termo de embargo'; $dataMsg = $x.data_embargo; $muniMsg = $x.municipio_normalizado }
  elseif ($g.aprs.Count) { $x = $g.aprs | Sort-Object data_documento -Descending | Select-Object -First 1; $docMsg = 'um termo de apreensão'; $dataMsg = $x.data_documento; $muniMsg = $x.municipio_normalizado }
  elseif ($g.ineas.Count) { $x = $g.ineas | Sort-Object data_documento -Descending | Select-Object -First 1; $docMsg = 'uma penalidade ambiental'; $orgMsg = 'do INEA'; $dataMsg = $x.data_documento; $muniMsg = $x.municipio_normalizado }
  elseif ($g.nots.Count) { $x = $g.nots | Sort-Object data_documento -Descending | Select-Object -First 1; $docMsg = 'uma notificação'; $dataMsg = $x.data_documento; $muniMsg = $x.municipio_normalizado }
  elseif ($g.acis.Count) { $x = $g.acis | Sort-Object data_documento -Descending | Select-Object -First 1; $docMsg = 'um comunicado de acidente ambiental'; $dataMsg = $x.data_documento; $muniMsg = $x.municipio_normalizado }
  elseif ($g.lics.Count) { $x = $g.lics | Sort-Object data_documento -Descending | Select-Object -First 1; $docMsg = 'uma licença ambiental federal'; $dataMsg = $x.data_documento; $muniMsg = $x.municipio_normalizado }
  $nomeEmp = if ($e -and $e.nome_fantasia) { $e.nome_fantasia } elseif ($e) { $e.razao_social } else { '' }
  $nomeEmp = (([string]$nomeEmp) -replace '\s*\[CPF omitido\]', '' -replace '\d{3}\.?\d{3}\.?\d{3}-?\d{2}', '').Trim()   # MEI: nome sem o CPF na mensagem
  # [regex]::Replace com avaliador funciona no Windows PowerShell 5.1 (o -creplace com { } so existe no PowerShell 7)
  $muniTxt = [regex]::Replace((Get-Culture).TextInfo.ToTitleCase(([string]$muniMsg).ToLower()), ' (De|Da|Do|Dos|Das|E) ', [System.Text.RegularExpressions.MatchEvaluator] { param($m) ' ' + $m.Groups[1].Value.ToLower() + ' ' })
  $msg = $textoModelo.Replace('{ORGAO}', $orgMsg).Replace('{DOCUMENTO}', $docMsg).Replace('{EMPRESA}', $nomeEmp).Replace('{MUNICIPIO}', $muniTxt).Replace('{MES}', (Mes $dataMsg))
  $msg = Mascara-Texto $msg
  $msgWa = (($msg -replace '\{P\}\s*', "`n`n") -replace '\{L\}\s*', "`n").Trim()   # paragrafos so no WhatsApp
  $msg = ($msg.Replace('{P}', ' ').Replace('{L}', ' ') -replace '\s{2,}', ' ').Trim()
  $cel = @($tels | Where-Object { $_.Length -eq 11 -and $_[2] -eq '9' }); $celSite = @($telsSite | Where-Object { $_.Length -eq 11 -and $_[2] -eq '9' }); $wa = ''; $waTipo = ''
  if ($e) {
    if ($waSite.Count) { $wa = 'https://wa.me/55' + $waSite[0] + '?text=' + [uri]::EscapeDataString($msgWa); $waTipo = 'WhatsApp publicado no site da empresa' }
    elseif ($cel.Count) { $wa = 'https://wa.me/55' + $cel[0] + '?text=' + [uri]::EscapeDataString($msgWa); $waTipo = 'celular' }
    elseif ($celSite.Count) { $wa = 'https://wa.me/55' + $celSite[0] + '?text=' + [uri]::EscapeDataString($msgWa); $waTipo = 'celular publicado no site' }
    elseif ($tels.Count) { $wa = 'https://wa.me/55' + $tels[0] + '?text=' + [uri]::EscapeDataString($msgWa); $waTipo = 'fixo (pode nao ter WhatsApp Business)' }
  }
  $links = @(); if ($g.autos.Count) { $links += 'https://dadosabertos.ibama.gov.br/dataset/fiscalizacao-auto-de-infracao' }; if ($g.embs.Count) { $links += 'https://dadosabertos.ibama.gov.br/dataset/fiscalizacao-termo-de-embargo' }
  if ($g.dems.Count) { $links += 'https://dadosabertos.ibama.gov.br/dataset/fiscalizacao-termo-de-demolicao' }; if ($g.aprs.Count) { $links += 'https://dadosabertos.ibama.gov.br/dataset/fiscalizacao-termo-de-apreensao' }; if ($g.acis.Count) { $links += 'https://dadosabertos.ibama.gov.br/dataset/siema-comunicado-de-acidente-ambiental' }; if ($g.lics.Count) { $links += 'https://dadosabertos.ibama.gov.br/dataset/licencas-ambientais-de-atividades-e-empreendimentos-licenciados-pelo-ibama' }; if ($g.ineas.Count) { $links += 'https://dadosabertos.rj.gov.br/dataset/fiscalizacao-e-combate-as-infracoes-ambientais' }
  if ($g.nots.Count) { $links += 'https://dadosabertos.ibama.gov.br/dataset/fiscalizacao-notificacao' }; if ($g.suss.Count) { $links += 'https://dadosabertos.ibama.gov.br/dataset/fiscalizacao-termo-de-suspensao' }
  [pscustomobject][ordered]@{
    prioridade = $pri; pontos = $pts; novo_lead = $(if ($ant -and -not $antes.ContainsKey($d)) { 'NOVO' } else { '' })
    status_contato = $(if ($s0) { "$($s0.status) $($s0.data)".Trim() } else { '' })
    cnpj = (Cnpj-Fmt $d); razao_social = $(if ($e) { $e.razao_social } else { '' }); nome_fantasia = $(if ($e) { $e.nome_fantasia } else { '' })
    porte = $porte; atividade_principal = $(if ($e) { $e.atividade_principal } else { '' }); municipio_sede = $(if ($e) { $e.municipio_sede } else { '' })
    telefones = (@($tels | ForEach-Object { Fmt-Fone $_ }) -join ' / '); email = $mail; socios = $(if ($e) { $e.socios } else { '' }); whatsapp_tipo = $waTipo; whatsapp_link = $wa
    site = $(if ($cSite) { $cSite.site } else { '' }); site_confirmacao = $(if ($cSite) { $cSite.site_confirmacao } else { '' })
    emails_site = $(if ($cSite) { $cSite.emails_site } else { '' }); telefones_site = (@($telsSite | ForEach-Object { Fmt-Fone $_ }) -join ' / '); whatsapp_site = (@($waSite | ForEach-Object { Fmt-Fone $_ }) -join ' / ')
    redes_sociais = $(if ($cSite) { $cSite.redes_sociais } else { '' }); fonte_contato_site = $(if ($cSite) { "$($cSite.fonte_paginas) (lido em $($cSite.site_busca_em))" } else { '' })
    mensagem_sugerida = $msg
    ultimo_documento = $(if ($ult) { $ult.ToString('yyyy-MM-dd') } else { '' }); autos_validos_12m = $g.autos.Count
    prazo_defesa_aberto_ate = ((@($ab | ForEach-Object { $_.prazo_defesa_fim_estimado }) | Sort-Object -Descending | Select-Object -First 1))
    embargos_vigentes = $g.embs.Count; embargos_12m = $e12.Count; notificacoes_12m = $g.nots.Count; suspensoes_12m = $g.suss.Count; demolicoes = $g.dems.Count; apreensoes_12m = $g.aprs.Count; acidentes_24m = $g.acis.Count; inea_penalidades = $g.ineas.Count; inea_penalidades_12m = $i12.Count; licencas_federais = $g.lics.Count
    valor_indicado_autos_RS_NAO_E_DANO = $val
    tipos_infracao = ((@($g.autos | ForEach-Object { $_.tipo_infracao }) + @($g.embs | ForEach-Object { $_.TIPO_AREA }) | Where-Object { $_ } | Sort-Object -Unique) -join '; ')
    municipios_documentos = ((@($g.autos | ForEach-Object { $_.municipio }) + @($g.embs + $g.nots + $g.suss + $g.dems + $g.aprs + $g.acis + $g.ineas | ForEach-Object { $_.municipio_normalizado }) | Where-Object { $_ } | Sort-Object -Unique) -join '; ')
    autos = ((@($g.autos | Sort-Object data_auto -Descending | ForEach-Object { "$($_.n_auto): lavrado $(DataOu $_.data_auto)$(if ($_.data_ciencia) { ", ciencia $($_.data_ciencia)" })$(if ($_.prazo_defesa_fim_estimado) { ", prazo de defesa estimado ate $($_.prazo_defesa_fim_estimado) ($($_.prazo_defesa_status))" }); proc. $($_.processo)" })) -join ' | ')
    outros_documentos_datas = ((@(
      @($g.nots | ForEach-Object { "Notificacao IBAMA $(DataOu $_.data_documento)" }) + @($g.suss | ForEach-Object { "Termo de suspensao IBAMA $(DataOu $_.data_documento)" }) +
      @($g.dems | ForEach-Object { "Termo de demolicao IBAMA $(DataOu $_.data_documento)" }) + @($g.aprs | ForEach-Object { "Termo de apreensao IBAMA $(DataOu $_.data_documento)" }) +
      @($g.acis | ForEach-Object { "Acidente SIEMA $(DataOu $_.data_documento)" }) + @($g.ineas | ForEach-Object { "Penalidade INEA $(DataOu $_.data_documento)$(if ($_.penalidade) { " ($($_.penalidade))" })" }) +
      @($g.lics | ForEach-Object { "Licenca federal $(DataOu $_.data_documento)" }))) -join ' | ')
    embargos = ((@($g.embs | Sort-Object data_embargo -Descending | ForEach-Object { "$($_.NUM_TAD): lavrado $(DataOu $_.data_embargo)" })) -join ' | ')
    motivos_pontuacao = ($mot -join '; '); alerta_cadastro = $alerta; fontes = ($links -join ' ')
    data_coleta = $HOJE
    classificacao = 'Prioridade comercial a partir de FATOS publicos (IBAMA, INEA e Receita). Nao e acusacao nem condenacao; valor indicado no auto nao e dano; prazo e estimado'
  }
}
$leads = @($leads | Sort-Object @{ e = { $_.prioridade.Substring(0, 1) } }, @{ e = { $_.pontos }; Descending = $true })

# ---------- 4. gravar planilha e pagina ----------
Cabecalho-Etapa 4 $TOTET 'Gravando planilha e pagina de WhatsApp' $ini0
$fL = Join-Path $PRO "LEADS_RJ_$STAMP.csv"; $leads | Export-Csv $fL -Delimiter ';' -NoTypeInformation -Encoding UTF8
function HtmlTxt($t) { [Net.WebUtility]::HtmlEncode([string]$t) }
$fila = @($leads | Where-Object { $_.prioridade -match '^[AB]' })
$cards = foreach ($l in $fila) {
  $id = $l.cnpj -replace '\D', ''
  $bt = @()
  if ($l.whatsapp_link) { $bt += "<a class='b wa' href='$(HtmlTxt $l.whatsapp_link)' target='_blank' rel='noopener'>WhatsApp ($(HtmlTxt $l.whatsapp_tipo))</a>" }
  $mailBt = if ($l.email) { $l.email } elseif ($l.emails_site) { (([string]$l.emails_site) -split ' / ')[0] } else { '' }
  if ($mailBt) { $bt += "<a class='b' href='mailto:$(HtmlTxt $mailBt)?subject=$([uri]::EscapeDataString('Apoio técnico ambiental'))&body=$([uri]::EscapeDataString($l.mensagem_sugerida))'>E-mail</a>" }
  $bt += "<button class='b' onclick='copiar(this)' data-m='$(HtmlTxt $l.mensagem_sugerida)'>Copiar mensagem</button>"
  @"
<div class='card' data-id='$id' data-p='$(HtmlTxt $l.prioridade.Substring(0,1))'>
 <div class='top'><span class='pri p$(HtmlTxt $l.prioridade.Substring(0,1))'>$(HtmlTxt $l.prioridade)</span><span class='pts'>$($l.pontos) pts</span>$(if ($l.novo_lead) { "<span class='novo'>NOVO</span>" })$(if ($l.status_contato) { "<span class='st'>$(HtmlTxt $l.status_contato)</span>" })
 <label class='ok'><input type='checkbox' onchange='marca(this)'> contatado</label></div>
 <h3>$(HtmlTxt $l.razao_social)</h3><div class='sub'>$(HtmlTxt ((@($l.cnpj, $l.nome_fantasia, $l.porte, $(if ($l.municipio_sede) { 'sede ' + $l.municipio_sede })) | Where-Object { $_ }) -join ' · '))</div>
 <div class='sub'>$(HtmlTxt $l.atividade_principal)</div>
 <div class='fx'>Último documento: <b>$(HtmlTxt $l.ultimo_documento)</b> · autos válidos 12m: $($l.autos_validos_12m) · embargos vigentes: $($l.embargos_vigentes) · notificações: $($l.notificacoes_12m) · suspensões: $($l.suspensoes_12m) · demolições: $($l.demolicoes) · apreensões: $($l.apreensoes_12m) · acidentes: $($l.acidentes_24m) · INEA: $($l.inea_penalidades)$(if ($l.prazo_defesa_aberto_ate) { " · <b>prazo de defesa estimado até $(HtmlTxt $l.prazo_defesa_aberto_ate)</b>" })</div>
 $(if ($l.autos) { "<div class='fx'><b>Autos (datas):</b> $(HtmlTxt $l.autos)</div>" })
 $(if ($l.embargos) { "<div class='fx'><b>Embargos (datas):</b> $(HtmlTxt $l.embargos)</div>" })
 $(if ($l.outros_documentos_datas) { "<div class='fx'><b>Outros documentos (datas):</b> $(HtmlTxt $l.outros_documentos_datas)</div>" })
 <div class='mot'>$(HtmlTxt $l.motivos_pontuacao)</div>
 $(if ($l.alerta_cadastro) { "<div class='al'>$(HtmlTxt $l.alerta_cadastro)</div>" })
 <div class='ct'>$(HtmlTxt $l.telefones) $(HtmlTxt $l.email)</div>
 $(if ($l.socios) { "<div class='ct'>Sócios: $(HtmlTxt $l.socios)</div>" })
 $(if ($l.site) { "<div class='ct'>Site: <a href='$(HtmlTxt $l.site)' target='_blank' rel='noopener'>$(HtmlTxt $l.site)</a> ($(HtmlTxt $l.site_confirmacao)) $(HtmlTxt $l.emails_site) $(HtmlTxt $l.telefones_site) $(if ($l.whatsapp_site) { 'WhatsApp ' + (HtmlTxt $l.whatsapp_site) }) $(HtmlTxt $l.redes_sociais)</div>" })
 <div class='bts'>$($bt -join ' ')</div>
</div>
"@
}
$html = @"
<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Fila de prospecção $HOJE</title>
<style>
:root{--bg:#f6f7f5;--fg:#1d2a22;--card:#fff;--mut:#5d6b62;--bd:#dfe5e0;--a:#1f7a4d;--al:#9a3b00}
@media (prefers-color-scheme:dark){:root{--bg:#121714;--fg:#e4ebe6;--card:#1b221e;--mut:#9aa8a0;--bd:#2c3631;--a:#4cc38a;--al:#ffb27a}}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.45 system-ui,Segoe UI,Arial,sans-serif}
header{padding:16px;max-width:980px;margin:auto}h1{font-size:20px;margin:0 0 4px}.nota{color:var(--mut);font-size:13px}
.ctl{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}.ctl button{padding:6px 10px;border:1px solid var(--bd);background:var(--card);color:var(--fg);border-radius:6px;cursor:pointer}
main{max-width:980px;margin:auto;padding:0 16px 40px}.card{background:var(--card);border:1px solid var(--bd);border-radius:10px;padding:12px 14px;margin:10px 0}
.card.feito{opacity:.45}.top{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.pri{font-weight:700;padding:2px 8px;border-radius:6px;background:var(--a);color:#fff}.pB{background:#6b7f2a}
.pts{color:var(--mut)}.novo{background:#c0392b;color:#fff;border-radius:6px;padding:1px 6px;font-size:12px}.st{border:1px solid var(--bd);border-radius:6px;padding:1px 6px;font-size:12px}
.ok{margin-left:auto;font-size:13px}h3{margin:6px 0 2px;font-size:16px}.sub,.mot,.ct{color:var(--mut);font-size:13px}.fx{margin:6px 0;font-size:14px}.al{color:var(--al);font-size:13px;margin:4px 0}
.bts{margin-top:8px;display:flex;gap:8px;flex-wrap:wrap}.b{display:inline-block;padding:7px 12px;border-radius:8px;border:1px solid var(--bd);background:var(--card);color:var(--fg);text-decoration:none;cursor:pointer;font:inherit}.wa{background:#25d366;color:#08311a;border-color:#25d366;font-weight:600}
</style></head><body><header><h1>Fila de prospecção · $HOJE</h1>
<div class='nota'>USO INTERNO, NÃO PUBLICAR. $($fila.Count) empresas com prioridade A ou B (de $($leads.Count) analisadas). Fonte: IBAMA Dados Abertos (autos, embargos, notificações, suspensões, demolições, apreensões, acidentes SIEMA, licenças) e INEA (dados abertos do Estado), mais a base pública do CNPJ. Auto, embargo ou notificação NÃO é condenação; valor do auto NÃO é dano; prazo é ESTIMADO (20 dias da ciência, Decreto 6.514/2008, art. 113). Respeite quem pedir para não receber mensagens: anote em 05-Interno\contatos_status.csv como NAO CONTATAR.</div>
<div class='ctl'><button onclick="filtra('')">Todos</button><button onclick="filtra('A')">Só A</button><button onclick="filtra('B')">Só B</button><button onclick='ocultaFeitos()'>Ocultar contatados</button></div></header>
<main>
$($cards -join "`n")
</main>
<script>
function k(id){return 'radar-contatado-'+id}
function marca(cb){var c=cb.closest('.card');try{localStorage.setItem(k(c.dataset.id),cb.checked?'1':'')}catch(e){}c.classList.toggle('feito',cb.checked)}
function copiar(b){var t=b.dataset.m;(navigator.clipboard?navigator.clipboard.writeText(t):Promise.reject()).then(function(){b.textContent='Copiado!'},function(){prompt('Copie a mensagem:',t)})}
function filtra(p){document.querySelectorAll('.card').forEach(function(c){c.style.display=(!p||c.dataset.p===p)?'':'none'})}
function ocultaFeitos(){document.querySelectorAll('.card.feito').forEach(function(c){c.style.display='none'})}
document.querySelectorAll('.card').forEach(function(c){var v='';try{v=localStorage.getItem(k(c.dataset.id))}catch(e){}if(v){c.classList.add('feito');c.querySelector('input').checked=true}})
</script></body></html>
"@
$fH = Join-Path $PRO "FILA_WHATSAPP_RJ_$STAMP.html"; [IO.File]::WriteAllText($fH, $html, (New-Object Text.UTF8Encoding($true)))

# ---------- 5. arquivos para a area restrita do site (formato do gerar_dados.py) ----------
Cabecalho-Etapa 5 $TOTET 'Gerando arquivos da area restrita do site' $ini0
$okSite = @{}; foreach ($l in $leads) { if ($l.prioridade -notmatch '^X') { $okSite[($l.cnpj -replace '\D', '')] = $l } }
$aS = foreach ($a in $autos) { $d = $a.cpf_cnpj -replace '\D', ''; if ($a.tipo_pessoa -ne 'PJ' -or -not $okSite.ContainsKey($d)) { continue }
  [pscustomobject][ordered]@{ data_coleta = $a.data_coleta; tipo_pessoa = 'PJ'; cpf_cnpj = $a.cpf_cnpj; n_auto = $a.n_auto; data_auto = $a.data_auto; municipio = $a.municipio; autuado = $a.autuado
    processo = $a.processo; valor_auto_RS = ('{0:0.00}' -f (Num-Br $a.valor_auto_RS_nao_e_dano)).Replace(',', '.'); tipo_infracao = $a.tipo_infracao; descricao = $a.descricao; gravidade = $a.gravidade
    cancelado = 'NAO'; situacao_formulario = $a.situacao } }
$cS = @{}; foreach ($a in @($aS)) { $cS[($a.cpf_cnpj -replace '\D', '')] = 1 }
$eS = foreach ($e in $emps) { $d = $e.cnpj -replace '\D', ''; if (-not $cS.ContainsKey($d)) { continue }; $l = $okSite[$d]
  [pscustomobject][ordered]@{ cnpj = $e.cnpj; razao_social = $e.razao_social; nome_fantasia = $e.nome_fantasia; situacao_receita = $e.situacao_receita; natureza_juridica = $e.natureza_juridica
    mei_ou_individual = $e.mei_ou_individual; atividade_principal = $e.atividade_principal; municipio_sede = $e.municipio_sede
    telefone = $(if ($e.telefone -match '^\d') { $e.telefone } else { '' }); email = $(if ($e.email -match '@') { $e.email } else { '' })
    alerta = (@($(if ($e.alerta -match 'NOME NO DOCUMENTO') { 'nome no auto difere da razão social' }), "prioridade $($l.prioridade) ($($l.pontos) pts)") | Where-Object { $_ }) -join ' | ' } }
$fAS = Join-Path $SITE 'autos_site.csv'; @($aS) | Export-Csv $fAS -Delimiter ';' -NoTypeInformation -Encoding UTF8
$fES = Join-Path $SITE 'empresas_site.csv'; @($eS) | Export-Csv $fES -Delimiter ';' -NoTypeInformation -Encoding UTF8

$vaz = 0; foreach ($arq in $fL, $fH, $fAS, $fES) { foreach ($m in [regex]::Matches((Get-Content $arq -Raw -Encoding UTF8) + '', '(?<![\d/])\d{3}\.?\d{3}\.?\d{3}-?\d{2}(?![\d/])')) { if (Cpf-Ok $m.Value) { $vaz++ } } }
Write-Host "`n================ RESUMO ================"
foreach ($p in 'A', 'B', 'C') { $q = @($leads | Where-Object { $_.prioridade -like "$p*" }); Write-Host ("Prioridade {0}: {1,4} | com WhatsApp/telefone: {2} | com e-mail: {3}" -f $p, $q.Count, @($q | Where-Object whatsapp_link).Count, @($q | Where-Object email).Count) }
Write-Host ("Descartados (X): {0}  -> {1}" -f @($leads | Where-Object { $_.prioridade -like 'X*' }).Count, ((@($leads | Where-Object { $_.prioridade -like 'X*' } | Group-Object prioridade | ForEach-Object { "$($_.Name): $($_.Count)" })) -join ' | '))
Write-Host "Leads NOVOS desde a ultima fila: $(@($leads | Where-Object novo_lead).Count)"
Write-Host "`nTOP 10:"; $leads | Where-Object { $_.prioridade -match '^[AB]' } | Select-Object -First 10 | ForEach-Object { Write-Host ("  {0,-3} {1,3} pts  {2}  {3}" -f $_.prioridade.Substring(0, 1), $_.pontos, $_.cnpj, $_.razao_social) }
if ($vaz) { Write-Host "ATENCAO: $vaz possiveis CPFs nos arquivos. NAO publicar antes de conferir." -ForegroundColor Red } else { Write-Host 'Conferencia de CPF: OK (zero).' -ForegroundColor Green }
Write-Host "`nPlanilha: $fL`nPagina (abra no navegador, clique para abrir o WhatsApp): $fH`nArea restrita do site: $SITE (use no gerar_dados.py)"
Write-Host "Anote o andamento em $STATUS (CONTATADO, RESPONDEU, CLIENTE, NAO CONTATAR...). Edite a mensagem em $MODELO."
Write-Host "Tempo total: $(Fmt ((Get-Date) - $ini0).TotalSeconds)"
Som
try { Start-Process $fH } catch {}
