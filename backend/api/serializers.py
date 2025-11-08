from django.contrib.auth import get_user_model
from djoser.serializers import UserCreateSerializer, UserSerializer
from drf_extra_fields.fields import Base64ImageField

from rest_framework import serializers
from rest_framework.fields import IntegerField, SerializerMethodField
from rest_framework.serializers import SerializerMethodField

from recipes.models import Ingredient, IngredientAmount, Recipe, Tag, Favorite
from users.models import Subscribe
from recipes.models import ShoppingCart

User = get_user_model()


class CustomUserCreateSerializer(UserCreateSerializer):
    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ('id', 'email', 'username', 'first_name', 'last_name', 'password')
        read_only_fields = ('id',)

    def create(self, validated_data):
        user = User.objects.create_user(**validated_data)
        return user


class CustomUserSerializer(UserSerializer):
    is_subscribed = SerializerMethodField(read_only=True)
    avatar = serializers.SerializerMethodField()

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
        """Гарантированно возвращает строку (URL или пустую строку)"""
        if not obj.avatar:
            return ""
        try:
            request = self.context.get('request')
            if request and hasattr(obj.avatar, 'url'):
                return request.build_absolute_uri(obj.avatar.url)
            elif hasattr(obj.avatar, 'url'):
                return obj.avatar.url
            else:
                return ""
        except Exception:
            return ""

    def get_is_subscribed(self, obj):
        user = self.context.get('request').user
        if user.is_anonymous:
            return False
        return Subscribe.objects.filter(user=user, author=obj).exists()


class SubscribeSerializer(CustomUserSerializer):
    is_subscribed = serializers.SerializerMethodField()
    recipes_count = SerializerMethodField()
    recipes = SerializerMethodField()
    avatar = serializers.SerializerMethodField()

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

    def get_is_subscribed(self, obj):
        """Проверяем, подписан ли текущий пользователь на этого автора"""
        user = self.context.get('request').user
        if user.is_authenticated:
            return Subscribe.objects.filter(
                user=user, 
                author=obj
            ).exists()
        return False

    def get_recipes(self, obj):
        """Получаем рецепты автора с поддержкой recipes_limit"""
        request = self.context.get('request')
        recipes_limit = request.query_params.get('recipes_limit') if request else None
        recipes = obj.recipes.all()
        if recipes_limit:
            try:
                recipes = recipes[:int(recipes_limit)]
            except (ValueError, TypeError):
                pass
        return RecipeShortSerializer(recipes, many=True).data

    def get_recipes_count(self, obj):
        """Получаем общее количество рецептов автора"""
        return obj.recipes.count()


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

    is_favorited = serializers.BooleanField(read_only=True, default=False)
    is_in_shopping_cart = serializers.BooleanField(
        read_only=True,
        default=False
    )

    def get_ingredients(self, obj):
        ingredients = IngredientAmount.objects.filter(recipe=obj)
        return IngredientRecipeSerializer(ingredients, many=True).data

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
        if not request or request.user.is_anonymous:
            return False
        return obj.shopping_list.filter(user=request.user).exists()

    class Meta:
        model = Recipe
        fields = (
            'id', 'tags', 'author', 'ingredients', 'is_favorited',
            'is_in_shopping_cart', 'name', 'image', 'text', 'cooking_time'
        )


class CreateRecipeSerializer(serializers.ModelSerializer):
    ingredients = IngredientRecipeSerializer(
        many=True,
    )
    tags = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=Tag.objects.all(),
        error_messages={'does_not_exist': 'Указанного тега не существует'}
    )
    image = Base64ImageField(max_length=None)
    author = UserSerializer(read_only=True)
    is_favorited = serializers.BooleanField(read_only=True, default=False)
    is_in_shopping_cart = serializers.BooleanField(
        read_only=True,
        default=False
    )
    cooking_time = serializers.IntegerField()

    class Meta:
        model = Recipe
        fields = (
            'id', 'tags', 'author', 'ingredients',
            'name', 'image', 'text', 'cooking_time',
            'is_favorited', 'is_in_shopping_cart',
        )

    def validate_tags(self, value):
        if not value:
            raise serializers.ValidationError('Добавьте хотя бы один тег')
        if len(value) != len(set(value)):
            raise serializers.ValidationError('Теги не должны повторяться')
        return value

    def validate_cooking_time(self, value):
        """Проверка времени приготовления"""
        if value <= 0:
            raise serializers.ValidationError(
                "Время приготовления должно быть больше 0."
            )
        return value
    
    def validate(self, data):
        """Общая валидация"""
        # Проверяем, что все обязательные поля присутствуют при создании
        if self.context['request'].method in ['POST', 'PUT', 'PATCH']:
            required_fields = ['tags', 'ingredients', 'name', 'image', 'text', 'cooking_time']
            for field in required_fields:
                if field not in data or not data[field]:
                    raise serializers.ValidationError(
                        {field: "Это поле обязательно."}
                    )
        
        return data

    def validate_ingredients(self, value):
        """Проверка ингредиентов"""
        if not value:
            raise serializers.ValidationError(
                "Должен быть указан хотя бы один ингредиент."
            )
        
        # Проверка на дубликаты ингредиентов
        ingredients_ids = [item['id'].id for item in value]
        if len(ingredients_ids) != len(set(ingredients_ids)):
            raise serializers.ValidationError(
                "Ингредиенты не должны повторяться."
            )
        
        # Проверка количества ингредиентов
        for ingredient in value:
            if ingredient['amount'] <= 0:
                raise serializers.ValidationError(
                    "Количество ингредиента должно быть больше 0."
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
        recipe.tags.set(tags_data)
        
        # Создаем ингредиенты
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
        
        return recipe

    def update(self, instance, validated_data):
        tags_data = validated_data.pop('tags', None)
        ingredients_data = validated_data.pop('ingredients', None)
        
        # Обновляем основные поля
        instance = super().update(instance, validated_data)
        
        # Обновляем теги
        if tags_data is not None:
            instance.tags.set(tags_data)
        
        # Обновляем ингредиенты
        if ingredients_data is not None:
            # Удаляем старые ингредиенты
            instance.ingredient_amounts.all().delete()
            
            # Создаем новые
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

    def to_representation(self, instance):
        """После создания возвращаем данные в формате для чтения"""
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
            raise serializers.ValidationError("Рецепт уже в избранном.")
        return value


class ShoppingCartSerializer(serializers.ModelSerializer):
    """Сериализатор для списка покупок """

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
