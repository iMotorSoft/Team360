-- Team360 migration 022 — safe citizen case notifications V1.
-- Additive V1 only: minimal, deterministic, public outbound communication to
-- the citizen (RECEIVED / IN_PROGRESS / RESOLVED). The trace is isolated from
-- the operational message history and the immutable audit snapshot. No LLM is
-- used to render public text and no internal Flow state is ever written here.
-- Depends on migrations 011 through 021.

-- ---------------------------------------------------------------------------
-- Citizen notification trace. This is NOT a duplicate of flow_messages: the
-- operational table cannot safely represent notification type, delivery status,
-- provider reconciliation or a request-level dedupe key. Keeping the public
-- outbound trace separate also guarantees it never contaminates the immutable
-- audit snapshot or the Directorio timeline.
-- ---------------------------------------------------------------------------
create table if not exists flow_citizen_notifications (
    id                              uuid        primary key default gen_random_uuid(),
    request_id                      uuid        not null references flow_requests(id),
    notification_type               text        not null,
    channel                         text        not null default 'email',
    recipient                       text        not null,
    public_reference                text        not null,
    subject                         text        not null default '',
    body                            text        not null default '',
    dedupe_key                      text        not null,
    status                          text        not null default 'PENDING',
    provider_message_id             text,
    provider_thread_id              text,
    outbound_rfc_message_id         text,
    outbound_observed_rfc_message_id text,
    attempt_count                   integer     not null default 0,
    last_error_code                 text,
    last_error_detail               text,
    sent_at_utc                     timestamptz,
    created_at_utc                  timestamptz not null default now(),
    updated_at_utc                  timestamptz not null default now(),
    constraint chk_flow_citizen_notification_type check (
        notification_type in (
            'CITIZEN_RECEIVED',
            'CITIZEN_IN_PROGRESS',
            'CITIZEN_INFO_REQUIRED',
            'CITIZEN_RESOLVED'
        )
    ),
    constraint chk_flow_citizen_notification_channel check (
        channel = 'email'
    ),
    constraint chk_flow_citizen_notification_status check (
        status in ('PENDING', 'SENT', 'DELIVERY_UNCERTAIN', 'DELIVERY_FAILED')
    ),
    constraint chk_flow_citizen_notification_recipient check (
        length(trim(recipient)) > 0
    ),
    constraint chk_flow_citizen_notification_reference check (
        length(trim(public_reference)) > 0
    ),
    constraint chk_flow_citizen_notification_attempts check (attempt_count >= 0),
    -- Deterministic idempotency: exactly one trace (and one eventual public
    -- send) per request and public notification type, regardless of retries.
    constraint uq_flow_citizen_notification_dedupe unique (request_id, notification_type),
    -- A SENT trace must carry provider evidence and a send timestamp.
    constraint chk_flow_citizen_notification_sent check (
        status <> 'SENT'
        or (sent_at_utc is not null and provider_message_id is not null)
    ),
    constraint chk_flow_citizen_notification_uncertain check (
        status <> 'DELIVERY_UNCERTAIN' or last_error_code is not null
    )
);

create index if not exists idx_flow_citizen_notifications_request
    on flow_citizen_notifications (request_id, created_at_utc);

create unique index if not exists uq_flow_citizen_notification_rfc
    on flow_citizen_notifications (outbound_rfc_message_id)
    where outbound_rfc_message_id is not null;

create unique index if not exists uq_flow_citizen_notification_provider
    on flow_citizen_notifications (provider_message_id)
    where provider_message_id is not null;

comment on table flow_citizen_notifications is
    'Traceable, deduplicated public citizen communication emitted by Flow policy.';
comment on column flow_citizen_notifications.dedupe_key is
    'Deterministic request_id + notification_type key for idempotent delivery.';
comment on column flow_citizen_notifications.body is
    'Sanitized public message; never contains internal Flow operational data.';

-- Reversal, only when explicitly approved and no citizen communication trace
-- must be retained:
-- drop table flow_citizen_notifications;
