from django.urls import path
from . import views

urlpatterns = [
    path('', views.landing_page, name='landing'),
    path('discord/login/', views.discord_login, name='discord_login'),
    path('discord/callback', views.discord_callback, name='discord_callback'),
    path('profile/', views.profile_view, name='profile'),
    path('watch/', views.watch_view, name='watch'),
] 