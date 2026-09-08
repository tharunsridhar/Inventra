from django.urls import path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenBlacklistView, TokenObtainPairView, TokenRefreshView

from apps.accounts.views import MeView, RegisterView, UserViewSet

router = DefaultRouter()
router.register("users", UserViewSet, basename="user")


class ThrottledTokenObtainPairView(TokenObtainPairView):
    throttle_scope = "auth"


class ThrottledTokenRefreshView(TokenRefreshView):
    throttle_scope = "auth"


class ThrottledTokenBlacklistView(TokenBlacklistView):
    throttle_scope = "auth"


urlpatterns = [
    path("auth/register", RegisterView.as_view(), name="register"),
    # SimpleJWT's built-in views are the DRF equivalent of
    # fastapi_users.get_auth_router(auth_backend) - login/refresh/logout
    # come from the library, not hand-written route handlers. Subclassed
    # only to attach throttle_scope="auth" (ScopedRateThrottle reads it off
    # the view class, so it can't be set any other way for a library view).
    path("auth/login", ThrottledTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("auth/refresh", ThrottledTokenRefreshView.as_view(), name="token_refresh"),
    path("auth/logout", ThrottledTokenBlacklistView.as_view(), name="token_blacklist"),
    path("users/me", MeView.as_view(), name="me"),
] + router.urls
