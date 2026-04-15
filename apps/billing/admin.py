from django.contrib import admin
from .models import Subscription, Payment

@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ('company', 'plan', 'status', 'expires_at')

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('company', 'amount', 'status', 'created_at')