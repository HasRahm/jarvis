-- Phase 25 — Supabase-backed async brain
-- Memory table for Jarvis's direct read/write path (brain_get / brain_write /
-- the Supabase-first half of brain_query). Lives in `public` so PostgREST
-- serves it with the default exposed-schema config.
--
-- Apply via the Supabase MCP apply_migration tool (after restoring the project)
-- or: psql "$DATABASE_URL" -f scripts/supabase_jarvis_memory.sql

create table if not exists public.jarvis_memory (
  slug          text primary key,
  content       text not null default '',
  namespace     text generated always as (split_part(slug, '/', 1)) stored,
  updated_at    timestamptz not null default now(),
  search_vector tsvector generated always as (
    to_tsvector('english', coalesce(slug, '') || ' ' || coalesce(content, ''))
  ) stored
);

create index if not exists jarvis_memory_search_idx
  on public.jarvis_memory using gin (search_vector);

create index if not exists jarvis_memory_namespace_idx
  on public.jarvis_memory (namespace);

-- Keep updated_at fresh on upsert-as-update.
create or replace function public.jarvis_memory_touch() returns trigger
  language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end $$;

drop trigger if exists jarvis_memory_touch_trg on public.jarvis_memory;
create trigger jarvis_memory_touch_trg
  before update on public.jarvis_memory
  for each row execute function public.jarvis_memory_touch();
