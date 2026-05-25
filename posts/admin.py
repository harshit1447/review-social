from django.contrib import admin
from .models import Friendship, Item, Recommendation, Review

admin.site.register(Item)
admin.site.register(Review)
admin.site.register(Friendship)
admin.site.register(Recommendation)
