-- Conferência diária (✕ reprovar / ✓ aprovar) — pedido do usuário em 07/11/2026.
-- Reprovado fica 45 dias (pode restaurar); depois o coletor apaga os dados da empresa e deixa só o CNPJ marcado 'expurgado',
-- para a coleta não trazer de volta. Auto NOVO depois da reprovação devolve a empresa à conferência.
create table if not exists public.triagem (
  cnpj text primary key,
  decisao text not null check (decisao in ('aprovado','reprovado','expurgado')),
  decidido_em timestamptz not null default now(),
  autor_email text not null default (auth.jwt() ->> 'email'),
  nota text
);
alter table public.triagem enable row level security;
drop policy if exists ler_triagem on public.triagem;
create policy ler_triagem on public.triagem for select to authenticated using (public.eh_autorizado());
drop policy if exists gravar_triagem on public.triagem;
create policy gravar_triagem on public.triagem for insert to authenticated with check (public.eh_autorizado() and decisao in ('aprovado','reprovado'));
drop policy if exists mudar_triagem on public.triagem;
create policy mudar_triagem on public.triagem for update to authenticated using (public.eh_autorizado() and decisao <> 'expurgado') with check (public.eh_autorizado() and decisao in ('aprovado','reprovado'));
drop policy if exists desfazer_triagem on public.triagem;
create policy desfazer_triagem on public.triagem for delete to authenticated using (public.eh_autorizado() and decisao <> 'expurgado');
grant select, insert, update, delete on public.triagem to authenticated;
grant all on public.triagem to service_role;
