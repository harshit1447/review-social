from django.urls import path 
from . import views

urlpatterns = [
    path("", views.landing, name="landing"),
    path("feed/", views.feed, name="feed"),
    path("discover/", views.discover, name="discover"),
    path("search/", views.search, name="search"),
    path("signup/", views.signup, name="signup"),
    path("friends/", views.friends, name="friends"),
    path("friends/add/<int:user_id>/", views.add_friend, name="add_friend"),
    path("friends/remove/<int:user_id>/", views.remove_friend, name="remove_friend"),
    path("reviews/new/", views.new_review, name="new_review"),
    path("items/suggest/", views.suggest_items, name="suggest_items"),
    path("items/<int:item_id>/", views.item_reviews, name="item_reviews"),
    path("reviews/<int:review_id>/like/", views.toggle_like, name="toggle_like"),
    path("items/<int:item_id>/save/<str:list_type>/", views.toggle_saved_item, name="toggle_saved_item"),
    path("recommend/", views.recommend, name="recommend"),
    path("profile/", views.profile, name="profile"),
]
