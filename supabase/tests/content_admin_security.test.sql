begin;

create extension if not exists pgtap with schema extensions;

select extensions.plan(52);

insert into auth.users (id, email)
values
  ('90000000-0000-4000-8000-000000000001'::uuid, 'admin-test@example.com'),
  ('90000000-0000-4000-8000-000000000002'::uuid, 'non-admin-test@example.com');

insert into public.admin_users (user_id, email)
values (
  '90000000-0000-4000-8000-000000000001'::uuid,
  'admin-test@example.com'
);

insert into storage.objects (bucket_id, name)
values ('card-media', 'tests/anon-delete-target.mp4');

select extensions.is(
  (
    select count(*)::integer
      from pg_class
      where oid in (
        'public.admin_users'::regclass,
        'public.media_assets'::regclass,
        'public.content_drafts'::regclass,
        'public.content_versions'::regclass,
        'public.site_state'::regclass
      )
        and relrowsecurity
  ),
  5,
  'RLS is enabled on every public content table'
);

select extensions.ok(
  not has_table_privilege('anon', 'public.admin_users', 'SELECT')
  and not has_table_privilege('anon', 'public.media_assets', 'SELECT')
  and not has_table_privilege('anon', 'public.content_drafts', 'SELECT')
  and not has_table_privilege('anon', 'public.content_versions', 'SELECT')
  and not has_table_privilege('anon', 'public.site_state', 'SELECT'),
  'anon has no direct table read grants'
);

set local role anon;

select extensions.is(
  public.get_active_content_manifest() ->> 'schemaVersion',
  '1',
  'anon can fetch the active manifest through the one public RPC'
);

select extensions.throws_ok(
  $$select * from public.content_drafts$$,
  '42501',
  null,
  'anon cannot read the mutable draft'
);

select extensions.throws_ok(
  $$insert into public.media_assets (
      original_name, storage_path, mime_type, status
    ) values (
      'anon.mp4', 'tests/anon.mp4', 'video/mp4', 'ready'
    )$$,
  '42501',
  null,
  'anon cannot create a media row'
);

select extensions.throws_ok(
  $$select public.save_content_draft(1, '{}'::jsonb)$$,
  '42501',
  null,
  'anon cannot execute the draft save RPC'
);

select extensions.throws_ok(
  $$insert into storage.objects (bucket_id, name)
    values ('card-media', 'tests/anon-upload.mp4')$$,
  '42501',
  null,
  'anon cannot upload a Storage object'
);

select extensions.is_empty(
  $$delete from storage.objects
    where bucket_id = 'card-media'
      and name = 'tests/anon-delete-target.mp4'
    returning name$$,
  'anon cannot delete an existing Storage object'
);

reset role;
set local role authenticated;
set local request.jwt.claim.sub = '90000000-0000-4000-8000-000000000002';

select extensions.is_empty(
  $$select id from public.content_drafts$$,
  'a signed-in non-admin sees no draft rows'
);

select extensions.is_empty(
  $$select id from public.media_assets$$,
  'a signed-in non-admin sees no media rows'
);

select extensions.throws_ok(
  $$select public.save_content_draft(
      1,
      (select manifest from public.content_drafts limit 1)
    )$$,
  '42501',
  null,
  'the save RPC explicitly rejects a signed-in non-admin'
);

select extensions.throws_ok(
  $$insert into public.media_assets (
      original_name, storage_path, mime_type, status, created_by
    ) values (
      'non-admin.mp4',
      'tests/non-admin.mp4',
      'video/mp4',
      'ready',
      '90000000-0000-4000-8000-000000000002'::uuid
    )$$,
  '42501',
  null,
  'a signed-in non-admin cannot create a media row'
);

select extensions.throws_ok(
  $$insert into storage.objects (bucket_id, name)
    values ('card-media', 'tests/non-admin-upload.mp4')$$,
  '42501',
  null,
  'a signed-in non-admin cannot upload a Storage object'
);

