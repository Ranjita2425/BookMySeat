from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from django.contrib import messages
from .forms import UserRegisterForm, UserUpdateForm, ProfileUpdateForm, LocationUpdateForm
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate
from django.contrib.auth.decorators import login_required
from movies.models import Movie, Booking
from reportlab.pdfgen import canvas
from django.http import HttpResponse
from datetime import datetime
from django.utils import timezone
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.db import transaction
import razorpay,uuid
from movies.tasks import send_booking_ticket_email_task
# ============================================================
# HOME
# ============================================================
def home(request):
    movies = Movie.objects.filter(
        is_trending=True
    ).prefetch_related(
        "posters"
    ).order_by(
        "-release_date"
    )[:6]

    return render(
        request,
        "home.html",
        { "movies": movies}
    )

# ============================================================
# REGISTER
# ============================================================

def register(request):
    if request.method == "POST":
        form = UserRegisterForm(
            request.POST
        )
        if form.is_valid():
            form.save()
            username = form.cleaned_data.get(
                "username"
            )
            password = form.cleaned_data.get(
                "password1"
            )
            user = authenticate(
                username=username,
                password=password
            )
            login(request, user)

            return redirect("profile")
    else:
        form = UserRegisterForm()
    return render(
        request,
        "users/register.html",
        {"form": form}
    )

# ============================================================
# LOGIN
# ============================================================

def login_view(request):
    if request.method == "POST":
        form = AuthenticationForm(
            request,data=request.POST
        )
        if form.is_valid():
            user = form.get_user()
            login(
                request,user
            )

            return redirect("/")
    else:
        form = AuthenticationForm()

    return render(
        request,
        "users/login.html",
        {
            "form": form
        }
    )

# ============================================================
# PROFILE
# ============================================================

@login_required
def profile(request):
    bookings = Booking.objects.filter(
        user=request.user
    ).select_related(
        "movie",
        "theater",
        "seat",
        "show_schedule",
        "show_schedule__screen"
    )

    # ========================================================
    # AUTOMATICALLY MARK COMPLETED SHOWS
    # ========================================================
    now = timezone.now()
    for booking in bookings:
        if (
            booking.booking_status == "Confirmed"
            and booking.payment_status == "Success"
            and booking.show_schedule
        ):
            show_end = timezone.make_aware(
                datetime.combine(
                    booking.show_schedule.show_date,
                    booking.show_schedule.end_time
                )
            )
            if show_end <= now:
                booking.booking_status = "Completed"
                booking.save(
                    update_fields=[
                        "booking_status"
                    ]
                )
    # ========================================================
    # UPDATE PROFILE
    # ========================================================

    if request.method == "POST":
        u_form = UserUpdateForm(
            request.POST,
            instance=request.user
        )

        location_form = LocationUpdateForm(
            request.POST,
            instance=request.user.profile
        )

        if u_form.is_valid() and location_form.is_valid():
            u_form.save()
            location_form.save()
            return redirect(
                "profile"
            )
    else:
        u_form = UserUpdateForm(
            instance=request.user
        )
        location_form = LocationUpdateForm(
            instance=request.user.profile
        )

    return render(
        request,
        "users/profile.html",
        {
            "u_form": u_form,"location_form": location_form,  "bookings": bookings
        }
    )
# ============================================================
# RESET PASSWORD
# ============================================================

@login_required
def reset_password(request):
    if request.method == "POST":
        form = PasswordChangeForm(
            user=request.user,
            data=request.POST
        )
        if form.is_valid():
            form.save()
            return redirect(
                "login"
            )

    else:

        form = PasswordChangeForm(
            user=request.user
        )
    return render(
        request,
        "users/reset_password.html",
        {"form": form}
    )

