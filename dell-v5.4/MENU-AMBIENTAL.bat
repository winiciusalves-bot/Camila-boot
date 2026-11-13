@echo off
chcp 65001 >nul
title RADAR AMBIENTAL - Gabinete
cd /d "%~dp0"
set "PS=powershell -NoProfile -ExecutionPolicy Bypass -File"
rem desbloqueia os scripts baixados (evita o aviso de seguranca a cada execucao)
powershell -NoProfile -Command "Get-ChildItem -LiteralPath '%~dp0scripts' -Recurse | Unblock-File" >nul 2>nul
rem v5.2 (09/11/2026): rotina automatica. "MENU-AMBIENTAL.bat AUTO" roda a fila sem perguntas e fecha sozinho.
if /I "%~1"=="AUTO" goto AUTO

:MENU
cls
echo ==============================================================
echo                 RADAR AMBIENTAL  -  Gabinete
echo   Multas, autos, licencas, TACs e embargos ambientais (RJ)
echo ==============================================================
echo.
echo   [1] Autos/multas/licencas nos Diarios Oficiais (CNPJ, 12 meses)
echo   [2] Canais de transparencia nos sites (92 prefeituras + INEA + IBAMA)
echo   [3] Conferir CNPJs na Receita (preenche razao social da coleta 1)
echo   [4] IBAMA: autos NOVOS + embargos + cruzamento (RJ, dados abertos)
echo   [5] DOU Secao 3: editais ambientais (INLABS + reserva base mensal)
echo   [6] Guardar login do INLABS (criptografado, so voce abre)  [7] Apagar login
echo   --- PROSPECCAO DE CLIENTES (v5) ---
echo   [8]  IBAMA: notificacoes, suspensoes, demolicoes, apreensoes, acidentes, licencas
echo   [9]  Enriquecer CNPJs na Receita (4 fontes: BrasilAPI, Minha Receita, CNPJ.ws, ReceitaWS)
echo   [10] LEADS: pontuacao + fila de WhatsApp + arquivos da area restrita
echo   [11] Sondar novas fontes (INEA, DOERJ, DO Rio, MPRJ, dados abertos, Querido Diario)
echo   --- BASE DE DADOS (v5.1) ---
echo   [12] BASE UNICA: junta todas as fontes, sem duplicatas, com historico (02-Base)
echo   [13] INEA: penalidades aplicadas + acoes de fiscalizacao (dados abertos RJ)
echo   [14] ENVIAR BASE AO SITE (Supabase; precisa de 05-Interno\supabase_secret.txt)
echo   [15] SITES DAS EMPRESAS: acha o site (confirmado no Registro.br) e traz os contatos
echo   --- DIARIOS MUNICIPAIS (v5.3) ---
echo   [16] DIARIOS que so abrem deste PC: acha a pagina do diario de 29 prefeituras e guarda copia
echo   --- INEA (v5.4) ---
echo   [17] DIARIO ELETRONICO DO INEA: notificacoes de fiscalizacao + licencas (desde a ultima leitura)
echo   [R]  ROTINA COMPLETA = 4 8 13 9 15 10 12
echo   [D] Desligar o computador (use no fim da fila)
echo   --- AUTOMATICO (v5.2) ---
echo   [A] Agendar a rotina automatica: dias uteis as 09:30 (Agendador do Windows)
echo   [V] Ver o agendamento e a ultima execucao    [X] Cancelar o agendamento
echo       Fila automatica: 17 4 8 9 15 10 12 (+14 se existir 05-Interno\supabase_secret.txt).
echo       Para mudar, escreva a fila em 05-Interno\rotina_auto.txt  (ex.: 4 8 9 15 10 12 14)
echo.
echo   [P] Abrir pasta de achados   [L] Abrir fila de prospeccao   [S] Sair
echo.
echo   FILA: digite varias opcoes separadas por espaco. Ex.:  R 11 D  ou  4 1 3 D  (virgula tambem vale: 1,3,D)
echo.
set "FILA="
set /p "FILA=Escolha: "
if not defined FILA goto MENU
if /I "%FILA%"=="S" exit /b
if /I "%FILA%"=="P" start "" "%~dp004-Achados" & goto MENU
if /I "%FILA%"=="L" start "" "%~dp004-Achados\prospeccao" & goto MENU
if /I "%FILA%"=="A" goto AGENDAR
if /I "%FILA%"=="V" goto VERAGENDA
if /I "%FILA%"=="X" goto CANCELAR
set "FILA=%FILA:,= %"
set "FILA=%FILA:R=4 8 13 9 15 10 12%"

set "INI=%TIME%"
set /a N=0
for %%T in (%FILA%) do set /a N+=1
set "RADAR_FILA=%N%"
set /a K=0
for %%T in (%FILA%) do call :RODA %%T
echo.
echo ===== FILA CONCLUIDA (inicio %INI% - fim %TIME%) =====
powershell -c "[console]::beep(880,300);[console]::beep(988,300);[console]::beep(1175,400)"
pause
goto MENU

