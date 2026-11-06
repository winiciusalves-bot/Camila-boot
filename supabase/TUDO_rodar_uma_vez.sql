-- ===== 01_estrutura.sql =====
-- Ambiental Costa · Área restrita · Estrutura do banco (Supabase / Postgres)
-- Rode UMA vez no SQL Editor do Supabase, antes de 02_dados.sql.
-- Proteção: só usuários logados E cadastrados em usuarios_autorizados leem os dados.
-- Visitante sem login (chave anon) não lê nada.

create table if not exists usuarios_autorizados (
  email text primary key,
  nome text,
  criado_em timestamptz default now()
);

create table if not exists empresas (
  cnpj text primary key,
  razao_social text, nome_fantasia text, situacao_receita text, natureza_juridica text,
  individual boolean default false,          -- MEI / empresário individual (contato liberado em 06/11/2026; CPF sempre mascarado)
  atividade text, municipio_sede text, telefone text, email text,
  nome_divergente boolean default false,     -- nome no auto difere da razão social na Receita
  alerta text, data_coleta date
);

create table if not exists autos (
  n_auto text primary key,
  cnpj text references empresas(cnpj),
  data_auto date, municipio text, nome_no_auto text, processo text,
  valor_auto numeric,                         -- valor indicado no auto: NÃO é dano nem condenação
  tipo_infracao text, descricao text, gravidade text,
  cancelado boolean default false, situacao_formulario text, data_coleta date
);

-- Registro de contatos: só inclusão (histórico não se apaga pelo site).
create table if not exists contatos (
  id bigint generated always as identity primary key,
  cnpj text not null references empresas(cnpj),
  status text not null check (status in ('novo','contatado','respondeu','reuniao','cliente','sem_interesse','nao_contatar')),
  canal text, nota text,
  autor_email text not null default (auth.jwt() ->> 'email'),
  criado_em timestamptz not null default now()
);
create index if not exists contatos_cnpj_idx on contatos (cnpj, criado_em desc);
create index if not exists autos_cnpj_idx on autos (cnpj);

create or replace function public.eh_autorizado() returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from usuarios_autorizados
                 where lower(email) = lower(auth.jwt() ->> 'email'));
$$;

alter table usuarios_autorizados enable row level security;  -- sem política: ninguém lê pelo site
alter table empresas enable row level security;
alter table autos    enable row level security;
alter table contatos enable row level security;

revoke all on usuarios_autorizados, empresas, autos, contatos from anon;

drop policy if exists ler_empresas on empresas;
create policy ler_empresas on empresas for select to authenticated using (public.eh_autorizado());
drop policy if exists ler_autos on autos;
create policy ler_autos on autos for select to authenticated using (public.eh_autorizado());
drop policy if exists ler_contatos on contatos;
create policy ler_contatos on contatos for select to authenticated using (public.eh_autorizado());
drop policy if exists registrar_contato on contatos;
create policy registrar_contato on contatos for insert to authenticated
  with check (public.eh_autorizado() and autor_email = (auth.jwt() ->> 'email'));

-- Depois de criar o usuário em Authentication > Users, autorize o e-mail:
-- insert into usuarios_autorizados (email, nome) values ('seu-email@exemplo.com', 'Seu nome');

-- ===== 03_coleta_online.sql =====
-- Ambiental Costa · Coleta online diária
-- Rode depois de 01_estrutura.sql. Pode rodar de novo sem problema.

-- Quando o auto apareceu pela 1ª vez na coleta (para destacar "novos")
alter table autos add column if not exists primeira_coleta date default current_date;
alter table empresas add column if not exists cadastro_atualizado_em date;
alter table empresas add column if not exists fonte_cadastro text;

-- Registro de cada execução do coletor (auditoria: fonte, data, método, totais)
create table if not exists coletas (
  id bigint generated always as identity primary key,
  iniciada_em timestamptz not null default now(),
  terminada_em timestamptz,
  status text,                 -- ok | erro
  fonte text, metodo text,
  autos_lidos int, autos_rj_pj int, autos_novos int,
  empresas_novas int, empresas_atualizadas int,
  mensagem text
);
alter table coletas enable row level security;
revoke all on coletas from anon;
drop policy if exists ler_coletas on coletas;
create policy ler_coletas on coletas for select to authenticated using (public.eh_autorizado());

-- Números agregados para o site público (sem nomes, sem CNPJ). Única coisa que o visitante sem login pode ler.
create or replace function public.resumo_publico() returns json
language sql stable security definer set search_path = public as $$
  select json_build_object(
    'autos',      (select count(*) from autos where data_auto >= current_date - 365),
    'cnpjs',      (select count(distinct cnpj) from autos where data_auto >= current_date - 365),
    'cancelados', (select count(*) from autos where cancelado and data_auto >= current_date - 365),
    'de',         (select min(data_auto) from autos where data_auto >= current_date - 365),
    'ate',        (select max(data_auto) from autos),
    'coleta',     (select max(terminada_em)::date from coletas where status = 'ok'),
    'tipos',      (select coalesce(json_agg(json_build_array(tipo_infracao, n) order by n desc), '[]'::json)
                   from (select tipo_infracao, count(*) n from autos
                         where data_auto >= current_date - 365 group by 1 order by 2 desc limit 6) t)
  );
