from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
import base64
import hashlib
from cryptography.fernet import Fernet, InvalidToken

db = SQLAlchemy()

# ── Application-level column encryption ──────────────────────────────────────
# The encryption key is derived at runtime from the app's SECRET_KEY.
# Call init_encryption(app) once during app startup.

_fernet = None


def init_encryption(secret_key: str):
    """Call once at app startup to initialise the column encryption cipher."""
    global _fernet
    key_bytes = hashlib.sha256(secret_key.encode()).digest()
    _fernet = Fernet(base64.urlsafe_b64encode(key_bytes))


def _encrypt(value: str) -> str:
    if _fernet is None or not value:
        return value or ''
    return _fernet.encrypt(value.encode()).decode()


def _decrypt(value: str) -> str:
    if _fernet is None or not value:
        return value or ''
    try:
        return _fernet.decrypt(value.encode()).decode()
    except (InvalidToken, Exception):
        return ''  # Return empty on decryption failure (wrong key or corrupt)


class Player(db.Model):
    __tablename__ = 'players'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, index=True)
    category = db.Column(db.String(20), nullable=False, default='regular', index=True)  # regular, adhoc, kid
    phone = db.Column(db.String(20))
    email = db.Column(db.String(100), index=True)
    password_hash = db.Column(db.String(255))
    zelle_preference = db.Column(db.String(10), default='email')  # 'email' or 'phone'
    date_of_birth = db.Column(db.Date, nullable=True)  # Optional date of birth
    gender = db.Column(db.String(10), default='male')  # 'male', 'female', 'other'
    profile_photo = db.Column(db.String(255))  # filename of uploaded photo
    managed_by = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=True)  # Parent player who can vote/pay for this player
    is_admin = db.Column(db.Boolean, default=False)  # Player admin flag
    is_active = db.Column(db.Boolean, default=True, index=True)  # Active/Inactive status
    is_approved = db.Column(db.Boolean, default=False, index=True)  # Registration approval status

    # Admin-managed fields for active sessions
    additional_charges = db.Column(db.Float, default=0)  # Extra charges added by admin
    admin_comments = db.Column(db.Text)  # Admin comments for this player

    # Audit fields
    created_by = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_by = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    attendances = db.relationship('Attendance', backref='player', lazy='dynamic', cascade='all, delete-orphan', foreign_keys='Attendance.player_id')
    payments = db.relationship('Payment', backref='player', lazy='dynamic', cascade='all, delete-orphan', foreign_keys='Payment.player_id')

    # Managed players relationship (players this player can vote/pay for)
    managed_players = db.relationship('Player', backref=db.backref('manager', remote_side=[id]), foreign_keys=[managed_by])

    def set_password(self, password):
        """Set password hash from plain text password"""
        self.password_hash = generate_password_hash(password, method='pbkdf2:sha256')

    def check_password(self, password):
        """Check if provided password matches hash"""
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)

    def get_total_charges(self):
        """Calculate total charges from attended sessions based on player category.
        Includes YES, DROPOUT, and FILLIN statuses - dropouts and fill-ins are still charged."""
        total = 0
        for attendance in self.attendances.filter(Attendance.status.in_(['YES', 'DROPOUT', 'FILLIN'])).all():
            session = attendance.session
            if attendance.category == 'kid':
                # Kids pay flat $11 per session
                total += session.get_cost_per_kid()
            elif attendance.category == 'adhoc':
                # Adhoc players: adhoc court cost / adhoc players + birdie
                total += session.get_cost_per_adhoc_player()
            else:
                # Regular players: regular court cost / regular players + birdie
                total += session.get_cost_per_regular_player()
        return round(total, 2)

    def get_total_payments(self):
        """Calculate total payments made"""
        return round(sum(p.amount for p in self.payments.all()), 2)

    def get_balance(self):
        """Calculate outstanding balance (charges - payments)"""
        return round(self.get_total_charges() - self.get_total_payments(), 2)

    def get_pending_refunds_count(self):
        """Count pending refunds for this player"""
        return DropoutRefund.query.filter_by(player_id=self.id, status='pending').count()

    def get_total_refunded(self):
        """Get total amount already refunded to this player"""
        total = db.session.query(db.func.sum(DropoutRefund.refund_amount)).filter_by(
            player_id=self.id, status='processed'
        ).scalar() or 0
        return round(total, 2)

    def get_pending_refund_amount(self):
        """Get total pending refund amount for this player"""
        total = db.session.query(db.func.sum(DropoutRefund.refund_amount)).filter_by(
            player_id=self.id, status='pending'
        ).scalar() or 0
        return round(total, 2)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'category': self.category,
            'phone': self.phone,
            'email': self.email,
            'zelle_preference': self.zelle_preference,
            'total_charges': self.get_total_charges(),
            'total_payments': self.get_total_payments(),
            'balance': self.get_balance()
        }


