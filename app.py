from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, make_response
from functools import wraps
from datetime import datetime, date
from werkzeug.utils import secure_filename
import os
import uuid
import logging
from collections import defaultdict
from logging.handlers import RotatingFileHandler
from config import Config
from models import db, Player, Session, Court, Attendance, Payment, BirdieBank, DropoutRefund, SiteSettings, ExternalIntegration, init_encryption
from sqlalchemy import func
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_caching import Cache
from flask_migrate import Migrate

app = Flask(__name__)
app.config.from_object(Config)

# Caching Configuration
app.config['CACHE_TYPE'] = 'SimpleCache'  # In-memory cache (use 'RedisCache' for production with Redis)
app.config['CACHE_DEFAULT_TIMEOUT'] = 300  # 5 minutes default
cache = Cache(app)

# CSRF Protection
csrf = CSRFProtect(app)

# Rate Limiting
limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"
)


# Static file cache headers (1 week for assets)
@app.after_request
def add_cache_headers(response):
    # Cache static files (CSS, JS, images) for 1 week
    if request.path.startswith('/static/'):
        response.headers['Cache-Control'] = 'public, max-age=604800'  # 1 week
    return response

# Logging Configuration
if not os.path.exists('logs'):
    os.makedirs('logs')

# Security audit log
security_handler = RotatingFileHandler('logs/security.log', maxBytes=10240000, backupCount=10)
security_handler.setFormatter(logging.Formatter(
    '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
))
security_handler.setLevel(logging.INFO)

security_logger = logging.getLogger('security')
security_logger.setLevel(logging.INFO)
security_logger.addHandler(security_handler)

# Application log
app_handler = RotatingFileHandler('logs/app.log', maxBytes=10240000, backupCount=10)
app_handler.setFormatter(logging.Formatter(
    '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
))
app_handler.setLevel(logging.INFO)
app.logger.addHandler(app_handler)
app.logger.setLevel(logging.INFO)
app.logger.info('BP Badminton startup')

# File upload configuration
UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # 5MB max

# Ensure upload folder exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def save_profile_photo(file):
    """Save uploaded profile photo and return filename"""
    if file and allowed_file(file.filename):
        # Generate unique filename
        ext = file.filename.rsplit('.', 1)[1].lower()
        filename = f"{uuid.uuid4().hex}.{ext}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        return filename
    return None

db.init_app(app)
migrate = Migrate(app, db)

# Initialise column encryption (key derived from SECRET_KEY — never stored)
init_encryption(app.config['SECRET_KEY'])

# Create tables
with app.app_context():
    db.create_all()


# Authentication decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('authenticated'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


# Admin-only decorator (allows both master admin and player admins)
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('authenticated'):
            return redirect(url_for('login'))
        if session.get('user_type') not in ['admin', 'player_admin']:
            flash('Admin access required', 'error')
            return redirect(url_for('player_profile'))
        return f(*args, **kwargs)
    return decorated_function


# Cached helper for monthly summary (expensive calculation)
@cache.memoize(timeout=60)  # Cache for 60 seconds
def get_cached_monthly_summary():
    """Calculate monthly summary with caching"""
    all_sessions = Session.query.order_by(Session.date.desc()).all()

    # Build session_id -> month_key map for pending refund lookup
    session_month_map = {sess.id: sess.date.strftime('%Y-%m') for sess in all_sessions}

    monthly_summary = {}
    for sess in all_sessions:
        key = sess.date.strftime('%Y-%m')
        label = sess.date.strftime('%B %Y')
        if key not in monthly_summary:
            monthly_summary[key] = {
                'label': label,
                'sessions': [],
                'total_sessions': 0,
                'archived_sessions': 0,
                'birdie_charges': 0,
                'regular_charges': 0,
                'adhoc_charges': 0,
                'kid_charges': 0,
                'total_refunds': 0,
                'total_collection': 0,
                'payments_received': 0,
                'pending_credits': 0,
                'session_credits': 0,
            }
        monthly_summary[key]['sessions'].append(sess)
        monthly_summary[key]['total_sessions'] += 1
        if sess.is_archived:
            monthly_summary[key]['archived_sessions'] += 1
        monthly_summary[key]['birdie_charges'] += sess.get_birdie_cost_total()
        monthly_summary[key]['regular_charges'] += sess.get_regular_player_charges()
        monthly_summary[key]['adhoc_charges'] += sess.get_adhoc_player_charges()
        monthly_summary[key]['kid_charges'] += sess.get_kid_player_charges()
        monthly_summary[key]['total_refunds'] += sess.get_total_refunds()
        monthly_summary[key]['total_collection'] += sess.get_total_collection()
        monthly_summary[key]['session_credits'] += (sess.credits or 0)

    # Actual payments received, grouped by payment month
    for payment in Payment.query.all():
        key = payment.date.strftime('%Y-%m')
        if key in monthly_summary:
            monthly_summary[key]['payments_received'] += payment.amount

    # Pending dropout refunds = credits owed back to players, grouped by session month
    for refund in DropoutRefund.query.filter_by(status='pending').all():
        key = session_month_map.get(refund.session_id)
        if key and key in monthly_summary:
            monthly_summary[key]['pending_credits'] += refund.refund_amount

    for key in monthly_summary:
        monthly_summary[key]['is_fully_archived'] = (
            monthly_summary[key]['total_sessions'] == monthly_summary[key]['archived_sessions']
        )

    return sorted(monthly_summary.items(), key=lambda x: x[0], reverse=True)


def clear_session_cache():
    """Clear session-related cache when data changes"""
    cache.delete_memoized(get_cached_monthly_summary)


# Master admin only decorator (for sensitive operations like promoting admins)
def master_admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('authenticated'):
            return redirect(url_for('login'))
        if session.get('user_type') not in ['admin', 'player_admin']:
            flash('Admin access required', 'error')
            return redirect(url_for('player_profile'))
        return f(*args, **kwargs)
    return decorated_function


# Auth routes
@app.route('/login', methods=['GET', 'POST'])
@limiter.limit("10 per minute")  # Rate limit: 10 login attempts per minute
def login():
    if request.method == 'POST':
        login_type = request.form.get('login_type', 'admin')
        client_ip = request.remote_addr

        if login_type == 'admin':
            password = request.form.get('password')
            if password == app.config['APP_PASSWORD']:
                session['authenticated'] = True
                session['user_type'] = 'admin'
                security_logger.info(f'ADMIN_LOGIN_SUCCESS - IP: {client_ip}')
                flash('Successfully logged in as admin!', 'success')
                return redirect(url_for('dashboard'))
            security_logger.warning(f'ADMIN_LOGIN_FAILED - IP: {client_ip}')
            flash('Invalid password', 'error')
        else:
            # Player login
            email = request.form.get('email', '').strip().lower()
            password = request.form.get('player_password')
            player = Player.query.filter(db.func.lower(Player.email) == email).first()
            if player and player.check_password(password):
                if not player.is_approved:
                    security_logger.info(f'LOGIN_PENDING_APPROVAL - Email: {email}, IP: {client_ip}')
                    flash('Your registration is pending approval. Please wait for admin approval.', 'error')
                    return render_template('login.html',
                                           member_guidelines=SiteSettings.get('member_guidelines', ''),
                                           booking_guidelines=SiteSettings.get('booking_guidelines', ''))
                if not player.is_active:
                    security_logger.warning(f'LOGIN_INACTIVE_ACCOUNT - Email: {email}, IP: {client_ip}')
                    flash('Your account has been deactivated. Please contact an admin.', 'error')
                    return render_template('login.html',
                                           member_guidelines=SiteSettings.get('member_guidelines', ''),
                                           booking_guidelines=SiteSettings.get('booking_guidelines', ''))
                session['authenticated'] = True
                session['player_id'] = player.id
                if player.is_admin:
                    session['user_type'] = 'player_admin'
                    security_logger.info(f'PLAYER_ADMIN_LOGIN_SUCCESS - Player: {player.name} (ID: {player.id}), IP: {client_ip}')
                    flash(f'Welcome back, {player.name}! (Admin)', 'success')
                    return redirect(url_for('dashboard'))
                else:
                    session['user_type'] = 'player'
                    security_logger.info(f'PLAYER_LOGIN_SUCCESS - Player: {player.name} (ID: {player.id}), IP: {client_ip}')
                    flash(f'Welcome back, {player.name}!', 'success')
                    return redirect(url_for('player_profile'))
            security_logger.warning(f'PLAYER_LOGIN_FAILED - Email: {email}, IP: {client_ip}')
            flash('Invalid email or password', 'error')

    return render_template('login.html',
                           member_guidelines=SiteSettings.get('member_guidelines', ''),
                           booking_guidelines=SiteSettings.get('booking_guidelines', ''))


@app.route('/logout')
def logout():
    session.pop('authenticated', None)
    session.pop('user_type', None)
    session.pop('player_id', None)
    flash('Logged out successfully', 'success')
    return redirect(url_for('login'))


@app.route('/register', methods=['GET', 'POST'])
@limiter.limit("5 per hour")  # Rate limit: 5 registrations per hour per IP
def register():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        phone = request.form.get('phone', '').strip()
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        client_ip = request.remote_addr

        # Validation
        if not name or not email or not password:
            flash('Name, email, and password are required', 'error')
            return render_template('register.html',
                               member_guidelines=SiteSettings.get('member_guidelines', ''),
                               booking_guidelines=SiteSettings.get('booking_guidelines', ''))

        if password != confirm_password:
            flash('Passwords do not match', 'error')
            return render_template('register.html',
                               member_guidelines=SiteSettings.get('member_guidelines', ''),
                               booking_guidelines=SiteSettings.get('booking_guidelines', ''))

        if len(password) < 4:
            flash('Password must be at least 4 characters', 'error')
            return render_template('register.html',
                               member_guidelines=SiteSettings.get('member_guidelines', ''),
                               booking_guidelines=SiteSettings.get('booking_guidelines', ''))

        # Check if email already exists
        existing_player = Player.query.filter(db.func.lower(Player.email) == email).first()
        if existing_player:
            security_logger.warning(f'REGISTRATION_DUPLICATE_EMAIL - Email: {email}, IP: {client_ip}')
            flash('An account with this email already exists. Please contact an admin to reset your password.', 'error')
            return render_template('register.html',
                               member_guidelines=SiteSettings.get('member_guidelines', ''),
                               booking_guidelines=SiteSettings.get('booking_guidelines', ''))

        # Create new player (pending approval)
        player = Player(
            name=name,
            email=email,
            phone=phone,
            category='regular',
            is_approved=False,
            is_active=True
        )
        player.set_password(password)

        db.session.add(player)
        db.session.commit()

        security_logger.info(f'REGISTRATION_SUCCESS - Name: {name}, Email: {email}, IP: {client_ip}')
        flash('Registration successful! Please wait for admin approval.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html',
                               member_guidelines=SiteSettings.get('member_guidelines', ''),
                               booking_guidelines=SiteSettings.get('booking_guidelines', ''))


# Health check endpoint for uptime monitoring (keeps Render from sleeping)
@app.route('/health')
def health_check():
    return 'OK', 200


# Guidelines Management
@app.route('/guidelines')
@admin_required
def guidelines():
    """Admin page to view and edit club guidelines"""
    member_guidelines = SiteSettings.get('member_guidelines', '')
    booking_guidelines = SiteSettings.get('booking_guidelines', '')
    return render_template('guidelines.html',
                           member_guidelines=member_guidelines,
                           booking_guidelines=booking_guidelines)


@app.route('/guidelines/edit', methods=['POST'])
@csrf.exempt
@admin_required
def edit_guidelines():
    """Save updated guidelines"""
    data = request.get_json(silent=True) or {}
    member_guidelines = data.get('member_guidelines', '')
    booking_guidelines = data.get('booking_guidelines', '')

    SiteSettings.set('member_guidelines', member_guidelines)
    SiteSettings.set('booking_guidelines', booking_guidelines)

    return jsonify({'success': True})


@app.route('/api/guidelines')
def get_guidelines():
    """Public API to get guidelines for login/register pages"""
    return jsonify({
        'member_guidelines': SiteSettings.get('member_guidelines', ''),
        'booking_guidelines': SiteSettings.get('booking_guidelines', '')
    })


