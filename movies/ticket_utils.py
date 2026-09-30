from io import BytesIO
from reportlab.pdfgen import canvas


def generate_ticket_pdf(booking):
    buffer = BytesIO()

    pdf = canvas.Canvas(buffer)

    pdf.setTitle(
        f"BookMySeat Ticket - {booking.id}"
    )

    pdf.setFont("Helvetica-Bold", 20)
    pdf.drawString(180, 800, "BOOKMYSEAT")

    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(200, 770, "Movie Ticket")

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

    return buffer.getvalue()