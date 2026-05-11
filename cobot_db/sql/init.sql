-- =============================================================================
-- cobot2 Supabase schema (feat/supabase-migration)
--
-- Apply order:
--   1) Extensions
--   2) Tables  (inventory -> inventory_logs FK; exception_logs standalone)
--   3) RPC     (decrement_inventory_atomic)
--   4) RLS     (publishable/anon key writes allowed via RPC + permissive insert)
--   5) Seed    (4 nuts x 1000)
--
-- Apply via:  Supabase Dashboard -> SQL Editor, paste this file, Run.
-- =============================================================================


-- ---------- 1) Extensions ----------------------------------------------------
create extension if not exists "uuid-ossp";


-- ---------- 2) Tables --------------------------------------------------------

-- 2-1) exception_logs : task-specific failure records
--   task_name is constrained to the two flows we track in cobot_task_manager:
--     - 'cluster_push'        (cluster_policy.py)
--     - 'verification_round'  (post-run verification loop in task_manager_node)
create table if not exists public.exception_logs (
    id            uuid primary key default uuid_generate_v4(),
    created_at    timestamptz not null default now(),
    task_name     text        not null
                  check (task_name in ('cluster_push', 'verification_round')),
    state         text        not null,
    error_code    int4        not null default 0,
    error_msg     text,
    target_class  text,
    target_xyz    jsonb,
    robot_pose    jsonb
);

create index if not exists exception_logs_created_at_idx
    on public.exception_logs (created_at desc);
create index if not exists exception_logs_task_name_idx
    on public.exception_logs (task_name, created_at desc);


-- 2-2) inventory : current stock per nut type (one row per class)
create table if not exists public.inventory (
    nut_type       text  primary key
                   check (nut_type in ('almond', 'cashew', 'pistachio', 'walnut')),
    current_stock  int4  not null default 1000
                   check (current_stock >= 0)
);


-- 2-3) inventory_logs : every stock change, append-only ledger
create table if not exists public.inventory_logs (
    id             uuid        primary key default uuid_generate_v4(),
    nut_type       text        not null references public.inventory(nut_type)
                                on update cascade on delete restrict,
    change_amount  int4        not null,
    reason         text        not null,
    created_at     timestamptz not null default now()
);

create index if not exists inventory_logs_nut_type_idx
    on public.inventory_logs (nut_type, created_at desc);


-- ---------- 3) Atomic decrement RPC -----------------------------------------
-- Single-statement UPDATE + INSERT inside one transaction, executed
-- server-side so two concurrent callers cannot race on current_stock.
-- SECURITY DEFINER lets anon-key callers run it without granting raw
-- UPDATE/INSERT privileges on the underlying tables.
--
-- change_amount semantics: SIGNED.
--   -1, -2, ...  -> deduction (pick success)
--   +N           -> refill
-- Refuses to drive current_stock below zero.
create or replace function public.update_inventory_atomic(
    p_nut_type      text,
    p_change_amount int4,
    p_reason        text
)
returns table (nut_type text, current_stock int4)
language plpgsql
security definer
set search_path = public
as $$
declare
    v_new_stock int4;
begin
    if p_nut_type not in ('almond', 'cashew', 'pistachio', 'walnut') then
        raise exception 'invalid nut_type: %', p_nut_type
            using errcode = '22023';
    end if;
    if p_change_amount = 0 then
        raise exception 'change_amount must be non-zero'
            using errcode = '22023';
    end if;

    update public.inventory inv
       set current_stock = inv.current_stock + p_change_amount
     where inv.nut_type = p_nut_type
     returning inv.current_stock into v_new_stock;

    if v_new_stock is null then
        raise exception 'nut_type not found in inventory: %', p_nut_type
            using errcode = 'P0002';
    end if;

    -- the CHECK (current_stock >= 0) above already rejects underflow with
    -- a CHECK violation, but we surface a clearer error here.
    if v_new_stock < 0 then
        raise exception 'insufficient stock for %: would go to %',
            p_nut_type, v_new_stock
            using errcode = '23514';
    end if;

    insert into public.inventory_logs (nut_type, change_amount, reason)
    values (p_nut_type, p_change_amount, p_reason);

    return query
        select p_nut_type, v_new_stock;
