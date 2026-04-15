from django.urls import path
from apps.billing import views

app_name = "billing"

urlpatterns = [
    path("checkout/<str:plan_key>/",  views.checkout,          name="checkout"),
    path("payment/success/",          views.payment_success,   name="payment_success"),
    path("webhook/yukassa/",          views.yukassa_webhook,   name="yukassa_webhook"),
]
