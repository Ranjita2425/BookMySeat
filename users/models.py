from django.db import models
from django.contrib.auth.models import User


class Location(models.Model):
    state = models.CharField(max_length=100)
    district = models.CharField(max_length=100)
    city = models.CharField(max_length=100)

    class Meta:
        ordering = ["state", "district", "city"]

    def __str__(self):
        return f"{self.city}, {self.district}, {self.state}"


class UserProfile(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="profile"
    )

    preferred_location = models.ForeignKey(
        Location,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="users"
    )

    def __str__(self):
        return self.user.username