class Session(db.Model):
    __tablename__ = 'sessions'

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, index=True)
    birdie_cost = db.Column(db.Float, nullable=False, default=0)
    notes = db.Column(db.Text)
    is_archived = db.Column(db.Boolean, default=False, index=True)
    voting_frozen = db.Column(db.Boolean, default=False)  # If True, players cannot change their votes

    # Session time configuration (used when creating sessions, courts can override)
    hours = db.Column(db.Float, default=3)  # Duration in hours (2, 3, or 3.5)
    start_time = db.Column(db.String(10), default='06:30')  # HH:MM format
    end_time = db.Column(db.String(10), default='09:30')  # HH:MM format
    court_cost = db.Column(db.Float, default=105)  # Default cost per court based on hours
    credits = db.Column(db.Float, default=0)  # Credits issued for this session, usable toward future bookings
    apply_credits = db.Column(db.Boolean, default=False)  # If True, credits are included in per-player cost calculation

    # Audit fields
    created_by = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_by = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    attendances = db.relationship('Attendance', backref='session', lazy='dynamic', cascade='all, delete-orphan')
    courts = db.relationship('Court', backref='session', lazy='dynamic', cascade='all, delete-orphan', order_by='Court.id')

    def get_attendee_count(self):
        """Count players who attended (status=YES) plus dropouts (for frozen sessions, dropouts still count toward cost calculation)"""
        return self.attendances.filter(Attendance.status.in_(['YES', 'DROPOUT'])).count()

    def get_regular_player_count(self):
        """Count regular players who attended (status=YES or DROPOUT - dropouts still count for frozen session cost calculation)"""
        return self.attendances.filter(
            Attendance.status.in_(['YES', 'DROPOUT']),
            Attendance.category == 'regular'
        ).count()

    def get_adhoc_player_count(self):
        """Count adhoc players who attended (status=YES or DROPOUT - dropouts still count for frozen session cost calculation)"""
        return self.attendances.filter(
            Attendance.status.in_(['YES', 'DROPOUT']),
            Attendance.category == 'adhoc'
        ).count()

    def get_kid_player_count(self):
        """Count kid players who attended (status=YES or DROPOUT - dropouts still count for frozen session cost calculation)"""
        return self.attendances.filter(
            Attendance.status.in_(['YES', 'DROPOUT']),
            Attendance.category == 'kid'
        ).count()

    def get_court_count(self):
        """Get number of courts booked"""
        return self.courts.count()

    def get_suggested_courts(self):
        """Suggest number of courts based on attendees (5 players per court)"""
        attendees = self.get_attendee_count()
        if attendees == 0:
            return 0
        import math
        return math.ceil(attendees / 5)

    def get_total_cost(self):
        """Calculate total session cost from all courts"""
        return sum(court.cost for court in self.courts.all())

    def get_time_range(self):
        """Get overall time range from all courts, or session defaults if no courts"""
        court_list = self.courts.all()
        if not court_list:
            # Use session's stored times if no courts yet
            if self.start_time and self.end_time:
                # Convert HH:MM to display format
                def format_time(time_str):
                    try:
                        h, m = map(int, time_str.split(':'))
                        period = 'AM' if h < 12 else 'PM'
                        display_h = h if h <= 12 else h - 12
                        if display_h == 0:
                            display_h = 12
                        return f"{display_h}:{m:02d} {period}"
                    except:
                        return time_str
                return format_time(self.start_time), format_time(self.end_time)
            return "TBD", "TBD"
        start_times = [c.start_time for c in court_list]
        end_times = [c.end_time for c in court_list]
        return min(start_times), max(end_times)

    def get_cost_per_player(self):
        """Calculate average cost per attending player (for display purposes)"""
        # This returns the regular player cost as the default display
        return self.get_cost_per_regular_player()

    def get_cost_per_regular_player(self):
        """Cost per non-kid player: (regular courts + credits if applied) / regular players + birdie"""
        reg_count = self.get_regular_player_count()
        if reg_count == 0:
            return 0
        total_shared = self.get_regular_court_cost()
        if self.apply_credits:
            total_shared += (self.credits or 0)
        return round(total_shared / reg_count + self.birdie_cost, 2)

    def get_cost_per_adhoc_player(self):
        """Same as regular — all non-kid players share the full cost pool equally"""
        return self.get_cost_per_regular_player()

    def get_cost_per_kid(self):
        """Kids pay flat $11 per session, no birdie cost"""
        return 11.0

    def get_dropout_count(self):
        """Count players who dropped out"""
        return self.attendances.filter_by(status='DROPOUT').count()

    def get_fillin_count(self):
        """Count fill-in players"""
        return self.attendances.filter_by(status='FILLIN').count()

    def calculate_suggested_refund(self):
        """
        Calculate suggested refund amount for a dropout.
        Logic:
        - If there are fill-ins >= dropouts, suggest full refund (someone took their spot)
        - Otherwise, suggest partial refund (cost per player minus birdie cost)
        """
        fillin_count = self.get_fillin_count()
        dropout_count = self.get_dropout_count()

        if fillin_count >= dropout_count and fillin_count > 0:
            # Full refund possible since fill-ins covered the spots
            return self.get_cost_per_player()
        else:
            # Partial refund - they still used some resources (birdie cost is sunk)
            # Refund the court cost portion only
            attendee_count = self.get_attendee_count()
            if attendee_count > 0:
                court_cost_per_player = self.get_regular_court_cost() / attendee_count
                return round(court_cost_per_player, 2)
            return 0

    def get_regular_court_cost(self):
        """Get total cost of regular courts"""
        return sum(court.cost for court in self.courts.all() if court.court_type == 'regular')

    def get_adhoc_court_cost(self):
        """Get total cost of adhoc courts"""
        return sum(court.cost for court in self.courts.all() if court.court_type == 'adhoc')

    def get_total_refunds(self):
        """Get total refunds given for this session"""
        return sum(r.refund_amount for r in self.dropout_refunds if r.status == 'processed')

    def get_total_collection(self):
        """
        Calculate total expected collection from players for this session.
        Includes YES, DROPOUT, and FILLIN - all are charged.
        - Regular players: regular court cost / regular count + birdie
        - Adhoc players: adhoc court cost / adhoc count + birdie
        - Kids: flat $11
        """
        total = 0
        for attendance in self.attendances.filter(Attendance.status.in_(['YES', 'DROPOUT', 'FILLIN'])).all():
            if attendance.category == 'kid':
                total += self.get_cost_per_kid()
            elif attendance.category == 'adhoc':
                total += self.get_cost_per_adhoc_player()
            else:
                total += self.get_cost_per_regular_player()
        return round(total, 2)

    def get_birdie_cost_total(self):
        """Get total birdie cost for the session (birdie_cost * non-kid attendees)"""
        non_kid_count = self.get_regular_player_count() + self.get_adhoc_player_count()
        return round(self.birdie_cost * non_kid_count, 2)

    def get_regular_player_charges(self):
        """Get total charges from regular players for this session"""
        regular_count = self.get_regular_player_count()
        if regular_count == 0:
            return 0
        return round(self.get_cost_per_regular_player() * regular_count, 2)

    def get_adhoc_player_charges(self):
        """Get total charges from adhoc players for this session"""
        adhoc_count = self.get_adhoc_player_count()
        if adhoc_count == 0:
            return 0
        return round(self.get_cost_per_adhoc_player() * adhoc_count, 2)

    def get_kid_player_charges(self):
        """Get total charges from kid players for this session (flat $11 each)"""
        kid_count = self.get_kid_player_count()
        return round(self.get_cost_per_kid() * kid_count, 2)

    def to_dict(self):
        start_time, end_time = self.get_time_range()
        return {
            'id': self.id,
            'date': self.date.isoformat(),
            'start_time': start_time,
            'end_time': end_time,
            'court_count': self.get_court_count(),
            'birdie_cost': self.birdie_cost,
            'notes': self.notes,
            'attendee_count': self.get_attendee_count(),
            'total_cost': self.get_total_cost(),
            'cost_per_player': self.get_cost_per_player()
        }