# Dashboard
@app.route('/')
@login_required
def dashboard():
    # Redirect non-admin players to their profile
    if session.get('user_type') == 'player':
        return redirect(url_for('player_profile'))
    # Admin and player_admin can access dashboard

    total_players = Player.query.filter_by(is_approved=True).count()
    upcoming_sessions = Session.query.filter(
        Session.is_archived == False,
        Session.date >= date.today()
    ).count()

    # Monthly summary: last 6 months that have any session (archived or not), descending
    all_sessions_for_summary = Session.query.all()
    session_months = sorted(
        {(s.date.year, s.date.month) for s in all_sessions_for_summary},
        reverse=True
    )[:6]

    monthly_summary = []
    for year, month in session_months:
        month_start = date(year, month, 1)
        month_end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)

        m_sessions = [s for s in all_sessions_for_summary
                      if month_start <= s.date < month_end]
        # Month is "active" if it has at least one non-archived session
        is_active_month = any(not s.is_archived for s in m_sessions)

        m_charges = 0
        m_attendees = 0
        for sess in m_sessions:
            for att in sess.attendances:
                if att.status in ['YES', 'DROPOUT', 'FILLIN'] and att.player and att.player.is_active:
                    m_attendees += 1
                    if att.category == 'kid':
                        m_charges += sess.get_cost_per_kid()
                    elif att.category == 'adhoc':
                        m_charges += sess.get_cost_per_adhoc_player()
                    else:
                        m_charges += sess.get_cost_per_regular_player()
                    m_charges += (att.additional_cost or 0)

        m_payments = Payment.query.filter(
            Payment.date >= datetime.combine(month_start, datetime.min.time()),
            Payment.date < datetime.combine(month_end, datetime.min.time())
        ).all()
        m_collected = sum(p.amount for p in m_payments)

        m_birdie = sum(sess.get_birdie_cost_total() for sess in m_sessions)
        m_refunds = sum(sess.get_total_refunds() for sess in m_sessions)
        m_session_credits = sum(sess.credits or 0 for sess in m_sessions)

        monthly_summary.append({
            'month': month_start.strftime('%b %Y'),
            'month_key': month_start.strftime('%Y-%m'),
            'is_active': is_active_month,
            'sessions': len(m_sessions),
            'attendees': m_attendees,
            'charges': round(m_charges, 2),
            'collected': round(m_collected, 2),
            'outstanding': round(m_charges - m_collected, 2),
            'birdie': round(m_birdie, 2),
            'refunds': round(m_refunds, 2),
            'credits': round(m_session_credits, 2),
        })

    # Top cards: aggregate from active months (charges - collected for those months)
    total_collected = round(sum(r['collected'] for r in monthly_summary if r['is_active']), 2)
    total_charges = round(sum(r['charges'] for r in monthly_summary if r['is_active']), 2)
    total_outstanding = round(sum(r['outstanding'] for r in monthly_summary if r['is_active']), 2)

    # Pending approvals
    pending_approvals = Player.query.filter_by(is_approved=False).order_by(Player.created_at.desc()).all()

    return render_template('dashboard.html',
                         total_players=total_players,
                         upcoming_sessions=upcoming_sessions,
                         total_outstanding=total_outstanding,
                         total_collected=total_collected,
                         total_charges=round(total_charges, 2),
                         pending_approvals=pending_approvals,
                         monthly_summary=monthly_summary)


# Player self-service profile
@app.route('/player/profile', methods=['GET', 'POST'])
@login_required
def player_profile():
    if session.get('user_type') != 'player':
        return redirect(url_for('dashboard'))

    player_id = session.get('player_id')
    player = Player.query.get_or_404(player_id)

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'update_profile':
            name = request.form.get('name', '').strip()
            email = request.form.get('email', '').strip().lower()
            phone = request.form.get('phone', '').strip()

            if not name:
                flash('Name is required', 'error')
            else:
                # Check if email is taken by another player
                if email:
                    existing = Player.query.filter(
                        db.func.lower(Player.email) == email,
                        Player.id != player.id
                    ).first()
                    if existing:
                        flash('This email is already in use by another player', 'error')
                        return redirect(url_for('player_profile'))

                player.name = name
                player.email = email if email else None
                player.phone = phone if phone else None
                db.session.commit()
                flash('Profile updated successfully!', 'success')

        elif action == 'update_zelle':
            zelle_pref = request.form.get('zelle_preference')
            if zelle_pref in ['email', 'phone']:
                player.zelle_preference = zelle_pref
                db.session.commit()
                flash('Zelle preference updated!', 'success')

        elif action == 'change_password':
            current_password = request.form.get('current_password')
            new_password = request.form.get('new_password')
            confirm_password = request.form.get('confirm_password')

            if not player.check_password(current_password):
                flash('Current password is incorrect', 'error')
            elif new_password != confirm_password:
                flash('New passwords do not match', 'error')
            elif len(new_password) < 4:
                flash('Password must be at least 4 characters', 'error')
            else:
                player.set_password(new_password)
                db.session.commit()
                flash('Password changed successfully!', 'success')

        elif action == 'update_photo':
            if 'profile_photo' in request.files:
                file = request.files['profile_photo']
                if file and file.filename:
                    # Delete old photo if exists
                    if player.profile_photo:
                        old_path = os.path.join(app.config['UPLOAD_FOLDER'], player.profile_photo)
                        if os.path.exists(old_path):
                            os.remove(old_path)
                    filename = save_profile_photo(file)
                    if filename:
                        player.profile_photo = filename
                        db.session.commit()
                        flash('Profile photo updated!', 'success')
                    else:
                        flash('Invalid file type. Please upload an image (PNG, JPG, GIF, WEBP).', 'error')

        return redirect(url_for('player_profile'))

    # Get attendance history
    attendances = player.attendances.join(Session).order_by(Session.date.desc()).all()
    payments = player.payments.order_by(Payment.date.desc()).all()

    return render_template('player_profile.html', player=player, attendances=attendances, payments=payments)


# Player sessions view - see all sessions and vote
@app.route('/player/sessions')
@login_required
def player_sessions():
    if session.get('user_type') != 'player':
        return redirect(url_for('sessions'))

    player_id = session.get('player_id')
    player = Player.query.get_or_404(player_id)

    # Get managed players (spouse, kids, etc.)
    managed_players = player.managed_players

    # Get today's date for splitting sessions
    today = date.today()

    # Get upcoming sessions (not archived, date >= today)
    upcoming_sessions = Session.query.filter(
        Session.is_archived == False,
        Session.date >= today
    ).order_by(Session.date.asc()).all()

    # Get past sessions (not archived, date < today) - these are completed but not yet archived
    past_sessions = Session.query.filter(
        Session.is_archived == False,
        Session.date < today
    ).order_by(Session.date.desc()).all()

    # Get archived sessions grouped by year-month
    archived_sessions = Session.query.filter_by(is_archived=True).order_by(Session.date.desc()).all()

    # Group archived by year-month
    archived_grouped = {}
    for sess in archived_sessions:
        key = sess.date.strftime('%Y-%m')
        label = sess.date.strftime('%B %Y')
        if key not in archived_grouped:
            archived_grouped[key] = {'label': label, 'sessions': []}
        archived_grouped[key]['sessions'].append(sess)

    # Sort by key (year-month) descending
    archived_sorted = sorted(archived_grouped.items(), key=lambda x: x[0], reverse=True)

    # Get attendance map for this player and managed players
    attendance_map = {}  # {player_id: {session_id: status}}
    players_to_track = [player] + list(managed_players)
    for p in players_to_track:
        attendance_map[p.id] = {}
        for att in Attendance.query.filter_by(player_id=p.id).all():
            attendance_map[p.id][att.session_id] = att.status

    # Get all players for showing attendance
    all_players = Player.query.order_by(Player.name).all()

    # Get all attendance records for sessions we're displaying
    all_sessions = upcoming_sessions + past_sessions + archived_sessions
    session_attendance = {}  # {session_id: {player_id: status}}
    for sess in all_sessions:
        session_attendance[sess.id] = {}
        for att in sess.attendances.all():
            session_attendance[sess.id][att.player_id] = att.status

    # Ensure current player and managed players have attendance records for upcoming sessions
    for sess in upcoming_sessions + past_sessions:
        for p in players_to_track:
            if sess.id not in attendance_map[p.id]:
                attendance = Attendance(player_id=p.id, session_id=sess.id, status='NO')
                db.session.add(attendance)
                attendance_map[p.id][sess.id] = 'NO'
                session_attendance[sess.id][p.id] = 'NO'
    db.session.commit()

    return render_template('player_sessions.html',
                         player=player,
                         managed_players=managed_players,
                         upcoming_sessions=upcoming_sessions,
                         past_sessions=past_sessions,
                         archived_groups=archived_sorted,
                         attendance_map=attendance_map,
                         all_players=all_players,
                         session_attendance=session_attendance)


# Player payment - players can record their own and managed players' payments
@app.route('/player/payments', methods=['GET', 'POST'])
@login_required
def player_payments():
    if session.get('user_type') != 'player':
        return redirect(url_for('payments'))

    player_id = session.get('player_id')
    player = Player.query.get_or_404(player_id)
    managed_players = player.managed_players

    if request.method == 'POST':
        target_player_id = int(request.form.get('player_id', player_id))
        amount = float(request.form.get('amount'))
        method = request.form.get('method')
        date_str = request.form.get('date')
        notes = request.form.get('notes')

        # Verify target is self or managed player
        managed_player_ids = [p.id for p in managed_players]
        if target_player_id != player_id and target_player_id not in managed_player_ids:
            flash('You can only record payments for yourself or managed players', 'error')
            return redirect(url_for('player_payments'))

        payment_date = datetime.strptime(date_str, '%Y-%m-%d') if date_str else datetime.utcnow()

        payment = Payment(
            player_id=target_player_id,
            amount=amount,
            method=method,
            date=payment_date,
            notes=notes
        )
        db.session.add(payment)
        db.session.commit()

        target_player = Player.query.get(target_player_id)
        flash(f'Payment of ${amount:.2f} for {target_player.name} recorded successfully!', 'success')
        return redirect(url_for('player_payments'))

    # Get payments for player and managed players
    all_player_ids = [player_id] + [p.id for p in managed_players]
    all_payments = Payment.query.filter(Payment.player_id.in_(all_player_ids)).order_by(Payment.date.desc()).all()

    return render_template('player_payments.html',
                         player=player,
                         managed_players=managed_players,
                         payments=all_payments,
                         today=date.today().isoformat())


# Player attendance API - players can update their own and managed players' attendance
@app.route('/api/player/attendance', methods=['POST'])
@csrf.exempt  # API endpoint uses JSON
@login_required
def update_player_attendance():
    if session.get('user_type') != 'player':
        return jsonify({'error': 'Player access only'}), 403

    current_player_id = session.get('player_id')
    current_player = Player.query.get(current_player_id)
    data = request.get_json()
    session_id = data.get('session_id')
    status = data.get('status')
    target_player_id = data.get('player_id', current_player_id)  # Default to self

    # Check if voting is frozen for this session
    sess = Session.query.get(session_id)
    if sess and sess.voting_frozen:
        return jsonify({'error': 'Voting is frozen for this session'}), 403

    # Players can only use YES, NO, TENTATIVE (DROPOUT and FILLIN are admin-only)
    if status not in ['YES', 'NO', 'TENTATIVE']:
        return jsonify({'error': 'Invalid status'}), 400

    # Check if target player is self or a managed player
    managed_player_ids = [p.id for p in current_player.managed_players]
    if target_player_id != current_player_id and target_player_id not in managed_player_ids:
        return jsonify({'error': 'You can only vote for yourself or your managed players'}), 403

    attendance = Attendance.query.filter_by(player_id=target_player_id, session_id=session_id).first()

    if attendance:
        attendance.status = status
    else:
        attendance = Attendance(player_id=target_player_id, session_id=session_id, status=status)
        db.session.add(attendance)

    db.session.commit()

    # Return updated session info
    sess = Session.query.get(session_id)
    return jsonify({
        'success': True,
        'attendee_count': sess.get_attendee_count(),
        'cost_per_player': sess.get_cost_per_player()
    })


