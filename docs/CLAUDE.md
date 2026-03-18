# Database Schema Documentation

## Entity Relationship Diagram

```
┌─────────────────────┐
│       PLAYERS       │◄──── managed_by (self-ref FK)
├─────────────────────┤
│ PK  id              │
│     name            │
│     category        │  regular | adhoc | kid
│     email           │
│     password_hash   │
│     phone           │
│     date_of_birth   │
│     gender          │
│     profile_photo   │
│     zelle_preference│
│     managed_by (FK) │──► players.id
│     is_admin        │
│     is_active       │
│     is_approved     │
│     additional_chgs │
│     admin_comments  │
│     created/updated │
└──────────┬──────────┘
           │ 1:N (to all tables below via player_id)
    ┌──────┴──────────┬─────────────────┐
    ▼                 ▼                 ▼
┌───────────────┐  ┌──────────┐  ┌──────────────────┐
│  ATTENDANCES  │  │ PAYMENTS │  │ DROPOUT_REFUNDS   │
├───────────────┤  ├──────────┤  ├──────────────────┤
│ PK id         │  │ PK id    │  │ PK id            │
│ FK player_id  │  │FK player │  │ FK player_id     │
│ FK session_id │  │  amount  │  │ FK session_id    │
│    status     │  │  method  │  │    refund_amount  │
│    category   │  │  date    │  │    suggested_amt  │
│ payment_status│  │  notes   │  │    instructions  │
│ additional_   │  │ created/ │  │    status        │
│    cost       │  │ updated  │  │    processed_date│
│    comments   │  └──────────┘  │    created/upd   │
│ created/upd   │                └──────────────────┘
└───────┬───────┘
        │ N:1
        ▼
┌──────────────────────┐        ┌─────────────────┐
│       SESSIONS       │◄──1:N──│     COURTS      │
├──────────────────────┤        ├─────────────────┤
│ PK  id               │        │ PK id           │
│     date             │        │ FK session_id   │
│     birdie_cost      │        │    name         │
│     notes            │        │    court_type   │  regular | adhoc
│     is_archived      │        │    cost         │
│     voting_frozen    │        │    start_time   │
│     payment_released │        │    end_time     │
│     credits          │        │    created/upd  │
│     apply_credits    │        └─────────────────┘
│     hours (legacy)   │
│     start/end_time   │        ┌─────────────────┐
│     court_cost       │◄──1:N──│  BIRDIE_BANK    │
│     created/updated  │        ├─────────────────┤
└──────────────────────┘        │ PK id           │
                                │ FK session_id   │
                                │ FK purchased_by │──► players.id
                                │ transaction_type│  purchase | usage | reimbursement
                                │    quantity     │
                                │    cost         │
                                │    notes        │
                                │    created/upd  │
                                └─────────────────┘

┌──────────────────────┐        ┌──────────────────────┐
│   ACTIVITY_LOGS      │        │    NOTIFICATIONS     │
├──────────────────────┤        ├──────────────────────┤
│ PK  id               │        │ PK  id               │
│     timestamp        │        │     title            │
│     user_type        │        │     message          │
│     user_name        │        │     type             │
│     action           │        │     target           │
│     entity_type      │        │ FK  player_id        │──► players.id
│     entity_id        │        │     link             │
│     description      │        │ FK  created_by       │──► players.id
│     ip_address       │        │     created_at       │
└──────────────────────┘        └──────────┬───────────┘
                                           │ 1:N
                                           ▼
                                ┌──────────────────────┐
                                │  NOTIFICATION_READS  │
                                ├──────────────────────┤
                                │ PK  id               │
                                │ FK  notification_id  │
                                │ FK  player_id        │──► players.id
                                │     read_at          │
                                │  UQ (notif, player)  │
                                └──────────────────────┘

┌─────────────────────────┐     ┌─────────────────┐
│ EXTERNAL_INTEGRATIONS   │     │  SITE_SETTINGS  │
├─────────────────────────┤     ├─────────────────┤
│ PK  id                  │     │ PK id           │
│     name (unique)       │     │    key (unique) │
│     url (encrypted)     │     │    value        │
│     username (encrypted)│     │    updated_at   │
│     password (encrypted)│     └─────────────────┘
│     session_cookie (enc)│
│     created/updated     │
└─────────────────────────┘
```

## Relationship Summary

| Parent | Child | FK | Notes |
|--------|-------|----|-------|
| players | players | managed_by | Self-ref: parent votes/pays for dependent |
| players | attendances | player_id | |
| players | payments | player_id | |
| players | dropout_refunds | player_id | |
| players | notifications | player_id | Target player for notification |
| players | birdie_bank | purchased_by | Who paid for purchase |
| sessions | courts | session_id | CASCADE DELETE |
| sessions | attendances | session_id | CASCADE DELETE |
| sessions | dropout_refunds | session_id | Manual cleanup on delete |
| sessions | birdie_bank | session_id | Optional (usage entries only) |
| notifications | notification_reads | notification_id | |

