from django.contrib import admin
from django.contrib.admin import display

from recipes.models import (
    Favorite,
    Ingredient,
    IngredientAmount,
    Recipe,
    ShoppingCart,
    Tag,
)


@admin.register(Recipe)
class RecipeAdmin(admin.ModelAdmin):
    list_display = ('name', 'id', 'author', 'added_in_favorites')
    readonly_fields = ('added_in_favorites',)
    list_filter = ('author', 'tags',)
    search_fields = ('name',)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'author'
        ).prefetch_related(
            'tags',
            'ingredients',
            'favorites',
        )

    @display(description='Количество в избранных')
    def added_in_favorites(self, obj):
        return obj.favorites.count()


@admin.register(Ingredient)
class IngredientAdmin(admin.ModelAdmin):
    list_display = ('name', 'measurement_unit',)
    search_fields = ('name',)


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ('name', 'color', 'slug',)
    search_fields = ('name',)


@admin.register(ShoppingCart)
class ShoppingCartAdmin(admin.ModelAdmin):
    list_display = ('user', 'recipe',)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'user', 'recipe'
        )


@admin.register(Favorite)
class FavoriteAdmin(admin.ModelAdmin):
    list_display = ('user', 'recipe',)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'user', 'recipe__author'
        )


@admin.register(IngredientAmount)
class IngredientAmountAdmin(admin.ModelAdmin):
    list_display = ('recipe', 'ingredient', 'amount',)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'recipe', 'ingredient'
        )
