# Templates Documentation

Conventions and guidance for working with templates in BP Badminton.

## Technology Stack

- **Jinja2** - Server-side templating
- **Tailwind CSS (CDN)** - Utility-first CSS
- **Alpine.js 3.x** - Lightweight JavaScript reactivity

## Theme Colors (Wimbledon-Inspired)

| Color | Hex | Tailwind Class | Usage |
|-------|-----|----------------|-------|
| Purple | #44005C | `text-wimbledon-purple`, `bg-wimbledon-purple` | Primary brand |
| Green | #006633 | `text-wimbledon-green`, `bg-wimbledon-green` | Success, accents |
| Gold | #C4A747 | `text-wimbledon-gold`, `bg-wimbledon-gold` | Highlights |
| Cream | #F5F5DC | `bg-wimbledon-cream` | Backgrounds |

## Template Files

| Template | Purpose |
|----------|---------|
| `base.html` | Base layout with navigation, includes Tailwind/Alpine, `{% block head %}` for extra scripts |
| `login.html` | Admin and player login + Google Sign-In |
| `register.html` | Player self-registration |
| `dashboard.html` | Admin dashboard with KPIs (tiles are clickable `<a>` links for mobile tap navigation) |
| `players.html` | Player list with filters |
| `player_form.html` | Add/edit player |
| `player_detail.html` | Player details, attendance, payments |
| `player_profile.html` | Player self-service profile |
| `player_sessions.html` | Player session voting (grouped by month) |
| `player_payments.html` | Player payment recording (frozen_only charges) |
| `sessions.html` | Session matrix with attendance, month filter, bulk actions |
| `session_form.html` | Add/edit session with courts |
| `session_detail.html` | Session details with attendance, freeze/release/archive toggles |
| `session_refunds.html` | Dropout refund management |
| `payments.html` | Payment list with search/sort |
| `payment_form.html` | Add payment |
| `birdie_bank.html` | Shuttlecock inventory |
| `month_sessions.html` | Monthly session summary |
| `notifications.html` | Player notifications |
| `admin_notifications.html` | Admin notification management |
| `activity_logs.html` | Audit log viewer |
| `guidelines.html` | Club guidelines (editable via SiteSettings) |
| `ezfacility_settings.html` | EZFacility integration settings |
| `ezfacility_sync.html` | Court booking sync from EZFacility |
| `reset_admin_password.html` | Admin password reset |

## Alpine.js Patterns

### State Management
```html
<div x-data="{ selectedSessions: [], paymentFilter: 'all', searchQuery: '' }">
```

### Conditional Display
```html
<div x-show="selectedSessions.length > 0" x-cloak>
```

### Event Handling
```html
<select @change="updateAttendance(sessionId, playerId, $event.target.value)">
```

### Dynamic Classes
```html
<button :class="paymentFilter === 'all' ? 'bg-wimbledon-purple text-white' : 'bg-white'">
```

## Mobile Responsive Patterns

All templates use Tailwind `sm:` breakpoints for mobile-first layouts. Key patterns:

### Responsive Text
```html
<h2 class="text-sm sm:text-lg font-bold">Title</h2>
<span class="text-xs sm:text-sm">Detail text</span>
```

### Hidden Columns on Mobile
```html
<th class="hidden sm:table-cell">Non-essential column</th>
<td class="hidden sm:table-cell">...</td>
```

### Flex Wrap for Button Groups
```html
<div class="flex flex-wrap items-center gap-2 sm:gap-3">
    <button class="text-xs sm:text-sm px-2 sm:px-3 py-1 sm:py-2">Action</button>
</div>
```

### Compact Padding
```html
<div class="px-2 sm:px-4 py-2 sm:py-4">
<td class="px-1 sm:px-3 py-1 sm:py-2">
```

## Common UI Components

### Status Badges
```html
<!-- Paid -->
<span class="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold bg-green-100 text-green-700">Paid</span>

<!-- Unpaid -->
<span class="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold bg-red-100 text-red-700">Unpaid</span>

<!-- Refund Pending -->
<span class="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold bg-orange-100 text-orange-700">Refund Pending</span>

<!-- Payment Released (amber) -->
<span class="px-3 py-1 bg-amber-100 text-amber-700 rounded-full text-sm font-medium">Payment Released</span>
```

### Attendance Dropdown Colors
```html
{% if status == 'YES' %}bg-green-100 border-green-500 text-green-700
{% elif status == 'NO' %}bg-red-100 border-red-500 text-red-700
{% elif status == 'TENTATIVE' %}bg-yellow-100 border-yellow-500 text-yellow-700
{% elif status == 'FILLIN' %}bg-blue-100 border-blue-500 text-blue-700
{% elif status == 'DROPOUT' %}bg-orange-100 border-orange-500 text-orange-700
{% elif status == 'STANDBY' %}bg-teal-100 border-teal-300 text-teal-700
{% elif status == 'PENDING_STANDBY' %}bg-teal-100 border-teal-300 text-teal-700
{% elif status == 'PENDING_DROPOUT' %}bg-orange-100 border-orange-300 text-orange-700
{% else %}bg-gray-100 border-gray-300 text-gray-500{% endif %}
```

