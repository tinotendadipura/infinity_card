from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator
from django.db import models
from django_countries.fields import CountryField


class User(AbstractUser):
    ACCOUNT_TYPE_CHOICES = [
        ('', 'Not Selected'),
        ('personal', 'Personal / Individual'),
        ('business', 'Business'),
    ]

    username = models.CharField(
        max_length=30,
        unique=True,
        validators=[
            RegexValidator(
                regex=r'^[a-z0-9]([a-z0-9-]*[a-z0-9])?$',
                message='Lowercase letters, numbers, and hyphens only. '
                        'Must start and end with a letter or number.',
            ),
        ],
    )
    email = models.EmailField(unique=True)
    account_type = models.CharField(
        max_length=10,
        choices=ACCOUNT_TYPE_CHOICES,
        default='',
        blank=True,
        help_text='Selected during onboarding: personal or business',
    )
    country = CountryField(
        blank=True,
        blank_label='(select country)',
        help_text='Select your country',
    )

    RESERVED_USERNAMES = {
        'www', 'admin', 'api', 'tap', 'static', 'media',
        'mail', 'ftp', 'dashboard', 'login', 'logout', 'signup',
    }

    def clean(self):
        super().clean()
        if self.username.lower() in self.RESERVED_USERNAMES:
            from django.core.exceptions import ValidationError
            raise ValidationError({'username': 'This username is reserved.'})

    def __str__(self):
        return self.username
