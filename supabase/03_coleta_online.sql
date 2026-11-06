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
