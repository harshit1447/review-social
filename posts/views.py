from django.contrib.auth.decorators import login_required
from django.contrib.auth import login
from django.contrib.auth.models import User
from django.contrib import messages
from django.core.cache import cache
from django.db.models import Avg, Count, Q
from django.core.paginator import Paginator
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.views.generic import CreateView, DetailView, ListView
from urllib.parse import parse_qs, quote, unquote, urlencode, urlparse
from urllib.request import Request, urlopen
import json
import os
import re

from .forms import CollectionForm, CommentForm, ProfileForm, RecommendationForm, ReviewEditForm, ReviewForm, SignUpForm
from .models import (
    Activity,
    Collection,
    CollectionItem,
    Comment,
    CommentLike,
    Follow,
    Friendship,
    Item,
    Notification,
    Profile,
    Recommendation,
    Review,
    ReviewLike,
    SavedItem,
    SavedReview,
)


def _cache_slug(value):
    return re.sub(r"[^a-z0-9:_-]+", "-", (value or "").lower()).strip("-")


def _followed_user_ids(user):
    follow_ids = set(Follow.objects.filter(follower=user).values_list("following_id", flat=True))
    friendship_ids = set(Friendship.objects.filter(from_user=user).values_list("to_user_id", flat=True))
    return follow_ids | friendship_ids


def _display_name(user):
    return user.get_full_name() or user.username


def _save_list_type_for_item(item):
    return "readlist" if item.item_type == "book" else "watchlist"


def _item_action_state(user, item):
    if not user.is_authenticated:
        return {
            "like_active": False,
            "save_active": False,
            "recommended_active": False,
            "save_list_type": _save_list_type_for_item(item),
        }
    save_list_type = _save_list_type_for_item(item)
    saved_rows = set(
        SavedItem.objects.filter(user=user, item=item).values_list("list_type", flat=True)
    )
    return {
        "like_active": "favorites" in saved_rows,
        "save_active": save_list_type in saved_rows,
        "recommended_active": Recommendation.objects.filter(
            from_user=user,
            item=item,
        ).exists(),
        "save_list_type": save_list_type,
    }


def _hydrate_review_card_counts(reviews):
    review_ids = [review.id for review in reviews if getattr(review, "id", None)]
    if not review_ids:
        return
    rows = Review.objects.filter(id__in=review_ids).annotate(
        likes_total=Count(
            "item__saved_entries",
            filter=Q(item__saved_entries__list_type="favorites"),
            distinct=True,
        ),
        review_like_total=Count("likes", distinct=True),
        comment_total=Count("comments", distinct=True),
    ).values("id", "likes_total", "review_like_total", "comment_total")
    counts = {row["id"]: row for row in rows}
    for review in reviews:
        row = counts.get(review.id, {})
        review.likes_total = row.get("likes_total", getattr(review, "likes_total", 0))
        review.review_like_total = row.get("review_like_total", getattr(review, "review_like_total", 0))
        review.comment_total = row.get("comment_total", getattr(review, "comment_total", 0))


def _review_card_action_context(user, reviews):
    item_ids = [review.item_id for review in reviews if getattr(review, "item_id", None)]
    review_ids = [review.id for review in reviews if getattr(review, "id", None)]
    context = {
        "watchlist_item_ids": set(),
        "readlist_item_ids": set(),
        "favorite_item_ids": set(),
        "saved_review_ids": set(),
        "recommended_item_ids": set(),
        "review_liked_ids": set(),
    }
    if not user.is_authenticated or not item_ids:
        return context
    context["watchlist_item_ids"] = set(
        SavedItem.objects.filter(user=user, list_type="watchlist", item_id__in=item_ids).values_list("item_id", flat=True)
    )
    context["readlist_item_ids"] = set(
        SavedItem.objects.filter(user=user, list_type="readlist", item_id__in=item_ids).values_list("item_id", flat=True)
    )
    context["favorite_item_ids"] = set(
        SavedItem.objects.filter(user=user, list_type="favorites", item_id__in=item_ids).values_list("item_id", flat=True)
    )
    context["recommended_item_ids"] = set(
        Recommendation.objects.filter(from_user=user, item_id__in=item_ids).values_list("item_id", flat=True)
    )
    if review_ids:
        context["saved_review_ids"] = set(
            SavedReview.objects.filter(user=user, review_id__in=review_ids).values_list("review_id", flat=True)
        )
        context["review_liked_ids"] = set(
            ReviewLike.objects.filter(user=user, review_id__in=review_ids).values_list("review_id", flat=True)
        )
    return context


def _create_activity(user, activity_type, message="", review=None, target_user=None, collection=None):
    return Activity.objects.create(
        user=user,
        activity_type=activity_type,
        message=message,
        review=review,
        target_user=target_user,
        collection=collection,
    )


def _notify(recipient, actor, notification_type, message, review=None, comment=None):
    if recipient == actor:
        return None
    return Notification.objects.create(
        recipient=recipient,
        actor=actor,
        notification_type=notification_type,
        message=message,
        review=review,
        comment=comment,
    )


def landing(request):
    if request.user.is_authenticated:
        return redirect("feed")
    return render(request, "landing.html")


def _item_queryset_for_type(item_type):
    return Item.objects.filter(item_type=item_type).annotate(
        review_total=Count("reviews", distinct=True),
        average_rating=Avg("reviews__rating"),
    )


def _category_label(item_type):
    labels = {
        "movie": "Movies",
        "series": "Series",
        "book": "Books",
    }
    return labels.get(item_type, "Items")


CONTENT_GENRE_BUCKETS = [
    {
        "slug": "rom-com",
        "label": "Rom-com",
        "keywords": ("rom-com", "romance", "romantic", "love", "wedding", "date", "couple"),
    },
    {
        "slug": "thriller",
        "label": "Thriller",
        "keywords": ("thriller", "mystery", "crime", "murder", "spy", "suspense", "detective"),
    },
    {
        "slug": "action",
        "label": "Action",
        "keywords": ("action", "revenge", "war", "fight", "mission", "agent", "heist", "superhero"),
    },
    {
        "slug": "sci-fi",
        "label": "Sci-fi",
        "keywords": ("sci-fi", "science fiction", "space", "future", "alien", "robot", "time"),
    },
    {
        "slug": "drama",
        "label": "Drama",
        "keywords": ("drama", "family", "coming", "biography", "true story", "college", "friend"),
    },
    {
        "slug": "comedy",
        "label": "Comedy",
        "keywords": ("comedy", "funny", "satire", "sitcom", "humor", "laugh"),
    },
    {
        "slug": "fantasy",
        "label": "Fantasy",
        "keywords": ("fantasy", "magic", "wizard", "kingdom", "myth", "dragon", "supernatural"),
    },
    {
        "slug": "horror",
        "label": "Horror",
        "keywords": ("horror", "scary", "ghost", "haunted", "monster", "slasher"),
    },
    {
        "slug": "crime",
        "label": "Crime",
        "keywords": ("crime", "police", "court", "law", "legal", "gangster", "mafia"),
    },
]


TMDB_GENRE_MAP = {
    "rom-com": {"movie": "10749,35", "series": "18,35"},
    "thriller": {"movie": "53", "series": "9648"},
    "action": {"movie": "28", "series": "10759"},
    "sci-fi": {"movie": "878", "series": "10765"},
    "drama": {"movie": "18", "series": "18"},
    "comedy": {"movie": "35", "series": "35"},
    "fantasy": {"movie": "14", "series": "10765"},
    "horror": {"movie": "27", "series": "9648"},
    "crime": {"movie": "80", "series": "80"},
}


BOOK_GENRE_BUCKETS = [
    {
        "slug": "fiction",
        "label": "Fiction",
        "query": "popular fiction books",
        "keywords": ("novel", "fiction", "story", "literary", "characters"),
    },
    {
        "slug": "mystery",
        "label": "Mystery",
        "query": "mystery thriller books",
        "keywords": ("mystery", "thriller", "crime", "detective", "murder", "suspense"),
    },
    {
        "slug": "romance",
        "label": "Romance",
        "query": "romance books",
        "keywords": ("romance", "love", "relationship", "wedding", "heart"),
    },
    {
        "slug": "fantasy",
        "label": "Fantasy",
        "query": "fantasy books",
        "keywords": ("fantasy", "magic", "wizard", "kingdom", "dragon", "myth"),
    },
    {
        "slug": "sci-fi",
        "label": "Sci-fi",
        "query": "science fiction books",
        "keywords": ("science fiction", "sci-fi", "space", "future", "alien", "robot"),
    },
    {
        "slug": "business",
        "label": "Business",
        "query": "business economics startup books",
        "keywords": ("business", "startup", "economics", "money", "market", "company"),
    },
    {
        "slug": "self-help",
        "label": "Self-help",
        "query": "self help habit productivity books",
        "keywords": ("self-help", "habit", "productivity", "mindset", "psychology", "life"),
    },
    {
        "slug": "biography",
        "label": "Biography",
        "query": "biography memoir books",
        "keywords": ("biography", "memoir", "life of", "autobiography", "true story"),
    },
]


def _genre_haystack(item, extra_text=""):
    return " ".join(
        [
            item.title or "",
            item.description or "",
            item.creator_name or "",
            item.cast_names or "",
            extra_text or "",
        ]
    ).lower()


def _infer_content_genre(item, extra_text=""):
    if not item or item.item_type not in {"movie", "series"}:
        return None
    haystack = _genre_haystack(item, extra_text)
    for bucket in CONTENT_GENRE_BUCKETS:
        if any(keyword in haystack for keyword in bucket["keywords"]):
            return {"slug": bucket["slug"], "label": bucket["label"]}
    return None


def _attach_genres_to_reviews(reviews):
    for review in reviews:
        genre = _infer_content_genre(review.item, review.review_text)
        review.inferred_genre_slug = genre["slug"] if genre else ""
        review.inferred_genre_label = genre["label"] if genre else ""
    return reviews


def _filter_reviews_by_genre(reviews, genre_slug):
    if not genre_slug:
        return list(reviews)
    rows = []
    for review in reviews:
        genre = _infer_content_genre(review.item, review.review_text)
        if genre and genre["slug"] == genre_slug:
            review.inferred_genre_slug = genre["slug"]
            review.inferred_genre_label = genre["label"]
            rows.append(review)
    return rows


def _content_genre_sections(reviews):
    sections = []
    assigned_review_ids = set()
    review_rows = list(reviews)
    for bucket in CONTENT_GENRE_BUCKETS:
        rows = []
        for review in review_rows:
            genre = _infer_content_genre(review.item, review.review_text)
            if genre and genre["slug"] == bucket["slug"]:
                review.inferred_genre_slug = genre["slug"]
                review.inferred_genre_label = genre["label"]
                rows.append(review)
                assigned_review_ids.add(review.id)
            if len(rows) == 3:
                break
        sections.append({**bucket, "reviews": rows})

    remaining = [review for review in review_rows if review.id not in assigned_review_ids][:3]
    sections.append(
        {
            "slug": "hidden-gems",
            "label": "Hidden gems",
            "keywords": (),
            "reviews": remaining,
        }
    )
    return sections


def category_page(request, item_type):
    if item_type not in {"movie", "series", "book"}:
        return redirect("discover")

    items = _item_queryset_for_type(item_type).select_related()
    recently_reviewed = list(
        Review.objects.filter(item__item_type=item_type)
        .select_related("user", "user__profile", "item")
        .order_by("-created_at")[:8]
    )
    _attach_genres_to_reviews(recently_reviewed)
    top_rated = items.filter(review_total__gt=0).order_by("-average_rating", "-review_total", "title")[:8]
    active_items = items.filter(review_total__gt=0).order_by("-review_total", "title")[:8]

    return render(
        request,
        "posts/category_page.html",
        {
            "item_type": item_type,
            "category_label": _category_label(item_type),
            "recently_reviewed": recently_reviewed,
            "top_rated": top_rated,
            "active_items": active_items,
        },
    )


@login_required
def people_discovery(request):
    query = request.GET.get("q", "").strip()
    followed_ids = _followed_user_ids(request.user)
    people = User.objects.select_related("profile").exclude(id=request.user.id)
    if query:
        people = people.filter(
            Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(username__icontains=query)
            | Q(email__icontains=query)
        )
    people = people.annotate(review_total=Count("review", distinct=True)).order_by("-review_total", "first_name", "username")[:30]

    current_types = set(
        Review.objects.filter(user=request.user).values_list("item__item_type", flat=True)
    )
    people_cards = []
    for index, person in enumerate(people):
        person_types = set(Review.objects.filter(user=person).values_list("item__item_type", flat=True))
        overlap = len(current_types & person_types)
        base_match = 58 + min(overlap * 12, 30) + min(getattr(person, "review_total", 0), 10)
        top_favourites = (
            Review.objects.filter(user=person)
            .select_related("item")
            .order_by("-rating", "-created_at")
            .values_list("item__title", flat=True)[:3]
        )
        people_cards.append(
            {
                "user": person,
                "match": min(base_match + (index % 4) * 2, 96),
                "top_favourites": list(top_favourites),
                "is_following": person.id in followed_ids,
            }
        )

    return render(
        request,
        "posts/people.html",
        {
            "query": query,
            "people_cards": people_cards,
        },
    )


@login_required
def recommendations_page(request):
    raw_likes = request.GET.get("likes", "").strip()
    liked_terms = [term.strip() for term in raw_likes.replace("\n", ",").split(",") if term.strip()]

    user_types = list(
        Review.objects.filter(user=request.user)
        .values("item__item_type")
        .annotate(total=Count("id"))
        .order_by("-total")
        .values_list("item__item_type", flat=True)
    )
    preferred_types = user_types or ["series", "movie", "book"]
    exclude_titles = {term.lower() for term in liked_terms}
    exclude_ids = set(Review.objects.filter(user=request.user).values_list("item_id", flat=True))
    candidate_items = (
        Item.objects.filter(item_type__in=preferred_types)
        .exclude(id__in=exclude_ids)
        .annotate(review_total=Count("reviews", distinct=True), average_rating=Avg("reviews__rating"))
        .order_by("-review_total", "-average_rating", "title")[:30]
    )

    recommendations = []
    for item in candidate_items:
        if item.title.lower() in exclude_titles:
            continue
        if liked_terms:
            reason = f"Because you liked {liked_terms[0]}, this fits your {item.get_item_type_display().lower()} taste profile."
        elif item.review_total:
            reason = f"{item.review_total} Revue review{'' if item.review_total == 1 else 's'} make this a good next title to explore."
        else:
            reason = "A useful starter pick while Revue learns your taste."
        recommendations.append({"item": item, "reason": reason})
        if len(recommendations) >= 8:
            break

    return render(
        request,
        "posts/recommendations.html",
        {
            "likes": raw_likes,
            "liked_terms": liked_terms,
            "recommendations": recommendations,
            "needs_more_reviews": Review.objects.filter(user=request.user).count() < 10,
        },
    )


