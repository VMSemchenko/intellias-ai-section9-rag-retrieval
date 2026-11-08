---
id: policy-oncall
title: "Policy: on-call rotation, severities and escalation"
doc_type: policy
service: platform
status: active
visibility: everyone
updated_at: 2026-07-21
---

# Policy: on-call rotation, severities and escalation

## Rotation

One primary and one secondary per owning team, weekly, handover Monday 10:00 local. The
platform on-call is always additionally paged for anything touching the gateway, shared
libraries or TLS.

A team without two people able to take the rotation cannot own a production service. In that
case ownership moves to Platform until the team is staffed.

## Severities

| Sev | Definition | Response | Comms |
|---|---|---|---|
| 1 | Revenue-affecting or total unavailability | page primary + secondary + incident commander, 5 min | status page within 15 min |
| 2 | Degraded for a subset of users, or a workaround exists | page primary, 15 min | internal channel |
| 3 | No user impact, but a safeguard is broken | next business day | ticket |

An alert that has fired for six days without anyone noticing is a Sev 3 in its own right —
see the catalog staleness and TLS expiry postmortems. Broken detection is an incident even
when nothing is currently on fire.

## Escalation

15 minutes without acknowledgement escalates to the secondary, then to the path in the
service ownership policy. Do not escalate by asking in a team channel; use the pager.

Escalating early is free. The most common regret in our incident reviews is waiting.

## During an incident

- The first person on becomes incident commander until they hand it over explicitly.
- One channel, `#incident-<date>`. Decisions in the channel, not in DMs.
- Mitigate first, understand second. A rollback that restores service before the cause is
  known is the correct move.
- Do not make two changes at once. You will not know which one worked.

## After

Sev 1 and Sev 2 require a written postmortem within 5 business days, blameless, with the
timeline in UTC and at least one change that would have shortened detection. A postmortem
whose only action item is "be more careful" is not accepted.
