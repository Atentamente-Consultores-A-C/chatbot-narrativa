-- ============================================================
-- MIGRACIÓN: 3 bots (apoyo emocional / dudas sobre el curso /
-- dudas sobre el contenido) para una base de datos que YA tiene
-- el esquema anterior (una sola sesión por whatsapp_id).
--
-- Ejecuta esto en el SQL Editor de Supabase, en orden, UNA VEZ.
-- Las sesiones existentes se conservan y quedan como
-- bot_type = 'apoyo_emocional' (el único bot que ya funcionaba).
-- ============================================================

-- 1. Tabla nueva: contactos (uno por whatsapp_id, compartido entre los 3 bots)
create table if not exists contacts (
  whatsapp_id text primary key,
  contact_name text,
  active_bot_type text check (active_bot_type in ('apoyo_emocional', 'dudas_curso', 'dudas_contenido')),
  context jsonb not null default '{}',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create trigger contacts_updated_at
  before update on contacts
  for each row execute function update_updated_at();

-- 2. Agregar bot_type a sessions (todas las filas existentes quedan como apoyo_emocional)
alter table sessions add column if not exists bot_type text not null default 'apoyo_emocional'
  check (bot_type in ('apoyo_emocional', 'dudas_curso', 'dudas_contenido'));

-- 3. Cambiar la unicidad de whatsapp_id solo -> (whatsapp_id, bot_type)
--    Ajusta el nombre de la constraint si en tu base tiene otro nombre
--    (consúltalo con: \d sessions  o  select conname from pg_constraint where conrelid = 'sessions'::regclass;)
alter table sessions drop constraint if exists sessions_whatsapp_id_key;
alter table sessions add constraint sessions_whatsapp_id_bot_type_key unique (whatsapp_id, bot_type);

-- 4. Sembrar contacts con los contactos que ya existen en sessions
insert into contacts (whatsapp_id, contact_name, active_bot_type, context)
select s.whatsapp_id, s.contact_name, 'apoyo_emocional', '{}'::jsonb
from sessions s
on conflict (whatsapp_id) do nothing;

-- ============================================================
-- VERIFICACIÓN
-- ============================================================
select column_name, data_type from information_schema.columns
where table_name = 'sessions' order by ordinal_position;

select count(*) as contactos_creados from contacts;