FALLBACK_TITLE_SUGGESTIONS = [
        {"title": "Inception", "item_type": "movie", "year": "2010", "creator": "Christopher Nolan", "image_url": ""},
        {"title": "Interstellar", "item_type": "movie", "year": "2014", "creator": "Christopher Nolan", "image_url": ""},
        {"title": "The Social Network", "item_type": "movie", "year": "2010", "creator": "David Fincher", "image_url": ""},
        {"title": "3 Idiots", "item_type": "movie", "year": "2009", "creator": "Rajkumar Hirani", "image_url": ""},
        {"title": "Shutter Island", "item_type": "movie", "year": "2010", "creator": "Martin Scorsese", "image_url": ""},
        {"title": "The Dark Knight", "item_type": "movie", "year": "2008", "creator": "Christopher Nolan", "image_url": ""},
        {"title": "Dune: Part Two", "item_type": "movie", "year": "2024", "creator": "Denis Villeneuve", "image_url": ""},
        {"title": "Parasite", "item_type": "movie", "year": "2019", "creator": "Bong Joon Ho", "image_url": ""},
        {"title": "Succession", "item_type": "series", "year": "2018", "creator": "Jesse Armstrong", "image_url": ""},
        {"title": "Brooklyn Nine-Nine", "item_type": "series", "year": "2013", "creator": "Dan Goor, Michael Schur", "image_url": ""},
        {"title": "Fool Me Once", "item_type": "series", "year": "2024", "creator": "Harlan Coben", "image_url": ""},
        {"title": "Maamla Legal Hai", "item_type": "series", "year": "2024", "creator": "Sameer Saxena", "image_url": ""},
        {"title": "Suits", "item_type": "series", "year": "2011", "creator": "Aaron Korsh", "image_url": ""},
        {"title": "Silo", "item_type": "series", "year": "2023", "creator": "Graham Yost", "image_url": ""},
        {"title": "Severance", "item_type": "series", "year": "2022", "creator": "Dan Erickson", "image_url": ""},
        {"title": "Modern Family", "item_type": "series", "year": "2009", "creator": "Christopher Lloyd, Steven Levitan", "image_url": ""},
        {"title": "Stranger Things", "item_type": "series", "year": "2016", "creator": "The Duffer Brothers", "image_url": ""},
        {"title": "Sherlock", "item_type": "series", "year": "2010", "creator": "Mark Gatiss, Steven Moffat", "image_url": ""},
        {"title": "Peaky Blinders", "item_type": "series", "year": "2013", "creator": "Steven Knight", "image_url": ""},
        {"title": "Atomic Habits", "item_type": "book", "year": "2018", "creator": "James Clear", "image_url": "https://covers.openlibrary.org/b/isbn/9780735211292-L.jpg"},
        {"title": "Good Economics for Hard Times", "item_type": "book", "year": "2019", "creator": "Abhijit Banerjee, Esther Duflo", "image_url": "https://covers.openlibrary.org/b/isbn/9781541762879-L.jpg"},
        {"title": "The Midnight Library", "item_type": "book", "year": "2020", "creator": "Matt Haig", "image_url": "https://covers.openlibrary.org/b/isbn/9780525559474-L.jpg"},
        {"title": "The Fault in Our Stars", "item_type": "book", "year": "2012", "creator": "John Green", "image_url": "https://covers.openlibrary.org/b/isbn/9780525478812-L.jpg"},
        {"title": "Looking for Alaska", "item_type": "book", "year": "2005", "creator": "John Green", "image_url": "https://covers.openlibrary.org/b/isbn/9780142402511-L.jpg"},
        {"title": "The Alchemist", "item_type": "book", "year": "1988", "creator": "Paulo Coelho", "image_url": "https://covers.openlibrary.org/b/isbn/9780061122415-L.jpg"},
        {"title": "The Psychology of Money", "item_type": "book", "year": "2020", "creator": "Morgan Housel", "image_url": "https://covers.openlibrary.org/b/isbn/9780857197689-L.jpg"},
        {"title": "Sapiens: A Brief History of Humankind", "item_type": "book", "year": "2011", "creator": "Yuval Noah Harari", "image_url": "https://covers.openlibrary.org/b/isbn/9780062316097-L.jpg"},
        {"title": "Ikigai", "item_type": "book", "year": "2016", "creator": "Hector Garcia, Francesc Miralles", "image_url": "https://covers.openlibrary.org/b/isbn/9780143130727-L.jpg"},
        {"title": "The Kite Runner", "item_type": "book", "year": "2003", "creator": "Khaled Hosseini", "image_url": "https://covers.openlibrary.org/b/isbn/9781594631931-L.jpg"},
        {"title": "A Thousand Splendid Suns", "item_type": "book", "year": "2007", "creator": "Khaled Hosseini", "image_url": "https://covers.openlibrary.org/b/isbn/9781594483851-L.jpg"},
    ]


DISCOVER_RAIL_SECTIONS = [
    {
        "title": "Talk of the town",
        "kicker": "Fresh picks people are opening now",
        "items": [
            {"title": "Obsession", "item_type": "series", "year": "2023", "creator": "Morgan Lloyd Malcolm", "tag": "New show", "description": "A tense limited series about desire, secrets, and consequences."},
            {"title": "Spider-Noir", "item_type": "series", "year": "2026", "creator": "Oren Uziel", "tag": "New show", "description": "A noir-inspired superhero mystery with a shadowy city at its center."},
            {"title": "Cocktail 2", "item_type": "movie", "year": "2026", "creator": "Homi Adajania", "tag": "Trailer", "description": "Friendship, romance, and messy choices return in a breezy ensemble story."},
            {"title": "The Great Grand Superhero", "item_type": "movie", "year": "2026", "creator": "Indra Kumar", "tag": "New movie", "description": "A loud, comic superhero adventure built for easy weekend watching."},
            {"title": "Drishyam 3", "item_type": "movie", "year": "2026", "creator": "Jeethu Joseph", "tag": "New movie", "description": "The family thriller continues with another carefully guarded secret."},
            {"title": "Euphoria", "item_type": "series", "year": "2019", "creator": "Sam Levinson", "tag": "Series", "description": "A stylized teen drama about identity, friendship, and self-destruction."},
        ],
    },
    {
        "title": "Watch it with friends",
        "kicker": "Easy group-watch candidates",
        "items": [
            {"title": "The Mandalorian and Grogu", "item_type": "movie", "year": "2026", "creator": "Jon Favreau", "tag": "Movie", "description": "A new Star Wars adventure built around a familiar duo."},
            {"title": "Karuppu", "item_type": "movie", "year": "2026", "creator": "R. J. Balaji", "tag": "Movie", "description": "A high-energy Tamil drama with action and emotion."},
            {"title": "Chand Mera Dil", "item_type": "movie", "year": "2026", "creator": "Vivek Soni", "tag": "Movie", "description": "A romantic drama with a late-night mood."},
            {"title": "Hokum", "item_type": "movie", "year": "2026", "creator": "Unknown director", "tag": "Movie", "description": "A dark title people are curious about this week."},
            {"title": "Pati Patni Aur Woh Do", "item_type": "movie", "year": "2026", "creator": "Mudassar Aziz", "tag": "Movie", "description": "A comedy of errors around relationships and timing."},
            {"title": "Mortal Kombat II", "item_type": "movie", "year": "2026", "creator": "Simon McQuoid", "tag": "Movie", "description": "A tournament action spectacle for game-to-film fans."},
        ],
    },
    {
        "title": "Worth watching on Prime",
        "kicker": "Shows and films for your next queue",
        "items": [
            {"title": "Spider-Noir", "item_type": "series", "year": "2026", "creator": "Oren Uziel", "tag": "Show", "description": "A stylish, shadow-heavy superhero story."},
            {"title": "Ela Veezha Poonchira", "item_type": "movie", "year": "2022", "creator": "Shahi Kabir", "tag": "Movie", "description": "A Malayalam thriller set around an isolated police outpost."},
            {"title": "The Salesman", "item_type": "movie", "year": "2016", "creator": "Asghar Farhadi", "tag": "Movie", "description": "A tense drama about trauma, pride, and revenge."},
            {"title": "Evangelion: 3.0+1.0 Thrice Upon a Time", "item_type": "movie", "year": "2021", "creator": "Hideaki Anno", "tag": "Movie", "description": "A reflective, maximal finale to a landmark anime saga."},
            {"title": "Alienoid: Return to the Future", "item_type": "movie", "year": "2024", "creator": "Choi Dong-hoon", "tag": "Movie", "description": "A genre-blending Korean sci-fi fantasy sequel."},
        ],
    },
    {
        "title": "Books people keep recommending",
        "kicker": "Fast starts for your reading list",
        "items": [
            {"title": "Atomic Habits", "item_type": "book", "year": "2018", "creator": "James Clear", "tag": "Book", "description": "A practical guide to improving systems and habits.", "image_url": "https://covers.openlibrary.org/b/isbn/9780735211292-L.jpg"},
            {"title": "Good Economics for Hard Times", "item_type": "book", "year": "2019", "creator": "Abhijit Banerjee, Esther Duflo", "tag": "Book", "description": "Clear thinking on inequality, growth, and policy.", "image_url": "https://covers.openlibrary.org/b/isbn/9781541762879-L.jpg"},
            {"title": "The Midnight Library", "item_type": "book", "year": "2020", "creator": "Matt Haig", "tag": "Book", "description": "A warm novel about regret, choices, and possible lives.", "image_url": "https://covers.openlibrary.org/b/isbn/9780525559474-L.jpg"},
            {"title": "Project Hail Mary", "item_type": "book", "year": "2021", "creator": "Andy Weir", "tag": "Book", "description": "A funny, puzzle-like survival story in deep space.", "image_url": "https://covers.openlibrary.org/b/isbn/9780593135204-L.jpg"},
            {"title": "Tomorrow, and Tomorrow, and Tomorrow", "item_type": "book", "year": "2022", "creator": "Gabrielle Zevin", "tag": "Book", "description": "A novel about games, friendship, ambition, and art.", "image_url": "https://covers.openlibrary.org/b/isbn/9780593321201-L.jpg"},
        ],
    },
]


def _catalog_rows():
    rows = []
    for section in DISCOVER_RAIL_SECTIONS:
        for row in section["items"]:
            rows.append(row)
    return rows


def _catalog_suggestions(query, item_types=None):
    normalized_query = query.lower().strip()
    compact_query = normalized_query.replace(" ", "")
    allowed_types = set(item_types or ["movie", "series", "book"])
    results = []
    seen = set()
    for row in _catalog_rows():
        if row["item_type"] not in allowed_types:
            continue
        title = row["title"]
        compact_title = title.lower().replace(" ", "")
        if normalized_query not in title.lower() and compact_query not in compact_title:
            continue
        key = f"catalog:{row['item_type']}:{title.lower()}"
        if key in seen:
            continue
        seen.add(key)
        results.append(
            {
                **row,
                "key": key,
                "image_url": row.get("image_url", ""),
                "external_source": "catalog",
                "external_id": key,
                "source": "catalog",
            }
        )
    return results


def _preview_url_for_payload(row):
    params = {
        "preview": "1",
        "item_type": row.get("item_type", "movie"),
        "year": row.get("year", ""),
        "creator": row.get("creator", ""),
        "description": row.get("description", ""),
        "image_url": row.get("image_url", ""),
        "external_source": row.get("external_source", "catalog"),
        "external_id": row.get("external_id", ""),
    }
    return f"/review/{quote(row.get('title', '').strip())}/?{urlencode(params)}"


def _discover_rail_sections():
    local_items = Item.objects.filter(
        title__in=[row["title"] for row in _catalog_rows()],
        item_type__in=["movie", "series", "book"],
    )
    local_by_key = {
        (item.title.lower(), item.item_type): item
        for item in local_items
    }
    sections = []
    for section in DISCOVER_RAIL_SECTIONS:
        section_rows = []
        for seed in section["items"]:
            item = local_by_key.get((seed["title"].lower(), seed["item_type"]))
            row = {
                **seed,
                "image_url": item.image_url if item and item.image_url else seed.get("image_url", ""),
                "review_total": item.reviews.count() if item and item.pk else 0,
                "external_source": item.external_source if item and item.external_source else "catalog",
                "external_id": item.external_id if item and item.external_id else f"catalog:{seed['item_type']}:{seed['title'].lower()}",
            }
            if item and item.pk:
                row["url"] = reverse("item_reviews", args=[item.title])
            else:
                row["url"] = _preview_url_for_payload(row)
            section_rows.append(row)
        sections.append({**section, "items": section_rows})

    tmdb_sections = [
        {
            "title": "Talk of the town",
            "kicker": "Trending movies and shows from TMDB",
            "rows": _tmdb_discover_rows("trending/all/week", "movie", 12),
        },
        {
            "title": "Movies people are opening",
            "kicker": "Popular films to review next",
            "rows": _tmdb_discover_rows("movie/popular", "movie", 12),
        },
        {
            "title": "Series worth tracking",
            "kicker": "Popular shows to follow and discuss",
            "rows": _tmdb_discover_rows("tv/popular", "series", 12),
        },
    ]
    live_sections = []
    for section in tmdb_sections:
        rows = section["rows"]
        if not rows:
            continue
        for row in rows:
            row["url"] = _preview_url_for_payload(row)
        live_sections.append({"title": section["title"], "kicker": section["kicker"], "items": rows})
    if live_sections:
        return live_sections + sections[-1:]
    return sections


