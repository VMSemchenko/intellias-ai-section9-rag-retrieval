---
id: rb-platform-secret-rotation
title: "Runbook: rotating platform secrets and database credentials"
doc_type: runbook
service: platform
version: v2
status: active
visibility: everyone
updated_at: 2026-07-30
---

# Runbook: rotating platform secrets and database credentials

Quarterly for all secrets, immediately on suspected exposure.

## The general shape

Every rotation is the same three-phase pattern, and skipping the middle phase is how you
cause an outage:

1. **Add** the new credential alongside the old one. Both work.
2. **Wait** for every consumer to pick up the new one. Verify, do not assume.
3. **Remove** the old one.

The auth signing key rotation is a specific instance of this pattern with a specific wait
period; see its own runbook. The April 2026 outage was phase 1 and 3 in a single change.

## Database credentials

1. Create the new role with identical grants:

       CREATE ROLE app_2026q3 LOGIN PASSWORD '...';
       GRANT app_readwrite TO app_2026q3;

2. Write the new credential to the secret store as a *second* key. Do not overwrite.
3. Roll the deployment. Consumers read the new key preferentially.
4. Verify no sessions remain on the old role:

       SELECT usename, count(*) FROM pg_stat_activity GROUP BY usename;

5. Only when the count is zero: `DROP ROLE app_2026q2;`

Dropping the role while a connection pool still holds sessions on it will not fail the
`DROP` — it will fail every subsequent reconnect, minutes later, in a way that looks
unrelated to your change.

## Webhook signing secrets

Subscriptions support two active secrets. Add the new one, tell the partner, wait for them
to confirm they verify against both, then remove the old. Partners routinely take weeks.
Plan the rotation around that rather than forcing it.

## On suspected exposure

Skip the wait. Accept the failures, announce them first, and revoke immediately. A short
outage is preferable to a live credential in a public place. Record the exposure window in
the incident ticket.

## Verification

No secret older than 100 days may remain. `platform-cli secrets audit --max-age 100d`
runs weekly and fails the build for the owning team's repository.
