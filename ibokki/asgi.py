"""
ASGI config for ibokki project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.1/howto/deployment/asgi/
"""

import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from django.urls import path, re_path
from home.consumers import ChatConsumer

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ibokki.settings")

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": AuthMiddlewareStack(
        URLRouter([
            path("ws/chat/", ChatConsumer.as_asgi()),
            re_path(r"ws/chat/(?P<stream_id>\w+)/$", ChatConsumer.as_asgi()),
        ])
    ),
})