def _book_discover_sections():
    cache_key = "book_discover_sections:v2"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    section_specs = [
        {
            "title": "Latest books",
            "kicker": "Fresh titles to open and review",
            "query": "subject:fiction",
            "order_by": "newest",
        },
        {
            "title": "Books people keep recommending",
            "kicker": "Reliable starts for your reading list",
            "query": "popular books",
            "order_by": "relevance",
        },
        {
            "title": "Useful non-fiction",
            "kicker": "Ideas, business, behaviour, and better thinking",
            "query": "subject:business subject:psychology",
            "order_by": "relevance",
        },
        {
            "title": "Fiction worth browsing",
            "kicker": "Stories people can build a taste profile around",
            "query": "subject:literary fiction",
            "order_by": "relevance",
        },
    ]
    sections = []
    seen_titles = set()

    for spec in section_specs:
        rows = []
        sources = _google_books_suggestions(spec["query"], max_results=18, order_by=spec["order_by"])
        if len(sources) < 8:
            sources += _openlibrary_suggestions(spec["query"])
        for row in sources:
            title = (row.get("title") or "").strip()
            if not title:
                continue
            dedupe_key = f"{spec['title']}:{title.lower()}"
            if dedupe_key in seen_titles:
                continue
            seen_titles.add(dedupe_key)
            row = {
                **row,
                "item_type": "book",
                "tag": "Book",
                "external_source": row.get("external_source") or row.get("source") or "googlebooks",
            }
            row["url"] = _preview_url_for_payload(row)
            rows.append(row)
            if len(rows) >= 12:
                break
        if rows:
            sections.append({"title": spec["title"], "kicker": spec["kicker"], "items": rows})

    curated_book_sections = [
        {**section, "items": [row for row in section.get("items", []) if row.get("item_type") == "book"]}
        for section in _discover_rail_sections()
    ]
    curated_book_sections = [section for section in curated_book_sections if section["items"]]
    for section in curated_book_sections:
        for row in section["items"]:
            row.setdefault("url", _preview_url_for_payload(row))
    fallback_book_rows = []
    fallback_seen = set()
    for row in FALLBACK_TITLE_SUGGESTIONS + _catalog_rows():
        if row.get("item_type") != "book":
            continue
        title = (row.get("title") or "").strip()
        if not title or title.lower() in fallback_seen:
            continue
        fallback_seen.add(title.lower())
        payload = {
            **row,
            "item_type": "book",
            "tag": "Book",
            "external_source": row.get("external_source") or "catalog",
            "external_id": row.get("external_id") or f"catalog:book:{title.lower()}",
        }
        payload["url"] = _preview_url_for_payload(payload)
        fallback_book_rows.append(payload)

    if len(sections) < 2:
        sections.extend(curated_book_sections)
    else:
        sections.extend(curated_book_sections[:1])
    if fallback_book_rows and not any(section.get("title") == "Books people keep recommending" for section in sections):
        sections.append(
            {
                "title": "Books people keep recommending",
                "kicker": "Reliable starts for your reading list",
                "items": fallback_book_rows[:12],
            }
        )
    if not sections and fallback_book_rows:
        sections.append(
            {
                "title": "Books people keep recommending",
                "kicker": "Reliable starts for your reading list",
                "items": fallback_book_rows[:12],
            }
        )

    cache.set(cache_key, sections, 21600)
    return sections


def _book_matches_genre(item, genre_slug, extra_text=""):
    bucket = next((row for row in BOOK_GENRE_BUCKETS if row["slug"] == genre_slug), None)
    if not bucket or not item:
        return False
    haystack = _genre_haystack(item, extra_text)
    return any(keyword in haystack for keyword in bucket["keywords"])


def _fallback_title_suggestions(query, item_types=None):
    normalized_query = query.lower().strip()
    compact_query = normalized_query.replace(" ", "")
    allowed_types = set(item_types or ["movie", "series", "book"])
    results = []
    for row in FALLBACK_TITLE_SUGGESTIONS:
        if row["item_type"] not in allowed_types:
            continue
        title = row["title"]
        compact_title = title.lower().replace(" ", "")
        if normalized_query not in title.lower() and compact_query not in compact_title:
            continue
        results.append({**row, "key": f"fallback:{row['item_type']}:{title.lower()}", "external_source": "", "external_id": "", "source": "fallback"})
    results.extend(_catalog_suggestions(query, item_types))
    return results


def landing_suggest_items(request):
    query = request.GET.get("q", "").strip()
    if len(query) < 2:
        return JsonResponse({"results": []})

    cache_key = f"landing_suggest:v6:{_cache_slug(query)}"
    cached = cache.get(cache_key)
    if cached is not None:
        return JsonResponse({"results": cached})

    results = []
    seen = set()

    existing = Item.objects.filter(
        title__icontains=query,
        item_type__in=["movie", "series", "book"],
    ).order_by("title").values("title", "item_type", "release_year", "creator_name", "image_url")

    def add_row(row):
        title = (row.get("title") or "").strip()
        item_type = row.get("item_type", "")
        key = f"{title.lower()}:{row.get('year') or row.get('release_year', '')}:{item_type}"
        if not title or not item_type or key in seen:
            return
        if item_type not in {"movie", "series", "book"}:
            return
        seen.add(key)
        results.append(
            {
                "title": title,
                "item_type": item_type,
                "year": row.get("year") or row.get("release_year", ""),
                "creator": row.get("creator") or row.get("creator_name", ""),
                "image_url": row.get("image_url", ""),
                "external_source": row.get("external_source", ""),
                "external_id": row.get("external_id", ""),
            }
        )

    for row in existing:
        add_row(row)

    for row in _fallback_title_suggestions(query, ["movie", "series", "book"]):
        add_row(row)

    if len(query) >= 3:
        for row_type in ("movie", "series"):
            external_rows = _tmdb_suggestions(query, row_type)
            if not external_rows:
                external_rows = _omdb_fast_suggestions(query, row_type)
            for row in external_rows:
                add_row(row)
    if len(query) >= 4:
        for row in _google_books_suggestions(query):
            add_row(row)

    cache.set(cache_key, results, 300)
    return JsonResponse({"results": results})


def _json_get(url: str, timeout: int = 4):
    request = Request(
        url,
        headers={
            "User-Agent": "RevueReviewApp/1.0 (local development)",
            "Accept": "application/json",
        },
    )
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w500"


def _tmdb_api_key():
    return os.environ.get("TMDB_API_KEY", "").strip()


def _tmdb_image_url(path):
    return f"{TMDB_IMAGE_BASE}{path}" if path else ""


def _tmdb_year(row, item_type):
    raw_date = row.get("release_date") if item_type == "movie" else row.get("first_air_date")
    return (raw_date or "")[:4]


def _tmdb_title(row, item_type):
    return (row.get("title") if item_type == "movie" else row.get("name")) or ""


def _tmdb_suggestions(query: str, item_type: str):
    api_key = _tmdb_api_key()
    if not api_key or not query or item_type not in {"movie", "series"}:
        return []

    tmdb_kind = "movie" if item_type == "movie" else "tv"
    cache_key = f"tmdb_suggestions:v2:{item_type}:{_cache_slug(query)}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        params = urlencode(
            {
                "api_key": api_key,
                "query": query,
                "include_adult": "false",
                "language": "en-US",
                "page": 1,
            }
        )
        payload = _json_get(f"https://api.themoviedb.org/3/search/{tmdb_kind}?{params}", timeout=3)
    except Exception:
        return []

    results = []
    for row in payload.get("results", []):
        title = _tmdb_title(row, item_type).strip()
        tmdb_id = row.get("id")
        if not title or not tmdb_id:
            continue
        results.append(
            {
                "key": f"tmdb:{item_type}:{tmdb_id}",
                "title": title,
                "item_type": item_type,
                "year": _tmdb_year(row, item_type),
                "creator": "",
                "description": (row.get("overview") or "").strip(),
                "image_url": _tmdb_image_url(row.get("poster_path")),
                "external_source": "tmdb",
                "external_id": f"{item_type}:{tmdb_id}",
                "source": "tmdb",
            }
        )
    cache.set(cache_key, results, 3600)
    return results


def _tmdb_details(external_id: str):
    api_key = _tmdb_api_key()
    if not api_key or not external_id or ":" not in external_id:
        return {}

    item_type, tmdb_id = external_id.split(":", 1)
    if item_type not in {"movie", "series"} or not tmdb_id:
        return {}

    tmdb_kind = "movie" if item_type == "movie" else "tv"
    cache_key = f"tmdb_details:v1:{external_id}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        params = urlencode({"api_key": api_key, "language": "en-US", "append_to_response": "credits,external_ids"})
        payload = _json_get(f"https://api.themoviedb.org/3/{tmdb_kind}/{quote(tmdb_id)}?{params}", timeout=4)
    except Exception:
        return {}

    credits = payload.get("credits") or {}
    cast = [
        person.get("name", "")
        for person in (credits.get("cast") or [])[:4]
        if person.get("name")
    ]
    creator = ""
    if item_type == "movie":
        directors = [
            person.get("name", "")
            for person in (credits.get("crew") or [])
            if person.get("job") == "Director" and person.get("name")
        ]
        creator = ", ".join(directors[:2])
    else:
        creators = payload.get("created_by") or []
        creator = ", ".join([person.get("name", "") for person in creators if person.get("name")][:2])

    year = (payload.get("release_date") or payload.get("first_air_date") or "")[:4]
    rating = payload.get("vote_average")
    metadata = {
        "release_year": year,
        "creator_name": creator,
        "cast_names": ", ".join(cast),
        "description": (payload.get("overview") or "").strip(),
        "image_url": _tmdb_image_url(payload.get("poster_path")),
        "imdb_rating": f"{float(rating):.1f}" if rating else "",
    }
    metadata = {key: value for key, value in metadata.items() if value}
    cache.set(cache_key, metadata, 86400)
    return metadata


def _tmdb_discover_rows(endpoint: str, item_type: str, limit: int = 10):
    api_key = _tmdb_api_key()
    if not api_key or item_type not in {"movie", "series"}:
        return []

    cache_key = f"tmdb_discover:v1:{endpoint}:{item_type}:{limit}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        separator = "&" if "?" in endpoint else "?"
        payload = _json_get(
            f"https://api.themoviedb.org/3/{endpoint}{separator}{urlencode({'api_key': api_key, 'language': 'en-US'})}",
            timeout=4,
        )
    except Exception:
        return []

    rows = []
    for row in payload.get("results", []):
        media_type = row.get("media_type")
        row_type = item_type
        if media_type == "tv":
            row_type = "series"
        elif media_type == "movie":
            row_type = "movie"
        elif media_type and media_type not in {"movie", "tv"}:
            continue

        title = _tmdb_title(row, row_type).strip()
        tmdb_id = row.get("id")
        if not title or not tmdb_id:
            continue
        rows.append(
            {
                "title": title,
                "item_type": row_type,
                "year": _tmdb_year(row, row_type),
                "creator": "",
                "tag": "Movie" if row_type == "movie" else "Show",
                "description": (row.get("overview") or "").strip(),
                "image_url": _tmdb_image_url(row.get("poster_path")),
                "external_source": "tmdb",
                "external_id": f"{row_type}:{tmdb_id}",
            }
        )
        if len(rows) >= limit:
            break

    cache.set(cache_key, rows, 21600)
    return rows


def _tmdb_genre_discover_rows(genre_slug: str, limit: int = 18):
    genre_map = TMDB_GENRE_MAP.get(genre_slug)
    if not genre_map:
        return []
    cache_key = f"tmdb_genre_discover:v1:{genre_slug}:{limit}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    rows = []
    endpoints = [
        ("movie", f"discover/movie?{urlencode({'sort_by': 'popularity.desc', 'with_genres': genre_map['movie'], 'vote_count.gte': 40})}"),
        ("series", f"discover/tv?{urlencode({'sort_by': 'popularity.desc', 'with_genres': genre_map['series'], 'vote_count.gte': 20})}"),
    ]
    for item_type, endpoint in endpoints:
        for row in _tmdb_discover_rows(endpoint, item_type, limit):
            row["score"] = f"{min(95, max(15, (len(rows) + 3) * 5))}%"
            row["url"] = _preview_url_for_payload(row)
            rows.append(row)
            if len(rows) >= limit:
                break
        if len(rows) >= limit:
            break

    if len(rows) < 4:
        local_reviews = Review.objects.select_related("item").filter(item__item_type__in=["movie", "series"]).order_by("-created_at")[:80]
        for review in _filter_reviews_by_genre(local_reviews, genre_slug):
            item = review.item
            rows.append(
                {
                    "title": item.title,
                    "item_type": item.item_type,
                    "year": item.release_year,
                    "creator": item.creator_name,
                    "tag": item.get_item_type_display(),
                    "description": item.description,
                    "image_url": item.image_url,
                    "url": reverse("item_reviews", args=[item.title]),
                    "score": f"{min(95, max(15, review.rating * 15))}%",
                }
            )
            if len(rows) >= limit:
                break

    cache.set(cache_key, rows, 21600)
    return rows


