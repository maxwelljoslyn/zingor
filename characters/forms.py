from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from .models import Character

# Ceiling on an uploaded character picture. Django's own upload limits govern
# only non-file POST data, so a file needs its own cap.
MAX_PICTURE_MB = 1
MAX_PICTURE_BYTES = MAX_PICTURE_MB * 1024 * 1024

# Ceiling on each side in pixels. Bytes alone don't bound the cost of decoding
# an image: a heavily compressed file well under MAX_PICTURE_BYTES can hold tens
# of thousands of pixels per side and expand to gigabytes in memory when Pillow
# opens it. Dimensions are read from the header, so this rejects such a file
# before anything decodes it.
MAX_PICTURE_PIXELS = 2048


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


class CharacterPictureForm(forms.ModelForm):
    """An uploaded character picture: a real image file, within the size cap.

    ImageField verifies the upload actually decodes as an image, so a renamed
    non-image (or a mislabelled one) is rejected before it reaches MEDIA_ROOT.
    """

    # The model field is optional so a character can have no picture; submitting
    # this form without a file is still an error, not a silent no-op.
    picture = forms.ImageField(required=True)

    class Meta:
        model = Character
        fields = ("picture",)

    def clean_picture(self):
        picture = self.cleaned_data["picture"]
        if picture.size > MAX_PICTURE_BYTES:
            raise forms.ValidationError(
                f"Picture must be {MAX_PICTURE_MB} MB or smaller."
            )
        # ImageField.to_python hangs the opened (not yet decoded) PIL image off
        # the upload, so the dimensions cost nothing to read here.
        image = getattr(picture, "image", None)
        if image is not None and max(image.size) > MAX_PICTURE_PIXELS:
            raise forms.ValidationError(
                f"Picture must be {MAX_PICTURE_PIXELS}x{MAX_PICTURE_PIXELS} pixels or smaller."
            )
        return picture


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
