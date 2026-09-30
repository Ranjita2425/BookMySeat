from datetime import datetime
from io import BytesIO
from itertools import count
import uuid
from django.core import paginator
from django.core.paginator import Paginator
import qrcode
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, models, transaction
from django.http import HttpResponse, request
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from .forms import ReviewForm
from urllib.parse import urlparse, parse_qs
from django.contrib.auth.models import User
from .models import Movie, MovieLanguage, Screen, ShowSchedule, Theater, Seat, Booking, Review, MovieCategory
from django.db import IntegrityError, models, transaction
from django.db.models.functions import TruncDate, TruncMonth, TruncYear
from django.http import HttpResponse
from django.db import models
from django.core.mail import EmailMessage
from .tasks import send_booking_ticket_email_task
from django.core.exceptions import PermissionDenied
from io import BytesIO
from reportlab.pdfgen import canvas
from django.http import HttpResponse

# ============================================================
# MOVIE LIST
# ============================================================
def movie_list(request):
    search_query = request.GET.get("search")

    if search_query:
       movies = Movie.objects.filter(
        name__icontains=search_query
    ).select_related(
        "category",
        "language"
    ).prefetch_related(
        "cast_members",
        "posters"
    )
    else:
        movies = Movie.objects.select_related(
            "category",
            "language"
        ).prefetch_related(
            "cast_members",
            "posters"
        )

    movie_count = movies.count()
    category_id = request.GET.get("category")

    if category_id:
        movies = movies.filter(category_id=category_id)

    language_id = request.GET.get("language")

    if language_id:
        movies = movies.filter(language_id=language_id)

    release_date = request.GET.get("release_date")

    if release_date:
        movies = movies.filter(release_date=release_date)

    show_time = request.GET.get("show_time")

    if show_time:
        movies = movies.filter(
            shows__start_time=show_time,
            shows__is_active=True
        ).distinct()

    city = request.GET.get("city")

    if city:
        movies = movies.filter(
            shows__screen__theater__city__icontains=city
        ).distinct()

    theater_id = request.GET.get("theater")

    if theater_id:
        movies = movies.filter(
            shows__screen__theater_id=theater_id
        ).distinct()

    rating = request.GET.get("rating")

    if rating:
        movies = movies.filter(
            average_rating__gte=rating
        )

    movie_count = movies.count()

    sort = request.GET.get("sort")

    if sort == "newest":
        movies = movies.order_by("-release_date")

    elif sort == "rating":
        movies = movies.order_by("-average_rating")

    elif sort == "popular":
        movies = movies.annotate(
            booking_count=models.Count("booking")
        ).order_by("-booking_count")

    elif sort == "price_low":
        movies = movies.annotate(
            min_ticket_price=models.Min("shows__ticket_price")
        ).order_by("min_ticket_price")

    elif sort == "price_high":
        movies = movies.annotate(
            min_ticket_price=models.Min("shows__ticket_price")
        ).order_by("-min_ticket_price")

    paginator = Paginator(movies, 6)

    page_number = request.GET.get("page")

    movies = paginator.get_page(page_number)
    categories = MovieCategory.objects.all()
    languages = MovieLanguage.objects.all()
    theaters = Theater.objects.only(
        "id",
        "theater_name",
        "city"
    )
    recommended_movies = Movie.objects.none()

    if request.user.is_authenticated:
        booked_movie_ids = Booking.objects.filter(
            user=request.user,
            booking_status__in=["Confirmed", "Completed"]
        ).values_list("movie_id", flat=True)

        booked_categories = Movie.objects.filter(
            id__in=booked_movie_ids
        ).values_list("category_id", flat=True)

        recommended_movies = Movie.objects.filter(
            category_id__in=booked_categories
        ).exclude(
            id__in=booked_movie_ids
        ).distinct()[:6]

    recently_viewed_movies = Movie.objects.none()

    recently_viewed_ids = request.session.get("recently_viewed", [])

    if recently_viewed_ids:
        recently_viewed_movies = Movie.objects.filter(
            id__in=recently_viewed_ids
        ).select_related(
            "category",
            "language"
        ).prefetch_related(
            "posters"
        )

    recently_viewed_movies = sorted(
        recently_viewed_movies,
        key=lambda movie: recently_viewed_ids.index(movie.id)
    )

    return render(
        request,
        "movies/movie_list.html",
        {
            "movies": movies,
            "movie_count": movie_count,
            "categories": categories,
            "languages": languages,
            "theaters": theaters,
            "recommended_movies": recommended_movies,
            "recently_viewed_movies": recently_viewed_movies
        }
    )

