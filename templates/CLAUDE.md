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
| `dashboard.html` | Admin dashboard with KPIs |
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
{% else %}bg-gray-100 border-gray-300 text-gray-500{% endif %}
```

### Profile Photo with Fallback
Photos are stored in the database (survives Render deploys). Served via `/player-photo/<id>` route:
```html
{% if player.profile_photo %}
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

For performance, some routes pass pre-computed data:

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

Use in template:
```html
{% set stats = player_stats[player.id] %}
{{ stats.balance }}
```

### Player Payments Page (frozen_only)
Charges and balance use `frozen_only=True` — only sessions with `payment_released=True` or `is_archived=True` are included:
```html
{{ player.get_total_charges(frozen_only=True) }}
{{ player.get_balance(frozen_only=True) }}
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

### Form alignment in flex containers
Use `class="flex"` on `<form>` elements inside flex containers (not `class="inline"`):
```html
<div class="flex flex-wrap items-center gap-3">
    <form method="POST" action="..." class="flex">
        <button type="submit" class="...">Action</button>
    </form>
</div>
```
