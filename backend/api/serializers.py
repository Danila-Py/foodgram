import base64

from django.core.files.base import ContentFile
from django.contrib.auth import get_user_model
from djoser.serializers import UserCreateSerializer, UserSerializer
from drf_extra_fields.fields import Base64ImageField

from rest_framework import serializers
from rest_framework.fields import IntegerField, SerializerMethodField

from recipes.models import Ingredient, IngredientAmount, Recipe, Tag, Favorite
from users.models import Subscribe
from recipes.models import ShoppingCart

User = get_user_model()


class AvatarSerializer(serializers.ModelSerializer):
    avatar = serializers.CharField(required=False)
    avatar_file = serializers.ImageField(required=False, write_only=True)

    class Meta:
        model = User
        fields = ['avatar', 'avatar_file']
        read_only_fields = ['avatar']

    def validate(self, data):
        if not data.get('avatar') and not data.get('avatar_file'):
            raise serializers.ValidationError({
                'avatar': 'Должен быть передан как файл или base64 строка.'
            })
        return data

    def validate_avatar(self, value):
        if value and not value.startswith('data:image'):
            raise serializers.ValidationError(
                'Некорректный формат base64 строки'
            )
        return value

    def update(self, instance, validated_data):
        avatar_data = validated_data.get('avatar')
        avatar_file = validated_data.get('avatar_file')

        try:
            if avatar_data:
                format, imgstr = avatar_data.split(';base64,')
                ext = format.split('/')[-1]
                data = ContentFile(
                    base64.b64decode(imgstr),
                    name=f'avatar_{instance.id}.{ext}'
                )
                instance.avatar.save(
                    f'avatar_{instance.id}.{ext}',
                    data,
                    save=True
                )
            elif avatar_file:
                instance.avatar = avatar_file
                instance.save()
        except Exception as e:
            raise serializers.ValidationError({
                'avatar': f'Ошибка обработки изображения: {str(e)}'
            })
        return instance

    def to_representation(self, instance):
        return {
            'avatar': instance.avatar.url if instance.avatar else None
        }


class CustomUserCreateSerializer(UserCreateSerializer):
    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = (
            'id',
            'email',
            'username',
            'first_name',
            'last_name',
            'password'
        )
        read_only_fields = ('id',)

    def create(self, validated_data):
        user = User.objects.create_user(**validated_data)
        return user


class CustomUserSerializer(UserSerializer):
    is_subscribed = SerializerMethodField(read_only=True)
    avatar = SerializerMethodField()

    class Meta:
        model = User
        fields = (
            'email',
            'id',
            'username',
            'first_name',
            'last_name',
            'is_subscribed',
            'avatar',
        )

    def get_avatar(self, obj):
        if not obj.avatar:
            return ''
        try:
            request = self.context.get('request')
            if request and hasattr(obj.avatar, 'url'):
                return request.build_absolute_uri(obj.avatar.url)
            elif hasattr(obj.avatar, 'url'):
                return obj.avatar.url
        except Exception:
            return ''

    def get_is_subscribed(self, obj):
        user = self.context.get('request').user
        if user.is_anonymous:
            return False
        return Subscribe.objects.filter(user=user, author=obj).exists()


class SubscribeSerializer(CustomUserSerializer):
    is_subscribed = SerializerMethodField()
    recipes_count = IntegerField(read_only=True)
    recipes = SerializerMethodField()
    avatar = SerializerMethodField()

    class Meta(CustomUserSerializer):
        model = User
        fields = (
            'email',
            'id',
            'username',
            'first_name',
            'last_name',
            'is_subscribed',
            'recipes_count',
            'recipes',
            'avatar',
        )
        read_only_fields = ('email', 'username')

    def validate(self, data):
        user = data['user']
        author = data['author']
        if user == author:
            raise serializers.ValidationError(
                'Нельзя подписаться на самого себя'
            )
        if Subscribe.objects.filter(user=user, author=author).exists():
            raise serializers.ValidationError(
                'Вы уже подписаны на этого автора'
            )
        return data

    def get_is_subscribed(self, obj):
        return True

    def get_recipes(self, obj):
        request = self.context.get('request')
        recipes_limit = request.query_params.get(
            'recipes_limit'
        ) if request else None
        recipes = obj.recipes.all()
        if recipes_limit:
            if isinstance(recipes_limit, str) and recipes_limit.isdigit():
                recipes = recipes[:int(recipes_limit)]
        return RecipeShortSerializer(recipes, many=True).data