def _youtube_video_id(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.netloc.lower().replace("www.", "")
    if host == "youtu.be":
        return parsed.path.strip("/").split("/")[0]
    if host.endswith("youtube.com"):
        if parsed.path == "/watch":
            return (parse_qs(parsed.query).get("v") or [""])[0]
        parts = [part for part in parsed.path.split("/") if part]
        if parts and parts[0] in {"shorts", "embed", "live"} and len(parts) > 1:
            return parts[1]
    return ""


def _podcast_metadata_from_url(url: str):
    parsed = urlparse(url)
    host = parsed.netloc.lower().replace("www.", "")
    if "youtube.com" in host or host == "youtu.be":
        video_id = _youtube_video_id(url)
        title = ""
        thumbnail_url = ""
        try:
            payload = _json_get(f"https://www.youtube.com/oembed?{urlencode({'url': url, 'format': 'json'})}")
            title = payload.get("title", "")
            thumbnail_url = payload.get("thumbnail_url", "")
        except Exception:
            title = ""
            thumbnail_url = ""
        if video_id:
            return {
                "title": title,
                "external_source": "youtube",
                "external_id": url,
                "image_url": thumbnail_url or f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg",
            }
    if "spotify.com" in host:
        title = ""
        image_url = ""
        try:
            payload = _json_get(f"https://open.spotify.com/oembed?{urlencode({'url': url})}")
            title = payload.get("title", "")
            image_url = payload.get("thumbnail_url", "")
        except Exception:
            title = ""
            image_url = ""
        return {
            "title": title,
            "external_source": "spotify",
            "external_id": url,
            "image_url": image_url,
        }
    return {
        "title": "",
        "external_source": "podcast",
        "external_id": url,
        "image_url": "",
    }


def _first_claim_value(claims, prop):
    values = claims.get(prop) or []
    if not values:
        return ""
    return values[0].get("mainsnak", {}).get("datavalue", {}).get("value", "")


def _wikidata_label(entity_id):
    if not entity_id:
        return ""
    try:
        payload = _json_get(
            f"https://www.wikidata.org/wiki/Special:EntityData/{quote(entity_id)}.json"
        )
    except Exception:
        return ""
    labels = payload.get("entities", {}).get(entity_id, {}).get("labels", {})
    return labels.get("en", {}).get("value", "")


def _wikidata_image_url(filename):
    if not filename:
        return ""
    return f"https://commons.wikimedia.org/wiki/Special:Redirect/file/{quote(filename)}"


def _wikidata_suggestions(query: str, item_type: str):
    type_ids = {
        "movie": {"Q11424"},
        "series": {"Q5398426", "Q1259759"},
        "book": {"Q571", "Q7725634"},
    }
    if item_type not in type_ids:
        return []

    try:
        search_params = urlencode(
            {
                "action": "wbsearchentities",
                "search": query,
                "language": "en",
                "format": "json",
                "limit": 50,
            }
        )
        search_payload = _json_get(f"https://www.wikidata.org/w/api.php?{search_params}")
    except Exception:
        return []

    results = []
    for row in search_payload.get("search", []):
        entity_id = row.get("id")
        if not entity_id:
            continue
        try:
            entity_payload = _json_get(
                f"https://www.wikidata.org/wiki/Special:EntityData/{quote(entity_id)}.json"
            )
        except Exception:
            continue
        entity = entity_payload.get("entities", {}).get(entity_id, {})
        claims = entity.get("claims", {})
        instance_ids = {
            claim.get("mainsnak", {}).get("datavalue", {}).get("value", {}).get("id")
            for claim in claims.get("P31", [])
        }
        if not (instance_ids & type_ids[item_type]):
            continue

        title = entity.get("labels", {}).get("en", {}).get("value", row.get("label", "")).strip()
        if not title:
            continue

        release = _first_claim_value(claims, "P577") or _first_claim_value(claims, "P571")
        if isinstance(release, dict):
            release = release.get("time", "")
        year = release.lstrip("+")[:4] if release else ""

        creator_prop = "P50" if item_type == "book" else "P57"
        creator_value = _first_claim_value(claims, creator_prop)
        creator_id = creator_value.get("id", "") if isinstance(creator_value, dict) else ""
        creator = _wikidata_label(creator_id)

        image_name = _first_claim_value(claims, "P18")
        image_url = _wikidata_image_url(image_name if isinstance(image_name, str) else "")
        results.append(
            {
                "key": f"wikidata:{entity_id}",
                "title": title,
                "item_type": item_type,
                "year": year,
                "creator": creator,
                "image_url": image_url,
                "external_source": "wikidata",
                "external_id": entity_id,
                "source": "wikidata",
            }
        )
    return results


def _google_books_suggestions(query: str, max_results: int = 12, order_by: str = "relevance"):
    if not query:
        return []
    max_results = max(1, min(int(max_results or 12), 40))
    order_by = order_by if order_by in {"relevance", "newest"} else "relevance"
    cache_key = f"google_books_suggestions:v4:{_cache_slug(query)}:{max_results}:{order_by}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    try:
        params = urlencode(
            {
                "q": query,
                "printType": "books",
                "maxResults": max_results,
                "orderBy": order_by,
            }
        )
        payload = _json_get(f"https://www.googleapis.com/books/v1/volumes?{params}", timeout=1.5)
    except Exception:
        return []
    items = payload.get("items", [])
    results = []
    for row in items:
        volume = row.get("volumeInfo", {})
        title = (volume.get("title") or "").strip()
        if not title:
            continue
        published = (volume.get("publishedDate") or "").strip()
        year = published[:4] if published else ""
        authors = volume.get("authors") or []
        creator = authors[0] if authors else ""
        average_rating = volume.get("averageRating")
        image_url = ""
        image_links = volume.get("imageLinks") or {}
        if image_links.get("thumbnail") or image_links.get("smallThumbnail"):
            image_url = (image_links.get("thumbnail") or image_links.get("smallThumbnail") or "").replace("http://", "https://")
        results.append(
            {
                "key": f"googlebooks:{row.get('id', title)}",
                "title": title,
                "item_type": "book",
                "year": year,
                "creator": creator,
                "image_url": image_url,
                "book_rating": str(average_rating) if average_rating else "",
                "book_rating_source": "Google Books" if average_rating else "",
                "external_source": "googlebooks",
                "external_id": row.get("id", ""),
                "source": "google",
            }
        )
    cache.set(cache_key, results, 3600)
    return results


def _openlibrary_suggestions(query: str):
    cache_key = f"openlibrary_suggestions:v3:{_cache_slug(query)}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    try:
        params = urlencode(
            {
                "q": query,
                "fields": "key,title,author_name,first_publish_year,cover_i",
                "limit": 12,
            }
        )
        payload = _json_get(f"https://openlibrary.org/search.json?{params}", timeout=1.5)
    except Exception:
        return []

    results = []
    for row in payload.get("docs", []):
        title = (row.get("title") or "").strip()
        year = str(row.get("first_publish_year") or "")
        authors = row.get("author_name") or []
        creator = authors[0] if authors else ""
        cover_id = row.get("cover_i")
        image_url = f"https://covers.openlibrary.org/b/id/{cover_id}-M.jpg" if cover_id else ""
        results.append(
            {
                "key": f"openlibrary:{row.get('key', title)}",
                "title": title,
                "item_type": "book",
                "year": year,
                "creator": creator,
                "image_url": image_url,
                "external_source": "openlibrary",
                "external_id": row.get("key", ""),
                "source": "openlibrary",
            }
        )
    cache.set(cache_key, results, 3600)
    return results


def _book_genre_discover_rows(genre_slug: str, limit: int = 24):
    bucket = next((row for row in BOOK_GENRE_BUCKETS if row["slug"] == genre_slug), None)
    if not bucket:
        return []
    cache_key = f"book_genre_discover:v2:{genre_slug}:{limit}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    rows = []
    seen = set()

    def add_row(row, score_index=None):
        title = (row.get("title") or "").strip()
        if not title:
            return
        key = f"{title.lower()}:{row.get('year', '')}"
        if key in seen:
            return
        seen.add(key)
        payload = {
            **row,
            "item_type": "book",
            "tag": "Book",
            "score": f"{min(95, max(15, ((score_index if score_index is not None else len(rows)) + 3) * 5))}%",
        }
        payload["url"] = _preview_url_for_payload(payload)
        rows.append(payload)

    for row in _google_books_suggestions(bucket["query"]):
        add_row(row)
        if len(rows) >= limit:
            break

    if len(rows) < limit:
        for row in _openlibrary_suggestions(bucket["query"]):
            add_row(row)
            if len(rows) >= limit:
                break

    if len(rows) < 5:
        local_reviews = Review.objects.select_related("item").filter(item__item_type="book").order_by("-created_at")[:120]
        for review in local_reviews:
            if not _book_matches_genre(review.item, genre_slug, review.review_text):
                continue
            item = review.item
            add_row(
                {
                    "title": item.title,
                    "year": item.release_year,
                    "creator": item.creator_name,
                    "description": item.description,
                    "image_url": item.image_url,
                    "external_source": item.external_source or "local",
                    "external_id": item.external_id or "",
                },
                score_index=review.rating,
            )
            if len(rows) >= limit:
                break

    if len(rows) < 5:
        keywords = bucket["keywords"]
        for seed in FALLBACK_TITLE_SUGGESTIONS + _catalog_rows():
            if seed.get("item_type") != "book":
                continue
            haystack = " ".join(
                [
                    seed.get("title", ""),
                    seed.get("description", ""),
                    seed.get("creator", ""),
                    bucket["label"],
                ]
            ).lower()
            if not any(keyword in haystack for keyword in keywords):
                continue
            add_row(seed)
            if len(rows) >= limit:
                break

    cache.set(cache_key, rows, 21600)
    return rows


def _omdb_suggestions(query: str, item_type: str):
    api_key = os.environ.get("OMDB_API_KEY", "").strip()
    if not query or not api_key or item_type not in {"movie", "series"}:
        return []
    try:
        params = urlencode({"apikey": api_key, "s": query, "type": item_type})
        search_payload = _json_get(f"https://www.omdbapi.com/?{params}")
    except Exception:
        return []

    if search_payload.get("Response") != "True":
        return []

    results = []
    for row in search_payload.get("Search", []):
        imdb_id = row.get("imdbID", "")
        if not imdb_id:
            continue
        detail = {}
        try:
            detail = _json_get(
                f"https://www.omdbapi.com/?{urlencode({'apikey': api_key, 'i': imdb_id})}"
            )
        except Exception:
            detail = {}

        creator = ""
        if detail.get("Director") and detail.get("Director") != "N/A":
            creator = detail["Director"]
        elif detail.get("Writer") and detail.get("Writer") != "N/A":
            creator = detail["Writer"]
        year = (detail.get("Year") or row.get("Year") or "").replace("–", "-").split("-")[0]
        poster = detail.get("Poster") or row.get("Poster") or ""
        if poster == "N/A":
            poster = ""
        results.append(
            {
                "key": f"omdb:{imdb_id}",
                "title": row.get("Title", "").strip(),
                "item_type": item_type,
                "year": year,
                "creator": creator,
                "image_url": poster,
                "external_source": "omdb",
                "external_id": imdb_id,
                "source": "google",
            }
        )
    return results


def _omdb_fast_suggestions(query: str, item_type: str):
    api_key = os.environ.get("OMDB_API_KEY", "").strip()
    if not query or not api_key or item_type not in {"movie", "series"}:
        return []
    try:
        params = urlencode({"apikey": api_key, "s": query, "type": item_type})
        search_payload = _json_get(f"https://www.omdbapi.com/?{params}")
    except Exception:
        return []
    if search_payload.get("Response") != "True":
        return []
    results = []
    for row in search_payload.get("Search", []):
        imdb_id = row.get("imdbID", "")
        if not imdb_id:
            continue
        poster = row.get("Poster") or ""
        if poster == "N/A":
            poster = ""
        results.append(
            {
                "key": f"omdb:{imdb_id}",
                "title": row.get("Title", "").strip(),
                "item_type": item_type,
                "year": (row.get("Year") or "").replace("–", "-").split("-")[0],
                "creator": "",
                "image_url": poster,
                "external_source": "omdb",
                "external_id": imdb_id,
                "source": "omdb",
            }
        )
    return results


def _omdb_details(imdb_id: str):
    api_key = os.environ.get("OMDB_API_KEY", "").strip()
    if not api_key or not imdb_id:
        return {}
    try:
        detail = _json_get(
            f"https://www.omdbapi.com/?{urlencode({'apikey': api_key, 'i': imdb_id, 'plot': 'short'})}",
            timeout=6,
        )
    except Exception:
        return {}
    if detail.get("Response") == "False":
        return {}
    ratings = {row.get("Source"): row.get("Value") for row in detail.get("Ratings", [])}
    poster = detail.get("Poster") or ""
    if poster == "N/A":
        poster = ""
    creator = ""
    if detail.get("Director") and detail.get("Director") != "N/A":
        creator = detail["Director"]
    elif detail.get("Writer") and detail.get("Writer") != "N/A":
        creator = detail["Writer"]
    imdb_rating = detail.get("imdbRating", "")
    return {
        "release_year": (detail.get("Year") or "").replace("–", "-").split("-")[0],
        "creator_name": creator,
        "cast_names": detail.get("Actors", "") if detail.get("Actors") != "N/A" else "",
        "producer_name": detail.get("Production", "") if detail.get("Production") != "N/A" else "",
        "description": detail.get("Plot", "") if detail.get("Plot") != "N/A" else "",
        "image_url": poster,
        "imdb_rating": imdb_rating if imdb_rating != "N/A" else "",
        "rotten_tomatoes_rating": ratings.get("Rotten Tomatoes", ""),
    }


def _omdb_best_match(title: str, item_type: str):
    matches = _omdb_fast_suggestions(title, item_type)
    if not matches:
        return {}
    title_lower = title.strip().lower()
    match = next((row for row in matches if row["title"].strip().lower() == title_lower), matches[0])
    metadata = _omdb_details(match.get("external_id", ""))
    if match.get("external_id"):
        metadata["external_source"] = "omdb"
        metadata["external_id"] = match["external_id"]
    return metadata


def _google_book_rating(volume_id: str, title: str, creator: str = ""):
    try:
        if volume_id:
            payload = _json_get(f"https://www.googleapis.com/books/v1/volumes/{quote(volume_id)}", timeout=6)
        else:
            query = f"intitle:{title}"
            if creator:
                query += f" inauthor:{creator}"
            params = urlencode({"q": query, "printType": "books", "maxResults": 1})
            payload = _json_get(f"https://www.googleapis.com/books/v1/volumes?{params}", timeout=6)
            payload = (payload.get("items") or [{}])[0]
    except Exception:
        return {}
    rating = payload.get("volumeInfo", {}).get("averageRating")
    if not rating:
        return {}
    volume = payload.get("volumeInfo", {})
    metadata = {"book_rating": str(rating), "book_rating_source": "Google Books"}
    description = volume.get("description", "")
    if description:
        metadata["description"] = description
    return metadata


def _enrich_item_metadata(item: Item):
    if item.item_type in {"movie", "series"} and item.description and item.creator_name and item.image_url and item.imdb_rating:
        return
    if item.item_type == "book" and item.description and item.book_rating:
        return

    if item.item_type in {"movie", "series"} and item.external_source == "tmdb":
        metadata = _tmdb_details(item.external_id)
    elif item.item_type in {"movie", "series"} and item.external_source == "omdb":
        metadata = _omdb_details(item.external_id)
    elif item.item_type in {"movie", "series"}:
        metadata = {}
        tmdb_matches = _tmdb_suggestions(item.title, item.item_type)
        if tmdb_matches:
            best = next((row for row in tmdb_matches if row["title"].strip().lower() == item.title.strip().lower()), tmdb_matches[0])
            metadata = _tmdb_details(best.get("external_id", ""))
            if best.get("external_id"):
                metadata["external_source"] = "tmdb"
                metadata["external_id"] = best["external_id"]
        if not metadata:
            metadata = _omdb_best_match(item.title, item.item_type)
    elif item.item_type == "book":
        volume_id = item.external_id if item.external_source == "googlebooks" else ""
        metadata = _google_book_rating(volume_id, item.title, item.creator_name)
    else:
        metadata = {}

    changed = []
    for field, value in metadata.items():
        value = (value or "").strip()
        if value and not getattr(item, field):
            setattr(item, field, value)
            changed.append(field)
    if changed:
        item.save(update_fields=changed)


def _metadata_from_payload(payload):
    def first_value(key, default=""):
        value = payload.get(key, default)
        if isinstance(value, (list, tuple)):
            value = value[0] if value else default
        return (value or default)

    item_type = first_value("item_type", "movie").strip().lower()
    if item_type not in {"movie", "series", "book"}:
        item_type = "movie"
    return {
        "title": (first_value("title") or first_value("item_title")).strip(),
        "item_type": item_type,
        "release_year": (first_value("year") or first_value("release_year")).strip(),
        "creator_name": (first_value("creator") or first_value("creator_name")).strip(),
        "description": first_value("description").strip(),
        "cast_names": first_value("cast_names").strip(),
        "image_url": first_value("image_url").strip(),
        "external_source": first_value("external_source").strip(),
        "external_id": first_value("external_id").strip(),
    }


def _apply_external_metadata_to_unsaved_item(item):
    metadata = {}
    if item.external_source == "catalog":
        return
    if item.item_type in {"movie", "series"} and item.external_source == "tmdb" and item.external_id:
        metadata = _tmdb_details(item.external_id)
    elif item.item_type in {"movie", "series"} and item.external_source == "omdb" and item.external_id:
        metadata = _omdb_details(item.external_id)
    elif item.item_type in {"movie", "series"}:
        metadata = {}
        tmdb_matches = _tmdb_suggestions(item.title, item.item_type)
        if tmdb_matches:
            best = next((row for row in tmdb_matches if row["title"].strip().lower() == item.title.strip().lower()), tmdb_matches[0])
            metadata = _tmdb_details(best.get("external_id", ""))
        if not metadata:
            metadata = _omdb_best_match(item.title, item.item_type)
    elif item.item_type == "book":
        volume_id = item.external_id if item.external_source == "googlebooks" else ""
        metadata = _google_book_rating(volume_id, item.title, item.creator_name)
    for field, value in metadata.items():
        value = (value or "").strip()
        if value and not getattr(item, field):
            setattr(item, field, value)


def _materialize_item_from_payload(payload):
    data = _metadata_from_payload(payload)
    if not data["title"]:
        return None
    item = (
        Item.objects.filter(title__iexact=data["title"], item_type=data["item_type"])
        .order_by("id")
        .first()
    )
    if item:
        _enrich_item_metadata(item)
        return item

    item = Item.objects.create(
        title=data["title"],
        item_type=data["item_type"],
        release_year=data["release_year"],
        creator_name=data["creator_name"],
        description=data["description"],
        cast_names=data["cast_names"],
        image_url=data["image_url"],
        external_source=data["external_source"],
        external_id=data["external_id"],
    )
    _enrich_item_metadata(item)
    return item


def _preview_query_for_item(item):
    params = {
        "preview": "1",
        "item_type": item.item_type,
        "year": item.release_year or "",
        "creator": item.creator_name or "",
        "description": item.description or "",
        "cast_names": item.cast_names or "",
        "image_url": item.image_url or "",
        "external_source": item.external_source or "",
        "external_id": item.external_id or "",
    }
    return urlencode({key: value for key, value in params.items() if value})


@login_required
def suggest_items(request):
    query = request.GET.get("q", "").strip()
    item_type = request.GET.get("item_type", "").strip().lower()
    if item_type not in {"movie", "series", "book", "all"}:
        return JsonResponse({"results": [], "error": "Please choose movie, series, or book."})
    if len(query) < 2:
        return JsonResponse({"results": [], "error": ""})

    if item_type == "all":
        requested_types = {
            value.strip()
            for value in request.GET.get("types", "").split(",")
            if value.strip() in {"movie", "series", "book"}
        }
        if not requested_types:
            requested_types = {"movie", "series", "book"}
        cache_key = f"suggest_items:all:v8:{'-'.join(sorted(requested_types))}:{_cache_slug(query)}"
        cached = cache.get(cache_key)
        if cached is not None:
            return JsonResponse({"results": cached, "error": ""})
        merged = []
        seen_keys = set()
        error_message = ""

        def add_rows(rows):
            for row in rows:
                key = f"{row.get('title', '').lower()}:{row.get('item_type', '')}:{row.get('year', '')}:{row.get('external_id', '')}"
                if not row.get("title") or key in seen_keys:
                    continue
                seen_keys.add(key)
                merged.append(row)

        for row_type in ("movie", "series", "book"):
            if row_type not in requested_types:
                continue
            existing_rows = Item.objects.filter(title__icontains=query, item_type=row_type).order_by("title").values(
                "id", "title", "item_type", "release_year", "creator_name", "image_url"
            )
            rows = [
                {
                    "key": f"item:{item_row['id']}",
                    "title": item_row["title"],
                    "item_type": item_row["item_type"],
                    "year": item_row["release_year"],
                    "creator": item_row["creator_name"],
                    "image_url": item_row["image_url"],
                    "external_source": "",
                    "external_id": "",
                    "source": "existing",
                }
                for item_row in existing_rows
            ]
            add_rows(rows)
            add_rows(_fallback_title_suggestions(query, [row_type]))
            if len(query) >= 3 and row_type in {"movie", "series"}:
                add_rows(_tmdb_suggestions(query, row_type))
            if len(query) >= 3 and row_type == "book":
                book_rows = _google_books_suggestions(query, max_results=10)
                if len(book_rows) < 5:
                    book_rows += _openlibrary_suggestions(query)
                add_rows(book_rows)
        cache.set(cache_key, merged, 300)
        return JsonResponse({"results": merged, "error": error_message})

    cache_key = f"suggest_items:{item_type}:v8:{_cache_slug(query)}"
    cached = cache.get(cache_key)
    if cached is not None:
        return JsonResponse(cached)

    existing = list(
        Item.objects.filter(
            Q(title__icontains=query),
            Q(item_type=item_type) if item_type in {"movie", "book", "series"} else Q(),
        )
        .order_by("title")
        .values("id", "title", "item_type", "release_year", "creator_name", "image_url")
    )
    results = [
        {
            "key": f"item:{row['id']}",
            "title": row["title"],
            "item_type": row["item_type"],
            "year": row["release_year"],
            "creator": row["creator_name"],
            "image_url": row["image_url"],
            "external_source": "",
            "external_id": "",
            "source": "existing",
        }
        for row in existing
    ]

    existing_titles = {row["title"].strip().lower() for row in results}
    for row in _fallback_title_suggestions(query, [item_type]):
        normalized = row["title"].lower()
        if normalized in existing_titles:
            continue
        existing_titles.add(normalized)
        results.append(row)

    external_results = []
    error_message = ""
    if item_type == "book" and len(query) >= 3:
        external_results = _google_books_suggestions(query)
        if len(external_results) < 5:
            external_results += _openlibrary_suggestions(query)
    elif item_type in {"movie", "series"} and len(query) >= 3:
        external_results = _tmdb_suggestions(query, item_type)
        if not external_results:
            external_results = _omdb_fast_suggestions(query, item_type)
        if not external_results:
            external_results = _wikidata_suggestions(query, item_type)
        if not external_results and not _tmdb_api_key():
            error_message = "No poster results found. Add TMDB_API_KEY for stronger movie and series metadata."

    for row in external_results:
        normalized = row["title"].lower()
        if normalized in existing_titles:
            continue
        results.append(row)

    payload = {"results": results, "error": error_message}
    cache.set(cache_key, payload, 300)
    return JsonResponse(payload)


@login_required
def feed(request, review_form=None):
    if request.method == "POST" and review_form is None:
        return new_review(request, render_feed_on_error=True)

    friends_only = request.GET.get("filter") == "friends"
    query = request.GET.get("q", "").strip()
    sort = request.GET.get("sort", "newest")
    type_filter = request.GET.get("type", "").strip().lower()
    if type_filter not in {"movie", "book", "series"}:
        type_filter = ""
    friend_ids = []

    if request.user.is_authenticated:
        friend_ids = _followed_user_ids(request.user)

    reviews = Review.objects.select_related("user", "user__profile", "item").filter(
        item__item_type__in=["movie", "book", "series"]
    )

    if friends_only and request.user.is_authenticated:
        reviews = reviews.filter(user_id__in=friend_ids)

    if type_filter:
        reviews = reviews.filter(item__item_type=type_filter)

    if query:
        reviews = reviews.filter(
            Q(item__title__icontains=query)
            | Q(item__item_type__icontains=query)
            | Q(review_text__icontains=query)
            | Q(user__username__icontains=query)
            | Q(user__first_name__icontains=query)
        )

    reviews = reviews.annotate(
        likes_total=Count(
            "item__saved_entries",
            filter=Q(item__saved_entries__list_type="favorites"),
            distinct=True,
        ),
        review_like_total=Count("likes", distinct=True),
        comment_total=Count("comments", distinct=True),
    )
    if sort == "top":
        reviews = reviews.order_by("-likes_total", "-rating", "-created_at")
    else:
        reviews = reviews.order_by("-created_at")
    paginator = Paginator(reviews, 10)
    page_obj = paginator.get_page(request.GET.get("page"))
    page_reviews = list(page_obj.object_list)
    _attach_genres_to_reviews(page_reviews)
    page_item_ids = [review.item_id for review in page_reviews]
    page_review_ids = [review.id for review in page_reviews]
    watchlist_item_ids = set()
    readlist_item_ids = set()
    favorite_item_ids = set()
    saved_review_ids = set()
    recommended_item_ids = set()
    review_liked_ids = set()
    if request.user.is_authenticated:
        watchlist_item_ids = set(
            SavedItem.objects.filter(
                user=request.user,
                list_type="watchlist",
                item_id__in=page_item_ids,
            ).values_list("item_id", flat=True)
        )
        readlist_item_ids = set(
            SavedItem.objects.filter(
                user=request.user,
                list_type="readlist",
                item_id__in=page_item_ids,
            ).values_list("item_id", flat=True)
        )
        favorite_item_ids = set(
            SavedItem.objects.filter(
                user=request.user,
                list_type="favorites",
                item_id__in=page_item_ids,
            ).values_list("item_id", flat=True)
        )
        saved_review_ids = set(
            SavedReview.objects.filter(
                user=request.user,
                review_id__in=page_review_ids,
            ).values_list("review_id", flat=True)
        )
        recommended_item_ids = set(
            Recommendation.objects.filter(
                from_user=request.user,
                item_id__in=page_item_ids,
            ).values_list("item_id", flat=True)
        )
        review_liked_ids = set(
            ReviewLike.objects.filter(
                user=request.user,
                review_id__in=page_review_ids,
            ).values_list("review_id", flat=True)
        )
    activities = Activity.objects.select_related("user", "user__profile", "review", "review__item", "target_user", "collection")
    followed_activities = activities.filter(user_id__in=friend_ids) if friend_ids else Activity.objects.none()
    popular_reviews = Review.objects.select_related("user", "user__profile", "item").annotate(
        likes_total=Count(
            "item__saved_entries",
            filter=Q(item__saved_entries__list_type="favorites"),
            distinct=True,
        )
    ).order_by("-likes_total", "-created_at")[:5]
    suggested_users = User.objects.select_related("profile").exclude(id=request.user.id).exclude(id__in=friend_ids).order_by("first_name", "username")[:5]
    notifications_preview = Notification.objects.filter(
        recipient=request.user
    ).select_related("actor").order_by("-created_at")[:5]
    user_review_count = Review.objects.filter(user=request.user).count()

    review_form_instance = review_form
    if review_form_instance is None:
        initial = {}
        if request.GET.get("item_title") or request.GET.get("title"):
            item_payload = _metadata_from_payload(request.GET)
            item_title = item_payload["title"]
            item_type = item_payload["item_type"]
            external_source = item_payload["external_source"]
            external_id = item_payload["external_id"]
            initial = {
                "item_title": item_title,
                "item_type": item_type,
                "selected_item_title": item_title,
                "selected_item_year": item_payload["release_year"],
                "selected_item_creator": item_payload["creator_name"],
                "selected_item_image_url": item_payload["image_url"],
                "selected_item_external_source": external_source,
                "selected_item_external_id": external_id,
                "selected_item_key": f"{external_source}:{external_id}" if external_source and external_id else f"preview:{item_title}",
            }
        review_form_instance = ReviewForm(initial=initial)

    return render(
        request,
        "posts/feed.html",
        {
            "reviews": page_reviews,
            "page_obj": page_obj,
            "friends_only": friends_only,
            "query": query,
            "sort": sort,
            "type_filter": type_filter,
            "watchlist_item_ids": watchlist_item_ids,
            "readlist_item_ids": readlist_item_ids,
            "favorite_item_ids": favorite_item_ids,
            "saved_review_ids": saved_review_ids,
            "recommended_item_ids": recommended_item_ids,
            "review_liked_ids": review_liked_ids,
            "review_form": review_form_instance,
            "activities": activities[:12],
            "followed_activities": followed_activities[:6],
            "popular_reviews": popular_reviews,
            "suggested_users": suggested_users,
            "notifications_preview": notifications_preview,
            "user_review_count": user_review_count,
            "remaining_taste_reviews": max(10 - user_review_count, 0),
        },
    )


@login_required
def discover(request):
    return redirect("discover_media")


def _discover_sections_for_types(item_types):
    allowed_types = set(item_types)
    if allowed_types == {"book"}:
        return _book_discover_sections()
    sections = []
    for section in _discover_rail_sections():
        rows = [row for row in section.get("items", []) if row.get("item_type") in allowed_types]
        if rows:
            sections.append({**section, "items": rows})
    return sections


def _weekly_top_sections():
    sections = {}
    specs = (
        ("movie", "Movies", "Movie"),
        ("series", "Series", "Series"),
        ("book", "Books", "Book"),
    )
    catalog_rows = _catalog_rows()
    for item_type, label, singular_label in specs:
        ranked_items = list(
            Item.objects.filter(item_type=item_type)
            .annotate(
                review_total=Count("reviews", distinct=True),
                average_rating=Avg("reviews__rating"),
                like_total=Count("saved_entries", filter=Q(saved_entries__list_type="favorites"), distinct=True),
            )
            .filter(Q(review_total__gt=0) | Q(like_total__gt=0))
            .order_by("-average_rating", "-like_total", "-review_total", "title")[:10]
        )
        rows = []
        for index, item in enumerate(ranked_items, start=1):
            meta_parts = [item.get_item_type_display()]
            if item.release_year:
                meta_parts.append(str(item.release_year))
            score = (
                f"{item.average_rating:.1f}/5"
                if item.average_rating
                else f"{item.like_total} like{'' if item.like_total == 1 else 's'}"
            )
            rows.append(
                {
                    "rank": index,
                    "title": item.title,
                    "meta": " - ".join(meta_parts),
                    "score": score,
                    "url": reverse("item_reviews", args=[item.title]),
                }
            )

        if len(rows) < 10:
            used_titles = {row["title"].lower() for row in rows}
            for seed in catalog_rows:
                if seed.get("item_type") != item_type:
                    continue
                title = seed.get("title", "").strip()
                if not title or title.lower() in used_titles:
                    continue
                seed_year = seed.get("year", "")
                meta_parts = [singular_label]
                if seed_year:
                    meta_parts.append(str(seed_year))
                rows.append(
                    {
                        "rank": len(rows) + 1,
                        "title": title,
                        "meta": " - ".join(meta_parts),
                        "score": "New",
                        "url": _preview_url_for_payload(seed),
                    }
                )
                used_titles.add(title.lower())
                if len(rows) >= 10:
                    break
        sections[item_type] = {"label": label, "rows": rows}
    return sections


@login_required
def discover_media(request):
    query = request.GET.get("q", "").strip()
    chip = request.GET.get("chip", "for-you")
    sort = request.GET.get("sort", "newest")
    genre_filter = request.GET.get("genre", "").strip().lower()
    valid_genres = {bucket["slug"] for bucket in CONTENT_GENRE_BUCKETS}
    if genre_filter not in valid_genres:
        genre_filter = ""
    friend_ids = _followed_user_ids(request.user)

    trending_reviews = Review.objects.select_related("item", "user", "user__profile")
    friend_favorites = Review.objects.select_related("item", "user", "user__profile").filter(
        user_id__in=friend_ids
    )
    recent_reviews = Review.objects.select_related("item", "user", "user__profile")

    if query:
        filter_query = (
            Q(item__title__icontains=query)
            | Q(item__item_type__icontains=query)
            | Q(review_text__icontains=query)
            | Q(user__username__icontains=query)
            | Q(user__first_name__icontains=query)
        )
        trending_reviews = trending_reviews.filter(filter_query)
        friend_favorites = friend_favorites.filter(filter_query)
        recent_reviews = recent_reviews.filter(filter_query)

    if chip == "trending":
        friend_favorites = friend_favorites.none()
        recent_reviews = recent_reviews.none()
    elif chip == "new-releases":
        trending_reviews = trending_reviews.none()
        friend_favorites = friend_favorites.none()

    trending_reviews = trending_reviews.annotate(
        likes_total=Count(
            "item__saved_entries",
            filter=Q(item__saved_entries__list_type="favorites"),
            distinct=True,
        )
    )
    friend_favorites = friend_favorites.annotate(
        likes_total=Count(
            "item__saved_entries",
            filter=Q(item__saved_entries__list_type="favorites"),
            distinct=True,
        )
    )
    recent_reviews = recent_reviews.annotate(
        likes_total=Count(
            "item__saved_entries",
            filter=Q(item__saved_entries__list_type="favorites"),
            distinct=True,
        )
    )
    if sort == "top":
        trending_reviews = trending_reviews.order_by("-likes_total", "-rating", "-created_at")
        friend_favorites = friend_favorites.order_by("-likes_total", "-rating", "-created_at")
        recent_reviews = recent_reviews.order_by("-likes_total", "-rating", "-created_at")
    else:
        trending_reviews = trending_reviews.order_by("-rating", "-created_at")
        friend_favorites = friend_favorites.order_by("-created_at")
        recent_reviews = recent_reviews.order_by("-created_at")

    if genre_filter:
        trending_reviews = _filter_reviews_by_genre(trending_reviews[:240], genre_filter)
        friend_favorites = _filter_reviews_by_genre(friend_favorites[:240], genre_filter)
        recent_reviews = _filter_reviews_by_genre(recent_reviews[:240], genre_filter)

    trending_page = Paginator(trending_reviews, 6).get_page(request.GET.get("trending_page"))
    friends_page = Paginator(friend_favorites, 6).get_page(request.GET.get("friends_page"))
    recent_page = Paginator(recent_reviews, 6).get_page(request.GET.get("recent_page"))
    trending_review_rows = list(trending_page.object_list)
    friend_favorite_rows = list(friends_page.object_list)
    recent_review_rows = list(recent_page.object_list)
    _attach_genres_to_reviews(trending_review_rows)
    _attach_genres_to_reviews(friend_favorite_rows)
    _attach_genres_to_reviews(recent_review_rows)
    discover_card_reviews = trending_review_rows + friend_favorite_rows + recent_review_rows
    _hydrate_review_card_counts(discover_card_reviews)
    review_card_context = _review_card_action_context(request.user, discover_card_reviews)
    selected_genre_label = ""
    if genre_filter:
        selected_genre_label = next((bucket["label"] for bucket in CONTENT_GENRE_BUCKETS if bucket["slug"] == genre_filter), "")
    return render(
        request,
        "posts/discover_media.html",
        {
            "query": query,
            "chip": chip,
            "sort": sort,
            "genre_filter": genre_filter,
            "selected_genre_label": selected_genre_label,
            "genre_options": CONTENT_GENRE_BUCKETS,
            "trending_reviews": trending_review_rows,
            "friend_favorites": friend_favorite_rows,
            "recent_reviews": recent_review_rows,
            "discover_rails": _discover_sections_for_types(["movie", "series"]),
            "genre_rows": _tmdb_genre_discover_rows(genre_filter, 24) if genre_filter else [],
            "weekly_top_sections": _weekly_top_sections(),
            "popular_books": Item.objects.filter(item_type="book").annotate(review_total=Count("reviews")).order_by("-review_total", "title")[:6],
            "popular_movies": Item.objects.filter(item_type="movie").annotate(review_total=Count("reviews")).order_by("-review_total", "title")[:6],
            "popular_shows": Item.objects.filter(item_type="series").annotate(review_total=Count("reviews")).order_by("-review_total", "title")[:6],
            "trending_page_obj": trending_page,
            "friends_page_obj": friends_page,
            "recent_page_obj": recent_page,
            **review_card_context,
        },
    )


@login_required
def discover_books(request):
    friend_ids = _followed_user_ids(request.user)
    genre_filter = request.GET.get("genre", "").strip().lower()
    valid_book_genres = {bucket["slug"] for bucket in BOOK_GENRE_BUCKETS}
    if genre_filter not in valid_book_genres:
        genre_filter = ""
    book_reviews = (
        Review.objects.select_related("item", "user", "user__profile")
        .filter(item__item_type="book")
        .order_by("-created_at")[:12]
    )
    book_reviews = list(book_reviews)
    _attach_genres_to_reviews(book_reviews)
    _hydrate_review_card_counts(book_reviews)
    review_card_context = _review_card_action_context(request.user, book_reviews)
    selected_genre_label = ""
    if genre_filter:
        selected_genre_label = next((bucket["label"] for bucket in BOOK_GENRE_BUCKETS if bucket["slug"] == genre_filter), "")
    return render(
        request,
        "posts/discover_books.html",
        {
            "query": request.GET.get("q", "").strip(),
            "genre_filter": genre_filter,
            "genre_options": BOOK_GENRE_BUCKETS,
            "selected_genre_label": selected_genre_label,
            "genre_rows": _book_genre_discover_rows(genre_filter, 24) if genre_filter else [],
            "book_reviews": book_reviews,
            "discover_rails": _discover_sections_for_types(["book"]),
            "weekly_top_sections": _weekly_top_sections(),
            **review_card_context,
        },
    )


@login_required
def search(request):
    query = request.GET.get("q", "").strip()
    section = request.GET.get("section", "all")
    friend_ids = _followed_user_ids(request.user)

    people = User.objects.none()
    reviews = Review.objects.none()
    items = Item.objects.none()
    lists = Recommendation.objects.none()

    if query:
        people = User.objects.filter(
            Q(username__icontains=query) | Q(first_name__icontains=query)
        ).exclude(id=request.user.id).order_by("first_name", "username")
        reviews = Review.objects.select_related("item", "user").filter(
            Q(item__title__icontains=query)
            | Q(review_text__icontains=query)
            | Q(user__username__icontains=query)
            | Q(user__first_name__icontains=query)
        ).order_by("-created_at")[:10]
        items = Item.objects.filter(
            Q(title__icontains=query) | Q(item_type__icontains=query)
        ).order_by("title")[:10]
        lists = Recommendation.objects.select_related("from_user", "item").filter(
            Q(item__title__icontains=query) | Q(message__icontains=query),
            to_user_id__in=list(friend_ids) + [request.user.id],
        ).order_by("-created_at")[:6]

    if section == "people":
        reviews = Review.objects.none()
        items = Item.objects.none()
        lists = Recommendation.objects.none()
    elif section == "movies":
        people = User.objects.none()
        reviews = reviews.filter(item__item_type="movie")
        items = items.filter(item_type="movie")
        lists = lists.filter(item__item_type="movie")
    elif section == "books":
        people = User.objects.none()
        reviews = reviews.filter(item__item_type="book")
        items = items.filter(item_type="book")
        lists = lists.filter(item__item_type="book")
    elif section == "reviews":
        people = User.objects.none()
        items = Item.objects.none()
        lists = Recommendation.objects.none()
    elif section == "lists":
        people = User.objects.none()
        items = Item.objects.none()
        reviews = Review.objects.none()

    people_page = Paginator(people, 8).get_page(request.GET.get("people_page"))
    items_page = Paginator(items, 8).get_page(request.GET.get("items_page"))
    reviews_page = Paginator(reviews, 8).get_page(request.GET.get("reviews_page"))
    lists_page = Paginator(lists, 6).get_page(request.GET.get("lists_page"))

    return render(
        request,
        "posts/search.html",
        {
            "query": query,
            "section": section,
            "people": people_page.object_list,
            "reviews": reviews_page.object_list,
            "items": items_page.object_list,
            "lists": lists_page.object_list,
            "people_page_obj": people_page,
            "items_page_obj": items_page,
            "reviews_page_obj": reviews_page,
            "lists_page_obj": lists_page,
        },
    )


def signup(request):
    if request.method == "POST":
        form = SignUpForm(request.POST, request.FILES)
        if form.is_valid():
            user = form.save()
            login(request, user, backend="posts.auth_backends.EmailOrUsernameBackend")
            return redirect("feed")
    else:
        form = SignUpForm()

    return render(request, "registration/signup.html", {"form": form})


@login_required
def new_review(request, render_feed_on_error=False):
    if request.method == "POST":
        form = ReviewForm(request.POST)
        if form.is_valid():
            item_type = form.cleaned_data["item_type"]
            selected_key = form.cleaned_data["selected_item_key"]
            selected_title = form.cleaned_data["selected_item_title"].strip()
            selected_year = form.cleaned_data.get("selected_item_year", "").strip()
            selected_creator = form.cleaned_data.get("selected_item_creator", "").strip()
            selected_image = form.cleaned_data.get("selected_item_image_url", "").strip()
            selected_external_source = form.cleaned_data.get("selected_item_external_source", "").strip()
            selected_external_id = form.cleaned_data.get("selected_item_external_id", "").strip()
            podcast_url = form.cleaned_data.get("podcast_url", "").strip()

            if item_type == "podcast":
                metadata = _podcast_metadata_from_url(podcast_url)
                podcast_title = (metadata.get("title") or selected_title or podcast_url).strip()[:255]
                item = Item.objects.filter(
                    external_source=metadata["external_source"],
                    external_id=metadata["external_id"],
                ).first()
                if not item:
                    item = Item.objects.filter(title__iexact=podcast_title, item_type="podcast").first()
                if not item:
                    item = Item.objects.create(
                        title=podcast_title,
                        item_type="podcast",
                        image_url=metadata["image_url"],
                        release_year="",
                        creator_name="",
                        cast_names="",
                        producer_name="",
                        description="",
                        imdb_rating="",
                        rotten_tomatoes_rating="",
                        book_rating="",
                        book_rating_source="",
                        external_source=metadata["external_source"],
                        external_id=metadata["external_id"],
                    )
                else:
                    changed = False
                    if podcast_title and item.title == podcast_url:
                        item.title = podcast_title
                        changed = True
                    if metadata["image_url"] and not item.image_url:
                        item.image_url = metadata["image_url"]
                        changed = True
                    if changed:
                        item.save(update_fields=["title", "image_url"])
            elif item_type == "experience":
                item = Item.objects.filter(title__iexact=selected_title, item_type="experience").first()
                if not item:
                    item = Item.objects.create(
                        title=selected_title,
                        item_type="experience",
                        image_url="",
                        release_year="",
                        creator_name="",
                        cast_names="",
                        producer_name="",
                        description="",
                        imdb_rating="",
                        rotten_tomatoes_rating="",
                        book_rating="",
                        book_rating_source="",
                        external_source="",
                        external_id="",
                    )
            elif selected_key.startswith("item:"):
                item_id = int(selected_key.split(":", 1)[1])
                item = get_object_or_404(Item, id=item_id)
            else:
                item = None
                if selected_external_source and selected_external_id:
                    item = Item.objects.filter(
                        external_source=selected_external_source,
                        external_id=selected_external_id,
                    ).first()
                if not item:
                    item = Item.objects.filter(
                        title__iexact=selected_title,
                        item_type=item_type,
                    ).first()
                if not item:
                    item = Item.objects.create(
                        title=selected_title,
                        item_type=item_type,
                        image_url=selected_image,
                        release_year=selected_year,
                        creator_name=selected_creator,
                        cast_names="",
                        producer_name="",
                        description="",
                        imdb_rating="",
                        rotten_tomatoes_rating="",
                        book_rating="",
                        book_rating_source="",
                        external_source=selected_external_source,
                        external_id=selected_external_id,
                    )
                else:
                    changed = False
                    if selected_image and not item.image_url:
                        item.image_url = selected_image
                        changed = True
                    if selected_year and not item.release_year:
                        item.release_year = selected_year
                        changed = True
                    if selected_creator and not item.creator_name:
                        item.creator_name = selected_creator
                        changed = True
                    if selected_external_source and selected_external_id and (not item.external_source or not item.external_id):
                        item.external_source = selected_external_source
                        item.external_id = selected_external_id
                        changed = True
                    if changed:
                        item.save(update_fields=["image_url", "release_year", "creator_name", "external_source", "external_id"])
            if item.item_type in {"movie", "series", "book"}:
                _enrich_item_metadata(item)
            review = Review.objects.create(
                user=request.user,
                item=item,
                rating=form.cleaned_data["rating"],
                review_text=form.cleaned_data["review_text"],
            )
            _create_activity(
                request.user,
                Activity.REVIEW_POSTED,
                f"{_display_name(request.user)} reviewed {item.title}",
                review=review,
            )
            messages.success(request, "Your review was posted.")
            return redirect("feed")
        if render_feed_on_error:
            return feed(request, review_form=form)
    else:
        form = ReviewForm()
        item_id = request.GET.get("item")
        if item_id:
            item = get_object_or_404(Item, id=item_id)
            form.initial.update(
                {
                    "item_type": item.item_type,
                    "item_title": item.title,
                    "selected_item_key": f"item:{item.id}",
                    "selected_item_title": item.title,
                    "selected_item_year": item.release_year,
                    "selected_item_creator": item.creator_name,
                    "selected_item_image_url": item.image_url,
                    "selected_item_external_source": item.external_source,
                    "selected_item_external_id": item.external_id,
                }
            )

    return render(request, "posts/new_review.html", {"form": form})


@login_required
def edit_review(request, review_id):
    review = get_object_or_404(
        Review.objects.select_related("item"),
        id=review_id,
        user=request.user,
    )
    next_url = request.POST.get("next") or request.GET.get("next") or reverse("feed")
    if request.method == "POST":
        form = ReviewEditForm(request.POST, instance=review)
        if form.is_valid():
            form.save()
            messages.success(request, "Review updated.")
            return redirect(next_url)
    else:
        form = ReviewEditForm(instance=review)

    return render(
        request,
        "posts/edit_review.html",
        {
            "form": form,
            "review": review,
            "next_url": next_url,
        },
    )


@login_required
def delete_review(request, review_id):
    review = get_object_or_404(Review, id=review_id, user=request.user)
    if request.method == "POST":
        review.delete()
        messages.success(request, "Review deleted.")
        return redirect(request.POST.get("next") or "feed")
    return redirect("feed")


@login_required
def friends(request):
    query = request.GET.get("q", "").strip()
    tab = request.GET.get("tab", "following")
    friend_ids = _followed_user_ids(request.user)
    follower_ids = set(Follow.objects.filter(following=request.user).values_list("follower_id", flat=True)) | set(
        Friendship.objects.filter(to_user=request.user).values_list("from_user_id", flat=True)
    )
    friends_list = User.objects.filter(id__in=friend_ids).order_by("first_name", "username")
    followers_list = User.objects.filter(id__in=follower_ids).order_by("first_name", "username")
    suggested_users = User.objects.exclude(
        id=request.user.id
    ).exclude(
        id__in=friend_ids
    ).order_by("first_name", "username")
    recommendations = Recommendation.objects.filter(
        to_user=request.user,
        from_user_id__in=friend_ids,
    ).select_related("from_user", "item").order_by("-created_at")

    if query:
        people_query = Q(username__icontains=query) | Q(first_name__icontains=query)
        friends_list = friends_list.filter(people_query)
        followers_list = followers_list.filter(people_query)
        suggested_users = suggested_users.filter(people_query)
        recommendations = recommendations.filter(
            Q(from_user__username__icontains=query)
            | Q(from_user__first_name__icontains=query)
            | Q(item__title__icontains=query)
            | Q(message__icontains=query)
        )

    return render(
        request,
        "posts/friends.html",
        {
            "friends": friends_list,
            "followers": followers_list,
            "suggested_users": suggested_users,
            "recommendations": recommendations,
            "query": query,
            "active_tab": tab,
        },
    )


@login_required
def add_friend(request, user_id):
    if request.method != "POST":
        return redirect("friends")
    friend = get_object_or_404(User, id=user_id)
    created = False
    if friend != request.user:
        _, created = Friendship.objects.get_or_create(from_user=request.user, to_user=friend)
        Follow.objects.get_or_create(follower=request.user, following=friend)
        if created:
            _create_activity(
                request.user,
                Activity.USER_FOLLOWED,
                f"{_display_name(request.user)} started following {_display_name(friend)}",
                target_user=friend,
            )
            _notify(
                friend,
                request.user,
                Notification.FOLLOW,
                f"{_display_name(request.user)} followed you.",
            )
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse(
            {
                "ok": True,
                "active": created,
                "label": "Following",
                "followers_count": Friendship.objects.filter(to_user=friend).count(),
            }
        )
    return redirect("friends")


@login_required
def remove_friend(request, user_id):
    if request.method != "POST":
        return redirect("friends")
    Friendship.objects.filter(
        from_user=request.user,
        to_user_id=user_id,
    ).delete()
    Follow.objects.filter(follower=request.user, following_id=user_id).delete()
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse(
            {
                "ok": True,
                "active": False,
                "label": "Follow",
            }
        )
    return redirect("friends")


@login_required
def recommend(request):
    friend_ids = _followed_user_ids(request.user)
    to_user_id = request.GET.get("to_user")
    item_id = request.GET.get("item")

    if request.method == "POST":
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            item = get_object_or_404(Item, id=request.POST.get("item"))
            selected_friend_ids = [
                int(value) for value in request.POST.getlist("to_user") if value.isdigit()
            ]
            allowed_friend_ids = set(selected_friend_ids) & set(friend_ids)
            recipients = list(User.objects.filter(id__in=allowed_friend_ids))
            if not recipients:
                return JsonResponse(
                    {"ok": False, "error": "Choose at least one friend."},
                    status=400,
                )
            message = (request.POST.get("message") or "").strip()[:140]
            for recipient in recipients:
                recommendation = Recommendation.objects.create(
                    from_user=request.user,
                    to_user=recipient,
                    item=item,
                    message=message,
                )
                _create_activity(
                    request.user,
                    Activity.RECOMMENDED,
                    f"{_display_name(request.user)} recommended {recommendation.item.title}",
                    target_user=recommendation.to_user,
                )
                _notify(
                    recipient,
                    request.user,
                    Notification.COMMENT,
                    f"{_display_name(request.user)} recommended {recommendation.item.title} to you.",
                )
            return JsonResponse(
                {
                    "ok": True,
                    "item_id": item.id,
                    "action": "recommend",
                    "active": True,
                    "recommended_active": True,
                    "message": f"Recommendation sent to {len(recipients)} friend{'s' if len(recipients) != 1 else ''}.",
                }
            )
        form = RecommendationForm(request.POST)
        form.fields["to_user"].queryset = User.objects.filter(id__in=friend_ids)
        if form.is_valid():
            recommendation = form.save(commit=False)
            recommendation.from_user = request.user
            recommendation.save()
            _create_activity(
                request.user,
                Activity.RECOMMENDED,
                f"{_display_name(request.user)} recommended {recommendation.item.title}",
                target_user=recommendation.to_user,
            )
            _notify(
                recommendation.to_user,
                request.user,
                Notification.COMMENT,
                f"{_display_name(request.user)} recommended {recommendation.item.title} to you.",
            )
            messages.success(request, "Recommendation sent.")
            return redirect("feed")
    else:
        form = RecommendationForm()
        form.fields["to_user"].queryset = User.objects.filter(
            id__in=friend_ids
        ).order_by("first_name", "username")
        if to_user_id:
            form.initial["to_user"] = to_user_id
        if item_id:
            form.initial["item"] = item_id

    return render(request, "posts/recommend.html", {"form": form})


@login_required
def profile(request):
    profile_obj, _ = Profile.objects.get_or_create(user=request.user)
    if request.method == "POST":
        form = ProfileForm(request.POST, request.FILES, instance=profile_obj)
        if form.is_valid():
            form.save()
            messages.success(request, "Profile updated.")
            return redirect("profile")
    else:
        form = ProfileForm(instance=profile_obj)

    friend_count = Follow.objects.filter(follower=request.user).count() or Friendship.objects.filter(from_user=request.user).count()
    review_count = Review.objects.filter(user=request.user).count()
    recommendation_count = Recommendation.objects.filter(to_user=request.user).count()
    recent_reviews = list(Review.objects.filter(
        user=request.user
    ).select_related("user", "user__profile", "item").order_by("-created_at")[:5])
    _attach_genres_to_reviews(recent_reviews)
    _hydrate_review_card_counts(recent_reviews)
    review_card_context = _review_card_action_context(request.user, recent_reviews)
    top_rated_reviews = Review.objects.filter(
        user=request.user
    ).select_related("item").order_by("-rating", "-created_at")[:5]
    top_types = Review.objects.filter(user=request.user).values(
        "item__item_type"
    ).annotate(
        total=Count("id")
    ).order_by("-total")
    followers_count = Follow.objects.filter(following=request.user).count() or Friendship.objects.filter(to_user=request.user).count()
    likes_received = SavedItem.objects.filter(
        list_type="favorites",
        item__reviews__user=request.user,
    ).distinct().count()
    watchlist_items = SavedItem.objects.filter(
        user=request.user, list_type="watchlist"
    ).select_related("item").order_by("-created_at")
    readlist_items = SavedItem.objects.filter(
        user=request.user, list_type="readlist"
    ).select_related("item").order_by("-created_at")
    return render(
        request,
        "posts/profile.html",
        {
            "friend_count": friend_count,
            "followers_count": followers_count,
            "review_count": review_count,
            "likes_received": likes_received,
            "recommendation_count": recommendation_count,
            "recent_reviews": recent_reviews,
            "top_rated_reviews": top_rated_reviews,
            "top_types": top_types,
            "watchlist_items": watchlist_items,
            "readlist_items": readlist_items,
            "profile_form": form,
            "collections": Collection.objects.filter(user=request.user)[:5],
            "saved_reviews": SavedReview.objects.filter(user=request.user).select_related("review", "review__item")[:5],
            **review_card_context,
        },
    )


@login_required
def delete_profile_photo(request):
    if request.method != "POST":
        return redirect("profile")

    profile_obj, _ = Profile.objects.get_or_create(user=request.user)
    if profile_obj.profile_photo:
        profile_obj.profile_photo.delete(save=False)
        profile_obj.profile_photo = ""
        profile_obj.save(update_fields=["profile_photo", "updated_at"])
        messages.success(request, "Profile photo removed.")
    return redirect("profile")


def item_reviews_by_id(request, item_id):
    item = get_object_or_404(Item, id=item_id)
    return redirect("item_reviews", item_title=item.title)


def item_reviews(request, item_title):
    normalized_title = unquote(item_title).strip()
    item = (
        Item.objects.annotate(review_total=Count("reviews"))
        .order_by("-review_total", "id")
        .filter(title__iexact=normalized_title)
        .first()
    )
    is_preview_item = False
    preview_query = ""
    if item:
        _enrich_item_metadata(item)
        item.refresh_from_db()
    elif request.GET.get("preview") or request.GET.get("item_type") or request.GET.get("external_id"):
        is_preview_item = True
        payload = _metadata_from_payload({**request.GET, "title": normalized_title})
        item = Item(
            title=payload["title"] or normalized_title,
            item_type=payload["item_type"],
            release_year=payload["release_year"],
            creator_name=payload["creator_name"],
            description=payload["description"],
            cast_names=payload["cast_names"],
            image_url=payload["image_url"],
            external_source=payload["external_source"],
            external_id=payload["external_id"],
        )
        _apply_external_metadata_to_unsaved_item(item)
        preview_query = _preview_query_for_item(item)
    else:
        raise Http404("No item found.")
    reviews = (
        Review.objects.filter(item=item) if item.pk else Review.objects.none()
    )
    reviews = (
        reviews
        .select_related("user", "user__profile")
        .annotate(
            review_like_total=Count("likes", distinct=True),
            comment_total=Count("comments", distinct=True),
        )
        .order_by("-created_at")
    )
    page_obj = Paginator(reviews, 12).get_page(request.GET.get("page"))
    page_reviews = list(page_obj.object_list)
    _attach_genres_to_reviews(page_reviews)
    item_genre_text = " ".join([review.review_text for review in page_reviews[:6]]) if page_reviews else ""
    item_genre = _infer_content_genre(item, item_genre_text)
    item_state = {
        "save_list_type": _save_list_type_for_item(item),
        "like_active": False,
        "save_active": False,
        "recommended_active": False,
    }
    if request.user.is_authenticated and item.pk:
        item_state = _item_action_state(request.user, item)
    item_like_count = SavedItem.objects.filter(item=item, list_type="favorites").count() if item.pk else 0
    review_liked_ids = set()
    friend_ids = set()
    if request.user.is_authenticated:
        review_liked_ids = set(
            ReviewLike.objects.filter(
                user=request.user,
                review_id__in=[review.id for review in page_reviews],
            ).values_list("review_id", flat=True)
        )
        friend_ids = _followed_user_ids(request.user)
    popular_reviews = (
        Review.objects.exclude(item=item) if item.pk else Review.objects.all()
    )
    popular_reviews = (
        popular_reviews
        .select_related("item", "user", "user__profile")
        .annotate(
            likes_total=Count(
                "item__saved_entries",
                filter=Q(item__saved_entries__list_type="favorites"),
                distinct=True,
            )
        )
        .order_by("-likes_total", "-created_at")[:4]
    )
    suggested_users = User.objects.select_related("profile")
    if request.user.is_authenticated:
        suggested_users = suggested_users.exclude(id=request.user.id).exclude(id__in=friend_ids)
    suggested_users = suggested_users.order_by("first_name", "username")[:3]
    if item.pk:
        top_level_comments = Comment.objects.filter(
            review__item=item,
            parent__isnull=True,
        ).select_related("user", "user__profile", "review").prefetch_related("replies", "likes")[:20]
    else:
        top_level_comments = Comment.objects.none()
    return render(
        request,
        "posts/item_reviews.html",
        {
            "item": item,
            "item_genre_label": item_genre["label"] if item_genre else "",
            "item_genre_slug": item_genre["slug"] if item_genre else "",
            "reviews": page_reviews,
            "page_obj": page_obj,
            "comment_form": CommentForm(),
            "comments": top_level_comments,
            "item_save_list_type": item_state["save_list_type"],
            "liked_item_active": item_state["like_active"],
            "saved_item_active": item_state["save_active"],
            "recommended_item_active": item_state["recommended_active"],
            "item_like_count": item_like_count,
            "review_liked_ids": review_liked_ids,
            "popular_reviews": popular_reviews,
            "suggested_users": suggested_users,
            "is_preview_item": is_preview_item,
            "preview_query": preview_query,
            "open_recommend_on_load": request.GET.get("open_recommend") == "1",
        },
    )


@login_required
def preview_item_action(request, action):
    if request.method != "POST":
        return redirect("discover")
    if action not in {"favorites", "watchlist", "readlist", "recommend"}:
        return redirect("discover")
    item = _materialize_item_from_payload(request.POST)
    if not item:
        messages.error(request, "Choose a valid title first.")
        return redirect("discover")

    if action in {"favorites", "watchlist", "readlist"}:
        SavedItem.objects.get_or_create(user=request.user, item=item, list_type=action)
        if action == "favorites":
            _create_activity(
                request.user,
                Activity.REVIEW_LIKED,
                f"{_display_name(request.user)} liked {item.title}",
            )
        return redirect("item_reviews", item_title=item.title)

    return redirect(f"{reverse('item_reviews', kwargs={'item_title': item.title})}?open_recommend=1")


@login_required
def toggle_like(request, review_id):
    if request.method != "POST":
        return redirect("feed")

    review = get_object_or_404(Review, id=review_id)
    like, created = ReviewLike.objects.get_or_create(
        user=request.user,
        review=review,
    )
    if not created:
        like.delete()
    active = created
    if created:
        _create_activity(
            request.user,
            Activity.REVIEW_LIKED,
            f"{_display_name(request.user)} liked a review of {review.item.title}",
            review=review,
        )
        _notify(
            review.user,
            request.user,
            Notification.LIKE,
            f"{_display_name(request.user)} liked your review of {review.item.title}.",
            review=review,
        )
    count = review.likes.count()
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse(
            {
                "ok": True,
                "review_id": review.id,
                "action": "review_like",
                "active": active,
                "label": "Unlike" if active else "Like",
                "count": count,
            }
        )

    return redirect(request.POST.get("next") or "feed")


@login_required
def toggle_saved_item(request, item_id, list_type):
    if request.method != "POST":
        return redirect("feed")

    if list_type not in {"watchlist", "readlist", "favorites"}:
        return redirect(request.POST.get("next") or "feed")

    item = get_object_or_404(Item, id=item_id)
    saved, created = SavedItem.objects.get_or_create(
        user=request.user,
        item=item,
        list_type=list_type,
    )
    if not created:
        saved.delete()
    item_state = _item_action_state(request.user, item)
    active = item_state["like_active"] if list_type == "favorites" else item_state["save_active"]
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        favorites_labels = ("Liked", "Like") if request.POST.get("label_context") == "like" else ("Saved to Favorites", "Favorite")
        list_labels = {
            "watchlist": ("Saved to Watchlist", "Watchlist"),
            "readlist": ("Saved to Readlist", "Readlist"),
            "favorites": favorites_labels,
        }
        on_label, off_label = list_labels[list_type]
        count = SavedItem.objects.filter(item=item, list_type="favorites").count() if list_type == "favorites" else None
        return JsonResponse(
            {
                "ok": True,
                "item_id": item.id,
                "action": "like" if list_type == "favorites" else "save",
                "list_type": list_type,
                "active": active,
                "like_active": item_state["like_active"],
                "save_active": item_state["save_active"],
                "recommended_active": item_state["recommended_active"],
                "save_list_type": item_state["save_list_type"],
                "label": on_label if active else off_label,
                "like_count": count,
            }
        )

    return redirect(request.POST.get("next") or "feed")


@login_required
def toggle_saved_review(request, review_id):
    if request.method != "POST":
        return redirect("feed")
    review = get_object_or_404(Review, id=review_id)
    saved, created = SavedReview.objects.get_or_create(user=request.user, review=review)
    if not created:
        saved.delete()
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse(
            {
                "ok": True,
                "active": created,
                "label": "Saved" if created else "Save",
            }
        )
    messages.success(request, "Review saved." if created else "Review removed from saved.")
    return redirect(request.POST.get("next") or "feed")


@login_required
def add_comment(request, review_id):
    review = get_object_or_404(Review, id=review_id)
    if request.method != "POST":
        return redirect("item_reviews", item_title=review.item.title)
    form = CommentForm(request.POST)
    parent = None
    parent_id = request.POST.get("parent")
    if parent_id:
        parent = get_object_or_404(Comment, id=parent_id, review=review)
    if form.is_valid():
        comment = form.save(commit=False)
        comment.user = request.user
        comment.review = review
        comment.parent = parent
        comment.save()
        _create_activity(
            request.user,
            Activity.COMMENTED,
            f"{_display_name(request.user)} commented on {review.item.title}",
            review=review,
        )
        _notify(
            parent.user if parent else review.user,
            request.user,
            Notification.REPLY if parent else Notification.COMMENT,
            f"{_display_name(request.user)} replied to you." if parent else f"{_display_name(request.user)} commented on your review.",
            review=review,
            comment=comment,
        )
        messages.success(request, "Comment posted.")
    return redirect(f"{reverse('item_reviews', kwargs={'item_title': review.item.title})}#review-{review.id}")


@login_required
def delete_comment(request, comment_id):
    comment = get_object_or_404(Comment, id=comment_id)
    item_title = comment.review.item.title
    if request.method == "POST" and comment.user == request.user:
        comment.delete()
        messages.success(request, "Comment deleted.")
    return redirect("item_reviews", item_title=item_title)


@login_required
def like_comment(request, comment_id):
    comment = get_object_or_404(Comment, id=comment_id)
    like, created = CommentLike.objects.get_or_create(user=request.user, comment=comment)
    if not created:
        like.delete()
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({"ok": True, "active": created, "count": comment.likes.count()})
    return redirect("item_reviews", item_title=comment.review.item.title)


@login_required
def followers(request, username=None):
    viewed_user = get_object_or_404(User, username=username) if username else request.user
    ids = set(Follow.objects.filter(following=viewed_user).values_list("follower_id", flat=True)) | set(
        Friendship.objects.filter(to_user=viewed_user).values_list("from_user_id", flat=True)
    )
    people = User.objects.filter(id__in=ids).order_by("first_name", "username")
    return render(request, "posts/follow_list.html", {"people": people, "viewed_user": viewed_user, "mode": "Followers"})


@login_required
def following(request, username=None):
    viewed_user = get_object_or_404(User, username=username) if username else request.user
    ids = set(Follow.objects.filter(follower=viewed_user).values_list("following_id", flat=True)) | set(
        Friendship.objects.filter(from_user=viewed_user).values_list("to_user_id", flat=True)
    )
    people = User.objects.filter(id__in=ids).order_by("first_name", "username")
    return render(request, "posts/follow_list.html", {"people": people, "viewed_user": viewed_user, "mode": "Following"})


@login_required
def user_profile(request, username):
    viewed_user = get_object_or_404(User, username=username)
    Profile.objects.get_or_create(user=viewed_user)
    is_following = Follow.objects.filter(follower=request.user, following=viewed_user).exists() or Friendship.objects.filter(
        from_user=request.user, to_user=viewed_user
    ).exists()
    follower_ids = set(Follow.objects.filter(following=viewed_user).values_list("follower_id", flat=True))
    my_following_ids = _followed_user_ids(request.user)
    mutual_ids = follower_ids & my_following_ids
    mutual_count = len(mutual_ids)
    mutual_users = list(User.objects.filter(id__in=mutual_ids).select_related("profile").order_by("first_name", "username")[:6])
    for mutual_user in mutual_users:
        Profile.objects.get_or_create(user=mutual_user)
    reviews = list(Review.objects.filter(user=viewed_user).select_related("user", "user__profile", "item").order_by("-created_at")[:10])
    _attach_genres_to_reviews(reviews)
    watchlist_items = SavedItem.objects.filter(
        user=viewed_user,
        list_type="watchlist",
    ).select_related("item").order_by("-created_at")[:5]
    readlist_items = SavedItem.objects.filter(
        user=viewed_user,
        list_type="readlist",
    ).select_related("item").order_by("-created_at")[:5]
    saved_reviews = SavedReview.objects.filter(
        user=viewed_user,
    ).select_related("review", "review__item").order_by("-created_at")[:5]
    liked_items = SavedItem.objects.filter(
        user=viewed_user,
        list_type="favorites",
    ).select_related("item").order_by("-created_at")[:10]
    liked_reviews = list(ReviewLike.objects.filter(
        user=viewed_user,
    ).select_related("review", "review__user", "review__user__profile", "review__item").order_by("-created_at")[:10])
    liked_review_objects = [row.review for row in liked_reviews]
    _attach_genres_to_reviews(liked_review_objects)
    _hydrate_review_card_counts(reviews + liked_review_objects)
    review_card_context = _review_card_action_context(request.user, reviews + liked_review_objects)
    collections = Collection.objects.filter(user=viewed_user, is_public=True).prefetch_related("items")[:5]
    return render(
        request,
        "posts/user_profile.html",
        {
            "viewed_user": viewed_user,
            "reviews": reviews,
            "review_count": Review.objects.filter(user=viewed_user).count(),
            "followers_count": Follow.objects.filter(following=viewed_user).count()
            or Friendship.objects.filter(to_user=viewed_user).count(),
            "following_count": Follow.objects.filter(follower=viewed_user).count()
            or Friendship.objects.filter(from_user=viewed_user).count(),
            "likes_received": SavedItem.objects.filter(
                list_type="favorites",
                item__reviews__user=viewed_user,
            ).distinct().count(),
            "is_following": is_following,
            "mutual_count": mutual_count,
            "mutual_users": mutual_users,
            "watchlist_items": watchlist_items,
            "readlist_items": readlist_items,
            "saved_reviews": saved_reviews,
            "liked_items": liked_items,
            "liked_reviews": liked_reviews,
            "collections": collections,
            **review_card_context,
        },
    )


@login_required
def notifications(request):
    rows = Notification.objects.filter(recipient=request.user).select_related(
        "actor",
        "actor__profile",
        "review",
        "review__item",
        "comment",
    ).order_by("-created_at")
    if request.method == "POST":
        rows.update(is_read=True)
        messages.success(request, "Notifications marked as read.")
        return redirect("notifications")
    page_obj = Paginator(rows, 20).get_page(request.GET.get("page"))
    friend_ids = _followed_user_ids(request.user)
    friend_activity = Activity.objects.filter(
        user_id__in=friend_ids,
        activity_type__in=[
            Activity.REVIEW_POSTED,
            Activity.REVIEW_LIKED,
            Activity.RECOMMENDED,
        ],
    ).select_related("user", "user__profile", "review", "review__item", "target_user").order_by("-created_at")[:20]
    return render(
        request,
        "posts/notifications.html",
        {
            "notifications": page_obj.object_list,
            "page_obj": page_obj,
            "friend_activity": friend_activity,
        },
    )


@login_required
def saved_reviews(request):
    rows = SavedReview.objects.filter(user=request.user).select_related("review", "review__item", "review__user").order_by("-created_at")
    return render(request, "posts/saved_reviews.html", {"saved_reviews": rows})


class CollectionListView(ListView):
    model = Collection
    template_name = "posts/collections.html"
    context_object_name = "collections"
    paginate_by = 20

    def get_queryset(self):
        return Collection.objects.filter(user=self.request.user)


class CollectionCreateView(CreateView):
    model = Collection
    form_class = CollectionForm
    template_name = "posts/collection_form.html"
    success_url = reverse_lazy("collections")

    def form_valid(self, form):
        form.instance.user = self.request.user
        response = super().form_valid(form)
        _create_activity(
            self.request.user,
            Activity.COLLECTION_CREATED,
            f"{_display_name(self.request.user)} created {self.object.title}",
            collection=self.object,
        )
        messages.success(self.request, "Collection created.")
        return response


class CollectionDetailView(DetailView):
    model = Collection
    template_name = "posts/collection_detail.html"
    context_object_name = "collection"

    def get_queryset(self):
        return Collection.objects.filter(Q(user=self.request.user) | Q(is_public=True))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["available_items"] = Item.objects.order_by("title")[:120]
        return context


@login_required
def add_item_to_collection(request, collection_id, item_id):
    collection = get_object_or_404(Collection, id=collection_id, user=request.user)
    item = get_object_or_404(Item, id=item_id)
    CollectionItem.objects.get_or_create(collection=collection, item=item)
    messages.success(request, "Item added to collection.")
    return redirect("collection_detail", pk=collection.id)


@login_required
def add_existing_item_to_collection(request, collection_id):
    collection = get_object_or_404(Collection, id=collection_id, user=request.user)
    if request.method == "POST":
        item_id = request.POST.get("item")
        item = get_object_or_404(Item, id=item_id)
        CollectionItem.objects.get_or_create(collection=collection, item=item)
        messages.success(request, "Item added to collection.")
    return redirect("collection_detail", pk=collection.id)
