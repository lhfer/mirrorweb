# MirrorWeb content model

This model adds editable content without making layout, typography, motion,
glass, entry, culling, or renderer configuration editable. The public product
receives one validated manifest at boot and does not subscribe to Realtime or
replace running video textures.

## Database records

| Object | Purpose | Mutation path |
| --- | --- | --- |
| `admin_users` | Allowlist tying an approved email to an existing `auth.users.id` | Bootstrap SQL only in v1 |
| `media_assets` | Immutable Storage paths/canonical public URLs plus metadata and lifecycle state for one MP4 source and optional poster | Admin RLS for create/upload completion; archive/purge RPCs for destructive lifecycle changes |
| `content_drafts` | The one mutable manifest and optimistic-lock revision | `save_content_draft`, `publish_content`, or `rollback_content` |
| `content_versions` | Immutable published snapshots | Inserted only by `publish_content`; trigger rejects update/delete |
| `site_state` | The one pointer to the active immutable version | Updated only inside `publish_content` |

The draft singleton UUID is
`00000000-0000-4000-8000-000000000001`. `site_state.singleton` is a checked
boolean primary key, so neither table can acquire a second row.

Creator/editor foreign keys use `on delete set null`. This preserves the audit
record and published snapshot if an Auth user is later removed. The seed rows
have a null actor and are described as system-created.

## Manifest contract

`schemaVersion: 1` has exactly these top-level fields:

```ts
type ContentManifest = {
  schemaVersion: 1;
  version: number;
  cards: Array<{
    id: string;
    code: string;
    category: string;
    title: string;
    deck: string;
    accent: string;
    palette: [string, string, string, string];
    mediaAssetId: string;
    mediaUrl: string;
    posterUrl?: string;
    focusX: number;
    focusY: number;
    zoom: number;
    enabled: boolean;
    sortOrder: number;
  }>;
  site: {
    footerCaption: string;
    brandText: string;
    brandUrl: string;
    ctaLabel: string;
    ctaUrl: string;
    loaderBrandText: string;
  };
};
```

The TypeScript and database validators enforce the same operational limits:

- one to 256 cards, with at least one enabled card;
- unique `id`, `code`, and non-negative integer `sortOrder` values;
- `id` up to 128 identifier characters; `code` 64; `category` 80;
  `title` 120; `deck` 280;
- `footerCaption` 120 and `brandText`, `ctaLabel`, and `loaderBrandText` 80;
- plain text must be non-empty and contain no control characters;
- visible strings are data, not markup. An XSS-shaped title such as
  `<img onerror=...>` is valid literal text and must be assigned with
  `textContent`. There is no HTML, SVG, or style field in this schema;
- colours are exactly `#RRGGBB`;
- `focusX` and `focusY` are finite values in `[0,1]`; zoom is in the frozen
  safe range `[1,1.5]`;
- brand URLs use `https`; CTA URLs use `https` or `mailto`; media/poster URLs
  use `https` or a safe root-relative path. `javascript:` is invalid;
- every `mediaAssetId` is a versioned UUID that exists in `media_assets` and
  is not reserved for purge;
- one `mediaAssetId` always resolves to one `mediaUrl` and one optional
  `posterUrl` across all cards, and those values must equal the canonical URLs
  on its `media_assets` row, which keeps runtime source deduplication
  deterministic;
- `poster_path` and `poster_url` are either both null or both present;
- a draft may use a `ready` asset or retain an `archived` historical asset;
  publishing requires every referenced asset to be `ready`.
- publication proves that every video/poster path exists in `storage.objects`.
  The only video-object exceptions are the three exact seed tuples documented
  below: their fixed media ID, null `created_by`, bundled path, and canonical
  `/clips/*.mp4` URL must all match. A `bundled/` prefix alone grants no
  exemption.

The database rejects unknown top-level, card, and site keys. This keeps the
published format versioned and prevents a typo from silently becoming
unvalidated data.

## Draft, publish, and rollback

`save_content_draft(expected_revision, manifest)` locks the singleton draft,
compares `expected_revision`, validates the candidate, increments revision by
one, and returns the saved draft as JSON. A stale editor receives SQLSTATE
`40001`; it must reload and reconcile rather than overwrite another edit.

