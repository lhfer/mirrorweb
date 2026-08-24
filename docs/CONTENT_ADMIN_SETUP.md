# Content Admin setup

## Current status

The repository contains reproducible migrations, seed data, RLS/Storage
policies, RPCs, and database tests. On 2026-08-24 they were applied through the
connected Supabase plugin to the only available, empty project
`xrdwaputkfeeogryanbq` (`ACTIVE_HEALTHY`, `us-west-2`). Hosted verification
observed:

- four recorded migrations, including the validator-grant and platform-helper
  hardening follow-ups;
- 52/52 pgTAP assertions passing inside a rolled-back transaction;
- five public content tables with RLS enabled;
- one active v1 manifest containing 24 enabled cards and three seed media rows;
- a public `card-media` bucket with a 100 MiB limit and the intended MIME list;
- zero Supabase Security Advisor findings;
- a production build loading `source=remote`, `version=1` with zero console
  warnings or errors.

Auth setup now has one invited and email-confirmed administrator, one matching
`admin_users` allowlist row, public signups disabled, and exact local Site URL
and Redirect URLs configured. A real `shouldCreateUser:false` Magic Link login
opened the authenticated `SUPABASE LIVE` editor, and a fresh tab recovered the
same session with zero console warnings or errors. User-driven draft edits and
publishes advanced the active remote manifest from v1 to v3; a public reload
then loaded `source=remote`, `version=3` and displayed the published edit.

Never put a secret key, legacy `service_role` JWT, database password, or
personal access token in Vite variables, browser code, source files, logs, or
Git history. The browser uses only:

```dotenv
VITE_SUPABASE_URL=https://PROJECT_REF.supabase.co
VITE_SUPABASE_PUBLISHABLE_KEY=sb_publishable_REPLACE_ME
```

Use an enabled publishable key. A legacy `anon` key may work for compatibility,
but a current publishable key is preferred. There is deliberately no
`VITE_SUPABASE_SERVICE_ROLE_KEY`.

## Local database

Install a current Supabase CLI separately, then discover the installed command
surface before using it:

```bash
supabase --version
supabase --help
supabase migration --help
supabase test --help
```

This workstation did not have the Supabase CLI or a running local/linked
database. A standalone `psql` client was present, but there was no database
target against which the migrations could be executed during authoring. Once
the CLI is available:

```bash
supabase init                 # only if supabase/config.toml is still absent
supabase start
supabase db reset
supabase test db
```

`db reset` is destructive to the local development database only. Confirm the
CLI says the target is local before running it. It should apply, in order:

1. `20260823090000_content_admin_schema.sql`;
2. `20260823090100_seed_v1_content.sql`;
3. `20260824070000_fix_media_url_validator_grant.sql`;
4. `20260824073000_harden_platform_helpers_and_indexes.sql`;
5. `content_admin_security.test.sql` inside a transaction that rolls back.

After reset, verify these invariants with the local SQL editor or `psql`:

```sql
select public.get_active_content_manifest() ->> 'version'; -- 1
select count(*) from public.content_versions;              -- 1
select count(*) from public.content_drafts;                -- 1
select count(*) from public.media_assets;                  -- 3
select public.get_active_content_manifest() -> 'cards';    -- 24 entries
```

Then run the application build and the four required product viewports. A
database test pass proves database behavior; it does not prove pixel identity
or mobile rendering.

## Apply to the intended hosted project

Before changing production, create a project backup and verify the project ref.
Then inspect the current CLI help and use the standard linked migration flow:

```bash
supabase login
supabase link --project-ref YOUR_PROJECT_REF
supabase migration list --linked
supabase db push
supabase migration list --linked
```

Do not paste access tokens or database passwords into committed commands.
Prefer a development branch or separate staging project for the first apply.
After applying, run both Supabase database advisors and resolve any security or
performance findings before enabling the admin UI:

```bash
supabase db advisors --help
supabase db advisors
```

Supabase changed Data API defaults in 2026: public tables may no longer be
auto-exposed. The schema migration therefore includes explicit table and
function grants as well as RLS. Do not compensate for an access error by
granting `ALL` or disabling RLS.

## Auth and first admin

1. In Auth settings, enable Email Magic Link and disable public user creation.
2. Set the production Site URL to the canonical HTTPS origin.
3. Add exact additional Redirect URLs:
   - local: `http://127.0.0.1:5280/admin.html`;
   - production: `https://YOUR_HOST/admin.html`;
   - add a deliberate preview-host pattern only if preview deployments are
     part of the release process. Prefer exact production paths over broad
     wildcards.
4. Create or invite the administrator in **Auth > Users**. Do not make the
   browser create this user.
5. Copy the user's UUID and bootstrap the allowlist in the SQL editor:

```sql
insert into public.admin_users (user_id, email)
values (
  'AUTH_USER_UUID'::uuid,
  'approved-admin@example.com'
);
```

