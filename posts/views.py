from django.contrib.auth.decorators import login_required
from django.contrib.auth import login
from django.contrib.auth.models import User
from django.contrib import messages
from django.db.models import Count, Q
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.views.generic import CreateView, DetailView, ListView
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen
import json
import os

from .forms import CollectionForm, CommentForm, ProfileForm, RecommendationForm, ReviewForm, SignUpForm
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


def _followed_user_ids(user):
    follow_ids = set(Follow.objects.filter(follower=user).values_list("following_id", flat=True))
    friendship_ids = set(Friendship.objects.filter(from_user=user).values_list("to_user_id", flat=True))
    return follow_ids | friendship_ids


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
                "limit": 12,
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
        if len(results) >= 8:
            break
    return results


def _google_books_suggestions(query: str):
    if not query:
        return []
    try:
        params = urlencode(
            {
                "q": query,
                "printType": "books",
                "maxResults": 8,
            }
        )
        payload = _json_get(f"https://www.googleapis.com/books/v1/volumes?{params}")
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
        if image_links.get("thumbnail"):
            image_url = image_links["thumbnail"].replace("http://", "https://")
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
    return results


def _openlibrary_suggestions(query: str):
    try:
        params = urlencode(
            {
                "q": query,
                "limit": 8,
                "fields": "key,title,author_name,first_publish_year,cover_i",
            }
        )
        payload = _json_get(f"https://openlibrary.org/search.json?{params}")
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
    return results


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
    for row in search_payload.get("Search", [])[:8]:
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
    for row in search_payload.get("Search", [])[:8]:
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
    if item.item_type in {"movie", "series"} and item.external_source == "omdb":
        metadata = _omdb_details(item.external_id)
    elif item.item_type in {"movie", "series"}:
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


