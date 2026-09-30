from django.urls import path
from . import views
from .views import (
    register,
    login_view,
    profile,
    reset_password,
    home,
)
from django.contrib.auth import views as auth_views

from movies.views import booking_qr, pay_booking


class CustomLogoutView(auth_views.LogoutView):

    def get(self, request, *args, **kwargs):
        return self.post(request, *args, **kwargs)


urlpatterns = [

    # ================= HOME =================

    path(
        "",
        home,
        name="home"
    ),

    # ================= AUTH =================

    path(
        "register/",
        register,
        name="register"
    ),

    path(
        "login/",
        login_view,
        name="login"
    ),

    path(
        "logout/",
        auth_views.LogoutView.as_view(
            template_name="users/logout.html"
        ),
        name="logout"
    ),

    # ================= PROFILE =================

    path(
        "profile/",
        profile,
        name="profile"
    ),

    path(
        "reset-password/",
        reset_password,
        name="reset-password"
    ),

    # ================= PASSWORD RESET =================

    path(
        "password-reset/",
        auth_views.PasswordResetView.as_view(
            template_name="users/reset_password.html"
        ),
        name="password_reset"
    ),

    path(
        "password-reset/done/",
        auth_views.PasswordResetDoneView.as_view(
            template_name="users/password_reset_done.html"
        ),
        name="password_reset_done"
    ),

    path(
        "password-reset-confirm/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="users/password_reset_confirm.html"
        ),
        name="password_reset_confirm"
    ),

    path(
        "password-reset-complete/",
        auth_views.PasswordResetCompleteView.as_view(
            template_name="users/password_reset_complete.html"
        ),
        name="password_reset_complete"
    ),

    # ================= PAYMENT =================

    path(
        "pay/<int:booking_id>/",
        pay_booking,
        name="pay_booking"
    ),

    # ================= CANCEL BOOKING =================

    path(
        "cancel/<int:booking_id>/",
        views.cancel_booking,
        name="cancel_booking"
    ),

    # ================= TICKET =================

    path(
        "booking/<int:booking_id>/ticket/",
        views.booking_ticket,
        name="booking_ticket"
    ),

    # ================= QR CODE =================

    path(
        "booking/<int:booking_id>/qr/",
        booking_qr,
        name="booking_qr"
    ),

    # ================= DOWNLOAD TICKET =================

    path(
        "booking/<int:booking_id>/download/",
        views.download_ticket,
        name="download_ticket"
    ),

    # ================= CONFIRMATION =================

    path(
        "booking/<int:booking_id>/confirmation/",
        views.booking_confirmation,
        name="booking_confirmation"
    ),
    path(
    "upi-payment/<int:booking_id>/",
    views.upi_payment,
    name="upi_payment"
),

]