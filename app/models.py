from django.db import models
from django.conf import settings
from django.utils import timezone
import uuid


class Employee(models.Model):
    # Employee linked to a Django user (login-based), plus standalone fields.
    employee_id = models.CharField(
        max_length=20,
        unique=True,
        blank=True,     # auto-generated if not provided
        editable=False,  # hidden from manual entry
    )
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="employee_profile",
        null=True,
        blank=True,
    )
    full_name = models.CharField(max_length=150)
    department = models.CharField(max_length=100, blank=True)
    designation = models.CharField(max_length=100, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    is_active = models.BooleanField(default=True)

    # Unique QR code per employee
    qr_code = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)

    @classmethod
    def generate_employee_id(cls):
        """
        Auto-generate the next sequential employee ID.
        Format: EMP0001, EMP0002, ...
        """
        prefix = "EMP"
        digit_width = 4
        last = (
            cls.objects.filter(employee_id__startswith=prefix)
            .order_by("-employee_id")
            .first()
        )
        if last and last.employee_id[len(prefix):].isdigit():
            next_num = int(last.employee_id[len(prefix):]) + 1
        else:
            next_num = 1
        return f"{prefix}{next_num:0{digit_width}d}"

    def save(self, *args, **kwargs):
        # Auto-generate employee_id if not provided
        if not self.employee_id:
            self.employee_id = self.generate_employee_id()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.employee_id} - {self.full_name}"


class OfficeQRCode(models.Model):
    """
    Only one active QR should exist.
    QR can be rotated daily or whenever required.
    """

    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    name = models.CharField(max_length=100, default="Main Office QR")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    def is_valid(self):
        if not self.is_active:
            return False

        if self.expires_at and timezone.now() > self.expires_at:
            return False

        return True

    def __str__(self):
        return self.name


class Attendance(models.Model):

    class AttendanceType(models.TextChoices):
        CHECK_IN = "IN", "Check In"
        CHECK_OUT = "OUT", "Check Out"

    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name="attendances"
    )

    qr = models.ForeignKey(
        OfficeQRCode,
        on_delete=models.SET_NULL,
        related_name="attendances",
        null=True,
        blank=True
    )

    attendance_type = models.CharField(
        max_length=3,
        choices=AttendanceType.choices
    )

    timestamp = models.DateTimeField(auto_now_add=True)

    latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True
    )

    longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True
    )

    device_name = models.CharField(max_length=150, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ["-timestamp"]

        indexes = [
            models.Index(fields=["employee", "timestamp"]),
            models.Index(fields=["attendance_type"]),
        ]

    def __str__(self):
        return f"{self.employee} - {self.attendance_type} - {self.timestamp}"


class Todo(models.Model):
    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name="todos"
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    is_completed = models.BooleanField(default=False)
    due_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["is_completed", "-created_at"]

    def __str__(self):
        return f"{self.employee.full_name} - {self.title}"

