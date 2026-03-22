-- Store encrypted Google OAuth tokens for server-side NotebookLM cookie exchange.
create table if not exists google_tokens (
    user_id text primary key references profiles(id) on delete cascade,
    encrypted_refresh_token text not null,
    encrypted_access_token text,
    token_scope text,
    created_at timestamptz not null default timezone('utc', now()),
    updated_at timestamptz not null default timezone('utc', now())
);