# ============================================================
# THEATER LIST
# ============================================================
def theater_list(request, movie_id):

    movie = get_object_or_404(
        Movie,
        id=movie_id
    )
    recently_viewed = request.session.get("recently_viewed", [])

    recently_viewed = [
        movie_id for movie_id in recently_viewed
        if movie_id != movie.id
    ]

    recently_viewed.insert(0, movie.id)

    request.session["recently_viewed"] = recently_viewed[:6]

    # Store recently viewed movies
    recently_viewed = request.session.get("recently_viewed", [])

    if movie.id in recently_viewed:
        recently_viewed.remove(movie.id)

    recently_viewed.insert(0, movie.id)
    recently_viewed = recently_viewed[:6]

    request.session["recently_viewed"] = recently_viewed

    youtube_embed_url = None

    if movie.trailer_url:
        parsed_url = urlparse(movie.trailer_url)

        if parsed_url.hostname in [
            "youtube.com",
            "www.youtube.com",
            "m.youtube.com"
        ]:
            video_id = parse_qs(
                parsed_url.query
            ).get("v", [None])[0]

            if video_id:
                youtube_embed_url = (
                    f"https://www.youtube.com/embed/{video_id}"
                )
        elif parsed_url.hostname == "youtu.be":
            video_id = parsed_url.path.strip("/")
            if video_id:
                youtube_embed_url = (
                    f"https://www.youtube.com/embed/{video_id}"
                )
    schedules = ShowSchedule.objects.filter(
        movie=movie,
        is_active=True
    ).select_related(
        "screen",
        "screen__theater"
    )

    reviews = Review.objects.filter(
        movie=movie,
        is_reported=False
    ).select_related(
        "user"
    ).order_by(
        "-created_at"
    )

    # Similar movies based on category OR language
    similar_movies = Movie.objects.filter(
        category=movie.category
    ).exclude(
        id=movie.id
    )

    if movie.language:
        similar_movies = similar_movies.filter(
            language=movie.language
        )

    similar_movies = similar_movies[:6]
    # Trending movies
    trending_movies = Movie.objects.filter(
        is_trending=True
    ).exclude(
        id=movie.id
    ).order_by(
        "-created_at"
    )[:6]
# Recently released movies
    recent_movies = Movie.objects.filter(
        release_date__isnull=False
    ).exclude(
        id=movie.id
    ).order_by(
        "-release_date"
    )[:6]

    recently_viewed_movies = Movie.objects.filter(
        id__in=recently_viewed
    ).exclude(
        id=movie.id
    )

    return render(
        request,
        "movies/theater_list.html",
        {
            "movie": movie,
            "schedules": schedules,
            "reviews": reviews,
            "similar_movies": similar_movies,
            "trending_movies": trending_movies,
            "recent_movies": recent_movies,
            "youtube_embed_url": youtube_embed_url,
            "recently_viewed_movies": recently_viewed_movies,
        }
    )

def movie_details(request, movie_id):

    movie = get_object_or_404(
        Movie,
        id=movie_id
    )
    # Store recently viewed movies
    recently_viewed = request.session.get("recently_viewed", [])

    if movie.id in recently_viewed:
        recently_viewed.remove(movie.id)

    recently_viewed.insert(0, movie.id)

    # Keep only the latest 6 movies
    recently_viewed = recently_viewed[:6]

    request.session["recently_viewed"] = recently_viewed

    reviews = Review.objects.filter(
        movie=movie,
        is_reported=False
    ).select_related(
        "user"
    ).order_by(
        "-created_at"
    )

    similar_movies = Movie.objects.filter(
        category=movie.category,
        language=movie.language
    ).exclude(
        id=movie.id
    )[:6]

    trending_movies = Movie.objects.filter(
        is_trending=True
    ).exclude(
        id=movie.id
    )[:6]

    recent_movies = Movie.objects.filter(
        release_date__isnull=False
    ).exclude(
        id=movie.id
    ).order_by(
        "-release_date"
    )[:6]
    recently_viewed_movies = Movie.objects.filter(
        id__in=recently_viewed
    ).exclude(
        id=movie.id
    )

    return render(
        request,
        "movies/movie_details.html",
        {
            "movie": movie,
            "reviews": reviews,
            "similar_movies": similar_movies,
            "trending_movies": trending_movies,
            "recent_movies": recent_movies,
            "recently_viewed_movies": recently_viewed_movies,
        }
    )