class IngredientSerializer(serializers.ModelSerializer):

    class Meta:
        model = Ingredient
        fields = ('id', 'name', 'measurement_unit')


class TagSerializer(serializers.ModelSerializer):

    class Meta:
        model = Tag
        fields = ('id', 'name', 'slug')


class IngredientRecipeSerializer(serializers.ModelSerializer):
    id = serializers.PrimaryKeyRelatedField(queryset=Ingredient.objects.all())
    name = serializers.CharField(source='ingredient.name', read_only=True)
    measurement_unit = serializers.CharField(
        source='ingredient.measurement_unit',
        read_only=True
    )

    class Meta:
        model = IngredientAmount
        fields = ['id', 'name', 'measurement_unit', 'amount']


class RecipeReadSerializer(serializers.ModelSerializer):
    id = IntegerField(read_only=True)
    author = CustomUserSerializer(read_only=True)
    tags = TagSerializer(many=True, read_only=True)
    ingredients = IngredientRecipeSerializer(
        many=True,
        read_only=True,
        source='ingredient_amounts'
    )
    image = Base64ImageField()

    is_favorited = serializers.SerializerMethodField()
    is_in_shopping_cart = serializers.SerializerMethodField()

    class Meta:
        model = Recipe
        fields = (
            'id', 'tags', 'author', 'ingredients', 'is_favorited',
            'is_in_shopping_cart', 'name', 'image', 'text', 'cooking_time'
        )

    def get_is_favorited(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return Favorite.objects.filter(
                user=request.user,
                recipe=obj
            ).exists()
        return False

    def get_is_in_shopping_cart(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return ShoppingCart.objects.filter(
                user=request.user,
                recipe=obj
            ).exists()
        return False

    def get_ingredients(self, obj):
        ingredients = IngredientAmount.objects.filter(recipe=obj)
        return IngredientRecipeSerializer(ingredients, many=True).data


class CreateRecipeSerializer(serializers.ModelSerializer):
    ingredients = IngredientRecipeSerializer(
        many=True,
        required=True,
        allow_empty=False
    )
    tags = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=Tag.objects.all(),
        required=True,
        allow_empty=False,
        error_messages={
            'does_not_exist': 'Указанного тега не существует',
            'empty': 'Добавьте хотя бы один тег'
        }
    )
    image = Base64ImageField(
        max_length=None,
        required=True,
        allow_empty_file=False,
        error_messages={
            'required': 'Изображение обязательно.',
            'empty': 'Изображение не может быть пустым.'
        }
    )
    author = UserSerializer(read_only=True)
    is_favorited = serializers.BooleanField(read_only=True, default=False)
    is_in_shopping_cart = serializers.BooleanField(
        read_only=True,
        default=False
    )
    cooking_time = serializers.IntegerField(
        required=True,
        min_value=1,
        error_messages={
            'min_value': 'Время приготовления должно быть больше 0.',
            'required': 'Время приготовления обязательно.'
        }
    )

    class Meta:
        model = Recipe
        fields = (
            'id', 'tags', 'author', 'ingredients',
            'name', 'image', 'text', 'cooking_time',
            'is_favorited', 'is_in_shopping_cart',
        )

    def validate_tags(self, value):
        if len(value) != len(set(value)):
            raise serializers.ValidationError('Теги не должны повторяться')
        return value

    def validate_cooking_time(self, value):
        if value <= 0:
            raise serializers.ValidationError(
                'Время приготовления должно быть больше 0.'
            )
        return value

    def validate(self, data):
        if not data.get('tags'):
            raise serializers.ValidationError(
                {'tags': 'Добавьте хотя бы один тег'}
            )
        if not data.get('ingredients'):
            raise serializers.ValidationError(
                {'ingredients': 'Добавьте хотя бы один ингредиент'}
            )
        if not data.get('image'):
            raise serializers.ValidationError(
                {'image': 'Изображение обязательно.'}
            )
        return data

    def validate_ingredients(self, value):
        ingredients_ids = [item['id'].id for item in value]
        if len(ingredients_ids) != len(set(ingredients_ids)):
            raise serializers.ValidationError(
                'Ингредиенты не должны повторяться.'
            )
        for ingredient in value:
            if ingredient['amount'] <= 0:
                raise serializers.ValidationError(
                    'Количество ингредиента должно быть больше 0.'
                )
        return value

    def create_ingredients(self, ingredients, recipe):
        IngredientAmount.objects.bulk_create([
            IngredientAmount(
                recipe=recipe,
                ingredient=ingredient['id'],
                amount=ingredient['amount']
            ) for ingredient in ingredients
        ])

    def create(self, validated_data):
        tags_data = validated_data.pop('tags')
        ingredients_data = validated_data.pop('ingredients')
        recipe = Recipe.objects.create(**validated_data)
        self._add_tags_and_ingredients(recipe, tags_data, ingredients_data)
        return recipe

    def update(self, instance, validated_data):
        tags_data = validated_data.pop('tags', None)
        ingredients_data = validated_data.pop('ingredients', None)
        instance = super().update(instance, validated_data)
        if tags_data is not None:
            instance.tags.set(tags_data)
    
        if ingredients_data is not None:
            instance.ingredient_amounts.all().delete()
            ingredient_amounts = []
            for ingredient_data in ingredients_data:
                ingredient = ingredient_data['id']
                amount = ingredient_data['amount']
                ingredient_amounts.append(
                    IngredientAmount(
                        recipe=instance,
                        ingredient=ingredient,
                        amount=amount
                    )
                )
            IngredientAmount.objects.bulk_create(ingredient_amounts)
    
        return instance

    def _add_tags_and_ingredients(self, recipe, tags_data, ingredients_data):
        recipe.tags.set(tags_data)
        ingredient_amounts = []
        for ingredient_data in ingredients_data:
            ingredient = ingredient_data['id']
            amount = ingredient_data['amount']
            ingredient_amounts.append(
                IngredientAmount(
                    recipe=recipe,
                    ingredient=ingredient,
                    amount=amount
                )
            )
        IngredientAmount.objects.bulk_create(ingredient_amounts)

    def to_representation(self, instance):
        return RecipeReadSerializer(instance, context=self.context).data


class RecipeShortSerializer(serializers.ModelSerializer):

    class Meta:
        model = Recipe
        fields = ('id', 'name', 'image', 'cooking_time')


class FavoriteSerializer(serializers.ModelSerializer):

    class Meta:
        model = Favorite
        fields = ('user', 'recipe')

    def to_representation(self, instance):
        return RecipeShortSerializer(instance.recipe).data

    def validate_recipe(self, value):
        user = self.context['request'].user
        if Favorite.objects.filter(user=user, recipe=value).exists():
            raise serializers.ValidationError('Рецепт уже в избранном.')
        return value


class ShoppingCartSerializer(serializers.ModelSerializer):

    class Meta:
        model = ShoppingCart
        fields = ('user', 'recipe')

    def to_representation(self, instance):
        return RecipeShortSerializer(instance.recipe).data

    def validate(self, data):
        user = data['user']
        recipe = data['recipe']
        if ShoppingCart.objects.filter(user=user, recipe=recipe).exists():
            raise serializers.ValidationError(
                'Уже добавлен в корзину'
            )
        return data
