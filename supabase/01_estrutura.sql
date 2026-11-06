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
