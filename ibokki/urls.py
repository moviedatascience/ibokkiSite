"""
URL configuration for ibokki project.
"""

from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    # OpenID Connect provider endpoints (authorize, token, userinfo, jwks,
    # and /o/.well-known/openid-configuration). Used by Fluxer SSO.
    path('o/', include('oauth2_provider.urls', namespace='oauth2_provider')),
    path('', include('home.urls')),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
