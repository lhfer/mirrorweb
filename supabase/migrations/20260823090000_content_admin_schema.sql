begin;

create schema if not exists private;

revoke all on schema private from public, anon, authenticated, service_role;

create table public.admin_users (
  user_id uuid primary key references auth.users (id) on delete cascade,
  email text not null,
  created_at timestamptz not null default now(),
  constraint admin_users_email_present check (char_length(btrim(email)) between 3 and 320)
);

create unique index admin_users_email_lower_key
  on public.admin_users (lower(email));

create table public.media_assets (
  id uuid primary key default gen_random_uuid(),
  original_name text not null,
  storage_path text not null unique,
  poster_path text,
  media_url text not null,
  poster_url text,
  mime_type text not null,
  size_bytes bigint,
  width integer,
  height integer,
  duration_ms integer,
  status text not null default 'uploading',
  sha256 text,
  purge_requested_at timestamptz,
  created_by uuid references auth.users (id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint media_assets_original_name_present
    check (char_length(btrim(original_name)) between 1 and 512),
  constraint media_assets_storage_path_present
    check (
      char_length(btrim(storage_path)) between 1 and 1024
      and storage_path !~ '(^/|(^|/)\.\.(/|$)|[[:cntrl:]])'
    ),
  constraint media_assets_poster_path_safe
    check (
      poster_path is null
      or (
        char_length(btrim(poster_path)) between 1 and 1024
        and poster_path !~ '(^/|(^|/)\.\.(/|$)|[[:cntrl:]])'
      )
    ),
  constraint media_assets_poster_path_url_parity
    check ((poster_path is null) = (poster_url is null)),
  constraint media_assets_mime_type_supported
    check (mime_type = 'video/mp4'),
  constraint media_assets_size_nonnegative
    check (size_bytes is null or size_bytes >= 0),
  constraint media_assets_width_positive
    check (width is null or width > 0),
  constraint media_assets_height_positive
    check (height is null or height > 0),
  constraint media_assets_duration_positive
    check (duration_ms is null or duration_ms > 0),
  constraint media_assets_status_valid
    check (status in ('uploading', 'ready', 'archived', 'failed')),
  constraint media_assets_sha256_valid
    check (sha256 is null or sha256 ~ '^[0-9a-f]{64}$')
);

create unique index media_assets_poster_path_key
  on public.media_assets (poster_path)
  where poster_path is not null;

create unique index media_assets_media_url_key
  on public.media_assets (media_url);

create unique index media_assets_poster_url_key
  on public.media_assets (poster_url)
  where poster_url is not null;

create index media_assets_status_created_at_idx
  on public.media_assets (status, created_at desc);

create index media_assets_created_by_idx
  on public.media_assets (created_by)
  where created_by is not null;

create index media_assets_sha256_idx
  on public.media_assets (sha256)
  where sha256 is not null;

create table public.content_drafts (
  id uuid primary key,
  manifest jsonb not null,
  revision integer not null default 0,
  updated_by uuid references auth.users (id) on delete set null,
  updated_at timestamptz not null default now(),
  constraint content_drafts_singleton
    check (id = '00000000-0000-4000-8000-000000000001'::uuid),
  constraint content_drafts_revision_nonnegative check (revision >= 0)
);

create index content_drafts_updated_by_idx
  on public.content_drafts (updated_by)
  where updated_by is not null;

create table public.content_versions (
  id uuid primary key default gen_random_uuid(),
  version integer not null unique,
  manifest jsonb not null,
  created_by uuid references auth.users (id) on delete set null,
  created_at timestamptz not null default now(),
  release_note text,
  constraint content_versions_version_positive check (version > 0),
  constraint content_versions_release_note_length
    check (release_note is null or char_length(release_note) <= 500)
);

create index content_versions_created_by_idx
  on public.content_versions (created_by)
  where created_by is not null;

create index content_versions_created_at_idx
  on public.content_versions (created_at desc);

create table public.site_state (
  singleton boolean primary key default true,
  active_version_id uuid not null references public.content_versions (id) on delete restrict,
  updated_at timestamptz not null default now(),
  constraint site_state_singleton check (singleton)
);

create index site_state_active_version_id_idx
  on public.site_state (active_version_id);

create or replace function private.is_nonempty_text(
  p_value text,
  p_max_length integer
)
returns boolean
language sql
immutable
strict
parallel safe
security invoker
set search_path = ''
as $$
  select
    char_length(btrim(p_value)) between 1 and p_max_length
    and p_value !~ '[[:cntrl:]]';
$$;

create or replace function private.is_hex_colour(p_value text)
returns boolean
language sql
immutable
strict
parallel safe
security invoker
set search_path = ''
as $$
  select p_value ~ '^#[0-9A-Fa-f]{6}$';
$$;

create or replace function private.is_https_url(p_value text)
returns boolean
language sql
immutable
strict
parallel safe
security invoker
set search_path = ''
as $$
  select
    char_length(p_value) between 9 and 2048
    and p_value ~ '^https://[^[:space:]<>]+$'
    and split_part(
      split_part(
        split_part(substring(p_value from 9), '/', 1),
        '?',
        1
      ),
      '#',
      1
    ) <> ''
    and split_part(
      split_part(
        split_part(substring(p_value from 9), '/', 1),
        '?',
        1
      ),
      '#',
      1
    ) !~ '@';
$$;

create or replace function private.is_cta_url(p_value text)
returns boolean
language sql
immutable
strict
parallel safe
security invoker
set search_path = ''
as $$
  select
    private.is_https_url(p_value)
    or (
      char_length(p_value) between 8 and 2048
      and p_value ~ '^mailto:[^[:space:]<>@]+@[^[:space:]<>@]+$'
    );
$$;

create or replace function private.is_media_url(p_value text)
returns boolean
language sql
immutable
strict
parallel safe
security invoker
set search_path = ''
as $$
  select
    private.is_https_url(p_value)
    or (
      char_length(p_value) between 2 and 2048
      and left(p_value, 1) = '/'
      and left(p_value, 2) <> '//'
      and p_value !~ '[[:space:]<>]'
      and strpos(p_value, chr(92)) = 0
    );
$$;

alter table public.media_assets
  add constraint media_assets_media_url_safe
    check (private.is_media_url(media_url)),
  add constraint media_assets_poster_url_safe
    check (poster_url is null or private.is_media_url(poster_url));

create or replace function private.validate_content_manifest(
  p_manifest jsonb,
  p_require_ready_media boolean
)
returns void
language plpgsql
security invoker
set search_path = ''
as $$
declare
  v_cards jsonb;
  v_card jsonb;
  v_site jsonb;
  v_palette_item jsonb;
  v_media_id uuid;
  v_media_status text;
  v_purge_requested_at timestamptz;
  v_media_url text;
  v_poster_url text;
  v_storage_path text;
  v_poster_path text;
  v_media_created_by uuid;
  v_is_bundled_seed boolean;
  v_focus_x numeric;
  v_focus_y numeric;
  v_zoom numeric;
  v_card_count integer;
  v_distinct_count integer;
begin
  if p_manifest is null or jsonb_typeof(p_manifest) <> 'object' then
    raise exception using
      errcode = '22023',
      message = 'manifest must be a JSON object';
  end if;

  if not (p_manifest ?& array['schemaVersion', 'version', 'cards', 'site']) then
    raise exception using
      errcode = '22023',
      message = 'manifest is missing a required top-level field';
  end if;

  if exists (
    select 1
      from jsonb_object_keys(p_manifest) as manifest_key(key)
      where manifest_key.key not in ('schemaVersion', 'version', 'cards', 'site')
  ) then
    raise exception using
      errcode = '22023',
      message = 'manifest contains an unsupported top-level field';
  end if;

  if jsonb_typeof(p_manifest -> 'schemaVersion') <> 'number'
     or p_manifest ->> 'schemaVersion' <> '1' then
    raise exception using
      errcode = '22023',
      message = 'manifest schemaVersion must be 1';
  end if;

  if jsonb_typeof(p_manifest -> 'version') <> 'number'
     or (p_manifest ->> 'version') !~ '^[0-9]+$' then
    raise exception using
      errcode = '22023',
      message = 'manifest version must be a non-negative integer';
  end if;

  v_cards := p_manifest -> 'cards';
  if jsonb_typeof(v_cards) <> 'array' or jsonb_array_length(v_cards) = 0 then
    raise exception using
      errcode = '22023',
      message = 'manifest must contain at least one card';
  end if;
  if jsonb_array_length(v_cards) > 256 then
    raise exception using
      errcode = '22023',
      message = 'manifest cannot contain more than 256 cards';
  end if;

  for v_card in
    select value from jsonb_array_elements(v_cards)
  loop
    if jsonb_typeof(v_card) <> 'object' then
      raise exception using
        errcode = '22023',
        message = 'each card must be a JSON object';
    end if;

    if not (
      v_card ?& array[
        'id', 'code', 'category', 'title', 'deck', 'accent', 'palette',
        'mediaAssetId', 'mediaUrl', 'focusX', 'focusY', 'zoom',
        'enabled', 'sortOrder'
      ]
    ) then
      raise exception using
        errcode = '22023',
        message = 'card is missing a required field';
    end if;

    if exists (
      select 1
        from jsonb_object_keys(v_card) as card_key(key)
        where card_key.key not in (
          'id', 'code', 'category', 'title', 'deck', 'accent', 'palette',
          'mediaAssetId', 'mediaUrl', 'posterUrl', 'focusX', 'focusY',
          'zoom', 'enabled', 'sortOrder'
        )
    ) then
      raise exception using
        errcode = '22023',
        message = 'card contains an unsupported field';
    end if;

    if jsonb_typeof(v_card -> 'id') <> 'string'
       or not private.is_nonempty_text(v_card ->> 'id', 128)
       or (v_card ->> 'id') !~ '^[A-Za-z0-9][A-Za-z0-9._:-]*$' then
      raise exception using errcode = '22023', message = 'card id is invalid';
    end if;

    if jsonb_typeof(v_card -> 'code') <> 'string'
       or not private.is_nonempty_text(v_card ->> 'code', 64) then
      raise exception using errcode = '22023', message = 'card code is invalid';
    end if;

    if jsonb_typeof(v_card -> 'category') <> 'string'
       or not private.is_nonempty_text(v_card ->> 'category', 80) then
      raise exception using errcode = '22023', message = 'card category is invalid';
    end if;

    if jsonb_typeof(v_card -> 'title') <> 'string'
       or not private.is_nonempty_text(v_card ->> 'title', 120) then
      raise exception using errcode = '22023', message = 'card title is invalid';
    end if;

    if jsonb_typeof(v_card -> 'deck') <> 'string'
       or not private.is_nonempty_text(v_card ->> 'deck', 280) then
      raise exception using errcode = '22023', message = 'card deck is invalid';
    end if;

    if jsonb_typeof(v_card -> 'accent') <> 'string'
       or not private.is_hex_colour(v_card ->> 'accent') then
      raise exception using errcode = '22023', message = 'card accent is invalid';
    end if;

    if jsonb_typeof(v_card -> 'palette') <> 'array'
       or jsonb_array_length(v_card -> 'palette') <> 4 then
      raise exception using
        errcode = '22023',
        message = 'card palette must contain exactly four colours';
    end if;

    for v_palette_item in
      select value from jsonb_array_elements(v_card -> 'palette')
    loop
      if jsonb_typeof(v_palette_item) <> 'string'
         or not private.is_hex_colour(v_palette_item #>> '{}') then
        raise exception using
          errcode = '22023',
          message = 'card palette contains an invalid colour';
      end if;
    end loop;

    if jsonb_typeof(v_card -> 'mediaAssetId') <> 'string'
       or (v_card ->> 'mediaAssetId') !~* '^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$' then
      raise exception using errcode = '22023', message = 'card mediaAssetId is invalid';
    end if;

    if jsonb_typeof(v_card -> 'mediaUrl') <> 'string'
       or not private.is_media_url(v_card ->> 'mediaUrl') then
      raise exception using errcode = '22023', message = 'card mediaUrl is invalid';
    end if;

    if v_card ? 'posterUrl' then
      if jsonb_typeof(v_card -> 'posterUrl') <> 'string'
         or not private.is_media_url(v_card ->> 'posterUrl') then
        raise exception using errcode = '22023', message = 'card posterUrl is invalid';
      end if;
    end if;

    if jsonb_typeof(v_card -> 'focusX') <> 'number'
       or jsonb_typeof(v_card -> 'focusY') <> 'number'
       or jsonb_typeof(v_card -> 'zoom') <> 'number' then
      raise exception using
        errcode = '22023',
        message = 'card focus and zoom values must be numbers';
    end if;

    v_focus_x := (v_card ->> 'focusX')::numeric;
    v_focus_y := (v_card ->> 'focusY')::numeric;
    v_zoom := (v_card ->> 'zoom')::numeric;
    if v_focus_x < 0 or v_focus_x > 1
       or v_focus_y < 0 or v_focus_y > 1
       or v_zoom < 1 or v_zoom > 1.5 then
      raise exception using
        errcode = '22023',
        message = 'card focus must be within [0,1] and zoom within [1,1.5]';
    end if;

    if jsonb_typeof(v_card -> 'enabled') <> 'boolean' then
      raise exception using errcode = '22023', message = 'card enabled must be boolean';
    end if;

    if jsonb_typeof(v_card -> 'sortOrder') <> 'number'
       or (v_card ->> 'sortOrder') !~ '^[0-9]+$' then
      raise exception using
        errcode = '22023',
        message = 'card sortOrder must be a non-negative integer';
    end if;

    v_media_id := (v_card ->> 'mediaAssetId')::uuid;
    select
      media.status,
      media.purge_requested_at,
      media.media_url,
      media.poster_url,
      media.storage_path,
      media.poster_path,
      media.created_by
      into
        v_media_status,
        v_purge_requested_at,
        v_media_url,
        v_poster_url,
        v_storage_path,
        v_poster_path,
        v_media_created_by
      from public.media_assets as media
      where media.id = v_media_id;

    if not found then
      raise exception using
        errcode = '23503',
        message = format('card references missing media asset %s', v_media_id);
    end if;

    v_is_bundled_seed :=
      v_media_created_by is null
      and v_poster_path is null
      and v_poster_url is null
      and (
        (
          v_media_id = '11111111-1111-4111-8111-111111111111'::uuid
          and v_storage_path = 'bundled/niulai-intro.mp4'
          and v_media_url = '/clips/niulai-intro.mp4'
        )
        or (
          v_media_id = '22222222-2222-4222-8222-222222222222'::uuid
          and v_storage_path = 'bundled/cursor-niulai.mp4'
          and v_media_url = '/clips/cursor-niulai.mp4'
        )
        or (
          v_media_id = '33333333-3333-4333-8333-333333333333'::uuid
          and v_storage_path = 'bundled/pelican-ai.mp4'
          and v_media_url = '/clips/pelican-ai.mp4'
        )
      );

    if v_purge_requested_at is not null then
      raise exception using
        errcode = '55000',
        message = format('card references media asset %s pending purge', v_media_id);
    end if;

    if (v_card ->> 'mediaUrl') is distinct from v_media_url
       or (v_card ->> 'posterUrl') is distinct from v_poster_url then
      raise exception using
        errcode = '22023',
        message = format(
          'card URLs do not match canonical media asset %s',
          v_media_id
        );
    end if;

    if p_require_ready_media and v_media_status <> 'ready' then
      raise exception using
        errcode = '22023',
        message = format('media asset %s is not ready to publish', v_media_id);
    end if;

    if not p_require_ready_media and v_media_status not in ('ready', 'archived') then
      raise exception using
        errcode = '22023',
        message = format('media asset %s is not usable by a draft', v_media_id);
    end if;

    if p_require_ready_media and not v_is_bundled_seed and not exists (
      select 1
        from storage.objects as object
        where object.bucket_id = 'card-media'
          and object.name = v_storage_path
    ) then
      raise exception using
        errcode = '23503',
        message = format('media asset %s has no uploaded video object', v_media_id);
    end if;

    if p_require_ready_media and v_poster_path is not null
       and not exists (
         select 1
           from storage.objects as object
           where object.bucket_id = 'card-media'
             and object.name = v_poster_path
       ) then
      raise exception using
        errcode = '23503',
        message = format('media asset %s has no uploaded poster object', v_media_id);
    end if;
  end loop;

  select count(*), count(distinct card.value ->> 'id')
    into v_card_count, v_distinct_count
    from jsonb_array_elements(v_cards) as card(value);
  if v_card_count <> v_distinct_count then
    raise exception using errcode = '22023', message = 'card ids must be unique';
  end if;

  select count(*), count(distinct card.value ->> 'code')
    into v_card_count, v_distinct_count
    from jsonb_array_elements(v_cards) as card(value);
  if v_card_count <> v_distinct_count then
    raise exception using errcode = '22023', message = 'card codes must be unique';
  end if;

  select count(*), count(distinct (card.value ->> 'sortOrder')::integer)
    into v_card_count, v_distinct_count
    from jsonb_array_elements(v_cards) as card(value);
  if v_card_count <> v_distinct_count then
    raise exception using errcode = '22023', message = 'card sortOrder values must be unique';
  end if;

  if exists (
    select 1
      from jsonb_array_elements(v_cards) as card(value)
      group by card.value ->> 'mediaAssetId'
      having count(distinct card.value ->> 'mediaUrl') > 1
         or count(
           distinct coalesce(
             nullif(card.value ->> 'posterUrl', 'null'),
             ''
           )
         ) > 1
  ) then
    raise exception using
      errcode = '22023',
      message = 'one mediaAssetId cannot map to multiple media or poster URLs';
  end if;

  if not exists (
    select 1
      from jsonb_array_elements(v_cards) as card(value)
      where (card.value ->> 'enabled')::boolean
  ) then
    raise exception using
      errcode = '22023',
      message = 'manifest must contain at least one enabled card';
  end if;

  v_site := p_manifest -> 'site';
  if jsonb_typeof(v_site) <> 'object'
     or not (
       v_site ?& array[
         'footerCaption', 'brandText', 'brandUrl', 'ctaLabel', 'ctaUrl',
         'loaderBrandText'
       ]
     ) then
    raise exception using
      errcode = '22023',
      message = 'manifest site settings are invalid';
  end if;

  if exists (
    select 1
      from jsonb_object_keys(v_site) as site_key(key)
      where site_key.key not in (
        'footerCaption', 'brandText', 'brandUrl', 'ctaLabel', 'ctaUrl',
        'loaderBrandText'
      )
  ) then
    raise exception using
      errcode = '22023',
      message = 'site settings contain an unsupported field';
  end if;

  if jsonb_typeof(v_site -> 'footerCaption') <> 'string'
     or not private.is_nonempty_text(v_site ->> 'footerCaption', 120) then
    raise exception using errcode = '22023', message = 'footerCaption is invalid';
  end if;

  if jsonb_typeof(v_site -> 'brandText') <> 'string'
     or not private.is_nonempty_text(v_site ->> 'brandText', 80) then
    raise exception using errcode = '22023', message = 'brandText is invalid';
  end if;

  if jsonb_typeof(v_site -> 'brandUrl') <> 'string'
     or not private.is_https_url(v_site ->> 'brandUrl') then
    raise exception using errcode = '22023', message = 'brandUrl must use https';
  end if;

  if jsonb_typeof(v_site -> 'ctaLabel') <> 'string'
     or not private.is_nonempty_text(v_site ->> 'ctaLabel', 80) then
    raise exception using errcode = '22023', message = 'ctaLabel is invalid';
  end if;

  if jsonb_typeof(v_site -> 'ctaUrl') <> 'string'
     or not private.is_cta_url(v_site ->> 'ctaUrl') then
    raise exception using
      errcode = '22023',
      message = 'ctaUrl must use https or mailto';
  end if;

  if jsonb_typeof(v_site -> 'loaderBrandText') <> 'string'
     or not private.is_nonempty_text(v_site ->> 'loaderBrandText', 80) then
    raise exception using errcode = '22023', message = 'loaderBrandText is invalid';
  end if;
end;
$$;

create or replace function private.touch_updated_at()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
  new.updated_at := now();
  return new;
end;
$$;

create or replace function private.guard_media_asset_update()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
  if new.id is distinct from old.id
     or new.created_by is distinct from old.created_by
     or new.created_at is distinct from old.created_at
     or new.storage_path is distinct from old.storage_path
     or new.poster_path is distinct from old.poster_path
     or new.media_url is distinct from old.media_url
     or new.poster_url is distinct from old.poster_url then
    raise exception using
      errcode = '22023',
      message = 'media asset identity, creator, paths, and public URLs are immutable';
  end if;

  if current_user = 'authenticated'
     and new.status is distinct from old.status
     and not (
       (old.status = 'uploading' and new.status in ('ready', 'failed'))
       or (old.status = 'failed' and new.status = 'uploading')
     ) then
    raise exception using
      errcode = '42501',
      message = 'this media status transition requires a guarded RPC';
  end if;

  if current_user in ('anon', 'authenticated')
     and new.purge_requested_at is distinct from old.purge_requested_at then
    raise exception using
      errcode = '42501',
      message = 'purge state may only be changed through purge RPCs';
  end if;

  if current_user in ('anon', 'authenticated')
     and old.purge_requested_at is not null then
    raise exception using
      errcode = '55000',
      message = 'media asset metadata is locked while purge is in progress';
  end if;

  return new;
end;
$$;

create or replace function private.guard_content_draft_write()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
  perform private.validate_content_manifest(new.manifest, false);

  if tg_op = 'UPDATE' then
    if new.id is distinct from old.id then
      raise exception using errcode = '22023', message = 'draft id is immutable';
    end if;
    if new.revision <> old.revision + 1 then
      raise exception using
        errcode = '22023',
        message = 'draft revision must increase by exactly one';
    end if;
  end if;

  return new;
end;
$$;

create or replace function private.guard_content_version_insert()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
  perform private.validate_content_manifest(new.manifest, true);
  if (new.manifest ->> 'version') !~ '^[0-9]+$'
     or (new.manifest ->> 'version')::integer <> new.version then
    raise exception using
      errcode = '22023',
      message = 'content version row and manifest version must match';
  end if;
  return new;
end;
$$;

create or replace function private.reject_content_version_mutation()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
  raise exception using
    errcode = '55000',
    message = 'published content versions are immutable';
end;
$$;

create trigger media_assets_10_guard_update
before update on public.media_assets
for each row execute function private.guard_media_asset_update();

create trigger media_assets_90_touch_updated_at
before update on public.media_assets
for each row execute function private.touch_updated_at();

create trigger content_drafts_10_validate
before insert or update on public.content_drafts
for each row execute function private.guard_content_draft_write();

create trigger content_drafts_90_touch_updated_at
before update on public.content_drafts
for each row execute function private.touch_updated_at();

create trigger content_versions_10_validate_insert
before insert on public.content_versions
for each row execute function private.guard_content_version_insert();

create trigger content_versions_20_reject_mutation
before update or delete on public.content_versions
for each row execute function private.reject_content_version_mutation();

create trigger site_state_90_touch_updated_at
before update on public.site_state
for each row execute function private.touch_updated_at();

alter table public.admin_users enable row level security;
alter table public.media_assets enable row level security;
alter table public.content_drafts enable row level security;
alter table public.content_versions enable row level security;
alter table public.site_state enable row level security;

revoke all on table public.admin_users from anon, authenticated;
revoke all on table public.media_assets from anon, authenticated;
revoke all on table public.content_drafts from anon, authenticated;
revoke all on table public.content_versions from anon, authenticated;
revoke all on table public.site_state from anon, authenticated;

grant select on table public.admin_users to authenticated;
grant select, insert, update on table public.media_assets to authenticated;
grant select on table public.content_drafts to authenticated;
grant select on table public.content_versions to authenticated;
grant select on table public.site_state to authenticated;

create policy admin_users_select_self
on public.admin_users
for select
to authenticated
using ((select auth.uid()) is not null and user_id = (select auth.uid()));

create policy media_assets_admin_select
on public.media_assets
for select
to authenticated
using (
  exists (
    select 1
      from public.admin_users as admins
      where admins.user_id = (select auth.uid())
  )
);

create policy media_assets_admin_insert
on public.media_assets
for insert
to authenticated
with check (
  created_by = (select auth.uid())
  and status = 'uploading'
  and purge_requested_at is null
  and exists (
    select 1
      from public.admin_users as admins
      where admins.user_id = (select auth.uid())
  )
);

create policy media_assets_admin_update
on public.media_assets
for update
to authenticated
using (
  exists (
    select 1
      from public.admin_users as admins
      where admins.user_id = (select auth.uid())
  )
)
with check (
  exists (
    select 1
      from public.admin_users as admins
      where admins.user_id = (select auth.uid())
  )
);

create policy content_drafts_admin_select
on public.content_drafts
for select
to authenticated
using (
  exists (
    select 1
      from public.admin_users as admins
      where admins.user_id = (select auth.uid())
  )
);

create policy content_versions_admin_select
on public.content_versions
for select
to authenticated
using (
  exists (
    select 1
      from public.admin_users as admins
      where admins.user_id = (select auth.uid())
  )
);

create policy site_state_admin_select
on public.site_state
for select
to authenticated
using (
  exists (
    select 1
      from public.admin_users as admins
      where admins.user_id = (select auth.uid())
  )
);

create or replace function private.require_content_admin()
returns uuid
language plpgsql
stable
security invoker
set search_path = ''
as $$
declare
  v_user_id uuid := (select auth.uid());
begin
  if v_user_id is null or not exists (
    select 1 from public.admin_users where user_id = v_user_id
  ) then
    raise exception using
      errcode = '42501',
      message = 'content administrator access required';
  end if;
  return v_user_id;
end;
$$;

create or replace function private.get_active_content_manifest_impl()
returns jsonb
language sql
stable
security definer
set search_path = ''
as $$
  select versions.manifest
    from public.site_state as state
    join public.content_versions as versions
      on versions.id = state.active_version_id
    where state.singleton;
$$;

create or replace function private.save_content_draft_impl(
  p_expected_revision integer,
  p_manifest jsonb
)
returns jsonb
language plpgsql
volatile
security definer
set search_path = ''
as $$
declare
  v_user_id uuid;
  v_draft public.content_drafts%rowtype;
begin
  v_user_id := private.require_content_admin();

  select draft.*
    into v_draft
    from public.content_drafts as draft
    where draft.id = '00000000-0000-4000-8000-000000000001'::uuid
    for update;

  if not found then
    raise exception using
      errcode = '55000',
      message = 'content draft singleton is not initialized';
  end if;

  if v_draft.revision <> p_expected_revision then
    raise exception using
      errcode = '40001',
      message = format(
        'stale draft revision: expected %s, actual %s',
        p_expected_revision,
        v_draft.revision
      );
  end if;

  perform private.validate_content_manifest(p_manifest, false);

  update public.content_drafts as draft
    set manifest = p_manifest,
        revision = draft.revision + 1,
        updated_by = v_user_id
    where draft.id = v_draft.id
    returning draft.* into v_draft;

  return jsonb_build_object(
    'id', v_draft.id,
    'manifest', v_draft.manifest,
    'revision', v_draft.revision,
    'updatedBy', v_draft.updated_by,
    'updatedAt', v_draft.updated_at
  );
end;
$$;

create or replace function private.publish_content_impl(
  p_expected_revision integer,
  p_release_note text
)
returns jsonb
language plpgsql
volatile
security definer
set search_path = ''
as $$
declare
  v_user_id uuid;
  v_draft public.content_drafts%rowtype;
  v_version public.content_versions%rowtype;
  v_next_version integer;
  v_manifest jsonb;
  v_release_note text := nullif(btrim(p_release_note), '');
begin
  v_user_id := private.require_content_admin();

  if v_release_note is not null and char_length(v_release_note) > 500 then
    raise exception using
      errcode = '22023',
      message = 'release note must be 500 characters or fewer';
  end if;

  select draft.*
    into v_draft
    from public.content_drafts as draft
    where draft.id = '00000000-0000-4000-8000-000000000001'::uuid
    for update;

  if not found then
    raise exception using
      errcode = '55000',
      message = 'content draft singleton is not initialized';
  end if;

  if v_draft.revision <> p_expected_revision then
    raise exception using
      errcode = '40001',
      message = format(
        'stale draft revision: expected %s, actual %s',
        p_expected_revision,
        v_draft.revision
      );
  end if;

  -- Hold every referenced media status and canonical path stable until the
  -- immutable version and active pointer commit. The ordered lock also keeps
  -- concurrent archive operations from landing between validation and insert.
  perform 1
    from public.media_assets as media
    where media.id in (
      select distinct (card.value ->> 'mediaAssetId')::uuid
        from jsonb_array_elements(v_draft.manifest -> 'cards') as card(value)
    )
    order by media.id
    for share;

  perform private.validate_content_manifest(v_draft.manifest, true);

  select coalesce(max(versions.version), 0) + 1
    into v_next_version
    from public.content_versions as versions;

  v_manifest := jsonb_set(
    v_draft.manifest,
    '{version}',
    to_jsonb(v_next_version),
    true
  );

  insert into public.content_versions (
    version,
    manifest,
    created_by,
    release_note
  )
  values (
    v_next_version,
    v_manifest,
    v_user_id,
    v_release_note
  )
  returning * into v_version;

  insert into public.site_state (singleton, active_version_id)
  values (true, v_version.id)
  on conflict (singleton) do update
    set active_version_id = excluded.active_version_id,
        updated_at = now();

  update public.content_drafts as draft
    set manifest = v_manifest,
        revision = draft.revision + 1,
        updated_by = v_user_id
    where draft.id = v_draft.id
    returning draft.* into v_draft;

  return jsonb_build_object(
    'id', v_version.id,
    'version', v_version.version,
    'manifest', v_version.manifest,
    'createdBy', v_version.created_by,
    'createdAt', v_version.created_at,
    'releaseNote', v_version.release_note,
    'draftRevision', v_draft.revision
  );
end;
$$;

create or replace function private.rollback_content_impl(p_version_id uuid)
returns jsonb
language plpgsql
volatile
security definer
set search_path = ''
as $$
declare
  v_user_id uuid;
  v_draft public.content_drafts%rowtype;
  v_version public.content_versions%rowtype;
begin
  v_user_id := private.require_content_admin();

  select draft.*
    into v_draft
    from public.content_drafts as draft
    where draft.id = '00000000-0000-4000-8000-000000000001'::uuid
    for update;

  if not found then
    raise exception using
      errcode = '55000',
      message = 'content draft singleton is not initialized';
  end if;

  select versions.*
    into v_version
    from public.content_versions as versions
    where versions.id = p_version_id;

  if not found then
    raise exception using
      errcode = '22023',
      message = 'content version does not exist';
  end if;

  perform private.validate_content_manifest(v_version.manifest, false);

  update public.content_drafts as draft
    set manifest = v_version.manifest,
        revision = draft.revision + 1,
        updated_by = v_user_id
    where draft.id = v_draft.id
    returning draft.* into v_draft;

  return jsonb_build_object(
    'id', v_draft.id,
    'manifest', v_draft.manifest,
    'revision', v_draft.revision,
    'updatedBy', v_draft.updated_by,
    'updatedAt', v_draft.updated_at,
    'restoredFromVersion', v_version.version,
    'activeVersionUnchanged', true
  );
end;
$$;

create or replace function private.media_reference_counts(p_media_asset_id uuid)
returns jsonb
language sql
stable
security invoker
set search_path = ''
as $$
  with draft_references as (
    select count(*)::integer as card_count
      from public.content_drafts as draft
      cross join lateral jsonb_array_elements(draft.manifest -> 'cards') as card(value)
      where card.value ->> 'mediaAssetId' = p_media_asset_id::text
  ),
  published_references as (
    select
      count(*)::integer as card_count,
      count(distinct versions.id)::integer as version_count
      from public.content_versions as versions
      cross join lateral jsonb_array_elements(versions.manifest -> 'cards') as card(value)
      where card.value ->> 'mediaAssetId' = p_media_asset_id::text
  ),
  active_references as (
    select count(*)::integer as card_count
      from public.site_state as state
      join public.content_versions as versions
        on versions.id = state.active_version_id
      cross join lateral jsonb_array_elements(versions.manifest -> 'cards') as card(value)
      where state.singleton
        and card.value ->> 'mediaAssetId' = p_media_asset_id::text
  )
  select jsonb_build_object(
    'mediaAssetId', p_media_asset_id,
    'draftCardReferences', draft_references.card_count,
    'publishedCardReferences', published_references.card_count,
    'publishedVersionReferences', published_references.version_count,
    'activeCardReferences', active_references.card_count
  )
  from draft_references, published_references, active_references;
$$;

create or replace function private.get_media_asset_reference_counts_impl(
  p_media_asset_id uuid
)
returns jsonb
language plpgsql
stable
security definer
set search_path = ''
as $$
begin
  perform private.require_content_admin();
  if not exists (select 1 from public.media_assets where id = p_media_asset_id) then
    raise exception using errcode = '22023', message = 'media asset does not exist';
  end if;
  return private.media_reference_counts(p_media_asset_id);
end;
$$;

create or replace function private.archive_media_asset_impl(p_media_asset_id uuid)
returns jsonb
language plpgsql
volatile
security definer
set search_path = ''
as $$
declare
  v_asset public.media_assets%rowtype;
begin
  perform private.require_content_admin();

  select media.*
    into v_asset
    from public.media_assets as media
    where media.id = p_media_asset_id
    for update;

  if not found then
    raise exception using errcode = '22023', message = 'media asset does not exist';
  end if;
  if v_asset.purge_requested_at is not null then
    raise exception using errcode = '55000', message = 'media asset purge is in progress';
  end if;

  if v_asset.status <> 'archived' then
    update public.media_assets as media
      set status = 'archived'
      where media.id = v_asset.id
      returning media.* into v_asset;
  end if;

  return to_jsonb(v_asset);
end;
$$;

create or replace function private.prepare_media_asset_purge_impl(
  p_media_asset_id uuid
)
returns jsonb
language plpgsql
volatile
security definer
set search_path = ''
as $$
declare
  v_asset public.media_assets%rowtype;
  v_references jsonb;
begin
  perform private.require_content_admin();

  perform 1
    from public.content_drafts as draft
    where draft.id = '00000000-0000-4000-8000-000000000001'::uuid
    for update;

  select media.*
    into v_asset
    from public.media_assets as media
    where media.id = p_media_asset_id
    for update;

  if not found then
    raise exception using errcode = '22023', message = 'media asset does not exist';
  end if;
  if v_asset.status <> 'archived' then
    raise exception using
      errcode = '55000',
      message = 'media asset must be archived before purge preparation';
  end if;

  v_references := private.media_reference_counts(p_media_asset_id);
  if (v_references ->> 'draftCardReferences')::integer > 0
     or (v_references ->> 'publishedCardReferences')::integer > 0 then
    raise exception using
      errcode = '23503',
      message = 'referenced media assets cannot be purged',
      detail = v_references::text;
  end if;

  update public.media_assets as media
    set purge_requested_at = now()
    where media.id = v_asset.id
    returning media.* into v_asset;

  return jsonb_build_object(
    'canPurge', true,
    'mediaAssetId', v_asset.id,
    'storagePath', v_asset.storage_path,
    'posterPath', v_asset.poster_path,
    'purgeRequestedAt', v_asset.purge_requested_at,
    'references', v_references
  );
end;
$$;

create or replace function private.cancel_media_asset_purge_impl(
  p_media_asset_id uuid
)
returns jsonb
language plpgsql
volatile
security definer
set search_path = ''
as $$
declare
  v_asset public.media_assets%rowtype;
begin
  perform private.require_content_admin();

  update public.media_assets as media
    set purge_requested_at = null
    where media.id = p_media_asset_id
      and media.status = 'archived'
    returning media.* into v_asset;

  if not found then
    raise exception using
      errcode = '22023',
      message = 'archived media asset does not exist';
  end if;
  return to_jsonb(v_asset);
end;
$$;

create or replace function private.finalize_media_asset_purge_impl(
  p_media_asset_id uuid,
  p_expected_storage_path text,
  p_expected_poster_path text
)
returns boolean
language plpgsql
volatile
security definer
set search_path = ''
as $$
declare
  v_asset public.media_assets%rowtype;
  v_references jsonb;
begin
  perform private.require_content_admin();

  perform 1
    from public.content_drafts as draft
    where draft.id = '00000000-0000-4000-8000-000000000001'::uuid
    for update;

  select media.*
    into v_asset
    from public.media_assets as media
    where media.id = p_media_asset_id
    for update;

  if not found then
    raise exception using errcode = '22023', message = 'media asset does not exist';
  end if;
  if v_asset.purge_requested_at is null then
    raise exception using errcode = '55000', message = 'media purge was not prepared';
  end if;
  if v_asset.storage_path is distinct from p_expected_storage_path
     or v_asset.poster_path is distinct from p_expected_poster_path then
    raise exception using
      errcode = '40001',
      message = 'media paths changed after purge preparation';
  end if;

  if exists (
    select 1
      from storage.objects as object
      where object.bucket_id = 'card-media'
        and object.name = v_asset.storage_path
  ) then
    raise exception using
      errcode = '55000',
      message = 'media video object must be deleted before purge finalization';
  end if;

  if v_asset.poster_path is not null and exists (
    select 1
      from storage.objects as object
      where object.bucket_id = 'card-media'
        and object.name = v_asset.poster_path
  ) then
    raise exception using
      errcode = '55000',
      message = 'media poster object must be deleted before purge finalization';
  end if;

  v_references := private.media_reference_counts(p_media_asset_id);
  if (v_references ->> 'draftCardReferences')::integer > 0
     or (v_references ->> 'publishedCardReferences')::integer > 0 then
    raise exception using
      errcode = '23503',
      message = 'referenced media assets cannot be purged',
      detail = v_references::text;
  end if;

  delete from public.media_assets where id = p_media_asset_id;
  return true;
end;
$$;

create or replace function public.get_active_content_manifest()
returns jsonb
language sql
stable
security invoker
set search_path = ''
as $$
  select private.get_active_content_manifest_impl();
$$;

create or replace function public.save_content_draft(
  expected_revision integer,
  manifest jsonb
)
returns jsonb
language sql
volatile
security invoker
set search_path = ''
as $$
  select private.save_content_draft_impl($1, $2);
$$;

create or replace function public.publish_content(
  expected_revision integer,
  release_note text default null
)
returns jsonb
language sql
volatile
security invoker
set search_path = ''
as $$
  select private.publish_content_impl($1, $2);
$$;

create or replace function public.rollback_content(version_id uuid)
returns jsonb
language sql
volatile
security invoker
set search_path = ''
as $$
  select private.rollback_content_impl($1);
$$;

create or replace function public.get_media_asset_reference_counts(media_asset_id uuid)
returns jsonb
language sql
stable
security invoker
set search_path = ''
as $$
  select private.get_media_asset_reference_counts_impl($1);
$$;

create or replace function public.archive_media_asset(media_asset_id uuid)
returns jsonb
language sql
volatile
security invoker
set search_path = ''
as $$
  select private.archive_media_asset_impl($1);
$$;

create or replace function public.prepare_media_asset_purge(media_asset_id uuid)
returns jsonb
language sql
volatile
security invoker
set search_path = ''
as $$
  select private.prepare_media_asset_purge_impl($1);
$$;

create or replace function public.cancel_media_asset_purge(media_asset_id uuid)
returns jsonb
language sql
volatile
security invoker
set search_path = ''
as $$
  select private.cancel_media_asset_purge_impl($1);
$$;

create or replace function public.finalize_media_asset_purge(
  media_asset_id uuid,
  expected_storage_path text,
  expected_poster_path text
)
returns boolean
language sql
volatile
security invoker
set search_path = ''
as $$
  select private.finalize_media_asset_purge_impl($1, $2, $3);
$$;

revoke execute on function private.is_nonempty_text(text, integer)
  from public, anon, authenticated, service_role;
revoke execute on function private.is_hex_colour(text)
  from public, anon, authenticated, service_role;
revoke execute on function private.is_https_url(text)
  from public, anon, authenticated, service_role;
revoke execute on function private.is_cta_url(text)
  from public, anon, authenticated, service_role;
revoke execute on function private.is_media_url(text)
  from public, anon, authenticated, service_role;
revoke execute on function private.validate_content_manifest(jsonb, boolean)
  from public, anon, authenticated, service_role;
revoke execute on function private.touch_updated_at()
  from public, anon, authenticated, service_role;
revoke execute on function private.guard_media_asset_update()
  from public, anon, authenticated, service_role;
revoke execute on function private.guard_content_draft_write()
  from public, anon, authenticated, service_role;
revoke execute on function private.guard_content_version_insert()
  from public, anon, authenticated, service_role;
revoke execute on function private.reject_content_version_mutation()
  from public, anon, authenticated, service_role;
revoke execute on function private.require_content_admin()
  from public, anon, authenticated, service_role;
revoke execute on function private.media_reference_counts(uuid)
  from public, anon, authenticated, service_role;

revoke execute on function private.get_active_content_manifest_impl()
  from public, anon, authenticated, service_role;
revoke execute on function private.save_content_draft_impl(integer, jsonb)
  from public, anon, authenticated, service_role;
revoke execute on function private.publish_content_impl(integer, text)
  from public, anon, authenticated, service_role;
revoke execute on function private.rollback_content_impl(uuid)
  from public, anon, authenticated, service_role;
revoke execute on function private.get_media_asset_reference_counts_impl(uuid)
  from public, anon, authenticated, service_role;
revoke execute on function private.archive_media_asset_impl(uuid)
  from public, anon, authenticated, service_role;
revoke execute on function private.prepare_media_asset_purge_impl(uuid)
  from public, anon, authenticated, service_role;
revoke execute on function private.cancel_media_asset_purge_impl(uuid)
  from public, anon, authenticated, service_role;
revoke execute on function private.finalize_media_asset_purge_impl(uuid, text, text)
  from public, anon, authenticated, service_role;

grant usage on schema private to anon, authenticated;

-- media_assets exposes authenticated INSERT/UPDATE under RLS, and its CHECK
-- constraints call is_media_url, which delegates HTTPS validation to
-- is_https_url. The private schema is not exposed through the Data API, so
-- these grants do not create an RPC surface.
grant execute on function private.is_media_url(text)
  to authenticated;
grant execute on function private.is_https_url(text)
  to authenticated;

grant execute on function private.get_active_content_manifest_impl()
  to anon, authenticated;
grant execute on function private.save_content_draft_impl(integer, jsonb)
  to authenticated;
grant execute on function private.publish_content_impl(integer, text)
  to authenticated;
grant execute on function private.rollback_content_impl(uuid)
  to authenticated;
grant execute on function private.get_media_asset_reference_counts_impl(uuid)
  to authenticated;
grant execute on function private.archive_media_asset_impl(uuid)
  to authenticated;
grant execute on function private.prepare_media_asset_purge_impl(uuid)
  to authenticated;
grant execute on function private.cancel_media_asset_purge_impl(uuid)
  to authenticated;
grant execute on function private.finalize_media_asset_purge_impl(uuid, text, text)
  to authenticated;

revoke execute on function public.get_active_content_manifest()
  from public, anon, authenticated, service_role;
revoke execute on function public.save_content_draft(integer, jsonb)
  from public, anon, authenticated, service_role;
revoke execute on function public.publish_content(integer, text)
  from public, anon, authenticated, service_role;
revoke execute on function public.rollback_content(uuid)
  from public, anon, authenticated, service_role;
revoke execute on function public.get_media_asset_reference_counts(uuid)
  from public, anon, authenticated, service_role;
revoke execute on function public.archive_media_asset(uuid)
  from public, anon, authenticated, service_role;
revoke execute on function public.prepare_media_asset_purge(uuid)
  from public, anon, authenticated, service_role;
revoke execute on function public.cancel_media_asset_purge(uuid)
  from public, anon, authenticated, service_role;
revoke execute on function public.finalize_media_asset_purge(uuid, text, text)
  from public, anon, authenticated, service_role;

grant execute on function public.get_active_content_manifest()
  to anon, authenticated;
grant execute on function public.save_content_draft(integer, jsonb)
  to authenticated;
grant execute on function public.publish_content(integer, text)
  to authenticated;
grant execute on function public.rollback_content(uuid)
  to authenticated;
grant execute on function public.get_media_asset_reference_counts(uuid)
  to authenticated;
grant execute on function public.archive_media_asset(uuid)
  to authenticated;
grant execute on function public.prepare_media_asset_purge(uuid)
  to authenticated;
grant execute on function public.cancel_media_asset_purge(uuid)
  to authenticated;
grant execute on function public.finalize_media_asset_purge(uuid, text, text)
  to authenticated;

insert into storage.buckets (
  id,
  name,
  public,
  file_size_limit,
  allowed_mime_types
)
values (
  'card-media',
  'card-media',
  true,
  104857600,
  array['video/mp4', 'image/jpeg', 'image/png', 'image/webp']::text[]
)
on conflict (id) do update
set name = excluded.name,
    public = excluded.public,
    file_size_limit = excluded.file_size_limit,
    allowed_mime_types = excluded.allowed_mime_types;

drop policy if exists card_media_admin_select on storage.objects;
drop policy if exists card_media_admin_insert on storage.objects;
drop policy if exists card_media_admin_update on storage.objects;
drop policy if exists card_media_admin_delete on storage.objects;

create policy card_media_admin_select
on storage.objects
for select
to authenticated
using (
  bucket_id = 'card-media'
  and exists (
    select 1
      from public.admin_users as admins
      where admins.user_id = (select auth.uid())
  )
);

create policy card_media_admin_insert
on storage.objects
for insert
to authenticated
with check (
  bucket_id = 'card-media'
  and exists (
    select 1
      from public.admin_users as admins
      where admins.user_id = (select auth.uid())
  )
);

create policy card_media_admin_delete
on storage.objects
for delete
to authenticated
using (
  bucket_id = 'card-media'
  and exists (
    select 1
      from public.admin_users as admins
      where admins.user_id = (select auth.uid())
  )
  and exists (
    select 1
      from public.media_assets as media
      where (
        media.storage_path = storage.objects.name
        or media.poster_path = storage.objects.name
      )
        and (
          (
            media.status = 'archived'
            and media.purge_requested_at is not null
          )
          or (
            media.created_by = (select auth.uid())
            and media.status in ('uploading', 'failed')
          )
        )
  )
);

comment on table public.admin_users is
  'Allowlist of Supabase Auth users permitted to operate the content admin.';
comment on table public.content_drafts is
  'Single mutable content manifest. Writes must use save/publish/rollback RPCs.';
comment on table public.content_versions is
  'Immutable published content manifests.';
comment on table public.site_state is
  'Singleton pointer to the active immutable content version.';
comment on column public.media_assets.purge_requested_at is
  'Two-phase purge reservation. While set, manifests cannot newly reference the asset.';
comment on function public.get_active_content_manifest() is
  'The only anonymous database read surface: returns the active manifest as jsonb.';

commit;