The UUID must already exist in `auth.users`; the foreign key deliberately
rejects an email-only placeholder. Email is for display/audit, while
authorization uses the immutable user UUID.

The browser Magic Link call must not create users:

```ts
await supabase.auth.signInWithOtp({
  email,
  options: {
    shouldCreateUser: false,
    emailRedirectTo: new URL('/admin.html', location.origin).href,
  },
});
```

On return, restore the session, query the caller's own `admin_users` row, and
show 403 when it is absent. A missing/expired session returns to login. Logout
must call `supabase.auth.signOut()` and clear admin-only UI state.

Removing an `admin_users` row immediately makes subsequent RLS and RPC checks
fail even if an old Auth token still exists. For a full offboarding, revoke the
user's sessions before deleting or disabling the Auth user as well.

## Storage

The migration creates a public `card-media` bucket with a default 100 MiB
per-object limit and allowed MIME types for MP4 plus generated JPEG/PNG/WebP
posters. Change the limit deliberately in a follow-up migration if product
requirements differ; do not make a dashboard-only change that cannot be
reproduced.

Public bucket means exactly this: anyone who learns an object URL can retrieve
it, including an upload not yet used by a published manifest. This MVP accepts
only public-ready media. Private staging and signed URLs are later scope.
Storage policies require an allowlisted admin for list and upload. Overwrite,
upsert, move, and copy are deliberately not granted because media replacement
creates a new immutable UUID path. DELETE is narrower still: it only accepts an
exact path carrying a database purge reservation, or an uploading/failed object
owned by the current admin during compensating cleanup.

Upload flow:

1. Validate `.mp4` and `video/mp4` in the browser; H.264 MP4 is recommended for
   Safari and mobile compatibility.
2. Generate a UUID and use a path such as
   `media/UUID.mp4`; never include the original filename in a path.
3. Derive the bucket's canonical public video/poster URLs, then insert
   `media_assets` with those URLs, `status='uploading'`, SHA-256, and
   `created_by=auth.uid()`.
4. Upload video and generated poster with the authenticated Storage client.
5. Read width, height, and duration through `HTMLVideoElement` and update the
   metadata row to `ready`. On failure set `failed`; never claim readiness just
   because a Storage request returned.

The three system seed rows use `bundled/*.mp4` metadata paths and canonical
`/clips/*.mp4` public URLs. The admin preserves those URLs instead of rewriting
them to nonexistent Storage objects. The publication exemption recognizes only
the three fixed seed IDs with null `created_by`, exact bundled paths, exact
canonical URLs, and no poster. Any other asset—including another `bundled/`
path—must have its exact video and poster objects present before publication.

Permanent deletion must follow the two-phase RPC protocol in
`CONTENT_MODEL.md`. Never delete from `storage.objects` with SQL; use the
Storage API, then finalize the metadata purge. Archive is the normal action.
Finalization independently queries `storage.objects` and fails while either the
reserved video or poster path still exists.

## Backup and rollback

Create two backups because Supabase database backups contain Storage metadata,
not the media object bytes themselves:

1. Database: use **Database > Backups** (scheduled backup or PITR where
   available). Free projects should take regular logical exports. Inspect
   `supabase db dump --help`, then use a protected database connection string
   to export roles, schema, and data according to the current Supabase backup
   guide.
2. Storage: separately inventory and copy every `card-media` object and retain
   its exact path, size, MIME type, and checksum. Test a restore to staging.

Before applying these migrations, record the backup timestamp, project ref,
migration list, and `card-media` inventory. Supabase project restore causes
downtime, and restoring a database backup does not resurrect a deleted Storage
object.

For an editorial rollback, do not restore the database:

1. open Publish History;
2. call `rollback_content(version_id)`;
3. preview the restored draft with the production renderer;
4. publish it with a new release note.

This creates a new forward version and keeps the historical audit trail.
Reserve a database/PITR restore for database-level corruption, not a mistaken
headline or card order.

## Release checklist

- migrations and seed apply cleanly to an empty local database;
- `supabase test db` passes all RLS, revision, publication, immutability, and
  purge tests;
- Security and Performance advisors have no unresolved content-admin finding;
- public signup is disabled and Magic Link uses `shouldCreateUser:false`;
- local and production admin redirect URLs are allowlisted;
- the intended Auth UUID is present in `admin_users`;
- browser bundle contains the publishable key only and contains no secret or
  service-role key;
- anonymous direct draft/media/history access and Storage writes are denied;
- anonymous `get_active_content_manifest()` returns exactly version 1 after
  seed;
- Storage objects have a separate tested backup;
- public fallback, four-viewport pixel identity, frame pacing, and zero console
  errors are verified independently.

The hosted database, Auth, RLS, draft, publish and public reload gates are now
observed. A real Storage upload/archive/purge and the eventual production HTTPS
Site URL remain deployment follow-ups. Report the v1.1 branch state as:

`READY FOR CONTENT ADMIN PRODUCT REVIEW`.
