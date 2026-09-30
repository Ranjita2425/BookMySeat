from django.db import models
from django.contrib.auth.models import User 
from django.db.models import Avg
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver


class MovieCategory(models.Model):
    category_name = models.CharField(max_length=80, unique=True)
    category_description = models.TextField(blank=True)

    def __str__(self):
        return self.category_name

class MovieLanguage(models.Model):
    language_name = models.CharField(max_length=50, unique=True)
    language_code = models.CharField(max_length=10, unique=True)

    def __str__(self):
        return self.language_name
    
class CastMember(models.Model):
    full_name = models.CharField(max_length=120)
    role_name = models.CharField(max_length=120, blank=True)
    profile_image = models.ImageField(upload_to='cast_profiles/', blank=True, null=True)
    biography = models.TextField(blank=True)

    def __str__(self):
        return self.full_name

class Movie(models.Model):
    name = models.CharField(max_length=255, unique=True)
    category = models.ForeignKey(
    MovieCategory,
    on_delete=models.SET_NULL,
    null=True,
    blank=True,
    related_name="movies"
)

    language = models.ForeignKey(
        MovieLanguage,
        on_delete=models.SET_NULL,
        null=True,
        related_name="movies"
    )

    cast_members = models.ManyToManyField(
        CastMember,
        related_name="movies",
        blank=True
    )

    description = models.TextField()

    duration = models.PositiveIntegerField(
        help_text="Duration in minutes"
    )

    release_date = models.DateField()

    age_certificate = models.CharField(
        max_length=10,
        choices=[
            ("U", "Universal"),
            ("UA", "UA"),
            ("A", "Adults"),
        ],
    )

    trailer_url = models.URLField(blank=True)

    average_rating = models.DecimalField(
        max_digits=3,
        decimal_places=1,
        default=0.0
    )

    category = models.ForeignKey(
    MovieCategory,
    on_delete=models.SET_NULL,
    null=True,
    blank=True
)

    language = models.ForeignKey(
    MovieLanguage,
    on_delete=models.SET_NULL,
    null=True,
    blank=True
)

    cast_members = models.ManyToManyField(
    CastMember,
    blank=True
)

    trailer_url = models.URLField(
    blank=True,
    help_text="Paste YouTube video URL"
)

    release_date = models.DateField(
    null=True,
    blank=True
)

    duration = models.PositiveIntegerField(
    default=120,
    help_text="Duration in minutes"
)

    AGE_CHOICES = [
    ("U", "Universal"),
    ("UA", "Parental Guidance"),
    ("A", "Adults Only"),
]

    age_certificate = models.CharField(
    max_length=2,
    choices=AGE_CHOICES,
    default="U"
)

    is_trending = models.BooleanField(default=False)
    is_featured = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

class MoviePoster(models.Model):
    movie = models.ForeignKey(
        Movie,
        on_delete=models.CASCADE,
        related_name="posters"
    )

    image = models.ImageField(upload_to="movie_posters/")
    is_primary = models.BooleanField(default=False)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.movie.name} Poster"

class Theater(models.Model):
    theater_name = models.CharField(max_length=255)
    city = models.CharField(max_length=100, blank=True, null=True)
    address = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.theater_name

class Screen(models.Model):
    theater = models.ForeignKey(
        Theater,
        on_delete=models.CASCADE,
        related_name="screens"
    )

    screen_name = models.CharField(max_length=50)
    total_seats = models.PositiveIntegerField(default=12)

    def __str__(self):
        return f"{self.theater.theater_name} - {self.screen_name}"

    def save(self, *args, **kwargs):
        is_new = self.pk is None

        super().save(*args, **kwargs)

        if is_new:
            seat_numbers = [
                "A1", "A2", "A3", "A4", "A5", "A6",
                "B1", "B2", "B3", "B4", "B5", "B6"
            ]

            Seat.objects.bulk_create(
                [
                    Seat(
                        screen=self,
                        seat_number=seat_number,
                        seat_type="REGULAR",
                        is_active=True
                    )
                    for seat_number in seat_numbers
                ]
            )