reset role;
set local role authenticated;
set local request.jwt.claim.sub = '90000000-0000-4000-8000-000000000001';

select extensions.is(
  (select revision from public.content_drafts),
  1,
  'the approved admin can read the singleton draft'
);

select extensions.throws_ok(
  $$insert into public.media_assets (
      id, original_name, storage_path, poster_path, media_url,
      mime_type, status, created_by
    ) values (
      'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1'::uuid,
      'poster-path-only.mp4',
      'tests/parity/path-only.mp4',
      'tests/parity/path-only.jpg',
      'https://example.supabase.co/storage/v1/object/public/card-media/tests/parity/path-only.mp4',
      'video/mp4',
      'uploading',
      '90000000-0000-4000-8000-000000000001'::uuid
    )$$,
  '23514',
  null,
  'poster_path cannot exist without poster_url'
);

select extensions.throws_ok(
  $$insert into public.media_assets (
      id, original_name, storage_path, media_url, poster_url,
      mime_type, status, created_by
    ) values (
      'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa2'::uuid,
      'poster-url-only.mp4',
      'tests/parity/url-only.mp4',
      'https://example.supabase.co/storage/v1/object/public/card-media/tests/parity/url-only.mp4',
      'https://example.supabase.co/storage/v1/object/public/card-media/tests/parity/url-only.jpg',
      'video/mp4',
      'uploading',
      '90000000-0000-4000-8000-000000000001'::uuid
    )$$,
  '23514',
  null,
  'poster_url cannot exist without poster_path'
);

select extensions.throws_ok(
  $$update public.media_assets
      set status = 'failed'
    where id = '11111111-1111-4111-8111-111111111111'::uuid$$,
  '42501',
  null,
  'a browser admin cannot bypass guarded lifecycle RPCs for ready media'
);

select extensions.is(
  (
    public.save_content_draft(
      1,
      jsonb_set(
        (select manifest from public.content_drafts),
        '{cards,0,title}',
        to_jsonb('</script><img src=x onerror=alert(1)>'::text)
      )
    ) ->> 'revision'
  )::integer,
  2,
  'XSS-shaped text is stored as literal text rather than treated as markup'
);

