# TODO: Admin-Operated Attendance Scanner

1. [x] Views: rewrite app/views.py — remove employee-login logic, make dashboard admin stats, staff-only scan/process
2. [x] URLs: remove history route; keep staff routes
3. [x] Templates: rewrite scan_qr.html (no prefill, staff scanner)
4. [x] Templates: rewrite dashboard.html (admin stats dashboard)
5. [x] Templates: gate nav links in base.html to staff
6. [x] Templates: update login.html subtitle (admin-only)
7. [x] Verify with manage.py check

# 12-Hour Cooldown Rule

1. [x] Views: process_qr_scan enforces a 12-hour gap between the same employee's attendance records
2. [x] If within 12 hours → returns "already_done" with the remaining wait time
3. [x] If 12+ hours have passed → a new CHECK_IN record is created
4. [x] test.py: verifies first scan (IN), block within 12h, allow after 12h, and new record created

# Auto-Generated Employee ID

1. [x] Models: employee_id is now auto-generated (EMP0001, EMP0002, ...) via save()/generate_employee_id()
2. [x] Models: employee_id set to blank=True, editable=False (no manual typing)
3. [x] Admin: employee_id shown as read-only in the admin panel
4. [x] Migration 0006 applied (alter employee_id)
5. [x] Verified: creating an Employee without an employee_id auto-generates EMP0001
6. [x] manage.py check passes with no issues

# Nepal Timezone (Asia/Kathmandu, UTC+5:45)

1. [x] settings.py: TIME_ZONE = 'Asia/Kathmandu' (already set), USE_TZ = True
2. [x] Views: dashboard and admin attendance use timezone.localdate() for "today" (Nepal time)
3. [x] Templates: admin_attendance.html, dashboard.html, history.html now use `|localtime` filter to display all timestamps in Nepal time
4. [x] Verified: stored UTC 2026-08-05 10:40 → Nepal local 2026-08-05 16:25
5. [x] Note: system clock set to Aug 5, 2026 (machine date); timezone conversion is correct
