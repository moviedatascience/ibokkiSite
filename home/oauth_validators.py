"""OIDC claim mapping for the ibokki -> Fluxer SSO integration.

Fluxer reads standard OIDC claims (email, preferred_username) plus our custom
`role` claim from the ID token / userinfo response. Each claim is gated behind
the scope that carries it via `oidc_claim_scope`.
"""
from oauth2_provider.oauth2_validators import OAuth2Validator


class IbokkiOAuth2Validator(OAuth2Validator):
    # Map each claim to the scope that must be granted for it to be returned.
    oidc_claim_scope = {
        **OAuth2Validator.oidc_claim_scope,
        "email": "email",
        "email_verified": "email",
        "preferred_username": "profile",
        "name": "profile",
        "role": "roles",
        # Active podcast subscriptions, exposed so Fluxer can gate communities
        # by entitlement once it supports claim-based access.
        "entitlements": "profile",
    }

    def get_additional_claims(self, request):
        user = request.user
        display = user.display_name or user.username
        return {
            "email": user.email,
            "email_verified": True,
            "preferred_username": display,
            "name": display,
            "role": user.role,
            "entitlements": user.active_podcast_slugs(),
        }
