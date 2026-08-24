begin;

-- Authenticated media INSERT/UPDATE evaluates the media URL CHECK constraints
-- as the caller. is_media_url delegates HTTPS handling to is_https_url, so the
-- nested immutable helper also needs EXECUTE while the private schema remains
-- outside the exposed Data API schemas.
revoke execute on function private.is_https_url(text)
  from public, anon, service_role;
grant execute on function private.is_https_url(text)
  to authenticated;

commit;
