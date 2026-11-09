-- 07 · Gravação dos diários no schema comum por uma função (09/11/2026)
-- Por quê: o schema "comum" não é exposto na API REST, e a gravação direta por DATABASE_URL
-- depende de senha. Esta função fica no public (que a API já expõe), só o service_role pode
-- chamar, e grava em comum.coleta, comum.diario_edicao e comum.diario_ato.
-- Usada pelo coletor dos municípios (coletor/comum_diarios.py) e pela Vigia/alerta do gabinete.
-- Regras do banco continuam valendo: CNPJ com DV, CPF aberto recusado. Linha recusada não derruba
-- o lote; volta na lista "rejeitados" com o motivo.
--
-- Chamada: POST /rest/v1/rpc/diarios_gravar  {"p": {...}}
--   p.coleta_id   (opcional) continua uma coleta já aberta (lotes seguintes)
--   p.coleta      {fonte, robo, versao, onde, iniciou, terminou, status, linhas, erro}
--   p.edicoes     [{fonte, ente, data, edicao, parte, link, sha256, paginas, id_fonte, arquivo, bytes}]
--   p.atos        [{fonte, ente, data, edicao, parte, orgao, tipo, cnpj, razao_receita, pessoa_nome, cargo,
--                   valor, processo, classe, link, pagina, trecho, hash_ato, acao, papel, nivel, matricula,
--                   contrato, contratada}]
-- Retorno: {coleta_id, edicoes, atos_novos, atos_repetidos, rejeitados:[{hash_ato|link, motivo}]}

create or replace function public.diarios_gravar(p jsonb)
returns jsonb
language plpgsql
security definer
set search_path = pg_catalog, comum
as $$
declare
  v_coleta bigint := nullif(p->>'coleta_id','')::bigint;
  c jsonb := coalesce(p->'coleta','{}'::jsonb);
  e jsonb; a jsonb;
  n_ed int := 0; n_novo int := 0; n_rep int := 0; v_ed bigint;
  rej jsonb := '[]'::jsonb;
begin
  if v_coleta is null then
    insert into comum.coleta(fonte, robo, versao, onde, iniciou, terminou, status, linhas, erro)
    values (c->>'fonte', coalesce(c->>'robo','?'), c->>'versao', c->>'onde',
            coalesce((c->>'iniciou')::timestamptz, now()), (c->>'terminou')::timestamptz,
            coalesce(c->>'status','rodando'), nullif(c->>'linhas','')::int, left(c->>'erro', 2000))
    returning id into v_coleta;
  elsif c ? 'status' then
    update comum.coleta set status = c->>'status', terminou = coalesce((c->>'terminou')::timestamptz, now()),
           linhas = coalesce(nullif(c->>'linhas','')::int, linhas), erro = coalesce(left(c->>'erro', 2000), erro)
     where id = v_coleta;
  end if;

  for e in select * from jsonb_array_elements(coalesce(p->'edicoes','[]'::jsonb)) loop
    begin
      insert into comum.diario_edicao(fonte, ente, data, edicao, parte, link, sha256, paginas, coleta_id, id_fonte, arquivo, bytes)
      values (e->>'fonte', e->>'ente', (e->>'data')::date, coalesce(e->>'edicao',''), coalesce(nullif(e->>'parte',''),'unica'),
              e->>'link', nullif(lower(e->>'sha256'),''), nullif(e->>'paginas','')::int, v_coleta,
              e->>'id_fonte', e->>'arquivo', nullif(e->>'bytes','')::bigint)
      on conflict (fonte, data, edicao, parte) do update
        set sha256 = coalesce(excluded.sha256, diario_edicao.sha256),
            paginas = coalesce(excluded.paginas, diario_edicao.paginas),
            bytes = coalesce(excluded.bytes, diario_edicao.bytes),
            arquivo = coalesce(excluded.arquivo, diario_edicao.arquivo),
            id_fonte = coalesce(excluded.id_fonte, diario_edicao.id_fonte);
      n_ed := n_ed + 1;
    exception when others then
      rej := rej || jsonb_build_object('link', e->>'link', 'motivo', left(sqlerrm, 200));
    end;
  end loop;

  for a in select * from jsonb_array_elements(coalesce(p->'atos','[]'::jsonb)) loop
    begin
      select id into v_ed from comum.diario_edicao
       where fonte = a->>'fonte' and data = (a->>'data')::date and edicao = coalesce(a->>'edicao','')
         and parte = coalesce(nullif(a->>'parte',''),'unica');
      insert into comum.diario_ato(edicao_id, data, fonte, ente, orgao, tipo, cnpj, razao_receita, pessoa_nome, cargo, valor,
                                   processo, classe, link, pagina, trecho, hash_ato, coleta_id, acao, papel, nivel, matricula,
                                   contrato, contratada)
      values (v_ed, (a->>'data')::date, a->>'fonte', a->>'ente', a->>'orgao', a->>'tipo', comum.cnpj_norm(a->>'cnpj'),
              a->>'razao_receita', a->>'pessoa_nome', a->>'cargo', nullif(a->>'valor','')::numeric, a->>'processo',
              coalesce(a->>'classe','INDICIO'), a->>'link', nullif(a->>'pagina','')::int, left(a->>'trecho', 1500),
              a->>'hash_ato', v_coleta, a->>'acao', a->>'papel', a->>'nivel', a->>'matricula', a->>'contrato', a->>'contratada')
      on conflict (hash_ato) do nothing;
      if found then n_novo := n_novo + 1; else n_rep := n_rep + 1; end if;
    exception when others then
      rej := rej || jsonb_build_object('hash_ato', a->>'hash_ato', 'motivo', left(sqlerrm, 200));
    end;
  end loop;

  return jsonb_build_object('coleta_id', v_coleta, 'edicoes', n_ed, 'atos_novos', n_novo,
                            'atos_repetidos', n_rep, 'rejeitados', rej);
end $$;

revoke all on function public.diarios_gravar(jsonb) from public, anon, authenticated;
grant execute on function public.diarios_gravar(jsonb) to service_role;

-- Fonte do PNCP (a Vigia grava contratos do PNCP)
insert into comum.fonte(id, nome, url) values ('PNCP', 'Portal Nacional de Contratações Públicas', 'https://pncp.gov.br')
on conflict (id) do nothing;
