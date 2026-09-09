"""OAuth resource-server verification, independent of any client or IdP brand."""

import asyncio
import logging

import jwt
from mcp.server.auth.provider import AccessToken

from .settings import MCPSettings

logger = logging.getLogger(__name__)


class JWTVerifier:
    """Verify signed access tokens; never follow issuer/key URLs from the token."""

    def __init__(self, settings: MCPSettings):
        self.settings = settings
        self.jwks = jwt.PyJWKClient(
            settings.jwks_url, cache_jwk_set=True, lifespan=300, timeout=5
        )

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            # Key fetch and refresh use bounded blocking HTTP; keep off the event loop.
            key = await asyncio.to_thread(self.jwks.get_signing_key_from_jwt, token)
            claims = jwt.decode(
                token,
                key.key,
                algorithms=["RS256", "ES256"],
                audience=self.settings.audience,
                issuer=self.settings.issuer,
                options={"require": ["exp", "iss", "aud", "sub"]},
            )
            subject = claims["sub"]
            scope = claims.get("scope", claims.get("scp", ""))
            if (
                not isinstance(subject, str)
                or not subject.strip()
                or not isinstance(scope, str)
            ):
                return None
            return AccessToken(
                token=token,
                client_id=str(claims.get("client_id", claims.get("azp", subject))),
                subject=subject,
                scopes=scope.split(),
                expires_at=int(claims["exp"]),
                resource=self.settings.url,
            )
        except jwt.PyJWKClientError:
            # Never log the token, decoded claims, or untrusted exception message.
            logger.warning("MCP signing-key verification unavailable")
            return None
        except (jwt.PyJWTError, ValueError, TypeError, KeyError):
            return None