def release_expired_reservations():
    Booking.objects.filter(
        booking_status="Pending",
        payment_status="Pending",
        reservation_expires_at__lte=timezone.now()
    ).update(
        booking_status="Cancelled",
        payment_status="Failed",
        reservation_expires_at=None
    )

@login_required(login_url="/login/")
def change_seats(request, booking_id):

    booking = get_object_or_404(
        Booking,
        id=booking_id,
        user=request.user,
        booking_status="Pending",
        payment_status="Pending"
    )

    # Release the current pending seat reservations
    Booking.objects.filter(
        user=request.user,
        show_schedule=booking.show_schedule,
        booking_status="Pending",
        payment_status="Pending"
    ).update(
        booking_status="Cancelled",
        payment_status="Failed",
        reservation_expires_at=None
    )

    messages.info(
        request,
        "Your previous seat selection has been released. Please select your new seats."
    )

    return redirect(
        "book_seats",
        theater_id=booking.theater.id
    )

# ============================================================
# BOOK SEATS
# ============================================================

@login_required(login_url="/login/")
def book_seats(request, theater_id):
    release_expired_reservations()
    theater = get_object_or_404(
        Theater,
        id=theater_id
    )
    schedules = ShowSchedule.objects.filter(
        screen__theater=theater,
        is_active=True
    ).select_related(
        "movie",
        "screen"
    )
    schedule_id = request.GET.get("show_schedule")
    selected_schedule = None
    seats = Seat.objects.none()
    booked_seat_ids = []
    reserved_seat_ids = []

    # ========================================================
    # GET REQUEST
    # ========================================================

    if schedule_id:
        selected_schedule = get_object_or_404(
            ShowSchedule,
            id=schedule_id,
            screen__theater=theater,
            is_active=True
        )
        seats = Seat.objects.filter(
            screen=selected_schedule.screen,
            is_active=True
        )
        booked_seat_ids = Booking.objects.filter(
            show_schedule=selected_schedule,
            booking_status__in=[
                "Confirmed",
                "Completed"
            ]
        ).values_list(
            "seat_id",
            flat=True
        )

        reserved_seat_ids = Booking.objects.filter(
            show_schedule=selected_schedule,
            booking_status="Pending",
            payment_status="Pending",
            reservation_expires_at__gt=timezone.now()
        ).values_list(
            "seat_id",
            flat=True
        )

    # ========================================================
    # POST REQUEST
    # ========================================================

    if request.method == "POST":
        schedule_id = request.POST.get(
            "show_schedule"
        )
        if not schedule_id:
            messages.error(
                request,
                "Please select a show."
            )
            return redirect(
                "theater_list",
                movie_id=request.POST.get("movie_id")
            )
        selected_schedule = get_object_or_404(
            ShowSchedule,
            id=schedule_id,
            screen__theater=theater,
            is_active=True
        )

        # ====================================================
        # CHECK WHETHER SHOW HAS STARTED
        # ====================================================
        show_start = timezone.make_aware(
            datetime.combine(
                selected_schedule.show_date,
                selected_schedule.start_time
            )
        )
        if show_start <= timezone.now():
            seats = Seat.objects.filter(
                screen=selected_schedule.screen,
                is_active=True
            )
            booked_seat_ids = Booking.objects.filter(
                show_schedule=selected_schedule
            ).filter(
                models.Q(
                    booking_status__in=[
                        "Confirmed",
                        "Completed"
                    ]
                )
                |
                models.Q(
                    booking_status="Pending",
                    payment_status="Pending",
                    reservation_expires_at__gt=timezone.now()
                )
            ).values_list(
                "seat_id",
                flat=True
        )
            return render(
                request,
                "movies/seat_selection.html",
                {
                    "theater": theater,
                    "schedules": schedules,
                    "selected_schedule": selected_schedule,
                    "seats": seats,
                    "booked_seat_ids": booked_seat_ids,
                    "reserved_seat_ids": reserved_seat_ids,
                    "error": (
                        "This show has already started "
                        "and cannot be booked."
                    )
                }
            )

        # ====================================================
        # GET AVAILABLE SEATS
        # ====================================================

        seats = Seat.objects.filter(
            screen=selected_schedule.screen,
            is_active=True
        )
        booked_seat_ids = Booking.objects.filter(
            show_schedule=selected_schedule,
            booking_status__in=[
                "Pending",
                "Confirmed",
                "Completed"
            ]
        ).values_list(
            "seat_id",
            flat=True
        )

        # ====================================================
        # SELECTED SEATS
        # ====================================================

        selected_seats = request.POST.getlist(
            "seats"
        )
        if not selected_seats:
            return render(
                request,
                "movies/seat_selection.html",
                {
                    "theater": theater,
                    "schedules": schedules,
                    "selected_schedule": selected_schedule,
                    "seats": seats,
                    "booked_seat_ids": booked_seat_ids,
                    "error": "Please select at least one seat."
                }
            )

        # ====================================================
        # TOTAL AMOUNT
        # ====================================================
        total_amount = (
            selected_schedule.ticket_price
            * len(selected_seats)
        )
        error_seats = []
        created_bookings = []

        # ====================================================
        # CREATE BOOKINGS
        # ====================================================

        for seat_id in selected_seats:
            try:
                with transaction.atomic():
                    seat = Seat.objects.select_for_update().get(
                        id=seat_id,
                        screen=selected_schedule.screen,
                        is_active=True
                    )
                    already_booked = Booking.objects.filter(
                        seat=seat,
                        show_schedule=selected_schedule
                    ).filter(
                        models.Q(
                            booking_status__in=[
                                "Confirmed",
                                "Completed"
                            ]
                        )
                        |
                        models.Q(
                            booking_status="Pending",
                            payment_status="Pending",
                            reservation_expires_at__gt=timezone.now()
                        )
                    ).exists()
                    if already_booked:
                        error_seats.append(
                            seat.seat_number
                        )
                        continue

                    booking = Booking.objects.create(
                        user=request.user,
                        seat=seat,
                        movie=selected_schedule.movie,
                        theater=theater,
                        show_schedule=selected_schedule,
                        booking_status="Pending",
                        payment_status="Pending",
                        total_amount=selected_schedule.ticket_price,
                        reservation_expires_at=(
                            timezone.now()
                            + timezone.timedelta(minutes=2)
                        )
                    )
                    created_bookings.append(booking)
            except IntegrityError:
                error_seats.append(
                    seat.seat_number
                )

        # ====================================================
        # BOOKING ERROR
        # ====================================================

        if error_seats:
            booked_seat_ids = Booking.objects.filter(
                show_schedule=selected_schedule
            ).filter(
                models.Q(
                    booking_status__in=[
                        "Confirmed",
                        "Completed"
                    ]
                )
                |
                models.Q(
                    booking_status="Pending",
                    payment_status="Pending",
                    reservation_expires_at__gt=timezone.now()
                )
            ).values_list(
                "seat_id",
                flat=True
            )
            return render(
                request,
                "movies/seat_selection.html",
                {
                    "theater": theater,
                    "schedules": schedules,
                    "selected_schedule": selected_schedule,
                    "seats": seats,
                    "booked_seat_ids": booked_seat_ids,
                    "error": (
                        "These seats are already booked: "
                        + ", ".join(error_seats)
                    )
                }
            )

        # ====================================================
        # SUCCESS
        # ====================================================

        if created_bookings:
            messages.success(
                request,
                "Your seats have been selected. "
                "Please complete payment."
            )
            return redirect(
                "pay_booking",
                booking_id=created_bookings[0].id
            )
        messages.error(
            request,
            "Unable to create the booking."
        )
        return redirect(
            "theater_list",
            movie_id=selected_schedule.movie.id
        )

    # ========================================================
    # FINAL GET RESPONSE
    # ========================================================
    return render(
        request,
        "movies/seat_selection.html",
        {
            "theater": theater,
            "schedules": schedules,
            "selected_schedule": selected_schedule,
            "seats": seats,
            "booked_seat_ids": booked_seat_ids,
        }
    )

