from django.db import migrations, models


def transform_employee_to_standalone(apps, schema_editor):
    """Copy employee name/email from linked User into standalone fields."""
    Employee = apps.get_model("app", "Employee")
    for emp in Employee.objects.select_related("user").all():
        user = emp.user
        emp.full_name = (user.first_name or "") + (" " + user.last_name if user.last_name else "")
        emp.full_name = emp.full_name.strip() or user.username
        emp.email = user.email
        emp.save(update_fields=["full_name", "email"])


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0003_populate_employee_qr_codes"),
    ]

    operations = [
        migrations.AddField(
            model_name="employee",
            name="full_name",
            field=models.CharField(default="", max_length=150),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="employee",
            name="email",
            field=models.EmailField(blank=True, max_length=254),
        ),
        migrations.AddField(
            model_name="employee",
            name="phone",
            field=models.CharField(blank=True, max_length=20),
        ),
        migrations.RunPython(
            transform_employee_to_standalone,
            migrations.RunPython.noop,
        ),
        migrations.RemoveField(
            model_name="employee",
            name="user",
        ),
    ]