:RODA
set /a K+=1
echo.
echo ---------- Tarefa %K% de %N%: [%1]  (%TIME%) ----------
echo [%DATE% %TIME%] inicio tarefa %1 >> "logs\fila.log"
if "%1"=="1" %PS% "scripts\c1_autos_diarios.ps1"
if "%1"=="2" %PS% "scripts\c2_canais_sites.ps1"
if "%1"=="3" %PS% "scripts\c3_conferir_cnpj.ps1"
if "%1"=="4" %PS% "scripts\c4_ibama_autos_embargos.ps1"
if "%1"=="5" %PS% "scripts\c5_dou_editais.ps1"
if "%1"=="6" %PS% "scripts\c5_dou_editais.ps1" -Cadastrar
if "%1"=="7" %PS% "scripts\c5_dou_editais.ps1" -Esquecer
if "%1"=="8" %PS% "scripts\c6_ibama_notif_suspensao.ps1"
if "%1"=="9" %PS% "scripts\c7_enriquecer_cnpj.ps1"
if "%1"=="10" %PS% "scripts\c8_leads_prospeccao.ps1"
if "%1"=="11" %PS% "scripts\c9_sondar_fontes.ps1"
if "%1"=="12" %PS% "scripts\c10_base_consolidada.ps1"
if "%1"=="13" %PS% "scripts\c11_inea_penalidades.ps1"
if "%1"=="14" %PS% "scripts\c12_enviar_base_site.ps1"
if "%1"=="15" %PS% "scripts\c13_sites_contatos.ps1"
if "%1"=="16" %PS% "scripts\c14_diarios_dell.ps1"
if "%1"=="17" %PS% "scripts\c15_inea_diario.ps1"
if /I "%1"=="D" (
  echo Desligando em 60 segundos...  ^(para cancelar: shutdown /a^)
  shutdown /s /t 60
)
echo [%DATE% %TIME%] fim tarefa %1 >> "logs\fila.log"
exit /b

:AGENDAR
rem Roda so com voce logado (nao guarda senha). Se o PC estiver desligado na hora, roda quando ligar.
schtasks /Create /TN "RadarAmbiental-Automatico" /TR "\"%~f0\" AUTO" /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 09:30 /F
powershell -NoProfile -Command "$t=Get-ScheduledTask -TaskName 'RadarAmbiental-Automatico' -ErrorAction SilentlyContinue; if($t){$s=$t.Settings; $s.StartWhenAvailable=$true; $s.DisallowStartIfOnBatteries=$false; $s.StopIfGoingOnBatteries=$false; $s.ExecutionTimeLimit='PT6H'; Set-ScheduledTask -TaskName 'RadarAmbiental-Automatico' -Settings $s | Out-Null; Write-Host 'Agendado: dias uteis 09:30. Se o PC estiver desligado, roda quando ligar.' -ForegroundColor Green}"
echo [%DATE% %TIME%] agendamento criado (dias uteis 09:30) >> "logs\fila.log"
pause
goto MENU

:VERAGENDA
schtasks /Query /TN "RadarAmbiental-Automatico" /V /FO LIST 2>nul || echo Nenhum agendamento. Use a opcao A.
echo.
echo Ultimas linhas do registro da fila:
powershell -NoProfile -Command "Get-Content 'logs\fila.log' -Tail 12"
pause
goto MENU

:CANCELAR
schtasks /Delete /TN "RadarAmbiental-Automatico" /F
echo [%DATE% %TIME%] agendamento cancelado >> "logs\fila.log"
pause
goto MENU

:AUTO
rem Fila automatica: sem perguntas (RADAR_FILA maior que 1), sem pause no fim, registro em logs\fila.log
set "FILA=17 4 8 9 15 10 12"
if exist "05-Interno\supabase_secret.txt" set "FILA=17 4 8 9 15 10 12 14"
if exist "05-Interno\rotina_auto.txt" set /p FILA=<"05-Interno\rotina_auto.txt"
set "FILA=%FILA:,= %"
set "FILA=%FILA:R=4 8 13 9 15 10 12%"
echo [%DATE% %TIME%] ROTINA AUTOMATICA inicio: %FILA% >> "logs\fila.log"
set "INI=%TIME%"
set /a N=0
for %%T in (%FILA%) do set /a N+=1
set "RADAR_FILA=%N%"
if %N% LSS 2 set "RADAR_FILA=2"
set /a K=0
for %%T in (%FILA%) do call :RODA %%T
echo [%DATE% %TIME%] ROTINA AUTOMATICA fim (inicio %INI%) >> "logs\fila.log"
powershell -c "[console]::beep(880,300);[console]::beep(988,300);[console]::beep(1175,400)"
exit /b
