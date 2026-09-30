from django.contrib import admin
from django import forms

from .models import (
    Movie,
    MovieCategory,
    MovieLanguage,
    CastMember,
    MoviePoster,
    Theater,
    Screen,
    Seat,
    ShowSchedule,
    Booking,
    Review,
)


class MovieAdminForm(forms.ModelForm):
    class Meta:
        model = Movie
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["category"].empty_label = "Select Category"
        self.fields["language"].empty_label = "Select Language"


class MoviePosterInline(admin.TabularInline):
    model = MoviePoster
    extra = 2
    fields = (
        "image",
        "is_primary",
    )


@admin.register(Movie)
class MovieAdmin(admin.ModelAdmin):
    form = MovieAdminForm

    inlines = [
        MoviePosterInline,
    ]

    list_display = (
        "name",
        "category",
        "language",
        "release_date",
        "is_trending",
        "is_featured",
        "average_rating",
    )

    list_filter = (
        "category",
        "language",
        "is_trending",
        "is_featured",
    )

    search_fields = (
        "name",
        "description",
    )


admin.site.register(MovieCategory)
admin.site.register(MovieLanguage)
admin.site.register(CastMember)
admin.site.register(Theater)
admin.site.register(Screen)
admin.site.register(Seat)
admin.site.register(ShowSchedule)
admin.site.register(Booking)
admin.site.register(Review)