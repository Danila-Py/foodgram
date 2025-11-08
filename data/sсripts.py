import json

with open('./data/ingredients.json', 'r') as file:
    data = json.load(file)

transformed_data = []
for item in data:
    transformed_item = {
        "model": "recipes.Ingredient",
        "fields": {
            "name": item["name"],
            "measurement_unit": item["measurement_unit"]
        }
    }
    transformed_data.append(transformed_item)

with open('new_ingredients.json', 'w') as file:
    json.dump(transformed_data, file, ensure_ascii=False, indent=4)