end;
$$;

-- Allow publishable/anon key to invoke the RPC.
grant execute on function public.update_inventory_atomic(text, int4, text) to anon;
grant execute on function public.update_inventory_atomic(text, int4, text) to authenticated;


-- ---------- 4) Row Level Security -------------------------------------------
-- Robot runs with the publishable (anon) key.
-- Policy choice:
--   - inventory          : read-only for anon; writes only via RPC.
--   - inventory_logs     : read-only for anon; inserts only via RPC.
--   - exception_logs     : anon may INSERT + SELECT (the robot writes its
--                          own failure records directly; no aggregation needed).

alter table public.inventory        enable row level security;
alter table public.inventory_logs   enable row level security;
alter table public.exception_logs   enable row level security;

drop policy if exists inventory_read_anon         on public.inventory;
drop policy if exists inventory_logs_read_anon    on public.inventory_logs;
drop policy if exists exception_logs_read_anon    on public.exception_logs;
drop policy if exists exception_logs_insert_anon  on public.exception_logs;

create policy inventory_read_anon
    on public.inventory
    for select to anon, authenticated
    using (true);

create policy inventory_logs_read_anon
    on public.inventory_logs
    for select to anon, authenticated
    using (true);

create policy exception_logs_read_anon
    on public.exception_logs
    for select to anon, authenticated
    using (true);

create policy exception_logs_insert_anon
    on public.exception_logs
    for insert to anon, authenticated
    with check (true);


-- ---------- 5) Seed initial stock -------------------------------------------
-- Idempotent: re-running this file does not reset stock that has been picked.
insert into public.inventory (nut_type, current_stock) values
    ('almond',    1000),
    ('cashew',    1000),
    ('pistachio', 1000),
    ('walnut',    1000)
on conflict (nut_type) do nothing;


-- =============================================================================
-- robot_session : single-row interop table between web (web_stt_supabase_v2)
-- and ROS (task_manager / status bridge). Mirrors the Firestore
-- `robot_session/current` doc 1:1.
-- =============================================================================

create table if not exists public.robot_session (
    id                  text          primary key default 'current',
    display_state       text          not null default 'idle',
    question            text          not null default '',
    transcript          text          not null default '',
    categories          jsonb         not null default '[]'::jsonb,   -- NutClass[]
    intensity           text          not null default 'normal',
    combo               jsonb         not null default '[]'::jsonb,   -- NutComboItem[]
    combo_text          text          not null default '',
    confirm_message     text          not null default '',
    success             boolean       not null default false,
    theme               jsonb         not null default '{}'::jsonb,
    error               text          not null default '',
    robot_state         text,
    robot_target_class  text,
    request_id          text,
    updated_at          timestamptz   not null default now(),
    constraint robot_session_singleton check (id = 'current')
);

-- Mirror Firestore's serverTimestamp(): bump updated_at on every UPDATE.
create or replace function public.touch_updated_at()
returns trigger
language plpgsql
as $$
begin
    new.updated_at := now();
    return new;
end;
$$;

drop trigger if exists robot_session_touch on public.robot_session;
create trigger robot_session_touch
    before update on public.robot_session
    for each row execute function public.touch_updated_at();

-- RLS: anon (publishable key) can read AND write the session.
-- This matches the Firestore trust model: the browser is the authoritative
-- writer of voice-flow fields, and the ROS bridge writes robot_state.
-- There's no per-user data in this table.
alter table public.robot_session enable row level security;

drop policy if exists robot_session_read_anon  on public.robot_session;
drop policy if exists robot_session_write_anon on public.robot_session;

create policy robot_session_read_anon
    on public.robot_session
    for select to anon, authenticated using (true);

create policy robot_session_write_anon
    on public.robot_session
    for all to anon, authenticated
    using (true) with check (true);

-- Enable Realtime for this table (idempotent — guard with pg_publication_tables).
do $$
begin
    if not exists (
        select 1 from pg_publication_tables
        where pubname = 'supabase_realtime'
          and schemaname = 'public'
          and tablename = 'robot_session'
    ) then
        alter publication supabase_realtime add table public.robot_session;
    end if;
end $$;

-- Seed the singleton row.
insert into public.robot_session (id) values ('current')
on conflict (id) do nothing;