class ShowSchedule(models.Model):
    movie = models.ForeignKey(
        Movie,
        on_delete=models.CASCADE,
        related_name="shows"
    )

    screen = models.ForeignKey(
        Screen,on_delete=models.CASCADE,
        related_name="shows_schedules"
    )

    show_date = models.DateField()

    start_time = models.TimeField()

    end_time = models.TimeField()

    ticket_price = models.DecimalField(
        max_digits=8,
        decimal_places=2
    )

    available_seats = models.PositiveIntegerField()

    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.movie.name} | {self.show_date} | {self.start_time}"

class Seat(models.Model):
    SEAT_TYPES = [
        ("REGULAR", "Regular"),
        ("PREMIUM", "Premium"),
        ("VIP", "VIP"),
        ("RECLINER", "Recliner"),
    ]

    screen = models.ForeignKey(
        Screen,
        on_delete=models.CASCADE,
        related_name="seats",
        null=True,
        blank=True
    )

    seat_number = models.CharField(max_length=10)

    seat_type = models.CharField(
        max_length=20,
        choices=SEAT_TYPES,
        default="REGULAR"
    )

    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.screen.screen_name} - {self.seat_number}"

class Booking(models.Model):

    BOOKING_STATUS = [
        ("Pending", "Pending"),
        ("Confirmed", "Confirmed"),
        ("Cancelled", "Cancelled"),
        ("Completed", "Completed"),
    ]

    PAYMENT_STATUS = [
        ("Pending", "Pending"),
        ("Success", "Success"),
        ("Failed", "Failed"),
    ]

    user = models.ForeignKey(
        User,on_delete=models.CASCADE
    )

    seat = models.ForeignKey(
    Seat,
    on_delete=models.CASCADE
)

    movie = models.ForeignKey(
        Movie,on_delete=models.CASCADE
    )

    theater = models.ForeignKey(
        Theater,on_delete=models.CASCADE
    )

    
    show_schedule = models.ForeignKey(
        ShowSchedule,
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )

    booked_at = models.DateTimeField(auto_now_add=True)

    reservation_expires_at = models.DateTimeField(
        null=True,
        blank=True
    )

    booking_status = models.CharField(
        max_length=20,
        choices=BOOKING_STATUS,
        default="Pending"
    )

    payment_status = models.CharField(
        max_length=20,
        choices=PAYMENT_STATUS,
        default="Pending"
    )

    payment_reference = models.CharField(
        max_length=100,
        null=True,
        blank=True
    )

    total_amount = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=0
    )

    def __str__(self):
        return f"Booking by {self.user.username} for {self.movie.name}"

class Review(models.Model):

    RATING_CHOICES = [
        (1, "1 Star"),
        (2, "2 Stars"),
        (3, "3 Stars"),
        (4, "4 Stars"),
        (5, "5 Stars"),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE
    )

    movie = models.ForeignKey(
        Movie,
        on_delete=models.CASCADE,
        related_name="reviews"
    )

    booking = models.ForeignKey(
        Booking,
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )

    rating = models.PositiveSmallIntegerField(
        choices=RATING_CHOICES
    )

    review = models.TextField()

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    is_verified_viewer = models.BooleanField(
        default=False
    )

    is_reported = models.BooleanField(
        default=False
    )

    def __str__(self):
        return f"{self.user.username} - {self.movie.name}"

    def update_movie_rating(self):
        average = self.movie.reviews.aggregate(
        average=Avg("rating")
    )["average"]
        self.movie.average_rating = (
        round(average, 1)
        if average
        else 0
    )
        self.movie.save(
        update_fields=["average_rating"]
    )


@receiver(post_save, sender=Review)
def update_rating_after_review_save(
    sender,
    instance,
    **kwargs
):
    instance.update_movie_rating()


@receiver(post_delete, sender=Review)
def update_rating_after_review_delete(
    sender,
    instance,
    **kwargs
):
    instance.update_movie_rating()

