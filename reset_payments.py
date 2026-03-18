"""Reset all payment data to clean slate.
Run with DATABASE_URL set to target the Render database:
  DATABASE_URL=postgresql://... python3 reset_payments.py
"""
from app import app, db
from models import Payment, DropoutRefund, Attendance

with app.app_context():
    # Count before
    pay_count = Payment.query.count()
    refund_count = DropoutRefund.query.count()

    # Delete all payments
    Payment.query.delete()

    # Delete all dropout refunds
    DropoutRefund.query.delete()

    # Reset all attendance payment_status to unpaid
    Attendance.query.update({Attendance.payment_status: 'unpaid'})

    db.session.commit()

    print(f'Deleted {pay_count} payment(s)')
    print(f'Deleted {refund_count} dropout refund(s)')
    print(f'Reset all attendance payment_status to unpaid')
    print('Done — clean slate!')
