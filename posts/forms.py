from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from .models import Item, Recommendation, Review


class SignUpForm(UserCreationForm):
    class Meta:
        model = User
        fields = ["username", "password1", "password2"]


class ReviewForm(forms.Form):
    item_title = forms.CharField(max_length=255)
    item_type = forms.ChoiceField(choices=Item.TYPE_CHOICES)
    rating = forms.IntegerField(min_value=1, max_value=5)
    review_text = forms.CharField(widget=forms.Textarea(attrs={"rows": 4}))


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
