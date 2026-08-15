# attendance/views.py

import json
import re
import uuid
from django.shortcuts import render, redirect, reverse
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login, authenticate, logout
from django.contrib import messages
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from django.db.models import Q
from datetime import datetime
from io import BytesIO
import base64
from .models import Employee, Attendance, OfficeQRCode, Todo
try:
    import qrcode
    from qrcode.image.pil import PilImage
    QR_AVAILABLE = True
except ImportError:
    QR_AVAILABLE = False


# ─────────────────────────────────────────────
# Shared: resolve the Employee profile for a user (or None)
# ─────────────────────────────────────────────
def linked_employee(user):
    """Return the Employee profile linked to a user, or None."""
    if user is None:
        return None
    try:
        return user.employee_profile
    except Employee.DoesNotExist:
        return None


# ─────────────────────────────────────────────
# Login — role-aware (admin/staff AND employees)
# Staff/administrators go to the admin dashboard.
# Employees (linked to an Employee profile) go to their own dashboard.
# ─────────────────────────────────────────────
def login_view(request):
    """
    Single login page. Allows:
      - staff/admin users → admin dashboard
      - employees linked to an Employee profile → employee dashboard
    Unauthenticated or unauthorised users cannot proceed.
    """
    if request.user.is_authenticated:
        if request.user.is_staff:
            return redirect('app:dashboard')
        employee = linked_employee(request.user)
        if employee is not None and employee.is_active:
            return redirect('app:employee_dashboard')
        logout(request)
        messages.error(request, 'Your account is not linked to any staff or employee role.')

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')

        if not username or not password:
            messages.error(request, 'Please enter both username and password.')
            return render(request, 'attendance/login.html')

        user = authenticate(request, username=username, password=password)

        if user is not None:
            if not user.is_active:
                messages.error(request, 'Your account has been disabled.')
                return render(request, 'attendance/login.html')

            employee = linked_employee(user)
            if user.is_staff or (employee is not None and employee.is_active):
                login(request, user)
                messages.success(
                    request,
                    f"Welcome back, {user.get_full_name() or user.username}!"
                )
                if user.is_staff:
                    next_url = request.GET.get('next', 'app:dashboard')
                else:
                    next_url = request.GET.get('next', 'app:employee_dashboard')
                return redirect(next_url)

            messages.error(
                request,
                'Your account has no staff or employee role. Contact your administrator.'
            )
        else:
            messages.error(request, 'Invalid username or password.')

    return render(request, 'attendance/login.html')


# ─────────────────────────────────────────────
# Employee login — dedicated page for employees
# ─────────────────────────────────────────────
def employee_login_view(request):
    if request.user.is_authenticated:
        if request.user.is_staff:
            return redirect('app:dashboard')
        employee = linked_employee(request.user)
        if employee is not None and employee.is_active:
            return redirect('app:employee_dashboard')
        logout(request)

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')

        if not username or not password:
            messages.error(request, 'Please enter both username and password.')
            return render(request, 'attendance/employee_login.html')

        user = authenticate(request, username=username, password=password)

        if user is not None:
            if not user.is_active:
                messages.error(request, 'Your account has been disabled.')
                return render(request, 'attendance/employee_login.html')

            employee = linked_employee(user)
            if employee is not None and employee.is_active:
                login(request, user)
                messages.success(
                    request,
                    f"Welcome back, {employee.full_name}!"
                )
                next_url = request.GET.get('next', 'app:employee_dashboard')
                return redirect(next_url)
            elif user.is_staff:
                login(request, user)
                messages.success(
                    request,
                    f"Welcome back, {user.get_full_name() or user.username}!"
                )
                return redirect('app:dashboard')
            else:
                messages.error(
                    request,
                    'No employee profile is linked to this account. Contact your administrator.'
                )
        else:
            messages.error(request, 'Invalid username or password.')

    return render(request, 'attendance/employee_login.html')


# ─────────────────────────────────────────────
# Employee signup — self-service
# Creates a User with NO staff/superuser privileges and an Employee profile.
# The new account can only reach the employee dashboard.
# ─────────────────────────────────────────────
def employee_signup(request):
    if request.user.is_authenticated:
        if request.user.is_staff:
            return redirect('app:dashboard')
        employee = linked_employee(request.user)
        if employee is not None:
            return redirect('app:employee_dashboard')
        # Authenticated but without a profile — log them out so they can sign up fresh.
        logout(request)

    if request.method == 'POST':
        form = EmployeeSignupForm(request.POST)
        if form.is_valid():
            user, employee = form.save()
            login(request, user)
            messages.success(
                request,
                f"Account created. Welcome, {employee.full_name}!"
            )
            return redirect('app:employee_dashboard')
    else:
        form = EmployeeSignupForm()

    return render(request, 'attendance/employee_signup.html', {'form': form})