@app.route('/api/player/bulk-attendance', methods=['POST'])
@csrf.exempt  # API endpoint uses JSON
@login_required
def bulk_update_player_attendance():
    if session.get('user_type') != 'player':
        return jsonify({'error': 'Player access only'}), 403

    current_player_id = session.get('player_id')
    current_player = Player.query.get(current_player_id)
    managed_player_ids = [p.id for p in current_player.managed_players]

    data = request.get_json()
    updates = data.get('updates', [])

    if not updates:
        return jsonify({'error': 'No updates provided'}), 400

    today = date.today()
    updated_count = 0

    for update in updates:
        session_id = update.get('session_id')
        target_player_id = update.get('player_id')
        status = update.get('status')

        # Validate status
        if status not in ['YES', 'NO', 'TENTATIVE']:
            continue

        # Check if target player is self or a managed player
        if target_player_id != current_player_id and target_player_id not in managed_player_ids:
            continue

        # Check session exists, is not frozen, and is not in the past
        sess = Session.query.get(session_id)
        if not sess or sess.voting_frozen or sess.date < today:
            continue

        # Update or create attendance
        attendance = Attendance.query.filter_by(player_id=target_player_id, session_id=session_id).first()
        if attendance:
            attendance.status = status
        else:
            attendance = Attendance(player_id=target_player_id, session_id=session_id, status=status)
            db.session.add(attendance)

        updated_count += 1

    db.session.commit()
    return jsonify({'success': True, 'updated_count': updated_count})


# Player routes
@app.route('/players')
@admin_required
def players():
    category = request.args.get('category', 'all')
    search_query = request.args.get('search', '').strip()

    # Start with base query
    query = Player.query

    # Apply category filter
    if category != 'all':
        query = query.filter_by(category=category)

    # Apply search filter
    if search_query:
        search_term = f'%{search_query}%'
        query = query.filter(
            db.or_(
                Player.name.ilike(search_term),
                Player.phone.ilike(search_term),
                Player.email.ilike(search_term)
            )
        )

    player_list = query.order_by(Player.name).all()

    # Pre-group for grouped view (all / no search)
    regular_players = [p for p in player_list if p.is_active and p.category in ('regular', 'kid')]
    adhoc_players   = [p for p in player_list if p.is_active and p.category == 'adhoc']
    inactive_players = [p for p in player_list if not p.is_active]

    return render_template('players.html',
                           players=player_list,
                           regular_players=regular_players,
                           adhoc_players=adhoc_players,
                           inactive_players=inactive_players,
                           current_category=category,
                           search_query=search_query)


@app.route('/players/add', methods=['GET', 'POST'])
@admin_required
def add_player():
    if request.method == 'POST':
        name = request.form.get('name')
        category = request.form.get('category', 'regular')
        phone = request.form.get('phone')
        email = request.form.get('email')
        password = request.form.get('password')
        zelle_preference = request.form.get('zelle_preference', 'email')
        gender = request.form.get('gender', 'male')
        dob_str = request.form.get('date_of_birth')

        if not name:
            flash('Name is required', 'error')
            return render_template('player_form.html', player=None)

        player = Player(name=name, category=category, phone=phone, email=email, zelle_preference=zelle_preference, gender=gender, is_approved=True)

        # Handle date of birth
        if dob_str:
            player.date_of_birth = datetime.strptime(dob_str, '%Y-%m-%d').date()

        if password:
            player.set_password(password)

        # Handle managed_by
        managed_by = request.form.get('managed_by')
        if managed_by:
            player.managed_by = int(managed_by)

        # Handle profile photo upload
        if 'profile_photo' in request.files:
            file = request.files['profile_photo']
            if file and file.filename:
                filename = save_profile_photo(file)
                if filename:
                    player.profile_photo = filename

        db.session.add(player)
        db.session.commit()
        flash(f'Player {name} added successfully!', 'success')
        return redirect(url_for('players'))

    all_players = Player.query.order_by(Player.name).all()
    return render_template('player_form.html', player=None, all_players=all_players)


@app.route('/players/<int:id>')
@admin_required
def player_detail(id):
    player = Player.query.get_or_404(id)
    attendances = player.attendances.join(Session).order_by(Session.date.desc()).all()
    payments = player.payments.order_by(Payment.date.desc()).all()
    return render_template('player_detail.html', player=player, attendances=attendances, payments=payments)


@app.route('/players/<int:id>/edit', methods=['GET', 'POST'])
@admin_required
def edit_player(id):
    player = Player.query.get_or_404(id)

    if request.method == 'POST':
        player.name = request.form.get('name')
        player.category = request.form.get('category', 'regular')
        player.phone = request.form.get('phone')
        player.email = request.form.get('email')
        player.zelle_preference = request.form.get('zelle_preference', 'email')
        player.gender = request.form.get('gender', 'male')
        dob_str = request.form.get('date_of_birth')
        player.date_of_birth = datetime.strptime(dob_str, '%Y-%m-%d').date() if dob_str else None

        password = request.form.get('password')
        if password:
            player.set_password(password)

        # Handle managed_by
        managed_by = request.form.get('managed_by')
        player.managed_by = int(managed_by) if managed_by else None

        # Handle profile photo upload
        if 'profile_photo' in request.files:
            file = request.files['profile_photo']
            if file and file.filename:
                # Delete old photo if exists
                if player.profile_photo:
                    old_path = os.path.join(app.config['UPLOAD_FOLDER'], player.profile_photo)
                    if os.path.exists(old_path):
                        os.remove(old_path)
                filename = save_profile_photo(file)
                if filename:
                    player.profile_photo = filename

        db.session.commit()
        flash(f'Player {player.name} updated successfully!', 'success')
        return redirect(url_for('player_detail', id=id))

    all_players = Player.query.order_by(Player.name).all()
    return render_template('player_form.html', player=player, all_players=all_players)


@app.route('/players/<int:id>/delete', methods=['POST'])
@admin_required
def delete_player(id):
    player = Player.query.get_or_404(id)
    name = player.name
    db.session.delete(player)
    db.session.commit()
    flash(f'Player {name} deleted successfully!', 'success')
    return redirect(url_for('players'))


@app.route('/players/<int:id>/toggle-admin', methods=['POST'])
@admin_required
def toggle_admin(id):
    player = Player.query.get_or_404(id)
    player.is_admin = not player.is_admin
    db.session.commit()
    status = 'promoted to admin' if player.is_admin else 'removed from admin'
    flash(f'{player.name} has been {status}!', 'success')
    return redirect(url_for('player_detail', id=id))


@app.route('/api/players/<int:id>/category', methods=['POST'])
@csrf.exempt  # API endpoint uses JSON
@admin_required
def update_player_category(id):
    player = Player.query.get_or_404(id)
    data = request.get_json()
    category = data.get('category')

    if category not in ['regular', 'adhoc', 'kid']:
        return jsonify({'error': 'Invalid category'}), 400

    player.category = category
    db.session.commit()

    return jsonify({
        'success': True,
        'player_id': player.id,
        'category': player.category
    })


@app.route('/players/<int:id>/toggle-active', methods=['POST'])
@admin_required
def toggle_active(id):
    player = Player.query.get_or_404(id)
    player.is_active = not player.is_active
    db.session.commit()
    status = 'activated' if player.is_active else 'deactivated'
    flash(f'{player.name} has been {status}!', 'success')
    return redirect(url_for('player_detail', id=id))


@app.route('/players/<int:id>/approve', methods=['POST'])
@admin_required
def approve_player(id):
    player = Player.query.get_or_404(id)
    player.is_approved = True
    db.session.commit()
    admin_info = f"Admin" if session.get('user_type') == 'admin' else f"Player Admin (ID: {session.get('player_id')})"
    security_logger.info(f'PLAYER_APPROVED - Player: {player.name} (ID: {player.id}), By: {admin_info}, IP: {request.remote_addr}')
    flash(f'{player.name} has been approved!', 'success')
    return redirect(url_for('dashboard'))


@app.route('/players/<int:id>/reject', methods=['POST'])
@admin_required
def reject_player(id):
    player = Player.query.get_or_404(id)
    name = player.name
    email = player.email
    admin_info = f"Admin" if session.get('user_type') == 'admin' else f"Player Admin (ID: {session.get('player_id')})"
    security_logger.info(f'PLAYER_REJECTED - Player: {name}, Email: {email}, By: {admin_info}, IP: {request.remote_addr}')
    db.session.delete(player)
    db.session.commit()
    flash(f'Registration for {name} has been rejected and removed.', 'success')
    return redirect(url_for('dashboard'))


