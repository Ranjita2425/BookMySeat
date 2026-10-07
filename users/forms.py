from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from .models import UserProfile, Location

class UserRegisterForm(UserCreationForm):
    email = forms.EmailField()

    class Meta:
        model = User
        fields = ['username', 'email', 'password1', 'password2']

class UserUpdateForm(forms.ModelForm):
    email = forms.EmailField()

    class Meta:
        model = User
        fields = ['username', 'email']

class ProfileUpdateForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['password']

class LocationUpdateForm(forms.ModelForm):
    preferred_location = forms.ModelChoiceField(
        queryset=UserProfile._meta.get_field('preferred_location').remote_field.model.objects.all(),
        empty_label="Select Location"
    )

    class Meta:
        model = UserProfile
        fields = ['preferred_location']
        labels = {
            'preferred_location': 'Preferred Location'
        }