# ─────────────────────────────────────────────
# Logout
# ─────────────────────────────────────────────
def logout_view(request):
    logout(request)
    messages.info(request, 'You have been logged out successfully.')
    return redirect('app:login')


# ─────────────────────────────────────────────
# Admin Dashboard
# ─────────────────────────────────────────────
@login_required(login_url='/attendance/login/')
def dashboard(request):
    if not request.user.is_staff:
        # Employees landing here are sent to their own dashboard.
        if getattr(request.user, 'employee_profile', None) is not None:
            return redirect('app:employee_dashboard')
        messages.error(request, 'Access denied. Staff only.')
        return redirect('app:login')

    # Use Nepal timezone (Asia/Kathmandu, UTC+5:45) for "today"
    today = timezone.localdate()

    total_employees = Employee.objects.filter(is_active=True).count()

    # All attendance records for today
    today_attendance = Attendance.objects.filter(timestamp__date=today)

    # Employees who have checked in today (distinct)
    present_employee_ids = today_attendance.values_list(
        'employee_id', flat=True
    ).distinct()
    present_count = present_employee_ids.count()

    # Active employees absent today
    absent_count = max(total_employees - present_count, 0)

    # Recent records across all employees
    recent_records = Attendance.objects.select_related(
        'employee'
    ).order_by('-timestamp')[:10]

    context = {
        'total_employees':      total_employees,
        'today_attendance_count': today_attendance.count(),
        'present_count':        present_count,
        'absent_count':         absent_count,
        'recent_records':       recent_records,
        'today':                today,
    }
    return render(request, 'attendance/dashboard.html', context)


# ─────────────────────────────────────────────
# Office QR Scanner Page (employee self-service only)
#   Employees scan the shared office QR code at the entrance.
#   Staff are redirected to the admin dashboard.
# ─────────────────────────────────────────────
@login_required(login_url='/attendance/login/')
def scan_qr(request):
    if request.user.is_staff:
        return redirect('app:dashboard')

    employee = linked_employee(request.user)
    if employee is None:
        messages.error(request, 'No employee profile is linked to your account.')
        return redirect('app:login')

    return render(request, 'attendance/employee_scanner.html')


# ─────────────────────────────────────────────
# Employee Dashboard (self-service)
# Shows only the logged-in employee's own info & attendance.
# ─────────────────────────────────────────────
@login_required(login_url='/attendance/login/')
def employee_dashboard(request):
    # Staff/administrators keep the admin dashboard.
    if request.user.is_staff:
        return redirect('app:dashboard')

    try:
        employee = request.user.employee_profile
    except Employee.DoesNotExist:
        return render(
            request,
            'attendance/no_profile.html',
            {'error': 'Your account is not linked to an employee profile. Please contact your administrator.'},
        )

    today = timezone.localdate()

    today_records = Attendance.objects.filter(
        employee=employee,
        timestamp__date=today,
    ).order_by('-timestamp')
    present_today = today_records.exists()
    latest_record = today_records.first()

    attendance_history = Attendance.objects.filter(
        employee=employee
    ).order_by('-timestamp')[:20]

    todos = Todo.objects.filter(employee=employee)
    pending_todos_count = todos.filter(is_completed=False).count()
    completed_todos_count = todos.filter(is_completed=True).count()

    context = {
        'employee':          employee,
        'today':             today,
        'present_today':     present_today,
        'latest_record':     latest_record,
        'attendance_history': attendance_history,
        'todos':             todos,
        'pending_todos_count': pending_todos_count,
        'completed_todos_count': completed_todos_count,
    }
    return render(request, 'attendance/employee_dashboard.html', context)


# ─────────────────────────────────────────────
# Shared helpers
# ─────────────────────────────────────────────
UUID_PATTERN = re.compile(
    r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-'
    r'[0-9a-fA-F]{4}-[0-9a-fA-F]{12}'
)


def _extract_uuid(text):
    """Extract a UUID out of arbitrary scanned text (e.g. a wrapped URL)."""
    if not text:
        return None
    m = UUID_PATTERN.search(str(text))
    if not m:
        return None
    try:
        return uuid.UUID(m.group(0))
    except ValueError:
        return None


