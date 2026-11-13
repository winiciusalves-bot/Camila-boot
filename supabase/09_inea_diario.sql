-- Ambiental Costa · Diário Eletrônico do INEA: atos de LICENCIAMENTO (separados dos autuados)
-- Rode uma vez no SQL Editor do Supabase. Pode rodar de novo.
-- As notificações de FISCALIZAÇÃO vão para a tabela ocorrencias (chave INEA-DE|...). Aqui ficam só:
-- licença/documento emitido, pedido (requerimento) e notificação de licenciamento (exigência num pedido de licença).
-- Licenciado NÃO é autuado: nada desta tabela vira lead nem pontua.
-- Só pessoa jurídica com DV do CNPJ válido. Nenhum CPF.

create table if not exists inea_licenciamento (
  chave text primary key,                 -- INEADE|<categoria>|<número do documento>|<cnpj>
  categoria text,                         -- DOCUMENTO EMITIDO | REQUERIMENTO | NOTIFICACAO DE LICENCIAMENTO
  ato text, titulo text,                  -- ex.: ato "Licença de Operação (LO)"; título = licença a que o ato se refere
  numero text, processo text,
  data_publicacao date, data_validade date,
  cnpj text, nome text,
  municipio_endereco text,                -- município do ENDEREÇO do interessado (não necessariamente o do empreendimento)
  atividade text, codigo_atividade text, classe_impacto text, setor text,
  edicao int, link_fonte text,
  primeira_coleta date default current_date, ultima_coleta date
);
create index if not exists inea_lic_cnpj_idx on inea_licenciamento (cnpj);
create index if not exists inea_lic_data_idx on inea_licenciamento (data_publicacao desc);

alter table inea_licenciamento enable row level security;
revoke all on inea_licenciamento from anon;
drop policy if exists ler_inea_licenciamento on inea_licenciamento;
create policy ler_inea_licenciamento on inea_licenciamento for select to authenticated using (public.eh_autorizado());
