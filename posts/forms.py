from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from .models import Collection, Comment, Item, Profile, Recommendation, Review


REVIEW_ITEM_TYPE_CHOICES = (
    ("movie", "Movie"),
    ("series", "Series"),
    ("book", "Book"),
)


class SignUpForm(UserCreationForm):
    first_name = forms.CharField(label="Name", max_length=150)
    email = forms.EmailField(label="Email")

    class Meta:
        model = User
        fields = ["first_name", "email", "username", "password1", "password2"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["first_name"].widget.attrs.update(
            {
                "autocomplete": "name",
                "placeholder": "Your name",
            }
        )
        self.fields["email"].widget.attrs.update(
            {
                "autocomplete": "email",
                "placeholder": "you@example.com",
            }
        )
        self.fields["username"].widget.attrs.update(
            {
                "autocomplete": "username",
                "autocapitalize": "none",
                "spellcheck": "false",
                "placeholder": "Choose a username",
            }
        )
        self.fields["password1"].widget.attrs.update(
            {
                "autocomplete": "new-password",
                "placeholder": "Create a password",
            }
        )
        self.fields["password2"].widget.attrs.update(
            {
                "autocomplete": "new-password",
                "placeholder": "Confirm your password",
            }
        )

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.first_name = self.cleaned_data["first_name"].strip()
        user.email = self.cleaned_data["email"].strip().lower()
        if commit:
            user.save()
            Profile.objects.get_or_create(user=user)
        return user


class ReviewForm(forms.Form):
    item_title = forms.CharField(max_length=255)
    item_type = forms.ChoiceField(choices=REVIEW_ITEM_TYPE_CHOICES)
    selected_item_key = forms.CharField(widget=forms.HiddenInput(), required=False)
    selected_item_title = forms.CharField(widget=forms.HiddenInput(), required=False)
    selected_item_year = forms.CharField(widget=forms.HiddenInput(), required=False)
    selected_item_creator = forms.CharField(widget=forms.HiddenInput(), required=False)
    selected_item_image_url = forms.CharField(widget=forms.HiddenInput(), required=False)
    selected_item_external_source = forms.CharField(widget=forms.HiddenInput(), required=False)
    selected_item_external_id = forms.CharField(widget=forms.HiddenInput(), required=False)
    rating = forms.IntegerField(
        min_value=1,
        max_value=5,
        widget=forms.NumberInput(attrs={"placeholder": "out of 5"}),
    )
    review_text = forms.CharField(widget=forms.Textarea(attrs={"rows": 4}))

    def clean(self):
        cleaned_data = super().clean()
        selected_item_key = (cleaned_data.get("selected_item_key") or "").strip()
        selected_item_title = (cleaned_data.get("selected_item_title") or "").strip()
        typed_title = (cleaned_data.get("item_title") or "").strip()

        if not selected_item_key or not selected_item_title:
            raise forms.ValidationError("Please choose an item from the suggestions before posting.")

        if selected_item_title.lower() != typed_title.lower():
            raise forms.ValidationError("Please select an exact item from the suggestions list.")

        valid_prefixes = (
            "item:",
            "google:",
            "googlebooks:",
            "openlibrary:",
            "omdb:",
            "tmdb:",
            "catalog:",
            "fallback:",
            "wikidata:",
            "preview:",
        )
        if not selected_item_key.startswith(valid_prefixes):
            raise forms.ValidationError("Invalid item selection. Please pick again.")

        return cleaned_data


class ReviewEditForm(forms.ModelForm):
    class Meta:
        model = Review
        fields = ["rating", "review_text"]
        widgets = {
            "review_text": forms.Textarea(attrs={"rows": 4}),
        }


class RecommendationForm(forms.ModelForm):
    class Meta:
        model = Recommendation
        fields = ["to_user", "item", "message"]
        widgets = {
            "message": forms.Textarea(
                attrs={
                    "maxlength": 140,
                    "rows": 3,
                    "placeholder": "Add a short note, up to 140 characters.",
                }
            ),
        }
        help_texts = {
            "message": "Keep it short: 140 characters max.",
        }


class ProfileForm(forms.ModelForm):
    first_name = forms.CharField(label="Name", max_length=150)
    username = forms.CharField(label="Username", max_length=150)

    class Meta:
        model = Profile
        fields = [
            "first_name",
            "username",
            "profile_photo",
            "cover_image",
            "bio",
            "location",
            "website",
            "favorite_categories",
        ]
        widgets = {
            "profile_photo": forms.ClearableFileInput(attrs={"accept": "image/*"}),
            "cover_image": forms.ClearableFileInput(attrs={"accept": "image/*"}),
            "bio": forms.Textarea(attrs={"rows": 4}),
            "favorite_categories": forms.TextInput(attrs={"placeholder": "Movies, books, restaurants"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.user_id:
            self.fields["first_name"].initial = self.instance.user.first_name
            self.fields["username"].initial = self.instance.user.username

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        user = self.instance.user
        if User.objects.exclude(id=user.id).filter(username__iexact=username).exists():
            raise forms.ValidationError("This username is already taken.")
        return username

    def save(self, commit=True):
        profile = super().save(commit=False)
        user = profile.user
        user.first_name = self.cleaned_data["first_name"].strip()
        user.username = self.cleaned_data["username"].strip()
        if commit:
            user.save(update_fields=["first_name", "username"])
            profile.save()
        return profile


class CommentForm(forms.ModelForm):
    class Meta:
        model = Comment
        fields = ["body"]
        widgets = {
            "body": forms.Textarea(attrs={"rows": 3, "placeholder": "Add to the discussion..."})
        }


class CollectionForm(forms.ModelForm):
    class Meta:
        model = Collection
        fields = ["title", "description", "is_public"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
        }
