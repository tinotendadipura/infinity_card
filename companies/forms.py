from django import forms
from django.core.exceptions import ValidationError
from django.utils.text import slugify
from .models import Company, CompanyMembership


class CompanyRegistrationForm(forms.ModelForm):
    """Form for registering a new company."""

    class Meta:
        model = Company
        fields = ['name', 'logo', 'website', 'industry', 'email', 'phone', 'address']
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'Company name'}),
            'website': forms.URLInput(attrs={'placeholder': 'https://yourcompany.com'}),
            'industry': forms.TextInput(attrs={'placeholder': 'e.g. Technology, Finance, Healthcare'}),
            'email': forms.EmailInput(attrs={'placeholder': 'contact@yourcompany.com'}),
            'phone': forms.TextInput(attrs={'placeholder': 'Company phone number'}),
            'address': forms.Textarea(attrs={'placeholder': 'Company address', 'rows': 3}),
            'logo': forms.ClearableFileInput(attrs={'accept': 'image/*'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['name'].required = True
        self.fields['email'].required = True
        
        # Add custom validators
        self.fields['name'].validators = [self.validate_company_name]
        self.fields['email'].validators = [self.validate_company_email]
        self.fields['website'].validators = [self.validate_website]
        self.fields['phone'].validators = [self.validate_phone]
        self.fields['logo'].validators = [self.validate_logo]

    def validate_company_name(self, value):
        """Validate company name."""
        if len(value.strip()) < 2:
            raise ValidationError('Company name must be at least 2 characters long.')
        
        if len(value.strip()) > 200:
            raise ValidationError('Company name cannot exceed 200 characters.')
        
        # Check if company name already exists
        if Company.objects.filter(name__iexact=value.strip()).exists():
            raise ValidationError('A company with this name already exists.')
        
        return value.strip()

    def validate_company_email(self, value):
        """Validate company email."""
        value = value.strip().lower()
        
        # Check if email is already used by another company
        if Company.objects.filter(email__iexact=value).exists():
            raise ValidationError('This email is already registered with another company.')
        
        return value

    def validate_website(self, value):
        """Validate website URL."""
        if value and not value.startswith(('http://', 'https://')):
            raise ValidationError('Website URL must start with http:// or https://')
        return value

    def validate_phone(self, value):
        """Validate phone number."""
        if value:
            # Remove common phone number formatting
            cleaned_phone = ''.join(filter(str.isdigit, value))
            
            if len(cleaned_phone) < 10:
                raise ValidationError('Please enter a valid phone number with at least 10 digits.')
            
            if len(cleaned_phone) > 15:
                raise ValidationError('Phone number appears to be too long.')
        
        return value

    def validate_logo(self, value):
        """Validate logo file."""
        if value:
            # Check file size (max 5MB)
            if value.size > 5 * 1024 * 1024:
                raise ValidationError('Logo file size cannot exceed 5MB.')
            
            # Check file type
            allowed_types = ['image/jpeg', 'image/jpg', 'image/png', 'image/gif']
            if value.content_type not in allowed_types:
                raise ValidationError('Logo must be a JPEG, PNG, or GIF image.')
            
            # Check image dimensions (min 100x100, max 2000x2000)
            try:
                from PIL import Image
                img = Image.open(value)
                width, height = img.size
                
                if width < 100 or height < 100:
                    raise ValidationError('Logo must be at least 100x100 pixels.')
                
                if width > 2000 or height > 2000:
                    raise ValidationError('Logo cannot exceed 2000x2000 pixels.')
            except Exception:
                # If PIL is not available or image can't be processed
                pass
        
        return value

    def clean_industry(self):
        """Clean and validate industry field."""
        industry = self.cleaned_data.get('industry')
        if industry:
            return industry.strip().title()
        return industry

    def clean_address(self):
        """Clean and validate address field."""
        address = self.cleaned_data.get('address')
        if address:
            if len(address.strip()) < 10:
                raise ValidationError('Please provide a more detailed address.')
            return address.strip()
        return address

    def save(self, commit=True):
        """Save the company with auto-generated slug."""
        company = super().save(commit=False)
        
        # Generate slug from company name
        base_slug = slugify(company.name)
        slug = base_slug
        counter = 1
        
        # Ensure slug is unique
        while Company.objects.filter(slug=slug).exists():
            slug = f"{base_slug}-{counter}"
            counter += 1
        
        company.slug = slug
        
        if commit:
            company.save()
        
        return company


class InviteEmployeeForm(forms.Form):
    """Form for inviting an employee by name, title, and email."""
    first_name = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={'placeholder': 'e.g. John'}),
    )
    last_name = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={'placeholder': 'e.g. Doe'}),
    )
    title = forms.CharField(
        max_length=200,
        widget=forms.TextInput(attrs={'placeholder': 'e.g. Software Engineer'}),
    )
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={'placeholder': 'e.g. john@company.com'}),
    )

    def clean_email(self):
        return self.cleaned_data['email'].strip().lower()


class EmployeeDetailForm(forms.ModelForm):
    """Form for editing employee name/title on a membership."""

    class Meta:
        model = CompanyMembership
        fields = ['employee_name', 'employee_title', 'role']
        widgets = {
            'employee_name': forms.TextInput(attrs={'placeholder': 'Full name'}),
            'employee_title': forms.TextInput(attrs={'placeholder': 'Job title'}),
            'role': forms.Select(),
        }


class CompanySettingsForm(forms.ModelForm):
    """Form for editing company details."""

    class Meta:
        model = Company
        fields = ['name', 'profile_picture', 'logo', 'website', 'industry', 'email', 'phone', 'address']
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'Company name'}),
            'website': forms.URLInput(attrs={'placeholder': 'https://yourcompany.com'}),
            'industry': forms.TextInput(attrs={'placeholder': 'e.g. Technology, Finance'}),
            'email': forms.EmailInput(attrs={'placeholder': 'contact@yourcompany.com'}),
            'phone': forms.TextInput(attrs={'placeholder': 'Phone number'}),
            'address': forms.Textarea(attrs={'placeholder': 'Company address', 'rows': 3}),
            'logo': forms.ClearableFileInput(attrs={'accept': 'image/*'}),
            'profile_picture': forms.ClearableFileInput(attrs={'accept': 'image/*'}),
        }
