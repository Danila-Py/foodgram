from django.contrib.auth import get_user_model
from django.db.models import Q
from django_filters.rest_framework import (
    FilterSet,
    BooleanFilter,
    CharFilter,
    NumberFilter,
    ModelMultipleChoiceFilter,
)
from recipes.models import Ingredient, Recipe, Tag

User = get_user_model()


class IngredientFilter(FilterSet):
    name = CharFilter(method='filter_name')

    def filter_name(self, queryset, value):
        if not value:
            return queryset
        return queryset.filter(
            Q(name__icontains=value) | Q(name__istartswith=value)
        ).distinct()

    class Meta:
        model = Ingredient
        fields = ['name']


class RecipeFilter(FilterSet):
    tags = ModelMultipleChoiceFilter(
        field_name='tags__slug',
        to_field_name='slug',
        queryset=Tag.objects.all(),
        conjoined=False,
        label='Теги'
    )
    author = NumberFilter(field_name='author__id')
    is_favorited = BooleanFilter(method='filter_is_favorited')
    is_in_shopping_cart = BooleanFilter(method='filter_is_in_shopping_cart')

    def filter_is_favorited(self, queryset, name, value):
        user = self.request.user
        if value and user.is_authenticated:
            return queryset.filter(favorites__user=user)
        return queryset

    def filter_is_in_shopping_cart(self, queryset, name, value):
        user = self.request.user
        if value and user.is_authenticated:
            return queryset.filter(cart__user=user)
        return queryset

    class Meta:
        model = Recipe
        fields = ['tags', 'author', 'is_favorited', 'is_in_shopping_cart']
