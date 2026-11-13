-- Ficha editável (pedido do usuário em 13/11/2026):
--  1) contatos novos da empresa (depois da aprovação/conversa com o cliente), com editar e excluir;
--  2) anotações livres na ficha, com editar e excluir;
--  3) editar e excluir itens do histórico de contatos (tabela contatos).
-- Só registros criados pelo usuário no painel. Nada aqui apaga dado da coleta (autos, embargos, ocorrências, empresas).
-- Pode rodar mais de uma vez (idempotente). Inclui a tabela da conferência (06_triagem) caso ainda não exista.

-- ---------- 0) Conferência (mesmo conteúdo do 06_triagem.sql) ----------
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

-- carimbo de edição
create or replace function public.carimbar_edicao() returns trigger
language plpgsql set search_path = public as $$
begin
  new.editado_em := now();
  new.editado_por := coalesce(auth.jwt() ->> 'email', new.editado_por);
  return new;
end $$;

-- ---------- 1) Histórico de contatos: editar e excluir ----------
alter table public.contatos add column if not exists editado_em timestamptz;
alter table public.contatos add column if not exists editado_por text;
drop trigger if exists contatos_editado on public.contatos;
create trigger contatos_editado before update on public.contatos for each row execute function public.carimbar_edicao();
drop policy if exists editar_contato on public.contatos;
create policy editar_contato on public.contatos for update to authenticated using (public.eh_autorizado()) with check (public.eh_autorizado());
drop policy if exists excluir_contato on public.contatos;
create policy excluir_contato on public.contatos for delete to authenticated using (public.eh_autorizado());
grant select, insert, update, delete on public.contatos to authenticated;

-- ---------- 2) Contatos novos da empresa ----------
create table if not exists public.ficha_contatos (
  id bigint generated always as identity primary key,
  cnpj text not null references public.empresas(cnpj) on delete cascade,
  nome text, cargo text, telefone text, email text, obs text,
  autor_email text not null default (auth.jwt() ->> 'email'),
  criado_em timestamptz not null default now(),
  editado_em timestamptz, editado_por text,
  constraint ficha_contatos_algo check (coalesce(nome,'') <> '' or coalesce(telefone,'') <> '' or coalesce(email,'') <> '')
);
create index if not exists ficha_contatos_cnpj_idx on public.ficha_contatos (cnpj);
drop trigger if exists ficha_contatos_editado on public.ficha_contatos;
create trigger ficha_contatos_editado before update on public.ficha_contatos for each row execute function public.carimbar_edicao();

-- ---------- 3) Anotações da ficha ----------
create table if not exists public.ficha_anotacoes (
  id bigint generated always as identity primary key,
  cnpj text not null references public.empresas(cnpj) on delete cascade,
  texto text not null check (length(trim(texto)) > 0),
  autor_email text not null default (auth.jwt() ->> 'email'),
  criado_em timestamptz not null default now(),
  editado_em timestamptz, editado_por text
);
create index if not exists ficha_anotacoes_cnpj_idx on public.ficha_anotacoes (cnpj);
drop trigger if exists ficha_anotacoes_editado on public.ficha_anotacoes;
create trigger ficha_anotacoes_editado before update on public.ficha_anotacoes for each row execute function public.carimbar_edicao();

-- Permissões: só usuários autorizados leem, incluem, editam e excluem. Visitante sem login não vê nada.
do $$ declare t text; begin
  foreach t in array array['ficha_contatos','ficha_anotacoes'] loop
    execute format('alter table public.%I enable row level security', t);
    execute format('revoke all on public.%I from anon', t);
    execute format('drop policy if exists ler on public.%I', t);
    execute format('create policy ler on public.%I for select to authenticated using (public.eh_autorizado())', t);
    execute format('drop policy if exists incluir on public.%I', t);
    execute format('create policy incluir on public.%I for insert to authenticated with check (public.eh_autorizado())', t);
    execute format('drop policy if exists editar on public.%I', t);
    execute format('create policy editar on public.%I for update to authenticated using (public.eh_autorizado()) with check (public.eh_autorizado())', t);
    execute format('drop policy if exists excluir on public.%I', t);
    execute format('create policy excluir on public.%I for delete to authenticated using (public.eh_autorizado())', t);
    execute format('grant select, insert, update, delete on public.%I to authenticated', t);
    execute format('grant all on public.%I to service_role', t);
  end loop;
end $$;