def send_booking_ticket_email(booking):
    subject = f"BookMySeat Ticket - {booking.movie.name}"

    message = f"""
Hello {booking.user.username},

Your BookMySeat booking has been confirmed.

Movie: {booking.movie.name}
Theater: {booking.theater.theater_name}
Screen: {booking.show_schedule.screen.screen_name}
Seat: {booking.seat.seat_number}
Date: {booking.show_schedule.show_date}
Time: {booking.show_schedule.start_time}
Amount: ₹{booking.total_amount}

Payment Reference: {booking.payment_reference or "Not available"}

Thank you for booking with BookMySeat!
"""

    email = EmailMessage(
        subject,
        message,
        None,
        [booking.user.email],
    )

    # Attach PDF ticket
    from django.urls import reverse
    from django.test import RequestFactory

    request = RequestFactory().get(
        reverse("download_ticket", args=[booking.id])
    )

    response = download_ticket(request, booking.id)

    if response.status_code == 200:
        email.attach(
            f"BookMySeat_Ticket_{booking.id}.pdf",
            response.content,
            "application/pdf"
        )

    email.send()

@login_required
def test_booking_email(request, booking_id):
    booking = get_object_or_404(
        Booking,
        id=booking_id,
        user=request.user
    )

    send_booking_ticket_email_task.delay(booking.id)

    messages.success(
        request,
        "Test ticket email has been queued successfully."
    )

    return redirect(
        "booking_confirmation",
        booking_id=booking.id
    )
