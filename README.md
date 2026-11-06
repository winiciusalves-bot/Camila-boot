# Ambiental Costa: site, área restrita e coleta diária

```
site/                     -> o que vai para o ar (Netlify publica só esta pasta)
  area-restrita/          -> painel com login (dados vêm do Supabase, nunca de arquivo)
  assets/config.js        -> WhatsApp, CREA, URL e chave "anon" do Supabase
coletor/coletar.py        -> coleta diária IBAMA -> Supabase (roda no GitHub Actions)
supabase/*.sql            -> estrutura do banco (sem dados)
.github/workflows/        -> agenda da coleta (06:00, horário de Brasília)
```

Quem cria contas, senhas e chaves é você. O Claude nunca digita senha nem chave.

## Passo 1. Supabase (banco e login), cerca de 15 minutos
1. Em **supabase.com**, crie o projeto com **New project**. Use a região **South America (São Paulo)** e uma senha de banco criada por você.
2. Abra o **SQL Editor**, cole o conteúdo de `supabase/01_estrutura.sql` e clique em **Run**. Faça o mesmo, nesta ordem, com `supabase/03_coleta_online.sql` e `supabase/04_ocorrencias.sql`.
3. Em **Authentication > Sign In / Providers > Email**, desligue **Allow new users to sign up**. Assim ninguém se cadastra sozinho.
4. Em **Authentication > Users > Add user > Create new user**, informe seu e-mail e uma senha sua e marque **Auto Confirm User**.
5. No **SQL Editor**, autorize esse e-mail:
   `insert into usuarios_autorizados (email, nome) values ('seu@email.com', 'Seu nome');`
6. Em **Project Settings > API Keys**, copie a **Project URL** e a chave **Publishable** (`sb_publishable_...`, ou a antiga anon) para `site/assets/config.js` (`supabaseUrl` e `supabaseAnonKey`).
   A chave anon é pública por natureza: a proteção vem das regras do banco. **Não** use a `service_role` ou secret no site.

## Passo 2. GitHub (guarda o código e roda a coleta todo dia)
1. Crie um repositório **privado**, por exemplo `ambientalcosta`, e avise o Claude, que sobe os arquivos.
2. No repositório, vá em **Settings > Secrets and variables > Actions > New repository secret** e crie:
   - `SUPABASE_URL`: a Project URL
   - `SUPABASE_SERVICE_KEY`: a chave **service_role / secret**. Ela fica só aqui, nunca no site.
3. Em **Actions > "Coleta diária IBAMA -> Supabase" > Run workflow**, faça a primeira carga. Depois disso, a coleta roda sozinha todo dia às 06:00.

## Passo 3. Netlify ligado ao GitHub
Em **Site configuration > Build & deploy > Link repository**, escolha o repositório. O `netlify.toml` já manda publicar só a pasta `site/`.
A partir daí, qualquer ajuste no repositório vai para o ar sozinho, e não há mais arrastar pastas, nem risco de subir dados por engano.

Para entrar: **https://ambientalcosta.netlify.app/area-restrita/**

A área restrita tem três abas:
- **Fila de prospecção**: cartões por prioridade (A e B primeiro), com motivo da nota, prazo estimado, telefone e botão de WhatsApp com mensagem pronta (CREA, sem afirmar irregularidade, com opção SAIR).
- **Empresas**: tabela completa com filtros e registro de contatos.
- **Registro de documentos**: todos os documentos de todas as fontes, com FATO / INDÍCIO, situação e link da fonte.

## O que a coleta faz todo dia
- Baixa o `auto_infracao_csv.zip` do IBAMA Dados Abertos e filtra RJ, últimos 365 dias e pessoa jurídica com DV do CNPJ válido.
- Mascara CPF em qualquer campo de texto, inclusive no nome do autuado.
- Consulta o cadastro do CNPJ só para empresas novas ou com cadastro de mais de 30 dias. Usa BrasilAPI e, de reserva, minhareceita.org e publica.cnpj.ws. MEI e empresário individual entram com telefone e e-mail (pedido de 06/11/2026), com CPF mascarado. Sócios (QSA) só com nome e qualificação.
- Marca "nome no auto difere da razão social" como INDÍCIO, para conferir antes de contatar.
- Grava em `empresas` e `autos` sem tocar no histórico de `contatos`, e registra cada execução em `coletas` com fonte, método, totais e erros.
- Lê também os **termos de embargo** (vigente, desembargado ou cancelado), as **notificações** e os **termos de suspensão** do IBAMA. As colunas dos dois últimos são detectadas automaticamente e ficam registradas no log.
- Calcula **pontuação de 0 a 100 e prioridade A/B/C** por empresa, pela regra da v5 do Radar-Ambiental: recência, prazo de defesa estimado (ciência + 20 dias), embargo vigente, quantidade de documentos, valor indicado, porte e contato. Descarta como **X** quem não está ativa, órgão público, quem está na lista `exclusoes` (Petrobras por padrão) e quem tem status Não contatar, Sem interesse ou Cliente. A pontuação indica urgência de contato, não culpa nem dano.
- Grava cada documento na tabela única `ocorrencias` (mesmas chaves e colunas da base consolidada v5.1 do Radar-Ambiental). O Radar do PC pode enviar para a mesma tabela o que só ele coleta (INEA, DOU, diários municipais, demolição, apreensão, acidentes), com `origem = 'radar-pc'`.
- A pontuação usa a regra v5.1 sobre TODAS as ocorrências do banco: demolição +15, apreensão em 12 meses +10, acidente em 24 meses +10, INEA em 12 meses +15 (antigo +5), licença +3, além dos critérios da v5. Menções em diário (INDÍCIO) não pontuam.
- Atualiza os totais do site público pela função `resumo_publico`, que expõe só números.

## Limites (não contornamos bloqueio, captcha nem login)
- Os dados abertos do IBAMA podem levar dias para mostrar autos recentes.
- O DOU pelo INLABS exige login e pode bloquear servidores de nuvem. INEA e prefeituras não têm base aberta por CNPJ. Essas fontes continuam no Radar-Ambiental do PC ou via pedido de LAI.
- O plano gratuito do Supabase pausa projetos parados. A coleta diária mantém o projeto em uso.
- Auto de infração não é condenação, e o valor do auto não é dano.
