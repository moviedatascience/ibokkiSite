from django.urls import path
from . import views

urlpatterns = [
    path('', views.login_view, name='login'),
    path('home/', views.landing_page, name='landing'),
    path('register/<str:token>/', views.register_view, name='register'),
    path('invite/', views.send_invite_view, name='invite'),
    path('forgot-password/', views.forgot_password_view, name='forgot_password'),
    path('reset-password/<str:token>/', views.reset_password_view, name='reset_password'),
    path('watch/', views.watch, name='watch'),
    path('switch-stream/', views.switch_stream, name='switch_stream'),
    path('profile/', views.profile_view, name='profile'),
]
