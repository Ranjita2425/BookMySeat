from django.urls import path
from . import views
from .views import submit_review


urlpatterns=[
    path('',views.movie_list,name='movie_list'),
    path('<int:movie_id>/theaters',views.theater_list,name='theater_list'),
    path('theater/<int:theater_id>/seats/book/',views.book_seats,name='book_seats'),
    path('movie/<int:movie_id>/review/',submit_review,name='submit_review'),
    path(
    "booking/<int:booking_id>/verify/",
    views.verify_booking,
    name="verify_booking"
),
path(
    "review/<int:review_id>/edit/",
    views.edit_review,
    name="edit_review"
),
path(
    "review/<int:review_id>/report/",
    views.report_review,
    name="report_review"
),
path(
    "booking/<int:booking_id>/change-seats/",
    views.change_seats,
    name="change_seats"
),
path(
    "admin-dashboard/",
    views.admin_dashboard,
    name="admin_dashboard"
),
path(
    "admin-dashboard/export/",
    views.export_bookings_csv,
    name="export_bookings_csv"
),

]