@login_required
def upi_payment(request, booking_id):

    booking = get_object_or_404(
        Booking,
        id=booking_id,
        user=request.user
    )

    # Get all pending seats for this same booking/show
    bookings = Booking.objects.filter(
        user=request.user,
        movie=booking.movie,
        theater=booking.theater,
        show_schedule=booking.show_schedule,
        booking_status="Pending",
        payment_status="Pending"
    ).select_related(
        "seat",
        "movie",
        "theater",
        "show_schedule",
        "show_schedule__screen"
    )

    if not bookings.exists():

        if booking.payment_status == "Success":
            return redirect(
                "booking_confirmation",
                booking_id=booking.id
            )

        messages.error(
            request,
            "No pending bookings found."
        )

        return redirect("profile")

    # Check whether reservation has expired
    if booking.reservation_expires_at:

        if booking.reservation_expires_at <= timezone.now():

            bookings.update(
                booking_status="Cancelled",
                payment_status="Failed",
                reservation_expires_at=None
            )

            messages.error(
                request,
                "Your seat reservation has expired. Please book again."
            )

            return redirect("profile")

    # Calculate total
    total_amount = sum(
        item.total_amount
        for item in bookings
    )

    # ========================================================
    # POST - PAYMENT
    # ========================================================

    if request.method == "POST":

        # ====================================================
        # CUSTOM UPI DEMO PAYMENT
        # ====================================================

        upi_id = request.POST.get("upi_id", "").strip()

        if upi_id:

            # Basic UPI ID validation
            if "@" not in upi_id or upi_id.startswith("@") or upi_id.endswith("@"):

                messages.error(
                    request,
                    "Please enter a valid UPI ID."
                )

                return redirect(
                    "upi_payment",
                    booking_id=booking.id
                )

            # Generate demo payment reference
            payment_reference = (
                "UPI-DEMO-" +
                uuid.uuid4().hex[:12].upper()
            )

            with transaction.atomic():

                bookings.update(
                    payment_status="Success",
                    booking_status="Confirmed",
                    payment_reference=payment_reference,
                    reservation_expires_at=None
                )

            # Send ticket email asynchronously
            send_booking_ticket_email_task.delay(
                booking.id
            )

            messages.success(
                request,
                "UPI payment successful! Your booking is confirmed."
            )

            return redirect(
                "booking_confirmation",
                booking_id=booking.id
            )

        # ====================================================
        # RAZORPAY PAYMENT
        # ====================================================

        payment_id = request.POST.get(
            "razorpay_payment_id"
        )

        order_id = request.POST.get(
            "razorpay_order_id"
        )

        signature = request.POST.get(
            "razorpay_signature"
        )

        if payment_id and order_id and signature:

            try:

                client = razorpay.Client(
                    auth=(
                        settings.RAZORPAY_KEY_ID,
                        settings.RAZORPAY_KEY_SECRET
                    )
                )

                client.utility.verify_payment_signature({
                    "razorpay_payment_id": payment_id,
                    "razorpay_order_id": order_id,
                    "razorpay_signature": signature
                })

                with transaction.atomic():

                    bookings.update(
                        payment_status="Success",
                        booking_status="Confirmed",
                        payment_reference=payment_id,
                        reservation_expires_at=None
                    )

                send_booking_ticket_email_task.delay(
                    booking.id
                )

                messages.success(
                    request,
                    "Payment successful! All your seats are confirmed."
                )

                return redirect(
                    "booking_confirmation",
                    booking_id=booking.id
                )

            except razorpay.errors.SignatureVerificationError:

                messages.error(
                    request,
                    "Payment verification failed."
                )

                return redirect(
                    "upi_payment",
                    booking_id=booking.id
                )

            except Exception:

                messages.error(
                    request,
                    "Payment could not be verified. Please try again."
                )

                return redirect(
                    "upi_payment",
                    booking_id=booking.id
                )

        # No valid payment data
        messages.error(
            request,
            "Please enter a UPI ID or complete the Razorpay payment."
        )

        return redirect(
            "upi_payment",
            booking_id=booking.id
        )

    # ========================================================
    # GET - PAYMENT PAGE
    # ========================================================

    client = razorpay.Client(
        auth=(
            settings.RAZORPAY_KEY_ID,
            settings.RAZORPAY_KEY_SECRET
        )
    )

    razorpay_order = client.order.create({
        "amount": int(total_amount * 100),
        "currency": "INR",
        "receipt": f"booking_{booking.id}",
        "payment_capture": 1
    })

    return render(
        request,
        "users/upi_payment.html",
        {
            "booking": booking,
            "bookings": bookings,
            "total_amount": total_amount,
            "razorpay_key_id": settings.RAZORPAY_KEY_ID,
            "razorpay_order_id": razorpay_order["id"],
            "razorpay_amount": int(total_amount * 100),
        }
    )

# ============================================================
# CANCEL BOOKING
# ============================================================

@login_required
def cancel_booking(request, booking_id):

    booking = get_object_or_404(
        Booking,
        id=booking_id,
        user=request.user
    )

    if booking.booking_status == "Cancelled":
        messages.info(
            request,
            "This booking is already cancelled."
        )

        return redirect(
            "profile"
        )
    booking.booking_status = "Cancelled"
    if booking.payment_status == "Success":
        booking.payment_status = "Failed"
    booking.save()
    messages.success(
        request,
        "Your booking has been cancelled successfully."
    )
    return redirect(
        "profile"
    )


# ============================================================
# BOOKING TICKET
# ============================================================