### Profile Photo with Fallback
Photos are stored in the database (survives Render deploys). Served via `/player-photo/<id>` route with ETag caching.
**Important:** Use `profile_photo_mime` (not `profile_photo_data`) for existence checks — `profile_photo_data` is deferred and would trigger a separate DB query:
```html
{% if player.profile_photo_mime %}
<img src="{{ url_for('player_photo', player_id=player.id) }}"
     class="w-8 h-8 rounded-full object-cover">
{% else %}
<div class="w-8 h-8 rounded-full bg-gradient-to-br from-wimbledon-purple to-wimbledon-green
            flex items-center justify-center text-white text-xs font-bold">
    {{ player.name[0].upper() }}
</div>
{% endif %}
```

## JavaScript Functions

### Update Attendance (AJAX)
```javascript
function updateAttendance(sessionId, playerId, status) {
    fetch('/api/attendance', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content
        },
        body: JSON.stringify({ session_id: sessionId, player_id: playerId, status: status || 'CLEAR' })
    })
    .then(response => response.json())
    .then(data => data.success ? location.reload() : alert(data.error));
}
```

## Pre-computed Template Variables

**IMPORTANT:** Never call model methods (e.g. `sess.get_cost_per_player()`, `player.get_balance()`) inside template loops — these trigger N+1 database queries. Routes must pre-compute all data and pass it as dicts.

### Session Display Stats (`session_stats`)
Computed by `compute_session_display_stats(session_ids)` — used in `player_sessions.html`, `player_profile.html`:
```html
{% set start_time, end_time = session_stats[sess.id].time_range %}
{{ session_stats[sess.id].court_count }}
{{ session_stats[sess.id].attendee_count }}
{{ session_stats[sess.id].cost_per_player }}
```

### Single Session Stats (`sess_stats`)
Used in `session_detail.html`:
```html
{% set start_time, end_time = sess_stats.time_range %}
{{ sess_stats.court_count }}
{{ sess_stats.attendee_count }}
{{ sess_stats.cost_per_player }}
{{ sess_stats.birdie_total }}
{{ sess_stats.total_collection }}
```

### Per-Attendance Costs (`att_cost_map`)
Used in `player_detail.html`, `player_profile.html`:
```html
{{ att_cost_map.get(attendance.id, 0) }}
```

### Player Financials (`player_total_charges`, `player_balance`)
Used in `player_detail.html` — pre-computed in route, not from model methods:
```html
{{ player_total_charges }}
{{ player_total_payments }}
{{ player_balance }}
```

### Sessions Page (`player_stats`)
```python
player_stats[player.id] = {
    'balance': float,
    'total_payments': float,
    'pending_refunds': int,
    'pending_refund_amount': float,
    'total_refunded': float,
    'fillin_amount': float,
    'fillin_paid': float
}
```

### Player Payments Page (frozen_only)
Charges and balance pre-computed in route via `player_financials` dict:
```html
{{ player_financials[pid].total_charges }}
{{ player_financials[pid].balance }}
```

## Form Patterns

### CSRF Token
All forms must include CSRF token (handled by Flask-WTF):
```html
<meta name="csrf-token" content="{{ csrf_token() }}">
```

### Confirmation Dialog
```html
<form onsubmit="return confirm('Are you sure?')">
```

### Trivia Banner (Login)
The login trivia flash message uses a themed gradient banner with animation:
```html
<!-- Purple-to-green gradient background, gold header, shuttlecock icon, slide-in animation -->
<div class="bg-gradient-to-r from-wimbledon-purple to-wimbledon-green rounded-xl p-4 text-white animate-slide-in">
    <div class="text-wimbledon-gold font-bold text-lg">Did You Know?</div>
    <span class="text-4xl">&#x1F3F8;</span>  <!-- Large shuttlecock icon -->
    <p class="text-sm">{{ trivia_text }}</p>
</div>
```

### Payment Filter Dropdown (Sessions Page)
The payment filter uses a `<select>` dropdown with inline count badges instead of buttons:
```html
<select x-model="paymentFilter">
    <option value="all">All</option>
    <option value="paid">Paid (N)</option>
    <option value="unpaid">Unpaid (N)</option>
    <option value="np">Not Playing (N)</option>
</select>
```
Counts are computed from the attendance data and shown inline in each option.

### Form alignment in flex containers
Use `class="flex"` on `<form>` elements inside flex containers (not `class="inline"`):
```html
<div class="flex flex-wrap items-center gap-3">
    <form method="POST" action="..." class="flex">
        <button type="submit" class="...">Action</button>
    </form>
</div>
```
