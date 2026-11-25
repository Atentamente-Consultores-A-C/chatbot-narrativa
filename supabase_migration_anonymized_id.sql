-- ============================================================
-- Agrega el id anónimo de la persona a contacts.
-- Lo manda Turn.io / la app / la plataforma en el campo "anonymized_id" del webhook.
-- Correr una vez en el SQL Editor de Supabase.
-- ============================================================
alter table contacts add column if not exists anonymized_id text;

create index if not exists contacts_anonymized_id_idx on contacts (anonymized_id);