class Court(db.Model):
    __tablename__ = 'courts'

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('sessions.id'), nullable=False, index=True)
    name = db.Column(db.String(50), default='Court')  # e.g., "Court 1", "Court A"
    start_time = db.Column(db.String(20), nullable=False)  # "6:30 AM"
    end_time = db.Column(db.String(20), nullable=False)    # "9:30 AM"
    cost = db.Column(db.Float, nullable=False, default=0)
    court_type = db.Column(db.String(20), default='regular')  # 'regular' or 'adhoc'

    # Audit fields
    created_by = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_by = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'session_id': self.session_id,
            'name': self.name,
            'start_time': self.start_time,
            'end_time': self.end_time,
            'cost': self.cost
        }


class Attendance(db.Model):
    __tablename__ = 'attendances'

    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=False, index=True)
    session_id = db.Column(db.Integer, db.ForeignKey('sessions.id'), nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False, default='NO', index=True)  # YES, NO, TENTATIVE, DROPOUT, FILLIN
    category = db.Column(db.String(20), default='regular', index=True)  # regular, adhoc, kid - category for this session

    # Per-session payment tracking
    payment_status = db.Column(db.String(20), default='unpaid', index=True)  # unpaid, paid, pending_refund
    additional_cost = db.Column(db.Float, default=0)  # Extra charges for this player in this session
    comments = db.Column(db.Text)  # Admin comments for this player in this session

    # Audit fields
    created_by = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_by = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('player_id', 'session_id', name='unique_player_session'),
        db.Index('idx_attendance_status_category', 'status', 'category'),
        db.Index('idx_attendance_session_status_cat', 'session_id', 'status', 'category'),
    )

    def get_session_cost(self):
        """Calculate total cost for this player in this session (birdie + additional)"""
        session = self.session
        if self.status not in ['YES', 'DROPOUT', 'FILLIN']:
            return 0
        base_cost = session.birdie_cost if session else 0
        return round(base_cost + (self.additional_cost or 0), 2)

    def to_dict(self):
        return {
            'id': self.id,
            'player_id': self.player_id,
            'session_id': self.session_id,
            'status': self.status,
            'category': self.category,
            'payment_status': self.payment_status,
            'additional_cost': self.additional_cost,
            'comments': self.comments,
            'player_name': self.player.name if self.player else None
        }