# Session routes
@app.route('/sessions')
@admin_required
def sessions():
    # Get active sessions
    active_sessions = Session.query.filter_by(is_archived=False).order_by(Session.date.asc()).all()

    # Batch load all attendance records for active sessions to avoid N+1
    active_session_ids = [s.id for s in active_sessions]
    all_attendances = Attendance.query.filter(Attendance.session_id.in_(active_session_ids)).all() if active_session_ids else []

    # Build attendance map: {session_id: {player_id: status}}
    # Build attendance details: {session_id: {player_id: {status, payment_status, additional_cost, comments}}}
    attendance_map = {}
    attendance_details = {}
    for sess in active_sessions:
        attendance_map[sess.id] = {}
        attendance_details[sess.id] = {}
    for att in all_attendances:
        if att.session_id in attendance_map:
            attendance_map[att.session_id][att.player_id] = att.status
            attendance_details[att.session_id][att.player_id] = {
                'status': att.status,
                'payment_status': att.payment_status or 'unpaid',
                'additional_cost': att.additional_cost or 0,
                'comments': att.comments or ''
            }

    # Get cached monthly summary (expensive calculation)
    monthly_sorted = get_cached_monthly_summary()

    # Archived sessions grouped by year and month
    all_sessions = Session.query.filter_by(is_archived=True).order_by(Session.date.desc()).all()
    archived_sessions = all_sessions

    # Group archived by year-month
    archived_grouped = {}
    for sess in archived_sessions:
        key = sess.date.strftime('%Y-%m')
        label = sess.date.strftime('%B %Y')
        if key not in archived_grouped:
            archived_grouped[key] = {'label': label, 'sessions': []}
        archived_grouped[key]['sessions'].append(sess)

    # Sort by key (year-month) descending
    archived_sorted = sorted(archived_grouped.items(), key=lambda x: x[0], reverse=True)

    # Get all active players
    all_players = Player.query.filter_by(is_active=True, is_approved=True).order_by(Player.name).all()

    regular_players = [p for p in all_players if p.category == 'regular']
    adhoc_players = [p for p in all_players if p.category == 'adhoc']
    kid_players = [p for p in all_players if p.category == 'kid']

    # Pre-compute player stats using batch queries (avoids N×M query explosion)
    # 1. Refund totals
    refund_stats = db.session.query(
        DropoutRefund.player_id,
        func.count(DropoutRefund.id).filter(DropoutRefund.status == 'pending').label('pending_count'),
        func.sum(DropoutRefund.refund_amount).filter(DropoutRefund.status == 'pending').label('pending_amount'),
        func.sum(DropoutRefund.refund_amount).filter(DropoutRefund.status == 'processed').label('total_refunded')
    ).group_by(DropoutRefund.player_id).all()
    refund_map = {r.player_id: {'pending': r.pending_count or 0, 'pending_amount': float(r.pending_amount or 0), 'refunded': r.total_refunded or 0} for r in refund_stats}

    # 2. All sessions + courts in two queries (needed for all-time balance)
    all_sessions_all = Session.query.all()
    all_courts_all = Court.query.all()

    # 3. All chargeable attendances (YES/DROPOUT/FILLIN) across all sessions
    all_chargeable_att = Attendance.query.filter(
        Attendance.status.in_(['YES', 'DROPOUT', 'FILLIN'])
    ).all()

    # 4. Payment totals per player — exclude refund payments (negative) so balance
    #    reflects actual cash received; refunds are tracked separately in refund_map
    payment_totals = db.session.query(
        Payment.player_id,
        func.sum(Payment.amount).label('total')
    ).filter(Payment.amount > 0).group_by(Payment.player_id).all()
    player_payments = {r.player_id: float(r.total or 0) for r in payment_totals}

    # Build court cost map: session_id -> {regular: X, adhoc: X}
    court_cost_by_session = {}
    for court in all_courts_all:
        sid = court.session_id
        if sid not in court_cost_by_session:
            court_cost_by_session[sid] = {'regular': 0.0, 'adhoc': 0.0}
        if court.court_type == 'adhoc':
            court_cost_by_session[sid]['adhoc'] += court.cost
        else:
            court_cost_by_session[sid]['regular'] += court.cost

    # Count YES+DROPOUT per session per category (FILLIN not counted in divisor)
    session_counts = {}
    for att in all_chargeable_att:
        if att.status in ('YES', 'DROPOUT'):
            sid = att.session_id
            if sid not in session_counts:
                session_counts[sid] = {'regular': 0, 'adhoc': 0}
            if att.category == 'adhoc':
                session_counts[sid]['adhoc'] += 1
            elif att.category == 'regular':
                session_counts[sid]['regular'] += 1

    # Build per-session cost-per-player map
    session_birdie = {s.id: s.birdie_cost for s in all_sessions_all}
    session_cost_map = {}
    for s in all_sessions_all:
        sid = s.id
        courts = court_cost_by_session.get(sid, {'regular': 0.0, 'adhoc': 0.0})
        counts = session_counts.get(sid, {'regular': 0, 'adhoc': 0})
        birdie = session_birdie.get(sid, 0)
        reg = round(courts['regular'] / counts['regular'] + birdie, 2) if counts['regular'] > 0 else 0
        adhoc = round(courts['adhoc'] / counts['adhoc'] + birdie, 2) if counts['adhoc'] > 0 else 0
        session_cost_map[sid] = {'regular': reg, 'adhoc': adhoc, 'kid': 11.0}

    # Compute total charges per player in Python (no extra queries)
    player_charges = {}
    for att in all_chargeable_att:
        pid = att.player_id
        costs = session_cost_map.get(att.session_id, {'regular': 0, 'adhoc': 0, 'kid': 11.0})
        cat = att.category if att.category in ('adhoc', 'kid') else 'regular'
        player_charges[pid] = player_charges.get(pid, 0.0) + costs[cat]

    # Build player_stats (no per-player DB calls)
    player_stats = {}
    for player in all_players:
        charges = round(player_charges.get(player.id, 0), 2)
        payments = round(player_payments.get(player.id, 0), 2)
        refund_data = refund_map.get(player.id, {'pending': 0, 'pending_amount': 0.0, 'refunded': 0})
        player_stats[player.id] = {
            'balance': round(charges - payments, 2),
            'total_payments': payments,
            'pending_refunds': refund_data['pending'],
            'pending_refund_amount': refund_data['pending_amount'],
            'total_refunded': refund_data['refunded']
        }

    # Sort each player group: participating first (any active session YES/FILLIN/etc.), then NP — both sub-groups sorted by name
    def _is_participating(player_id):
        for sess in active_sessions:
            s = attendance_map.get(sess.id, {}).get(player_id, '')
            if s and s != 'NO':
                return True
        return False

    regular_players.sort(key=lambda p: (not _is_participating(p.id), p.name))
    adhoc_players.sort(key=lambda p: (not _is_participating(p.id), p.name))
    kid_players.sort(key=lambda p: (not _is_participating(p.id), p.name))

    # Pre-compute per-player cost for active sessions using unified pool model (no extra DB calls)
    active_session_costs = {}
    for s in active_sessions:
        sid = s.id
        courts = court_cost_by_session.get(sid, {'regular': 0.0, 'adhoc': 0.0})
        total_court_cost = courts['regular'] + courts['adhoc']
        counts = session_counts.get(sid, {'regular': 0, 'adhoc': 0})
        non_kid_count = counts['regular'] + counts['adhoc']
        credits = s.credits or 0
        if non_kid_count > 0:
            per_player = round((total_court_cost + credits) / non_kid_count + s.birdie_cost, 2)
        else:
            per_player = s.birdie_cost or 0
        active_session_costs[sid] = {'regular': per_player, 'adhoc': per_player, 'kid': 11.0}

    # Build standby-players-per-session map for the dropout modal
    player_name_map = {p.id: p.name for p in all_players}
    standby_by_session = {}
    for att in sorted(all_attendances, key=lambda a: a.updated_at or a.created_at):
        if att.status == 'STANDBY' and att.session_id in attendance_map:
            standby_by_session.setdefault(att.session_id, []).append({
                'id': att.player_id,
                'name': player_name_map.get(att.player_id, ''),
                'category': att.category or 'regular'
            })

    session_birdie_map = {s.id: (s.birdie_cost or 0) for s in active_sessions}

    # Patch attendance_details for existing dropouts that have a pending DropoutRefund
    # (handles records created before payment_status='pending_refund' was added)
    active_session_ids = [s.id for s in active_sessions]
    if active_session_ids:
        pending_refunds_q = db.session.query(
            DropoutRefund.session_id, DropoutRefund.player_id
        ).filter(
            DropoutRefund.status == 'pending',
            DropoutRefund.session_id.in_(active_session_ids)
        ).all()
        for sid, pid in pending_refunds_q:
            if sid in attendance_details and pid in attendance_details[sid]:
                attendance_details[sid][pid]['payment_status'] = 'pending_refund'

    return render_template('sessions.html',
                          active_sessions=active_sessions,
                          archived_groups=archived_sorted,
                          monthly_summary=monthly_sorted,
                          regular_players=regular_players,
                          adhoc_players=adhoc_players,
                          kid_players=kid_players,
                          attendance_map=attendance_map,
                          attendance_details=attendance_details,
                          player_stats=player_stats,
                          active_session_costs=active_session_costs,
                          standby_by_session=standby_by_session,
                          session_birdie_map=session_birdie_map)


@app.route('/sessions/month/<month_key>')
@admin_required
def sessions_by_month(month_key):
    """Show all sessions for a given month (YYYY-MM) with per-session summary."""
    try:
        from datetime import datetime as dt
        month_dt = dt.strptime(month_key, '%Y-%m')
    except ValueError:
        return redirect(url_for('sessions'))

    month_label = month_dt.strftime('%B %Y')
    year, month = month_dt.year, month_dt.month

    month_sessions = Session.query.filter(
        db.extract('year', Session.date) == year,
        db.extract('month', Session.date) == month
    ).order_by(Session.date.asc()).all()

    session_stats = []
    for sess in month_sessions:
        start_time, end_time = sess.get_time_range()
        courts = sess.courts.all()
        session_stats.append({
            'session': sess,
            'start_time': start_time,
            'end_time': end_time,
            'attendees': sess.get_attendee_count(),
            'total_cost': sess.get_total_cost(),
            'collection': sess.get_total_collection(),
            'refunds': sess.get_total_refunds(),
            'birdie': sess.get_birdie_cost_total(),
            'credits': sess.credits or 0,
            'courts': [{'name': c.name, 'start_time': c.start_time,
                        'end_time': c.end_time, 'cost': c.cost,
                        'court_type': c.court_type} for c in courts],
        })

    totals = {
        'sessions': len(month_sessions),
        'collection': sum(s['collection'] for s in session_stats),
        'refunds': sum(s['refunds'] for s in session_stats),
        'birdie': sum(s['birdie'] for s in session_stats),
        'credits': sum(s['credits'] for s in session_stats),
    }

    return render_template('month_sessions.html',
                           month_label=month_label,
                           month_key=month_key,
                           session_stats=session_stats,
                           totals=totals)


@app.route('/sessions/add', methods=['GET', 'POST'])
@admin_required
def add_session():
    if request.method == 'POST':
        birdie_cost = float(request.form.get('birdie_cost', 2))
        notes = request.form.get('notes', '')

        # Get all dates to create sessions for
        date_count = int(request.form.get('date_count', 1))
        created_sessions = []

        players = Player.query.all()

        for i in range(date_count):
            date_str = request.form.get(f'date_{i}')
            if not date_str:
                continue

            session_date = datetime.strptime(date_str, '%Y-%m-%d').date()

            new_session = Session(
                date=session_date,
                birdie_cost=birdie_cost,
                notes=notes
            )
            db.session.add(new_session)
            db.session.flush()

            # No courts added during creation - they will be added when editing individual sessions

            # Create attendance records for all players (default NO, category from player)
            for player in players:
                attendance = Attendance(player_id=player.id, session_id=new_session.id, status='NO', category=player.category)
                db.session.add(attendance)

            created_sessions.append(new_session)

        db.session.commit()
        clear_session_cache()

        if len(created_sessions) == 1:
            flash('Session created! Edit the session to add courts.', 'success')
            return redirect(url_for('session_detail', id=created_sessions[0].id))
        else:
            flash(f'{len(created_sessions)} sessions created! Edit each session to add courts.', 'success')
            return redirect(url_for('sessions'))

    return render_template('session_form.html', session=None)


@app.route('/sessions/<int:id>')
@admin_required
def session_detail(id):
    sess = Session.query.get_or_404(id)
    players = Player.query.order_by(Player.name).all()

    # Get attendance for all players
    attendance_map = {}
    category_map = {}
    attendance_records = {}  # Full attendance records for additional fields
    for att in sess.attendances.all():
        attendance_map[att.player_id] = att.status
        category_map[att.player_id] = att.category
        attendance_records[att.player_id] = att

    # Ensure all players have attendance records
    for player in players:
        if player.id not in attendance_map:
            attendance = Attendance(player_id=player.id, session_id=id, status='NO', category=player.category)
            db.session.add(attendance)
            attendance_map[player.id] = 'NO'
            category_map[player.id] = player.category
            db.session.flush()
            attendance_records[player.id] = attendance
    db.session.commit()

    # Calculate per-player session costs for bulk payment
    player_session_costs = {}
    for player in players:
        if player.is_active:
            att = attendance_records.get(player.id)
            if att and att.status in ['YES', 'DROPOUT', 'FILLIN']:
                cat = att.category
                if cat == 'kid':
                    base = sess.get_cost_per_kid()
                elif cat == 'adhoc':
                    base = sess.get_cost_per_adhoc_player()
                else:
                    base = sess.get_cost_per_regular_player()
                player_session_costs[player.id] = round(base + (att.additional_cost or 0), 2)
            else:
                player_session_costs[player.id] = 0

    # Sort active players for display: YES/FILLIN/DROPOUT first, then STANDBY (waitlisted) — both sub-groups by name
    def _display_priority(p):
        s = attendance_map.get(p.id, 'NO')
        if s in ['YES', 'FILLIN', 'DROPOUT']: return 0
        if s == 'STANDBY': return 1
        return 2

    players_display = sorted(
        [p for p in players if p.is_active and attendance_map.get(p.id, 'NO') in ['YES', 'FILLIN', 'STANDBY', 'DROPOUT']],
        key=lambda p: (_display_priority(p), p.name)
    )

    # Standby players sorted by when they joined the waitlist (first = highest priority)
    standby_atts = sorted(
        [att for att in attendance_records.values() if att.status == 'STANDBY'],
        key=lambda a: a.updated_at or a.created_at
    )
    standby_players = [
        {'id': att.player_id, 'name': att.player.name, 'category': att.category}
        for att in standby_atts if att.player
    ]

    # Refund data per player for this session (direct query avoids backref expiry after commit)
    session_refunds = DropoutRefund.query.filter_by(session_id=id).all()
    pending_refund_pids = {r.player_id for r in session_refunds if r.status == 'pending'}
    refund_by_player = {r.player_id: r for r in session_refunds}

    return render_template('session_detail.html', session=sess, players=players,
                          players_display=players_display,
                          attendance_map=attendance_map, category_map=category_map,
                          attendance_records=attendance_records,
                          player_session_costs=player_session_costs,
                          standby_players=standby_players,
                          pending_refund_pids=pending_refund_pids,
                          refund_by_player=refund_by_player)


