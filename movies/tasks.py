from celery import shared_task
from django.core.mail import EmailMessage

from .models import Booking
from .ticket_utils import generate_ticket_pdf


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def send_booking_ticket_email_task(self, booking_id):

    booking = Booking.objects.select_related(
        "user",
        "movie",
        "theater",
        "show_schedule",
        "show_schedule__screen",
        "seat",
    ).get(id=booking_id)

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

    pdf_content = generate_ticket_pdf(booking)

    email.attach(
        f"BookMySeat_Ticket_{booking.id}.pdf",
        pdf_content,
        "application/pdf",
    )

    email.send()