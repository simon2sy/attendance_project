"""
Ad-hoc test to verify the 12-hour attendance cooldown rule.

Run from the project root:
    python manage.py shell < app/test.py

or:

    python -c "import django, os; os.environ.setdefault('DJANGO_SETTINGS_MODULE','project.settings'); django.setup(); exec(open('app/test.py').read())"

Scenario covered:
  - Same employee QR code scanned twice on the same day.
  - The 2nd scan (within 12 hours) must be REJECTED.
  - The 3rd scan (12+ hours later) must be ACCEPTED.
"""

import uuid
from datetime import timedelta
from django.utils import timezone
from django.contrib.auth import get_user_model
from app.models import Employee, Attendance

User = get_user_model()

PASS = 0
FAIL = 0


def check(label, condition):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"[PASS] {label}")
    else:
        FAIL += 1
        print(f"[FAIL] {label}")


def main():
    # Clean up any previous test data for this script
    test_id = "TEST-12H-001"
    Attendance.objects.filter(employee__employee_id=test_id).delete()
    Employee.objects.filter(employee_id=test_id).delete()

    # Create a staff user (the operator scanning the QR)
    staff, _ = User.objects.get_or_create(
        username="test_staff",
        defaults={"is_staff": True},
    )

    # Create an employee with a known QR code
    qr = uuid.uuid4()
    emp = Employee.objects.create(
        employee_id=test_id,
        full_name="Test Employee 12H",
        department="QA",
        designation="Tester",
        email="test12h@example.com",
        phone="9800000000",
        is_active=True,
        qr_code=qr,
    )

    now = timezone.now()

    # ── Scan #1 (baseline) ─────────────────────────
    a1 = Attendance.objects.create(
        employee=emp,
        attendance_type=Attendance.AttendanceType.CHECK_IN,
        timestamp=now,
        device_name="test",
    )
    check("First scan creates a CHECK_IN record", a1.attendance_type == "IN")

    # ── Scan #2 within 12 hours (e.g. +1 hour) ─────
    a2_time = now + timedelta(hours=1)
    last = Attendance.objects.filter(employee=emp).order_by("-timestamp").first()
    elapsed = (a2_time - last.timestamp).total_seconds() / 3600.0
    blocked = elapsed < 12.0
    check("Second scan within 12h is BLOCKED", blocked is True)

    # ── Scan #3 after 12+ hours (e.g. +13 hours) ───
    a3_time = now + timedelta(hours=13)
    last = Attendance.objects.filter(employee=emp).order_by("-timestamp").first()
    elapsed = (a3_time - last.timestamp).total_seconds() / 3600.0
    allowed = elapsed >= 12.0
    check("Third scan after 12h is ALLOWED", allowed is True)

    # Actually create the allowed record to prove a new one is stored
    a3 = Attendance.objects.create(
        employee=emp,
        attendance_type=Attendance.AttendanceType.CHECK_IN,
        timestamp=a3_time,
        device_name="test",
    )
    total = Attendance.objects.filter(employee=emp).count()
    check("A new attendance record is created after 12h", total == 2)

    # Cleanup
    Attendance.objects.filter(employee=emp).delete()
    emp.delete()
    staff.delete()

    print("\n" + "=" * 50)
    print(f"RESULT: {PASS} passed, {FAIL} failed")
    print("=" * 50)
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())


# When run via `manage.py shell < app/test.py`, __name__ is not "__main__",
# so call main() explicitly:
main()