---

## Table: `players`

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| `id` | INTEGER PK | Auto | |
| `name` | VARCHAR(100) NN | — | Full name |
| `category` | VARCHAR(20) NN | `regular` | `regular`, `adhoc`, `kid` |
| `email` | VARCHAR(100) | NULL | Login email |
| `password_hash` | VARCHAR(255) | NULL | pbkdf2:sha256 hash |
| `phone` | VARCHAR(20) | NULL | |
| `date_of_birth` | DATE | NULL | Optional |
| `gender` | VARCHAR(10) | `male` | `male`, `female`, `other` |
| `profile_photo` | VARCHAR(255) | NULL | Uploaded filename |
| `zelle_preference` | VARCHAR(10) | `email` | `email` or `phone` |
| `managed_by` | INTEGER FK | NULL | → players.id |
| `is_admin` | BOOLEAN | FALSE | Player-level admin |
| `is_active` | BOOLEAN | TRUE | Active membership |
| `is_approved` | BOOLEAN | FALSE | Admin approval required |
| `additional_charges` | FLOAT | 0 | Extra charges by admin |
| `admin_comments` | TEXT | NULL | Admin notes |
| `created_by/at` | | | Audit |
| `updated_by/at` | | | Audit (auto) |

**Indexes:** name, category, email, is_active, is_approved

---

## Table: `sessions`

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| `id` | INTEGER PK | Auto | |
| `date` | DATE NN | — | Session date |
| `birdie_cost` | FLOAT NN | 0 | Birdie cost per non-kid player |
| `notes` | TEXT | NULL | |
| `is_archived` | BOOLEAN | FALSE | Session closed |
| `voting_frozen` | BOOLEAN | FALSE | Locks player votes |
| `payment_released` | BOOLEAN | FALSE | When True, charges visible on player payment screen |
| `credits` | FLOAT | 0 | Collected from players; split across non-kid players |
| `apply_credits` | BOOLEAN | FALSE | Include credits in per-player cost calculation |
| `hours` | FLOAT | 3 | Legacy session-level duration |
| `start_time` | VARCHAR(10) | `06:30` | Legacy HH:MM |
| `end_time` | VARCHAR(10) | `09:30` | Legacy HH:MM |
| `court_cost` | FLOAT | 105 | Legacy default court cost |
| `created_by/at` | | | Audit |
| `updated_by/at` | | | Audit (auto) |

**Indexes:** date, is_archived

**Session lifecycle:** Open → Voting Frozen → Payment Released → Archived

**Cost model:**
```
total_pool       = SUM(courts.cost WHERE type='regular') + (credits if apply_credits)
per_player_cost  = total_pool / non_kid_count + birdie_cost
kids             = flat $11
```
Regular and adhoc players pay the same rate.

---

## Table: `courts`

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| `id` | INTEGER PK | Auto | |
| `session_id` | INTEGER FK NN | — | → sessions.id (CASCADE DELETE) |
| `name` | VARCHAR(50) | `Court` | e.g. "Court 1" |
| `court_type` | VARCHAR(20) | `regular` | `regular` or `adhoc` |
| `cost` | FLOAT NN | 0 | Rental cost |
| `start_time` | VARCHAR(20) NN | — | e.g. "6:30 AM" |
| `end_time` | VARCHAR(20) NN | — | e.g. "9:30 AM" |
| `created_by/at` | | | Audit |
| `updated_by/at` | | | Audit (auto) |

---

## Table: `attendances`

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| `id` | INTEGER PK | Auto | |
| `player_id` | INTEGER FK NN | — | → players.id |
| `session_id` | INTEGER FK NN | — | → sessions.id (CASCADE DELETE) |
| `status` | VARCHAR(20) NN | `NO` | `YES`, `NO`, `TENTATIVE`, `DROPOUT`, `FILLIN`, `STANDBY`, `PENDING_DROPOUT` |
| `category` | VARCHAR(20) | `regular` | Per-session override: `regular`, `adhoc`, `kid` |
| `payment_status` | VARCHAR(20) | `unpaid` | `unpaid`, `paid`, `pending_refund` |
| `additional_cost` | FLOAT | 0 | Extra charge this session |
| `comments` | TEXT | NULL | Admin notes |
| `created_by/at` | | | Audit |
| `updated_by/at` | | | Audit (auto) |

**Unique:** (player_id, session_id)
**Indexes:** player_id, session_id, status, category, payment_status, (status, category), (session_id, status, category)
**Charged statuses:** YES, DROPOUT, FILLIN, PENDING_DROPOUT

---