# ============================================================
# SUBMIT REVIEW
# ============================================================

@login_required
def submit_review(request, movie_id):
    movie = get_object_or_404(
        Movie,
        id=movie_id
    )

    completed_booking = Booking.objects.filter(
        user=request.user,
        movie=movie,
        booking_status="Completed"
    ).first()


    if not completed_booking:

        messages.error(
            request,
            "You can only submit a review for a movie you have watched."
        )

        return redirect("movie_list")


    existing_review = Review.objects.filter(
        user=request.user,
        movie=movie
    ).first()


    if existing_review:

        messages.info(
            request,
            "You have already submitted a review for this movie."
        )

        return redirect("movie_list")
    if request.method == "POST":
        form = ReviewForm(
            request.POST
        )
        if form.is_valid():
            review = form.save(
                commit=False
            )
            review.user = request.user
            review.movie = movie
            review.booking = completed_booking
            review.is_verified_viewer = True
            review.save()
            messages.success(
                request,
                "Your review has been submitted successfully."
            )
            return redirect(
                "movie_list"
            )
    else:
        form = ReviewForm()
    return render(
        request,
        "movies/submit_review.html",
        {
            "form": form,
            "movie": movie
        }
    )

@login_required
def edit_review(request, review_id):

    review = get_object_or_404(
        Review,
        id=review_id,
        user=request.user
    )

    if request.method == "POST":

        form = ReviewForm(
            request.POST,
            instance=review
        )

        if form.is_valid():

            form.save()

            messages.success(
                request,
                "Your review has been updated successfully."
            )

            return redirect(
                "theater_list",
                movie_id=review.movie.id
            )

    else:

        form = ReviewForm(
            instance=review
        )

    return render(
        request,
        "movies/edit_review.html",
        {
            "form": form,
            "movie": review.movie,
            "review": review,
        }
    )

@login_required
def report_review(request, review_id):

    review = get_object_or_404(
        Review,
        id=review_id
    )

    if request.method == "POST":

        review.is_reported = True
        review.save(update_fields=["is_reported"])

        messages.success(
            request,
            "Review reported successfully."
        )

    return redirect(
        "theater_list",
        movie_id=review.movie.id
    )
