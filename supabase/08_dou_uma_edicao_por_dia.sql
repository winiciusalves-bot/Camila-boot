-- 08 · DOU: uma edicao por data e secao (09/11/2026, enviar_base_comum 1.1.4)
-- Antes da 1.1.4 cada ato do DOU virava uma "edicao" (link do proprio ato). Esta correcao:
--  1) cria a edicao DOU/Uniao/DO3 de cada dia; 2) religa os atos a ela (orgao fica em "orgao");
--  3) apaga as edicoes por ato que ficaram sem nenhum ato. Os atos NAO sao apagados (hash_ato nao muda).
-- Rodar em transacao e conferir os numeros antes do commit.
begin;
insert into comum.diario_edicao(fonte, ente, data, edicao, parte, link)
select distinct 'DOU', 'Uniao', a.data, '', 'DO3',
       'https://www.in.gov.br/leiturajornal?data=' || to_char(a.data, 'DD-MM-YYYY') || '&secao=do3'
  from comum.diario_ato a where a.fonte = 'DOU'
on conflict (fonte, ente, data, edicao, parte) do nothing;

update comum.diario_ato a
   set orgao = coalesce(a.orgao, a.ente), ente = 'Uniao', edicao_id = e.id
  from comum.diario_edicao e
 where a.fonte = 'DOU' and e.fonte = 'DOU' and e.ente = 'Uniao' and e.edicao = '' and e.parte = 'DO3' and e.data = a.data
   and (a.ente is distinct from 'Uniao' or a.edicao_id is distinct from e.id);

delete from comum.diario_edicao e
 where e.fonte = 'DOU' and e.ente <> 'Uniao'
   and not exists (select 1 from comum.diario_ato a where a.edicao_id = e.id);

-- conferencia: esperado 1 edicao por dia e 0 ato sem edicao
select a.data, count(*) atos, count(distinct a.edicao_id) eds, count(*) filter (where a.edicao_id is null) sem_ed
  from comum.diario_ato a where a.fonte = 'DOU' group by 1 order by 1;
-- se estiver certo: commit;  se nao: rollback;