## Table: `payments`

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| `id` | INTEGER PK | Auto | |
| `player_id` | INTEGER FK NN | — | → players.id |
| `amount` | FLOAT NN | — | Positive = payment; negative = refund credit |
| `method` | VARCHAR(20) NN | — | `Zelle`, `Cash`, `Venmo`, `Check`, `Other`, `Refund` |
| `date` | DATETIME | NOW | |
| `notes` | TEXT | NULL | |
| `created_by/at` | | | Audit |
| `updated_by/at` | | | Audit (auto) |

**Indexes:** player_id, date
**Note:** Global (not session-specific). Balance = charges(`frozen_only`) − payments(`amount > 0`). Negative payments are refund credits created by dropout processing.

---

## Table: `dropout_refunds`

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| `id` | INTEGER PK | Auto | |
| `player_id` | INTEGER FK NN | — | → players.id |
| `session_id` | INTEGER FK NN | — | → sessions.id |
| `refund_amount` | FLOAT NN | 0 | Actual refund |
| `suggested_amount` | FLOAT | 0 | System suggestion |
| `instructions` | TEXT | NULL | Admin notes |
| `status` | VARCHAR(20) | `pending` | `pending`, `processed`, `cancelled` |
| `processed_date` | DATETIME | NULL | When issued |
| `created_by/at` | | | Audit |
| `updated_by/at` | | | Audit (auto) |

**Indexes:** player_id, session_id, status, (player_id, status)
**Cleanup:** Manually deleted when parent session is deleted (not cascade).

---

## Table: `birdie_bank`

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| `id` | INTEGER PK | Auto | |
| `date` | DATETIME | NOW | |
| `transaction_type` | VARCHAR(20) NN | — | `purchase`, `usage`, or `reimbursement` |
| `quantity` | INTEGER NN | — | Always positive; direction from type |
| `cost` | FLOAT | 0 | Purchases only |
| `notes` | TEXT | NULL | |
| `session_id` | INTEGER FK | NULL | → sessions.id (usage only) |
| `purchased_by` | INTEGER FK | NULL | → players.id (who paid/gets reimbursed) |
| `created_by/at` | | | Audit |
| `updated_by/at` | | | Audit (auto) |

---

## Table: `activity_logs`

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| `id` | INTEGER PK | Auto | |
| `timestamp` | DATETIME | NOW (ET) | Action timestamp |
| `user_type` | VARCHAR(20) NN | — | `admin`, `player`, `player_admin` |
| `user_name` | VARCHAR(100) NN | — | Display name or 'Admin' |
| `action` | VARCHAR(50) NN | — | e.g. `login`, `create_session`, `update_attendance` |
| `entity_type` | VARCHAR(50) | NULL | e.g. `session`, `player`, `payment` |
| `entity_id` | INTEGER | NULL | ID of affected entity |
| `description` | TEXT NN | — | Human-readable description |
| `ip_address` | VARCHAR(45) | NULL | IPv4 or IPv6 |

**Indexes:** action, (timestamp, action)

---

## Table: `notifications`

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| `id` | INTEGER PK | Auto | |
| `title` | VARCHAR(200) NN | — | Notification title |
| `message` | TEXT NN | — | Body text |
| `type` | VARCHAR(30) | `general` | `general`, `dropout_request`, `registration`, `system` |
| `target` | VARCHAR(20) | `all` | `all`, `admin`, `player` |
| `player_id` | INTEGER FK | NULL | → players.id (specific player or NULL for broadcast) |
| `link` | VARCHAR(255) | NULL | Optional navigation URL |
| `created_by` | INTEGER FK | NULL | → players.id |
| `created_at` | DATETIME | NOW | |

**Indexes:** (target, created_at), (player_id, created_at)

---

## Table: `notification_reads`

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| `id` | INTEGER PK | Auto | |
| `notification_id` | INTEGER FK NN | — | → notifications.id |
| `player_id` | INTEGER FK NN | — | → players.id |
| `read_at` | DATETIME | NOW | |

**Unique:** (notification_id, player_id)

---

## Table: `external_integrations`

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| `id` | INTEGER PK | Auto | |
| `name` | VARCHAR(50) NN unique | — | e.g. `ezfacility` |
| `url` | TEXT (encrypted) | NULL | Service URL |
| `username` | TEXT (encrypted) | NULL | Login username |
| `password` | TEXT (encrypted) | NULL | Login password |
| `session_cookie` | TEXT (encrypted) | NULL | Cached session cookie |
| `created_at` | DATETIME | NOW | |
| `updated_at` | DATETIME | NOW | Auto-updated |

**Encryption:** Fernet symmetric encryption derived from app `SECRET_KEY`.

---

## Table: `site_settings`

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| `id` | INTEGER PK | Auto | |
| `key` | VARCHAR(50) NN unique | — | Setting name |
| `value` | TEXT | NULL | Setting value |
| `updated_at` | DATETIME | NOW | Auto-updated |
