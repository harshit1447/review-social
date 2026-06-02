from django.contrib.auth.decorators import login_required
from django.contrib.auth import login
from django.contrib.auth.models import User
from django.contrib import messages
from django.core.cache import cache
from django.db.models import Avg, Count, Q
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.views.generic import CreateView, DetailView, ListView
from urllib.parse import parse_qs, quote, unquote, urlencode, urlparse
from urllib.request import Request, urlopen
import json
import os

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


def category_page(request, item_type):
    if item_type not in {"movie", "series", "book"}:
        return redirect("discover")

    items = _item_queryset_for_type(item_type).select_related()
    recently_reviewed = (
        Review.objects.filter(item__item_type=item_type)
        .select_related("user", "user__profile", "item")
        .order_by("-created_at")[:8]
    )
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


def landing_suggest_items(request):
    query = request.GET.get("q", "").strip()
    if len(query) < 2:
        return JsonResponse({"results": []})

    cache_key = f"landing_suggest:v3:{query.lower()}"
    cached = cache.get(cache_key)
    if cached is not None:
        return JsonResponse({"results": cached})

    results = []
    seen = set()
    normalized_query = query.lower()

    existing = Item.objects.filter(
        title__icontains=query,
        item_type__in=["movie", "series"],
    ).order_by("title").values("title", "item_type", "release_year", "creator_name", "image_url")[:14]
    for row in existing:
        title = (row.get("title") or "").strip()
        key = f"{title.lower()}:{row.get('release_year', '')}:{row.get('item_type', '')}"
        if not title or key in seen:
            continue
        seen.add(key)
        results.append(
            {
                "title": title,
                "item_type": row.get("item_type", ""),
                "year": row.get("release_year", ""),
                "creator": row.get("creator_name", ""),
                "image_url": row.get("image_url", ""),
            }
        )

    fallback_titles = [
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
    ]
    for row in fallback_titles:
        title = row["title"]
        compact_title = title.lower().replace(" ", "")
        if normalized_query not in title.lower() and normalized_query not in compact_title:
            continue
        key = f"{title.lower()}:{row.get('year', '')}:{row.get('item_type', '')}"
        if key in seen:
            continue
        seen.add(key)
        results.append(row)

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


def _google_books_suggestions(query: str):
    if not query:
        return []
    try:
        params = urlencode(
            {
                "q": query,
                "printType": "books",
                "maxResults": 40,
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
    if item_type in {"podcast", "experience"}:
        return JsonResponse({"results": [], "error": ""})
    if item_type not in {"movie", "series", "book"}:
        return JsonResponse({"results": [], "error": "Please choose movie, series, book, podcast, or experience."})
    if len(query) < 2:
        return JsonResponse({"results": [], "error": ""})

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

    return JsonResponse({"results": results, "error": error_message})


@login_required
def feed(request, review_form=None):
    if request.method == "POST" and review_form is None:
        return new_review(request, render_feed_on_error=True)

    friends_only = request.GET.get("filter") == "friends"
    query = request.GET.get("q", "").strip()
    sort = request.GET.get("sort", "newest")
    type_filter = request.GET.get("type", "").strip().lower()
    if type_filter not in {"movie", "book", "series", "podcast", "experience"}:
        type_filter = ""
    friend_ids = []

    if request.user.is_authenticated:
        friend_ids = _followed_user_ids(request.user)

    reviews = Review.objects.select_related("user", "user__profile", "item")

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
            "review_form": review_form or ReviewForm(),
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
    query = request.GET.get("q", "").strip()
    chip = request.GET.get("chip", "for-you")
    sort = request.GET.get("sort", "newest")
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
            "trending_users": User.objects.select_related("profile").annotate(review_total=Count("review")).order_by("-review_total")[:6],
            "popular_books": Item.objects.filter(item_type="book").annotate(review_total=Count("reviews")).order_by("-review_total", "title")[:6],
            "popular_movies": Item.objects.filter(item_type="movie").annotate(review_total=Count("reviews")).order_by("-review_total", "title")[:6],
            "popular_shows": Item.objects.filter(item_type="series").annotate(review_total=Count("reviews")).order_by("-review_total", "title")[:6],
            "suggested_users": User.objects.select_related("profile").exclude(id=request.user.id).exclude(id__in=friend_ids).order_by("first_name", "username")[:6],
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
    recent_reviews = Review.objects.filter(
        user=request.user
    ).select_related("user", "user__profile", "item").order_by("-created_at")[:5]
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
    item = get_object_or_404(
        Item.objects.annotate(review_total=Count("reviews")).order_by("-review_total", "id"),
        title__iexact=normalized_title,
    )
    _enrich_item_metadata(item)
    item.refresh_from_db()
    reviews = (
        Review.objects.filter(item=item)
        .select_related("user", "user__profile")
        .annotate(
            review_like_total=Count("likes", distinct=True),
            comment_total=Count("comments", distinct=True),
        )
        .order_by("-created_at")
    )
    page_obj = Paginator(reviews, 12).get_page(request.GET.get("page"))
    page_reviews = list(page_obj.object_list)
    item_state = {
        "save_list_type": _save_list_type_for_item(item),
        "like_active": False,
        "save_active": False,
        "recommended_active": False,
    }
    if request.user.is_authenticated:
        item_state = _item_action_state(request.user, item)
    item_like_count = SavedItem.objects.filter(item=item, list_type="favorites").count()
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
        Review.objects.exclude(item=item)
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
    top_level_comments = Comment.objects.filter(
        review__item=item,
        parent__isnull=True,
    ).select_related("user", "user__profile", "review").prefetch_related("replies", "likes")[:20]
    return render(
        request,
        "posts/item_reviews.html",
        {
            "item": item,
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
        },
    )


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
    return redirect("item_reviews", item_title=review.item.title)


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
    mutual_count = len(follower_ids & my_following_ids)
    reviews = Review.objects.filter(user=viewed_user).select_related("user", "user__profile", "item").order_by("-created_at")[:10]
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
            "watchlist_items": watchlist_items,
            "readlist_items": readlist_items,
            "saved_reviews": saved_reviews,
            "collections": collections,
        },
    )


@login_required
def notifications(request):
    rows = Notification.objects.filter(recipient=request.user).select_related("actor", "actor__profile", "review").order_by("-created_at")
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
