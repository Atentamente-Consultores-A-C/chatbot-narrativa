-- ============================================================
-- SETUP COMPLETO PARA ATENTAMENTE BOT
-- Ejecuta esto en el SQL Editor de Supabase (en orden)
-- ============================================================

-- 1. Habilitar extensión pgvector (necesaria para embeddings)
create extension if not exists vector;

-- ============================================================
-- 2. TABLA DE SESIONES
-- Una fila por número de WhatsApp
-- ============================================================
create table sessions (
  id uuid primary key default gen_random_uuid(),
  whatsapp_id text unique not null,
  contact_name text,
  phase integer not null default 1,
  research_consent boolean,
  collected_data jsonb not null default '{}',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- ============================================================
-- 3. TABLA DE MENSAJES
-- Historial completo de cada conversación
-- ============================================================
create table messages (
  id uuid primary key default gen_random_uuid(),
  session_id uuid not null references sessions(id) on delete cascade,
  role text not null check (role in ('user', 'assistant')),
  content text not null,
  phase integer,
  created_at timestamptz not null default now()
);

create index idx_messages_session_id on messages(session_id);
create index idx_messages_created_at on messages(created_at);

-- ============================================================
-- 4. TABLA DE LECCIONES APRENDIDAS
-- El agente supervisor las genera; el agente principal las lee
-- ============================================================
create table lessons (
  id uuid primary key default gen_random_uuid(),
  trigger_desc text not null,
  rule text not null,
  reason text not null,
  embedding vector(1536),
  active boolean not null default true,
  times_applied integer not null default 0,
  created_at timestamptz not null default now()
);

-- ============================================================
-- 5. TABLA DE EVALUACIONES DEL SUPERVISOR
-- Una evaluación por cada respuesta del agente principal
-- ============================================================
create table evaluations (
  id uuid primary key default gen_random_uuid(),
  message_id uuid not null references messages(id) on delete cascade,
  quality text not null check (quality in ('buena', 'mejorable', 'incorrecta')),
  problem text,
  reasoning text,
  lesson_id uuid references lessons(id),
  created_at timestamptz not null default now()
);

-- ============================================================
-- 6. TABLA DE DOCUMENTOS (Vector Store para RAG)
-- Aquí van los PDFs de los cursos de AtentaMente
-- ============================================================
create table documents (
  id uuid primary key default gen_random_uuid(),
  content text not null,
  embedding vector(1536),
  metadata jsonb not null default '{}',
  created_at timestamptz not null default now()
);

create index idx_documents_metadata on documents using gin(metadata);

-- ============================================================
-- 7. TRIGGER: actualiza updated_at en sessions automáticamente
-- ============================================================
create or replace function update_updated_at()
returns trigger language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create trigger sessions_updated_at
  before update on sessions
  for each row execute function update_updated_at();

-- ============================================================
-- 8. FUNCIÓN RPC: búsqueda semántica en documentos
-- La llama el agente principal para RAG
-- ============================================================
create or replace function match_documents(
  query_embedding vector(1536),
  match_count int default 5,
  filter jsonb default '{}'
)
returns table (
  id uuid,
  content text,
  metadata jsonb,
  similarity float
)
language plpgsql
as $$
begin
  return query
  select
    d.id,
    d.content,
    d.metadata,
    1 - (d.embedding <=> query_embedding) as similarity
  from documents d
  where
    d.embedding is not null
    and (filter = '{}' or d.metadata @> filter)
  order by d.embedding <=> query_embedding
  limit match_count;
end;
$$;

-- ============================================================
-- 9. FUNCIÓN RPC: búsqueda semántica en lecciones aprendidas
-- La llama el agente principal para inyectar lecciones relevantes
-- ============================================================
create or replace function match_lessons(
  query_embedding vector(1536),
  match_count int default 5
)
returns table (
  id uuid,
  trigger_desc text,
  rule text,
  reason text,
  similarity float
)
language plpgsql
as $$
begin
  return query
  select
    l.id,
    l.trigger_desc,
    l.rule,
    l.reason,
    1 - (l.embedding <=> query_embedding) as similarity
  from lessons l
  where
    l.active = true
    and l.embedding is not null
  order by l.embedding <=> query_embedding
  limit match_count;
end;
$$;

-- ============================================================
-- VERIFICACIÓN: corre esto al final para confirmar que todo existe
-- ============================================================
select table_name from information_schema.tables
where table_schema = 'public'
order by table_name;