def _client_ip(request):
    x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded:
        return x_forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '')


def _record_attendance(employee, latitude, longitude, device_name, ip_address):
    """
    EXISTING attendance validation & creation logic — the SINGLE implementation.

    • Active-employee check
    • 12-hour cooldown rule (MIN_GAP_HOURS = 12)
    • Always records a Check-In
    • Same exact success / already_done messages

    Both the staff scanner and the employee office scanner call this.
    DO NOT change these rules.
    """
    # Active check
    if not employee.is_active:
        return JsonResponse(
            {'success': False, 'message': 'This employee account is inactive.'},
            status=403
        )

    # 12-hour cooldown — allow recording again only after 12 hours.
    MIN_GAP_HOURS = 12
    now = timezone.now()

    last_record = Attendance.objects.filter(
        employee=employee
    ).order_by('-timestamp').first()

    if last_record:
        elapsed = (now - last_record.timestamp).total_seconds() / 3600.0
        if elapsed < MIN_GAP_HOURS:
            wait_hours = MIN_GAP_HOURS - elapsed
            return JsonResponse({
                'success': False,
                'already_done': True,
                'message': (
                    f'Attendance already recorded. '
                    f'Please wait {wait_hours:.1f} more hour(s).'
                ),
                'data': {
                    'employee_name':   employee.full_name,
                    'employee_id':     employee.employee_id,
                    'attendance_type': last_record.get_attendance_type_display(),
                    'timestamp':       last_record.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                }
            }, status=200)

    # Always record as Check-In
    att_type = Attendance.AttendanceType.CHECK_IN

    attendance = Attendance.objects.create(
        employee=employee,
        qr=None,
        attendance_type=att_type,
        latitude=latitude if latitude is not None else None,
        longitude=longitude if longitude is not None else None,
        device_name=str(device_name)[:150],
        ip_address=ip_address,
    )

    return JsonResponse({
        'success': True,
        'message': f'Attendance recorded successfully for {employee.full_name}!',
        'data': {
            'employee_name':   employee.full_name,
            'employee_id':     employee.employee_id,
            'attendance_type': attendance.get_attendance_type_display(),
            'timestamp':       attendance.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
        }
    })


# ─────────────────────────────────────────────
# Office QR Scan (AJAX POST, employee self-service)
#
# The employee scans the single SHARED office QR code.
# The employee is identified from the authenticated session
# (request.user.employee_profile) — NOT from any value submitted by JS.
# Attendance validation is delegated to _record_attendance().
# ─────────────────────────────────────────────
@login_required(login_url='/attendance/login/')
@require_http_methods(["POST"])
def process_office_scan(request):
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse(
            {'success': False, 'message': 'Invalid JSON payload.'},
            status=400
        )

    # Identify the employee from the authenticated session
    try:
        employee = request.user.employee_profile
    except Employee.DoesNotExist:
        return JsonResponse(
            {'success': False, 'message': 'No employee profile is linked to your account.'},
            status=403
        )

    # Validate the office QR token server-side
    qr_text = data.get('office_qr', '')
    if not qr_text:
        return JsonResponse(
            {'success': False, 'message': 'No office QR code data received.'},
            status=400
        )

    token = _extract_uuid(qr_text)
    if token is None:
        return JsonResponse(
            {'success': False, 'message': 'Invalid office QR code format.'},
            status=400
        )

    office_qr = OfficeQRCode.objects.filter(uuid=token, is_active=True).first()
    if office_qr is None or not office_qr.is_valid():
        return JsonResponse(
            {'success': False, 'message': 'Invalid or inactive office QR code.'},
            status=400
        )

    # Existing attendance validation + creation logic (12-hour rule).
    return _record_attendance(
        employee,
        data.get('latitude'),
        data.get('longitude'),
        data.get('device_name', ''),
        _client_ip(request),
    )


# ─────────────────────────────────────────────
# Employee QR List (Staff only)
# ─────────────────────────────────────────────
@login_required(login_url='/attendance/login/')
def employee_qr_list(request):
    if not request.user.is_staff:
        messages.error(request, 'Access denied. Staff only.')
        return redirect('app:login')

    employees = Employee.objects.order_by('employee_id')
    return render(request, 'attendance/employee_qr_list.html', {
        'employees': employees,
    })