select extensions.is(
  (select manifest #>> '{cards,0,title}' from public.content_drafts),
  '</script><img src=x onerror=alert(1)>',
  'the XSS-shaped title remains an exact text value'
);

select extensions.throws_ok(
  $$select public.save_content_draft(
      (select revision from public.content_drafts),
      jsonb_set(
        (select manifest from public.content_drafts),
        '{site,ctaUrl}',
        '"javascript:alert(1)"'::jsonb
      )
    )$$,
  '22023',
  null,
  'javascript URLs are rejected'
);

select extensions.throws_ok(
  $$select public.save_content_draft(
      (select revision from public.content_drafts),
      jsonb_set(
        (select manifest from public.content_drafts),
        '{cards,0,accent}',
        '"red"'::jsonb
      )
    )$$,
  '22023',
  null,
  'invalid colours are rejected'
);

select extensions.throws_ok(
  $$select public.save_content_draft(
      1,
      (select manifest from public.content_drafts)
    )$$,
  '40001',
  null,
  'stale draft revisions are rejected'
);

select extensions.is(
  (select revision from public.content_drafts),
  2,
  'rejected draft saves do not advance revision'
);

select extensions.throws_ok(
  $$select public.save_content_draft(
      (select revision from public.content_drafts),
      jsonb_set(
        (select manifest from public.content_drafts),
        '{cards,3,mediaUrl}',
        '"/clips/conflicting.mp4"'::jsonb
      )
    )$$,
  '22023',
  null,
  'one mediaAssetId cannot resolve to conflicting URLs'
);

reset role;
update public.media_assets
set status = 'uploading'
where id = '11111111-1111-4111-8111-111111111111'::uuid;

set local role authenticated;
set local request.jwt.claim.sub = '90000000-0000-4000-8000-000000000001';

select extensions.throws_ok(
  $$select public.publish_content(
      (select revision from public.content_drafts),
      'must fail while media is not ready'
    )$$,
  '22023',
  null,
  'publishing is blocked when referenced media is not ready'
);

select extensions.is(
  (select max(version) from public.content_versions),
  1,
  'a failed publish creates no partial immutable version'
);

select extensions.is(
  (public.get_active_content_manifest() ->> 'version')::integer,
  1,
  'a failed publish leaves the active version unchanged'
);

reset role;
update public.media_assets
set status = 'ready'
where id = '11111111-1111-4111-8111-111111111111'::uuid;

set local role authenticated;
set local request.jwt.claim.sub = '90000000-0000-4000-8000-000000000001';

select extensions.is(
  (
    public.publish_content(
      (select revision from public.content_drafts),
      'pgTAP publication'
    ) ->> 'version'
  )::integer,
  2,
  'a valid publish creates the next immutable version'
);

select extensions.is(
  (select revision from public.content_drafts),
  3,
  'publishing advances the draft revision to invalidate stale editors'
);

select extensions.is(
  public.get_active_content_manifest() #>> '{cards,0,title}',
  '</script><img src=x onerror=alert(1)>',
  'the active manifest contains the exact text value after publish'
);

reset role;

select extensions.throws_ok(
  $$update public.content_versions
    set release_note = 'mutated'
    where version = 2$$,
  '55000',
  null,
  'published versions are immutable even to a direct privileged update'
);

set local role authenticated;
set local request.jwt.claim.sub = '90000000-0000-4000-8000-000000000001';

select extensions.is(
  (
    public.rollback_content(
      '00000000-0000-4000-8000-000000000101'::uuid
    ) ->> 'restoredFromVersion'
  )::integer,
  1,
  'rollback copies a historical version into the draft'
);

select extensions.is(
  (public.get_active_content_manifest() ->> 'version')::integer,
  2,
  'rollback does not change the active published version'
);

insert into public.media_assets (
  id,
  original_name,
  storage_path,
  media_url,
  mime_type,
  status,
  created_by
)
values (
  '88888888-8888-4888-8888-888888888888'::uuid,
  'missing-object.mp4',
  'tests/missing-object.mp4',
  'https://example.supabase.co/storage/v1/object/public/card-media/tests/missing-object.mp4',
  'video/mp4',
  'uploading',
  '90000000-0000-4000-8000-000000000001'::uuid
);

update public.media_assets
set status = 'ready'
where id = '88888888-8888-4888-8888-888888888888'::uuid;

do $missing_object_draft$
declare
  v_manifest jsonb;
begin
  v_manifest := jsonb_set(
    jsonb_set(
      (select manifest from public.content_drafts),
      '{cards,0,mediaAssetId}',
      '"88888888-8888-4888-8888-888888888888"'::jsonb
    ),
    '{cards,0,mediaUrl}',
    '"https://example.supabase.co/storage/v1/object/public/card-media/tests/missing-object.mp4"'::jsonb
  );
  perform public.save_content_draft(
    (select revision from public.content_drafts),
    v_manifest
  );
end;
$missing_object_draft$;

select extensions.throws_ok(
  $$select public.publish_content(
      (select revision from public.content_drafts),
      'must fail while the exact Storage object is missing'
    )$$,
  '23503',
  null,
  'ready metadata cannot publish without its canonical Storage object'
);

select extensions.is(
  (select max(version) from public.content_versions),
  2,
  'a missing Storage object cannot create a partial version'
);

do $restore_after_missing_object$
begin
  perform public.rollback_content(
    '00000000-0000-4000-8000-000000000101'::uuid
  );
end;
$restore_after_missing_object$;

insert into public.media_assets (
  id,
  original_name,
  storage_path,
  media_url,
  mime_type,
  status,
  created_by
)
values (
  '44444444-4444-4444-8444-444444444444'::uuid,
  'counterfeit-bundled.mp4',
  'bundled/counterfeit-bundled.mp4',
  'https://example.supabase.co/storage/v1/object/public/card-media/bundled/counterfeit-bundled.mp4',
  'video/mp4',
  'uploading',
  '90000000-0000-4000-8000-000000000001'::uuid
);

update public.media_assets
set status = 'ready'
where id = '44444444-4444-4444-8444-444444444444'::uuid;

do $counterfeit_bundled_draft$
declare
  v_manifest jsonb;
begin
  v_manifest := jsonb_set(
    jsonb_set(
      (select manifest from public.content_drafts),
      '{cards,0,mediaAssetId}',
      '"44444444-4444-4444-8444-444444444444"'::jsonb
    ),
    '{cards,0,mediaUrl}',
    '"https://example.supabase.co/storage/v1/object/public/card-media/bundled/counterfeit-bundled.mp4"'::jsonb
  );
  perform public.save_content_draft(
    (select revision from public.content_drafts),
    v_manifest
  );
end;
$counterfeit_bundled_draft$;

select extensions.throws_ok(
  $$select public.publish_content(
      (select revision from public.content_drafts),
      'must not trust a bundled path prefix'
    )$$,
  '23503',
  null,
  'only the three exact system seed tuples bypass Storage existence'
);

select extensions.is(
  (select max(version) from public.content_versions),
  2,
  'a counterfeit bundled path cannot create a partial version'
);

do $restore_after_counterfeit_bundled$
begin
  perform public.rollback_content(
    '00000000-0000-4000-8000-000000000101'::uuid
  );
end;
$restore_after_counterfeit_bundled$;

select extensions.is(
  public.archive_media_asset(
    '11111111-1111-4111-8111-111111111111'::uuid
  ) ->> 'status',
  'archived',
  'archiving is allowed without deleting referenced media bytes'
);

select extensions.is(
  (
    public.get_media_asset_reference_counts(
      '11111111-1111-4111-8111-111111111111'::uuid
    ) ->> 'publishedVersionReferences'
  )::integer,
  2,
  'media reference counts include every retained published version'
);

select extensions.throws_ok(
  $$select public.prepare_media_asset_purge(
      '11111111-1111-4111-8111-111111111111'::uuid
    )$$,
  '23503',
  null,
  'media referenced by retained versions cannot be prepared for purge'
);

insert into public.media_assets (
  id,
  original_name,
  storage_path,
  poster_path,
  media_url,
  poster_url,
  mime_type,
  status,
  created_by
)
values (
  '77777777-7777-4777-8777-777777777777'::uuid,
  'unreferenced.mp4',
  'tests/unreferenced/source.mp4',
  'tests/unreferenced/poster.jpg',
  'https://example.supabase.co/storage/v1/object/public/card-media/tests/unreferenced/source.mp4',
  'https://example.supabase.co/storage/v1/object/public/card-media/tests/unreferenced/poster.jpg',
  'video/mp4',
  'uploading',
  '90000000-0000-4000-8000-000000000001'::uuid
);

update public.media_assets
set status = 'ready'
where id = '77777777-7777-4777-8777-777777777777'::uuid;

insert into storage.objects (bucket_id, name)
values
  ('card-media', 'tests/unreferenced/source.mp4'),
  ('card-media', 'tests/unreferenced/poster.jpg');

select extensions.throws_ok(
  $$delete from public.media_assets
    where id = '77777777-7777-4777-8777-777777777777'::uuid$$,
  '42501',
  null,
  'even an admin cannot bypass the two-phase purge RPC with direct delete'
);

select extensions.is(
  public.archive_media_asset(
    '77777777-7777-4777-8777-777777777777'::uuid
  ) ->> 'status',
  'archived',
  'an unreferenced asset can first be archived'
);

select extensions.is(
  (
    public.prepare_media_asset_purge(
      '77777777-7777-4777-8777-777777777777'::uuid
    ) ->> 'canPurge'
  )::boolean,
  true,
  'an archived zero-reference asset can be reserved for purge'
);

select extensions.throws_ok(
  $$select public.finalize_media_asset_purge(
      '77777777-7777-4777-8777-777777777777'::uuid,
      'tests/unreferenced/source.mp4',
      'tests/unreferenced/poster.jpg'
    )$$,
  '55000',
  null,
  'purge cannot finalize while its video or poster object still exists'
);

select extensions.results_eq(
  $$with deleted as (
      delete from storage.objects
      where bucket_id = 'card-media'
        and name in (
          'tests/unreferenced/source.mp4',
          'tests/unreferenced/poster.jpg'
        )
      returning name
    )
    select name from deleted order by name$$,
  array[
    'tests/unreferenced/poster.jpg'::text,
    'tests/unreferenced/source.mp4'::text
  ],
  'the purge ticket authorizes deletion of the exact video and poster objects'
);

select extensions.is(
  public.finalize_media_asset_purge(
    '77777777-7777-4777-8777-777777777777'::uuid,
    'tests/unreferenced/source.mp4',
    'tests/unreferenced/poster.jpg'
  ),
  true,
  'purge finalization deletes the database row after Storage deletion'
);

select extensions.is(
  (select count(*)::integer from public.media_assets
    where id = '77777777-7777-4777-8777-777777777777'::uuid),
  0,
  'the finalized zero-reference media row is gone'
);

insert into public.media_assets (
  id, original_name, storage_path, media_url, mime_type, status, created_by
)
values (
  '66666666-6666-4666-8666-666666666666'::uuid,
  'admin-upload.mp4',
  'tests/admin-upload.mp4',
  'https://example.supabase.co/storage/v1/object/public/card-media/tests/admin-upload.mp4',
  'video/mp4',
  'uploading',
  '90000000-0000-4000-8000-000000000001'::uuid
);

insert into public.media_assets (
  id, original_name, storage_path, media_url, mime_type, status, created_by
)
values (
  '55555555-5555-4555-8555-555555555555'::uuid,
  'protected-ready.mp4',
  'tests/protected-ready.mp4',
  'https://example.supabase.co/storage/v1/object/public/card-media/tests/protected-ready.mp4',
  'video/mp4',
  'uploading',
  '90000000-0000-4000-8000-000000000001'::uuid
);

update public.media_assets
set status = 'ready'
where id = '55555555-5555-4555-8555-555555555555'::uuid;

select extensions.results_eq(
  $$insert into storage.objects (bucket_id, name)
    values ('card-media', 'tests/admin-upload.mp4')
    returning name$$,
  array['tests/admin-upload.mp4'::text],
  'an approved admin can upload to card-media'
);

insert into storage.objects (bucket_id, name)
values ('card-media', 'tests/protected-ready.mp4');

reset role;
set local role authenticated;
set local request.jwt.claim.sub = '90000000-0000-4000-8000-000000000002';

select extensions.is_empty(
  $$delete from storage.objects
    where bucket_id = 'card-media'
      and name = 'tests/admin-upload.mp4'
    returning name$$,
  'a signed-in non-admin cannot delete an existing Storage object'
);

reset role;
set local role authenticated;
set local request.jwt.claim.sub = '90000000-0000-4000-8000-000000000001';

select extensions.is_empty(
  $$update storage.objects
      set name = 'tests/protected-ready-moved.mp4'
    where bucket_id = 'card-media'
      and name = 'tests/protected-ready.mp4'
    returning name$$,
  'immutable media cannot be overwritten or moved through Storage UPDATE'
);

select extensions.is_empty(
  $$delete from storage.objects
    where bucket_id = 'card-media'
      and name = 'tests/protected-ready.mp4'
    returning name$$,
  'an admin cannot delete Storage bytes without a purge or cleanup ticket'
);

select extensions.results_eq(
  $$delete from storage.objects
    where bucket_id = 'card-media'
      and name = 'tests/admin-upload.mp4'
    returning name$$,
  array['tests/admin-upload.mp4'::text],
  'an approved admin can clean up an uploading object it owns'
);

reset role;

select * from extensions.finish();
rollback;
