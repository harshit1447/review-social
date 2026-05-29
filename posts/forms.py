from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from .models import Collection, Comment, Item, Profile, Recommendation, Review


class SignUpForm(UserCreationForm):
    class Meta:
        model = User
        fields = ["username", "password1", "password2"]


class ReviewForm(forms.Form):
    item_title = forms.CharField(max_length=255)
    item_type = forms.ChoiceField(choices=Item.TYPE_CHOICES)
    selected_item_key = forms.CharField(widget=forms.HiddenInput())
    selected_item_title = forms.CharField(widget=forms.HiddenInput())
    selected_item_year = forms.CharField(widget=forms.HiddenInput(), required=False)
    selected_item_creator = forms.CharField(widget=forms.HiddenInput(), required=False)
    selected_item_image_url = forms.CharField(widget=forms.HiddenInput(), required=False)
    selected_item_external_source = forms.CharField(widget=forms.HiddenInput(), required=False)
    selected_item_external_id = forms.CharField(widget=forms.HiddenInput(), required=False)
    rating = forms.IntegerField(min_value=1, max_value=5)
    review_text = forms.CharField(widget=forms.Textarea(attrs={"rows": 4}))

    def clean(self):
        cleaned_data = super().clean()
        selected_item_key = (cleaned_data.get("selected_item_key") or "").strip()
        selected_item_title = (cleaned_data.get("selected_item_title") or "").strip()
        typed_title = (cleaned_data.get("item_title") or "").strip()

        if not selected_item_key or not selected_item_title:
            raise forms.ValidationError("Please choose an item from the suggestions.")

        if selected_item_title.lower() != typed_title.lower():
            raise forms.ValidationError("Please select an exact item from the suggestions list.")

        valid_prefixes = (
            "item:",
            "google:",
            "googlebooks:",
            "openlibrary:",
            "omdb:",
            "wikidata:",
        )
        if not selected_item_key.startswith(valid_prefixes):
            raise forms.ValidationError("Invalid item selection. Please pick again.")

        return cleaned_data


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
    class Meta:
        model = Profile
        fields = [
            "profile_photo",
            "cover_image",
            "bio",
            "location",
            "website",
            "favorite_categories",
        ]
        widgets = {
            "bio": forms.Textarea(attrs={"rows": 4}),
            "favorite_categories": forms.TextInput(attrs={"placeholder": "Movies, books, restaurants"}),
        }


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