# ============================================================
# PAYMENT
# ===========================================================
@login_required
def pay_booking(request, booking_id):
    booking = get_object_or_404(
        Booking,
        id=booking_id,
        user=request.user
    )

        # Reservation expired
    if (
        booking.booking_status == "Pending"
        and booking.payment_status == "Pending"
        and booking.reservation_expires_at
        and booking.reservation_expires_at <= timezone.now()
    ):
        Booking.objects.filter(
            user=request.user,
            show_schedule=booking.show_schedule,
            booking_status="Pending",
            payment_status="Pending"
        ).update(
            booking_status="Cancelled",
            payment_status="Failed",
            reservation_expires_at=None
        )

        messages.error(
            request,
            "Your seat reservation has expired. Please select your seats again."
        )

        return redirect(
            "theater_list",
            movie_id=booking.movie.id
        )
    # Already cancelled
    if booking.booking_status == "Cancelled":
        messages.error(
            request,
            "This booking has been cancelled and cannot be paid for."
        )
        return redirect("profile")

    # Already paid
    if booking.payment_status == "Success":
        return redirect(
            "booking_confirmation",
            booking_id=booking.id
        )

    # Find all pending bookings for this show
    related_bookings = Booking.objects.filter(
        user=request.user,
        movie=booking.movie,
        theater=booking.theater,
        show_schedule=booking.show_schedule,
        booking_status="Pending",
        payment_status="Pending"
    )

    if not related_bookings.exists():
        messages.error(
            request,
            "No pending bookings found."
        )
        return redirect(
            "profile"
        )

    total_amount = sum(
        item.total_amount
        for item in related_bookings
    )

    # ========================================================
    # GET - SHOW PAYMENT PAGE
    # ========================================================

    if request.method == "GET":
        return render(
            request,
            "users/payment.html",
            {
                "booking": booking,
                "bookings": related_bookings,
                "total_amount": total_amount,
            }
        )

    # ========================================================
    # POST - PROCESS PAYMENT
    # ========================================================
    if request.method == "POST":
        payment_result = request.POST.get(
            "payment_result",
            "success"
        )

        # ====================================================
        # PAYMENT FAILED
        # ====================================================
        if payment_result == "failed":
            related_bookings.update(
                payment_status="Failed",
                booking_status="Cancelled"
            )
            messages.error(
                request,
                "Payment failed. Your seats have been released."
            )
            return redirect(
                "profile"
            )

        # ====================================================
        # PAYMENT SUCCESS
        # ====================================================
        payment_reference = "UPI-" + uuid.uuid4().hex[:12].upper()

        related_bookings.update(
            payment_status="Success",
            booking_status="Confirmed",
            payment_reference=payment_reference
        )
        send_booking_ticket_email_task.delay(booking.id)
        messages.success(
            request,
            "Payment successful! Your booking is confirmed."
        )
        return redirect(
            "booking_confirmation",
            booking_id=booking.id
        )