# ─────────────────────────────────────────────
# Generate QR Image (Staff only)
# Supports an optional ?employee=<id> to render a
# specific employee's personal QR code.
# ─────────────────────────────────────────────
@login_required(login_url='/attendance/login/')
def generate_qr_image(request):
    if not request.user.is_staff:
        messages.error(request, 'You do not have permission to view this page.')
        return redirect('app:login')

    if not QR_AVAILABLE:
        messages.error(request, 'qrcode library not installed. Run: pip install qrcode[pil]')
        return redirect('app:dashboard')

    employee_id = request.GET.get('employee', '')

    if employee_id:
        title = "Employee QR Code"
        try:
            employee = Employee.objects.get(pk=employee_id)
        except Employee.DoesNotExist:
            messages.error(request, 'Employee not found.')
            return redirect('app:employee_qr_list')
        data_str = str(employee.qr_code)
        subtitle = employee.full_name or employee.employee_id
    else:
        # Fallback: office QR (kept for backward compatibility)
        title = "Office QR Code"
        active_qr = OfficeQRCode.objects.filter(is_active=True).first()
        if not active_qr:
            messages.warning(
                request,
                'No active QR code found. Please create one in the Django admin panel.'
            )
            return redirect('app:dashboard')
        data_str = str(active_qr.uuid)
        subtitle = active_qr.name

    # Generate QR image
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=4,
    )
    qr.add_data(data_str)
    qr.make(fit=True)

    img = qr.make_image(fill_color='black', back_color='white')
    buffer = BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)
    img_base64 = base64.b64encode(buffer.getvalue()).decode()

    return render(request, 'attendance/qr_display.html', {
        'qr_image': img_base64,
        'title':    title,
        'subtitle': subtitle,
    })


# ─────────────────────────────────────────────
# Admin — Single Office QR Code (Staff only)
# Generates / displays the SHARED office QR. Optionally rotates it.
# The QR encodes a validation URL (contains the office QR token).
# ─────────────────────────────────────────────
@login_required(login_url='/attendance/login/')
def office_qr_display(request):
    if not request.user.is_staff:
        messages.error(request, 'Access denied. Staff only.')
        return redirect('app:login')

    if not QR_AVAILABLE:
        messages.error(request, 'qrcode library not installed. Run: pip install qrcode[pil]')
        return redirect('app:dashboard')

    # Rotate → deactivate the current one and issue a fresh token.
    if request.method == 'POST':
        OfficeQRCode.objects.filter(is_active=True).update(is_active=False)
        office_qr = OfficeQRCode.objects.create(name="Main Office QR", is_active=True)
        messages.success(request, "A new office QR code has been generated. The old one is now invalid.")
    else:
        office_qr = OfficeQRCode.objects.filter(is_active=True).order_by('-created_at').first()
        if office_qr is None:
            office_qr = OfficeQRCode.objects.create(name="Main Office QR", is_active=True)

    scan_url = (
        request.build_absolute_uri(reverse('app:process_office_scan'))
        + '?office_qr=' + str(office_qr.uuid)
    )

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=4,
    )
    qr.add_data(scan_url)
    qr.make(fit=True)

    img = qr.make_image(fill_color='black', back_color='white')
    buffer = BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)
    img_base64 = base64.b64encode(buffer.getvalue()).decode()

    return render(request, 'attendance/office_qr.html', {
        'office_qr': office_qr,
        'qr_image': img_base64,
        'scan_url': scan_url,
    })


# ─────────────────────────────────────────────
# Admin — All Attendance (Staff only)
# ─────────────────────────────────────────────
# ─────────────────────────────────────────────
# Admin — All Attendance (Staff only)
# ─────────────────────────────────────────────
@login_required(login_url='/attendance/login/')
def admin_attendance_view(request):
    if not request.user.is_staff:
        messages.error(request, 'Access denied. Staff only.')
        return redirect('app:login')

    start_date = request.GET.get('start_date', '')
    end_date   = request.GET.get('end_date', '')
    search     = request.GET.get('search', '')
    att_type   = request.GET.get('type', '')

    records = Attendance.objects.select_related(
        'employee', 'qr'
    ).order_by('-timestamp')

    if search:
        records = records.filter(
            Q(employee__employee_id__icontains=search) |
            Q(employee__full_name__icontains=search) |
            Q(employee__email__icontains=search)
        )

    if start_date:
        try:
            records = records.filter(
                timestamp__date__gte=datetime.strptime(start_date, '%Y-%m-%d').date()
            )
        except ValueError:
            pass

    if end_date:
        try:
            records = records.filter(
                timestamp__date__lte=datetime.strptime(end_date, '%Y-%m-%d').date()
            )
        except ValueError:
            pass

    if att_type in ['IN', 'OUT']:
        records = records.filter(attendance_type=att_type)

    # Nepal timezone "today" for the today_checkins stat
    today = timezone.localdate()

    context = {
        'records':          records[:200],
        'total_records':    records.count(),
        'total_employees':  Employee.objects.filter(is_active=True).count(),
        'today_checkins':   Attendance.objects.filter(
            timestamp__date=today,
            attendance_type='IN'
        ).count(),
        'start_date':  start_date,
        'end_date':    end_date,
        'search':      search,
        'att_type':    att_type,
    }
    return render(request, 'attendance/admin_attendance.html', context)