`publish_content(expected_revision, release_note)` performs one database
transaction:

1. authenticate the caller and require an `admin_users` row;
2. lock and revision-check the singleton draft;
3. validate structure and require every referenced media row to be `ready`;
4. allocate the next integer version while the draft lock serializes
   publishers;
5. write a new immutable `content_versions` row;
6. move `site_state.active_version_id` to that row;
7. copy the published version number back into the draft and increment draft
   revision.

Any failure rolls back all seven steps. There is no intermediate state where a
version exists without being active, or the active pointer changes without the
version.

`rollback_content(version_id)` is intentionally not a public rollback. It
locks the draft and copies the selected historical manifest into it, incrementing
the draft revision. `site_state` remains unchanged. The admin must review and
call `publish_content` to create a new immutable version.

## Public and admin RPCs

All privileged implementations are `security definer` functions in the
non-exposed `private` schema. They use `search_path = ''`, schema-qualified
relations, and an explicit `auth.uid()` lookup in `admin_users`. Public-schema
functions are `security invoker` wrappers. Every function starts with default
execution revoked and then receives an exact grant.

| RPC | Roles | Result |
| --- | --- | --- |
| `get_active_content_manifest()` | `anon`, `authenticated` | Raw active manifest `jsonb`, or SQL null before initialization |
| `save_content_draft(expected_revision, manifest)` | approved admin | Saved draft JSON with new revision |
| `publish_content(expected_revision, release_note)` | approved admin | New version JSON plus `draftRevision` |
| `rollback_content(version_id)` | approved admin | Restored draft JSON; active version unchanged |
| `get_media_asset_reference_counts(media_asset_id)` | approved admin | Draft, active, published-card, and published-version counts |
| `archive_media_asset(media_asset_id)` | approved admin | Archived media row |
| `prepare_media_asset_purge(media_asset_id)` | approved admin | Locked paths and zero-reference proof |
| `cancel_media_asset_purge(media_asset_id)` | approved admin | Clears an unfinished purge reservation |
| `finalize_media_asset_purge(media_asset_id, expected_storage_path, expected_poster_path)` | approved admin | Deletes the zero-reference metadata row |

Anonymous users have no direct grants on any content table. The active-manifest
RPC is the only anonymous database content read surface. Authenticated admins
can select draft/history/site state, and can insert/update media metadata under
RLS. Draft/version/site writes remain RPC-only so direct table calls cannot
bypass validation, revision checks, or atomic publication.

## Media lifecycle and purge

The allowed state labels are `uploading`, `ready`, `failed`, and `archived`.
Archive never removes bytes and is safe even when a published version still
references the asset.

Permanent purge uses two phases:

1. Archive the asset.
2. Call `prepare_media_asset_purge`. It locks the draft before the media row,
   proves there are zero draft and retained-version references, records
   `purge_requested_at`, and returns the exact video/poster paths.
3. Delete those exact objects with the authenticated Storage API.
4. Call `finalize_media_asset_purge` with the returned paths. It re-locks and
   rechecks references and paths, and queries `storage.objects` to prove both
   video and poster are absent, before deleting metadata.
5. If object deletion fails, leave the metadata row reserved and retry, or call
   `cancel_media_asset_purge`.

While a purge reservation exists, manifest validation rejects a new reference.
Direct database deletion is not granted even to an admin browser session.
The Storage DELETE policy recognizes only the reservation's exact paths (plus
upload-failure cleanup), so a normal administrator token cannot bypass retained
version protection by deleting bytes directly.

## Seed identity

The seed migration stores the same 24 cards and site copy as
`src/content/default-content.json`. It uses stable media IDs:

- `11111111-1111-4111-8111-111111111111` — `niulai-intro.mp4`;
- `22222222-2222-4222-8222-222222222222` — `cursor-niulai.mp4`;
- `33333333-3333-4333-8333-333333333333` — `pelican-ai.mp4`.

The first published row is version 1 at
`00000000-0000-4000-8000-000000000101`. Its URLs remain the bundled
`/clips/*.mp4` paths, so applying the schema does not make the accepted product
depend on an upload that has not happened yet. This exception also requires
the matching fixed ID, exact `bundled/<filename>` path, null `created_by`, and
no poster; it cannot be extended by inserting another `bundled/` row.
