from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from movies.models import Movie, Theater, Screen, ShowSchedule


class Command(BaseCommand):

    help = "Create movie shows from today until the end of the current month"

    def handle(self, *args, **options):

        today = timezone.localdate()
        month_end = today.replace(day=31)

        show_times = [
            (9, 0),
            (11, 30),
            (14, 0),
            (16, 30),
            (19, 0),
            (21, 30),
        ]

        created_count = 0

        movies = Movie.objects.filter(
            release_date__isnull=False
        )

        theaters = Theater.objects.all()

        for movie in movies:

            first_date = max(
                movie.release_date,
                today
            )

            current_date = first_date

            while current_date <= month_end:

                for theater in theaters:

                    screens = Screen.objects.filter(
                        theater=theater
                    )

                    for screen in screens:

                        for hour, minute in show_times:

                            start_time = f"{hour:02d}:{minute:02d}"

                            end_hour = hour + 2

                            if end_hour >= 24:
                                end_hour -= 24

                            end_time = f"{end_hour:02d}:{minute:02d}"

                            exists = ShowSchedule.objects.filter(
                                movie=movie,
                                screen=screen,
                                show_date=current_date,
                                start_time=start_time
                            ).exists()

                            if not exists:

                                ShowSchedule.objects.create(
                                    movie=movie,
                                    screen=screen,
                                    show_date=current_date,
                                    start_time=start_time,
                                    end_time=end_time,
                                    ticket_price=200,
                                    available_seats=screen.total_seats,
                                    is_active=True
                                )

                                created_count += 1

                current_date += timedelta(days=1)

        self.stdout.write("=" * 50)
        self.stdout.write(
            self.style.SUCCESS(
                f"Shows created: {created_count}"
            )
        )
        self.stdout.write(
            f"Shows available until: {month_end}"
        )
        self.stdout.write(
            f"Timings per theater/screen per day: {len(show_times)}"
        )
        self.stdout.write("=" * 50)