@login_required
def suggest_items(request):
    query = request.GET.get("q", "").strip()
    item_type = request.GET.get("item_type", "").strip().lower()
    if item_type not in {"movie", "series", "book"}:
        return JsonResponse({"results": [], "error": "Please choose movie, series, or book."})
    if len(query) < 2:
        return JsonResponse({"results": [], "error": ""})

    existing = list(
        Item.objects.filter(
            Q(title__icontains=query),
            Q(item_type=item_type) if item_type in {"movie", "book", "series"} else Q(),
        )
        .order_by("title")[:8]
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
    external_results = []
    error_message = ""
    if item_type == "book":
        external_results = _google_books_suggestions(query)
        if not external_results:
            external_results = _openlibrary_suggestions(query)
        if not external_results:
            external_results = _wikidata_suggestions(query, item_type)
    elif item_type in {"movie", "series"}:
        external_results = _omdb_fast_suggestions(query, item_type)
        if not external_results:
            external_results = _wikidata_suggestions(query, item_type)
        if not external_results and not os.environ.get("OMDB_API_KEY", "").strip():
            error_message = "No poster results found. Add OMDB_API_KEY for stronger movie and series metadata."

    for row in external_results:
        normalized = row["title"].lower()
        if normalized in existing_titles:
            continue
        results.append(row)
        if len(results) >= 12:
            break

    return JsonResponse({"results": results, "error": error_message})


@login_required
def feed(request):
    friends_only = request.GET.get("filter") == "friends"
    query = request.GET.get("q", "").strip()
    sort = request.GET.get("sort", "newest")
    friend_ids = []

    if request.user.is_authenticated:
        friend_ids = _followed_user_ids(request.user)

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

    reviews = reviews.annotate(likes_total=Count("likes"))
    if sort == "top":
        reviews = reviews.order_by("-likes_total", "-rating", "-created_at")
    else:
        reviews = reviews.order_by("-created_at")
    paginator = Paginator(reviews, 10)
    page_obj = paginator.get_page(request.GET.get("page"))
    page_reviews = page_obj.object_list
    liked_review_ids = set()
    watchlist_item_ids = set()
    favorite_item_ids = set()
    saved_review_ids = set()
    if request.user.is_authenticated:
        liked_review_ids = set(
            ReviewLike.objects.filter(
                user=request.user, review_id__in=page_reviews.values_list("id", flat=True)
            ).values_list("review_id", flat=True)
        )
        watchlist_item_ids = set(
            SavedItem.objects.filter(
                user=request.user,
                list_type="watchlist",
                item_id__in=page_reviews.values_list("item_id", flat=True),
            ).values_list("item_id", flat=True)
        )
        favorite_item_ids = set(
            SavedItem.objects.filter(
                user=request.user,
                list_type="favorites",
                item_id__in=page_reviews.values_list("item_id", flat=True),
            ).values_list("item_id", flat=True)
        )
        saved_review_ids = set(
            SavedReview.objects.filter(
                user=request.user,
                review_id__in=page_reviews.values_list("id", flat=True),
            ).values_list("review_id", flat=True)
        )
    activities = Activity.objects.select_related("user", "review", "review__item", "target_user", "collection")
    followed_activities = activities.filter(user_id__in=friend_ids) if friend_ids else Activity.objects.none()
    popular_reviews = Review.objects.select_related("user", "item").annotate(
        likes_total=Count("likes")
    ).order_by("-likes_total", "-created_at")[:5]
    suggested_users = User.objects.exclude(id=request.user.id).exclude(id__in=friend_ids).order_by("username")[:5]
    notifications_preview = Notification.objects.filter(
        recipient=request.user
    ).select_related("actor").order_by("-created_at")[:5]

    return render(
        request,
        "posts/feed.html",
        {
            "reviews": page_reviews,
            "page_obj": page_obj,
            "friends_only": friends_only,
            "query": query,
            "sort": sort,
            "liked_review_ids": liked_review_ids,
            "watchlist_item_ids": watchlist_item_ids,
            "favorite_item_ids": favorite_item_ids,
            "saved_review_ids": saved_review_ids,
            "review_form": ReviewForm(),
            "activities": activities[:12],
            "followed_activities": followed_activities[:6],
            "popular_reviews": popular_reviews,
            "suggested_users": suggested_users,
            "notifications_preview": notifications_preview,
        },
    )


@login_required
def discover(request):
    query = request.GET.get("q", "").strip()
    chip = request.GET.get("chip", "for-you")
    sort = request.GET.get("sort", "newest")
    friend_ids = _followed_user_ids(request.user)

    trending_reviews = Review.objects.select_related("item", "user")
    friend_favorites = Review.objects.select_related("item", "user").filter(
        user_id__in=friend_ids
    )
    recent_reviews = Review.objects.select_related("item", "user")

    if query:
        filter_query = (
            Q(item__title__icontains=query)
            | Q(item__item_type__icontains=query)
            | Q(review_text__icontains=query)
            | Q(user__username__icontains=query)
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

    trending_reviews = trending_reviews.annotate(likes_total=Count("likes"))
    friend_favorites = friend_favorites.annotate(likes_total=Count("likes"))
    recent_reviews = recent_reviews.annotate(likes_total=Count("likes"))
    if sort == "top":
        trending_reviews = trending_reviews.order_by("-likes_total", "-rating", "-created_at")
        friend_favorites = friend_favorites.order_by("-likes_total", "-rating", "-created_at")
        recent_reviews = recent_reviews.order_by("-likes_total", "-rating", "-created_at")
    else:
        trending_reviews = trending_reviews.order_by("-rating", "-created_at")
        friend_favorites = friend_favorites.order_by("-created_at")
        recent_reviews = recent_reviews.order_by("-created_at")

    trending_page = Paginator(trending_reviews, 6).get_page(request.GET.get("trending_page"))
    friends_page = Paginator(friend_favorites, 6).get_page(request.GET.get("friends_page"))
    recent_page = Paginator(recent_reviews, 6).get_page(request.GET.get("recent_page"))

    return render(
        request,
        "posts/discover.html",
        {
            "query": query,
            "chip": chip,
            "sort": sort,
            "trending_reviews": trending_page.object_list,
            "friend_favorites": friends_page.object_list,
            "recent_reviews": recent_page.object_list,
            "trending_users": User.objects.annotate(review_total=Count("review")).order_by("-review_total")[:6],
            "popular_books": Item.objects.filter(item_type="book").annotate(review_total=Count("reviews")).order_by("-review_total", "title")[:6],
            "popular_movies": Item.objects.filter(item_type="movie").annotate(review_total=Count("reviews")).order_by("-review_total", "title")[:6],
            "popular_shows": Item.objects.filter(item_type="series").annotate(review_total=Count("reviews")).order_by("-review_total", "title")[:6],
            "suggested_users": User.objects.exclude(id=request.user.id).exclude(id__in=friend_ids).order_by("username")[:6],
            "trending_page_obj": trending_page,
            "friends_page_obj": friends_page,
            "recent_page_obj": recent_page,
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
        people = User.objects.filter(username__icontains=query).exclude(id=request.user.id).order_by("username")
        reviews = Review.objects.select_related("item", "user").filter(
            Q(item__title__icontains=query)
            | Q(review_text__icontains=query)
            | Q(user__username__icontains=query)
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
            item_type = form.cleaned_data["item_type"]
            selected_key = form.cleaned_data["selected_item_key"]
            selected_title = form.cleaned_data["selected_item_title"].strip()
            selected_year = form.cleaned_data.get("selected_item_year", "").strip()
            selected_creator = form.cleaned_data.get("selected_item_creator", "").strip()
            selected_image = form.cleaned_data.get("selected_item_image_url", "").strip()
            selected_external_source = form.cleaned_data.get("selected_item_external_source", "").strip()
            selected_external_id = form.cleaned_data.get("selected_item_external_id", "").strip()

            if selected_key.startswith("item:"):
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
                f"{request.user.username} reviewed {item.title}",
                review=review,
            )
            messages.success(request, "Your review was posted.")
            return redirect("feed")
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
def friends(request):
    query = request.GET.get("q", "").strip()
    tab = request.GET.get("tab", "following")
    friend_ids = _followed_user_ids(request.user)
    follower_ids = set(Follow.objects.filter(following=request.user).values_list("follower_id", flat=True)) | set(
        Friendship.objects.filter(to_user=request.user).values_list("from_user_id", flat=True)
    )
    friends_list = User.objects.filter(id__in=friend_ids).order_by("username")
    followers_list = User.objects.filter(id__in=follower_ids).order_by("username")
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
        followers_list = followers_list.filter(username__icontains=query)
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
                f"{request.user.username} started following {friend.username}",
                target_user=friend,
            )
            _notify(
                friend,
                request.user,
                Notification.FOLLOW,
                f"{request.user.username} followed you.",
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
        form = RecommendationForm(request.POST)
        form.fields["to_user"].queryset = User.objects.filter(id__in=friend_ids)
        if form.is_valid():
            recommendation = form.save(commit=False)
            recommendation.from_user = request.user
            recommendation.save()
            _create_activity(
                request.user,
                Activity.RECOMMENDED,
                f"{request.user.username} recommended {recommendation.item.title}",
                target_user=recommendation.to_user,
            )
            _notify(
                recommendation.to_user,
                request.user,
                Notification.COMMENT,
                f"{request.user.username} recommended {recommendation.item.title} to you.",
            )
            messages.success(request, "Recommendation sent.")
            return redirect("feed")
    else:
        form = RecommendationForm()
        form.fields["to_user"].queryset = User.objects.filter(
            id__in=friend_ids
        ).order_by("username")
        if to_user_id:
            form.initial["to_user"] = to_user_id
        if item_id:
            form.initial["item"] = item_id

    return render(request, "posts/recommend.html", {"form": form})


@login_required
def profile(request):
    profile_obj, _ = Profile.objects.get_or_create(user=request.user)
    if request.method == "POST":
        form = ProfileForm(request.POST, instance=profile_obj)
        if form.is_valid():
            form.save()
            messages.success(request, "Profile updated.")
            return redirect("profile")
    else:
        form = ProfileForm(instance=profile_obj)

    friend_count = Follow.objects.filter(follower=request.user).count() or Friendship.objects.filter(from_user=request.user).count()
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
    followers_count = Follow.objects.filter(following=request.user).count() or Friendship.objects.filter(to_user=request.user).count()
    likes_received = ReviewLike.objects.filter(review__user=request.user).count()
    watchlist_items = SavedItem.objects.filter(
        user=request.user, list_type="watchlist"
    ).select_related("item").order_by("-created_at")
    readlist_items = SavedItem.objects.filter(
        user=request.user, list_type="readlist"
    ).select_related("item").order_by("-created_at")
    favorite_items = SavedItem.objects.filter(
        user=request.user, list_type="favorites"
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
            "top_types": top_types,
            "watchlist_items": watchlist_items,
            "readlist_items": readlist_items,
            "favorite_items": favorite_items,
            "profile_form": form,
            "collections": Collection.objects.filter(user=request.user)[:5],
            "saved_reviews": SavedReview.objects.filter(user=request.user).select_related("review", "review__item")[:5],
        },
    )


@login_required
def item_reviews(request, item_id):
    item = get_object_or_404(Item, id=item_id)
    _enrich_item_metadata(item)
    item.refresh_from_db()
    reviews = Review.objects.filter(item=item).select_related("user").order_by("-created_at")
    page_obj = Paginator(reviews, 12).get_page(request.GET.get("page"))
    top_level_comments = Comment.objects.filter(
        review__item=item,
        parent__isnull=True,
    ).select_related("user", "review").prefetch_related("replies", "likes")[:20]
    return render(
        request,
        "posts/item_reviews.html",
        {
            "item": item,
            "reviews": page_obj.object_list,
            "page_obj": page_obj,
            "comment_form": CommentForm(),
            "comments": top_level_comments,
        },
    )


@login_required
def toggle_like(request, review_id):
    if request.method != "POST":
        return redirect("feed")

    review = get_object_or_404(Review, id=review_id)
    like, created = ReviewLike.objects.get_or_create(user=request.user, review=review)
    if not created:
        like.delete()
    active = created
    if created:
        _create_activity(
            request.user,
            Activity.REVIEW_LIKED,
            f"{request.user.username} liked a review of {review.item.title}",
            review=review,
        )
        _notify(
            review.user,
            request.user,
            Notification.LIKE,
            f"{request.user.username} liked your review of {review.item.title}.",
            review=review,
        )
    count = ReviewLike.objects.filter(review=review).count()
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse(
            {
                "ok": True,
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
    active = created
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        list_labels = {
            "watchlist": ("Saved to Watchlist", "Watchlist"),
            "readlist": ("Saved to Readlist", "Readlist"),
            "favorites": ("Saved to Favorites", "Favorite"),
        }
        on_label, off_label = list_labels[list_type]
        return JsonResponse(
            {
                "ok": True,
                "active": active,
                "label": on_label if active else off_label,
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
        return redirect("item_reviews", item_id=review.item_id)
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
            f"{request.user.username} commented on {review.item.title}",
            review=review,
        )
        _notify(
            parent.user if parent else review.user,
            request.user,
            Notification.REPLY if parent else Notification.COMMENT,
            f"{request.user.username} replied to you." if parent else f"{request.user.username} commented on your review.",
            review=review,
            comment=comment,
        )
        messages.success(request, "Comment posted.")
    return redirect("item_reviews", item_id=review.item_id)


@login_required
def delete_comment(request, comment_id):
    comment = get_object_or_404(Comment, id=comment_id)
    item_id = comment.review.item_id
    if request.method == "POST" and comment.user == request.user:
        comment.delete()
        messages.success(request, "Comment deleted.")
    return redirect("item_reviews", item_id=item_id)


@login_required
def like_comment(request, comment_id):
    comment = get_object_or_404(Comment, id=comment_id)
    like, created = CommentLike.objects.get_or_create(user=request.user, comment=comment)
    if not created:
        like.delete()
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({"ok": True, "active": created, "count": comment.likes.count()})
    return redirect("item_reviews", item_id=comment.review.item_id)


@login_required
def followers(request, username=None):
    viewed_user = get_object_or_404(User, username=username) if username else request.user
    ids = set(Follow.objects.filter(following=viewed_user).values_list("follower_id", flat=True)) | set(
        Friendship.objects.filter(to_user=viewed_user).values_list("from_user_id", flat=True)
    )
    people = User.objects.filter(id__in=ids).order_by("username")
    return render(request, "posts/follow_list.html", {"people": people, "viewed_user": viewed_user, "mode": "Followers"})


@login_required
def following(request, username=None):
    viewed_user = get_object_or_404(User, username=username) if username else request.user
    ids = set(Follow.objects.filter(follower=viewed_user).values_list("following_id", flat=True)) | set(
        Friendship.objects.filter(from_user=viewed_user).values_list("to_user_id", flat=True)
    )
    people = User.objects.filter(id__in=ids).order_by("username")
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
    mutual_count = len(follower_ids & my_following_ids)
    reviews = Review.objects.filter(user=viewed_user).select_related("item").order_by("-created_at")[:10]
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
            "likes_received": ReviewLike.objects.filter(review__user=viewed_user).count(),
            "is_following": is_following,
            "mutual_count": mutual_count,
        },
    )


@login_required
def notifications(request):
    rows = Notification.objects.filter(recipient=request.user).select_related("actor", "review").order_by("-created_at")
    if request.method == "POST":
        rows.update(is_read=True)
        messages.success(request, "Notifications marked as read.")
        return redirect("notifications")
    page_obj = Paginator(rows, 20).get_page(request.GET.get("page"))
    return render(request, "posts/notifications.html", {"notifications": page_obj.object_list, "page_obj": page_obj})


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
            f"{self.request.user.username} created {self.object.title}",
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


@login_required
def add_item_to_collection(request, collection_id, item_id):
    collection = get_object_or_404(Collection, id=collection_id, user=request.user)
    item = get_object_or_404(Item, id=item_id)
    CollectionItem.objects.get_or_create(collection=collection, item=item)
    messages.success(request, "Item added to collection.")
    return redirect("collection_detail", pk=collection.id)
