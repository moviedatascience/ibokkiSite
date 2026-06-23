from django.urls import path
from . import views

urlpatterns = [
    path('', views.login_view, name='login'),
    path('home/', views.landing_page, name='landing'),
    path('register/', views.register_view, name='register'),
    path('register/<str:token>/', views.register_invite_view, name='register_invite'),
    path('verify-email/<str:token>/', views.verify_email_view, name='verify_email'),
    path('invite/', views.send_invite_view, name='invite'),
    path('forgot-password/', views.forgot_password_view, name='forgot_password'),
    path('reset-password/<str:token>/', views.reset_password_view, name='reset_password'),
    path('watch/', views.watch, name='watch'),
    path('videos/', views.all_videos, name='all_videos'),

    # Subscription checkout
    path('subscribe/', views.subscribe_index, name='subscribe'),
    path('subscribe/<int:product_id>/checkout/', views.checkout, name='checkout'),
    path('subscribe/success/<int:pk>/', views.checkout_success, name='checkout_success'),

    # Forum
    path('forum/', views.forum_index, name='forum_index'),
    path('forum/c/<slug:slug>/', views.forum_category, name='forum_category'),
    path('forum/c/<slug:slug>/new/', views.forum_new_thread, name='forum_new_thread'),
    path('forum/t/<int:pk>/', views.forum_thread, name='forum_thread'),
    path('forum/t/<int:pk>/reply/', views.forum_reply, name='forum_reply'),

    # Announcements
    path('announcements/', views.announcement_list, name='announcement_list'),
    path('announcements/<int:pk>/', views.announcement_detail, name='announcement_detail'),
    path('manage/announcements/', views.announcement_admin, name='announcement_admin'),
    path('manage/announcements/<int:pk>/edit/', views.announcement_edit, name='announcement_edit'),
    path('manage/announcements/<int:pk>/delete/', views.announcement_delete, name='announcement_delete'),

    path('emotes/manifest/', views.emote_manifest, name='emote_manifest'),
    path('emotes/favorite/', views.toggle_emote_favorite, name='toggle_emote_favorite'),
    path('switch-stream/', views.switch_stream, name='switch_stream'),
    path('profile/', views.profile_view, name='profile'),
]
