from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Subscribe, User


@admin.register(User)
class CustomUsersAdmin(UserAdmin):
    list_display = (
        'username',
        'id',
        'email',
        'first_name',
        'last_name',
    )
    list_filter = (
        'email',
        'first_name',
        'is_active',
        'is_superuser',
    )
    search_fields = (
        'email',
        'username',
        'first_name',
        'last_name',
    )

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related(
            'recipes'
        )


@admin.register(Subscribe)
class SubscribeAdmin(admin.ModelAdmin):
    list_display = ('user', 'author',)
    list_filter = ('user', 'author')
    search_fields = ('user__username', 'author__username')

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'user', 'author'
        )
