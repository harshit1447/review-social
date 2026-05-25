from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

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

        response = self.client.get(reverse("feed"), {"q": "alien"})

        self.assertContains(response, "Arrival")
        self.assertNotContains(response, "Dune")

    def test_profile_requires_login(self):
        response = self.client.get(reverse("profile"))

        self.assertEqual(response.status_code, 302)
