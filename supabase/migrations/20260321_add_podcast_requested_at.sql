alter table podcasts
    add column if not exists requested_at timestamptz;

update podcasts
set requested_at = coalesce(requested_at, generated_at)
where requested_at is null;
