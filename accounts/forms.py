import re

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from django_countries.fields import CountryField

User = get_user_model()


def _email_to_username(email):
    """Derive a unique username from an email address."""
    local = email.split('@')[0].lower()
    # Keep only allowed characters
    base = re.sub(r'[^a-z0-9-]', '', local)[:20] or 'user'
    # Ensure it starts/ends with alphanumeric
    base = base.strip('-') or 'user'
    # Ensure uniqueness
    candidate = base
    counter = 1
    while User.objects.filter(username=candidate).exists() or candidate in User.RESERVED_USERNAMES:
        candidate = f'{base}-{counter}'
        counter += 1
    return candidate


class SignupForm(UserCreationForm):
    first_name = forms.CharField(
        max_length=150,
        required=True,
        widget=forms.TextInput(attrs={'placeholder': 'First name'}),
    )
    last_name = forms.CharField(
        max_length=150,
        required=True,
        widget=forms.TextInput(attrs={'placeholder': 'Last name'}),
    )
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={'placeholder': 'you@example.com'}),
    )
    country = CountryField(blank_label='Select your country').formfield(
        required=True,
        widget=forms.Select(attrs={'class': 'country-select', 'id': 'id_country'}),
    )

    class Meta:
        model = User
        fields = ('first_name', 'last_name', 'email', 'country', 'password1', 'password2')

    def save(self, commit=True):
        user = super().save(commit=False)
        user.username = _email_to_username(user.email)
        user.first_name = self.cleaned_data['first_name'].strip().title()
        user.last_name = self.cleaned_data['last_name'].strip().title()
        if commit:
            user.save()
        return user
