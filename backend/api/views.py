import base64
from io import BytesIO

from django.core.files.base import ContentFile
from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from djoser.views import UserViewSet
from django.db.models import Count
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from django.utils import timezone
from django.db.models import Sum
from django.http import HttpResponse
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status
from rest_framework import filters
from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet

from api.pagination import CustomPagination
from users.models import Subscribe
from recipes.models import (
    Favorite,
    Ingredient,
    IngredientAmount,
    Recipe,
    ShoppingCart,
    Tag,
)
from api.filters import RecipeFilter, IngredientFilter
from api.permissions import IsAuthorOrReadOnly
from api.serializers import (
    IngredientSerializer,
    ShoppingCartSerializer,
    RecipeReadSerializer,
    TagSerializer,
    FavoriteSerializer,
    CreateRecipeSerializer,
    CustomUserSerializer,
    SubscribeSerializer,
    CustomUserCreateSerializer,
    AvatarSerializer,
    SubscribeDeleteSerializer,
)

User = get_user_model()


class CustomUserViewSet(UserViewSet):
    queryset = User.objects.all()
    serializer_class = CustomUserSerializer
    pagination_class = CustomPagination

    def get_permissions(self):
        if self.action == 'create':
            return [AllowAny()]
        elif self.action in ['retrieve', 'list']:
            return [AllowAny()]
        else:
            return [IsAuthenticated()]

    def get_serializer_class(self):
        if self.action == 'create':
            return CustomUserCreateSerializer
        elif self.action == 'avatar':
            return AvatarSerializer
        return CustomUserSerializer

    @action(
        detail=False,
        methods=['get', 'put', 'patch', 'delete'],
        permission_classes=[IsAuthenticated],
        url_path='me/avatar'
    )
    def avatar(self, request):
        user = request.user

        if request.method == 'GET':
            return Response(
                {'avatar': user.avatar.url if user.avatar else None},
                status=status.HTTP_200_OK
            )

        elif request.method in ['PUT', 'PATCH']:
            serializer = self.get_serializer(
                user,
                data=request.data,
                partial=(request.method == 'PATCH')
            )
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)

        elif request.method == 'DELETE':
            if user.avatar:
                user.avatar.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)

    @action(
        detail=False,
        methods=['post'],
        permission_classes=[IsAuthenticated]
    )
    def set_password(self, request):
        user = request.user
        current_password = request.data.get('current_password')
        new_password = request.data.get('new_password')
        if not current_password or not new_password:
            return Response(
                {'error': 'Требуются текущий пароль и новый пароль'},
                status=status.HTTP_400_BAD_REQUEST
            )
        if not user.check_password(current_password):
            return Response(
                {'current_password': 'Неверный текущий пароль'},
                status=status.HTTP_400_BAD_REQUEST
            )
        user.set_password(new_password)
        user.save()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(
        detail=True,
        methods=['post', 'delete'],
        permission_classes=[IsAuthenticated]
    )
    def subscribe(self, request, id=None):
        user = request.user
        author = get_object_or_404(User, id=id)

        if user == author:
            return Response(
                {'error': 'Нельзя подписаться на самого себя'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if request.method == 'POST':
            serializer = SubscribeSerializer(
                data={'user': user.id, 'author': author.id},
                context={'request': request}
            )
            serializer.is_valid(raise_exception=True)
            serializer.save()
            author_serializer = SubscribeSerializer(
                author,
                context={'request': request}
            )
            return Response(
                author_serializer.data,
                status=status.HTTP_201_CREATED
            )

        elif request.method == 'DELETE':
            serializer = SubscribeDeleteSerializer(
                data={},
                context={'request': request, 'author': author}
            )
            serializer.is_valid(raise_exception=True)
            Subscribe.objects.filter(user=user, author=author).delete()
            return Response(status=status.HTTP_204_NO_CONTENT)

    @action(
        detail=False,
        methods=['get'],
        permission_classes=[IsAuthenticated],
        pagination_class=CustomPagination
    )
    def subscriptions(self, request):
        user = request.user
        queryset = User.objects.filter(subscribing__user=user).annotate(
            recipes_count=Count('recipes')
        )
        page = self.paginate_queryset(queryset)
        serializer = SubscribeSerializer(
            page,
            many=True,
            context={'request': request}
        )
        return self.get_paginated_response(serializer.data)


class IngredientViewSet(ReadOnlyModelViewSet):
    serializer_class = IngredientSerializer
    filter_backends = [filters.SearchFilter]
    filterset_class = IngredientFilter

    def get_queryset(self):
        queryset = Ingredient.objects.all()
        name = self.request.query_params.get('name')
        if name:
            queryset = queryset.filter(name__istartswith=name)
        return queryset


class TagViewSet(ReadOnlyModelViewSet):
    queryset = Tag.objects.all()
    serializer_class = TagSerializer
    pagination_class = None


class RecipeViewSet(ModelViewSet):
    permission_classes = [IsAuthorOrReadOnly]
    pagination_class = CustomPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_class = RecipeFilter

    def get_queryset(self):
        return Recipe.objects.select_related('author').prefetch_related('tags')

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)

    def get_serializer_class(self):
        if self.action in ('list', 'retrieve'):
            return RecipeReadSerializer
        return CreateRecipeSerializer

    @action(
        detail=True,
        methods=['get'],
        permission_classes=[AllowAny],
        url_path='get-link'
    )
    def get_recipe_link(self, request, pk=None):
        recipe = get_object_or_404(Recipe, pk=pk)

        recipe_url = request.build_absolute_uri(
            f'/api/recipes/{recipe.id}/'
        )
        return Response(
            {
                'short-link': recipe_url
            },
            status=status.HTTP_200_OK
        )

    @action(
        detail=True,
        methods=['post'],
        permission_classes=[IsAuthorOrReadOnly]
    )
    def favorite(self, request, pk):
        context = {'request': request}
        recipe = get_object_or_404(Recipe, id=pk)
        data = {
            'user': request.user.id,
            'recipe': recipe.id
        }
        serializer = FavoriteSerializer(data=data, context=context)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @favorite.mapping.delete
    def remove_from_favorites(self, request, pk=None):
        recipe = get_object_or_404(Recipe, pk=pk)
        favorite = Favorite.objects.filter(user=request.user, recipe=recipe)

        if not favorite.exists():
            return Response(
                {'error': 'Рецепт не был добавлен в избранное.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        favorite.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(
        detail=True,
        methods=['post'],
        permission_classes=[IsAuthorOrReadOnly]
    )
    def shopping_cart(self, request, pk):
        context = {'request': request}
        recipe = get_object_or_404(Recipe, id=pk)
        data = {
            'user': request.user.id,
            'recipe': recipe.id
        }
        serializer = ShoppingCartSerializer(data=data, context=context)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @shopping_cart.mapping.delete
    def remove_from_cart(self, request, pk=None):
        recipe = get_object_or_404(Recipe, pk=pk)
        cart_item = ShoppingCart.objects.filter(
            user=request.user,
            recipe=recipe
        )

        if not cart_item.exists():
            return Response(
                {'error': 'Рецепт не был добавлен в корзину.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        cart_item.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    def generate_shopping_list_file(self, user, ingredients):
        today = timezone.now()
        shopping_list = (
            f'Список покупок для: {user.get_full_name() or user.username}\n\n'
            f'Дата: {today:%Y-%m-%d}\n\n'
        )
        shopping_list += '\n'.join([
            f'- {ingredient["ingredient__name"]} '
            f'({ingredient["ingredient__measurement_unit"]})'
            f' - {ingredient["total_amount"]}'
            for ingredient in ingredients
        ])
        shopping_list += f'\n\nFoodgram ({today:%Y})'
        buffer = BytesIO()
        buffer.write(shopping_list.encode('utf-8'))
        buffer.seek(0)
        return buffer

    @action(
        detail=False,
        methods=['get'],
        permission_classes=[IsAuthorOrReadOnly]
    )
    def download_shopping_cart(self, request):
        user = request.user
        if not user.cart.exists():
            return Response(
                {'error': 'Корзина покупок пуста'},
                status=status.HTTP_400_BAD_REQUEST
            )
        ingredients = IngredientAmount.objects.filter(
            recipe__cart__user=user
        ).values(
            'ingredient__name',
            'ingredient__measurement_unit'
        ).annotate(total_amount=Sum('amount'))
        buffer = self.generate_shopping_list_file(user, ingredients)
        filename = f'{user.username}_shopping_list.txt'
        response = HttpResponse(
            buffer.getvalue(),
            content_type='text/plain; charset=utf-8'
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
