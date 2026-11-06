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
