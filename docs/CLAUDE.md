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
│     credits          │◄───────│    end_time     │
│     hours (legacy)   │        │    created/upd  │
│     start/end_time   │        └─────────────────┘
│     court_cost       │
│     created/updated  │        ┌─────────────────┐
└──────────┬───────────┘◄──1:N──│  BIRDIE_BANK    │
           │                    ├─────────────────┤
           └────────────────────│ FK session_id   │
                                │ transaction_type│  purchase | usage
                                │    quantity     │
                                │    cost         │
                                │    notes        │
                                │    created/upd  │
                                └─────────────────┘

┌─────────────────┐
│  SITE_SETTINGS  │  (standalone key/value store)
├─────────────────┤
│ PK id           │
│    key (unique) │
│    value        │
│    updated_at   │
└─────────────────┘
```

## Relationship Summary

| Parent | Child | FK | Notes |
|--------|-------|----|-------|
| players | players | managed_by | Self-ref: parent votes/pays for dependent |
| players | attendances | player_id | |
| players | payments | player_id | |
| players | dropout_refunds | player_id | |
| sessions | courts | session_id | CASCADE DELETE |
| sessions | attendances | session_id | CASCADE DELETE |
| sessions | dropout_refunds | session_id | |
| sessions | birdie_bank | session_id | optional (usage entries only) |

---

## Table: `players`

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| `id` | INTEGER PK | Auto | |
| `name` | VARCHAR(100) NN | — | Full name |
| `category` | VARCHAR(20) NN | `regular` | `regular`, `adhoc`, `kid` |
| `email` | VARCHAR(100) | NULL | Login email |
| `password_hash` | VARCHAR(255) | NULL | Bcrypt hash |
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
| `credits` | FLOAT | 0 | **Collected from players this session; split across all non-kid players; funds adhoc courts; adjusts next month** |
| `hours` | FLOAT | 3 | Legacy session-level duration |
| `start_time` | VARCHAR(10) | `06:30` | Legacy HH:MM |
| `end_time` | VARCHAR(10) | `09:30` | Legacy HH:MM |
| `court_cost` | FLOAT | 105 | Legacy default court cost |
| `created_by/at` | | | Audit |
| `updated_by/at` | | | Audit (auto) |

**Indexes:** date, is_archived

**Cost model (key):**
```
total_pool       = SUM(courts.cost) + session.credits
per_player_cost  = total_pool / non_kid_count + birdie_cost
kids             = flat $11
```
Regular and adhoc players pay the same rate. Adhoc court costs are funded from credits.

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
| `session_id` | INTEGER FK NN | — | → sessions.id |
| `status` | VARCHAR(20) NN | `NO` | `YES`, `NO`, `TENTATIVE`, `DROPOUT`, `FILLIN`, `STANDBY` |
| `category` | VARCHAR(20) | `regular` | Per-session override: `regular`, `adhoc`, `kid` |
| `payment_status` | VARCHAR(20) | `unpaid` | `unpaid` or `paid` |
| `additional_cost` | FLOAT | 0 | Extra charge this session |
| `comments` | TEXT | NULL | Admin notes |
| `created_by/at` | | | Audit |
| `updated_by/at` | | | Audit (auto) |

**Unique:** (player_id, session_id)
**Indexes:** player_id, session_id, status, category, (status, category)
**Charged:** YES, DROPOUT, FILLIN — owe session cost
**Shown in session detail:** YES, FILLIN, STANDBY, DROPOUT (NO/TENTATIVE hidden)

---

## Table: `payments`

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| `id` | INTEGER PK | Auto | |
| `player_id` | INTEGER FK NN | — | → players.id |
| `amount` | FLOAT NN | — | Positive = payment; negative = refund |
| `method` | VARCHAR(20) NN | — | `Zelle`, `Cash`, `Venmo`, `Refund` |
| `date` | DATETIME | NOW | |
| `notes` | TEXT | NULL | |
| `created_by/at` | | | Audit |
| `updated_by/at` | | | Audit (auto) |

**Note:** Global (not session-specific). Per-session tracking via `attendances.payment_status`.

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
| `processed_date` | DATETIME | NULL | When issued — shown in Financial Summary |
| `created_by/at` | | | Audit |
| `updated_by/at` | | | Audit (auto) |

**Indexes:** player_id, session_id, status, (player_id, status)

---

## Table: `birdie_bank`

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| `id` | INTEGER PK | Auto | |
| `date` | DATETIME | NOW | |
| `transaction_type` | VARCHAR(20) NN | — | `purchase` or `usage` |
| `quantity` | INTEGER NN | — | Always positive; direction from type |
| `cost` | FLOAT | 0 | Purchases only |
| `notes` | TEXT | NULL | |
| `session_id` | INTEGER FK | NULL | → sessions.id (usage only) |
| `created_by/at` | | | Audit |
| `updated_by/at` | | | Audit (auto) |

---

## Table: `site_settings`

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| `id` | INTEGER PK | Auto | |
| `key` | VARCHAR(50) NN unique | — | Setting name |
| `value` | TEXT | NULL | Setting value |
| `updated_at` | DATETIME | NOW | Auto-updated |