class Payment(db.Model):
    __tablename__ = 'payments'

    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=False, index=True)
    amount = db.Column(db.Float, nullable=False)
    method = db.Column(db.String(20), nullable=False)  # Zelle, Cash, Venmo
    date = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    notes = db.Column(db.Text)

    # Audit fields
    created_by = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_by = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'player_id': self.player_id,
            'player_name': self.player.name if self.player else None,
            'amount': self.amount,
            'method': self.method,
            'date': self.date.isoformat(),
            'notes': self.notes
        }


class DropoutRefund(db.Model):
    """Track refunds for players who drop out of sessions"""
    __tablename__ = 'dropout_refunds'

    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=False, index=True)
    session_id = db.Column(db.Integer, db.ForeignKey('sessions.id'), nullable=False, index=True)
    refund_amount = db.Column(db.Float, nullable=False, default=0)
    suggested_amount = db.Column(db.Float, default=0)  # System-calculated suggestion
    instructions = db.Column(db.Text)  # Admin instructions/notes
    status = db.Column(db.String(20), default='pending', index=True)  # pending, processed, cancelled
    processed_date = db.Column(db.DateTime, nullable=True)

    # Audit fields
    created_by = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_by = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        db.Index('idx_refund_player_status', 'player_id', 'status'),
    )

    player = db.relationship('Player', foreign_keys=[player_id], backref='dropout_refunds')
    session = db.relationship('Session', backref='dropout_refunds')

    def to_dict(self):
        return {
            'id': self.id,
            'player_id': self.player_id,
            'player_name': self.player.name if self.player else None,
            'session_id': self.session_id,
            'refund_amount': self.refund_amount,
            'suggested_amount': self.suggested_amount,
            'instructions': self.instructions,
            'status': self.status,
            'processed_date': self.processed_date.isoformat() if self.processed_date else None
        }


