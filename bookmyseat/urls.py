from movies import views
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
urlpatterns = [
    path('admin/', admin.site.urls),
    path('users/', include('users.urls')),
    path('',include('users.urls')),
    path('movies/', include('movies.urls')),
    path("admin-dashboard/", views.admin_dashboard, name="admin_dashboard"),
    path(
    "upi-payment/<int:booking_id>/",
    views.upi_payment,
    name="upi_payment"
),
path(
    "booking-history/",
    views.booking_history,
    name="booking_history"
),
path(
    "booking/<int:booking_id>/test-email/",
    views.test_booking_email,
    name="test_booking_email"
),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)