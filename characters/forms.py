from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User


class RegistrationForm(UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta:
        model = User
        fields = ("username", "email", "password1", "password2")

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        if commit:
            user.save()
        return user


class FeedbackForm(forms.Form):
    title = forms.CharField(
        max_length=200,
        widget=forms.TextInput(attrs={"placeholder": "Brief summary of the issue"}),
    )
    description = forms.CharField(
        widget=forms.Textarea(
            attrs={
                "rows": 6,
                "placeholder": "What happened? What did you expect instead?",
            }
        ),
    )