$$;
revoke all on function public.resumo_publico() from public;
grant execute on function public.resumo_publico() to anon, authenticated;

-- ===== Prospecção (regras da v5 do Radar-Ambiental, 06/11/2026) =====
alter table autos add column if not exists data_ciencia date;
alter table autos add column if not exists prazo_defesa_estimado date;   -- ciência + 20 dias (Decreto 6.514/2008, art. 113). ESTIMATIVA.
alter table empresas add column if not exists porte text;
alter table empresas add column if not exists prioridade text;           -- A, B, C ou X (descartado)
alter table empresas add column if not exists pontos int;
alter table empresas add column if not exists motivos text;
alter table empresas add column if not exists embargos_vigentes int;
alter table empresas add column if not exists prazo_defesa_ate date;

create table if not exists embargos (
  num_tad text primary key,
  cnpj text, data_embargo date, municipio text, tipo_area text,
  status text,                       -- VIGENTE | DESEMBARGADO | CANCELADO (segundo os dados abertos)
  data_desembargo date, data_coleta date
);
create index if not exists embargos_cnpj_idx on embargos (cnpj);

-- Lista de exclusão (raiz do CNPJ = 8 primeiros dígitos). Petrobras entra por padrão.
create table if not exists exclusoes (cnpj_raiz text primary key, motivo text, criado_em timestamptz default now());
insert into exclusoes (cnpj_raiz, motivo) values ('33000167', 'Petrobras: excluída por padrão') on conflict do nothing;

alter table embargos  enable row level security;
alter table exclusoes enable row level security;
revoke all on embargos, exclusoes from anon;
drop policy if exists ler_embargos on embargos;
create policy ler_embargos on embargos for select to authenticated using (public.eh_autorizado());
drop policy if exists ler_exclusoes on exclusoes;
create policy ler_exclusoes on exclusoes for select to authenticated using (public.eh_autorizado());
drop policy if exists incluir_exclusao on exclusoes;
create policy incluir_exclusao on exclusoes for insert to authenticated with check (public.eh_autorizado());
alter table empresas add column if not exists natureza_codigo text;
alter table empresas add column if not exists socios text;   -- nome e qualificação do QSA, sem CPF

-- ===== 04_ocorrencias.sql =====
-- Ambiental Costa · Base única de ocorrências (mesmo formato do ocorrencias_pj.csv da v5.1 do Radar-Ambiental)
-- Rode depois de 03_coleta_online.sql. Pode rodar de novo.
-- Alimentada por: (a) coletor diário do GitHub (IBAMA) e (b) envio da base do PC (INEA, DOU, diários municipais etc.).
-- Só pessoa jurídica com DV do CNPJ válido. Nenhum CPF.

create table if not exists ocorrencias (
  chave text primary key,                 -- ex.: IBAMA-AUTO|ABC123/D, IBAMA-EMB|<SEQ_TAD>, IBAMA-NOT|<SEQ>, INEA-PEN|<id>
  fonte text, orgao text, tipo_documento text, numero text, processo text,
  data_documento date, data_documento_status text, data_ciencia date,
  prazo_defesa_fim_estimado date,         -- ESTIMATIVA (ciência + 20 dias); confirmar na notificação
  prazo_defesa_status text,
  situacao text,                          -- VALIDO | CANCELADO/EXCLUIDO | VIGENTE | DESEMBARGADO | REGISTRADA | INDICIO - ler o ato
  cnpj text, nome text, municipio text, cod_ibge text,
  valor_indicado_rs_nao_e_dano numeric,   -- multa proposta: NÃO é dano nem condenação
  assunto text, descricao text,
  nivel text,                             -- FATO (documento oficial) | INDICIO (menção; ler o ato)
  link_fonte text, primeira_coleta date default current_date, ultima_coleta date,
  origem text                             -- 'coletor-online' ou 'radar-pc'
);
create index if not exists ocorrencias_cnpj_idx on ocorrencias (cnpj);
create index if not exists ocorrencias_data_idx on ocorrencias (data_documento desc);

alter table ocorrencias enable row level security;
revoke all on ocorrencias from anon;
drop policy if exists ler_ocorrencias on ocorrencias;
create policy ler_ocorrencias on ocorrencias for select to authenticated using (public.eh_autorizado());

-- ===== 05_permissoes.sql =====
-- Ambiental Costa · Permissões explícitas da API (rode por último; pode rodar de novo).
-- Projetos novos do Supabase podem não liberar as tabelas para a API automaticamente.
-- O que cada usuário vê continua decidido pelas regras RLS (eh_autorizado()).
grant usage on schema public to anon, authenticated, service_role;
grant select on empresas, autos, contatos, coletas, embargos, exclusoes, ocorrencias to authenticated;
grant insert on contatos, exclusoes to authenticated;
grant all on all tables in schema public to service_role;
grant usage, select on all sequences in schema public to authenticated, service_role;
revoke all on usuarios_autorizados from anon, authenticated;
revoke execute on function public.eh_autorizado() from public, anon;
grant execute on function public.eh_autorizado() to authenticated, service_role;

