from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from unittest.mock import patch

from .models import Friendship, Item, Recommendation, Review


class SocialReviewTests(TestCase):
    def setUp(self):
        self.alex = User.objects.create_user(username="alex", password="pass")
        self.sam = User.objects.create_user(username="sam", password="pass")
        self.casey = User.objects.create_user(username="casey", password="pass")
        self.item = Item.objects.create(title="Arrival", item_type="movie")

    def test_friends_filter_only_shows_friend_reviews(self):
        Friendship.objects.create(from_user=self.alex, to_user=self.sam)
        Review.objects.create(
            user=self.sam,
            item=self.item,
            rating=5,
            review_text="Thoughtful and beautiful.",
        )
        Review.objects.create(
            user=self.casey,
            item=self.item,
            rating=2,
            review_text="Not for me.",
        )
        self.client.login(username="alex", password="pass")

        response = self.client.get(reverse("feed"), {"filter": "friends"})

        self.assertContains(response, "Thoughtful and beautiful.")
        self.assertNotContains(response, "Not for me.")

    def test_user_can_recommend_item_to_friend(self):
        Friendship.objects.create(from_user=self.alex, to_user=self.sam)
        self.client.login(username="alex", password="pass")

        response = self.client.post(
            reverse("recommend"),
            {
                "to_user": self.sam.id,
                "item": self.item.id,
                "message": "You would like the ending.",
            },
        )

        self.assertRedirects(response, reverse("feed"))
        self.assertTrue(
            Recommendation.objects.filter(
                from_user=self.alex,
                to_user=self.sam,
                item=self.item,
            ).exists()
        )

    def test_feed_search_filters_reviews(self):
        Review.objects.create(
            user=self.sam,
            item=self.item,
            rating=5,
            review_text="A thoughtful alien story.",
        )
        book = Item.objects.create(title="Dune", item_type="book")
        Review.objects.create(
            user=self.casey,
            item=book,
            rating=4,
            review_text="Huge and sandy.",
        )
        self.client.login(username="alex", password="pass")

        response = self.client.get(reverse("feed"), {"q": "alien"})

        self.assertContains(response, "Arrival")
        self.assertNotContains(response, "Dune")

    def test_profile_requires_login(self):
        response = self.client.get(reverse("profile"))

        self.assertEqual(response.status_code, 302)

    def test_discover_requires_login(self):
        response = self.client.get(reverse("discover"))

        self.assertEqual(response.status_code, 302)

    def test_search_returns_matching_item_and_person(self):
        self.client.login(username="alex", password="pass")
        ResponseItem = Item.objects.create(title="Past Lives", item_type="movie")
        Review.objects.create(
            user=self.sam,
            item=ResponseItem,
            rating=4,
            review_text="Quiet and reflective.",
        )

        response = self.client.get(reverse("search"), {"q": "sam"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "sam")
        self.assertContains(response, "People")

    def test_search_finds_people_by_display_name(self):
        self.sam.first_name = "Sam Reader"
        self.sam.save(update_fields=["first_name"])
        self.client.login(username="alex", password="pass")

        response = self.client.get(reverse("search"), {"q": "Reader"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sam Reader")
        self.assertContains(response, "@sam")

    def test_friends_search_finds_people_by_display_name(self):
        self.casey.first_name = "Casey Critic"
        self.casey.save(update_fields=["first_name"])
        self.client.login(username="alex", password="pass")

        response = self.client.get(reverse("friends"), {"tab": "suggestions", "q": "Critic"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Casey Critic")

    def test_feed_search_finds_reviews_by_display_name(self):
        self.sam.first_name = "Sam Reader"
        self.sam.save(update_fields=["first_name"])
        Review.objects.create(
            user=self.sam,
            item=self.item,
            rating=5,
            review_text="Name searchable.",
        )
        self.client.login(username="alex", password="pass")

        response = self.client.get(reverse("feed"), {"q": "Reader"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Name searchable.")

    def test_new_review_reuses_existing_item_for_selected_google_title(self):
        self.client.login(username="alex", password="pass")

        first = self.client.post(
            reverse("new_review"),
            {
                "item_title": "Interstellar",
                "item_type": "movie",
                "selected_item_key": "google:Interstellar",
                "selected_item_title": "Interstellar",
                "rating": 5,
                "review_text": "Great.",
            },
        )
        second = self.client.post(
            reverse("new_review"),
            {
                "item_title": "interstellar",
                "item_type": "movie",
                "selected_item_key": "google:interstellar",
                "selected_item_title": "interstellar",
                "rating": 4,
                "review_text": "Still great.",
            },
        )

        self.assertRedirects(first, reverse("feed"))
        self.assertRedirects(second, reverse("feed"))
        self.assertEqual(Item.objects.filter(title__iexact="interstellar", item_type="movie").count(), 1)
        item = Item.objects.get(title__iexact="interstellar", item_type="movie")
        self.assertEqual(Review.objects.filter(item=item).count(), 2)

    @patch("posts.views._podcast_metadata_from_url")
    def test_podcast_review_uses_link_as_input_and_metadata_title(self, metadata):
        metadata.return_value = {
            "title": "Smart Podcast Episode",
            "external_source": "youtube",
            "external_id": "https://youtu.be/abc123",
            "image_url": "https://img.youtube.com/vi/abc123/hqdefault.jpg",
        }
        self.client.login(username="alex", password="pass")

        response = self.client.post(
            reverse("new_review"),
            {
                "item_title": "https://youtu.be/abc123",
                "item_type": "podcast",
                "rating": 5,
                "review_text": "Worth listening.",
            },
        )

        self.assertRedirects(response, reverse("feed"))
        item = Item.objects.get(item_type="podcast")
        self.assertEqual(item.title, "Smart Podcast Episode")
        self.assertEqual(item.image_url, "https://img.youtube.com/vi/abc123/hqdefault.jpg")
        self.assertEqual(Review.objects.get(item=item).review_text, "Worth listening.")

    def test_review_owner_can_edit_review(self):
        review = Review.objects.create(
            user=self.alex,
            item=self.item,
            rating=3,
            review_text="Original.",
        )
        self.client.login(username="alex", password="pass")

        response = self.client.post(
            reverse("edit_review", args=[review.id]),
            {
                "rating": 5,
                "review_text": "Updated.",
                "next": reverse("feed"),
            },
        )

        self.assertRedirects(response, reverse("feed"))
        review.refresh_from_db()
        self.assertEqual(review.rating, 5)
        self.assertEqual(review.review_text, "Updated.")

    def test_non_owner_cannot_edit_or_delete_review(self):
        review = Review.objects.create(
            user=self.sam,
            item=self.item,
            rating=4,
            review_text="Keep this.",
        )
        self.client.login(username="alex", password="pass")

        edit_response = self.client.post(
            reverse("edit_review", args=[review.id]),
            {
                "rating": 1,
                "review_text": "Bad edit.",
            },
        )
        delete_response = self.client.post(reverse("delete_review", args=[review.id]))

        self.assertEqual(edit_response.status_code, 404)
        self.assertEqual(delete_response.status_code, 404)
        review.refresh_from_db()
        self.assertEqual(review.rating, 4)
        self.assertEqual(review.review_text, "Keep this.")

    def test_review_owner_can_delete_review(self):
        review = Review.objects.create(
            user=self.alex,
            item=self.item,
            rating=4,
            review_text="Delete me.",
        )
        self.client.login(username="alex", password="pass")

        response = self.client.post(
            reverse("delete_review", args=[review.id]),
            {"next": reverse("feed")},
        )

        self.assertRedirects(response, reverse("feed"))
        self.assertFalse(Review.objects.filter(id=review.id).exists())
