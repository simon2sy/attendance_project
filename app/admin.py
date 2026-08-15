import uuid
from django.contrib import admin
from django.contrib import messages
from django.utils.html import format_html
from .models import Employee, Attendance, OfficeQRCode, Todo


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = (
        "employee_id",
        "full_name",
        "department",
        "designation",
        "is_active",
        "qr_code",
    )

    search_fields = (
        "employee_id",
        "full_name",
        "email",
    )

    list_filter = (
        "department",
        "designation",
        "is_active",
    )

    readonly_fields = (
        "employee_id",
        "qr_code",
    )

    actions = ("regenerate_qr",)

    def regenerate_qr(self, request, queryset):
        updated = 0
        for emp in queryset:
            emp.qr_code = uuid.uuid4()
            emp.save(update_fields=["qr_code"])
            updated += 1
        self.message_user(
            request,
            f"QR code regenerated for {updated} employee(s).",
            level=messages.SUCCESS,
        )

    regenerate_qr.short_description = "Regenerate QR code for selected employees"

    def qr_code_display(self, obj):
        return format_html("<code>{}</code>", obj.qr_code)

    qr_code_display.short_description = "QR Code"


@admin.register(OfficeQRCode)
class OfficeQRCodeAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "uuid",
        "is_active",
        "created_at",
        "expires_at",
    )

    list_filter = (
        "is_active",
    )

    readonly_fields = (
        "uuid",
        "created_at",
    )


@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = (
        "employee",
        "attendance_type",
        "timestamp",
        "device_name",
    )

    list_filter = (
        "attendance_type",
        "timestamp",
    )

    search_fields = (
        "employee__employee_id",
        "employee__full_name",
        "employee__email",
    )

    readonly_fields = (
        "timestamp",
    )

    date_hierarchy = "timestamp"

    list_select_related = (
        "employee",
        "qr",
    )


@admin.register(Todo)
class TodoAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "employee",
        "is_completed",
        "due_date",
        "created_at",
    )
    list_filter = (
        "is_completed",
        "due_date",
    )
    search_fields = (
        "title",
        "description",
        "employee__full_name",
        "employee__employee_id",
    )

