# Data migration: assign a unique QR code to every existing employee.

import uuid
from django.db import migrations


def populate_qr_codes(apps, schema_editor):
    Employee = apps.get_model("app", "Employee")
    for emp in Employee.objects.all():
        emp.qr_code = uuid.uuid4()
        emp.save(update_fields=["qr_code"])


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0002_employee_qr_code_alter_attendance_qr"),
    ]

    operations = [
        migrations.RunPython(populate_qr_codes),
    ]
