# attendance/urls.py

from django.urls import path
from . import views

# app_name here registers the namespace
app_name = 'app'

urlpatterns = [
    # Auth
    path('login/',   views.login_view,   name='login'),
    path('employee-login/', views.employee_login_view, name='employee_login'),
    path('signup/', views.employee_signup, name='employee_signup'),
    path('logout/',  views.logout_view,  name='logout'),

# Main pages
    path('',    views.dashboard, name='dashboard'),
    path('dashboard/', views.employee_dashboard, name='employee_dashboard'),
    path('scan/', views.scan_qr, name='scan_qr'),

    # QR display (staff only)
    path('qr/display/', views.generate_qr_image, name='qr_display'),
    path('office-qr/', views.office_qr_display, name='office_qr_display'),

    # Employee QR list (staff only)
    path('qr/employees/', views.employee_qr_list, name='employee_qr_list'),

    # AJAX endpoints
    path('api/office-scan/', views.process_office_scan, name='process_office_scan'),

    # Staff attendance overview
    path('admin-view/', views.admin_attendance_view, name='admin_attendance'),
    path(
    "employees/add/",
    views.add_employee,
    name="add_employee",
),
]
