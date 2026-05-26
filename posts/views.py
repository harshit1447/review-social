from django.contrib.auth.decorators import login_required
from django.contrib.auth import login
from django.contrib.auth.models import User
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render

from .forms import RecommendationForm, ReviewForm, SignUpForm
from .models import Friendship, Item, Recommendation, Review


def landing(request):
    if request.user.is_authenticated:
        return redirect("feed")
    return render(request, "landing.html")


def feed(request):
    if not request.user.is_authenticated:
        return redirect("account_login")
    
    friends_only = request.GET.get("filter") == "friends"
    query = request.GET.get("q", "").strip()
    friend_ids = []

    if request.user.is_authenticated:
        friend_ids = Friendship.objects.filter(
            from_user=request.user
        ).values_list("to_user_id", flat=True)

    reviews = Review.objects.select_related("user", "item")

    if friends_only and request.user.is_authenticated:
        reviews = reviews.filter(user_id__in=friend_ids)

    if query:
        reviews = reviews.filter(
            Q(item__title__icontains=query)
            | Q(item__item_type__icontains=query)
            | Q(review_text__icontains=query)
            | Q(user__username__icontains=query)
        )

    reviews = reviews.order_by("-created_at")

    return render(
        request,
        "posts/feed.html",
        {
            "reviews": reviews,
            "friends_only": friends_only,
            "query": query,
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
    query = request.GET.get("q", "").strip()
    friend_ids = Friendship.objects.filter(
        from_user=request.user
    ).values_list("to_user_id", flat=True)
    friends_list = User.objects.filter(id__in=friend_ids).order_by("username")
    suggested_users = User.objects.exclude(
        id=request.user.id
    ).exclude(
        id__in=friend_ids
    ).order_by("username")
    recommendations = Recommendation.objects.filter(
        to_user=request.user,
        from_user_id__in=friend_ids,
    ).select_related("from_user", "item").order_by("-created_at")

    if query:
        friends_list = friends_list.filter(username__icontains=query)
        suggested_users = suggested_users.filter(username__icontains=query)
        recommendations = recommendations.filter(
            Q(from_user__username__icontains=query)
            | Q(item__title__icontains=query)
            | Q(message__icontains=query)
        )

    return render(
        request,
        "posts/friends.html",
        {
            "friends": friends_list,
            "suggested_users": suggested_users,
            "recommendations": recommendations,
            "query": query,
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


@login_required
def profile(request):
    friend_count = Friendship.objects.filter(from_user=request.user).count()
    review_count = Review.objects.filter(user=request.user).count()
    recommendation_count = Recommendation.objects.filter(to_user=request.user).count()
    recent_reviews = Review.objects.filter(
        user=request.user
    ).select_related("item").order_by("-created_at")[:5]
    top_types = Review.objects.filter(user=request.user).values(
        "item__item_type"
    ).annotate(
        total=Count("id")
    ).order_by("-total")

    return render(
        request,
        "posts/profile.html",
        {
            "friend_count": friend_count,
            "review_count": review_count,
            "recommendation_count": recommendation_count,
            "recent_reviews": recent_reviews,
            "top_types": top_types,
        },
    )
