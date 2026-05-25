from django.contrib.auth.decorators import login_required
from django.contrib.auth import login
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404, redirect, render

from .forms import RecommendationForm, ReviewForm, SignUpForm
from .models import Friendship, Item, Recommendation, Review


def feed(request):
    friends_only = request.GET.get("filter") == "friends"
    friend_ids = []

    if request.user.is_authenticated:
        friend_ids = Friendship.objects.filter(
            from_user=request.user
        ).values_list("to_user_id", flat=True)

    reviews = Review.objects.select_related("user", "item")

    if friends_only and request.user.is_authenticated:
        reviews = reviews.filter(user_id__in=friend_ids)

    reviews = reviews.order_by("-created_at")
    recommendations = Recommendation.objects.none()

    if request.user.is_authenticated:
        recommendations = Recommendation.objects.filter(
            to_user=request.user
        ).select_related("from_user", "item").order_by("-created_at")[:5]

    return render(
        request,
        "posts/feed.html",
        {
            "reviews": reviews,
            "recommendations": recommendations,
            "friends_only": friends_only,
        },
    )


def signup(request):
    if request.method == "POST":
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect("feed")
    else:
        form = SignUpForm()

    return render(request, "registration/signup.html", {"form": form})


@login_required
def new_review(request):
    if request.method == "POST":
        form = ReviewForm(request.POST)
        if form.is_valid():
            item, _ = Item.objects.get_or_create(
                title=form.cleaned_data["item_title"],
                defaults={"item_type": form.cleaned_data["item_type"]},
            )
            Review.objects.create(
                user=request.user,
                item=item,
                rating=form.cleaned_data["rating"],
                review_text=form.cleaned_data["review_text"],
            )
            return redirect("feed")
    else:
        form = ReviewForm()

    return render(request, "posts/new_review.html", {"form": form})


@login_required
def friends(request):
    friend_ids = Friendship.objects.filter(
        from_user=request.user
    ).values_list("to_user_id", flat=True)
    friends_list = User.objects.filter(id__in=friend_ids).order_by("username")
    suggested_users = User.objects.exclude(
        id=request.user.id
    ).exclude(
        id__in=friend_ids
    ).order_by("username")

    return render(
        request,
        "posts/friends.html",
        {
            "friends": friends_list,
            "suggested_users": suggested_users,
        },
    )


@login_required
def add_friend(request, user_id):
    friend = get_object_or_404(User, id=user_id)
    if friend != request.user:
        Friendship.objects.get_or_create(from_user=request.user, to_user=friend)
    return redirect("friends")


@login_required
def remove_friend(request, user_id):
    Friendship.objects.filter(
        from_user=request.user,
        to_user_id=user_id,
    ).delete()
    return redirect("friends")


@login_required
def recommend(request):
    friend_ids = Friendship.objects.filter(
        from_user=request.user
    ).values_list("to_user_id", flat=True)

    if request.method == "POST":
        form = RecommendationForm(request.POST)
        form.fields["to_user"].queryset = User.objects.filter(id__in=friend_ids)
        if form.is_valid():
            recommendation = form.save(commit=False)
            recommendation.from_user = request.user
            recommendation.save()
            return redirect("feed")
    else:
        form = RecommendationForm()
        form.fields["to_user"].queryset = User.objects.filter(
            id__in=friend_ids
        ).order_by("username")

    return render(request, "posts/recommend.html", {"form": form})
