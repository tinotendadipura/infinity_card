import re
from django import forms
from .models import (Profile, SocialLink, CatalogItem, CatalogCategory, Service, Skill,
                     Experience, Education, GalleryImage, BusinessHour, Testimonial, ContactMessage,
                     WebsitePortfolio)


class ProfileForm(forms.ModelForm):
    first_name = forms.CharField(
        max_length=150, required=False,
        widget=forms.TextInput(attrs={'placeholder': 'First name'}),
    )
    last_name = forms.CharField(
        max_length=150, required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Last name'}),
    )

    class Meta:
        model = Profile
        fields = [
            'category', 'display_name', 'headline', 'bio',
            'profile_image', 'phone', 'email', 'location',
            'website_url', 'is_published',
            'map_latitude', 'map_longitude', 'map_location_label',
        ]
        widgets = {
            'display_name': forms.TextInput(attrs={'placeholder': 'First Name Last Name'}),
            'headline': forms.TextInput(attrs={'placeholder': 'A short tagline about you'}),
            'bio': forms.Textarea(attrs={'rows': 5, 'placeholder': 'Tell people about yourself...'}),
            'phone': forms.HiddenInput(),
            'email': forms.EmailInput(attrs={'placeholder': 'public@email.com'}),
            'location': forms.TextInput(attrs={'placeholder': 'City, Country'}),
            'website_url': forms.URLInput(attrs={'placeholder': 'https://yoursite.com'}),
            'map_latitude': forms.HiddenInput(),
            'map_longitude': forms.HiddenInput(),
            'map_location_label': forms.HiddenInput(),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if self.user:
            self.fields['first_name'].initial = self.user.first_name
            self.fields['last_name'].initial = self.user.last_name

    def save_user(self):
        if self.user:
            self.user.first_name = self.cleaned_data.get('first_name', '')
            self.user.last_name = self.cleaned_data.get('last_name', '')
            self.user.save(update_fields=['first_name', 'last_name'])

    def clean_phone(self):
        phone = self.cleaned_data.get('phone', '').strip()
        if not phone:
            return ''
        # Must start with + and contain only digits after that
        if not re.match(r'^\+\d{7,15}$', phone):
            raise forms.ValidationError(
                'Enter a valid phone number with country code (e.g. +263771234567).'
            )
        return phone


class SocialLinkForm(forms.ModelForm):
    class Meta:
        model = SocialLink
        fields = ['platform', 'url', 'label', 'order']
        widgets = {
            'url': forms.URLInput(attrs={'placeholder': 'https://...'}),
            'label': forms.TextInput(attrs={'placeholder': 'Custom label (optional)'}),
            'order': forms.NumberInput(attrs={'min': 0, 'style': 'width:60px'}),
        }


class CatalogItemForm(forms.ModelForm):
    class Meta:
        model = CatalogItem
        fields = ['category', 'title', 'price', 'image']
        widgets = {
            'title': forms.TextInput(attrs={'placeholder': 'e.g. Chocolate Cake'}),
            'price': forms.TextInput(attrs={'placeholder': 'e.g. $25'}),
        }

    def __init__(self, *args, profile=None, **kwargs):
        super().__init__(*args, **kwargs)
        if profile:
            self.fields['category'].queryset = CatalogCategory.objects.filter(profile=profile)
        self.fields['category'].required = False
        self.fields['category'].empty_label = 'No category'
        # When editing an existing item, image is optional (keep current)
        if self.instance and self.instance.pk:
            self.fields['image'].required = False


class ServiceForm(forms.ModelForm):
    class Meta:
        model = Service
        fields = ['title', 'description', 'price', 'order']
        widgets = {
            'title': forms.TextInput(attrs={'placeholder': 'e.g. Plumbing Services'}),
            'description': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Briefly describe this service...'}),
            'price': forms.TextInput(attrs={'placeholder': 'e.g. $50/hr, From $200'}),
            'order': forms.NumberInput(attrs={'min': 0, 'style': 'width:80px'}),
        }


class SkillForm(forms.ModelForm):
    class Meta:
        model = Skill
        fields = ['name']
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'e.g. Project Management'}),
        }