from .forms import EmployeeForm, EmployeeSignupForm
@login_required(login_url='/attendance/login/')
def add_employee(request):
    if not request.user.is_staff:
        messages.error(request, "Access denied.")
        return redirect("app:login")

    if request.method == "POST":
        form = EmployeeForm(request.POST)

        if form.is_valid():
            form.save()
            messages.success(request, "Employee added successfully.")
            return redirect("app:add_employee")
    else:
        form = EmployeeForm()

    return render(
        request,
        "attendance/add_employee.html",
        {
            "form": form
        },
    )


# ─────────────────────────────────────────────
# Employee To-Do List views
# ─────────────────────────────────────────────
@login_required(login_url='/attendance/login/')
@require_http_methods(["POST"])
def add_todo(request):
    try:
        employee = request.user.employee_profile
    except Employee.DoesNotExist:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.content_type == 'application/json':
            return JsonResponse({'success': False, 'message': 'No employee profile found.'}, status=403)
        messages.error(request, 'No employee profile found.')
        return redirect('app:employee_dashboard')

    title = request.POST.get('title', '').strip()
    description = request.POST.get('description', '').strip()
    due_date = request.POST.get('due_date', '').strip() or None

    if not title:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.content_type == 'application/json':
            return JsonResponse({'success': False, 'message': 'Task title is required.'}, status=400)
        messages.error(request, 'Task title is required.')
        return redirect('app:employee_dashboard')

    todo = Todo.objects.create(
        employee=employee,
        title=title,
        description=description,
        due_date=due_date
    )

    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.content_type == 'application/json':
        return JsonResponse({
            'success': True,
            'message': 'Task added successfully!',
            'todo': {
                'id': todo.id,
                'title': todo.title,
                'description': todo.description,
                'is_completed': todo.is_completed,
                'due_date': todo.due_date.strftime('%Y-%m-%d') if todo.due_date else None,
                'created_at': todo.created_at.strftime('%Y-%m-%d %H:%M'),
            }
        })

    messages.success(request, 'Task added successfully!')
    return redirect('app:employee_dashboard')


@login_required(login_url='/attendance/login/')
@require_http_methods(["POST"])
def toggle_todo(request, todo_id):
    try:
        employee = request.user.employee_profile
        todo = Todo.objects.get(pk=todo_id, employee=employee)
    except (Employee.DoesNotExist, Todo.DoesNotExist):
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'message': 'Task not found.'}, status=404)
        messages.error(request, 'Task not found.')
        return redirect('app:employee_dashboard')

    todo.is_completed = not todo.is_completed
    todo.save()

    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.content_type == 'application/json':
        return JsonResponse({
            'success': True,
            'is_completed': todo.is_completed,
            'message': f"Task marked as {'completed' if todo.is_completed else 'pending'}."
        })

    messages.success(request, f"Task marked as {'completed' if todo.is_completed else 'pending'}.")
    return redirect('app:employee_dashboard')


@login_required(login_url='/attendance/login/')
@require_http_methods(["POST"])
def delete_todo(request, todo_id):
    try:
        employee = request.user.employee_profile
        todo = Todo.objects.get(pk=todo_id, employee=employee)
    except (Employee.DoesNotExist, Todo.DoesNotExist):
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'message': 'Task not found.'}, status=404)
        messages.error(request, 'Task not found.')
        return redirect('app:employee_dashboard')

    todo.delete()

    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.content_type == 'application/json':
        return JsonResponse({
            'success': True,
            'message': 'Task deleted successfully.'
        })

    messages.success(request, 'Task deleted successfully.')
    return redirect('app:employee_dashboard')

