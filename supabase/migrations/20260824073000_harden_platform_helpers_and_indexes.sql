begin;

create index if not exists content_drafts_updated_by_idx
  on public.content_drafts (updated_by)
  where updated_by is not null;

-- New Supabase projects install this event-trigger helper in public with broad
-- EXECUTE ACLs. The event trigger runs as its owner and does not need API-role
-- execution, so remove the unnecessary RPC-facing grants when it is present.
do $$
begin
  if to_regprocedure('public.rls_auto_enable()') is not null then
    revoke execute on function public.rls_auto_enable()
      from public, anon, authenticated, service_role;
  end if;
end;
$$;

commit;