class BirdieBank(db.Model):
    """Track birdie (shuttlecock) inventory - purchases and usage"""
    __tablename__ = 'birdie_bank'

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    transaction_type = db.Column(db.String(20), nullable=False)  # 'purchase' or 'usage'
    quantity = db.Column(db.Integer, nullable=False)  # positive for purchase, positive for usage (stored as positive, type determines direction)
    cost = db.Column(db.Float, default=0)  # cost for purchases
    notes = db.Column(db.Text)
    session_id = db.Column(db.Integer, db.ForeignKey('sessions.id'), nullable=True)  # link to session for usage

    # Audit fields
    created_by = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_by = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    session = db.relationship('Session', backref='birdie_transactions')

    def to_dict(self):
        return {
            'id': self.id,
            'date': self.date.isoformat(),
            'transaction_type': self.transaction_type,
            'quantity': self.quantity,
            'cost': self.cost,
            'notes': self.notes,
            'session_id': self.session_id
        }

    @staticmethod
    def get_current_stock():
        """Calculate current birdie stock"""
        purchases = db.session.query(db.func.sum(BirdieBank.quantity)).filter_by(transaction_type='purchase').scalar() or 0
        usage = db.session.query(db.func.sum(BirdieBank.quantity)).filter_by(transaction_type='usage').scalar() or 0
        return purchases - usage

    @staticmethod
    def get_total_spent():
        """Calculate total amount spent on birdies"""
        return db.session.query(db.func.sum(BirdieBank.cost)).filter_by(transaction_type='purchase').scalar() or 0


class ActivityLog(db.Model):
    """Log every admin and user action for audit trail"""
    __tablename__ = 'activity_logs'

    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    user_type = db.Column(db.String(20), nullable=False)  # 'admin', 'player', 'player_admin'
    user_name = db.Column(db.String(100), nullable=False)  # Display name or 'Admin'
    action = db.Column(db.String(50), nullable=False, index=True)  # e.g. 'login', 'create_session', 'update_attendance'
    entity_type = db.Column(db.String(50))  # e.g. 'session', 'player', 'payment', 'attendance'
    entity_id = db.Column(db.Integer)
    description = db.Column(db.Text, nullable=False)  # Human-readable description
    ip_address = db.Column(db.String(45))  # IPv4 or IPv6

    __table_args__ = (
        db.Index('idx_activity_log_action', 'action'),
        db.Index('idx_activity_log_ts_action', 'timestamp', 'action'),
    )


class SiteSettings(db.Model):
    """Store site-wide settings and content like guidelines"""
    __tablename__ = 'site_settings'

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(50), unique=True, nullable=False, index=True)
    value = db.Column(db.Text)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @staticmethod
    def get(key, default=None):
        """Get a setting value by key"""
        setting = SiteSettings.query.filter_by(key=key).first()
        return setting.value if setting else default

    @staticmethod
    def set(key, value):
        """Set a setting value"""
        setting = SiteSettings.query.filter_by(key=key).first()
        if setting:
            setting.value = value
        else:
            setting = SiteSettings(key=key, value=value)
            db.session.add(setting)
        db.session.commit()
        return setting


class ExternalIntegration(db.Model):
    """
    Stores external service credentials with application-level column encryption.
    All sensitive columns (url, username, password) are encrypted using Fernet
    symmetric encryption before being written to the database.
    The encryption key is derived from the app's SECRET_KEY at runtime.
    """
    __tablename__ = 'external_integrations'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)  # e.g. 'ezfacility'
    # Sensitive columns — values encrypted by _encrypt()/_decrypt() helpers
    _url_enc      = db.Column('url',            db.Text, nullable=True)
    _username_enc = db.Column('username',        db.Text, nullable=True)
    _password_enc = db.Column('password',        db.Text, nullable=True)
    _cookie_enc   = db.Column('session_cookie',  db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # ── Encrypted property accessors ──────────────────────────────────────────

    @property
    def url(self) -> str:
        return _decrypt(self._url_enc)

    @url.setter
    def url(self, value: str):
        self._url_enc = _encrypt(value)

    @property
    def username(self) -> str:
        return _decrypt(self._username_enc)

    @username.setter
    def username(self, value: str):
        self._username_enc = _encrypt(value)

    @property
    def password(self) -> str:
        return _decrypt(self._password_enc)

    @password.setter
    def password(self, value: str):
        self._password_enc = _encrypt(value)

    @property
    def session_cookie(self) -> str:
        return _decrypt(self._cookie_enc)

    @session_cookie.setter
    def session_cookie(self, value: str):
        self._cookie_enc = _encrypt(value)

    # ── Convenience class methods ─────────────────────────────────────────────

    @classmethod
    def get_or_create(cls, name: str) -> 'ExternalIntegration':
        obj = cls.query.filter_by(name=name).first()
        if not obj:
            obj = cls(name=name)
            db.session.add(obj)
        return obj

    @classmethod
    def get_credentials(cls, name: str):
        """Return (url, username, password) or (None, None, None) if not configured."""
        obj = cls.query.filter_by(name=name).first()
        if not obj:
            return None, None, None
        return obj.url, obj.username, obj.password
