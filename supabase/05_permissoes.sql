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