@login_required
def booking_ticket(request, booking_id):
    booking = get_object_or_404(
        Booking,
        id=booking_id,
        user=request.user
    )
    # Get all confirmed/paid bookings for the same show
    bookings = Booking.objects.filter(
        user=request.user,
        movie=booking.movie,
        theater=booking.theater,
        show_schedule=booking.show_schedule,
        payment_status="Success",
        booking_status__in=[
            "Confirmed",
            "Completed"
        ]
    ).select_related(
        "seat",
        "movie",
        "theater",
        "show_schedule",
        "show_schedule__screen"
    ).order_by(
        "seat__seat_number"
    )

    # Calculate total for all seats
    total_amount = sum(
        item.total_amount
        for item in bookings
    )

    return render(
        request,
        "users/booking_ticket.html",
        {
            "booking": booking,
            "bookings": bookings,
            "total_amount": total_amount,
        }
    )


# ============================================================
# DOWNLOAD TICKET
# ============================================================

@login_required
def download_ticket(request, booking_id):
    booking = get_object_or_404(
        Booking,
        id=booking_id,
        user=request.user
    )
    # Get all confirmed/paid bookings for the same show
    bookings = Booking.objects.filter(
        user=request.user,
        movie=booking.movie,
        theater=booking.theater,
        show_schedule=booking.show_schedule,
        payment_status="Success",
        booking_status__in=[
            "Confirmed",
            "Completed"
        ]
    ).select_related(
        "seat",
        "movie",
        "theater",
        "show_schedule",
        "show_schedule__screen"
    ).order_by(
        "seat__seat_number"
    )

    # Calculate combined total
    total_amount = sum(
        item.total_amount
        for item in bookings
    )

    response = HttpResponse(
        content_type="application/pdf"
    )

    response["Content-Disposition"] = (
        f'attachment; '
        f'filename="BookMySeat_Ticket_{booking.id}.pdf"'
    )

    pdf = canvas.Canvas(response)

    pdf.setTitle("BookMySeat Ticket")

    # =========================
    # HEADER
    # =========================

    pdf.drawString(
        200,
        800,
        "BOOKMYSEAT TICKET"
    )

    pdf.drawString(
        100,
        760,
        f"Booking ID: #{booking.id}"
    )

    pdf.drawString(
        100,
        730,
        f"Movie: {booking.movie.name}"
    )

    pdf.drawString(
        100,
        700,
        f"Theater: {booking.theater.theater_name}"
    )

    pdf.drawString(
        100,
        670,
        f"Screen: "
        f"{booking.show_schedule.screen.screen_name}"
    )

    # =========================
    # SEATS
    # =========================

    pdf.drawString(
        100,
        640,
        "Selected Seats:"
    )

    y_position = 620

    for item in bookings:

        pdf.drawString(
            120,
            y_position,
            f"- {item.seat.seat_number}"
        )

        y_position -= 20

    # =========================
    # SHOW DETAILS
    # =========================

    pdf.drawString(
        100,
        y_position - 10,
        f"Date: {booking.show_schedule.show_date}"
    )

    pdf.drawString(
        100,
        y_position - 40,
        f"Time: "
        f"{booking.show_schedule.start_time} - "
        f"{booking.show_schedule.end_time}"
    )

    # =========================
    # TOTAL
    # =========================

    pdf.drawString(
        100,
        y_position - 70,
        f"Total Amount: Rs. {total_amount}"
    )

    pdf.drawString(
        100,
        y_position - 100,
        f"Booking Status: "
        f"{booking.booking_status}"
    )

    pdf.drawString(
        100,
        y_position - 130,
        f"Payment Status: "
        f"{booking.payment_status}"
    )

    pdf.drawString(
        100,
        y_position - 170,
        "Thank you for booking with BookMySeat!"
    )

    pdf.save()

    return response

# ============================================================
# BOOKING CONFIRMATION
# ============================================================
@login_required
def booking_confirmation(request, booking_id):

    booking = get_object_or_404(
        Booking,
        id=booking_id,
        user=request.user
    )

    bookings = Booking.objects.filter(
        user=request.user,
        movie=booking.movie,
        theater=booking.theater,
        show_schedule=booking.show_schedule,
        payment_status="Success",
        booking_status__in=["Confirmed", "Completed"]
    ).select_related(
        "seat",
        "show_schedule__screen"
    ).order_by("seat__seat_number")

    total_amount = sum(item.total_amount for item in bookings)

    return render(
        request,
        "users/booking_confirmation.html",
        {
            "booking": booking,
            "bookings": bookings,
            "total_amount": total_amount,
        }
    )