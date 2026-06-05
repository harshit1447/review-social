from django.contrib.auth.models import User
from django.contrib.auth import authenticate
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from .models import Friendship, Item, Recommendation, Review, SavedItem


class SocialReviewTests(TestCase):
    def setUp(self):
        self.alex = User.objects.create_user(username="alex", email="alex@example.com", password="pass")
        self.sam = User.objects.create_user(username="sam", password="pass")
        self.casey = User.objects.create_user(username="casey", password="pass")
        self.item = Item.objects.create(title="Arrival", item_type="movie")

    def test_user_can_authenticate_with_username_or_email(self):
        username_user = authenticate(username="alex", password="pass")
        email_user = authenticate(username="alex@example.com", password="pass")
        mixed_case_email_user = authenticate(username="Alex@Example.com", password="pass")

        self.assertEqual(username_user, self.alex)
        self.assertEqual(email_user, self.alex)
        self.assertEqual(mixed_case_email_user, self.alex)

    def test_signup_requires_unique_email(self):
        response = self.client.post(
            reverse("signup"),
            {
                "first_name": "Another Alex",
                "email": "alex@example.com",
                "username": "anotheralex",
                "password1": "ComplexPass123!",
                "password2": "ComplexPass123!",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "An account with this email already exists.")
        self.assertFalse(User.objects.filter(username="anotheralex").exists())

    def test_signup_works_without_profile_or_cover_photo(self):
        response = self.client.post(
            reverse("signup"),
            {
                "first_name": "Photo Optional",
                "email": "photo-optional@example.com",
                "username": "photooptional",
                "password1": "ComplexPass123!",
                "password2": "ComplexPass123!",
            },
        )

        self.assertRedirects(response, reverse("feed"))
        user = User.objects.get(username="photooptional")
        self.assertEqual(user.email, "photo-optional@example.com")
        self.assertFalse(user.profile.profile_photo)
        self.assertFalse(user.profile.cover_image)

    def test_daily_quiz_renders_and_scores(self):
        self.client.login(username="alex", password="pass")
        response = self.client.get(reverse("daily_quiz"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Movie and series quiz")
        questions = response.context["questions"]
        self.assertEqual(len(questions), 6)

        post_data = {
            f"question_{index}": question["answer"]
            for index, question in enumerate(questions)
        }
        result = self.client.post(reverse("daily_quiz"), post_data)

        self.assertEqual(result.status_code, 200)
        self.assertContains(result, "6/6")

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

    def test_feed_review_post_shows_inline_error_when_item_not_selected(self):
        self.client.login(username="alex", password="pass")

        response = self.client.post(
            reverse("feed"),
            {
                "item_title": "Unselected Movie",
                "item_type": "movie",
                "rating": 5,
                "review_text": "This should stay on the feed.",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "What are you recommending today?")
        self.assertContains(response, "Please choose an item from the suggestions before posting.")
        self.assertContains(response, "composer-error")
        self.assertFalse(Review.objects.filter(review_text="This should stay on the feed.").exists())

    def test_podcast_review_type_is_not_accepted(self):
        self.client.login(username="alex", password="pass")

        response = self.client.post(
            reverse("feed"),
            {
                "item_title": "https://youtu.be/abc123",
                "item_type": "podcast",
                "rating": 5,
                "review_text": "Worth listening.",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Select a valid choice")
        self.assertFalse(Item.objects.filter(item_type="podcast").exists())
        self.assertFalse(Review.objects.filter(review_text="Worth listening.").exists())

    def test_item_like_save_response_returns_centralized_item_state(self):
        self.client.login(username="alex", password="pass")
        SavedItem.objects.create(user=self.alex, item=self.item, list_type="watchlist")

        response = self.client.post(
            reverse("toggle_saved_item", args=[self.item.id, "favorites"]),
            {"label_context": "like"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["item_id"], self.item.id)
        self.assertEqual(payload["action"], "like")
        self.assertTrue(payload["like_active"])
        self.assertTrue(payload["save_active"])
        self.assertFalse(payload["recommended_active"])

    def test_recommend_response_returns_item_state_for_shared_buttons(self):
        Friendship.objects.create(from_user=self.alex, to_user=self.sam)
        self.client.login(username="alex", password="pass")

        response = self.client.post(
            reverse("recommend"),
            {"item": self.item.id, "to_user": [self.sam.id], "message": "Try this."},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["item_id"], self.item.id)
        self.assertEqual(payload["action"], "recommend")
        self.assertTrue(payload["recommended_active"])

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

    def test_profile_photo_can_be_uploaded_and_deleted(self):
        self.client.login(username="alex", password="pass")
        image = SimpleUploadedFile(
            "avatar.jpg",
            b"fake-image-bytes",
            content_type="image/jpeg",
        )

        upload_response = self.client.post(
            reverse("profile"),
            {
                "first_name": "Alex Reader",
                "username": "alex",
                "bio": "",
                "location": "",
                "website": "",
                "favorite_categories": "",
                "profile_photo": image,
            },
        )

        self.assertRedirects(upload_response, reverse("profile"))
        self.alex.profile.refresh_from_db()
        self.assertTrue(self.alex.profile.profile_photo)

        delete_response = self.client.post(reverse("delete_profile_photo"))

        self.assertRedirects(delete_response, reverse("profile"))
        self.alex.profile.refresh_from_db()
        self.assertFalse(self.alex.profile.profile_photo)
