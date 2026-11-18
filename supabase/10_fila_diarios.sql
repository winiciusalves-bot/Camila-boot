-- Ambiental Costa · Fila "Diários a conferir" (pedido do usuário em 18/11/2026).
-- Achados dos diários municipais (auto de infração, embargo, interdição) entram aqui como INDÍCIO.
-- Só viram empresa do painel depois que alguém LÊ O ATO e marca "É FATO" (regra: palavra-chave não é decisão).
-- Rode depois de 04_ocorrencias.sql. Pode rodar de novo.

create table if not exists public.fila_diarios (
  chave text primary key,                 -- mesma chave da ocorrência INDÍCIO (DOMT|cnpj|data|link)
  cnpj text not null,
  nome text, municipio text, orgao text,
  data_documento date,                    -- data da EDIÇÃO do diário (não é a data do auto)
  assunto text, link_fonte text, trecho text,
  pretriagem text check (pretriagem in ('provavel','duvidoso','provavel_falso')),
  pretriagem_motivo text,
  status text not null default 'a_conferir' check (status in ('a_conferir','fato','descartado')),
  tipo_confirmado text check (tipo_confirmado in ('auto de infração ambiental','embargo','interdição','notificação ambiental')),
  numero_ato text, data_ato date, nota text,
  conferido_em timestamptz, autor_email text,
  criado_em timestamptz not null default now()
);
create index if not exists fila_diarios_status_idx on public.fila_diarios (status, data_documento desc);
create index if not exists fila_diarios_cnpj_idx on public.fila_diarios (cnpj);

alter table public.fila_diarios enable row level security;
revoke all on public.fila_diarios from anon;
drop policy if exists ler_fila_diarios on public.fila_diarios;
create policy ler_fila_diarios on public.fila_diarios for select to authenticated using (public.eh_autorizado());
-- quem confere só muda a decisão; a linha em si é criada pelo coletor (service_role)
drop policy if exists conferir_fila_diarios on public.fila_diarios;
create policy conferir_fila_diarios on public.fila_diarios for update to authenticated
  using (public.eh_autorizado()) with check (public.eh_autorizado());
grant select on public.fila_diarios to authenticated;
grant update (status, tipo_confirmado, numero_ato, data_ato, nota, conferido_em, autor_email) on public.fila_diarios to authenticated;
grant all on public.fila_diarios to service_role;

-- A carga (com pré-triagem e CPF mascarado no trecho) é feita pelo coletor diário (coletor/fila_diarios.py).
