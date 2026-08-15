import json
from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from django.contrib.auth import get_user_model

from app.models import Employee, Attendance, OfficeQRCode

User = get_user_model()


class OfficeQRAttendanceTests(TestCase):
    """End-to-end tests for the employee login + shared office QR workflow."""

    def setUp(self):
        self.password = "testpass123"

        # Staff / admin
        self.staff = User.objects.create_user(
            username="admin", password=self.password, is_staff=True, is_superuser=True
        )

        # Employee A (non-staff, has an employee profile)
        self.user_a = User.objects.create_user(
            username="emp_a", password=self.password, is_staff=False
        )
        self.emp_a = Employee.objects.create(
            user=self.user_a,
            full_name="Employee A",
            department="IT",
            designation="Engineer",
            is_active=True,
        )

        # Employee B (linked to a different employee)
        self.user_b = User.objects.create_user(
            username="emp_b", password=self.password, is_staff=False
        )
        self.emp_b = Employee.objects.create(
            user=self.user_b,
            full_name="Employee B",
            department="HR",
            designation="Manager",
            is_active=True,
        )

        # A single, active shared office QR
        self.office_qr = OfficeQRCode.objects.create(
            name="Main Office QR", is_active=True
        )
        self.office_token = str(self.office_qr.uuid)

    # ── helpers ──────────────────────────────────────────────
    def office_scan(self, token=None, extra_payload=None, as_user=None):
        payload = {"office_qr": token if token is not None else self.office_token}
        if extra_payload:
            payload.update(extra_payload)
        if as_user is None:
            self.client.login(username="emp_a", password=self.password)
        else:
            self.client.login(username=as_user, password=self.password)
        return self.client.post(
            reverse("app:process_office_scan"),
            data=json.dumps(payload),
            content_type="application/json",
        )

    def _last(self, employee):
        return Attendance.objects.filter(employee=employee).order_by("-timestamp").first()

    # ── 1. Authentication ─────────────────────────────────────
    def test_valid_employee_login_redirects_to_dashboard(self):
        ok = self.client.login(username="emp_a", password=self.password)
        self.assertTrue(ok)
        r = self.client.get(reverse("app:employee_dashboard"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, self.emp_a.full_name)

    def test_invalid_employee_login_fails(self):
        r = self.client.post(
            reverse("app:employee_login"),
            {"username": "emp_a", "password": "wrongpassword"},
        )
        self.assertFalse(r.wsgi_request.user.is_authenticated)

    def test_unauthenticated_cannot_access_employee_dashboard(self):
        r = self.client.get(reverse("app:employee_dashboard"))
        self.assertIn(r.status_code, (301, 302))

    def test_unauthenticated_cannot_record_attendance(self):
        r = self.client.post(
            reverse("app:process_office_scan"),
            data=json.dumps({"office_qr": self.office_token}),
            content_type="application/json",
        )
        # @login_required redirects a browser hit; the endpoint is protected.
        self.assertIn(r.status_code, (301, 302))
        self.assertEqual(Attendance.objects.count(), 0)
# ── 3. Existing attendance rules preserved ────────────────
    def test_first_valid_scan_succeeds(self):
        r = self.office_scan()
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["success"])
        att = Attendance.objects.get()
        self.assertEqual(att.attendance_type, Attendance.AttendanceType.CHECK_IN)

    def test_second_scan_within_12h_rejected(self):
        self.office_scan()
        r = self.office_scan()
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertFalse(data["success"])
        self.assertTrue(data["already_done"])
        # No duplicate record created.
        self.assertEqual(Attendance.objects.filter(employee=self.emp_a).count(), 1)

    def test_scan_after_12h_allowed(self):
        self.office_scan()
        first = self._last(self.emp_a)
        # Simulate that this record happened 13 hours ago.
        Attendance.objects.filter(pk=first.pk).update(
            timestamp=timezone.now() - timedelta(hours=13)
        )
        r = self.office_scan()
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["success"])
        self.assertEqual(Attendance.objects.filter(employee=self.emp_a).count(), 2)

    # ── 4. Security / identification ──────────────────────────
    def test_attendance_marked_for_logged_in_employee(self):
        r = self.office_scan(as_user="emp_a")
        self.assertTrue(r.json()["success"])
        att = Attendance.objects.get()
        self.assertEqual(att.employee, self.emp_a)

    def test_cannot_record_for_another_employee_via_id_submission(self):
        # Attacker sends Employee B's employee_id; the server must ignore it.
        payload = {"employee_id": self.emp_b.employee_id}
        r = self.office_scan(extra_payload=payload, as_user="emp_a")
        self.assertTrue(r.json()["success"])
        att = Attendance.objects.get()
        self.assertEqual(att.employee, self.emp_a)  # still employee A
        self.assertNotEqual(att.employee, self.emp_b)

    # ── 5. Dashboard ownership ────────────────────────────────
    def test_employee_dashboard_shows_own_attendance_only(self):
        # B records via office scan; A should NOT see B's record.
        self.office_scan(as_user="emp_b")
        self.client.login(username="emp_a", password=self.password)
        r = self.client.get(reverse("app:employee_dashboard"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, self.emp_a.full_name)
        self.assertNotContains(r, self.emp_b.full_name)

    def test_unapproved_user_with_no_profile_blocked(self):
        User.objects.create_user(username="nobody", password=self.password)
        self.client.login(username="nobody", password=self.password)
        r = self.client.post(
            reverse("app:process_office_scan"),
            data=json.dumps({"office_qr": self.office_token}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 403)
        self.assertEqual(Attendance.objects.count(), 0)

    def test_office_qr_admin_page_is_staff_only(self):
        self.client.login(username="emp_a", password=self.password)
        r = self.client.get(reverse("app:office_qr_display"))
        self.assertIn(r.status_code, (301, 302))

        self.client.login(username="admin", password=self.password)
        r = self.client.get(reverse("app:office_qr_display"))
        self.assertEqual(r.status_code, 200)

    def test_employee_scanner_page_renders(self):
        self.client.login(username="emp_a", password=self.password)
        r = self.client.get(reverse("app:scan_qr"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Scan Office QR Code")

# ── 6. Employee signup ───────────────────────────────────
    def signup(self, **overrides):
        data = {
            "username": "new_emp",
            "email": "",
            "full_name": "New Employee",
            "department": "Sales",
            "designation": "Associate",
            "phone": "9800000001",
            "password1": "Signup-Pass-123",
            "password2": "Signup-Pass-123",
        }
        data.update(overrides)
        return self.client.post(reverse("app:employee_signup"), data)

    def test_signup_page_accessible_unauthenticated(self):
        r = self.client.get(reverse("app:employee_signup"))
        self.assertEqual(r.status_code, 200)

    def test_signup_creates_non_privileged_account(self):
        r = self.signup()
        self.assertEqual(r.status_code, 302)
        emp = Employee.objects.get(full_name="New Employee")
        user = emp.user
        # Configurational powers must NOT be granted.
        self.assertIsNone(getattr(user, "_perm_cache", None))
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertTrue(user.is_active)
        # Auto employee id generated and linked.
        self.assertTrue(emp.employee_id.startswith("EMP"))
        # New signups cannot use the admin/staff views.
        r2 = self.client.get(reverse("app:office_qr_display"))
        self.assertIn(r2.status_code, (301, 302))

    def test_signup_user_redirected_to_employee_dashboard(self):
        r = self.signup()
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.url, reverse("app:employee_dashboard"))
        r2 = self.client.get(reverse("app:employee_dashboard"))
        self.assertEqual(r2.status_code, 200)
        self.assertContains(r2, "New Employee")

    def test_signup_duplicate_username_rejected(self):
        self.signup()
        self.client.logout()
        r = self.signup()  # same username again
        self.assertContains(r, "already exists")
        self.assertEqual(
            User.objects.filter(username="new_emp").count(), 1
        )

    def test_signup_password_mismatch_rejected(self):
        r = self.signup(password2="Different-123")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "The two password fields did not match.")
        self.assertEqual(Employee.objects.filter(full_name="New Employee").count(), 0)
    def test_login_pages_render(self):
        r = self.client.get(reverse("app:login"))
        self.assertEqual(r.status_code, 200)
        r = self.client.get(reverse("app:employee_login"))
        self.assertEqual(r.status_code, 200)

    def test_office_scan_rejected_by_wrong_inactive_qr(self):
        self.office_qr.is_active = False
        self.office_qr.save()
        r = self.office_scan()
        self.assertEqual(r.status_code, 400)
        self.assertEqual(Attendance.objects.count(), 0)

    # ── 2. QR validation ──────────────────────────────────────
    def test_correct_office_qr_accepted(self):
        r = self.office_scan(extra_payload={"device_name": "phone"})
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertTrue(data["success"])
        self.assertEqual(Attendance.objects.count(), 1)

    def test_invalid_office_qr_rejected(self):
        r = self.office_scan(token="00000000-0000-0000-0000-000000000000")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(Attendance.objects.count(), 0)

    def test_old_employee_personal_qr_not_required(self):
        # The private employee QR (uuid) is no longer what the employee scans.
        r = self.office_scan(token=str(self.emp_a.qr_code))
        self.assertEqual(r.status_code, 400)  # not a valid office QR
        self.assertEqual(Attendance.objects.count(), 0)