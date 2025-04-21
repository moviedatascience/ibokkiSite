from django.urls import path
from . import views

urlpatterns = [
    path('', views.landing_page, name='landing'),
    path('discord/login/', views.discord_login, name='discord_login'),
    path('discord/callback', views.discord_callback, name='discord_callback'),
    path('watch/', views.watch, name='watch'),
    path('switch-stream/', views.switch_stream, name='switch_stream'),
    path('profile/', views.profile_view, name='profile'),
] 