@login_required(login_url="/login/")
def upi_payment(request, booking_id):

    booking = get_object_or_404(
        Booking,
        id=booking_id,
        user=request.user,
        booking_status="Pending",
        payment_status="Pending"
    )

    related_bookings = Booking.objects.filter(
        user=request.user,
        show_schedule=booking.show_schedule,
        booking_status="Pending",
        payment_status="Pending"
    )

    if request.method == "POST":

        payment_reference = "UPI-" + uuid.uuid4().hex[:12].upper()

        related_bookings.update(
            payment_status="Success",
            booking_status="Confirmed",
            payment_reference=payment_reference,
            reservation_expires_at=None
        )
        send_booking_ticket_email_task.delay(booking.id)
        messages.success(
            request,
            "Payment successful! Your booking is confirmed."
        )

        return redirect(
            "booking_confirmation",
            booking_id=booking.id
        )

    total_amount = related_bookings.aggregate(
        total=models.Sum("total_amount")
    )["total"] or 0

    return render(
        request,
        "movies/upi_payment.html",
        {
            "booking": booking,
            "bookings": related_bookings,
            "total_amount": total_amount,
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
    if request.method != "POST":
        return redirect(
            "profile"
        )
    if booking.booking_status != "Confirmed":
        messages.error(
            request,
            "Only confirmed bookings can be cancelled."
        )
        return redirect(
            "profile"
        )
    booking.booking_status = "Cancelled"
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
# BOOKING QR CODE
# ============================================================

@login_required
def booking_qr(request, booking_id):

    booking = get_object_or_404(
        Booking,
        id=booking_id,
        user=request.user
    )

    # Get all bookings for the same show
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
    ).select_related("seat").order_by(
        "seat__seat_number"
    )

    # Get all seat numbers
    seats = ", ".join(
        item.seat.seat_number
        for item in bookings
    )

    # Calculate total amount
    total_amount = sum(
        item.total_amount
        for item in bookings
    )

    qr_data = request.build_absolute_uri(
    f"/booking/{booking.id}/verify/"
    )

    qr = qrcode.make(qr_data)

    buffer = BytesIO()

    qr.save(
        buffer,
        format="PNG"
    )

    return HttpResponse(
        buffer.getvalue(),
        content_type="image/png"
    )

@login_required(login_url="/login/")
def booking_history(request):
    bookings = Booking.objects.filter(
        user=request.user
    ).select_related(
        "movie",
        "theater",
        "show_schedule",
        "show_schedule__screen",
        "seat"
    ).order_by("-booked_at")

    return render(
        request,
        "movies/booking_history.html",
        {
            "bookings": bookings
        }
    )

@login_required
def verify_booking(request, booking_id):

    booking = get_object_or_404(
        Booking,
        id=booking_id
    )

    bookings = Booking.objects.filter(
        user=booking.user,
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

    total_amount = sum(
        item.total_amount
        for item in bookings
    )

    return render(
        request,
        "movies/verify_booking.html",
        {
            "booking": booking,
            "bookings": bookings,
            "total_amount": total_amount,
        }
    )
@login_required(login_url="/login/")
def admin_dashboard(request):

    if not request.user.is_staff:
        raise PermissionDenied
    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")

    booking_filter = Booking.objects.filter(
        booking_status__in=["Confirmed", "Completed"],
        payment_status="Success"
    )

    if start_date:
        booking_filter = booking_filter.filter(
            booked_at__date__gte=start_date
        )

    if end_date:
        booking_filter = booking_filter.filter(
            booked_at__date__lte=end_date
    )

    total_bookings = booking_filter.count()

    total_revenue = booking_filter.aggregate(
        total=models.Sum("total_amount")
    )["total"] or 0

    users_filter = User.objects.all()

    if start_date:
        users_filter = users_filter.filter(
            date_joined__date__gte=start_date
    )

    if end_date:
        users_filter = users_filter.filter(
            date_joined__date__lte=end_date
        )
    

    total_users = users_filter.count()
    cancelled_bookings = Booking.objects.filter(
        booking_status="Cancelled"
    )

    if start_date:
        cancelled_bookings = cancelled_bookings.filter(
            booked_at__date__gte=start_date
        )

    if end_date:
        cancelled_bookings = cancelled_bookings.filter(
            booked_at__date__lte=end_date
        )

    cancelled_count = cancelled_bookings.count()
    refunded_count = Booking.objects.filter(
        payment_status="Failed",
        booking_status="Cancelled"
    ).count()

    most_booked_movies = booking_filter.values(
        "movie__name"
    ).annotate(
        booking_count=models.Count("id")
    ).order_by("-booking_count")[:5]

    top_theaters = booking_filter.values(
        "theater__theater_name"
    ).annotate(
        booking_count=models.Count("id")
    ).order_by("-booking_count")[:5]

    daily_revenue = booking_filter.annotate(
        day=TruncDate("booked_at")
    ).values("day").annotate(
        revenue=models.Sum("total_amount")
    ).order_by("-day")[:7]


    monthly_revenue = booking_filter.annotate(
        month=TruncMonth("booked_at")
    ).values("month").annotate(
        revenue=models.Sum("total_amount")
    ).order_by("-month")[:12]

    yearly_revenue = booking_filter.annotate(
        year=TruncYear("booked_at")
    ).values("year").annotate(
        revenue=models.Sum("total_amount")
    ).order_by("-year")

    peak_hours = booking_filter.annotate(
        hour=models.functions.ExtractHour("booked_at")
    ).values(
        "hour"
    ).annotate(
        booking_count=models.Count("id")
    ).order_by("-booking_count")[:5]

    popular_show_times = booking_filter.values(
        "show_schedule__start_time"
    ).annotate(
        booking_count=models.Count("id")
    ).order_by("-booking_count")[:5]

    occupancy_data = []
    screens = Screen.objects.select_related("theater").only(
        "id",
        "screen_name",
        "total_seats",
        "theater__id",
        "theater__theater_name"
    )

    for screen in screens:

        booked_seats = booking_filter.filter(
            show_schedule__screen_id=screen.id
        ).count()

        occupancy_percentage = (
            round((booked_seats / screen.total_seats) * 100, 2)
            if screen.total_seats > 0
            else 0
        )

        occupancy_data.append({
            "theater": screen.theater,
            "screen_name": screen.screen_name,
            "booked_seats": booked_seats,
            "total_seats": screen.total_seats,
            "occupancy_percentage": occupancy_percentage,
        })

    user_growth = users_filter.annotate(
        day=TruncDate("date_joined")
    ).values(
        "day"
    ).annotate(
        user_count=models.Count("id")
    ).order_by("-day")[:7]   

    booking_status_summary = Booking.objects.values(
        "booking_status"
    ).annotate(
        count=models.Count("id")
    ).order_by("booking_status")

    average_ticket_price = booking_filter.aggregate(
        average=models.Avg("total_amount")
    )["average"] or 0

    total_seats_booked = booking_filter.count()
    total_movies = Movie.objects.count()

    return render(
        request,
        "movies/admin_dashboard.html",
        {
            "total_bookings": total_bookings,
            "total_revenue": total_revenue,
            "total_users": total_users,
            "cancelled_count": cancelled_count,
            "refunded_count": refunded_count,
            "most_booked_movies": most_booked_movies,
            "top_theaters": top_theaters,
            "daily_revenue": daily_revenue,
            "monthly_revenue": monthly_revenue,
            "yearly_revenue": yearly_revenue,
            "peak_hours": peak_hours,
            "occupancy_data": occupancy_data,
            "user_growth": user_growth,
            "booking_status_summary": booking_status_summary,
            "average_ticket_price": average_ticket_price,
            "total_seats_booked": total_seats_booked,
            "total_movies": total_movies,
        }
    )

def export_bookings_csv(request):
    if not request.user.is_staff:
        return redirect("home")

    import csv

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="bookings.csv"'

    writer = csv.writer(response)

    writer.writerow([
        "Booking ID",
        "Movie",
        "Theater",
        "Screen",
        "Seat",
        "Amount",
        "Booking Status",
        "Payment Status",
        "Payment Reference",
        "Booked At"
    ])

    bookings = Booking.objects.select_related(
        "movie",
        "theater",
        "show_schedule__screen",
        "seat"
    ).order_by("-booked_at")

    for booking in bookings:
        writer.writerow([
            booking.id,
            booking.movie.name,
            booking.theater.theater_name,
            booking.show_schedule.screen.screen_name,
            booking.seat.seat_number,
            booking.total_amount,
            booking.booking_status,
            booking.payment_status,
            booking.payment_reference or "",
            booking.booked_at,
        ])

    return response


def download_ticket(request, booking_id):
    booking = get_object_or_404(
        Booking,
        id=booking_id,
        user=request.user
    )

    buffer = BytesIO()

    pdf = canvas.Canvas(buffer)

    pdf.setTitle(
        f"BookMySeat Ticket - {booking.id}"
    )

    pdf.setFont("Helvetica-Bold", 20)
    pdf.drawString(
        180,
        800,
        "BOOKMYSEAT"
    )

    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(
        200,
        770,
        "Movie Ticket"
    )

    pdf.setFont("Helvetica", 11)

    y = 720

    ticket_details = [
        f"Booking ID: {booking.id}",
        f"Movie: {booking.movie.name}",
        f"Theater: {booking.theater.theater_name}",
        f"Screen: {booking.show_schedule.screen.screen_name}",
        f"Seat: {booking.seat.seat_number}",
        f"Date: {booking.show_schedule.show_date}",
        f"Time: {booking.show_schedule.start_time}",
        f"Amount: Rs. {booking.total_amount}",
        f"Payment Status: {booking.payment_status}",
        f"Payment Reference: {booking.payment_reference or 'Not available'}",
    ]

    for detail in ticket_details:
        pdf.drawString(80, y, detail)
        y -= 30

    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(
        80,
        y - 20,
        "Thank you for booking with BookMySeat!"
    )

    pdf.save()

    buffer.seek(0)

    response = HttpResponse(
        buffer.getvalue(),
        content_type="application/pdf"
    )

    response[
        "Content-Disposition"
    ] = (
        f'attachment; filename="BookMySeat_Ticket_{booking.id}.pdf"'
    )

    return response