class ExperienceForm(forms.ModelForm):
    class Meta:
        model = Experience
        fields = ['title', 'company', 'location', 'start_date', 'end_date',
                  'is_current', 'description', 'company_logo']
        widgets = {
            'title': forms.TextInput(attrs={'placeholder': 'e.g. Software Engineer'}),
            'company': forms.TextInput(attrs={'placeholder': 'e.g. Google'}),
            'location': forms.TextInput(attrs={'placeholder': 'e.g. Harare, Zimbabwe'}),
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'end_date': forms.DateInput(attrs={'type': 'date'}),
            'description': forms.Textarea(attrs={'rows': 4, 'placeholder': 'Describe your role and achievements...'}),
        }

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('is_current'):
            cleaned['end_date'] = None
        elif not cleaned.get('end_date'):
            self.add_error('end_date', 'Provide an end date or check "I currently work here".')
        return cleaned


class EducationForm(forms.ModelForm):
    class Meta:
        model = Education
        fields = ['school', 'degree', 'field_of_study', 'start_year',
                  'end_year', 'description', 'school_logo']
        widgets = {
            'school': forms.TextInput(attrs={'placeholder': 'e.g. University of Zimbabwe'}),
            'degree': forms.TextInput(attrs={'placeholder': 'e.g. Bachelor of Science'}),
            'field_of_study': forms.TextInput(attrs={'placeholder': 'e.g. Computer Science'}),
            'start_year': forms.NumberInput(attrs={'placeholder': 'e.g. 2018', 'min': 1950, 'max': 2040}),
            'end_year': forms.NumberInput(attrs={'placeholder': 'e.g. 2022', 'min': 1950, 'max': 2040}),
            'description': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Activities, achievements, etc.'}),
        }


class GalleryImageForm(forms.ModelForm):
    class Meta:
        model = GalleryImage
        fields = ['image', 'caption']
        widgets = {
            'caption': forms.TextInput(attrs={'placeholder': 'Optional caption...'}),
        }


class BusinessHourForm(forms.ModelForm):
    class Meta:
        model = BusinessHour
        fields = ['day', 'opening_time', 'closing_time', 'is_closed']
        widgets = {
            'opening_time': forms.TimeInput(attrs={'type': 'time'}),
            'closing_time': forms.TimeInput(attrs={'type': 'time'}),
        }


class TestimonialForm(forms.ModelForm):
    class Meta:
        model = Testimonial
        fields = ['author_name', 'author_role', 'author_photo', 'content', 'rating']
        widgets = {
            'author_name': forms.TextInput(attrs={'placeholder': 'e.g. John Doe'}),
            'author_role': forms.TextInput(attrs={'placeholder': 'e.g. CEO at Acme Inc.'}),
            'content': forms.Textarea(attrs={'rows': 3, 'placeholder': 'What did they say about you?'}),
            'rating': forms.NumberInput(attrs={'min': 1, 'max': 5, 'style': 'width:80px'}),
        }


class ContactMessageForm(forms.ModelForm):
    class Meta:
        model = ContactMessage
        fields = ['sender_name', 'sender_phone', 'sender_email']
        widgets = {
            'sender_name': forms.TextInput(attrs={'placeholder': 'Full name'}),
            'sender_phone': forms.TextInput(attrs={'placeholder': '+263 7X XXX XXXX'}),
            'sender_email': forms.EmailInput(attrs={'placeholder': 'email@example.com'}),
        }


class WebsitePortfolioForm(forms.ModelForm):
    class Meta:
        model = WebsitePortfolio
        fields = ['url', 'title', 'description']
        widgets = {
            'url': forms.URLInput(attrs={'placeholder': 'https://example.com'}),
            'title': forms.TextInput(attrs={'placeholder': 'e.g. Acme Corp Redesign'}),
            'description': forms.TextInput(attrs={'placeholder': 'Brief description (optional)'}),
        }
