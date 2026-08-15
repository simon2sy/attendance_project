from django import forms
from django.contrib.auth import get_user_model
from .models import Employee
import re

User = get_user_model()


class EmployeeForm(forms.ModelForm):
    user = forms.ModelChoiceField(
        queryset=User.objects.filter(employee_profile__isnull=True),
        required=False,
        empty_label="No linked user account",
        widget=forms.Select(attrs={
            "class": "form-select",
        }),
        help_text="Optional: Link this employee with a Django login."
    )

    class Meta:
        model = Employee
        fields = [
            "user",
            "full_name",
            "department",
            "designation",
            "email",
            "phone",
            "is_active",
        ]

        widgets = {
            "full_name": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "John Doe",
                "autofocus": True,
                "autocomplete": "name",
            }),

            "department": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Information Technology",
            }),

            "designation": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Software Engineer",
            }),

            "email": forms.EmailInput(attrs={
                "class": "form-control",
                "placeholder": "john@company.com",
                "autocomplete": "email",
            }),

            "phone": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "+97798XXXXXXXX",
                "autocomplete": "tel",
            }),

            "is_active": forms.CheckboxInput(attrs={
                "class": "form-check-input",
                "role": "switch",
            }),
        }

        help_texts = {
            "is_active": "Inactive employees cannot mark attendance.",
        }

    def clean_full_name(self):
        return self.cleaned_data["full_name"].strip()

    def clean_department(self):
        return self.cleaned_data.get("department", "").strip()

    def clean_designation(self):
        return self.cleaned_data.get("designation", "").strip()

    def clean_email(self):
        email = self.cleaned_data.get("email")

        if email:
            email = email.lower().strip()

            qs = Employee.objects.filter(email=email)

            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)

            if qs.exists():
                raise forms.ValidationError(
                    "An employee with this email already exists."
                )

        return email

    def clean_phone(self):
        phone = self.cleaned_data.get("phone", "").strip()

        if phone and not re.match(r"^[\d\s()+-]{7,20}$", phone):
            raise forms.ValidationError(
                "Enter a valid phone number."
            )

        return phone
class EmployeeSignupForm(forms.Form):
    """
    Self-service employee signup.

    Creates a Django user with NO staff/superuser privileges and links an
    Employee profile to it. The account can only reach the employee dashboard
    (record attendance for itself) — it cannot alter any data.
    """

    username = forms.CharField(
        max_length=150,
        label="Username",
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "Choose a username",
            "autofocus": True,
            "autocomplete": "username",
        }),
    )
    email = forms.EmailField(
        required=False,
        label="Email (optional)",
        widget=forms.EmailInput(attrs={
            "class": "form-control",
            "placeholder": "you@example.com",
            "autocomplete": "email",
        }),
    )
    full_name = forms.CharField(
        max_length=150,
        label="Full Name",
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "John Doe",
            "autocomplete": "name",
        }),
    )
    department = forms.CharField(
        required=False,
        max_length=100,
        label="Department (optional)",
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "Information Technology",
        }),
    )
    designation = forms.CharField(
        required=False,
        max_length=100,
        label="Designation (optional)",
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "Software Engineer",
        }),
    )
    phone = forms.CharField(
        required=False,
        max_length=20,
        label="Phone (optional)",
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "+97798XXXXXXXX",
            "autocomplete": "tel",
        }),
    )
    password1 = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(attrs={
            "class": "form-control",
            "placeholder": "Create a password",
            "autocomplete": "new-password",
        }),
    )
    password2 = forms.CharField(
        label="Confirm Password",
        widget=forms.PasswordInput(attrs={
            "class": "form-control",
            "placeholder": "Repeat your password",
            "autocomplete": "new-password",
        }),
    )

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("A user with this username already exists.")
        return username

    def clean_email(self):
        email = self.cleaned_data.get("email")
        if email:
            email = email.lower().strip()
            if (
                Employee.objects.filter(email=email).exists()
                or User.objects.filter(email__iexact=email).exists()
            ):
                raise forms.ValidationError("A user with this email already exists.")
        return email

    def clean_full_name(self):
        return self.cleaned_data["full_name"].strip()

    def clean_department(self):
        return self.cleaned_data.get("department", "").strip()

    def clean_designation(self):
        return self.cleaned_data.get("designation", "").strip()

    def clean_phone(self):
        phone = self.cleaned_data.get("phone", "").strip()
        if phone and not re.match(r"^[\d\s()+-]{7,20}$", phone):
            raise forms.ValidationError("Enter a valid phone number.")
        return phone

    def clean_password1(self):
        password = self.cleaned_data.get("password1")
        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError as DjangoValidationError

        try:
            validate_password(password)
        except DjangoValidationError as e:
            raise forms.ValidationError(e.messages)
        return password

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get("password1")
        p2 = cleaned.get("password2")
        if p1 and p2 and p1 != p2:
            raise forms.ValidationError("The two password fields did not match.")
        return cleaned

    def save(self):
        """Create the User (no staff/superuser privileges) and the Employee."""
        cd = self.cleaned_data
        user = User.objects.create_user(
            username=cd["username"],
            email=cd.get("email") or "",
            password=cd["password1"],
        )
        # Explicitly ensure the account has NO administrative power.
        user.is_staff = False
        user.is_superuser = False
        user.is_active = True
        user.save()

        employee = Employee.objects.create(
            user=user,
            full_name=cd["full_name"],
            department=cd.get("department", ""),
            designation=cd.get("designation", ""),
            email=cd.get("email") or "",
            phone=cd.get("phone", ""),
            is_active=True,
        )
        return user, employee