@app.route('/sessions/<int:id>/edit', methods=['GET', 'POST'])
@admin_required
def edit_session(id):
    sess = Session.query.get_or_404(id)

    if request.method == 'POST':
        sess.date = datetime.strptime(request.form.get('date'), '%Y-%m-%d').date()
        sess.birdie_cost = float(request.form.get('birdie_cost', 0))
        sess.credits = float(request.form.get('credits', 0))
        sess.notes = request.form.get('notes')

        def format_time(time_str):
            h, m = map(int, time_str.split(':'))
            period = 'AM' if h < 12 else 'PM'
            display_h = h if h <= 12 else h - 12
            if display_h == 0:
                display_h = 12
            return f"{display_h}:{m:02d} {period}"

        def compute_end_time(start_str, hours_float):
            h, m = map(int, start_str.split(':'))
            total = h * 60 + m + int(hours_float * 60)
            eh = (total // 60) % 24
            em = total % 60
            return f"{eh:02d}:{em:02d}"

        court_count = int(request.form.get('court_count', 0))

        # Delete existing courts and recreate
        Court.query.filter_by(session_id=id).delete()

        # Add courts with per-court duration
        for i in range(court_count):
            court_name = request.form.get(f'court_name_{i}', f'Court {i+1}')
            court_type = request.form.get(f'court_type_{i}', 'regular')
            court_cost = float(request.form.get(f'court_cost_{i}', 105))
            court_hours = float(request.form.get(f'court_hours_{i}', 3))
            court_start = request.form.get(f'court_start_time_{i}', '06:30')
            court_end = compute_end_time(court_start, court_hours)

            # Update session-level fields from first court (used as fallback when no courts exist)
            if i == 0:
                sess.hours = court_hours
                sess.start_time = court_start
                sess.end_time = court_end
                sess.court_cost = 75 if court_hours == 2 else (90 if court_hours == 3.5 else 105)

            court = Court(
                session_id=id,
                name=court_name,
                court_type=court_type,
                start_time=format_time(court_start),
                end_time=format_time(court_end),
                cost=court_cost
            )
            db.session.add(court)

        db.session.commit()
        clear_session_cache()
        flash('Session updated successfully!', 'success')
        return redirect(url_for('session_detail', id=id))

    return render_template('session_form.html', session=sess)


@app.route('/sessions/<int:id>/delete', methods=['POST'])
@admin_required
def delete_session(id):
    sess = Session.query.get_or_404(id)

    # Only archived sessions can be deleted
    if not sess.is_archived:
        flash('Only archived sessions can be deleted. Please archive the session first.', 'error')
        return redirect(url_for('session_detail', id=id))

    db.session.delete(sess)
    db.session.commit()
    flash('Session deleted successfully!', 'success')
    return redirect(url_for('sessions'))


@app.route('/sessions/<int:id>/toggle-archive', methods=['POST'])
@admin_required
def toggle_archive(id):
    sess = Session.query.get_or_404(id)
    sess.is_archived = not sess.is_archived
    db.session.commit()
    clear_session_cache()  # Invalidate cached monthly summary
    status = 'archived' if sess.is_archived else 'unarchived'
    flash(f'Session {status} successfully!', 'success')
    return redirect(url_for('session_detail', id=id))


@app.route('/sessions/<int:id>/toggle-voting-freeze', methods=['POST'])
@admin_required
def toggle_voting_freeze(id):
    sess = Session.query.get_or_404(id)
    sess.voting_frozen = not sess.voting_frozen
    db.session.commit()
    status = 'frozen' if sess.voting_frozen else 'unfrozen'
    flash(f'Voting {status} for this session!', 'success')
    return redirect(url_for('session_detail', id=id))


@app.route('/sessions/bulk-archive', methods=['POST'])
@admin_required
def bulk_archive_sessions():
    session_ids = request.form.getlist('session_ids')
    if not session_ids:
        flash('No sessions selected', 'error')
        return redirect(url_for('sessions'))

    count = 0
    for session_id in session_ids:
        sess = Session.query.get(int(session_id))
        if sess and not sess.is_archived:
            sess.is_archived = True
            count += 1

    db.session.commit()
    clear_session_cache()  # Invalidate cached monthly summary
    flash(f'{count} session(s) archived successfully!', 'success')
    return redirect(url_for('sessions'))


@app.route('/sessions/bulk-unarchive', methods=['POST'])
@admin_required
def bulk_unarchive_sessions():
    session_ids = request.form.getlist('session_ids')
    if not session_ids:
        flash('No sessions selected', 'error')
        return redirect(url_for('sessions'))

    count = 0
    for session_id in session_ids:
        sess = Session.query.get(int(session_id))
        if sess and sess.is_archived:
            sess.is_archived = False
            count += 1

    db.session.commit()
    clear_session_cache()  # Invalidate cached monthly summary
    flash(f'{count} session(s) unarchived successfully!', 'success')
    return redirect(url_for('sessions'))


@app.route('/sessions/bulk-delete', methods=['POST'])
@admin_required
def bulk_delete_sessions():
    session_ids = request.form.getlist('session_ids')
    if not session_ids:
        flash('No sessions selected', 'error')
        return redirect(url_for('sessions'))

    count = 0
    for session_id in session_ids:
        sess = Session.query.get(int(session_id))
        # Only delete archived sessions
        if sess and sess.is_archived:
            # Delete related dropout refunds first
            DropoutRefund.query.filter_by(session_id=sess.id).delete()
            # Delete related birdie bank transactions
            BirdieBank.query.filter_by(session_id=sess.id).delete()
            # Now delete the session (attendances and courts cascade automatically)
            db.session.delete(sess)
            count += 1

    db.session.commit()
    clear_session_cache()  # Invalidate cached monthly summary
    flash(f'{count} session(s) permanently deleted!', 'success')
    return redirect(url_for('sessions'))


@app.route('/api/bulk-assign-courts', methods=['POST'])
@csrf.exempt
@admin_required
def bulk_assign_courts():
    data = request.get_json()
    session_ids = data.get('session_ids', [])
    courts_data = data.get('courts', [])
    overwrite = data.get('overwrite', False)

    if not session_ids:
        return jsonify({'success': False, 'error': 'No sessions selected'})
    if not courts_data:
        return jsonify({'success': False, 'error': 'No courts defined'})

    def format_time(time_str):
        h, m = map(int, time_str.split(':'))
        period = 'AM' if h < 12 else 'PM'
        display_h = h if h <= 12 else h - 12
        if display_h == 0:
            display_h = 12
        return f"{display_h}:{m:02d} {period}"

    def compute_end_time(start_str, hours_float):
        h, m = map(int, start_str.split(':'))
        total = h * 60 + m + int(hours_float * 60)
        eh = (total // 60) % 24
        em = total % 60
        return f"{eh:02d}:{em:02d}"

    sessions = Session.query.filter(Session.id.in_(session_ids)).all()
    updated = 0
    skipped = 0

    for sess in sessions:
        if not overwrite and sess.courts.count() > 0:
            skipped += 1
            continue

        Court.query.filter_by(session_id=sess.id).delete()

        for i, court_data in enumerate(courts_data):
            court_hours = float(court_data.get('hours', 3))
            court_start = court_data.get('start_time', '06:30')
            court_end = compute_end_time(court_start, court_hours)

            if i == 0:
                sess.hours = court_hours
                sess.start_time = court_start
                sess.end_time = court_end
                sess.court_cost = 75 if court_hours == 2 else (90 if court_hours == 3.5 else 105)

            court = Court(
                session_id=sess.id,
                name=court_data.get('name', f'Court {i + 1}'),
                court_type=court_data.get('court_type', 'regular'),
                cost=float(court_data.get('cost', 105)),
                start_time=format_time(court_start),
                end_time=format_time(court_end)
            )
            db.session.add(court)

        updated += 1

    db.session.commit()
    clear_session_cache()
    return jsonify({'success': True, 'updated': updated, 'skipped': skipped})


@app.route('/sessions/bulk-freeze-voting', methods=['POST'])
@admin_required
def bulk_freeze_voting():
    session_ids = request.form.getlist('session_ids')
    if not session_ids:
        flash('No sessions selected', 'error')
        return redirect(url_for('sessions'))

    count = 0
    for session_id in session_ids:
        sess = Session.query.get(int(session_id))
        if sess and not sess.voting_frozen:
            sess.voting_frozen = True
            count += 1

    db.session.commit()
    flash(f'Voting frozen for {count} session(s)!', 'success')
    return redirect(url_for('sessions'))


@app.route('/sessions/bulk-unfreeze-voting', methods=['POST'])
@admin_required
def bulk_unfreeze_voting():
    session_ids = request.form.getlist('session_ids')
    if not session_ids:
        flash('No sessions selected', 'error')
        return redirect(url_for('sessions'))

    count = 0
    for session_id in session_ids:
        sess = Session.query.get(int(session_id))
        if sess and sess.voting_frozen:
            sess.voting_frozen = False
            count += 1

    db.session.commit()
    flash(f'Voting unfrozen for {count} session(s)!', 'success')
    return redirect(url_for('sessions'))


@app.route('/api/bulk-attendance', methods=['POST'])
@admin_required
def bulk_attendance():
    """Bulk update attendance for selected sessions"""
    data = request.get_json()
    session_ids = data.get('session_ids', [])
    category = data.get('category', 'all')  # 'regular', 'adhoc', 'kid', or 'all'
    status = data.get('status', 'YES')  # 'YES', 'NO', 'TENTATIVE', or 'CLEAR'

    if not session_ids:
        return jsonify({'success': False, 'error': 'No sessions selected'})

    # Get players based on category
    if category == 'regular':
        players = Player.query.filter_by(is_active=True, category='regular').all()
    elif category == 'adhoc':
        players = Player.query.filter_by(is_active=True, category='adhoc').all()
    elif category == 'kid':
        players = Player.query.filter_by(is_active=True, category='kid').all()
    else:
        players = Player.query.filter_by(is_active=True).all()

    count = 0
    for session_id in session_ids:
        sess = Session.query.get(int(session_id))
        if not sess:
            continue

        for player in players:
            # Find existing attendance or create new
            attendance = Attendance.query.filter_by(session_id=session_id, player_id=player.id).first()

            if status == 'CLEAR':
                if attendance:
                    db.session.delete(attendance)
                    count += 1
            else:
                if attendance:
                    attendance.status = status
                    attendance.category = player.category
                else:
                    attendance = Attendance(
                        session_id=session_id,
                        player_id=player.id,
                        status=status,
                        category=player.category
                    )
                    db.session.add(attendance)
                count += 1

    db.session.commit()
    return jsonify({'success': True, 'count': count})


@app.route('/api/bulk-player-attendance', methods=['POST'])
@admin_required
def bulk_player_attendance():
    """Bulk update attendance for a single player across multiple sessions"""
    data = request.get_json()
    player_id = data.get('player_id')
    session_ids = data.get('session_ids', [])
    status = data.get('status', 'YES')

    if not player_id:
        return jsonify({'success': False, 'error': 'No player specified'})

    if not session_ids:
        return jsonify({'success': False, 'error': 'No sessions specified'})

    player = Player.query.get(player_id)
    if not player:
        return jsonify({'success': False, 'error': 'Player not found'})

    count = 0
    for session_id in session_ids:
        sess = Session.query.get(int(session_id))
        if not sess:
            continue

        attendance = Attendance.query.filter_by(session_id=session_id, player_id=player_id).first()

        if status == 'CLEAR':
            if attendance:
                db.session.delete(attendance)
                count += 1
        else:
            if attendance:
                attendance.status = status
                attendance.category = player.category
            else:
                attendance = Attendance(
                    session_id=session_id,
                    player_id=player_id,
                    status=status,
                    category=player.category
                )
                db.session.add(attendance)
            count += 1

    db.session.commit()
    return jsonify({'success': True, 'count': count})


# Dropout Refund routes
@app.route('/sessions/<int:id>/refunds')
@admin_required
def session_refunds(id):
    sess = Session.query.get_or_404(id)

    # Get all dropouts for this session
    dropouts = Attendance.query.filter_by(session_id=id, status='DROPOUT').all()
    fillins = Attendance.query.filter_by(session_id=id, status='FILLIN').all()

    # Get existing refunds
    refunds = DropoutRefund.query.filter_by(session_id=id).all()
    refund_map = {r.player_id: r for r in refunds}

    # Calculate suggested refund
    suggested_refund = sess.calculate_suggested_refund()

    return render_template('session_refunds.html',
                         session=sess,
                         dropouts=dropouts,
                         fillins=fillins,
                         refunds=refunds,
                         refund_map=refund_map,
                         suggested_refund=suggested_refund)


@app.route('/sessions/<int:id>/refunds/add', methods=['POST'])
@admin_required
def add_dropout_refund(id):
    sess = Session.query.get_or_404(id)
    player_id = int(request.form.get('player_id'))
    refund_amount = float(request.form.get('refund_amount', 0))
    instructions = request.form.get('instructions', '').strip()

    # Check if refund already exists
    existing = DropoutRefund.query.filter_by(session_id=id, player_id=player_id).first()
    if existing:
        flash('Refund already exists for this player. Edit the existing one.', 'error')
        return redirect(url_for('session_refunds', id=id))

    suggested_amount = sess.calculate_suggested_refund()

    refund = DropoutRefund(
        player_id=player_id,
        session_id=id,
        refund_amount=refund_amount,
        suggested_amount=suggested_amount,
        instructions=instructions,
        status='pending'
    )
    db.session.add(refund)
    db.session.commit()

    player = Player.query.get(player_id)
    flash(f'Refund of ${refund_amount:.2f} created for {player.name}', 'success')
    return redirect(url_for('session_refunds', id=id))


@app.route('/refunds/<int:id>/update', methods=['POST'])
@admin_required
def update_dropout_refund(id):
    refund = DropoutRefund.query.get_or_404(id)
    session_id = refund.session_id

    action = request.form.get('action')

    if action == 'update':
        old_amount = refund.refund_amount
        new_amount = float(request.form.get('refund_amount', refund.refund_amount))
        refund.refund_amount = new_amount
        refund.instructions = request.form.get('instructions', '').strip()

        # If already processed, update the corresponding payment record
        if refund.status == 'processed':
            # Find and update the payment record
            payment = Payment.query.filter_by(
                player_id=refund.player_id,
                method='Refund'
            ).filter(
                Payment.notes.like(f'%Dropout refund for session {refund.session.date.strftime("%b %d, %Y")}%')
            ).first()

            if payment:
                payment.amount = -new_amount
                payment.notes = f'Dropout refund for session {refund.session.date.strftime("%b %d, %Y")}. {refund.instructions or ""}'.strip()
                flash(f'Refund updated from ${old_amount:.2f} to ${new_amount:.2f} and payment record adjusted', 'success')
            else:
                flash('Refund updated but could not find corresponding payment record', 'error')
        else:
            flash('Refund updated successfully!', 'success')

    elif action == 'process':
        refund.status = 'processed'
        refund.processed_date = datetime.utcnow()

        # Create a negative payment (credit) for the player
        payment = Payment(
            player_id=refund.player_id,
            amount=-refund.refund_amount,  # Negative amount = credit/refund
            method='Refund',
            date=datetime.utcnow(),
            notes=f'Dropout refund for session {refund.session.date.strftime("%b %d, %Y")}. {refund.instructions or ""}'.strip()
        )
        db.session.add(payment)

        # Revert dropout attendance payment_status to 'paid'
        dropout_att = Attendance.query.filter_by(
            player_id=refund.player_id, session_id=refund.session_id
        ).first()
        if dropout_att:
            dropout_att.payment_status = 'paid'

        flash(f'Refund of ${refund.refund_amount:.2f} processed and credited to {refund.player.name}', 'success')

    elif action == 'cancel':
        # If already processed, remove the payment record
        if refund.status == 'processed':
            payment = Payment.query.filter_by(
                player_id=refund.player_id,
                method='Refund'
            ).filter(
                Payment.notes.like(f'%Dropout refund for session {refund.session.date.strftime("%b %d, %Y")}%')
            ).first()

            if payment:
                db.session.delete(payment)
                flash('Refund cancelled and payment record removed', 'success')
            else:
                flash('Refund cancelled but could not find corresponding payment record', 'error')
        else:
            flash('Refund cancelled', 'success')

        refund.status = 'cancelled'

    db.session.commit()
    if request.form.get('from_session'):
        return redirect(url_for('session_detail', id=session_id))
    return redirect(url_for('session_refunds', id=session_id))


@app.route('/refunds/<int:id>/delete', methods=['POST'])
@admin_required
def delete_dropout_refund(id):
    refund = DropoutRefund.query.get_or_404(id)
    session_id = refund.session_id
    db.session.delete(refund)
    db.session.commit()
    flash('Refund deleted successfully!', 'success')
    return redirect(url_for('session_refunds', id=session_id))


# Attendance API - Batch update (for concurrent changes)
@app.route('/api/attendance/batch', methods=['POST'])
@csrf.exempt  # API endpoint uses JSON
@admin_required
def batch_update_attendance():
    """Batch update multiple attendance records in a single transaction"""
    data = request.get_json()
    updates = data.get('updates', [])

    if not updates:
        return jsonify({'success': False, 'error': 'No updates provided'})

    results = []
    errors = []

    for update in updates:
        player_id = update.get('player_id')
        session_id = update.get('session_id')
        status = update.get('status')

        if status not in ['YES', 'NO', 'TENTATIVE', 'DROPOUT', 'FILLIN', 'STANDBY', 'CLEAR']:
            errors.append(f'Invalid status for session {session_id}, player {player_id}')
            continue

        sess = Session.query.get(session_id)
        if not sess:
            errors.append(f'Session {session_id} not found')
            continue

        attendance = Attendance.query.filter_by(player_id=player_id, session_id=session_id).first()
        current_status = attendance.status if attendance else None

        # When session is frozen, only allow specific transitions
        if sess.voting_frozen:
            allowed_transitions = {
                'YES': ['DROPOUT', 'STANDBY'],
                'NO': ['FILLIN', 'STANDBY'],
                'TENTATIVE': ['DROPOUT', 'FILLIN', 'STANDBY'],
                'DROPOUT': ['YES', 'STANDBY'],
                'FILLIN': ['NO', 'STANDBY'],
                'STANDBY': ['YES', 'NO'],
                None: ['FILLIN', 'STANDBY'],
            }
            allowed = allowed_transitions.get(current_status, [])
            if status not in allowed and status != current_status:
                errors.append(f'Session {session_id} is frozen. Only Dropout and Fill-in changes allowed.')
                continue

        if status == 'CLEAR':
            if attendance:
                db.session.delete(attendance)
        elif attendance:
            old_status = attendance.status
            attendance.status = status

            # Auto-create refund when dropping out of a frozen session
            if sess.voting_frozen and status == 'DROPOUT' and old_status == 'YES':
                existing_refund = DropoutRefund.query.filter_by(
                    session_id=session_id, player_id=player_id
                ).first()
                if not existing_refund:
                    suggested_amount = sess.calculate_suggested_refund()
                    refund = DropoutRefund(
                        player_id=player_id,
                        session_id=session_id,
                        refund_amount=suggested_amount,
                        suggested_amount=suggested_amount,
                        status='pending'
                    )
                    db.session.add(refund)

            # Auto-delete refund when reverting from dropout
            if sess.voting_frozen and old_status == 'DROPOUT' and status == 'YES':
                existing_refund = DropoutRefund.query.filter_by(
                    session_id=session_id, player_id=player_id, status='pending'
                ).first()
                if existing_refund:
                    db.session.delete(existing_refund)
        else:
            player = Player.query.get(player_id)
            attendance = Attendance(
                session_id=session_id,
                player_id=player_id,
                status=status,
                category=player.category if player else 'regular'
            )
            db.session.add(attendance)

        results.append({'session_id': session_id, 'player_id': player_id, 'status': status})

    db.session.commit()
    clear_session_cache()  # Invalidate cached data

    return jsonify({
        'success': len(errors) == 0,
        'updated': len(results),
        'errors': errors
    })


# Attendance API
@app.route('/api/attendance', methods=['POST'])
@csrf.exempt  # API endpoint uses JSON
@admin_required
def update_attendance():
    data = request.get_json()
    player_id = data.get('player_id')
    session_id = data.get('session_id')
    status = data.get('status')

    if status not in ['YES', 'NO', 'TENTATIVE', 'DROPOUT', 'FILLIN', 'STANDBY', 'CLEAR']:
        return jsonify({'error': 'Invalid status'}), 400

    sess = Session.query.get(session_id)
    if not sess:
        return jsonify({'error': 'Session not found'}), 404

    attendance = Attendance.query.filter_by(player_id=player_id, session_id=session_id).first()
    current_status = attendance.status if attendance else None

    # When session is frozen, only allow specific transitions
    if sess.voting_frozen:
        allowed_transitions = {
            'YES': ['DROPOUT', 'STANDBY'],
            'NO': ['FILLIN', 'STANDBY'],
            'TENTATIVE': ['DROPOUT', 'FILLIN', 'STANDBY'],
            'DROPOUT': ['YES', 'STANDBY'],
            'FILLIN': ['NO', 'STANDBY'],
            'STANDBY': ['YES', 'NO'],
            None: ['FILLIN', 'STANDBY'],
        }

        allowed = allowed_transitions.get(current_status, [])
        if status not in allowed and status != current_status:
            return jsonify({'error': f'Session is frozen. Only Dropout and Fill-in changes are allowed.'}), 403

    if status == 'CLEAR':
        if attendance:
            db.session.delete(attendance)
    elif attendance:
        old_status = attendance.status
        attendance.status = status

        # Auto-create refund when dropping out of a frozen session
        if sess.voting_frozen and status == 'DROPOUT' and old_status == 'YES':
            # Check if refund already exists
            existing_refund = DropoutRefund.query.filter_by(
                session_id=session_id, player_id=player_id
            ).first()
            if not existing_refund:
                suggested_amount = sess.calculate_suggested_refund()
                refund = DropoutRefund(
                    player_id=player_id,
                    session_id=session_id,
                    refund_amount=suggested_amount,
                    suggested_amount=suggested_amount,
                    status='pending'
                )
                db.session.add(refund)

        # Remove refund if reverting from DROPOUT back to YES
        if sess.voting_frozen and status == 'YES' and old_status == 'DROPOUT':
            existing_refund = DropoutRefund.query.filter_by(
                session_id=session_id, player_id=player_id, status='pending'
            ).first()
            if existing_refund:
                db.session.delete(existing_refund)
    else:
        player = Player.query.get(player_id)
        attendance = Attendance(player_id=player_id, session_id=session_id, status=status, category=player.category if player else 'regular')
        db.session.add(attendance)

    db.session.commit()
    clear_session_cache()  # Invalidate cached data

    # Return updated session costs
    return jsonify({
        'success': True,
        'attendee_count': sess.get_attendee_count(),
        'cost_per_player': sess.get_cost_per_player()
    })


# Dropout + fill-in handler — atomically processes dropout, assigns fill-in, creates refund
@app.route('/api/attendance/process-dropout', methods=['POST'])
@csrf.exempt
@admin_required
def process_dropout():
    data = request.get_json()
    session_id       = data.get('session_id')
    dropout_player_id = data.get('dropout_player_id')
    fillin_player_id  = data.get('fillin_player_id')   # may be None
    refund_amount    = float(data.get('refund_amount', 0))

    from datetime import date as _date
    sess = Session.query.get_or_404(session_id)
    today = _date.today().strftime('%m/%d')

    # ── Look up player names ──────────────────────────────────────────────────
    dropout_player = Player.query.get(dropout_player_id)
    fillin_player  = Player.query.get(fillin_player_id) if fillin_player_id else None
    dropout_name   = dropout_player.name if dropout_player else f'Player {dropout_player_id}'
    fillin_name    = fillin_player.name  if fillin_player  else None

    def _append_comment(att, new_note):
        existing = (att.comments or '').strip()
        att.comments = (existing + '\n' + new_note).strip() if existing else new_note

    # ── Mark dropout ──────────────────────────────────────────────────────────
    dropout_att = Attendance.query.filter_by(
        player_id=dropout_player_id, session_id=session_id
    ).first()
    if not dropout_att:
        return jsonify({'error': 'Player attendance not found'}), 404

    dropout_att.status = 'DROPOUT'
    dropout_att.payment_status = 'pending_refund'
    dropout_note = f'Dropped out on {today}'
    dropout_note += f', filled by {fillin_name}' if fillin_name else ', no fill-in'
    _append_comment(dropout_att, dropout_note)

    # Create / update refund record
    existing_refund = DropoutRefund.query.filter_by(
        session_id=session_id, player_id=dropout_player_id
    ).first()
    if existing_refund:
        existing_refund.refund_amount = refund_amount
    else:
        db.session.add(DropoutRefund(
            player_id=dropout_player_id,
            session_id=session_id,
            refund_amount=refund_amount,
            suggested_amount=refund_amount,
            status='pending'
        ))

    # ── Assign fill-in (standby → fillin) ────────────────────────────────────
    if fillin_player_id:
        fillin_att = Attendance.query.filter_by(
            player_id=fillin_player_id, session_id=session_id
        ).first()
        if fillin_att:
            fillin_att.status = 'FILLIN'
            fillin_att.payment_status = 'unpaid'
        else:
            fillin_att = Attendance(
                player_id=fillin_player_id,
                session_id=session_id,
                status='FILLIN',
                category=fillin_player.category if fillin_player else 'regular',
                payment_status='unpaid'
            )
            db.session.add(fillin_att)
        _append_comment(fillin_att, f'Filled in on {today} for {dropout_name}')

    db.session.commit()
    clear_session_cache()

    return jsonify({
        'success': True,
        'attendee_count': sess.get_attendee_count(),
        'cost_per_player': sess.get_cost_per_player(),
        'fillin_assigned': bool(fillin_player_id)
    })


# Attendance category API - update player category for a specific session
@app.route('/api/attendance/category', methods=['POST'])
@csrf.exempt  # API endpoint uses JSON
@admin_required
def update_attendance_category():
    data = request.get_json()
    player_id = data.get('player_id')
    session_id = data.get('session_id')
    category = data.get('category')

    if category not in ['regular', 'adhoc', 'kid']:
        return jsonify({'error': 'Invalid category'}), 400

    attendance = Attendance.query.filter_by(player_id=player_id, session_id=session_id).first()

    if attendance:
        attendance.category = category
    else:
        attendance = Attendance(player_id=player_id, session_id=session_id, status='NO', category=category)
        db.session.add(attendance)

    db.session.commit()

    return jsonify({
        'success': True,
        'player_id': player_id,
        'session_id': session_id,
        'category': category
    })


@app.route('/api/attendance/additional-cost', methods=['POST'])
@csrf.exempt
@admin_required
def update_attendance_additional_cost():
    data = request.get_json()
    player_id = data.get('player_id')
    session_id = data.get('session_id')
    additional_cost = float(data.get('additional_cost', 0))

    attendance = Attendance.query.filter_by(player_id=player_id, session_id=session_id).first()

    if attendance:
        attendance.additional_cost = additional_cost
        db.session.commit()
        return jsonify({'success': True})

    return jsonify({'error': 'Attendance record not found'}), 404


@app.route('/api/attendance/bulk-payment-status', methods=['POST'])
@csrf.exempt
@admin_required
def bulk_update_payment_status():
    data = request.get_json()
    player_ids = data.get('player_ids', [])
    session_ids = data.get('session_ids', [])
    payment_status = data.get('payment_status')

    if payment_status not in ['paid', 'unpaid']:
        return jsonify({'error': 'Invalid payment status'}), 400
    if not player_ids or not session_ids:
        return jsonify({'error': 'player_ids and session_ids required'}), 400

    records = Attendance.query.filter(
        Attendance.player_id.in_(player_ids),
        Attendance.session_id.in_(session_ids),
        Attendance.status.in_(['YES', 'DROPOUT', 'FILLIN'])
    ).all()

    for att in records:
        att.payment_status = payment_status

    # Optionally record payment entries when marking as paid
    if payment_status == 'paid':
        method = data.get('method')
        payments = data.get('payments', [])  # [{player_id, amount}]
        valid_methods = ['Zelle', 'Cash', 'Venmo', 'Refund']
        if method in valid_methods and payments:
            for p in payments:
                pid = p.get('player_id')
                amount = float(p.get('amount', 0))
                if pid and amount > 0:
                    payment = Payment(
                        player_id=pid,
                        amount=amount,
                        method=method,
                        notes='Bulk payment via sessions matrix',
                        created_by=session.get('player_id') or 'admin'
                    )
                    db.session.add(payment)

    db.session.commit()
    return jsonify({'success': True, 'updated': len(records)})


@app.route('/api/attendance/payment-status', methods=['POST'])
@csrf.exempt
@admin_required
def update_attendance_payment_status():
    data = request.get_json()
    player_id = data.get('player_id')
    session_id = data.get('session_id')
    payment_status = data.get('payment_status')

    if payment_status not in ['unpaid', 'paid']:
        return jsonify({'error': 'Invalid payment status'}), 400

    attendance = Attendance.query.filter_by(player_id=player_id, session_id=session_id).first()

    if attendance:
        attendance.payment_status = payment_status
        db.session.commit()
        return jsonify({'success': True})

    return jsonify({'error': 'Attendance record not found'}), 404


@app.route('/api/attendance/comments', methods=['POST'])
@csrf.exempt
@admin_required
def update_attendance_comments():
    data = request.get_json()
    player_id = data.get('player_id')
    session_id = data.get('session_id')
    comments = data.get('comments', '')

    attendance = Attendance.query.filter_by(player_id=player_id, session_id=session_id).first()

    if attendance:
        attendance.comments = comments
        db.session.commit()
        return jsonify({'success': True})

    return jsonify({'error': 'Attendance record not found'}), 404


@app.route('/api/bulk-attendance-players', methods=['POST'])
@csrf.exempt
@admin_required
def bulk_attendance_players():
    """Set attendance (YES or NO) for specific player IDs across multiple sessions."""
    data = request.get_json()
    player_ids = data.get('player_ids', [])
    session_ids = data.get('session_ids', [])  # empty = all active sessions
    status = data.get('status', 'YES')

    if status not in ('YES', 'NO'):
        return jsonify({'error': 'Invalid status'}), 400
    if not player_ids:
        return jsonify({'error': 'No players selected'}), 400

    if not session_ids:
        session_ids = [s.id for s in Session.query.filter_by(is_archived=False).all()]

    count = 0
    for session_id in session_ids:
        sess = Session.query.get(session_id)
        if not sess:
            continue
        for player_id in player_ids:
            player = Player.query.get(player_id)
            if not player:
                continue
            att = Attendance.query.filter_by(session_id=session_id, player_id=player_id).first()
            if att:
                att.status = status
            else:
                att = Attendance(
                    session_id=session_id,
                    player_id=player_id,
                    status=status,
                    category=player.category
                )
                db.session.add(att)
            count += 1

    db.session.commit()
    cache.clear()
    return jsonify({'success': True, 'updated': count})


@app.route('/api/bulk-session-payment', methods=['POST'])
@csrf.exempt
@admin_required
def bulk_session_payment():
    """Record payments for multiple players in a session at once"""
    data = request.get_json()
    session_id = data.get('session_id')
    payments_data = data.get('payments', [])
    method = data.get('method', 'Zelle')

    if not session_id or not payments_data:
        return jsonify({'error': 'Missing required data'}), 400

    sess = Session.query.get(session_id)
    if not sess:
        return jsonify({'error': 'Session not found'}), 404

    session_date_str = sess.date.strftime("%b %d, %Y")
    count = 0
    for p_data in payments_data:
        player_id = p_data.get('player_id')
        amount = float(p_data.get('amount', 0))

        if not player_id or amount <= 0:
            continue

        player = Player.query.get(player_id)
        if not player:
            continue

        payment = Payment(
            player_id=player_id,
            amount=amount,
            method=method,
            date=datetime.utcnow(),
            notes=f'Session {session_date_str}'
        )
        db.session.add(payment)

        att = Attendance.query.filter_by(player_id=player_id, session_id=session_id).first()
        if att:
            att.payment_status = 'paid'

        count += 1

    db.session.commit()
    return jsonify({'success': True, 'count': count})


@app.route('/api/player/additional-charges', methods=['POST'])
@csrf.exempt
@admin_required
def update_player_additional_charges():
    data = request.get_json()
    player_id = data.get('player_id')
    additional_charges = float(data.get('additional_charges', 0))

    player = Player.query.get(player_id)
    if player:
        player.additional_charges = additional_charges
        db.session.commit()
        return jsonify({'success': True})

    return jsonify({'error': 'Player not found'}), 404


@app.route('/api/player/comments', methods=['POST'])
@csrf.exempt
@admin_required
def update_player_comments():
    data = request.get_json()
    player_id = data.get('player_id')
    comments = data.get('comments', '')

    player = Player.query.get(player_id)
    if player:
        player.admin_comments = comments
        db.session.commit()
        return jsonify({'success': True})

    return jsonify({'error': 'Player not found'}), 404


# Payment routes
@app.route('/payments')
@admin_required
def payments():
    payment_list = Payment.query.order_by(Payment.date.desc()).all()

    # Calculate totals
    total_collected = sum(p.amount for p in payment_list)

    # Outstanding balances
    players = Player.query.all()
    balances = [(p, p.get_balance()) for p in players if p.get_balance() > 0]
    balances.sort(key=lambda x: x[1], reverse=True)

    return render_template('payments.html',
                         payments=payment_list,
                         total_collected=round(total_collected, 2),
                         outstanding_balances=balances)


@app.route('/api/bulk-payment', methods=['POST'])
@csrf.exempt
@admin_required
def bulk_payment_api():
    """Record payments for multiple players at once (general, not session-specific)"""
    data = request.get_json()
    payments_data = data.get('payments', [])
    method = data.get('method', 'Zelle')
    date_str = data.get('date')

    if not payments_data:
        return jsonify({'error': 'No payments provided'}), 400

    payment_date = datetime.strptime(date_str, '%Y-%m-%d') if date_str else datetime.utcnow()

    count = 0
    for p_data in payments_data:
        player_id = p_data.get('player_id')
        amount = float(p_data.get('amount', 0))

        if not player_id or amount <= 0:
            continue

        player = Player.query.get(player_id)
        if not player:
            continue

        payment = Payment(
            player_id=player_id,
            amount=amount,
            method=method,
            date=payment_date,
            notes=p_data.get('notes', '')
        )
        db.session.add(payment)
        count += 1

    db.session.commit()
    return jsonify({'success': True, 'count': count})


@app.route('/payments/add', methods=['GET', 'POST'])
@admin_required
def add_payment():
    if request.method == 'POST':
        player_id = int(request.form.get('player_id'))
        amount = float(request.form.get('amount'))
        method = request.form.get('method')
        date_str = request.form.get('date')
        notes = request.form.get('notes')

        payment_date = datetime.strptime(date_str, '%Y-%m-%d') if date_str else datetime.utcnow()

        payment = Payment(
            player_id=player_id,
            amount=amount,
            method=method,
            date=payment_date,
            notes=notes
        )
        db.session.add(payment)
        db.session.commit()

        player = Player.query.get(player_id)
        flash(f'Payment of ${amount:.2f} from {player.name} recorded!', 'success')
        return redirect(url_for('payments'))

    players = Player.query.order_by(Player.name).all()
    return render_template('payment_form.html', players=players, payment=None, today=date.today().isoformat())


@app.route('/payments/<int:id>/delete', methods=['POST'])
@admin_required
def delete_payment(id):
    payment = Payment.query.get_or_404(id)
    db.session.delete(payment)
    db.session.commit()
    flash('Payment deleted successfully!', 'success')
    return redirect(url_for('payments'))


# Birdie Bank routes (admin only)
@app.route('/birdie-bank')
@admin_required
def birdie_bank():
    transactions = BirdieBank.query.order_by(BirdieBank.date.desc()).all()
    current_stock = BirdieBank.get_current_stock()
    total_spent = BirdieBank.get_total_spent()

    # Get sessions for linking usage
    sessions_list = Session.query.order_by(Session.date.desc()).limit(20).all()

    return render_template('birdie_bank.html',
                         transactions=transactions,
                         current_stock=current_stock,
                         total_spent=total_spent,
                         sessions=sessions_list,
                         today=date.today().isoformat())


@app.route('/birdie-bank/add', methods=['POST'])
@admin_required
def add_birdie_transaction():
    transaction_type = request.form.get('transaction_type')
    quantity = int(request.form.get('quantity'))
    cost = float(request.form.get('cost', 0))
    notes = request.form.get('notes')
    date_str = request.form.get('date')
    session_id = request.form.get('session_id')

    transaction_date = datetime.strptime(date_str, '%Y-%m-%d') if date_str else datetime.utcnow()

    transaction = BirdieBank(
        transaction_type=transaction_type,
        quantity=quantity,
        cost=cost if transaction_type == 'purchase' else 0,
        notes=notes,
        date=transaction_date,
        session_id=int(session_id) if session_id else None
    )
    db.session.add(transaction)
    db.session.commit()

    if transaction_type == 'purchase':
        flash(f'Added {quantity} birdies to inventory (${cost:.2f})', 'success')
    else:
        flash(f'Recorded usage of {quantity} birdies', 'success')

    return redirect(url_for('birdie_bank'))


@app.route('/birdie-bank/<int:id>/delete', methods=['POST'])
@admin_required
def delete_birdie_transaction(id):
    transaction = BirdieBank.query.get_or_404(id)
    db.session.delete(transaction)
    db.session.commit()
    flash('Transaction deleted successfully!', 'success')
    return redirect(url_for('birdie_bank'))


# Admin password reset (for player admins)
@app.route('/admin/reset-password', methods=['GET', 'POST'])
@admin_required
def reset_admin_password():
    if request.method == 'POST':
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')

        # Verify current admin password
        if current_password != app.config['APP_PASSWORD']:
            flash('Current admin password is incorrect', 'error')
            return redirect(url_for('reset_admin_password'))

        if new_password != confirm_password:
            flash('New passwords do not match', 'error')
            return redirect(url_for('reset_admin_password'))

        if len(new_password) < 4:
            flash('Password must be at least 4 characters', 'error')
            return redirect(url_for('reset_admin_password'))

        # Update the password in config (runtime only - need env var for persistence)
        app.config['APP_PASSWORD'] = new_password
        flash('Admin password updated successfully! Note: Update APP_PASSWORD environment variable for persistence.', 'success')
        return redirect(url_for('dashboard'))

    return render_template('reset_admin_password.html')


# ── EZFacility Integration ────────────────────────────────────────────────────

try:
    from ezfacility import fetch_bookings as ezf_fetch_bookings
    EZF_AVAILABLE = True
except ImportError:
    EZF_AVAILABLE = False

EZF_NAME = 'ezfacility'


@app.route('/ezfacility/settings', methods=['GET', 'POST'])
@admin_required
def ezfacility_settings():
    if request.method == 'POST':
        url      = request.form.get('url', '').strip()
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        rec = ExternalIntegration.get_or_create(EZF_NAME)
        if url:
            rec.url = url
        if username:
            rec.username = username
        if password:
            rec.password = password
        cookie = request.form.get('session_cookie', '').strip()
        if cookie:
            rec.session_cookie = cookie
        db.session.commit()

        flash('Royal Facility settings saved (encrypted).', 'success')
        return redirect(url_for('ezfacility_settings'))

    rec = ExternalIntegration.query.filter_by(name=EZF_NAME).first()
    stored_url      = rec.url            if rec else ''
    stored_username = rec.username       if rec else ''
    has_credentials = bool(rec and rec.username and rec._password_enc)
    has_cookie      = bool(rec and rec._cookie_enc)
    return render_template('ezfacility_settings.html',
                           has_credentials=has_credentials,
                           stored_username=stored_username,
                           stored_url=stored_url,
                           has_cookie=has_cookie)


@app.route('/ezfacility/sync')
@admin_required
def ezfacility_sync_page():
    if not EZF_AVAILABLE:
        flash('EZFacility module not installed. Run: pip install requests beautifulsoup4', 'error')
        return redirect(url_for('sessions'))
    _, username, password = ExternalIntegration.get_credentials(EZF_NAME)
    if not username or not password:
        flash('Configure EZFacility credentials first.', 'error')
        return redirect(url_for('ezfacility_settings'))
    return render_template('ezfacility_sync.html')


@app.route('/api/ezfacility/open-browser', methods=['POST'])
@csrf.exempt
@admin_required
def api_ezfacility_open_browser():
    """Open EZFacility login page in the system default browser."""
    import subprocess, sys
    url = 'https://royalbadminton.ezfacility.com/login'
    try:
        if sys.platform == 'darwin':
            subprocess.Popen(['open', url])
        elif sys.platform == 'win32':
            subprocess.Popen(['start', url], shell=True)
        else:
            subprocess.Popen(['xdg-open', url])
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/ezfacility/import-browser-cookies', methods=['POST'])
@csrf.exempt
@admin_required
def api_ezfacility_import_browser_cookies():
    """
    Read fresh EZFacility cookies from any installed browser.
    Tries Chrome, Brave, Edge, Arc, Chromium, Firefox, Safari — uses first with a valid auth cookie.
    Works on macOS, Windows, and Linux.
    """
    try:
        import browser_cookie3
    except ImportError:
        return jsonify({'success': False, 'error': 'browser_cookie3 not installed.'})

    domain = 'royalbadminton.ezfacility.com'
    auth_names = {'EZSelfServiceAuth', '.ASPXAUTH', 'EZAuth'}

    # Try all supported browsers — order by most common
    candidates = [
        ('Chrome',    browser_cookie3.chrome),
        ('Brave',     browser_cookie3.brave),
        ('Edge',      browser_cookie3.edge),
        ('Arc',       browser_cookie3.arc),
        ('Chromium',  browser_cookie3.chromium),
        ('Firefox',   browser_cookie3.firefox),
        ('Safari',    browser_cookie3.safari),
        ('Opera',     browser_cookie3.opera),
        ('Vivaldi',   browser_cookie3.vivaldi),
    ]

    cookies = []
    browser_used = None
    for name, getter in candidates:
        try:
            jar = getter(domain_name=domain)
            found = list(jar)
            # Must have an auth cookie — not just pre-login cookies
            if found and any(c.name in auth_names for c in found):
                cookies = found
                browser_used = name
                break
        except Exception:
            continue

    if not cookies:
        tried = ', '.join(n for n, _ in candidates)
        return jsonify({'success': False, 'error':
            f'No active session found in any browser ({tried}). '
            'Please log in to Royal Facility in your browser first, then try again.'})

    # Verify cookies actually work against /MySchedule
    from playwright.sync_api import sync_playwright
    pw_cookies = [{'name': c.name, 'value': c.value, 'domain': domain, 'path': '/'} for c in cookies]
    try:
        with sync_playwright() as pw:
            browser_pw = pw.chromium.launch(headless=True, args=['--no-sandbox'])
            ctx = browser_pw.new_context()
            ctx.add_cookies(pw_cookies)
            page = ctx.new_page()
            page.goto(f'https://{domain}/MySchedule', wait_until='networkidle', timeout=20000)
            logged_in = '/login' not in page.url.lower()
            browser_pw.close()
    except Exception as e:
        return jsonify({'success': False, 'error': f'Cookie verification failed: {e}'})

    if not logged_in:
        return jsonify({'success': False, 'error':
            f'Session in {browser_used} has expired — please log in to Royal Facility again, then retry.'})

    cookie_str = '; '.join(f'{c.name}={c.value}' for c in cookies)
    rec = ExternalIntegration.get_or_create(EZF_NAME)
    rec.session_cookie = cookie_str
    db.session.commit()
    return jsonify({'success': True,
                    'message': f'Connected via {browser_used} — session verified and saved.'})


@app.route('/api/ezfacility/fetch-bookings', methods=['POST'])
@csrf.exempt
@admin_required
def api_ezfacility_fetch_bookings():
    import subprocess, sys, json as _json, tempfile

    _, username, password = ExternalIntegration.get_credentials(EZF_NAME)
    if not username or not password:
        return jsonify({'success': False, 'error': 'EZFacility credentials not configured. Go to Settings.'})

    data = request.get_json(silent=True) or {}
    target_dates = sorted(set(data.get('dates', [])))
    if not target_dates:
        return jsonify({'success': False, 'error': 'No dates provided.'})

    out_path = os.path.join(os.path.dirname(__file__), 'instance', 'ezf_scrape_output.json')
    script   = os.path.join(os.path.dirname(__file__), 'ezf_scrape.py')

    env = os.environ.copy()
    env['RF_USERNAME'] = username
    env['RF_PASSWORD'] = password

    try:
        proc = subprocess.run(
            [sys.executable, script, '--dates', ','.join(target_dates), '--out', out_path],
            env=env,
            timeout=180,
            capture_output=True,
            text=True
        )
        app.logger.info(f'ezf_scrape stdout: {proc.stdout[-500:]}')
        if proc.returncode != 0:
            app.logger.error(f'ezf_scrape stderr: {proc.stderr[-500:]}')
            return jsonify({'success': False, 'error': f'Scraper exited with error. Check that Chrome is installed.'})
    except subprocess.TimeoutExpired:
        return jsonify({'success': False, 'error': 'Scraper timed out (3 min). Try fewer dates.'})
    except Exception as e:
        app.logger.error(f'ezf_scrape launch error: {e}', exc_info=True)
        return jsonify({'success': False, 'error': f'Could not run scraper: {e}'})

    try:
        with open(out_path) as f:
            raw_bookings = _json.load(f)
    except Exception as e:
        return jsonify({'success': False, 'error': f'Could not read scraper output: {e}'})

    # Group by date
    bookings_by_date = defaultdict(list)
    for b in raw_bookings:
        bookings_by_date[b['date']].append(b)

    # Load matching local sessions
    if bookings_by_date:
        from datetime import date as _date
        booking_dates = [_date.fromisoformat(d) for d in bookings_by_date]
        local_sessions = Session.query.filter(Session.date.in_(booking_dates)).all()
    else:
        local_sessions = []

    local_by_date = {s.date.isoformat(): s for s in local_sessions}

    result = []
    for date_str, courts in sorted(bookings_by_date.items()):
        local_sess = local_by_date.get(date_str)
        local_courts = local_sess.courts.all() if local_sess else []
        local_court_names = {c.name.lower() for c in local_courts}

        result.append({
            'date': date_str,
            'local_session_id': local_sess.id if local_sess else None,
            'courts': [{
                'court_name':       b['court_name'],
                'start_time':       b['start_time'],
                'start_time_24':    b['start_time_24'],
                'end_time_24':      b['end_time_24'],
                'duration_minutes': b['duration_minutes'],
                'suggested_cost':   b['suggested_cost'],
                'already_in_local': b['court_name'].lower() in local_court_names,
            } for b in courts],
        })

    return jsonify({'success': True, 'bookings': result, 'total': len(raw_bookings)})


@app.route('/api/ezfacility/sync', methods=['POST'])
@csrf.exempt
@admin_required
def api_ezfacility_sync():
    data = request.get_json()
    bookings = data.get('bookings', [])

    created_sessions = 0
    added_courts = 0
    skipped = 0

    players = Player.query.filter_by(is_active=True, is_approved=True).all()

    for booking in bookings:
        date_str = booking.get('date')
        courts_data = booking.get('courts', [])
        create_session_flag = booking.get('create_session', True)

        if not date_str or not courts_data:
            continue

        session_date = date.fromisoformat(date_str)
        local_sess = Session.query.filter_by(date=session_date).first()

        if not local_sess:
            if not create_session_flag:
                skipped += 1
                continue
            local_sess = Session(
                date=session_date,
                birdie_cost=2.0,
                notes='Created via EZFacility sync'
            )
            db.session.add(local_sess)
            db.session.flush()
            for player in players:
                att = Attendance(
                    player_id=player.id,
                    session_id=local_sess.id,
                    status='NO',
                    category=player.category
                )
                db.session.add(att)
            created_sessions += 1

        existing_names = {c.name.lower() for c in local_sess.courts.all()}
        for cd in courts_data:
            name = cd.get('court_name', 'Court')
            if name.lower() in existing_names:
                continue
            court = Court(
                session_id=local_sess.id,
                name=name,
                start_time=cd.get('start_time_24') or cd.get('start_time', '06:30'),
                end_time=cd.get('end_time_24') or cd.get('end_time', '09:30'),
                cost=float(cd.get('cost', 105.0)),
                court_type=cd.get('court_type', 'regular')
            )
            db.session.add(court)
            added_courts += 1
            existing_names.add(name.lower())

    db.session.commit()
    clear_session_cache()

    return jsonify({'success': True, 'created_sessions': created_sessions,
                    'added_courts': added_courts, 'skipped': skipped})


# Rate limit error handler
@app.errorhandler(429)
def ratelimit_handler(e):
    security_logger.warning(f'RATE_LIMIT_EXCEEDED - IP: {request.remote_addr}, Path: {request.path}')
    flash('Too many requests. Please try again later.', 'error')
    return redirect(url_for('login'))


if __name__ == '__main__':
    app.run(debug=True, port=5050, use_reloader=False)  # use_reloader=False prevents Playwright/Chromium conflicts
