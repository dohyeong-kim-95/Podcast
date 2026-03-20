create table if not exists profiles (
    id text primary key,
    email text,
    display_name text,
    created_at timestamptz not null default timezone('utc', now()),
    last_login_at timestamptz not null default timezone('utc', now())
);

create table if not exists user_memory (
    user_id text primary key references profiles(id) on delete cascade,
    interests text not null default '',
    tone text not null default '',
    depth text not null default '',
    custom text not null default '',
    feedback_history jsonb not null default '[]'::jsonb,
    updated_at timestamptz not null default timezone('utc', now())
);

create table if not exists sources (
    id text primary key,
    user_id text not null references profiles(id) on delete cascade,
    file_name text not null,
    original_type text not null,
    converted_type text,
    original_storage_path text not null,
    converted_storage_path text,
    uploaded_at timestamptz not null default timezone('utc', now()),
    window_date date not null,
    status text not null
);

create index if not exists idx_sources_user_date_uploaded
    on sources (user_id, window_date, uploaded_at);

create table if not exists podcasts (
    id text primary key,
    user_id text not null references profiles(id) on delete cascade,
    date date not null,
    status text not null,
    source_ids jsonb not null default '[]'::jsonb,
    source_count integer not null default 0,
    audio_path text,
    duration_seconds integer,
    generated_at timestamptz,
    instructions_used text,
    error text,
    feedback text,
    downloaded boolean not null default false
);

create unique index if not exists idx_podcasts_user_date
    on podcasts (user_id, date);

create table if not exists nb_sessions (
    user_id text primary key references profiles(id) on delete cascade,
    storage_state text not null,
    auth_flow text not null default 'new_tab',
    status text not null default 'valid',
    expires_at timestamptz,
    last_updated timestamptz not null default timezone('utc', now())
);

create table if not exists nb_auth_sessions (
    session_id text primary key,
    user_id text not null references profiles(id) on delete cascade,
    status text not null,
    viewer_url text not null,
    auth_flow text not null default 'new_tab',
    started_at timestamptz,
    updated_at timestamptz not null default timezone('utc', now()),
    completed_at timestamptz,
    error text,
    nb_session_status text,
    expires_at timestamptz
);

create index if not exists idx_nb_auth_sessions_user_updated
    on nb_auth_sessions (user_id, updated_at desc);

create table if not exists push_subscriptions (
    user_id text primary key references profiles(id) on delete cascade,
    endpoint text not null,
    subscription jsonb not null,
    updated_at timestamptz not null default timezone('utc', now())
);
