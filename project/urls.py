# project/urls.py

from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView

urlpatterns = [
    path('admin/', admin.site.urls),

    # ✅ namespace declared INSIDE the app's urls.py via app_name
    # so just include without namespace= here
    path('attendance/', include('app.urls')),

    # ✅ Root redirect — use RedirectView, NOT a lambda with reverse()
    # because lambda runs before URLs are fully loaded
    path('', RedirectView.as_view(url='/attendance/', permanent=False)),
]