from django.urls import path 
from . import views

urlpatterns = [
    path("", views.feed, name="feed"),
    path("signup/", views.signup, name="signup"),
    path("friends/", views.friends, name="friends"),
    path("friends/add/<int:user_id>/", views.add_friend, name="add_friend"),
    path("friends/remove/<int:user_id>/", views.remove_friend, name="remove_friend"),
    path("reviews/new/", views.new_review, name="new_review"),
    path("recommend/", views.recommend, name="recommend"),
    path("profile/", views.profile, name="profile"),
]
